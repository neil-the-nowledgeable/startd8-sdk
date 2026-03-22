# Kaizen for Query Prime — Requirements

> **Version:** 1.1.0
> **Status:** IMPLEMENTED — 18/18 requirements done, all Kaizen components wired into engine runtime
> **Date:** 2026-03-21
> **Scope:** Systematic continuous improvement of Query Prime (secure query generation) through run-over-run analysis of security verification outcomes, false positive rates, model tier effectiveness, and credential handling compliance
> **Design Principle:** [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) + [ANZEN_DESIGN_PRINCIPLE.md](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md)
> **Parent:** [QUERY_PRIME_REQUIREMENTS.md](QUERY_PRIME_REQUIREMENTS.md) (generation pipeline — REQ-QP-100–1002)
> **Siblings:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) (code generation Kaizen), [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) (plan ingestion Kaizen), [KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md](../kaizen/KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md) (observability artifact Kaizen)
> **Implementation Home:** `startd8-sdk` (validators + metrics + postmortem) + `cap-dev-pipe` (trend aggregation + gate scripts)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Security Verification Metrics (REQ-KQP-1xx)](#3-layer-1--security-verification-metrics-req-kqp-1xx)
4. [Layer 2 — False Positive Tracking (REQ-KQP-2xx)](#4-layer-2--false-positive-tracking-req-kqp-2xx)
5. [Layer 3 — Query Quality Scoring (REQ-KQP-3xx)](#5-layer-3--query-quality-scoring-req-kqp-3xx)
6. [Layer 4 — Cross-Run Aggregation (REQ-KQP-4xx)](#6-layer-4--cross-run-aggregation-req-kqp-4xx)
7. [Layer 5 — Postmortem Integration (REQ-KQP-5xx)](#7-layer-5--postmortem-integration-req-kqp-5xx)
8. [Layer 6 — Feedback Loop (REQ-KQP-6xx)](#8-layer-6--feedback-loop-req-kqp-6xx)
9. [Existing Capabilities Leveraged](#9-existing-capabilities-leveraged)
10. [Traceability Matrix](#10-traceability-matrix)
11. [Verification Strategy](#11-verification-strategy)
12. [Cross-References](#12-cross-references)

---

## 1. Overview

### 1.1 Vision

Query Prime generates secure database query code through a DECOMPOSE→CLASSIFY→ROUTE→GENERATE→VERIFY loop (REQ-QP-100–603). The Kaizen layer ensures this loop **improves across runs** — each query generation run contributes to a cumulative understanding of which database/framework combinations produce injection-free code, which model tiers are cost-effective, and where false positives erode developer trust.

Without Kaizen, Query Prime is a stateless function: given the same inputs, it makes the same mistakes. With Kaizen, prior run outcomes shape model routing (REQ-QP-401), suppress known false positives (REQ-QP-702), and inject security warnings into prompts for patterns that previously failed (REQ-QP-701).

### 1.2 The Query Security Pipeline

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
│  DECOMPOSE   │───→│   CLASSIFY   │───→│    ROUTE     │───→│   GENERATE   │───→│   VERIFY (Security)  │
│              │    │              │    │              │    │              │    │                      │
│ Plan → query │    │ Signals →    │    │ Tier → model │    │ Parameterized│    │ Injection detection  │
│ work items   │    │ tier assign  │    │ selection    │    │ query code   │    │ Credential check     │
│              │    │              │    │              │    │              │    │ Lifecycle check      │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────────────┘
 Deterministic      Deterministic +      Kaizen-informed     LLM (T3/T2/T1)     Deterministic + LLM
                    Kaizen signals                                               (database-aware)
```

**Key Kaizen-bearing stages:**
- **CLASSIFY**: `prior_injection_failure` and `target_framework_familiarity` signals come from Kaizen history (REQ-QP-300)
- **ROUTE**: Effectiveness-based routing adjusts model tiers from Kaizen data after ≥10 runs (REQ-QP-401)
- **VERIFY**: False positive suppression uses Kaizen tracking to avoid flagging known-safe patterns (REQ-QP-702)

### 1.3 What We Measure (vs. Code Generation Kaizen)

| Dimension | Code Generation Kaizen | Query Prime Kaizen |
|-----------|----------------------|-------------------|
| Primary quality signal | AST validity + stub completeness | Parameterization correctness + injection freedom |
| False positive impact | Low (AST checks are reliable) | High (database-specific patterns cause false positives — QP-F2) |
| Model effectiveness | Success rate per tier | Per-database, per-framework effectiveness |
| Security dimension | Not a first-class metric | Primary quality gate — zero tolerance for injection |
| Credential handling | Not measured | First-class metric — zero tolerance for leakage |
| Cost efficiency | Cost per feature | Cost per query work item, by tier and database |

### 1.4 Gaps to Close

| Gap | Problem | Impact | Layer |
|-----|---------|--------|-------|
| KQP-1 | No structured verification metrics per run | Cannot quantify injection prevention rate or credential compliance | Layer 1 |
| KQP-2 | No false positive tracking or suppression | Developers disable validators after false positives (QP-F2) | Layer 2 |
| KQP-3 | No per-query quality scoring | Cannot compare query quality across databases or frameworks | Layer 3 |
| KQP-4 | No cross-run security trend | Cannot answer "is query security improving?" | Layer 4 |
| KQP-5 | Security outcomes not in postmortem | Security findings are siloed from the main Kaizen loop | Layer 5 |
| KQP-6 | No prompt feedback from prior security failures | Same injection patterns recur across runs | Layer 6 |

### 1.5 Success Criteria

1. Every Query Prime run produces a `query-security-metrics.json` with per-work-item verification results (KQP-1 closed)
2. False positives are tracked per database/framework pattern; known-safe patterns are auto-suppressed after 3 confirmations (KQP-2 closed)
3. Each query work item receives a composite security quality score (KQP-3 closed)
4. A trend script compares security metrics across N archived runs, broken down by database (KQP-4 closed)
5. Security metrics are included in `kaizen-metrics.json` and the postmortem summary (KQP-5 closed)
6. Prior-run injection failures inject P1 prompt hints into subsequent runs (KQP-6 closed)

### 1.6 Constraints

- **No new LLM calls** for Kaizen analysis — all quality checks are deterministic or use existing verification outputs
- **Zero tolerance for injection suppression** — false positive tracking SHALL NOT auto-suppress injection findings (only credential/lifecycle patterns)
- **Database-specific granularity** — metrics, scoring, and trends must be segmentable by database and client framework
- **Backward compatible** — existing Prime Contractor postmortem pipeline unchanged; Query Prime metrics are additive

---

## 2. Status Dashboard

| Req ID | Description | Impl Home | Status | Closes |
|--------|-------------|-----------|--------|--------|
| **Layer 1 — Security Verification Metrics** | | | | |
| REQ-KQP-100 | Per-run verification report | startd8-sdk | **DONE** (`kaizen_metrics.py:build_verification_report`) | KQP-1 |
| REQ-KQP-101 | Per-work-item verification breakdown | startd8-sdk | **DONE** (per-item details in report) | KQP-1 |
| REQ-KQP-102 | Verification pipeline timing | startd8-sdk | **DONE** (timing threaded from `verify_file` → report items) | KQP-1 |
| **Layer 2 — False Positive Tracking** | | | | |
| REQ-KQP-200 | False positive registry | startd8-sdk | **DONE** (`fp_registry.py` — wired into engine + verify_file) | KQP-2 |
| REQ-KQP-201 | Auto-suppression with threshold | startd8-sdk | **DONE** (`fp_registry.py` — wired into verify_file) | KQP-2 |
| REQ-KQP-202 | Suppression audit log | startd8-sdk | **DONE** (`verify_file` logs each suppression at WARNING) | KQP-2 |
| **Layer 3 — Query Quality Scoring** | | | | |
| REQ-KQP-300 | Per-query security quality score | startd8-sdk | **DONE** (`kaizen_metrics.py:compute_query_security_score`) | KQP-3 |
| REQ-KQP-301 | Per-database aggregate score | startd8-sdk | **DONE** (`by_database` in report + kaizen-metrics) | KQP-3 |
| REQ-KQP-302 | Model tier effectiveness score | startd8-sdk | **DONE** (`by_tier` in report) | KQP-3 |
| **Layer 4 — Cross-Run Aggregation** | | | | |
| REQ-KQP-400 | Cross-run security trend script | startd8-sdk + cap-dev-pipe | **DONE** (`run_query_prime_trends.py` + pipeline wiring) | KQP-4 |
| REQ-KQP-401 | Per-database trend breakdown | startd8-sdk | **DONE** (in trend script) | KQP-4 |
| REQ-KQP-402 | False positive rate trajectory | startd8-sdk | **DONE** (in trend script) — needs FP data to populate | KQP-4 |
| **Layer 5 — Postmortem Integration** | | | | |
| REQ-KQP-500 | Security metrics in kaizen-metrics.json | startd8-sdk | **DONE** (`update_query_security_metrics` wired into Anzen gate) | KQP-5 |
| REQ-KQP-501 | Per-feature security assessment | startd8-sdk | **DONE** (Anzen→semantic bridge in integration_engine) | KQP-5 |
| REQ-KQP-502 | Security section in postmortem summary | startd8-sdk | **DONE** (SECURITY_VIOLATION root cause + postmortem section) | KQP-5 |
| **Layer 6 — Feedback Loop** | | | | |
| REQ-KQP-600 | Injection-history prompt hints | startd8-sdk | **DONE** (`_apply_kaizen_hints` + `prior_security_findings` + escalation) | KQP-6 |
| REQ-KQP-601 | Framework effectiveness routing adjustment | startd8-sdk | **DONE** (`routing_overrides.py` — wired into engine classification) | KQP-6 |
| REQ-KQP-602 | Security-specific CAUSE_TO_SUGGESTION entries | startd8-sdk | **DONE** (8 entries in `prime_postmortem.py`) | KQP-6 |

---

## 3. Layer 1 — Security Verification Metrics (REQ-KQP-1xx)

**Closes:** Gap KQP-1 (no structured verification metrics)

Today, Query Prime's VERIFY stage (REQ-QP-600–603) produces pass/fail per work item, but there is no aggregated, persistent, queryable metric report. The verification pipeline runs four deterministic checks plus an optional LLM review, but outcomes are logged and discarded.

### REQ-KQP-100: Per-Run Verification Report

After Query Prime completes (or on any verification failure), the engine SHALL write a `query-security-metrics.json` to the output directory:

```json
{
  "schema_version": "1.0.0",
  "run_id": "run-092-20260320T1803",
  "run_timestamp": "2026-03-20T18:18:08Z",
  "work_items_total": 12,
  "work_items_passed": 10,
  "work_items_failed": 2,
  "verification_summary": {
    "injection_found": 1,
    "injection_escaped": 0,
    "credential_leak_found": 1,
    "credential_leak_escaped": 0,
    "lifecycle_warnings": 3,
    "false_positives_suppressed": 2,
    "parameterization_rate": 0.917
  },
  "by_database": {
    "postgresql": {
      "work_items": 6,
      "passed": 5,
      "failed": 1,
      "injection_found": 1,
      "parameterization_rate": 0.833
    },
    "spanner": {
      "work_items": 4,
      "passed": 4,
      "failed": 0,
      "false_positives_suppressed": 2
    },
    "redis": {
      "work_items": 2,
      "passed": 1,
      "failed": 1,
      "credential_leak_found": 1
    }
  },
  "by_tier": {
    "TRIVIAL": { "count": 3, "t3_sufficient": 3, "escalated": 0 },
    "SIMPLE": { "count": 5, "t3_sufficient": 4, "escalated": 1 },
    "MODERATE": { "count": 3, "t3_sufficient": 0, "escalated": 0 },
    "COMPLEX": { "count": 1, "t3_sufficient": 0, "escalated": 0 }
  },
  "cost": {
    "total_usd": 0.28,
    "by_tier": {
      "TRIVIAL": 0.006,
      "SIMPLE": 0.04,
      "MODERATE": 0.15,
      "COMPLEX": 0.084
    }
  }
}
```

**Leverages:** REQ-QP-700 defines the metric schema; this requirement specifies persistence and structure.

**Advisory persistence:** Wraps I/O in `try/except OSError` with `logger.warning` — never fails a successful run due to a report write error.

### REQ-KQP-101: Per-Work-Item Verification Breakdown

Each work item in the verification report SHALL include a detailed breakdown:

```json
{
  "work_item_id": "QWI-003",
  "database": "postgresql",
  "framework": "npgsql",
  "operation_type": "upsert",
  "tier": "MODERATE",
  "model_used": "claude-sonnet-4-20250514",
  "escalated": false,
  "verification": {
    "injection_check": "PASS",
    "credential_check": "PASS",
    "lifecycle_check": "WARN",
    "llm_review": "PASS",
    "overall": "PASS"
  },
  "lifecycle_warnings": [
    "DataSource created in AddItemAsync — should be in constructor"
  ],
  "cost_usd": 0.052,
  "generation_time_ms": 3400,
  "verification_time_ms": 45
}
```

**Leverages:** `SecurityVerificationResult` from REQ-QP-603; `QueryResult` from REQ-QP-200.

### REQ-KQP-102: Verification Pipeline Timing

Each verification step SHALL record timing for performance analysis:

| Step | Timing Source | What It Reveals |
|------|--------------|-----------------|
| Injection detection | `time.monotonic()` bookends | Regex/AST check performance per database |
| Credential check | `time.monotonic()` bookends | Variable tracking analysis cost |
| Lifecycle check | `time.monotonic()` bookends | Scope analysis cost |
| LLM review (T3) | `token_usage.time_ms` | Model latency for security review |

**Threshold alert:** If total verification time exceeds 500ms per work item for deterministic checks, log a warning — pattern module complexity may need optimization.

---

## 4. Layer 2 — False Positive Tracking (REQ-KQP-2xx)

**Closes:** Gap KQP-2 (no false positive tracking)

The Spanner false positive (QP-F2) demonstrated that validators that flag safe code as unsafe erode developer trust faster than they catch real issues. False positive tracking is the mechanism to maintain validator credibility.

### REQ-KQP-200: False Positive Registry

A persistent registry SHALL track confirmed false positives:

```json
{
  "schema_version": "1.0.0",
  "entries": [
    {
      "pattern_hash": "sha256:a1b2c3...",
      "database": "spanner",
      "framework": "spanner_client",
      "finding_type": "sql_injection_risk",
      "pattern_description": "SpannerParameterCollection with @param binding",
      "confirmation_count": 3,
      "first_seen": "2026-03-15T12:00:00Z",
      "last_confirmed": "2026-03-20T18:18:08Z",
      "suppressed": true,
      "suppressed_at": "2026-03-20T18:18:08Z"
    }
  ]
}
```

**Location:** `{project_root}/.startd8/query-prime-false-positives.json`

**Leverages:** REQ-QP-702 defines the tracking requirements; this requirement specifies the persistence format.

### REQ-KQP-201: Auto-Suppression with Threshold

After 3 confirmed false positives for the same `(database, framework, pattern_hash, finding_type)` tuple, the pattern SHALL be auto-suppressed:

**Acceptance criteria:**
- Suppressed patterns produce WARNING logs instead of errors
- Suppression applies to credential and lifecycle checks ONLY — **never** to injection checks
- Suppressed patterns are included in `query-security-metrics.json` as `false_positives_suppressed`
- The registry records the suppression timestamp and reason
- A `--no-suppress` flag disables all auto-suppression for audit runs

### REQ-KQP-202: Suppression Audit Log

Every suppression event SHALL be logged with context for forensic review:

```
WARNING [startd8.query_prime.verifier] Suppressed known false positive:
  database=spanner, framework=spanner_client,
  finding=sql_injection_risk, pattern=SpannerParameterCollection,
  confirmations=3, first_seen=2026-03-15
```

The audit log enables periodic review of suppressed patterns — a suppressed pattern that later proves to be a true positive (e.g., after a framework update changes parameter binding behavior) must be un-suppressed.

---

## 5. Layer 3 — Query Quality Scoring (REQ-KQP-3xx)

**Closes:** Gap KQP-3 (no per-query quality scoring)

Per-query composite scores enable comparison across databases, frameworks, and model tiers. Equivalent to `compute_disk_quality_score()` in code generation.

### REQ-KQP-300: Per-Query Security Quality Score

```
query_security_score = (parameterization    x 0.35)
                     + (credential_safety   x 0.25)
                     + (lifecycle_compliance x 0.15)
                     + (verification_pass    x 0.15)
                     + (tier_efficiency      x 0.10)
```

| Component | Score Range | How Computed |
|-----------|-----------|--------------|
| `parameterization` | 0.0 or 1.0 | All external inputs use parameterized queries. Any injection finding → 0.0 |
| `credential_safety` | 0.0 or 1.0 | No credential leakage detected. Any leak → 0.0 |
| `lifecycle_compliance` | 0.0 – 1.0 | `1.0 - (lifecycle_warnings / lifecycle_checks)`. Fraction of lifecycle checks passed |
| `verification_pass` | 0.0 or 1.0 | Overall verification passed (including LLM review if applicable) |
| `tier_efficiency` | 0.0 – 1.0 | `1.0` if generated by expected tier; `0.5` if required escalation; `0.0` if max escalation and still failed |

**Short-circuit:** Injection finding → overall score 0.0 (parameterization weight dominates). Credential leak → capped at 0.25 maximum.

### REQ-KQP-301: Per-Database Aggregate Score

For each database in the run, compute:

| Metric | How | What It Reveals |
|--------|-----|-----------------|
| `avg_query_score` | Mean of per-query scores for this database | Overall database-specific quality |
| `injection_free_rate` | Queries without injection / total queries | Security posture per database |
| `false_positive_rate` | Suppressed findings / total findings | Validator calibration per database |
| `t3_sufficiency_rate` | T3-only queries / total queries | Model cost efficiency per database |

### REQ-KQP-302: Model Tier Effectiveness Score

Per-tier aggregate across all databases:

| Metric | How | What It Reveals |
|--------|-----|-----------------|
| `first_pass_rate` | Queries passing verification on first generation / total | Tier's reliability |
| `avg_cost` | Mean cost per work item | Tier's cost profile |
| `escalation_rate` | Queries requiring tier escalation / total | Tier's sufficiency |
| `security_score` | Mean `query_security_score` for queries at this tier | Quality at each cost point |

**Threshold alert:** If T3 `first_pass_rate` drops below 0.6 for any database, log a warning — auto-escalation to T2 is warranted (REQ-QP-401).

---

## 6. Layer 4 — Cross-Run Aggregation (REQ-KQP-4xx)

**Closes:** Gap KQP-4 (no cross-run security trend)

### REQ-KQP-400: Cross-Run Security Trend Script

A script SHALL read `query-security-metrics.json` from multiple archived runs and produce a trend summary:

```
Query Prime Security Trends (last 5 runs)
──────────────────────────────────────────
                      run-088  run-089  run-090  run-091  run-092
Parameterization rate 0.83     0.92     0.92     1.00     1.00   ↑
Injection found       2        1        1        0        0      ↓
False positive rate   0.25     0.20     0.10     0.05     0.03   ↓
T3 sufficiency        0.50     0.55     0.60     0.65     0.70   ↑
Cost per query        $0.08    $0.06    $0.05    $0.04    $0.04  ↓
Credential leaks      1        0        0        0        0      ↓
```

**Leverages:** Same `_linear_slope()` function used by code generation Kaizen trends (REQ-KZ-400). Reuses the `kaizen-index.json` run archive.

### REQ-KQP-401: Per-Database Trend Breakdown

The trend script SHALL support per-database drill-down:

```
PostgreSQL (Npgsql) — 5 runs
  Parameterization rate: 0.80 → 1.00  (slope: +0.05/run)
  First-pass rate:       0.60 → 0.80  (slope: +0.05/run)

Spanner — 5 runs
  False positive rate:   0.40 → 0.03  (slope: -0.09/run)  ← suppression working
  Parameterization rate: 1.00 → 1.00  (stable)
```

### REQ-KQP-402: False Positive Rate Trajectory

Track false positive rate over time to verify that:
1. Auto-suppression reduces noise without masking real issues
2. New database pattern modules reduce false positive rates
3. No suppressed pattern has reverted to a true positive

**Threshold alert:** If false positive rate increases by >10% between runs, log a warning — may indicate a framework update that changed parameter binding behavior.

---

## 7. Layer 5 — Postmortem Integration (REQ-KQP-5xx)

**Closes:** Gap KQP-5 (security outcomes not in postmortem)

### REQ-KQP-500: Security Metrics in kaizen-metrics.json

The existing `kaizen-metrics.json` MUST be extended with Query Prime security metrics:

```json
{
  "query_security": {
    "work_items_evaluated": 12,
    "parameterization_rate": 0.917,
    "injection_found_pre_export": 1,
    "injection_escaped": 0,
    "credential_leak_prevented": 1,
    "false_positive_count": 2,
    "false_positives_suppressed": 2,
    "t3_sufficiency_rate": 0.667,
    "avg_query_security_score": 0.88,
    "cost_per_query_usd": 0.023,
    "by_database": {
      "postgresql": { "score": 0.85, "injection_free": true },
      "spanner": { "score": 0.95, "injection_free": true },
      "redis": { "score": 0.75, "credential_leak": true }
    }
  }
}
```

**Leverages:** Existing `kaizen-metrics.json` schema with additive `query_security` key.

### REQ-KQP-501: Per-Feature Security Assessment

The postmortem evaluator MUST produce a per-feature security assessment for features tagged `security_sensitive`:

```json
{
  "feature_id": "PI-005",
  "feature_name": "AlloyDB Cart Store",
  "security_sensitive": true,
  "query_work_items": 4,
  "parameterization_compliant": 3,
  "credential_compliant": 4,
  "lifecycle_compliant": 2,
  "security_score": 0.82,
  "findings": [
    {
      "work_item": "QWI-003",
      "check": "injection_detection",
      "severity": "error",
      "message": "String interpolation in DELETE query — use NpgsqlParameter"
    }
  ]
}
```

**Leverages:** Existing `PrimePostMortemEvaluator` per-feature structure; security assessment is an additional section.

### REQ-KQP-502: Security Section in Postmortem Summary

The existing `prime-postmortem-summary.md` MUST include a "Query Security" section when Query Prime was active:

```markdown
## Query Security

- Work items evaluated: 12
- Parameterization rate: 91.7%
- Injections caught: 1 (0 escaped)
- Credential leaks caught: 1
- False positives suppressed: 2
- T3 sufficiency: 66.7%
- Average security score: 0.88

### Per-Database Breakdown
| Database | Score | Injection-Free | Notes |
|----------|-------|----------------|-------|
| PostgreSQL | 0.85 | Yes | 1 lifecycle warning |
| Spanner | 0.95 | Yes | 2 FP suppressed |
| Redis | 0.75 | Yes | 1 credential leak |
```

---

## 8. Layer 6 — Feedback Loop (REQ-KQP-6xx)

**Closes:** Gap KQP-6 (no prompt feedback from security failures)

### REQ-KQP-600: Injection-History Prompt Hints

When a prior run produced injection findings for a specific `(database, framework)` combination, subsequent runs SHALL inject Kaizen hints into the generation prompt:

**Hint format:**
```
SECURITY WARNING (Kaizen): Prior run {run_id} produced SQL injection in
{framework} queries targeting {database}. Use {safe_pattern} for ALL
external inputs. Specifically: {parameterization_example}
```

**Acceptance criteria:**
- Hints are P1 priority in the prompt budget (see `implementation_engine/budget.py`)
- Maximum 3 security Kaizen hints per generation prompt
- Hints reference the specific safe pattern from the database's pattern module
- Hints persist until 3 consecutive clean runs for the same `(database, framework)` combination
- Injection hints are **never** auto-removed by the suppression system (REQ-KQP-201)

**Leverages:** REQ-QP-701 defines the hint injection; REQ-KZ-500 (code generation Kaizen) provides the P1 prompt budget pattern.

### REQ-KQP-601: Framework Effectiveness Routing Adjustment

When cross-run analysis shows T3 insufficiency for a specific framework, routing SHALL auto-adjust:

**Acceptance criteria:**
- After ≥10 runs: if T3 `first_pass_rate` < 0.6 for `(database, framework)`, auto-escalate SIMPLE→T2
- After ≥10 runs: if T3 `first_pass_rate` > 0.8 for `(database, framework)`, allow SIMPLE→T3 (restore default)
- Routing adjustments are logged with the data that triggered them
- Adjustments are written to `{project_root}/.startd8/query-prime-routing-overrides.json`
- Overrides can be manually set or cleared via `--reset-routing` flag

**Leverages:** REQ-QP-401 (effectiveness-based routing); REQ-KQP-302 (tier effectiveness scoring).

### REQ-KQP-602: Security-Specific CAUSE_TO_SUGGESTION Entries

The following root cause codes MUST be added to `CAUSE_TO_SUGGESTION` in `prime_postmortem.py`:

| Root Cause Code | Phase | Hint |
|-----------------|-------|------|
| `query_injection_interpolation` | query_gen | "Query for '{database}' uses string interpolation — use {safe_pattern} parameterization" |
| `query_injection_concatenation` | query_gen | "Query for '{database}' uses string concatenation in SQL — use {safe_pattern} parameterization" |
| `query_credential_logged` | query_gen | "Connection string or credential logged via {log_call} — redact sensitive values before logging" |
| `query_credential_exposed` | query_gen | "Secret retrieved from {source} is not isolated in a dedicated method — extract to separate method" |
| `query_lifecycle_per_request` | query_gen | "DataSource/ConnectionPool created per-request in {method} — move to constructor or singleton" |
| `query_lifecycle_no_dispose` | query_gen | "Connection not disposed — use 'using'/'with'/'defer'/'try-finally' for resource cleanup" |
| `query_false_positive_spanner` | query_verify | "Spanner @param binding flagged as injection — verify pattern module handles SpannerParameterCollection" |
| `query_t3_insufficient` | query_route | "T3 model failed verification for {framework} — consider auto-escalating SIMPLE→T2 for this framework" |

**Leverages:** Existing `CAUSE_TO_SUGGESTION` dict in `prime_postmortem.py` (25 existing mappings). Security entries follow the same `(root_cause_code, phase, hint_template)` structure.

---

## 9. Existing Capabilities Leveraged

| Capability | Source | Kaizen Use |
|-----------|--------|------------|
| `CAUSE_TO_SUGGESTION` | `prime_postmortem.py` | Foundation for REQ-KQP-602 (security root cause hints) |
| `generate_kaizen_suggestions()` | `prime_postmortem.py` | Injects REQ-KQP-600 hints into subsequent run prompts |
| `kaizen-metrics.json` schema | `prime_postmortem.py` | Extended with `query_security` section (REQ-KQP-500) |
| `kaizen-index.json` run archive | `batch_postmortem.py` | Run archive for REQ-KQP-400 trend analysis |
| `_linear_slope()` | `batch_postmortem.py` | Trend computation for REQ-KQP-400 |
| `enforce_prompt_budget()` P1 sections | `implementation_engine/budget.py` | Prompt budget for security hints (REQ-KQP-600) |
| `csharp_semantic_checks.py` SQL detection | `validators/csharp_semantic_checks.py` | `_SQL_INTERPOLATION_RE`, `_SQL_CONCAT_RE` patterns reusable in Query Prime injection detection |
| `java_semantic_checks.py` SQL detection | `validators/java_semantic_checks.py` | `_SQL_CONCAT_RE`, `_SQL_FORMAT_RE` patterns reusable |
| Database pattern modules | `query_prime/patterns/` | Per-database safe/unsafe pattern definitions (REQ-QP-600) |

---

## 10. Traceability Matrix

| Gap | Requirements | Kaizen Principle Rule | Query Prime Parent Req |
|-----|-------------|----------------------|----------------------|
| KQP-1: No verification metrics | REQ-KQP-100, 101, 102 | Rule 1 (preserve all outputs) | REQ-QP-700 |
| KQP-2: No false positive tracking | REQ-KQP-200, 201, 202 | Rule 3 (measure) + Rule 5 (feed forward) | REQ-QP-702 |
| KQP-3: No query quality scoring | REQ-KQP-300, 301, 302 | Rule 3 (measure before and after) | REQ-QP-700 |
| KQP-4: No cross-run trend | REQ-KQP-400, 401, 402 | Rule 3 (measure) + Rule 6 (automate) | REQ-QP-401 |
| KQP-5: Security not in postmortem | REQ-KQP-500, 501, 502 | Rule 1 (preserve) + Rule 4 (attributable) | REQ-QP-804 |
| KQP-6: No prompt feedback | REQ-KQP-600, 601, 602 | Rule 5 (feed forward) | REQ-QP-701 |

---

## 11. Verification Strategy

### Unit Tests

| Test Area | Expected Tests | Priority |
|-----------|---------------|----------|
| Verification report schema (REQ-KQP-100) | 5 (schema fields, by_database, by_tier, cost) | P0 |
| Per-work-item breakdown (REQ-KQP-101) | 5 (each verification step, tier_efficiency) | P0 |
| False positive registry (REQ-KQP-200) | 5 (add, confirm, threshold, suppression, never-inject) | P0 |
| Quality scoring (REQ-KQP-300) | 8 (component isolation, short-circuit, composite) | P1 |
| Per-database aggregation (REQ-KQP-301) | 4 (multi-database, single-database, empty) | P1 |
| CAUSE_TO_SUGGESTION entries (REQ-KQP-602) | 8 (one per root cause code) | P1 |
| Prompt hint injection (REQ-KQP-600) | 4 (hint format, max 3, persistence, never-suppress) | P1 |

### Integration Tests

| Test | Description |
|------|-------------|
| Run-079 regression | Replay C# AlloyDB injection scenario; verify `injection_found: 1`, score < 0.5, hint injected in next run |
| Run-079 Spanner FP | Replay Spanner false positive; verify FP tracked, suppressed after 3 confirmations, not applied to injection |
| Cross-run trend | 3 archived runs with improving security metrics; verify trend slope is positive |
| Prompt feedback loop | Run 1 produces injection → Run 2 receives P1 hint → Run 2 produces clean query |

### Acceptance Criteria

1. Run-079's AlloyDB `$"DELETE FROM ... '{userId}'"` scores 0.0 (parameterization = 0.0)
2. Run-079's Spanner `SpannerParameterCollection` does NOT produce an injection finding (false positive resolved)
3. `kaizen-metrics.json` includes `query_security` section with correct per-database breakdown
4. After 3 runs with the same Spanner false positive, it is auto-suppressed with audit log
5. Injection-bearing run injects P1 hint into next run's generation prompt
6. T3 sufficiency rate drops below 0.6 for PostgreSQL → auto-escalation to T2 is recorded

---

## 12. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) | Governing design principle (don't discard lessons across runs) |
| [ANZEN_DESIGN_PRINCIPLE.md](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md) | Security correctness by design principle |
| [QUERY_PRIME_REQUIREMENTS.md](QUERY_PRIME_REQUIREMENTS.md) | Parent: generation pipeline that produces the outputs Kaizen measures |
| [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) | Sibling: code generation Kaizen (same 6-layer structure, different subject) |
| [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) | Sibling: plan ingestion Kaizen |
| [KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md](../kaizen/KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md) | Sibling: observability artifact Kaizen |
| `csharp_semantic_checks.py`, `java_semantic_checks.py` | SQL injection detection regex patterns reusable in Query Prime verifier |
| `prime_postmortem.py` | Integration target for Layers 5–6 (CAUSE_TO_SUGGESTION, kaizen-metrics.json) |
| SDK Lessons: Leg 13 #60 | str+Enum case mismatch — applicable to database enum values |
| C# Run-079 Findings | QP-F1 through QP-F4 — the incidents that motivated Query Prime |
