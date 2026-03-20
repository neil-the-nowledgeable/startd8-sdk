# Security Prime — Implementation Plan

> **Version:** 5.0.0 — COMPLETE
> **Date:** 2026-03-20
> **Requirements:** [SECURITY_PRIME_REQUIREMENTS.md](./SECURITY_PRIME_REQUIREMENTS.md) v1.1.0 (46 requirements)
> **Check Infrastructure:** `src/startd8/query_prime/` — IMPLEMENTED (not rebuilt)
> **Shipped Code:** ~1,700 lines across 9 commits (Phases 0–2 + Category S + extensions + emitter enrichment)
> **Principle:** Anzen — Security Correctness by Design (安全)
> **Status:** All planned phases SHIPPED. Remaining items tracked in [SECURITY_PRIME_REMAINING_WORK.md](./SECURITY_PRIME_REMAINING_WORK.md).

---

## Context

`query_prime/` already provides: two-pass injection detection, credential leakage, lifecycle checks, 5 database pattern modules (PostgreSQL, Spanner, MySQL, Redis, SQLite × multiple languages), `verify_file()` pipeline with PASS/WARN/FAIL, `QueryPrimeEngine` with tier routing and T3→T2→T1 escalation, and LLM generation with safe-pattern system prompts.

**None of that is rebuilt.** This plan wires it into the generation pipeline.

---

## Phase 0: Wire It In

**Goal:** Anzen gate live. Runs 78–79 fixed. Single PR.

**~50 lines across 5 existing files. Zero new files.**

### Changes

**1. `contractors/integration_engine.py`** (~20 lines)

After `_run_semantic_checks()` (line ~2077), before advisory downgrade:

```python
# Anzen gate — security verification via query_prime
from startd8.query_prime.security import verify_file
from startd8.query_prime.decomposer import detect_database_type
from startd8.query_prime.models import SecurityVerdict

db_type = detect_database_type(source_code)
if db_type is not None:
    sv_result = verify_file(source_code, file_path, db_type, language_id)
    if sv_result.verdict == SecurityVerdict.FAIL:
        logger.error("Anzen gate FAIL: %s — %s", file_path,
                      sv_result.findings[0].message if sv_result.findings else "injection/credential")
        # Hard failure — NOT subject to advisory downgrade
        return IntegrationResult(success=False, reason=f"Anzen gate: {sv_result.findings[0].message}")
    elif sv_result.verdict == SecurityVerdict.WARN:
        logger.warning("Anzen gate WARN: %s — lifecycle issue", file_path)
```

**2. `implementation_engine/drafter.py`** (~10 lines)

In `get_drafter_system_prompt()`, after language role injection:

```python
# P0 security constraint when database framework detected
if language_profile and hasattr(language_profile, 'framework_imports'):
    db_frameworks = {"npgsql", "psycopg2", "pg", "spanner", "jdbc", "mysql", "sqlite3", "redis"}
    detected = [fw for fw in language_profile.framework_imports if fw in db_frameworks]
    if detected:
        prompt += (
            "\n\nSECURITY CONSTRAINT: MUST use parameterized queries for ALL external inputs. "
            "NEVER use string interpolation or concatenation for user-supplied values in SQL/query strings. "
            "If the reference uses an insecure pattern, DEVIATE and use the secure alternative. "
            "Document with: // SECURITY: Deviates from reference (CWE-89)."
        )
```

**3. `implementation_engine/spec_builder.py`** (~5 lines)

In `build_spec_prompt()`, when `context.get("security_sensitive")`:

```python
if context.get("security_sensitive"):
    sections.append("SECURITY CONSTRAINT: MUST use parameterized queries. "
                     "NEVER use string interpolation in SQL/query strings.")
```

**4. `complexity/models.py` + `complexity/classifier.py`** (~10 lines)

```python
# models.py — add field:
security_sensitive: bool = False

# classifier.py — after COMPLEX triggers, before SIMPLE eligibility:
if signals.security_sensitive and result_tier in (ComplexityTier.TRIVIAL, ComplexityTier.SIMPLE):
    return _emit(ComplexityTier.MODERATE,
                 f"{reason}; elevated to MODERATE (security_sensitive)", signals)
```

