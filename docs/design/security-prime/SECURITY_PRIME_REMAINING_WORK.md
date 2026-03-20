# Security Prime — Remaining Work

> **Date:** 2026-03-19
> **Status:** Phases 0–2 + Category S shipped. This tracks remaining extensions.

---

## Available Now (~50–100 lines each)

### 1. OWASP Coverage Matrix (~50 lines)
Static mapping from `SecurityCheckType` → OWASP Top 10 categories. No code analysis — just a dict + report function. Everything needed exists in `query_prime.models.SecurityCheckType` (INJECTION, CREDENTIAL_LEAKAGE, LIFECYCLE). Map to A01–A10, report covered/uncovered in postmortem.

**File:** `security_prime/owasp_coverage.py`

### 2. Allowlist (~60 lines)
Load `security_allowlist.yaml` from project root, filter findings against `file_pattern + check_id` before verdict computation. Schema: `entries: [{file_pattern, check_id, justification}]`. The Anzen gate already has findings — add a filter step before the verdict check in `integration_engine.py:_run_anzen_gate()`.

**Files:** `security_prime/allowlist.py`, modify `integration_engine.py`

### 3. Security Profile CLI (~100 lines)
`scripts/run_security_profile.py` — calls `derive_security_contract()` (Phase 2), formats output as `security-profile.json`, prints a review checklist. Thin CLI wrapper around `contract.py` + `DatabasePatternRegistry.get_all_for_database()`.

**File:** `scripts/run_security_profile.py`

---

## Almost Available (~10–50 lines each, need wiring)

### 4. Anzen Gate OTel Wiring (~10 lines)
`security_prime/otel.py:record_gate_result()` exists but isn't called from `integration_engine.py:_run_anzen_gate()`. Add the call after each `verify_file()` result.

**File:** modify `integration_engine.py:_run_anzen_gate()`

### 5. Kaizen Metrics Persistence (~30 lines)
`security_prime/kaizen.py:update_security_metrics()` exists but isn't called after runs complete. Wire into the postmortem evaluator or the prime contractor's post-run cleanup.

**File:** modify `contractors/prime_contractor.py` or `prime_postmortem.py`

### 6. Batch Postmortem Security Trends (~50 lines)
`batch_postmortem.py` needs a `security` section reading `kaizen-metrics.json` security data across runs. Reports `aggregate_score_trajectory`, `consecutive_injection_runs`.

**Dependency:** Item 5 (Kaizen metrics persistence) must be wired first.

**File:** modify `contractors/batch_postmortem.py`

---

## Far From Available (need design decisions, data, or external dependencies)

### 7. LLM Tiers 1–3
System prompt for security analyst LLM, JSON schema for findings, deduplication against Tier 0, cost tracking. **Blocked on:** empirical FP rate data from production runs through the Anzen gate. No production data exists yet. Revisit after 10+ pipeline runs.

### 8. De Facto S-Only Detection
Detect SQL interpolation patterns WITHOUT `// TODO` markers (implicit security TODOs). Run `detect_injection()` as a scanner, report in TODO inventory or separate security inventory. **Needs decision:** report location (TODO inventory extension vs. standalone report).

### 9. Full Pipeline Plan Ingestion Enrichment
Move `security_sensitive` tagging from generation-time (`_inject_security_contract`) into plan ingestion EMIT phase so the seed file carries security metadata before reaching the contractor. **Medium complexity:** emitter is ~500 lines, insertion point is clear but requires careful threading.
