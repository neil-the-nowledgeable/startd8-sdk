# Security Prime — Security Orchestration Layer Requirements

> **Version:** 1.1.0
> **Status:** IMPLEMENTED (Phases 0–2 + Category S + extensions shipped 2026-03-19/20)
> **Date:** 2026-03-19
> **Author:** human:neil + agent:claude-code
> **Design Principle:** [ANZEN_DESIGN_PRINCIPLE.md](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md) — Security Correctness by Design (安全)
> **Check Infrastructure:** `src/startd8/query_prime/` — **IMPLEMENTED** (see §2)
> **Sibling:** [TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md](../prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md) — same contract→TODO→generate→verify pattern for observability
> **Scope:** Orchestration layer that wires `query_prime/security/` into the generation pipeline — prompt injection, gate insertion, scoring, Kaizen feedback. ~550 lines of new code.

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [What Already Exists](#2-what-already-exists)
3. [What This Document Specifies](#3-what-this-document-specifies)
4. [Anzen Gate — Pipeline Security Verification](#4-anzen-gate--pipeline-security-verification)
5. [Pre-Generation Security Injection](#5-pre-generation-security-injection)
6. [Security Scoring](#6-security-scoring)
7. [Kaizen Security Feedback Loop](#7-kaizen-security-feedback-loop)
8. [Pipeline Integration](#8-pipeline-integration)
9. [Observability](#9-observability)
10. [Future Extensions](#10-future-extensions)
11. [Requirements Index](#11-requirements-index)
12. [Verification Strategy](#12-verification-strategy)
13. [Phased Delivery Plan](#13-phased-delivery-plan)

---

## 1. Motivation

### 1.1 The Incident

C# Prime Contractor runs 78–79 against the Online Boutique cartservice revealed: **the LLM faithfully reproduced a SQL injection vulnerability from the reference implementation**.

- **Run 78:** AlloyDB `$"SELECT...{userId}"` — genuine SQL injection. The C# semantic validator missed the multiline pattern.
- **Run 79:** Spanner `SpannerParameterCollection` — parameterized and safe. The validator false-positived, eroding trust.

### 1.2 The Three Gaps

1. **LLMs reproduce insecure patterns** without explicit security guidance in the prompt.
2. **Deterministic validators lack semantic understanding** — producing both false negatives (multiline SQL) and false positives (parameterized queries flagged).
3. **Security validation is reactive** — catching vulnerabilities after generation wastes tokens and cost.

### 1.3 The Anzen Principle

Security must be structural, not a review finding. Anzen (安全) wires security into every pipeline stage: prompts that guide generation, validators that check output, feedback loops that improve future runs, and scoring that makes security posture visible.

This document specifies the **orchestration layer** that makes this structural. The detection infrastructure already exists.

---

## 2. What Already Exists

`src/startd8/query_prime/` provides the complete check infrastructure. **These are NOT re-specified in this document.**

| Capability | Location | Status |
|-----------|----------|--------|
| Two-pass SQL injection detection (multiline, comment-aware, parameterization-suppression) | `security/injection.py` | **IMPLEMENTED** |
| Credential leakage detection | `security/credentials.py` | **IMPLEMENTED** |
| Resource lifecycle issue detection | `security/lifecycle.py` | **IMPLEMENTED** |
| Full verification pipeline (injection→credentials→lifecycle, PASS/WARN/FAIL) | `security/__init__.py:verify_file()` | **IMPLEMENTED** |
| Hard-fail on injection+credentials, WARN on lifecycle | `security/__init__.py:80–97` | **IMPLEMENTED** |
| Database pattern registry (safe/unsafe regex per database×language) | `patterns/__init__.py:DatabasePatternRegistry` | **IMPLEMENTED** |
| PostgreSQL patterns (C#/Npgsql, Python/psycopg2, Node/pg) | `patterns/postgresql.py` | **IMPLEMENTED** |
| Spanner patterns (C#, Go, Java) — with false-positive fix | `patterns/spanner.py` | **IMPLEMENTED** |
| MySQL, Redis, SQLite patterns | `patterns/mysql.py`, `redis.py`, `sqlite.py` | **IMPLEMENTED** |
| SecurityFinding, SecurityVerificationResult, SecurityVerdict models | `models.py` | **IMPLEMENTED** |
| QueryPrimeEngine (CLASSIFY→ROUTE→GENERATE→VERIFY with T3→T2→T1 escalation) | `engine.py` | **IMPLEMENTED** |
| Feature decomposer (feature → query work items) | `decomposer.py` | **IMPLEMENTED** |
| LLM generator with safe-pattern system prompt injection | `generator.py:_build_system_prompt()` | **IMPLEMENTED** |
| Wired into forward manifest validator | `forward_manifest_validator.py:722` | **IMPLEMENTED** |

**What `query_prime/` does NOT have** (and what this document specifies):

| Gap | Impact |
|-----|--------|
| Not wired into `integration_engine.py` | Generated code passes through without security gate |
| No P0 constraint in spec/draft prompts | LLM has no pre-generation security guidance during Prime Contractor runs |
| No security scoring | Security findings mixed into general semantic penalty |
| No quality gate integration | `quality_score >= 60` can pass despite injection vulnerabilities |
| No Kaizen feedback | No `SECURITY_VIOLATION` root cause, no cross-run escalation |
| No standalone mode auto-detection | Standalone runs have no security contract |
| No OTel instrumentation | Security checks invisible in Grafana/Loki |
| No reference deviation policy | LLM doesn't know to deviate from insecure reference patterns |

---

## 3. What This Document Specifies

Security Prime is a thin orchestration package (`src/startd8/security_prime/`, ~550 lines) that wires `query_prime/security/verify_file()` into the generation pipeline at three intercept points:

```
Task Seed ──▶ INTERCEPT 1: Context Assembly ──▶ INTERCEPT 2: Prompt ──▶ Generate ──▶ INTERCEPT 3: Gate
                (detect DB, inject contract)      (P0 constraint,          (existing       (verify_file()
                                                   P1 safe patterns)        generator)       hard-fail)
                                                                                                │
                                                                                                ▼
                                                                                            SCORE + KAIZEN
```

**No new check code. No new pattern modules. No generator changes. Pure wiring.**

---

## 4. Anzen Gate — Pipeline Security Verification

### REQ-SP-100: Gate Insertion

| ID | Requirement |
|----|-------------|
| SP-GT-001 | `integration_engine.py` SHALL call `query_prime.security.verify_file()` on every generated file where a database framework is detected via `LanguageProfile.framework_imports`. |
| SP-GT-002 | The gate SHALL execute AFTER `_run_semantic_checks()` and `_attempt_semantic_repair()` but BEFORE advisory downgrade logic. Security findings are NOT subject to advisory downgrade. |
| SP-GT-003 | `SecurityVerdict.FAIL` (injection or credential findings) SHALL be a hard integration failure — the file is rejected and the feature transitions to FAILED. |
| SP-GT-004 | `SecurityVerdict.WARN` (lifecycle issues) SHALL produce a warning but allow integration to proceed (consistent with `query_prime/security/__init__.py:94`). |
| SP-GT-005 | Database type detection SHALL use `query_prime.decomposer.detect_database_type()` applied to the file's source code + task description. When no database is detected, the gate is skipped (no security surface). |
| SP-GT-006 | Language detection SHALL use the existing `LanguageProfile.language_id` from the task's resolved language profile. |
| SP-GT-007 | Gate results SHALL be persisted to `{output_dir}/security-gate-results.json` as a list of `SecurityVerificationResult` (serialized via `dataclasses.asdict()`). |

### REQ-SP-110: Standalone Mode

| ID | Requirement |
|----|-------------|
| SP-GT-010 | In standalone mode (`is_standalone_mode()`), database type SHALL be auto-detected from file content via `detect_database_type(source_code)`. |
| SP-GT-011 | In pipeline mode, database type SHALL be read from `gen_context["detected_database"]` (set during plan ingestion enrichment). |
| SP-GT-012 | The gate SHALL run in both modes. Standalone produces an INFO log: "Security gate running in standalone mode — database auto-detected from source content." |

---

## 5. Pre-Generation Security Injection

### REQ-SP-200: P0 Hard Constraint

| ID | Requirement |
|----|-------------|
| SP-INJ-001 | When `LanguageProfile.framework_imports` detects a database driver (Npgsql, psycopg2, pg, Spanner, JDBC, etc.), `get_drafter_system_prompt()` SHALL append a P0 security constraint: `"SECURITY CONSTRAINT: MUST use parameterized queries for ALL external inputs. NEVER use string interpolation or concatenation for user-supplied values in SQL/query strings."` |
| SP-INJ-002 | The P0 constraint is a hardcoded string (~50 tokens). It does NOT require YAML templates, budget system changes, or new modules. It is appended directly to the system prompt return value. |
| SP-INJ-003 | The P0 constraint SHALL be appended in `spec_builder.py:build_spec_prompt()` as well, for tasks where `gen_context.get("security_sensitive")` is True. |

### REQ-SP-210: Reference Deviation Policy

| ID | Requirement |
|----|-------------|
| SP-INJ-010 | When a security constraint conflicts with the reference implementation, the P0 constraint SHALL include: `"If the reference uses an insecure pattern (e.g., string interpolation in SQL), DEVIATE and use the secure alternative. Document with: // SECURITY: Deviates from reference (CWE-89)."` |

### REQ-SP-220: P1 Library-Specific Guidance (Phase 1)

| ID | Requirement |
|----|-------------|
| SP-INJ-020 | Phase 1 SHALL add a P1 section with safe/unsafe code examples sourced from `query_prime.patterns.DatabasePatternRegistry.get(database, language).safe_param_syntax`. |
| SP-INJ-021 | P1 guidance SHALL be budget-managed via `enforce_prompt_budget()` at priority level 1 (trimmed under extreme budget pressure, alongside Kaizen hints). |
| SP-INJ-022 | Missing patterns (database×language pair not registered) SHALL degrade to the P0 constraint only — no P1 examples, no error. |

---

## 6. Security Scoring

### REQ-SP-300: Per-File Score

| ID | Requirement |
|----|-------------|
| SP-SCR-001 | Each file processed by the Anzen gate SHALL receive a `security_score` in [0.0, 1.0] derived from its `SecurityVerificationResult`: PASS=1.0, WARN=0.7, FAIL=0.0. |
| SP-SCR-002 | Files where the gate is skipped (no database surface) SHALL receive `security_score = 1.0`. |
| SP-SCR-003 | When finer granularity is needed (multiple findings of different severity), the score SHALL use: `1.0 - max(penalty) - (remaining_penalty_sum × 0.3)` with penalties `warning=0.05, error=0.15`. The worst finding dominates; additional findings contribute at 30% rate. |

### REQ-SP-310: Quality Gate Integration

| ID | Requirement |
|----|-------------|
| SP-SCR-010 | The security score SHALL be evaluated as a PARALLEL gate alongside `quality_score >= _MIN_QUALITY_SCORE` in `prime_contractor.py:_check_quality_gate()`. Both must pass. |
| SP-SCR-011 | Security score threshold: `0.70` (configurable). A file with `quality_score=90, security_score=0.0` is `QUALITY_PASS_SECURITY_FAIL` — distinct from quality failure. |
| SP-SCR-012 | Aggregate security score for a run SHALL be `min(per_file_scores)` — weakest link, not average. |

---

## 7. Kaizen Security Feedback Loop

### REQ-SP-400: Root Cause and Suggestion

| ID | Requirement |
|----|-------------|
| SP-KZ-001 | `prime_postmortem.py:RootCause` SHALL gain `SECURITY_VIOLATION = "security_violation"`. |
| SP-KZ-002 | `CAUSE_TO_SUGGESTION` SHALL map `SECURITY_VIOLATION` to: `"Use parameterized queries for all database operations. See query_prime/patterns/ for language-specific safe patterns."` |
| SP-KZ-003 | Features that fail the Anzen gate SHALL be assigned root cause `SECURITY_VIOLATION` in the postmortem report. |

### REQ-SP-410: Escalating Hints

| ID | Requirement |
|----|-------------|
| SP-KZ-010 | When the same database type produces `SECURITY_VIOLATION` across consecutive runs, Kaizen hints SHALL escalate: Run 1: "Prefer parameterized queries." → Run 2: "You MUST use parameterized queries — previous run had injection in {file}." → Run 3+: "CRITICAL: Injection found in {N} consecutive runs. ALL queries MUST use parameterized bindings. Files will be REJECTED." |
| SP-KZ-011 | Escalation state SHALL be persisted in `kaizen-metrics.json` under a `security` key: `{consecutive_injection_runs: int, last_injection_files: List[str]}`. |

### REQ-SP-420: Security Metrics in Post-Mortem

| ID | Requirement |
|----|-------------|
| SP-KZ-020 | `kaizen-metrics.json` SHALL include: `security.injection_blocked` (count caught by gate), `security.credential_blocked`, `security.aggregate_score`, `security.files_checked`, `security.files_skipped` (no DB surface). |
| SP-KZ-021 | `prime-postmortem-report.json` SHALL include a `security` section per feature: `{verdict, score, findings_count, database, language}`. |

---

## 8. Pipeline Integration

### REQ-SP-500: Task Enrichment

| ID | Requirement |
|----|-------------|
| SP-PL-001 | During plan ingestion, tasks whose `target_files` or description reference database libraries (detected via `query_prime.decomposer.detect_database_type()`) SHALL have `gen_context["security_sensitive"] = True` and `gen_context["detected_database"] = database_type.value` set. |
| SP-PL-002 | `complexity/models.py:TaskComplexitySignals` SHALL gain `security_sensitive: bool = False`. When True, `classify_tier()` SHALL enforce a MODERATE floor — security-sensitive tasks never route below MODERATE. |

### REQ-SP-510: Security Contract (Phase 2)

| ID | Requirement |
|----|-------------|
| SP-PL-010 | Pipeline mode SHALL support a `security_contract` in `gen_context`, derived from `.contextcore.yaml` `spec.security.data_stores` + `LanguageProfile.framework_imports`. |
| SP-PL-011 | The contract SHALL be a dict keyed by database ID, with each entry containing: `client_library`, `safe_param_syntax` (from `DatabasePatternRegistry`), and `sensitivity` (low/medium/high). |
| SP-PL-012 | When `spec.security` is absent, the pipeline SHALL fall back to auto-detection from plan metadata (graceful degradation). |

### REQ-SP-520: Budget System (Phase 1)

| ID | Requirement |
|----|-------------|
| SP-PL-020 | `budget.py` SHALL register `SECURITY_CONSTRAINT` as a P0 section (~200 chars, never trimmed). |
| SP-PL-021 | `budget.py` SHALL register `SECURITY_GUIDANCE` as a P1 section (~800–1600 chars, alongside Kaizen hints). |

---

## 9. Observability

### REQ-SP-600: OTel Integration

| ID | Requirement |
|----|-------------|
| SP-OBS-001 | The Anzen gate SHALL emit an OTel span `security_prime.gate` with attributes: `security.verdict`, `security.score`, `security.database`, `security.finding_count`, `security.language`. |
| SP-OBS-002 | `SecurityVerdict.FAIL` findings SHALL emit OTel span events with finding details for Loki alerting. |
| SP-OBS-003 | Aggregate metrics: `security_prime.score` (histogram), `security_prime.gate_verdicts` (counter by verdict). |

### REQ-SP-610: Logging

| ID | Requirement |
|----|-------------|
| SP-OBS-010 | All logging SHALL use `get_logger(__name__)` per SDK convention. |
| SP-OBS-011 | INFO: gate verdict per file, aggregate score, P0 constraint injected. |
| SP-OBS-012 | WARNING: gate WARN verdict (lifecycle issues). |
| SP-OBS-013 | ERROR: gate FAIL verdict (injection or credential). |

---

## 10. Extensions and Future Work

### Shipped Extensions (2026-03-19/20)

| Extension | Status | Commit | Location |
|-----------|--------|--------|----------|
| **Category S TODOs** | SHIPPED | `56d43a1` | `seeds/todo_derivation.py`, `todo_completion_workflow.py` |
| **OWASP Coverage Matrix** | SHIPPED | `e3d33c1` | `security_prime/owasp_coverage.py` |
| **Allowlist** | SHIPPED | `e3d33c1` | `security_prime/allowlist.py`, wired into `_run_anzen_gate()` |
| **Security Profile CLI** | SHIPPED | `e3d33c1` | `scripts/run_security_profile.py` |
| **Anzen Gate OTel Wiring** | SHIPPED | `e3d33c1` | Wired into `_run_anzen_gate()` |
| **Plan Ingestion Enrichment** | SHIPPED | `db30fb0` | `plan_ingestion_workflow.py` EMIT phase |

### Remaining Work

| Item | Effort | Blocker |
|------|--------|---------|
| Kaizen metrics persistence | ~30 lines | Wire `update_security_metrics()` into postmortem |
| Batch postmortem security trends | ~50 lines | Needs Kaizen metrics persistence first |
| LLM tiers 1–3 | ~400 lines | Needs empirical FP rate data from 10+ production runs |
| De facto S-only detection | ~80 lines | Needs design decision: TODO inventory vs. standalone report |

See [SECURITY_PRIME_REMAINING_WORK.md](./SECURITY_PRIME_REMAINING_WORK.md) for details.

---

## 11. Requirements Index

| ID Range | Section | Count |
|----------|---------|-------|
| SP-GT-001 – SP-GT-012 | Anzen Gate | 10 |
| SP-INJ-001 – SP-INJ-022 | Pre-Generation Injection | 8 |
| SP-SCR-001 – SP-SCR-012 | Security Scoring + Quality Gate | 6 |
| SP-KZ-001 – SP-KZ-021 | Kaizen Feedback | 8 |
| SP-PL-001 – SP-PL-021 | Pipeline Integration | 7 |
| SP-OBS-001 – SP-OBS-013 | Observability | 7 |
| **Total** | | **46** |

---

## 12. Verification Strategy

### Unit Tests

| Test | Target | Method |
|------|--------|--------|
| `test_gate_blocks_injection` | SP-GT-003 | AlloyDB multiline SQL injection → `FAIL` |
| `test_gate_passes_parameterized` | SP-GT-001 | Spanner parameterized → `PASS` (zero false positives) |
| `test_gate_warns_lifecycle` | SP-GT-004 | Per-call DataSource → `WARN` |
| `test_gate_skips_no_database` | SP-GT-005 | Pure data model file → gate skipped, score 1.0 |
| `test_p0_constraint_injected` | SP-INJ-001 | Database driver detected → system prompt contains "MUST use parameterized" |
| `test_p0_not_injected_no_db` | SP-INJ-001 | No database driver → no P0 constraint |
| `test_security_score_pass` | SP-SCR-001 | PASS → 1.0 |
| `test_security_score_fail` | SP-SCR-001 | FAIL → 0.0 |
| `test_quality_pass_security_fail` | SP-SCR-011 | quality=90, security=0.0 → distinct failure type |
| `test_aggregate_weakest_link` | SP-SCR-012 | 13 PASS + 1 FAIL → aggregate 0.0 |
| `test_security_violation_root_cause` | SP-KZ-001 | Gate FAIL → SECURITY_VIOLATION in postmortem |
| `test_kaizen_escalation` | SP-KZ-010 | 3 consecutive runs → "CRITICAL" hint |
| `test_standalone_auto_detect` | SP-GT-010 | No pipeline context → database detected from source |
| `test_otel_span_emitted` | SP-OBS-001 | Gate run → `security_prime.gate` span with attributes |
| `test_reference_deviation_clause` | SP-INJ-010 | Reference in context → deviation policy in P0 |

### Integration Tests

| Test | Target | Method |
|------|--------|--------|
| `test_anzen_gate_e2e` | SP-GT-001–007 | Generate C# cartservice → AlloyDB file REJECTED, Spanner file PASSED |
| `test_security_injection_prevents_vuln` | SP-INJ-001 | Same task with/without P0 → compare injection rate |
| `test_kaizen_feedback_loop` | SP-KZ-010 | Run 1 produces FAIL → Run 2 prompt has escalated hint |

### Regression Golden Files

| File | Expected | Source |
|------|----------|--------|
| AlloyDB multiline injection (C#) | FAIL | Run 078 pattern |
| Spanner parameterized (C#) | PASS | Run 079 false-positive fix |

---

## 13. Phased Delivery Plan

### Phase 0: Wire It In — SHIPPED (`992543a`, `21163d4`)

Anzen gate in `integration_engine.py`, P0 drafter constraint, `security_sensitive` classifier signal, `SECURITY_VIOLATION` root cause. +211 lines across 5 files.

### Phase 1: `security_prime/` Package — SHIPPED (`00eec89`)

Scorer, P1 guidance from `DatabasePatternRegistry`, Kaizen escalation, OTel, YAML templates, budget P0/P1 registration. +549 lines, 6 new files.

### Phase 2: Full Pipeline Integration — SHIPPED (`42fa7a2`, `db30fb0`)

Security contract derivation from `.contextcore.yaml`, task enrichment, standalone auto-detect, plan ingestion EMIT-time tagging. +324 lines, 2 new files.

### Category S TODOs — SHIPPED (`56d43a1`)

B+S dual contract injection, C+S deferral with human review warning, security labels. +110 lines.

### Extensions — SHIPPED (`e3d33c1`)

OWASP coverage matrix, allowlist with suppression in Anzen gate, security profile CLI, OTel wiring in gate. +498 lines, 3 new files.

### Remaining (deferred — see [SECURITY_PRIME_REMAINING_WORK.md](./SECURITY_PRIME_REMAINING_WORK.md))

- Kaizen metrics persistence (~30 lines wiring)
- Batch postmortem security trends (~50 lines)
- LLM tiers 1–3: when Tier 0 FP data warrants
- De facto S-only detection: needs design decision on report location

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Anzen** | 安全 — "safety." Security as a structural pipeline property |
| **Anzen gate** | Call to `query_prime.security.verify_file()` in the integration engine |
| **P0 constraint** | Hardcoded security directive in the LLM prompt, never trimmed |
| **P1 guidance** | Budget-managed safe/unsafe code examples from pattern registry |
| **Security Prime** | This orchestration layer (`security_prime/`). Wires existing checks into pipeline |
| **Query Prime** | The existing check + pattern + generation infrastructure (`query_prime/`). Already built |
| **`verify_file()`** | `query_prime.security.verify_file(source, path, database, language) → SecurityVerificationResult` |

## Appendix B: AlloyDB/Spanner Case Study

Preserved from v0.1.0 — the incidents that motivated this work.

### B.1 AlloyDB — Genuine SQL Injection (Run 78–79)

```csharp
selectCmd.CommandText =
    $"SELECT quantity FROM {_tableName} " +
    $"WHERE userId='{userId}' AND productId='{productId}'";
```

**How `query_prime` addresses it:** `security/injection.py` two-pass detection: identifies SQL construction site on line 1, tracks multiline context, flags the `WHERE` clause interpolation on line 3. `patterns/postgresql.py` provides `unsafe_patterns` that match `$"...{var}..."`.

### B.2 Spanner — False Positive (Run 79)

```csharp
cmd.CommandText = "SELECT quantity FROM cart_items WHERE user_id = @userId AND product_id = @productId";
cmd.Parameters.Add("userId", SpannerDbType.String, userId);
```

**How `query_prime` addresses it:** `patterns/spanner.py` provides `safe_patterns` that match `SpannerParameter`, `Parameters.Add`. Two-pass detection (injection.py:92–99) suppresses the finding when safe parameterization is detected in adjacent lines.

### B.3 What Security Prime Adds

Neither case is caught or prevented by the current pipeline because `verify_file()` is not called during generation. Security Prime wires it in:
- **Prevention:** P0 constraint tells the LLM to use parameterized queries BEFORE generating code
- **Detection:** Anzen gate calls `verify_file()` AFTER generation and REJECTS injection
- **Learning:** `SECURITY_VIOLATION` root cause feeds Kaizen hints into the NEXT run