**5. `contractors/prime_postmortem.py`** (~5 lines)

```python
# In RootCause enum:
SECURITY_VIOLATION = "security_violation"

# In CAUSE_TO_SUGGESTION:
RootCause.SECURITY_VIOLATION: (
    "Use parameterized queries for all database operations. "
    "See query_prime/patterns/ for language-specific safe patterns."
),
```

### Done When

1. C# cartservice generation → AlloyDB `$"SELECT...{userId}"` file **REJECTED** by Anzen gate
2. Spanner `SpannerParameterCollection` file **PASSES** with zero false positives
3. P0 constraint visible in walkthrough mode when database framework detected
4. `SECURITY_VIOLATION` appears in postmortem for rejected features
5. `security_sensitive=True` elevates TRIVIAL/SIMPLE → MODERATE
6. All existing tests pass

### What This Does NOT Touch

- No new package
- No new data models (uses `query_prime.models.SecurityVerificationResult`)
- No YAML templates
- No budget system changes
- No namespace rename
- No scoring formula

---

## Phase 1: `security_prime/` Package

**Goal:** Structured orchestration — scoring, YAML-backed guidance, Kaizen escalation, OTel.

**~300 lines across 6 new files + 3 modified files.**

### New Files

```
src/startd8/security_prime/
├── __init__.py              # Public API: run_anzen_gate(), inject_guidance()
├── scorer.py                # compute_security_score(): PASS=1.0, WARN=0.7, FAIL=0.0
│                            #   + max-severity-weighted for multi-finding granularity
│                            #   + aggregate = min(per_file_scores)
├── guidance.py              # inject_p1_guidance(): loads safe_param_syntax from
│                            #   DatabasePatternRegistry, formats as P1 prompt section
├── kaizen.py                # generate_security_hint(): escalating hints across runs
│                            #   + security metrics for kaizen-metrics.json
├── otel.py                  # security_prime.gate span + attributes + events
└── templates/
    └── security_constraints.yaml  # Human-editable safe/unsafe examples (supplements
                                   #   pattern registry with prose explanations + CWE refs)
```

### Modified Files

| File | Change |
|------|--------|
| `implementation_engine/budget.py` | Register `SECURITY_CONSTRAINT` (P0) and `SECURITY_GUIDANCE` (P1) priority sections |
| `implementation_engine/spec_builder.py` | Replace Phase 0's inline P0 string with `security_prime.guidance.inject_p1_guidance()` call for security_sensitive tasks |
| `contractors/batch_postmortem.py` | Add `security` section to cross-run trends: `consecutive_injection_runs`, `aggregate_score_trajectory` |

### Key Design Decisions

- **`scorer.py` uses `query_prime.models.SecurityVerificationResult` directly** — no new score model. Maps verdict → float, optionally refines with finding-level penalties.
- **`guidance.py` reads from `DatabasePatternRegistry`** — no duplicated pattern data. Formats `safe_param_syntax` tuples into prompt text with CWE references from the YAML supplement.
- **`kaizen.py` reads/writes `kaizen-metrics.json`** — adds a `security` key alongside existing quality metrics. Escalation state (`consecutive_injection_runs`) persists across runs.

### Done When

1. Security score reported in postmortem alongside quality score
2. P1 guidance shows library-specific safe patterns in walkthrough mode
3. Kaizen hint escalates from "prefer" → "MUST" → "CRITICAL" across 3 runs
4. OTel span `security_prime.gate` visible in Tempo/Grafana
5. Budget system enforces P0 (never trimmed) and P1 (trimmed under pressure)

---

## Phase 2: Full Pipeline Integration

**Goal:** Security contract from manifest, plan ingestion enrichment, reference deviation tracking.

**~200 lines across 2 new files + 2 modified files.**

### New Files

```
src/startd8/security_prime/
├── contract.py              # derive_security_contract(): manifest + plan + DatabasePatternRegistry
│                            #   → dict[database_id → {client_library, safe_param_syntax, sensitivity}]
└── enrichment.py            # enrich_security_tasks(): tag tasks during plan ingestion
│                            #   → sets gen_context["security_sensitive"], gen_context["detected_database"]
```

