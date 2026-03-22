# Query Prime Activation — Implementation Plan

> **Requirements:** [QUERY_PRIME_ACTIVATION_REQUIREMENTS.md](QUERY_PRIME_ACTIVATION_REQUIREMENTS.md)
> **Date:** 2026-03-22
> **Estimated scope:** ~150 lines across 5 files + ~80 lines of tests

---

## Implementation Order

Ordered by dependency — Layer D (trend script fix) unblocks validation of everything else.

```
Phase 1: Fix what's broken          (D → A)
Phase 2: Expand what's narrow       (B → C)
Phase 3: Validate end-to-end
```

---

## Phase 1: Fix Broken Routing (REQ-QPA-4xx → 1xx)

### Step 1.1 — Fix trend script field mapping (REQ-QPA-400)

**File:** `scripts/run_query_prime_trends.py`
**Function:** `_load_runs()`

**Current (broken):**
```python
run_dir = output_dir / entry.get("relative_path", "")
metrics_path = run_dir / "kaizen-metrics.json"
```

**Fix:**
```python
# Try absolute metrics_path first (current kaizen-index format)
metrics_path = Path(entry.get("metrics_path", ""))
if not metrics_path.is_file():
    # Fall back to run_dir + filename
    run_dir = Path(entry.get("run_dir", ""))
    metrics_path = run_dir / "kaizen-metrics.json"
if not metrics_path.is_file():
    # Legacy: relative_path
    run_dir = output_dir / entry.get("relative_path", "")
    metrics_path = run_dir / "kaizen-metrics.json"
if not metrics_path.is_file():
    metrics_path = run_dir / "query-security-metrics.json"
```

**Effort:** ~10 lines changed
**Test:** Verify `_load_runs()` returns runs from online-boutique kaizen-index.json

---

### Step 1.2 — Write query-security-metrics.json to pipeline output (REQ-QPA-102)

**File:** `src/startd8/contractors/integration_engine.py`
**Location:** After line 1580 (`update_query_security_metrics(output_dir, qp_report)`)

**Add:**
```python
# REQ-QPA-102: standalone query-security-metrics.json in pipeline output
if out_dir:
    qp_standalone_path = Path(out_dir) / "query-security-metrics.json"
    try:
        import json as _json
        qp_report_with_meta = {
            "schema_version": "1.0.0",
            "run_id": unit.get("run_id", ""),
            "timestamp": _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
            **qp_report,
        }
        qp_standalone_path.write_text(_json.dumps(qp_report_with_meta, indent=2) + "\n")
        logger.info("Wrote query-security-metrics.json to %s", qp_standalone_path)
    except OSError as exc:
        logger.warning("Advisory: failed to write query-security-metrics.json: %s", exc)
```

**Effort:** ~15 lines
**Dependency:** Needs `out_dir` — check how `write_gate_metrics_report` receives it (line 1530)

---

### Step 1.3 — Write security-gate-metrics.json to pipeline output (REQ-QPA-101)

**File:** `src/startd8/contractors/integration_engine.py`
**Location:** `write_gate_metrics_report(gate_report, out_dir)` at line 1530

**Check:** Does `out_dir` point to pipeline output or project root? If project root, add a second write to pipeline output. The `out_dir` is likely derived from `self._output_dir` or a similar attribute.

**Effort:** ~5 lines (add second write path)

---

### Step 1.4 — Merge query_security into pipeline-output kaizen-metrics.json (REQ-QPA-100)

**File:** `src/startd8/contractors/prime_postmortem.py`
**Location:** Where `kaizen-metrics.json` is written to pipeline output

**Approach:** After writing the postmortem's `kaizen-metrics.json`, read back, check if project-root version has `query_security`, and merge it in.

**Alternative (simpler):** Pass `qp_report` through the result metadata so the postmortem can include it directly.

**Effort:** ~15 lines

---

## Phase 2: Expand Coverage (REQ-QPA-2xx → 3xx)

### Step 2.1 — Add Go DB import patterns to detect_database_type (REQ-QPA-200)

**File:** `src/startd8/query_prime/decomposer.py`
**Dict:** `_DATABASE_PATTERNS`

**Add entries:**
```python
"database/sql": DatabaseType.POSTGRESQL,    # Go stdlib
"pgxpool": DatabaseType.POSTGRESQL,         # pgx pool
"jackc/pgx": DatabaseType.POSTGRESQL,       # pgx driver
"go-redis": DatabaseType.REDIS,             # Go Redis client
"go-sql-driver/mysql": DatabaseType.MYSQL,  # Go MySQL driver
"mattn/go-sqlite3": DatabaseType.SQLITE,    # Go SQLite driver
"lib/pq": DatabaseType.POSTGRESQL,          # Older Go PG driver
```

**Effort:** ~7 lines
**Test:** 6 new assertions in test_decomposer.py

---

### Step 2.2 — Auto-tag security_sensitive in seed builder (REQ-QPA-300, 301)

**File:** `src/startd8/seeds/builder.py` (or `src/startd8/security_prime/enrichment.py`)

**Check first:** Does `enrich_security_fields()` in `security_prime/enrichment.py` already do this? The exploration report says it calls `detect_database_type()` on task descriptions during plan ingestion. If so, verify it runs during `SeedBuilder.derive_tasks()`, not just plan ingestion.

