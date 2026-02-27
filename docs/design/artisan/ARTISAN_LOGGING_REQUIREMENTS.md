# Artisan Logging — Requirements

> **Version:** 1.0.0
> **Status:** Draft (AL-1xx implemented; AL-2xx through AL-7xx planned)
> **Date:** 2026-02-24
> **Scope:** Structured logging requirements for the Artisan 8-phase pipeline — logger acquisition, phase/task lifecycle logging, gate and contract events, operational logging (LLM calls, errors, retries), Loki correlation, and graceful degradation
> **Extends:** `ARTISAN_REQUIREMENTS.md` Layer 6 (AR-6xx Observability)
> **Complements:** `ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md` (traces) — logs provide searchable, Loki-queryable visibility; traces provide span hierarchy and waterfall views
> **Depends on:** AR-600 (root span), AR-601 (phase spans), OT-708 (trace-log exemplars)

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Design Principles](#2-design-principles)
3. [Requirements](#3-requirements)
   - [Layer 1: Logger Acquisition (AL-1xx)](#layer-1-logger-acquisition-al-1xx)
   - [Layer 2: Phase-Lifecycle Logging (AL-2xx)](#layer-2-phase-lifecycle-logging-al-2xx)
   - [Layer 3: Gate and Contract Logging (AL-3xx)](#layer-3-gate-and-contract-logging-al-3xx)
   - [Layer 4: Operational Logging (AL-4xx)](#layer-4-operational-logging-al-4xx)
   - [Layer 5: Loki Correlation (AL-5xx)](#layer-5-loki-correlation-al-5xx)
   - [Layer 6: Structured Logging Conventions (AL-6xx)](#layer-6-structured-logging-conventions-al-6xx)
   - [Layer 7: Graceful Degradation (AL-7xx)](#layer-7-graceful-degradation-al-7xx)
4. [Log Flow Diagram](#4-log-flow-diagram)
5. [Traceability Matrix](#5-traceability-matrix)
6. [Status Dashboard](#6-status-dashboard)
7. [Verification](#7-verification)
8. [Related Documents](#8-related-documents)

---

## 1. Motivation

The Artisan pipeline emits logs from many modules, but without consistent logging requirements, several failure modes occur:

- **Silent telemetry loss** — Modules using `logging.getLogger()` bypass the OTel log bridge; logs never reach Loki even when Promtail is configured. See `PATTERN-silent-telemetry-loss.md` and CLAUDE.md "Must Avoid: Don't use logging.getLogger() directly in contractors/".
- **Trace-log correlation gaps** — Logs without `trace_id`/`span_id` cannot be correlated with Tempo traces, forcing operators to manually cross-reference.
- **Inconsistent log levels** — Phase transitions, gate outcomes, and LLM call outcomes lack standardized level semantics (INFO vs WARNING vs ERROR).
- **Missing operational context** — Retries, cost attribution, and contract violations are not consistently logged with structured fields for Loki querying.

This document specifies logging requirements that complement the OTel tracing layer (OT-1xx through OT-7xx). Traces answer "what happened in what order"; logs answer "what did the system report at each step" and are searchable in Loki. Together they enable full observability.

---

## 2. Design Principles

| Principle | Source Document | Compliance |
|-----------|----------------|------------|
| Fail Visible, Not Silent | `PATTERN-silent-telemetry-loss.md` | AL-100 mandates `get_logger()` so logs reach Loki; AL-7xx requires startup banner when logging pipeline is degraded |
| OTel Log Bridge | `src/startd8/logging_config.py`, `logging_otel.py` | AL-100 ensures all contractor modules use the bridge; AL-5xx mandates trace_id/span_id injection |
| Prescriptive Over Descriptive | `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md` | AL-3xx logs gate outcomes and contract state; AL-4xx logs context propagation diagnostics |
| Mottainai Rule 2: Forward, Don't Regenerate | `MOTTAINAI_DESIGN_PRINCIPLE.md` | Reuses existing `get_logger()`, `JSONFormatter`, `OTelTraceContextFilter`; no new logging infrastructure |
| Loki-Friendly Format | `LOKI_SETUP_GUIDE.md` | AL-6xx defines JSON structure and label cardinality for Promtail ingestion |
| Trace-Log Correlation | OT-708 | AL-5xx ensures logs carry exemplars for Grafana trace-to-log and log-to-trace navigation |

---

## 3. Requirements

### Layer 1: Logger Acquisition (AL-1xx)

All Artisan contractor modules must obtain loggers via the OTel-attached pipeline. Using `logging.getLogger()` directly bypasses the OTel log bridge and causes logs to silently miss Loki.

#### AL-100: get_logger() Mandate

**Status:** implemented (partial — 4 modules still use `logging.getLogger()`)
**Source:** CLAUDE.md "Must Do", `PATTERN-silent-telemetry-loss.md`

All Python modules in `src/startd8/contractors/**` must obtain loggers via `get_logger(__name__)` from `startd8.logging_config`, not `logging.getLogger(...)`.

**Scope note (Phase 1 policy freeze):**
- Applies to all contractor Python files, including `__init__.py`.
- Applies to all logger acquisition sites: module-level loggers, class attributes (for example `self.logger = ...`), and helper/fallback loggers.
- If a file emits logs, all logger acquisition in that file must follow AL-100 unless explicitly allowlisted under AL-101.

**Acceptance criteria:**
1. Every contractor module that emits logs imports `from startd8.logging_config import get_logger` and uses `get_logger(__name__)` for logger acquisition by default.
2. No contractor module directly calls `logging.getLogger(...)` unless explicitly documented in the AL-101 exception allowlist.
3. The `get_logger()` call triggers `_ensure_default_log_file_handler()` which attaches `OTelLogHandler` and `OTelTraceContextFilter` when OTel is configured.
4. Logs from contractor modules appear in Loki when Promtail is configured (per `LOKI_SETUP_GUIDE.md`).

**Migration targets (currently non-compliant):**
| Module | Current | Required |
|--------|---------|----------|
| `contractors/artisan_phases/design_prompts/seed_mapping.py` | `logging.getLogger(__name__)` | `get_logger(__name__)` |
| `contractors/context_schema.py` | `logging.getLogger(__name__)` | `get_logger(__name__)` |
| `contractors/context_strategy.py` | `logging.getLogger(__name__)` | `get_logger(__name__)` |
| `contractors/artisan_phases/domain_checklist.py` | `logging.getLogger(__name__)` | `get_logger(__name__)` |

#### AL-101: Logger Name Convention

**Status:** implemented
**Source:** `logging_config.py`, `logging_otel.py`

Logger names must follow the module path so Loki queries can filter by `logger` label.

**Acceptance criteria:**
1. Logger name is `__name__` (e.g., `startd8.contractors.context_seed_handlers`).
2. No ad-hoc logger names (e.g., `get_logger("custom")`) except modules explicitly listed in the AL-101 exception allowlist table below.
3. Promtail extracts `logger` as a low-cardinality label for LogQL filtering.

**AL-101 Exception Allowlist (authoritative for Phase 1):**

| Module Path | Allowed Logger Name(s) | Rationale |
|-------------|------------------------|-----------|
| `src/startd8/contractors/registry.py` | `startd8.contractors.registry` | Registry/bootstrap anchor logger used for subsystem-level lifecycle logging |

Governance rules:
- This table is the single source of truth for allowed non-`__name__` logger names in contractor scope.
- Any non-allowlisted `get_logger("...")` usage is non-compliant and must be migrated to `get_logger(__name__)` in Phase 1.
- New exceptions require updating this table in the same change that introduces the exception.

---

### Layer 2: Phase-Lifecycle Logging (AL-2xx)

Phase transitions and task boundaries must be logged at defined levels so operators can reconstruct pipeline progress from logs alone.

#### AL-200: Phase Entry Log

**Status:** planned
**Source:** `artisan_contractor.py` (`_execute_phase`)

Log at INFO when a phase is about to execute, including phase name and workflow context.

**Acceptance criteria:**
1. One INFO log per phase entry with message including phase name (e.g., `"Starting phase: design"`).
2. `extra` dict includes: `phase`, `workflow_id` (when available).
3. Log is emitted before the phase handler's `execute()` is invoked.
4. Log level is INFO (phase transitions are normal operational events).

#### AL-201: Phase Exit Log

**Status:** planned
**Source:** `artisan_contractor.py` (`_execute_phase`)

Log at INFO when a phase completes, including success/failure and duration.

**Acceptance criteria:**
1. One INFO log per phase exit with message including phase name and outcome.
2. `extra` dict includes: `phase`, `success` (bool), `duration_ms` (when measurable), `workflow_id`.
3. Log is emitted in a `finally` block so it runs even on exception.
4. On phase failure, an ERROR log with exception details is also emitted (AL-4xx).

#### AL-202: Task Boundary Log

**Status:** planned
**Source:** `context_seed_handlers.py` (DesignPhaseHandler, ImplementPhaseHandler, IntegratePhaseHandler, TestPhaseHandler, ReviewPhaseHandler)

Log at DEBUG when a task is about to be processed and when it completes.

**Acceptance criteria:**
1. DEBUG log at task start: `"Processing task {task_id}: {title}"` with `extra`: `task_id`, `task_title`, `phase`, `domain`.
2. DEBUG log at task completion: `"Task {task_id} completed: {status}"` with `extra`: `task_id`, `status`, `phase`, `cost_usd` (when available).
3. Task boundary logs are DEBUG to avoid log volume in production; INFO is reserved for phase-level and gate-level events.
4. Logs use `get_logger()` per AL-100.

---

### Layer 3: Gate and Contract Logging (AL-3xx)

Gate boundary validation and contract propagation results must be logged so operators can diagnose entry/exit failures and propagation gaps.

#### AL-300: Gate Entry Result Log

**Status:** planned
**Source:** `artisan_contractor.py` (`_execute_phase`), after `validate_phase_boundary()` entry

Log the entry gate validation result.

**Acceptance criteria:**
1. When entry gate passes: INFO log with `gate.entry.passed=true`, `gate.phase`, `gate.propagation_status`.
2. When entry gate fails: WARNING log with `gate.entry.passed=false`, `gate.phase`, `gate.propagation_status`, and any violation summary.
3. `extra` dict includes structured JSON fields for gate analysis: `phase`, `passed` (queryable via `| json`; not required as Loki labels).
4. Log is emitted inside the gate.entry span (OT-200) so trace-log correlation groups it with the span.

#### AL-301: Gate Exit Result Log

**Status:** planned
**Source:** `artisan_contractor.py` (`_execute_phase`), after `validate_phase_boundary()` exit

Log the exit gate validation result.

**Acceptance criteria:**
1. When exit gate passes: INFO log with `gate.exit.passed=true`, `gate.phase`.
2. When exit gate fails: WARNING log with `gate.exit.passed=false`, `gate.phase`, violation summary.
3. Log is emitted inside the gate.exit span (OT-201).
4. Same `extra` structure as AL-300 for consistency.

#### AL-302: Contract Propagation Gap Log

**Status:** planned
**Source:** `emit_boundary_result()` callers, forensic_log.py

When contract propagation is degraded (chain status DEGRADED or BROKEN), log a WARNING so operators can correlate with forensic logs.

**Acceptance criteria:**
1. WARNING log when `PropagationChainResult.status` is DEGRADED or BROKEN.
2. Message includes chain name and status.
3. `extra` includes: `chain_name`, `chain_status`, `phase`, `workflow_id`.
4. Log is emitted by the contract system, not duplicated in every phase handler.

---

### Layer 4: Operational Logging (AL-4xx)

LLM calls, errors, retries, and cost attribution must be logged with structured fields for Loki querying. Forensic logs (OT-7xx) cover LLM call schema; this layer covers non-forensic operational events.

#### AL-400: LLM Call Outcome Log

**Status:** implemented (via OT-7xx forensic logs)
**Source:** `forensic_log.py` (`emit_forensic_log`)

LLM call outcomes are captured by the forensic log schema (OT-700). This requirement ensures that when forensic logging is disabled or fails, a fallback INFO log is still emitted.

**Acceptance criteria:**
1. When `emit_forensic_log()` succeeds, no additional log is required (forensic log is the canonical record).
2. When `emit_forensic_log()` catches an internal error (OT-712 AC-8), the warning log includes `call_type`, `task_id`, and a truncated error message.
3. The fallback path uses `get_logger()` per AL-100.

#### AL-401: Retry Attempt Log

**Status:** planned
**Source:** `development.py` (LLMChunkExecutor), `test_construction.py` (_retry_generate_tests), `design_documentation.py` (design iteration retry)

Log at WARNING when a retry is attempted (chunk, test, or design iteration).

**Acceptance criteria:**
1. WARNING log: `"Retry attempt {attempt}/{max_attempts} for {context}"` with `extra`: `attempt`, `max_attempts`, `task_id` or `chunk_id`, `phase`, `reason` (truncated).
2. Log is emitted before the retry LLM call, not after.
3. Retry logs are WARNING so they stand out in Loki without being ERROR (retries are expected under load).

#### AL-402: Phase Exception Log

**Status:** implemented (partial)
**Source:** `artisan_contractor.py`, phase handlers

When a phase raises an exception, log at ERROR with full exception context.

**Acceptance criteria:**
1. ERROR log with `logger.exception()` or equivalent so traceback is captured.
2. Message includes phase name and exception type.
3. `extra` includes: `phase`, `workflow_id`, `task_id` (when applicable).
4. Log is emitted before the exception is re-raised (in the `except` block).
5. OTel span also records the exception (OT-507); log provides searchable record in Loki.

#### AL-403: Cost Attribution Log

**Status:** planned
**Source:** Phase handlers, cost tracker integration

Log cumulative cost at phase boundaries for budget monitoring.

**Acceptance criteria:**
1. INFO log at phase exit: `"Phase {phase} cost: ${cost_usd:.4f}"` when cost is available.
2. `extra` includes: `phase`, `cost_usd`, `workflow_id`, `task_count` (when applicable).
3. Log is emitted by the cost tracker or phase handler when `CostTracker` has recorded usage.
4. Enables Loki queries: `| json | phase="design" | cost_usd > 0.1`.

#### AL-404: Edit-First Gate Rejection Log

**Status:** implemented
**Source:** `edit_first_gate.py` (`emit_rejection_telemetry`), AR-813

When the Edit-First gate rejects a file (size regression), log and emit OTel span event.

**Acceptance criteria:**
1. WARNING log when a file is rejected: includes `task_id`, `file_path`, `input_chars`, `output_chars`, `ratio_pct`, `threshold_pct`.
2. OTel span event `edit_first.size_regression` is emitted (AR-813).
3. Log uses `get_logger()` per AL-100.
4. Log is emitted before retry prompt is built (AR-814).

---

### Layer 5: Loki Correlation (AL-5xx)

Logs must carry trace_id and span_id so Grafana can correlate logs with Tempo traces. The OTel log bridge and trace context filter provide this; requirements ensure they are used correctly.

#### AL-500: Trace Context Filter Attachment

**Status:** implemented
**Source:** `logging_config.py` (`_attach_otel_handlers`)

The `OTelTraceContextFilter` injects `trace_id` and `span_id` into every LogRecord. This filter must be attached to all handlers used by contractor loggers.

**Acceptance criteria:**
1. `_ensure_default_log_file_handler()` calls `_attach_otel_handlers(root_logger)` after OTel auto-configuration.
2. `OTelTraceContextFilter` is added to every handler on the root logger.
3. When OTel is unavailable, the filter still runs (no-op: sets `trace_id=""`, `span_id=""`).
4. JSONFormatter includes `trace_id` and `span_id` in the serialized output (per `logging_config.py` JSONFormatter).

#### AL-501: Correlation ID Propagation

**Status:** implemented
**Source:** `logging_config.py`, `logging_otel.py`

When a correlation_id is set (e.g., for request tracking), it must appear in log output and OTel log attributes.

**Acceptance criteria:**
1. `setup_logging(correlation_id=...)` injects correlation_id into LogRecord factory.
2. `OTelLogHandler` includes `correlation_id` in OTel log attributes when present.
3. JSONFormatter includes `correlation_id` in JSON output.
4. Promtail can extract `correlation_id` for LogQL filtering (as high-cardinality field in message, not as label).

#### AL-502: Loki Label Cardinality

**Status:** implemented
**Source:** `LOKI_SETUP_GUIDE.md`, `promtail-config.yml`

Only low-cardinality fields are used as Loki labels to avoid cardinality explosion.

**Acceptance criteria:**
1. Labels: `level`, `logger`, `exception_type`, `agent_name` (when present).
2. High-cardinality fields (`trace_id`, `correlation_id`, `task_id`) remain in JSON body, not as labels.
3. Promtail config documents the label extraction pipeline.
4. Log output structure is stable so Promtail pipeline does not break on schema changes.

---

### Layer 6: Structured Logging Conventions (AL-6xx)

Log messages and extra fields must follow conventions for consistent Loki querying and dashboard building.

#### AL-600: JSON Format for File Handler

**Status:** implemented
**Source:** `logging_config.py` (`JSONFormatter`, `_ensure_default_log_file_handler`)

The default file handler uses JSONFormatter for Loki-friendly output.

**Acceptance criteria:**
1. File handler at `~/.startd8/logs/startd8.log` uses `JSONFormatter`.
2. JSON output includes: `timestamp`, `level`, `logger`, `message`, `exception` (when present), `trace_id`, `span_id`, `correlation_id`, `source` (file, function, line).
3. All `extra` dict fields are merged into the JSON output (excluding reserved keys).
4. Timestamp is ISO 8601 UTC.

#### AL-601: Extra Field Naming

**Status:** planned
**Source:** This document

Structured extra fields use consistent naming for Loki query predictability.

**Acceptance criteria:**
1. Use snake_case for extra keys: `task_id`, `phase`, `workflow_id`, `cost_usd`, `gate_passed`.
2. Avoid redundant prefixes when context is clear: `phase` not `log.phase`.
3. Document reserved keys in `logging_config.py` JSONFormatter exclusion list.
4. New operational logs (AL-2xx, AL-3xx, AL-4xx) use these conventions.

#### AL-602: Log Level Semantics

**Status:** planned
**Source:** This document

Log levels have defined semantics for Artisan pipeline events.

**Acceptance criteria:**
1. **DEBUG**: Task boundaries, chunk-level detail, manifest diff details, internal state dumps.
2. **INFO**: Phase transitions, gate passes, successful LLM calls (forensic log), cost summaries, normal completion.
3. **WARNING**: Gate failures, retries, contract propagation gaps, Edit-First rejections, degraded context.
4. **ERROR**: Unhandled exceptions, phase failures, integration failures, LLM API errors.
5. **CRITICAL**: Reserved for process-level failures (e.g., OOM, unrecoverable state).
6. All new log statements in contractor modules follow these semantics.

---

### Layer 7: Graceful Degradation (AL-7xx)

When OTel is unavailable or the log pipeline is misconfigured, logging must degrade gracefully without breaking the pipeline.

#### AL-700: No-Op When OTel Unavailable

**Status:** implemented
**Source:** `logging_otel.py` (`OTelLogHandler`, `OTelTraceContextFilter`)

When OTel packages are not installed or LoggerProvider is not configured, logging still works; only the OTel export path is skipped.

**Acceptance criteria:**
1. `get_logger()` returns a standard Python logger regardless of OTel availability.
2. `OTelLogHandler._ensure_initialized()` returns False when OTel is unavailable; `emit()` is a no-op.
3. `OTelTraceContextFilter` sets `trace_id=""`, `span_id=""` when OTel is unavailable; filter returns True (log is not dropped).
4. File and console handlers continue to receive logs.
5. No ImportError or AttributeError when OTel is not installed.

#### AL-701: Startup Logging Banner

**Status:** implemented (for OTel; logging-specific banner planned)
**Source:** `otel.py` (`auto_configure_otel`), `artisan_contractor.py`

When the Artisan workflow starts, emit a one-line banner indicating logging/telemetry status.

**Acceptance criteria:**
1. OTel banner is already emitted: `"Telemetry: ACTIVE -> ..."` or `"Telemetry: INACTIVE -- ..."`.
2. (Planned) Extend banner to include: `"Logging: file=~/.startd8/logs/startd8.log, otel_bridge=active|inactive"`.
3. Banner is INFO level, emitted once per workflow run.
4. Follows "Fail Visible, Not Silent" — operator always sees status.

#### AL-702: Log File Fallback on Permission Error

**Status:** implemented
**Source:** `logging_config.py` (`_ensure_default_log_file_handler`)

When the log file cannot be created (permission denied, read-only filesystem), fall back to console-only logging with a warning.

**Acceptance criteria:**
1. `PermissionError` or `OSError` when creating log file triggers `warnings.warn()` with actionable message.
2. Console handler is still configured; pipeline continues.
3. No exception propagates to caller; `_default_logging_initialized` is still set to True.
4. Operator sees the warning and can fix permissions or redirect logs.

---

## 4. Log Flow Diagram

```mermaid
flowchart TD
    subgraph modules ["Contractor Modules (AL-100)"]
        DH[DesignPhaseHandler]
        IH[ImplementPhaseHandler]
        ITH[IntegratePhaseHandler]
        TH[TestPhaseHandler]
        RH[ReviewPhaseHandler]
        ENG[integration_engine]
        EFG[edit_first_gate]
        FL[forensic_log]
    end

    subgraph logging_config ["logging_config.py"]
        GL[get_logger]
        EFH[_ensure_default_log_file_handler]
        AOH[_attach_otel_handlers]
    end

    subgraph handlers ["Handlers"]
        FH[FileHandler + JSONFormatter]
        CH[ConsoleHandler]
        OH[OTelLogHandler]
    end

    subgraph filters ["Filters"]
        TCF[OTelTraceContextFilter]
    end

    subgraph destinations ["Destinations"]
        FILE[~/.startd8/logs/startd8.log]
        CONSOLE[stderr]
        LOKI[Loki via OTel]
    end

    DH & IH & ITH & TH & RH & ENG & EFG & FL -->|get_logger(__name__)| GL
    GL --> EFH
    EFH --> FH & CH & AOH
    AOH --> OH & TCF
    FH & CH --> TCF
    OH --> TCF
    FH --> FILE
    CH --> CONSOLE
    OH --> LOKI
```

---

## 5. Traceability Matrix

### Source Files → Requirements

| Source File | Implemented | Planned |
|-------------|-------------|---------|
| `src/startd8/logging_config.py` | AL-100, AL-101, AL-500, AL-600, AL-700, AL-701, AL-702 | |
| `src/startd8/logging_otel.py` | AL-500, AL-501, AL-700 | |
| `src/startd8/contractors/context_seed_handlers.py` | AL-100 | AL-202 |
| `src/startd8/contractors/artisan_contractor.py` | AL-100 | AL-200, AL-201, AL-300, AL-301, AL-402 |
| `src/startd8/contractors/integration_engine.py` | AL-100 | |
| `src/startd8/contractors/edit_first_gate.py` | AL-100, AL-404 | |
| `src/startd8/contractors/forensic_log.py` | AL-100, AL-400 | |
| `src/startd8/contractors/artisan_phases/design_documentation.py` | AL-100 | AL-401 |
| `src/startd8/contractors/artisan_phases/development.py` | AL-100 | AL-401 |
| `src/startd8/contractors/artisan_phases/test_construction.py` | AL-100 | AL-401 |
| `contractors/artisan_phases/design_prompts/seed_mapping.py` | | AL-100 (migration) |
| `contractors/context_schema.py` | | AL-100 (migration) |
| `contractors/context_strategy.py` | | AL-100 (migration) |
| `contractors/artisan_phases/domain_checklist.py` | | AL-100 (migration) |

### Cross-Cutting Requirements → Affected Source Files

| Requirement | Affected Source Files |
|-------------|----------------------|
| AL-100 (get_logger) | All contractor modules |
| AL-601 (Extra Field Naming) | All modules emitting AL-2xx, AL-3xx, AL-4xx logs |
| AL-602 (Log Level Semantics) | All contractor modules |

### Upstream Requirements (extends)

| This Requirement | Extends | Relationship |
|-----------------|---------|--------------|
| AL-200, AL-201 | AR-601 | Phase logs annotate phase span lifecycle |
| AL-300, AL-301 | OT-200, OT-201 | Gate logs complement gate spans |
| AL-400 | OT-7xx | Forensic logs are canonical LLM call record |
| AL-500 | OT-708 | Trace context enables log-to-trace correlation |
| AL-700 | AR-607 | Logging degrades when OTel degrades |

---

## 6. Status Dashboard

| Layer | ID Range | Total | Implemented | Partial | Planned |
|-------|----------|-------|-------------|---------|---------|
| Logger Acquisition | AL-1xx | 2 | 1 | 1 | 0 |
| Phase-Lifecycle Logging | AL-2xx | 3 | 0 | 0 | 3 |
| Gate and Contract Logging | AL-3xx | 3 | 0 | 0 | 3 |
| Operational Logging | AL-4xx | 5 | 2 | 0 | 3 |
| Loki Correlation | AL-5xx | 3 | 3 | 0 | 0 |
| Structured Conventions | AL-6xx | 3 | 1 | 0 | 2 |
| Graceful Degradation | AL-7xx | 3 | 3 | 0 | 0 |
| **Total** | | **22** | **10** | **1** | **11** |

> **AL-100 partial note:** AL-100 is partially implemented — most contractor modules use `get_logger()`, but 4 modules (seed_mapping, context_schema, context_strategy, domain_checklist) still use `logging.getLogger()` and require migration.

---

## 7. Verification

### Unit Tests

```bash
# Logging config and OTel bridge
pytest tests/unit/test_logging_config.py -v  # if exists
pytest tests/unit/test_logging_otel.py -v    # if exists

# Forensic logging (covers AL-400)
pytest tests/unit/contractors/test_forensic_logging.py -v
```

### Migration Verification (AL-100)

```bash
# Grep for non-compliant logger acquisition
rg "logging\.getLogger" src/startd8/contractors/
# Expected: 0 matches after migration (or only in explicitly documented exceptions)
```

### Integration Verification

1. **Loki log visibility** — Run a short Artisan workflow, then query Loki (job label from `promtail-config.yml`):
   ```logql
   {job="startd8"} | json | logger=~"startd8.contractors.*"
   ```

2. **Trace-log correlation** — From a Tempo trace, use "Logs for this span" to verify logs carry matching trace_id.

3. **Log file persistence** — Verify `~/.startd8/logs/startd8.log` exists and contains JSON entries after a run.

4. **Permission fallback** — In a read-only directory, run workflow; verify warning is emitted and pipeline completes.

### LogQL Query Examples

All queries use `job="startd8"` per `promtail-config.yml`. JSON fields are extracted by the Promtail pipeline.

| Use Case | Query |
|----------|-------|
| Phase transitions | `{job="startd8"} \| json \| message=~"Starting phase.*"` |
| Gate failures | `{job="startd8"} \| json \| level="WARNING" \| message=~"gate.*"` |
| Retries | `{job="startd8"} \| json \| message=~"Retry attempt.*"` |
| Edit-First rejections | `{job="startd8"} \| json \| message=~"edit_first.*"` |
| Forensic LLM calls | `{job="startd8"} \| json \| event="llm.call"` |
| Errors | `{job="startd8"} \| level="ERROR"` |

---

## 8. Related Documents

| Document | Relationship |
|----------|--------------|
| `ARTISAN_REQUIREMENTS.md` Layer 6 (AR-6xx) | Parent — observability layer |
| `ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md` | Sibling — traces; logs complement spans |
| `ARTISAN_METRICS_REQUIREMENTS.md` | Sibling — metrics; logs complement with aggregations |
| `PATTERN-silent-telemetry-loss.md` | Design principle — fail visible, not silent |
| `LOKI_SETUP_GUIDE.md` | Infrastructure — Promtail, Loki, Grafana setup |
| `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md` | Design principle — prescriptive logging |
| CLAUDE.md | Mandate — get_logger() in contractors |
| `src/startd8/logging_config.py` | Implementation — get_logger, JSONFormatter |
| `src/startd8/logging_otel.py` | Implementation — OTel log bridge |
| `promtail-config.yml` | Infrastructure — Loki label extraction, job=startd8 |
