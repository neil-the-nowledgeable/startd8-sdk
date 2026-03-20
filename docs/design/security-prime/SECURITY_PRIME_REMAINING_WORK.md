# Security Prime — Remaining Work

> **Updated:** 2026-03-20
> **Status:** Phases 0–2 + Category S + extensions + plan ingestion enrichment shipped.

---

## Shipped (closed)

| # | Item | Commit | Lines |
|---|------|--------|-------|
| 1 | OWASP Coverage Matrix | `e3d33c1` | `security_prime/owasp_coverage.py` |
| 2 | Allowlist + gate wiring | `e3d33c1` | `security_prime/allowlist.py`, `integration_engine.py` |
| 3 | Security Profile CLI | `e3d33c1` | `scripts/run_security_profile.py` |
| 4 | Anzen Gate OTel Wiring | `e3d33c1` | Wired into `_run_anzen_gate()` |
| 9 | Plan Ingestion Enrichment | `db30fb0` | `plan_ingestion_workflow.py` EMIT phase |

---

## Almost Available (~30–50 lines each, need wiring)

### 5. Kaizen Metrics Persistence (~30 lines)
`security_prime/kaizen.py:update_security_metrics()` exists but isn't called after runs complete. Wire into the postmortem evaluator or the prime contractor's post-run cleanup to persist `kaizen-metrics.json` security section.

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