### Modified Files

| File | Change |
|------|--------|
| `workflows/builtin/plan_ingestion_workflow.py` | Call `enrichment.enrich_security_tasks()` during task enrichment phase |
| `contractors/prime_contractor.py` | In `_build_gen_context()`: load security contract from `gen_context` in pipeline mode; auto-derive in standalone mode |

### Key Design Decisions

- **Contract is a plain dict, not a Pydantic model.** The existing `query_prime.models.SecurityContract` dataclass can be used if needed, but a dict keyed by database ID is sufficient for gen_context forwarding and simpler to serialize.
- **`enrichment.py` reuses `query_prime.decomposer.detect_database_type()`** — no new detection logic.
- **Standalone mode auto-derive** calls `detect_database_type()` on the task description; pipeline mode reads from `gen_context["detected_database"]` set during plan ingestion.

### Done When

1. `.contextcore.yaml` `spec.security.data_stores` parsed and forwarded as contract
2. Tasks auto-tagged `security_sensitive` during plan ingestion
3. Standalone mode derives database from task content with INFO log
4. Contract forwarded through Mottainai artifact chain (gen_context propagation)

---

## Dependency Graph

```
Phase 0: Wire It In (1 PR, ~50 lines)
  │
  ├──▶ Phase 1: security_prime/ package (~300 lines)
  │     │
  │     └──▶ Phase 2: Pipeline integration (~200 lines)
  │
  └──▶ Future: LLM tiers, Category S, Security profile, Allowlist
       (deferred — see requirements §10)
```

**Critical path:** Phase 0 → Phase 1 → Phase 2. All sequential; each builds on the prior.

---

## Validation Milestones

| After | Validation | Proves |
|-------|-----------|--------|
| **Phase 0** | AlloyDB REJECTED, Spanner PASSES, P0 constraint in prompt | Anzen gate live, runs 78–79 fixed |
| **Phase 1** | Score in postmortem, P1 guidance in walkthrough, Kaizen escalation | Feedback loop operational |
| **Phase 2** | Pipeline run with manifest-derived contract, standalone auto-detect | Full pipeline coverage |

---

## What We Chose NOT To Build (and Why)

| Capability | Why Not Now | When To Reconsider |
|-----------|-------------|-------------------|
| New check modules | `query_prime/security/` already has injection, credentials, lifecycle | When new check types are needed (auth, crypto, deserialization) |
| New pattern modules | `query_prime/patterns/` already covers 5 databases × multiple languages | When a new database is used in production |
| `security/` package (namespace rename) | `security_prime/` avoids collision; only 4 import sites reference `startd8.security` | Never — naming is settled |
| LLM-augmented validation (Tiers 1–3) | Zero false-positive-rate data; Tier 0 may be sufficient | When Tier 0 FP rate > 5% across 3+ runs |
| SecurityDomain enum (10 domains) | Only 3 domains have checks (injection, credentials, lifecycle) | When checks exist for new domains |
| Category S TODOs | TODO Completion workflow not yet mature | When REQ-TCW-100 is stable |
| Security profile CLI | Thin wrapper around contract derivation | When Phase 2 is stable |
| OWASP coverage matrix | ~50 lines, pure metadata, can ship anytime | Whenever convenient |
| Allowlist | Zero operator demand for false-positive suppression | When operators request it |

---

## Summary

| Metric | v1.0 Plan | v2.0 Plan | v3.0 Plan | v4.0 Plan (this) |
|--------|-----------|-----------|-----------|------------------|
| Requirements | 177 | 203 | 203 | **46** |
| Phases | 9 | 10 | 6 | **3** |
| New code (lines) | ~4,000 | ~4,000 | ~950 | **~550** |
| New files | ~35 | ~40 | ~8 | **6** |
| Modified files | ~20 | ~25 | ~8 | **7** |
| Phase 0 (immediate fix) | — | 150 lines | 150 lines | **50 lines** |
| Check code written | All new | All new | None (reuse query_prime) | **None** |
| Pattern modules written | All new | All new | None (reuse query_prime) | **None** |