**If missing from SeedBuilder:**
```python
# In SeedBuilder.derive_tasks() or _build_task():
from startd8.security_prime.enrichment import enrich_security_fields

security = enrich_security_fields(task_description, target_files)
if security.get("security_sensitive"):
    gen_context["security_sensitive"] = True
    gen_context["detected_database"] = security.get("detected_database")
```

**Effort:** ~10 lines
**Test:** "Catalog Loader (AlloyDB + Local JSON)" → `security_sensitive: true`, `detected_database: "postgresql"`

---

### Step 2.3 — Gate security_sensitive files without DB keywords (REQ-QPA-202)

**File:** `src/startd8/contractors/integration_engine.py`
**Location:** Anzen gate `_run_anzen_gate()`, around line 1252

**Current:**
```python
db_type = detect_database_type(source)
if db_type is None:
    files_skipped += 1
    continue  # No database surface — skip
```

**Fix — add metadata fallback:**
```python
db_type = detect_database_type(source)
if db_type is None:
    # REQ-QPA-201/202: check seed metadata for security_sensitive features
    feature_meta = self._get_feature_metadata_for_file(fpath, unit)
    if feature_meta and feature_meta.get("security_sensitive"):
        db_type_str = feature_meta.get("detected_database", "")
        db_type = _resolve_db_type(db_type_str) if db_type_str else "unknown"
    else:
        files_skipped += 1
        continue
```

**Helper needed:** `_get_feature_metadata_for_file(fpath, unit)` — looks up which feature produced this file and returns its gen_context. This may already exist via the generation manifest.

**Effort:** ~20 lines
**Risk:** Medium — needs to thread feature metadata into the Anzen gate

---

## Phase 3: Validate End-to-End

### Step 3.1 — Run existing tests

```bash
pytest tests/unit/query_prime/ -v --tb=short
```

Verify 325+ tests still pass.

### Step 3.2 — Add new tests

**File:** `tests/unit/query_prime/test_decomposer.py` (extend)
- `test_detect_database_type_go_stdlib`
- `test_detect_database_type_pgx_pool`
- `test_detect_database_type_go_redis`
- `test_detect_database_type_go_mysql`
- `test_detect_database_type_go_sqlite`
- `test_detect_database_type_lib_pq`

**File:** `tests/unit/query_prime/test_kaizen_wiring.py` (extend)
- `test_load_runs_absolute_metrics_path`
- `test_load_runs_run_dir_fallback`
- `test_load_runs_relative_path_compat`

**File:** `tests/unit/seeds/test_security_enrichment.py` (new or extend)
- `test_auto_tag_alloydb_description`
- `test_no_auto_tag_template_description`
- `test_manual_tag_not_overridden`

**Effort:** ~60 lines of tests

### Step 3.3 — Dry-run validation against online-boutique

After implementing Phases 1-2:
```bash
# Verify detect_database_type catches the generated catalog_loader.go
python3 -c "
from startd8.query_prime.decomposer import detect_database_type
source = open('.../catalog_loader.go').read()
print(detect_database_type(source))  # Should: DatabaseType.POSTGRESQL
"

# Verify trend script reads from kaizen-index
python3 scripts/run_query_prime_trends.py \
    --output-dir /path/to/online-boutique/pipeline-output/online-boutique \
    --json

# Expected: runs_analyzed >= 1 (was 0 before fix)
```

### Step 3.4 — Re-run online-boutique (optional live validation)

A full re-run of the online-boutique pipeline after all fixes would validate:
- ≥2 files gated (catalog_loader.go + any other DB-touching file)
- `query_security` in pipeline-output kaizen-metrics.json
- `query-security-metrics.json` standalone in pipeline output
- Trend script reports 1+ runs with query data

---

## File Change Summary

| File | Phase | Changes | Effort |
|------|-------|---------|--------|
| `scripts/run_query_prime_trends.py` | 1.1 | Fix `_load_runs()` field mapping | ~10 lines |
| `src/startd8/contractors/integration_engine.py` | 1.2, 1.3, 2.3 | Write standalone JSON + gate security_sensitive files | ~40 lines |
| `src/startd8/contractors/prime_postmortem.py` | 1.4 | Merge query_security into pipeline kaizen-metrics | ~15 lines |
| `src/startd8/query_prime/decomposer.py` | 2.1 | Add Go DB import patterns | ~7 lines |
| `src/startd8/seeds/builder.py` | 2.2 | Auto-tag security_sensitive | ~10 lines |
| Tests (3 files) | 3.2 | New test cases | ~60 lines |
| **Total** | | | **~142 lines** |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `database/sql` false positive on non-DB Go files | Low | Medium | `database/sql` is specific enough; only DB code imports it |
| Feature metadata not available at Anzen gate time | Medium | High | Check generation manifest for file→feature mapping; fall back to skipping |
| Postmortem merge creates race condition | Low | Low | Merge is append-only; `query_security` key doesn't conflict with existing keys |
| Trend script changes break existing pipeline | Low | Medium | Backward-compatible field resolution (try new fields, fall back to old) |
