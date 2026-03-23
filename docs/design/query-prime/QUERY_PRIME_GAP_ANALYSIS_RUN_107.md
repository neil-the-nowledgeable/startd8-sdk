# Query Prime Gap Analysis — Run-107 (Node.js Currency + Payment)

> **Date:** 2026-03-23
> **Run:** run-107-20260323T1012 (10 Node.js features, score 1.00)
> **Context:** First Node.js run evaluated against KAIZEN_QUERY_PRIME_REQUIREMENTS.md

---

## 1. Metadata Pollution Root Cause

Run-107 reports `query_security.by_database.postgresql: {count: 1}` despite being a Node.js run with zero database operations. Root cause is a **5-link chain**:

```
1. queue.py:228-344 — seed context fields (detected_database, security_sensitive)
   are NOT extracted into FeatureSpec.metadata

2. prime_contractor.py:287 — FeatureSpecUnit.context delegates to metadata
   which is missing these fields

3. integration_engine.py:1252-1272 — Anzen gate calls detect_database_type(source)
   which returns None for Node.js files, falls back to unit_ctx.get("security_sensitive")
   which is also None → ALL files skipped

4. integration_engine.py:1422 — update_query_security_metrics() gated behind
   `if gate_results:` — since all files were skipped, gate_results is empty,
   metrics never written for this run

5. project_root/query-security-metrics.json — stale file from prior C# run
   (run_id: "97c66812", timestamp 6 hours before run-107) never overwritten,
   gets read by postmortem aggregation → postgresql appears in Node.js metrics
```

**Fix:** Two changes needed:
- **A.** Extract `detected_database` and `security_sensitive` from seed context into FeatureSpec.metadata in `queue.py` (broken bridge)
- **B.** When a run has zero gate_results, write an EXPLICIT empty `query-security-metrics.json` instead of leaving the stale file from a prior run

---

## 2. Gap Catalog

### Tier 1 — Foundational (Must Fix First)

| ID | Description | Violates | Root Cause | Severity |
|----|-------------|----------|------------|----------|
| **QP-GAP-001** | Stale query-security-metrics.json pollutes non-DB runs | REQ-KQP-100 | `update_query_security_metrics()` gated behind non-empty gate_results; stale file persists | **Critical** |
| **QP-GAP-002** | Seed→FeatureSpec metadata bridge drops `detected_database` | REQ-KQP-501, REQ-QPI-105 | `queue.py:228-344` extracts 7 fields but not `detected_database`/`security_sensitive` | **Critical** |
| **QP-GAP-003** | No explicit "no queries to secure" signal | — | When run has zero DB operations, nothing is emitted; downstream assumes stale state | **High** |

### Tier 2 — Schema/Wiring

| ID | Description | Violates | Root Cause | Severity |
|----|-------------|----------|------------|----------|
| **QP-GAP-004** | `kaizen-metrics.json` query_security schema incomplete (6/9 fields missing) | REQ-KQP-500, 300, 301, 302 | `update_query_security_metrics()` populates only mean_score, pass_rate, total_work_items, by_database, by_tier | **High** |
| **QP-GAP-005** | No "Query Security" section in postmortem summary | REQ-KQP-502 | Template exists in requirements but not injected in `prime_postmortem.py` | **High** |
| **QP-GAP-006** | query-security-metrics.json not written to run directory | REQ-KQP-100, REQ-QPI-002 | Written to project root only; trend script scans run directories | **High** |

### Tier 3 — Feedback Loop

| ID | Description | Violates | Root Cause | Severity |
|----|-------------|----------|------------|----------|
| **QP-GAP-007** | Trend script returns 0 runs (insufficient_data) | REQ-KQP-400, 401, 402 | Metrics file not in run directory; trend script can't find it | **Medium** |
| **QP-GAP-008** | FP registry not wired to postmortem metrics | REQ-KQP-200, 500 | `update_query_security_metrics()` doesn't read FP registry | **Medium** |
| **QP-GAP-009** | CAUSE_TO_SUGGESTION has 3 entries, requirements specify 8 | REQ-KQP-602 | Only high-level security check types mapped, not database-specific | **Medium** |
| **QP-GAP-010** | Routing overrides never created | REQ-KQP-601, 302 | No batch postmortem wiring to trigger after ≥10 runs | **Low** |

