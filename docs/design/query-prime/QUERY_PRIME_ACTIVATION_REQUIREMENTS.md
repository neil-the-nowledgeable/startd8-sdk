# Query Prime Activation & Artifact Routing — Requirements

> **Version:** 1.0.0
> **Status:** IMPLEMENTED — 11/11 requirements done; validation requires live pipeline run
> **Date:** 2026-03-22
> **Scope:** Close the gaps between Query Prime's implemented Kaizen layer (REQ-KQP-*) and the Prime Contractor pipeline's ability to invoke it, persist its outputs, and feed them into cross-run analysis
> **Parent:** [QUERY_PRIME_REQUIREMENTS.md](QUERY_PRIME_REQUIREMENTS.md), [KAIZEN_QUERY_PRIME_REQUIREMENTS.md](KAIZEN_QUERY_PRIME_REQUIREMENTS.md)
> **Motivation:** Run-101 (online-boutique, 40 Go features, score=0.98) demonstrated that the Anzen gate ran but: (a) only 1 of 40 files was gated, (b) `query_security` data was written to the project root but not the pipeline output, (c) the trend script found 0 runs with query data across 20 archived runs

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer A — Artifact Routing (REQ-QPA-1xx)](#3-layer-a--artifact-routing-req-qpa-1xx)
4. [Layer B — Anzen Gate Coverage (REQ-QPA-2xx)](#4-layer-b--anzen-gate-coverage-req-qpa-2xx)
5. [Layer C — Seed Enrichment (REQ-QPA-3xx)](#5-layer-c--seed-enrichment-req-qpa-3xx)
6. [Layer D — Trend Pipeline Compatibility (REQ-QPA-4xx)](#6-layer-d--trend-pipeline-compatibility-req-qpa-4xx)
7. [Traceability Matrix](#7-traceability-matrix)
8. [Verification Strategy](#8-verification-strategy)

---

## 1. Problem Statement

### 1.1 Evidence from Run-101

Run-101 (online-boutique-demo, 2026-03-22) generated 40 Go microservice features including:
- **Catalog Loader (AlloyDB + Local JSON)** — imports `alloydbconn`, `pgx/v5/pgxpool`, builds SQL queries
- **Checkout gRPC Server + PlaceOrder** — server handling money operations
- **Frontend HTTP Handlers** — 14 HTTP handler/template features

**Observed:**

| Artifact | Expected Location | Actual Location | Status |
|----------|-------------------|-----------------|--------|
| `security-gate-metrics.json` | pipeline output + `.startd8/` | project root only | **MISROUTED** |
| `query_security` in `kaizen-metrics.json` | pipeline output (postmortem copy) | project root only | **NOT PROPAGATED** |
| `query-security-metrics.json` | pipeline output | nowhere | **NEVER WRITTEN** |
| `anzen_gate` in postmortem features | per-feature in report | absent | **NOT POPULATED** |

**Anzen gate execution:** 1 file gated (catalog_loader.go), 39 skipped. The gate correctly detected PostgreSQL in the one file that imports `pgx` directly, but missed all other files because:
- Go gRPC servers use indirect database access (gRPC client calls, not direct SQL)
- Go templates, Dockerfiles, go.mod files have no database surface
- The `detect_database_type(source)` function only matches source-level keywords

### 1.2 Gaps

| ID | Gap | Impact |
|----|-----|--------|
| QPA-1 | `query_security` written to project root but postmortem writes a fresh `kaizen-metrics.json` to pipeline output without it | Cross-run trends see 0 query data |
| QPA-2 | `security-gate-metrics.json` written to project root, not pipeline output | Trend scripts can't find it |
| QPA-3 | `query-security-metrics.json` (REQ-KQP-100) never written as standalone file | Trend script `_load_runs()` can't locate it |
| QPA-4 | Only 1/40 files gated because `detect_database_type(source)` requires direct DB imports | Features that delegate to DB-bearing modules are invisible |
| QPA-5 | Seed tasks not tagged `security_sensitive` despite "AlloyDB" in feature description | Prompt-level P1 security injection missed |
| QPA-6 | Trend script `_load_runs()` uses `relative_path` key but kaizen-index uses `run_dir`/`metrics_path` | Script loads 0 runs from a 20-run index |

### 1.3 Constraints

- **No new LLM calls** — all fixes are deterministic wiring/routing
- **Backward compatible** — existing postmortem output unchanged; query_security is additive
- **No false positive inflation** — expanding gate coverage must not flag non-database files

---

## 2. Status Dashboard

| Req ID | Description | Status | Closes |
|--------|-------------|--------|--------|
| **Layer A — Artifact Routing** | | | |
| REQ-QPA-100 | Merge query_security into pipeline-output kaizen-metrics.json | **DONE** | QPA-1 |
| REQ-QPA-101 | Write security-gate-metrics.json to pipeline output directory | **DONE** | QPA-2 |
| REQ-QPA-102 | Write query-security-metrics.json standalone to pipeline output | **DONE** | QPA-3 |
| **Layer B — Anzen Gate Coverage** | | | |
| REQ-QPA-200 | Expand detect_database_type with Go import patterns | **DONE** | QPA-4 |
| REQ-QPA-201 | Propagate detected database type from seed to Anzen gate | **DONE** | QPA-4 |
| REQ-QPA-202 | Gate files from security_sensitive features even without DB keywords | **DONE** | QPA-4 |
| **Layer C — Seed Enrichment** | | | |
| REQ-QPA-300 | Auto-tag security_sensitive from feature description keywords | **DONE** | QPA-5 |
| REQ-QPA-301 | Auto-detect database type from feature description in seed builder | **DONE** | QPA-5 |
| **Layer D — Trend Pipeline Compatibility** | | | |
| REQ-QPA-400 | Fix _load_runs() to use kaizen-index actual field names | **DONE** | QPA-6 |
| REQ-QPA-401 | Validate trend pipeline reads query_security from kaizen-metrics.json | **DONE** | QPA-6 |

---

## 3. Layer A — Artifact Routing (REQ-QPA-1xx)

**Closes:** QPA-1, QPA-2, QPA-3

### REQ-QPA-100: Merge query_security into Pipeline Output kaizen-metrics.json

The postmortem evaluator writes `kaizen-metrics.json` to the pipeline output directory. The Anzen gate writes `query_security` data into the project-root `kaizen-metrics.json` via `update_query_security_metrics()`. These are two different files.

**The postmortem's pipeline-output copy SHALL include the `query_security` section.**

Implementation options (pick one):
1. Postmortem reads project-root `kaizen-metrics.json`, merges `query_security` into its output
2. Anzen gate writes directly to the pipeline output path (passed via `output_dir` param)
3. Post-postmortem merge step reads both and combines

**Acceptance criteria:**
- After a Prime Contractor run, `{pipeline-output}/plan-ingestion/kaizen-metrics.json` contains a `query_security` key when any files were gated
- The `query_security` section matches the schema from REQ-KQP-500

### REQ-QPA-101: Write security-gate-metrics.json to Pipeline Output

Currently `write_gate_metrics_report()` writes to a path derived from `self.project_root`. This SHALL additionally write to (or primarily write to) the pipeline output directory.

**Acceptance criteria:**
- `{pipeline-output}/plan-ingestion/security-gate-metrics.json` exists after a run where ≥1 file was gated
- Contents match the existing `security-gate-metrics.json` schema

### REQ-QPA-102: Write query-security-metrics.json Standalone

REQ-KQP-100 specifies a standalone `query-security-metrics.json` file. The Anzen gate builds the data (`qp_report` dict) and passes it to `update_query_security_metrics()`, but the standalone file is never written.

**The Anzen gate SHALL write `query-security-metrics.json` to the pipeline output directory.**

**Acceptance criteria:**
- `{pipeline-output}/plan-ingestion/query-security-metrics.json` exists after a gated run
- Schema matches REQ-KQP-100 (run_id, timestamp, by_database, by_tier, items)
- The trend script `_load_runs()` can locate and parse it

---

## 4. Layer B — Anzen Gate Coverage (REQ-QPA-2xx)

**Closes:** QPA-4

### REQ-QPA-200: Expand detect_database_type with Go Import Patterns

The current `detect_database_type()` matches keywords like "alloydb", "npgsql", "pgx" in source text. Go files that import database packages use full module paths:

```go
import (
    "database/sql"
    "cloud.google.com/go/alloydbconn"
    "github.com/jackc/pgx/v5/pgxpool"
    "cloud.google.com/go/spanner"
    "github.com/go-redis/redis/v9"
    "github.com/go-sql-driver/mysql"
)
```

The current patterns already catch `alloydb` and `pgx` as substrings. But Go standard library `database/sql` is not matched.

**`_DATABASE_PATTERNS` SHALL be extended with:**

| Pattern | Database | Rationale |
|---------|----------|-----------|
| `database/sql` | POSTGRESQL (default) | Go stdlib database interface |
| `pgxpool` | POSTGRESQL | pgx connection pool |
| `jackc/pgx` | POSTGRESQL | pgx driver module path |
| `go-redis` | REDIS | Go Redis client |
| `go-sql-driver/mysql` | MYSQL | Go MySQL driver |
| `mattn/go-sqlite3` | SQLITE | Go SQLite driver |
| `cloud.google.com/go/spanner` | SPANNER | Full Go module path (current "spanner" keyword catches this already) |

**Acceptance criteria:**
- `detect_database_type('import "database/sql"')` returns `DatabaseType.POSTGRESQL`
- `detect_database_type('import "github.com/jackc/pgx/v5"')` returns `DatabaseType.POSTGRESQL`
- `detect_database_type('import "github.com/go-redis/redis/v9"')` returns `DatabaseType.REDIS`

### REQ-QPA-201: Propagate Detected Database from Seed to Anzen Gate

When `enrich_security_fields()` detects a database type during plan ingestion and stores it in `gen_context["detected_database"]`, this information is available at generation time but **not** at Anzen gate time.

**The integration engine SHALL check `gen_context["detected_database"]` as a fallback when `detect_database_type(source)` returns None.**

**Acceptance criteria:**
- A file generated from a `security_sensitive` seed task with `detected_database: "postgresql"` is gated even if the generated source doesn't contain database keywords directly
- The Anzen gate entry records the database type from the seed metadata

### REQ-QPA-202: Gate Files from security_sensitive Features Regardless of DB Keywords

When a feature is tagged `security_sensitive: true`, ALL generated files from that feature SHALL be gated, not just the ones containing database keywords.

**Rationale:** A security-sensitive feature may produce utility functions, configuration files, or helper modules that don't directly contain SQL but are part of the database access surface.

**Acceptance criteria:**
- All generated files from a `security_sensitive` feature appear in `security-gate-metrics.json`
- Files without database keywords get a default `database: "unknown"` and run the full injection + credential + lifecycle pipeline
- Non-security-sensitive features continue to use `detect_database_type(source)` for filtering

---

## 5. Layer C — Seed Enrichment (REQ-QPA-3xx)

**Closes:** QPA-5

### REQ-QPA-300: Auto-Tag security_sensitive from Feature Description

The `SeedBuilder.derive_tasks()` method (or the seed enrichment pipeline) SHALL set `security_sensitive: true` when the feature description contains database-related keywords.

**Keywords triggering auto-tagging:**

| Category | Keywords |
|----------|----------|
| Database names | alloydb, postgresql, postgres, spanner, redis, mysql, sqlite, dynamodb, mongodb, cassandra, cockroachdb |
| Access patterns | database, query, sql, crud, connection pool, data store, catalog loader |
| Security surfaces | credential, secret, connection string, api key, auth token |

**Acceptance criteria:**
- "Catalog Loader (AlloyDB + Local JSON)" auto-tagged `security_sensitive: true`
- "Frontend Header Template" NOT auto-tagged (no database keywords)
- Keyword matching is case-insensitive
- Existing manual `security_sensitive` annotations take precedence (never overridden to false)

### REQ-QPA-301: Auto-Detect Database Type from Description in Seed Builder

When `security_sensitive` is auto-tagged, the `detected_database` field SHALL also be populated from the same keyword match.

**Acceptance criteria:**
- "Catalog Loader (AlloyDB + Local JSON)" gets `detected_database: "postgresql"` (alloydb → postgresql)
- "Redis Cache Layer" gets `detected_database: "redis"`
- Features with no specific database keyword but other security keywords get `detected_database: null`

---

## 6. Layer D — Trend Pipeline Compatibility (REQ-QPA-4xx)

**Closes:** QPA-6

### REQ-QPA-400: Fix _load_runs() Kaizen Index Field Mapping

The trend script `_load_runs()` reads `entry.get("relative_path", "")` but the actual kaizen-index entries use `run_dir` (absolute path) and `metrics_path` (absolute path).

**`_load_runs()` SHALL be updated to:**
1. Try `metrics_path` first (absolute — most reliable)
2. Fall back to `run_dir` / `"kaizen-metrics.json"`
3. Fall back to `relative_path` / `"kaizen-metrics.json"` for backward compatibility

**Acceptance criteria:**
- Given the online-boutique kaizen-index.json (20 runs with `run_dir`/`metrics_path` fields), `_load_runs()` returns ≥1 run with query_security data
- Backward compatible with indexes that use `relative_path`

### REQ-QPA-401: Validate Trend Pipeline End-to-End

After REQ-QPA-100 and REQ-QPA-400 are implemented:

**Acceptance criteria:**
- `run_query_prime_trends.py --output-dir {online-boutique-pipeline-output}` reports ≥1 run with query data
- The trend output includes `score_slope`, `fp_rate_slope`, and `latest_score`
- Re-running online-boutique with REQ-QPA-200+300 fixes produces ≥2 gated files per run

---

## 7. Traceability Matrix

| Gap | Requirements | Upstream Kaizen Req | Implementation Site |
|-----|-------------|-------------------|-------------------|
| QPA-1 | REQ-QPA-100 | REQ-KQP-500 | `integration_engine.py` + `prime_postmortem.py` |
| QPA-2 | REQ-QPA-101 | — | `integration_engine.py` (Anzen gate `write_gate_metrics_report`) |
| QPA-3 | REQ-QPA-102 | REQ-KQP-100 | `integration_engine.py` (Anzen gate) |
| QPA-4 | REQ-QPA-200, 201, 202 | REQ-QP-603 | `decomposer.py`, `integration_engine.py` |
| QPA-5 | REQ-QPA-300, 301 | REQ-QP-701 | `seeds/builder.py` or `security_prime/enrichment.py` |
| QPA-6 | REQ-QPA-400, 401 | REQ-KQP-400 | `scripts/run_query_prime_trends.py` |

---

## 8. Verification Strategy

### Unit Tests

| Test Area | Expected Tests |
|-----------|---------------|
| `detect_database_type` with Go imports (REQ-QPA-200) | 6 (one per new pattern) |
| Auto-tagging from description (REQ-QPA-300) | 4 (triggers, doesn't trigger, case insensitive, no override) |
| `_load_runs()` with real index format (REQ-QPA-400) | 3 (metrics_path, run_dir fallback, relative_path compat) |

### Integration Tests

| Test | Description |
|------|-------------|
| Run-101 replay | Re-run with fixes; verify ≥2 files gated, `query_security` in pipeline kaizen-metrics.json |
| Trend pipeline | After 2+ runs, verify `run_query_prime_trends.py` reports non-zero data |

### Acceptance Criteria Summary

1. After a Prime Contractor run with database features, `{pipeline-output}/kaizen-metrics.json` contains `query_security` key
2. `security-gate-metrics.json` exists in pipeline output directory
3. `query-security-metrics.json` exists in pipeline output directory
4. `detect_database_type()` matches Go stdlib `database/sql` and common Go DB drivers
5. Features with "AlloyDB" in description are auto-tagged `security_sensitive`
6. Trend script finds and reports query data from archived runs
