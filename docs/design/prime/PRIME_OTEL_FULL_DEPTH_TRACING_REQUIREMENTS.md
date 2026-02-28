# Prime Workflow Full-Depth OTel Tracing — Requirements

> **Version:** 1.1.0
> **Status:** Rebuilt for Prime workflow scope; Partial baseline implemented (PC-OT-000 through PC-OT-003); Planned (PC-OT-1xx through PC-OT-7xx)
> **Date:** 2026-02-28
> **Scope:** Full-depth OpenTelemetry span instrumentation for `PrimeContractorWorkflow` feature lifecycle (`run → process_feature → develop_feature → integrate_feature`) including generation, staleness, merge/checkpoint, state/manifest writes, and Prime→Lead trace correlation
> **Extends:** `PRIME_CONTRACTOR_REQUIREMENTS.md` Layer 5 (REQ-PC-013, REQ-PC-014)
> **Complements:** `PRIME_LOGGING_REQUIREMENTS.md` (logs) and `PLAN_INGESTION_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md` (upstream ingestion tracing)
> **Primary sources:** `src/startd8/contractors/prime_contractor.py`, `src/startd8/contractors/integration_engine.py`, `src/startd8/contractors/adapters/contextcore.py`, `src/startd8/contractors/adapters/standalone.py`

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Design Principles](#2-design-principles)
3. [Requirements](#3-requirements)
   - [Layer 0: Current Baseline (PC-OT-000)](#layer-0-current-baseline-pc-ot-000)
   - [Layer 1: Workflow and Feature Lifecycle Spans (PC-OT-1xx)](#layer-1-workflow-and-feature-lifecycle-spans-pc-ot-1xx)
   - [Layer 2: Generation and LLM Spans (PC-OT-2xx)](#layer-2-generation-and-llm-spans-pc-ot-2xx)
   - [Layer 3: IntegrationEngine Spans (PC-OT-3xx)](#layer-3-integrationengine-spans-pc-ot-3xx)
   - [Layer 4: Artifact and State I/O Spans (PC-OT-4xx)](#layer-4-artifact-and-state-io-spans-pc-ot-4xx)
   - [Layer 5: Correlation Attribute Contract (PC-OT-5xx)](#layer-5-correlation-attribute-contract-pc-ot-5xx)
   - [Layer 6: Graceful Degradation and Backend Safety (PC-OT-6xx)](#layer-6-graceful-degradation-and-backend-safety-pc-ot-6xx)
   - [Layer 7: Infrastructure and Verification (PC-OT-7xx)](#layer-7-infrastructure-and-verification-pc-ot-7xx)
4. [Span Hierarchy](#4-span-hierarchy)
5. [Data Flow Diagram](#5-data-flow-diagram)
6. [Traceability Matrix](#6-traceability-matrix)
7. [Status Dashboard](#7-status-dashboard)
8. [Verification](#8-verification)
9. [Related Documents](#9-related-documents)

---

## 1. Motivation

Prime currently emits observability signals via the `Instrumentor` protocol (`emit_span`, `emit_event`, `emit_metric`, `emit_insight`), but coverage is shallow:
- only one explicit span call in `pre_flight_validation()`
- no root workflow span in `PrimeContractorWorkflow.run()`
- no per-feature child span hierarchy for generation/integration/checkpoint stages
- no deterministic trace correlation between Prime orchestration and nested `LeadContractorWorkflow.run()`

This makes it hard to answer operational questions:
- Which feature or sub-stage dominated cost/latency?
- Was generation skipped by staleness reuse or force-regenerate?
- Did integration fail at pre-validate, merge, checkpoint, or rollback?
- Which mode (`standalone` vs `pipeline`) produced the trace and with what context depth?

Full-depth tracing closes these gaps while preserving current runtime behavior when OTel/ContextCore is unavailable.

---

## 2. Design Principles

| Principle | Source | Application |
|-----------|--------|-------------|
| Observe the full feature lifecycle | `prime_contractor.py` (`run`, `process_feature`, `develop_feature`, `integrate_feature`) | Every feature stage must be represented as a trace subtree |
| Preserve no-ContextCore operability | `adapters/standalone.py` | Instrumentation must degrade to logs/no-op behavior without breaking execution |
| Prime→Lead trace continuity | `generators/lead_contractor.py`, `workflows/base.py` | Lead workflow spans must correlate to their parent Prime feature spans |
| Integration as first-class telemetry | `integration_engine.py` | Merge/checkpoint/rollback paths must be queryable, not inferred from logs |
| No functional regression | Prime mode/state/caching contracts | Tracing additions cannot change queue behavior, staleness decisions, or outputs |

---

## 3. Requirements

### Layer 0: Current Baseline (PC-OT-000)

#### PC-OT-000: Instrumentor Protocol Baseline

**Status:** implemented  
**Source:** `src/startd8/contractors/protocols.py` (`Instrumentor`)

Prime observability MUST continue to be routed through the `Instrumentor` abstraction.

**Acceptance criteria:**
1. Prime workflow remains backend-agnostic (`logging` or `contextcore` instrumentor).
2. `emit_span`, `emit_event`, `emit_metric`, `emit_insight` contract remains stable.
3. Existing non-OTel runs continue to function unchanged.

#### PC-OT-001: Preflight Span Emission Baseline

**Status:** implemented  
**Source:** `prime_contractor.py` (`pre_flight_validation`)

Prime currently emits a preflight span signal via instrumentor.

**Acceptance criteria:**
1. `code_generation.preflight` emission remains present.
2. Preflight estimate and decision events remain emitted.
3. Existing log-based observability remains intact.

#### PC-OT-002: Insight and Metric Baseline

**Status:** implemented  
**Source:** `prime_contractor.py` (`process_feature`, `run`, `develop_feature`)

Prime insight and metric signals MUST continue to be emitted.

**Acceptance criteria:**
1. `workflow_started` and `workflow_completed` insights are emitted.
2. `feature_selected` insight is emitted per processed feature.
3. `prime_contractor.feature_cost` metric is emitted on successful generation.

#### PC-OT-003: Lead Workflow Root Span Baseline

**Status:** implemented  
**Source:** `workflows/base.py`, `generators/lead_contractor.py`

`LeadContractorWorkflow.run()` emits its own root workflow span when OTel is available.

**Acceptance criteria:**
1. Lead workflow root span behavior remains unchanged.
2. Prime tracing enhancements must not disable Lead workflow span emission.
3. Correlation improvements must be additive (no behavior regressions).

---

### Layer 1: Workflow and Feature Lifecycle Spans (PC-OT-1xx)

#### PC-OT-100: Prime Module Tracer with Safe Fallback

**Status:** planned  
**Source:** `prime_contractor.py`

Add a module-level tracer for Prime workflow spans with graceful fallback.

**Acceptance criteria:**
1. Prime root/feature spans use a dedicated tracer namespace.
2. Missing OTel dependencies do not raise runtime errors.
3. Fallback behavior remains compatible with existing instrumentor usage.

#### PC-OT-101: Root Workflow Span

**Status:** planned  
**Source:** `PrimeContractorWorkflow.run`

Wrap `run()` in a root Prime workflow span.

**Acceptance criteria:**
1. Span name `workflow.prime-contractor` (or equivalent stable pattern).
2. Attributes include mode, dry_run, auto_commit, stop_on_failure, max_cost_usd.
3. Workflow summary stats (`processed`, `succeeded`, `failed`, `total_cost_usd`) are recorded on completion.

#### PC-OT-102: Per-Feature Parent Span

**Status:** planned  
**Source:** `process_feature`

Each feature MUST run under a parent feature span.

**Acceptance criteria:**
1. Span name pattern `feature.{feature_id}`.
2. Attributes include `feature.id`, `feature.name`, status at selection, target_files count.
3. Span status reflects final feature outcome (success/fail/blocked).

#### PC-OT-103: Stage Boundary Child Spans

**Status:** planned  
**Source:** `process_feature`, `develop_feature`, `integrate_feature`

Feature stage boundaries MUST be explicit child spans.

**Acceptance criteria:**
1. Child spans for preflight, develop, integrate stages.
2. Branches for dry-run, decomposition, and regeneration are trace-visible.
3. Span closure is guaranteed on all exit paths.

#### PC-OT-104: Queue Status Transition Events

**Status:** planned  
**Source:** `queue.start_feature`, `queue.complete_feature`, `queue.fail_feature`

Queue state transitions MUST be represented as span events.

**Acceptance criteria:**
1. Transition events include old/new status and feature ID.
2. Failed transition paths attach failure reason.
3. Events are attached to the active feature span.

#### PC-OT-105: Budget and Stop Conditions

**Status:** planned  
**Source:** `run` main loop

Workflow stop reasons MUST be observable.

**Acceptance criteria:**
1. Cost-budget stop emits explicit span event with budget and current spend.
2. Max retries exceeded emits event with feature ID and attempt count.
3. `stop_on_failure` path emits deterministic stop reason.

---

### Layer 2: Generation and LLM Spans (PC-OT-2xx)

#### PC-OT-200: Preflight Estimation Span Upgrade

**Status:** planned  
**Source:** `pre_flight_validation`

Preflight MUST emit a structured duration span (not just fire-and-forget).

**Acceptance criteria:**
1. Attributes include estimated lines/tokens/complexity/confidence.
2. Decomposition-required decisions are attached as span events.
3. Strict checkpoint preflight failures mark span as ERROR.

#### PC-OT-201: Context Resolution Span

**Status:** planned  
**Source:** `_resolve_context`, `develop_feature`

Context strategy resolution MUST be instrumented.

**Acceptance criteria:**
1. Attributes include strategy mode, context key count, fallback usage.
2. Strategy fallback emits explicit warning event in span.
3. Invalid resolved context path is trace-visible.

#### PC-OT-202: Staleness and Reuse Decision Span

**Status:** planned  
**Source:** `_check_staleness`, `_check_file_provenance`, `develop_feature`

Caching/reuse decisions MUST be queryable.

**Acceptance criteria:**
1. Span includes decision category (`force_regenerate`, `current`, `stale`, `missing`).
2. Checksum comparison results are captured.
3. Reuse short-circuit path is explicitly marked.

#### PC-OT-203: Lead Workflow Invocation Span

**Status:** planned  
**Source:** `develop_feature`, `LeadContractorCodeGenerator.generate`

Prime code generation invocation MUST be wrapped by a parent span.

**Acceptance criteria:**
1. Parent span `llm.lead_contractor.invoke` (or equivalent) exists per generation attempt.
2. Attributes include lead/drafter agent specs and max_iterations.
3. Child Lead workflow spans are trace-correlated to the parent feature span.

#### PC-OT-204: Generation Result Attributes

**Status:** planned  
**Source:** `develop_feature`

Generation output metrics MUST be attached to the generation span.

**Acceptance criteria:**
1. Capture `cost_usd`, `input_tokens`, `output_tokens`, model, generated file count.
2. Failed generation records error and exception context.
3. Retry-with-prior-error path emits a dedicated retry event.

#### PC-OT-205: Walkthrough Prompt Persistence Span

**Status:** planned  
**Source:** `_persist_walkthrough_prompts`, walkthrough branch in `develop_feature`

Walkthrough mode MUST be represented in spans.

**Acceptance criteria:**
1. Prompt persistence emits dedicated span with output directory and file count.
2. Walkthrough short-circuit is visible as non-LLM generation path.
3. Errors in prompt persistence record exception and continue behavior.

---

### Layer 3: IntegrationEngine Spans (PC-OT-3xx)

#### PC-OT-300: Integration Parent Span

**Status:** planned  
**Source:** `integrate_feature`, `IntegrationEngine.integrate`

Integration MUST run under a dedicated parent span.

**Acceptance criteria:**
1. Parent span includes feature ID, attempt number, dry_run flag.
2. Success/failure outcome is set as span attributes.
3. Parent covers the entire integrate lifecycle.

#### PC-OT-301: Pre-Merge Validation Span

**Status:** planned  
**Source:** `IntegrationEngine.integrate` pre-validate section

Pre-merge checkpoint validation MUST be traced.

**Acceptance criteria:**
1. Span includes number of generated paths validated.
2. Validation gate failures are marked as errors with checkpoint summary.
3. Gate contract emission failures are logged as span events.

#### PC-OT-302: Per-File Merge Spans

**Status:** planned  
**Source:** `IntegrationEngine.integrate` merge loop

Each source→target merge MUST be represented as a child span.

**Acceptance criteria:**
1. Attributes include source path, target path, merge strategy, edit-mode skip merge flag.
2. Merge conflicts/errors set ERROR status.
3. Successful merges include bytes/line counts when available.

#### PC-OT-303: Checkpoint Run Spans

**Status:** planned  
**Source:** `IntegrationEngine.integrate` checkpoint run section

Checkpoint execution MUST be fully traced.

**Acceptance criteria:**
1. Parent checkpoint span plus per-checkpoint child events/spans.
2. Attributes include checkpoint names, outcomes, strict_checkpoints behavior.
3. Failed checkpoints are correlated to rollback path.

#### PC-OT-304: Rollback and Commit Spans

**Status:** planned  
**Source:** `IntegrationEngine.integrate` failure and auto-commit branches

Rollback/commit side effects MUST be traced.

**Acceptance criteria:**
1. Rollback span emitted when integration fails after merge attempt.
2. Auto-commit span emitted with commit scope/details.
3. Snapshot cleanup span emitted after success/failure completion.

#### PC-OT-305: Manifest Diff Spans

**Status:** planned  
**Source:** `IntegrationEngine._manifest_pre_merge_diff`, `_manifest_post_merge_refresh`

Manifest diff and refresh operations MUST be trace-visible.

**Acceptance criteria:**
1. Pre-merge diff span includes removed/added/changed signature counts.
2. Breaking change and retention-threshold outcomes are emitted as events.
3. Post-merge refresh span includes files refreshed and failures count.

---

### Layer 4: Artifact and State I/O Spans (PC-OT-4xx)

#### PC-OT-400: Queue State Write Span

**Status:** planned  
**Source:** `_save_queue_state_with_mode`, `FeatureQueue.save_state`

Writes to `.prime_contractor_state.json` MUST be traced.

**Acceptance criteria:**
1. Span includes path and feature count.
2. `execution_mode` injection into state is recorded.
3. Write failures are surfaced as warning/error events.

#### PC-OT-401: Generation Manifest Write Span

**Status:** planned  
**Source:** `_write_generation_manifest`

Manifest writes MUST have explicit spans.

**Acceptance criteria:**
1. Span includes `source_checksum`, mode, total cost/token summary.
2. 0o600 permission set result is captured.
3. Write failures are recorded without altering workflow outcome semantics.

#### PC-OT-402: Result Artifact Span (Runner Script)

**Status:** planned  
**Source:** `scripts/run_prime_workflow.py` result write path

Result JSON writes from runner MUST be traceable when OTel is active.

**Acceptance criteria:**
1. Span includes output path and success/aborted flags.
2. Dry-run skip path is represented as a skip event.
3. Task-filter context is attached when present.

#### PC-OT-403: Recovery Snapshot Spans

**Status:** planned  
**Source:** `create_safety_snapshot`, `recover_from_stash`, snapshot helpers

Safety snapshot and recovery operations MUST be traced.

**Acceptance criteria:**
1. Snapshot create/pop operations emit spans with git command outcome.
2. Restore-from-backup path emits file-level recovery events.
3. Recovery failure paths set ERROR status.

---

### Layer 5: Correlation Attribute Contract (PC-OT-5xx)

#### PC-OT-500: Standard Prime Span Attributes

**Status:** planned  
**Source:** Prime + Integration tracing additions

Define stable attributes for Prime spans.

**Acceptance criteria:**
1. Workflow spans include `prime.mode`, `prime.dry_run`, `prime.auto_commit`.
2. Feature spans include `feature.id`, `feature.name`, `feature.target_file_count`.
3. Integration spans include `integration.attempt`, `integration.result`.

#### PC-OT-501: Generation Metrics Attributes

**Status:** planned  
**Source:** `develop_feature`, `LeadContractorCodeGenerator.generate`

Generation spans MUST expose consistent cost/token/model labels.

**Acceptance criteria:**
1. `llm.cost_usd`, `llm.input_tokens`, `llm.output_tokens`, `llm.model` are present.
2. Cache-hit paths include `llm.skipped=true`.
3. Retry attempts include attempt index and prior-error hash/marker.

#### PC-OT-502: Prime→Lead Correlation Keys

**Status:** planned  
**Source:** Prime generation invocation + lead workflow config

Prime and Lead traces MUST share correlation metadata.

**Acceptance criteria:**
1. Feature ID is propagated to Lead workflow span attributes.
2. Prime trace ID or equivalent correlation key is recorded in Lead run context.
3. Cross-trace querying by feature ID is supported.

#### PC-OT-503: Artifact and Provenance Correlation

**Status:** planned  
**Source:** manifest/state/result write paths

Trace data MUST correlate to persisted artifacts.

**Acceptance criteria:**
1. Artifact spans include file paths and checksum/version fields where relevant.
2. Manifest feature entries can be traced back to feature spans.
3. State snapshot spans include queue progress at write time.

---

### Layer 6: Graceful Degradation and Backend Safety (PC-OT-6xx)

#### PC-OT-600: OTel Optionality Safety

**Status:** planned  
**Source:** adapters + Prime tracing additions

Prime MUST operate correctly when OTel is unavailable.

**Acceptance criteria:**
1. No ImportError/AttributeError from tracing paths without OTel.
2. LoggingInstrumentor remains a fully supported backend.
3. Behavior parity is preserved between instrumented and non-instrumented runs.

#### PC-OT-601: Instrumentor Failure Isolation

**Status:** planned  
**Source:** Prime and adapter callsites

Instrumentation failures MUST not crash core workflow paths.

**Acceptance criteria:**
1. Instrumentation exceptions are caught and downgraded to warnings where appropriate.
2. Core generation/integration state transitions remain intact on instrumentor errors.
3. Failure telemetry includes backend type and failed call type.

#### PC-OT-602: Span Lifecycle Correctness

**Status:** planned  
**Source:** adapter implementations (`contextcore.py`, `standalone.py`)

Span lifecycle semantics MUST support meaningful duration and parent-child nesting.

**Acceptance criteria:**
1. Span start and end boundaries encompass real work duration.
2. Event emission can target active stage spans deterministically.
3. No zero-duration auto-close behavior for long-running stage spans.

#### PC-OT-603: Exception Recording Contract

**Status:** planned  
**Source:** Prime + Integration tracing additions

Error semantics MUST be consistent across all traced stages.

**Acceptance criteria:**
1. Exceptions are recorded on the active span.
2. Error status is set before propagating/handling failure.
3. Tracing does not swallow functional exceptions.

---

### Layer 7: Infrastructure and Verification (PC-OT-7xx)

#### PC-OT-700: Prime OTel Descriptor Coverage

**Status:** planned  
**Source:** Prime/integration modules

Add observability descriptor coverage for Prime span patterns.

**Acceptance criteria:**
1. Descriptor includes workflow, feature, generation, integration, and I/O span patterns.
2. Attribute contract aligns with PC-OT-500..503.
3. Descriptor generation has no runtime side effects.

#### PC-OT-701: Tempo Query Cookbook

**Status:** planned  
**Source:** this document + dashboard assets

Provide query patterns for Prime operational diagnostics.

**Acceptance criteria:**
1. Query for top-cost features by `llm.cost_usd`.
2. Query for integration failures grouped by stage (`pre_validate`, `merge`, `checkpoint`, `rollback`).
3. Query for cache hit vs regenerate decisions.

#### PC-OT-702: Automated Trace Verification Harness

**Status:** planned  
**Source:** tests/scripts

Add automated checks for Prime span hierarchy and required attributes.

**Acceptance criteria:**
1. Verification script/test validates required spans on a deterministic sample run.
2. Missing critical spans fail verification.
3. Validation supports both dry-run and live (mocked generator) modes.

---

## 4. Span Hierarchy

```mermaid
flowchart TD
    A["workflow.prime-contractor"] --> B["feature.{feature_id}"]
    B --> B1["stage.preflight"]
    B1 --> B1a["code_generation.preflight"]
    B --> B2["stage.develop"]
    B2 --> B2a["context.resolve"]
    B2 --> B2b["cache.staleness.check"]
    B2 --> B2c["llm.lead_contractor.invoke"]
    B2c --> B2d["workflow.lead-contractor"]
    B --> B3["stage.integrate"]
    B3 --> B3a["integration.pre_validate"]
    B3 --> B3b["integration.merge.file.*"]
    B3 --> B3c["integration.checkpoints"]
    B3 --> B3d["integration.rollback_or_commit"]
    A --> C["io.queue_state.write"]
    A --> D["io.generation_manifest.write"]
```

---

## 5. Data Flow Diagram

```mermaid
flowchart LR
    S["Seed + Queue State"] --> W["Prime run() root span"]
    W --> F["feature.{id} span"]
    F --> P["preflight + size estimate"]
    F --> G["develop: context + staleness + Lead generation"]
    G --> L["LeadContractorWorkflow span tree"]
    F --> I["integrate: validate/merge/checkpoint/rollback"]
    I --> O["state + manifest writes"]
    O --> R["result artifacts + summary"]
```

---

## 6. Traceability Matrix

| Requirement Range | Primary Targets | Verification Targets |
|-------------------|-----------------|----------------------|
| PC-OT-000..003 | `protocols.py`, `prime_contractor.py`, `generators/lead_contractor.py` | existing contractor instrumentation tests |
| PC-OT-100..105 | `prime_contractor.py` | new Prime tracing unit tests |
| PC-OT-200..205 | `prime_contractor.py`, `generators/lead_contractor.py` | generation/llm tracing tests |
| PC-OT-300..305 | `integration_engine.py` | integration span and failure-path tests |
| PC-OT-400..403 | `prime_contractor.py`, `queue.py`, `scripts/run_prime_workflow.py` | artifact/state write tracing tests |
| PC-OT-500..503 | shared tracing helpers/contracts | attribute-schema tests |
| PC-OT-600..603 | adapters + callsites | no-OTel and backend-failure tests |
| PC-OT-700..702 | descriptors + verification scripts | descriptor snapshot + trace harness tests |

---

## 7. Status Dashboard

| Layer | ID Range | Total | Implemented | Planned |
|-------|----------|-------|-------------|---------|
| Baseline | PC-OT-000..003 | 4 | 4 | 0 |
| Lifecycle Spans | PC-OT-100..105 | 6 | 0 | 6 |
| Generation/LLM | PC-OT-200..205 | 6 | 0 | 6 |
| IntegrationEngine | PC-OT-300..305 | 6 | 0 | 6 |
| Artifact/State I/O | PC-OT-400..403 | 4 | 0 | 4 |
| Correlation Contract | PC-OT-500..503 | 4 | 0 | 4 |
| Degradation/Safety | PC-OT-600..603 | 4 | 0 | 4 |
| Infra/Verification | PC-OT-700..702 | 3 | 0 | 3 |
| **Total** |  | **37** | **4** | **33** |

---

## 8. Verification

Add Prime-focused tracing tests (no external collector required):

1. `tests/unit/contractors/test_prime_otel_spans.py` (new):
   - root workflow span
   - per-feature span tree
   - staleness/reuse path spans
   - generation result attributes
2. `tests/unit/contractors/test_integration_engine_otel_spans.py` (new):
   - pre-validate, merge, checkpoint, rollback/commit spans
3. `tests/unit/contractors/test_instrumentor_span_lifecycle.py` (new):
   - contextcore + logging adapter lifecycle correctness
4. Regression checks:
   - existing Prime behavior unchanged in no-OTel mode
   - manifest/state writes still occur with identical functional semantics

---

## 9. Related Documents

- `docs/design/prime/PRIME_CONTRACTOR_REQUIREMENTS.md`
- `docs/design/prime/PRIME_EXECUTION_MODES_REQUIREMENTS.md`
- `docs/design/prime/PRIME_EXECUTION_MODES_PLAN.md`
- `docs/design/artisan/ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md`
- `docs/design/plan-ingestion/PLAN_INGESTION_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md`
- `src/startd8/contractors/prime_contractor.py`
- `src/startd8/contractors/integration_engine.py`
- `src/startd8/contractors/adapters/contextcore.py`
- `src/startd8/contractors/adapters/standalone.py`