---

## 3. Requirements for Fixes

### REQ-QP-FIX-001: Explicit Empty Metrics on Zero-Query Runs

When a Prime Contractor run produces zero Anzen gate results (no database-facing files verified), the integration engine MUST write an explicit empty `query-security-metrics.json` that supersedes any stale file:

```json
{
  "schema_version": "1.0.0",
  "run_id": "run-107-20260323T1012",
  "timestamp": "2026-03-23T10:39:58Z",
  "status": "no_queries_detected",
  "mean_score": null,
  "pass_rate": null,
  "total_work_items": 0,
  "by_database": {},
  "by_tier": {},
  "injection_total": 0,
  "credential_total": 0,
  "lifecycle_total": 0
}
```

**Key:** `"status": "no_queries_detected"` explicitly signals that this run had no database operations — distinct from "queries were checked and all passed" (`"status": "pass"`).

**Implementation:** In `integration_engine.py`, after the Anzen gate loop, if `not gate_results` AND `not enriched_entries`, write the empty metrics file. This prevents stale data from prior runs persisting.

### REQ-QP-FIX-002: Seed→FeatureSpec Metadata Bridge

In `queue.py:add_features_from_seed()`, extract `detected_database` and `security_sensitive` from `config.context` into `FeatureSpec.metadata`:

```python
# After existing metadata extraction (line ~340)
_ctx = config.get("context", {})
if _ctx.get("detected_database"):
    metadata["detected_database"] = _ctx["detected_database"]
if _ctx.get("security_sensitive"):
    metadata["security_sensitive"] = True
```

**Impact:** The Anzen gate's fallback at line 1257 (`unit_ctx.get("security_sensitive")`) will now find the field, enabling database-specific verification even when `detect_database_type(source)` returns None.

### REQ-QP-FIX-003: Kaizen-Metrics Empty Query Security Section

When the run has zero query work items, the `query_security` key in `kaizen-metrics.json` MUST be explicitly set to indicate absence:

```json
"query_security": {
  "status": "no_queries_detected",
  "total_work_items": 0,
  "by_database": {},
  "by_tier": {}
}
```

**Implementation:** In `security_prime/kaizen.py:update_query_security_metrics()`, when `report` is None or empty, write the explicit empty section instead of skipping the key entirely.

### REQ-QP-FIX-004: Stale File Overwrite Guard

The project-root `query-security-metrics.json` MUST be overwritten on every run, even if the run produces no query work items. This prevents stale data from contaminating subsequent run metrics.

**Rule:** `update_query_security_metrics()` is called unconditionally after the Anzen gate — not gated behind `if gate_results:`.

---

## 4. Non-Failure Observations (Correct Behavior)

These are behaviors that LOOK like gaps but are actually correct for a non-database Node.js run:

| Observation | Why It's Correct |
|-------------|-----------------|
| 0 Kaizen suggestions | Perfect score → nothing to improve |
| `console.warn()` in paymentservice/server.js not flagged | `server.js` is in the `_check_console_log_in_service()` allow list (entry points may use console) |
| All `semantic_issues: []` | Node.js semantic checks ran but found no issues (code uses `pino` logger, no `var`, no CJS/ESM mixing) |
| 10 exemplars extracted | All features clean → all eligible for exemplar extraction |

---

## 5. Priority Implementation Order

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | REQ-QP-FIX-001 (empty metrics on zero-query) | ~15 lines | Eliminates metadata pollution across all non-DB runs |
| **P0** | REQ-QP-FIX-004 (stale file overwrite guard) | ~10 lines | Prevents stale data from ever persisting |
| **P1** | REQ-QP-FIX-002 (seed→FeatureSpec bridge) | ~10 lines | Enables Anzen gate to use seed-level database context |
| **P1** | REQ-QP-FIX-003 (empty kaizen section) | ~10 lines | Clean metrics for non-DB runs |
| **P2** | QP-GAP-005 (postmortem summary section) | ~30 lines | "Query Security" section in summary.md |
| **P2** | QP-GAP-006 (file to run directory) | ~5 lines | Fixes trend script |
