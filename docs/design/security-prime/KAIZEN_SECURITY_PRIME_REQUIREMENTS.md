# Kaizen for Security Prime — Requirements

> **Version:** 0.1.0
> **Status:** DRAFT
> **Date:** 2026-03-21
> **Scope:** Systematic continuous improvement of Security Prime (Anzen gate orchestration) through run-over-run analysis of gate verdicts, scoring calibration, allowlist effectiveness, prompt injection impact, and OWASP coverage progression
> **Design Principle:** [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) + [ANZEN_DESIGN_PRINCIPLE.md](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md)
> **Parent:** [SECURITY_PRIME_REQUIREMENTS.md](SECURITY_PRIME_REQUIREMENTS.md) (orchestration layer — REQ-SP-100–610)
> **Siblings:** [KAIZEN_QUERY_PRIME_REQUIREMENTS.md](../query-prime/KAIZEN_QUERY_PRIME_REQUIREMENTS.md) (detection-layer Kaizen), [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) (code generation Kaizen)
> **Implementation Home:** `startd8-sdk` (scoring + metrics + OTel + allowlist + contract) + `cap-dev-pipe` (trend aggregation + gate scripts)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Gate Verdict Metrics (REQ-KSP-1xx)](#3-layer-1--gate-verdict-metrics-req-ksp-1xx)
4. [Layer 2 — Scoring Calibration (REQ-KSP-2xx)](#4-layer-2--scoring-calibration-req-ksp-2xx)
5. [Layer 3 — Allowlist Effectiveness (REQ-KSP-3xx)](#5-layer-3--allowlist-effectiveness-req-ksp-3xx)
6. [Layer 4 — Cross-Run Aggregation (REQ-KSP-4xx)](#6-layer-4--cross-run-aggregation-req-ksp-4xx)
7. [Layer 5 — Prompt Injection Effectiveness (REQ-KSP-5xx)](#7-layer-5--prompt-injection-effectiveness-req-ksp-5xx)
8. [Layer 6 — OWASP Coverage Progression (REQ-KSP-6xx)](#8-layer-6--owasp-coverage-progression-req-ksp-6xx)
9. [Existing Capabilities Leveraged](#9-existing-capabilities-leveraged)
10. [Traceability Matrix](#10-traceability-matrix)
11. [Verification Strategy](#11-verification-strategy)
12. [Cross-References](#12-cross-references)

---

## 1. Overview

### 1.1 Vision

Security Prime orchestrates the Anzen gate — wiring `query_prime/security/verify_file()` into the generation pipeline at three intercept points (context assembly, prompt injection, gate verification). The Kaizen layer ensures this orchestration **improves across runs**: each run contributes to understanding which prompt injections prevent vulnerabilities, whether the scoring formula correctly separates safe from unsafe code, and where the OWASP coverage matrix has gaps that matter.

Without Kaizen, Security Prime is a static gate: same prompts, same thresholds, same coverage. With Kaizen, prior gate verdicts shape scoring thresholds (REQ-KSP-200), allowlist coverage tracks trust accurately (REQ-KSP-300), and P0/P1 prompt effectiveness is measurable (REQ-KSP-500).

### 1.2 Security Prime vs. Query Prime Kaizen

| Concern | Query Prime Kaizen (REQ-KQP-*) | Security Prime Kaizen (REQ-KSP-*) |
|---------|-------------------------------|-----------------------------------|
| **Scope** | Detection layer — per-check accuracy | Orchestration layer — end-to-end gate effectiveness |
| **Primary signal** | Finding accuracy (FP/FN per check type) | Gate verdict correctness (files correctly accepted/rejected) |
| **Scoring** | Per-query component score | Per-file severity-weighted score + quality gate integration |
| **Allowlist** | Auto-accumulated FP registry (JSON) | Operator-declared allowlist (YAML) |
| **Prompt impact** | Not measured | P0/P1 prompt injection → vulnerability prevention rate |
| **Coverage** | Per-database, per-framework | OWASP Top 10 category coverage |
| **Escalation** | Tier routing (T3→T2→T1) | Kaizen hint escalation (guidance → requirement → critical) |

### 1.3 The Orchestration Pipeline

```
INTERCEPT 1: Context Assembly       INTERCEPT 2: Prompt          INTERCEPT 3: Gate
┌─────────────────────────┐    ┌────────────────────────┐    ┌─────────────────────────┐
│ detect_database_type()  │    │ P0: MUST parameterize  │    │ verify_file() call      │
│ derive_security_contract│    │ P1: safe pattern refs  │    │ SecurityScoreResult      │
│ enrich_gen_context()    │    │ Kaizen escalation hint │    │ OTel span + metrics      │
│ security_sensitive flag │    │ Reference deviation    │    │ Allowlist check          │
└────────┬────────────────┘    └───────────┬────────────┘    └────────────┬────────────┘
         │                                 │                              │
         ▼                                 ▼                              ▼
    KAIZEN measures:                  KAIZEN measures:              KAIZEN measures:
    Contract derivation success       Prompt → clean code rate      Verdict accuracy
    Enrichment coverage               P0 vs P1 impact              Score distribution
                                                                    Allowlist hit rate
```

### 1.4 Gaps to Close

| Gap | Problem | Impact | Layer |
|-----|---------|--------|-------|
| KSP-1 | No persistent gate verdict history | Cannot answer "what % of files pass the Anzen gate?" | Layer 1 |
| KSP-2 | Scoring thresholds are static | `0.70` threshold may be too lenient or too strict for specific projects | Layer 2 |
| KSP-3 | No allowlist effectiveness tracking | No data on whether allowlist entries are still needed or if they mask real issues | Layer 3 |
| KSP-4 | No cross-run security posture trend | Cannot answer "is the project getting more secure across runs?" | Layer 4 |
| KSP-5 | No P0/P1 prompt effectiveness measurement | Cannot determine if security prompt injection actually reduces vulnerabilities | Layer 5 |
| KSP-6 | OWASP coverage is static mapping | No tracking of whether coverage is improving or which gaps are most impactful | Layer 6 |

### 1.5 Success Criteria

1. Every Prime Contractor run with Security Prime active produces a `security-gate-metrics.json` with per-file gate verdicts and aggregate posture (KSP-1 closed)
2. Scoring calibration compares threshold-based verdicts against actual security outcomes, enabling threshold tuning (KSP-2 closed)
3. Each allowlist entry tracks hit count, last hit date, and whether the underlying pattern still triggers without it (KSP-3 closed)
4. A trend script compares security posture across N archived runs, broken down by verdict type and database (KSP-4 closed)
5. P0/P1 prompt injection effectiveness is measurable: runs with injection vs. hypothetical baseline (KSP-5 closed)
6. OWASP coverage progression is tracked — new checks widen coverage; Kaizen reports remaining gaps (KSP-6 closed)

### 1.6 Constraints

- **No new LLM calls** for Kaizen analysis — all quality checks use existing OTel spans, gate results, and deterministic analysis
- **Additive to kaizen-metrics.json** — Security Prime writes a `security_gate` key alongside existing `security` (from kaizen.py) and `query_security` (from kaizen_metrics.py) keys
- **Allowlist immutability** — Kaizen SHALL NOT auto-modify `security_allowlist.yaml`; it only reports effectiveness. Operators make allowlist changes.
- **Backward compatible** — existing `security_prime/` APIs and OTel instrumentation unchanged; metrics are additive
- **Score threshold changes require explicit opt-in** — auto-adjustment is suggested, not applied

---

## 2. Status Dashboard

| Req ID | Description | Impl Home | Status | Closes |
|--------|-------------|-----------|--------|--------|
| **Layer 1 — Gate Verdict Metrics** | | | | |
| REQ-KSP-100 | Per-run gate verdict report | startd8-sdk | PLANNED | KSP-1 |
| REQ-KSP-101 | Per-file gate verdict breakdown | startd8-sdk | PLANNED | KSP-1 |
| REQ-KSP-102 | Gate timing instrumentation | startd8-sdk | PLANNED | KSP-1 |
| REQ-KSP-103 | Verdict distribution summary | startd8-sdk | PLANNED | KSP-1 |
| **Layer 2 — Scoring Calibration** | | | | |
| REQ-KSP-200 | Score distribution analysis | startd8-sdk | PLANNED | KSP-2 |
| REQ-KSP-201 | Threshold sensitivity report | startd8-sdk | PLANNED | KSP-2 |
| REQ-KSP-202 | Score component contribution analysis | startd8-sdk | PLANNED | KSP-2 |
| **Layer 3 — Allowlist Effectiveness** | | | | |
| REQ-KSP-300 | Allowlist hit tracking | startd8-sdk | PLANNED | KSP-3 |
| REQ-KSP-301 | Stale entry detection | startd8-sdk | PLANNED | KSP-3 |
| REQ-KSP-302 | Allowlist audit report | startd8-sdk | PLANNED | KSP-3 |
| **Layer 4 — Cross-Run Aggregation** | | | | |
| REQ-KSP-400 | Cross-run security posture trend | startd8-sdk | PLANNED | KSP-4 |
| REQ-KSP-401 | Gate pass rate trajectory | startd8-sdk | PLANNED | KSP-4 |
| REQ-KSP-402 | Score distribution evolution | startd8-sdk | PLANNED | KSP-4 |
| **Layer 5 — Prompt Injection Effectiveness** | | | | |
| REQ-KSP-500 | P0 constraint impact measurement | startd8-sdk | PLANNED | KSP-5 |
| REQ-KSP-501 | P1 guidance impact measurement | startd8-sdk | PLANNED | KSP-5 |
| REQ-KSP-502 | Kaizen hint escalation effectiveness | startd8-sdk | PLANNED | KSP-5 |
| **Layer 6 — OWASP Coverage Progression** | | | | |
| REQ-KSP-600 | OWASP coverage tracking per run | startd8-sdk | PLANNED | KSP-6 |
| REQ-KSP-601 | Coverage gap impact ranking | startd8-sdk | PLANNED | KSP-6 |
| REQ-KSP-602 | Coverage progression trend | startd8-sdk | PLANNED | KSP-6 |

---

## 3. Layer 1 — Gate Verdict Metrics (REQ-KSP-1xx)

**Closes:** Gap KSP-1 (no persistent gate verdict history)

Today, `security_prime/otel.py:record_gate_result()` emits OTel spans and metrics for each gate execution, but there is no structured JSON report that aggregates these results for Kaizen consumption. The Loki/Grafana pipeline provides real-time visibility; this layer provides persistent, queryable run-level metrics.

### REQ-KSP-100: Per-Run Gate Verdict Report

After the Anzen gate completes for all files in a run, a `security-gate-metrics.json` SHALL be written to the output directory:

```json
{
  "schema_version": "1.0.0",
  "run_id": "run-095-20260321T1400",
  "run_timestamp": "2026-03-21T14:15:30Z",
  "files_total": 14,
  "files_gated": 12,
  "files_skipped": 2,
  "verdicts": {
    "pass": 10,
    "warn": 1,
    "fail": 1
  },
  "aggregate_score": 0.0,
  "mean_score": 0.87,
  "gate_pass_rate": 0.917,
  "databases_seen": ["postgresql", "spanner"],
  "languages_seen": ["csharp"],
  "total_findings": 5,
  "findings_by_type": {
    "injection": 1,
    "credential_leakage": 0,
    "lifecycle": 3,
    "health_check_exposure": 1
  },
  "allowlist_hits": 2,
  "p0_constraint_injected": true,
  "p1_guidance_injected": true,
  "kaizen_hint_level": "requirement"
}
```

**Leverages:** `security_prime/otel.py:record_gate_result()` already collects per-file data; this aggregates into a persistent report. `security_prime/scorer.py:compute_aggregate_score()` provides the weakest-link aggregate.

**Advisory persistence:** Wraps I/O in `try/except OSError` — never fails a successful run due to a report write error.

### REQ-KSP-101: Per-File Gate Verdict Breakdown

Each file in the report SHALL include a detailed breakdown:

```json
{
  "file_path": "src/CartService/Services/AlloyDbCartStore.cs",
  "verdict": "fail",
  "score": 0.0,
  "database": "postgresql",
  "language": "csharp",
  "finding_count": 1,
  "findings": [
    {
      "check_type": "injection",
      "severity": "error",
      "message": "String interpolation in DELETE query",
      "line": 47,
      "pattern_hash": "sha256:a1b2c3..."
    }
  ],
  "allowlisted": false,
  "security_sensitive": true,
  "gate_time_ms": 12.5
}
```

**Leverages:** `SecurityVerificationResult.to_dict()` for findings serialization; `SecurityScoreResult` from `scorer.py` for score+verdict; `verification_timing_ms` from `verify_file()`.

### REQ-KSP-102: Gate Timing Instrumentation

Each gate execution SHALL record timing for performance analysis:

| Metric | Source | What It Reveals |
|--------|--------|-----------------|
| `gate_time_ms` | `time.monotonic()` around `verify_file()` call | Per-file gate overhead |
| `scoring_time_ms` | `time.monotonic()` around `compute_security_score()` | Scoring computation cost |
| `allowlist_check_ms` | `time.monotonic()` around `is_allowlisted()` | Allowlist matching cost |
| `total_gate_time_ms` | Sum of all per-file gate times | Run-level gate overhead |

**Threshold alert:** If `total_gate_time_ms` exceeds 5000ms for a run, log a warning — pattern complexity or file count may need optimization.

### REQ-KSP-103: Verdict Distribution Summary

The report SHALL include a summary suitable for postmortem rendering:

```json
{
  "security_posture": "DEGRADED",
  "interpretation": "1 file failed the Anzen gate (injection in AlloyDbCartStore.cs). 11 of 12 gated files passed. 2 files skipped (no database surface).",
  "posture_level": "degraded",
  "posture_rules": {
    "clean": "All gated files pass (gate_pass_rate = 1.0)",
    "degraded": "Any file has verdict WARN or gate_pass_rate < 1.0",
    "critical": "Any file has verdict FAIL (injection or credential)"
  }
}
```

**Posture levels:**
- `clean` — gate_pass_rate = 1.0, no WARN verdicts
- `degraded` — gate_pass_rate < 1.0 OR any WARN verdicts, but no FAIL
- `critical` — any FAIL verdict (injection or credential finding)

---

## 4. Layer 2 — Scoring Calibration (REQ-KSP-2xx)

**Closes:** Gap KSP-2 (scoring thresholds are static)

`compute_security_score()` uses a max-severity-weighted formula (SP-SCR-003) with penalties: error=0.15, warning=0.05, diminishing rate=0.3. The quality gate threshold is `0.70`. These are reasonable defaults but have not been validated against production outcomes.

### REQ-KSP-200: Score Distribution Analysis

After each run, compute score distribution statistics:

```json
{
  "score_distribution": {
    "min": 0.0,
    "max": 1.0,
    "mean": 0.87,
    "median": 0.95,
    "p25": 0.70,
    "p75": 1.0,
    "std_dev": 0.28,
    "below_threshold": 2,
    "at_threshold": 0,
    "above_threshold": 10
  }
}
```

**Purpose:** Reveals whether the scoring formula produces a useful distribution. If scores cluster at 0.0 and 1.0 (bimodal), the formula correctly separates safe from unsafe. If scores cluster around the threshold (unimodal), the formula needs calibration.

### REQ-KSP-201: Threshold Sensitivity Report

For each run, compute the impact of threshold adjustments:

| Threshold | Files Passing | Files Failing | False Positives | False Negatives |
|-----------|--------------|--------------|-----------------|-----------------|
| 0.50 | 12 | 2 | 0 | 1 |
| 0.60 | 11 | 3 | 0 | 0 |
| 0.70 (current) | 10 | 4 | 1 | 0 |
| 0.80 | 8 | 6 | 3 | 0 |
| 0.90 | 5 | 9 | 5 | 0 |

**False positive definition:** File fails gate but has no injection or credential findings (only lifecycle warnings scored below threshold).
**False negative definition:** File passes gate but contains an injection or credential finding (should not occur with current FAIL=0.0 short-circuit, but validates the invariant).

**Acceptance criteria:**
- Report is advisory — does NOT change the threshold
- Logged at INFO level: "Threshold sensitivity: current=0.70, FP=1, FN=0. Suggested range: [0.55, 0.75]"
- When FN > 0, log at ERROR: "SECURITY INVARIANT VIOLATION: file with injection finding passed gate at threshold={threshold}"

### REQ-KSP-202: Score Component Contribution Analysis

For files that fail the gate, report which score components contributed:

```json
{
  "file_path": "src/CartService/Services/AlloyDbCartStore.cs",
  "score": 0.0,
  "component_contributions": {
    "max_severity_penalty": -0.15,
    "additional_penalties_diminished": -0.015,
    "short_circuit_applied": true,
    "short_circuit_reason": "injection finding → FAIL → 0.0"
  }
}
```

**Purpose:** When a file barely fails (score near threshold), understanding which component pushed it below helps determine if the formula is correctly weighted.

---

## 5. Layer 3 — Allowlist Effectiveness (REQ-KSP-3xx)

**Closes:** Gap KSP-3 (no allowlist effectiveness tracking)

`security_allowlist.yaml` is operator-declared and currently static. Without tracking, entries may become stale (underlying issue fixed but entry remains) or silently mask new true positives (framework update changes parameter binding behavior).

### REQ-KSP-300: Allowlist Hit Tracking

Each run SHALL record allowlist utilization:

```json
{
  "allowlist_metrics": {
    "entries_total": 3,
    "entries_hit": 2,
    "entries_unhit": 1,
    "hit_details": [
      {
        "file_pattern": "**/*SpannerCartStore.cs",
        "check_id": "injection",
        "hit_count": 2,
        "files_matched": ["src/CartService/Services/SpannerCartStore.cs", "src/CartService/Services/SpannerCartStoreV2.cs"],
        "justification": "Spanner uses parameterized queries via SpannerParameterCollection"
      }
    ],
    "unhit_entries": [
      {
        "file_pattern": "**/*RedisCache.cs",
        "check_id": "credential_leakage",
        "justification": "Redis connection string is from environment variable",
        "stale_since_run": "run-088"
      }
    ]
  }
}
```

**Leverages:** `allowlist.py:is_allowlisted()` already performs pattern matching; this adds a counter and records which entries matched.

### REQ-KSP-301: Stale Entry Detection

An allowlist entry SHALL be flagged as potentially stale when:

1. **No hits for 5+ consecutive runs** — the pattern may no longer match any generated files
2. **Underlying pattern no longer triggers** — re-running verification without the allowlist produces no finding for the pattern (the issue may have been fixed)

**Acceptance criteria:**
- Stale detection runs as a post-gate analysis (not in the hot path)
- Stale entries produce WARNING log: "Allowlist entry '{file_pattern}:{check_id}' has not matched in {N} runs — consider removal"
- Stale detection SHALL NOT remove entries — only report

### REQ-KSP-302: Allowlist Audit Report

A standalone script SHALL produce a comprehensive allowlist audit:

```
Security Allowlist Audit (3 entries)
════════════════════════════════════════════

ACTIVE (2 entries):
  ✓ **/*SpannerCartStore.cs : injection
    Last hit: run-095 (2026-03-21)
    Hit count: 12 across 6 runs
    Justification: Spanner parameterized queries

  ✓ **/*RedisCache.cs : credential_leakage
    Last hit: run-093 (2026-03-19)
    Hit count: 4 across 3 runs
    Justification: Redis connection string from env var

STALE (1 entry):
  ⚠ **/*LegacyCartStore.cs : injection
    Last hit: run-082 (2026-03-08)
    Not hit in 13 runs — consider removal
    Justification: Legacy direct SQL (since refactored)
```

---

## 6. Layer 4 — Cross-Run Aggregation (REQ-KSP-4xx)

**Closes:** Gap KSP-4 (no cross-run security posture trend)

### REQ-KSP-400: Cross-Run Security Posture Trend

A script SHALL read `security-gate-metrics.json` from multiple archived runs and compute:

```
Security Prime Posture Trends (last 5 runs)
══════════════════════════════════════════════
                       run-091  run-092  run-093  run-094  run-095
Gate pass rate         0.75     0.83     0.92     0.92     0.917  ↑
Mean score             0.68     0.74     0.85     0.87     0.87   ↑
Aggregate score        0.00     0.00     0.70     0.70     0.00   —
Injection findings     2        1        0        0        1      —
Allowlist hits         0        1        2        2        2      →
OWASP coverage (%)     30       30       30       30       30     →
Posture                CRIT     CRIT     CLEAN    CLEAN    CRIT   —
```

**Leverages:** `utils/trend_math.py:linear_slope()` for slope computation. Reuses the `kaizen-index.json` run archive from `batch_postmortem.py`.

### REQ-KSP-401: Gate Pass Rate Trajectory

Track gate pass rate (`files_pass / files_gated`) over time:

**Threshold alerts:**
- Pass rate declining (slope < -0.02/run) → WARNING: "Security gate pass rate is declining — review recent code generation prompts"
- Pass rate below 0.80 for 3+ consecutive runs → ERROR: "Sustained low pass rate — security posture degraded"
- Pass rate improving (slope > 0.02/run) → INFO: "Security posture improving — Kaizen hints may be effective"

### REQ-KSP-402: Score Distribution Evolution

Track how the score distribution changes across runs:

| Run | Min | Mean | Median | Bimodal | Interpretation |
|-----|-----|------|--------|---------|----------------|
| run-091 | 0.0 | 0.68 | 0.70 | Yes | Clear separation: safe vs. unsafe |
| run-093 | 0.70 | 0.85 | 0.95 | Yes | Improving: fewer low scores |
| run-095 | 0.0 | 0.87 | 1.0 | Yes | Single regression: AlloyDB file |

**Purpose:** Confirms the scoring formula maintains a useful distribution as the codebase evolves. A shift from bimodal to unimodal around the threshold signals the need for formula recalibration.

---

## 7. Layer 5 — Prompt Injection Effectiveness (REQ-KSP-5xx)

**Closes:** Gap KSP-5 (no P0/P1 prompt effectiveness measurement)

Security Prime injects three types of security guidance into LLM prompts:
1. **P0 hard constraint** — "MUST use parameterized queries" (SP-INJ-001)
2. **P1 library-specific guidance** — safe/unsafe examples from `DatabasePatternRegistry` (SP-INJ-020)
3. **Kaizen escalation hint** — escalating severity across consecutive violation runs (SP-KZ-010)

### REQ-KSP-500: P0 Constraint Impact Measurement

For each run, record whether the P0 constraint was injected and correlate with gate outcomes:

```json
{
  "prompt_effectiveness": {
    "p0_injected": true,
    "p0_injection_reason": "database driver detected: Npgsql",
    "security_sensitive_tasks": 8,
    "tasks_with_p0": 8,
    "gate_pass_rate_with_p0": 0.875,
    "injection_findings_with_p0": 1
  }
}
```

**Cross-run comparison:** When runs exist with and without P0 (e.g., non-database tasks mixed with database tasks), compare:
- Gate pass rate for P0-injected tasks vs. non-P0 tasks
- Injection finding rate for P0-injected tasks vs. non-P0 tasks

**Acceptance criteria:**
- Correlation is observational — no A/B testing within a single run
- Report includes: "P0-injected tasks: {pass_rate}% pass rate, {injection_rate}% injection rate"

### REQ-KSP-501: P1 Guidance Impact Measurement

Track whether P1 library-specific guidance improves outcomes for specific database×framework combinations:

```json
{
  "p1_effectiveness": {
    "p1_injected": true,
    "databases_with_p1": ["postgresql", "spanner"],
    "databases_without_p1": ["redis"],
    "p1_injection_rate": 0.0,
    "no_p1_injection_rate": 0.0,
    "p1_value_signal": "insufficient_data"
  }
}
```

**Value signal levels:**
- `insufficient_data` — fewer than 5 tasks with P1 guidance
- `positive` — P1-guided tasks have lower injection rate than baseline
- `neutral` — no measurable difference
- `negative` — P1-guided tasks have higher injection rate (regression — review P1 examples)

### REQ-KSP-502: Kaizen Hint Escalation Effectiveness

Track whether escalating hints (guidance → requirement → critical) reduce injection recurrence:

```json
{
  "hint_escalation": {
    "current_level": "requirement",
    "consecutive_injection_runs": 2,
    "level_history": [
      {"run": "run-093", "level": "guidance", "injection_found": true},
      {"run": "run-094", "level": "requirement", "injection_found": true},
      {"run": "run-095", "level": "critical", "injection_found": false}
    ],
    "effectiveness": "positive",
    "interpretation": "Injection resolved after escalation to 'critical' level"
  }
}
```

**Leverages:** `security_prime/kaizen.py:generate_security_hint()` already implements the 3-level escalation. `kaizen-metrics.json:security.consecutive_injection_runs` tracks the count.

**Effectiveness assessment:**
- `positive` — injection resolved within 3 escalation levels
- `neutral` — injection persists but at lower frequency
- `negative` — injection persists or worsens despite escalation (prompt guidance insufficient — structural fix needed)

---

## 8. Layer 6 — OWASP Coverage Progression (REQ-KSP-6xx)

**Closes:** Gap KSP-6 (OWASP coverage is static mapping)

`owasp_coverage.py` provides a static mapping of OWASP Top 10 categories to implemented check types. This layer makes coverage progression a measured Kaizen metric.

### REQ-KSP-600: OWASP Coverage Tracking Per Run

Each run SHALL report OWASP coverage status:

```json
{
  "owasp_coverage": {
    "categories_total": 10,
    "categories_covered": 4,
    "coverage_percentage": 0.40,
    "covered": [
      {"id": "A02:2021", "name": "Cryptographic Failures", "checks": ["credential_leakage"]},
      {"id": "A03:2021", "name": "Injection", "checks": ["injection"]},
      {"id": "A05:2021", "name": "Security Misconfiguration", "checks": ["lifecycle"]},
      {"id": "A09:2021", "name": "Security Logging and Monitoring Failures", "checks": ["credential_leakage"]}
    ],
    "uncovered": [
      {"id": "A01:2021", "name": "Broken Access Control", "impact": "high"},
      {"id": "A04:2021", "name": "Insecure Design", "impact": "medium"},
      {"id": "A06:2021", "name": "Vulnerable and Outdated Components", "impact": "high"},
      {"id": "A07:2021", "name": "Identification and Authentication Failures", "impact": "high"},
      {"id": "A08:2021", "name": "Software and Data Integrity Failures", "impact": "medium"},
      {"id": "A10:2021", "name": "Server-Side Request Forgery (SSRF)", "impact": "low"}
    ]
  }
}
```

**Leverages:** `owasp_coverage.py:generate_owasp_coverage()` already produces this data; this persists it in the gate metrics report.

### REQ-KSP-601: Coverage Gap Impact Ranking

Rank uncovered OWASP categories by impact based on project characteristics:

| Category | Impact | Reason |
|----------|--------|--------|
| A01: Broken Access Control | High | Project has API endpoints with user-specific data |
| A06: Vulnerable Components | High | Project uses NuGet packages — no supply chain checks |
| A07: Auth Failures | High | Project has authentication flows |
| A04: Insecure Design | Medium | Covered by architectural review, not automated checks |
| A08: Data Integrity | Medium | No deserialization detected in current codebase |
| A10: SSRF | Low | No external URL construction detected |

**Impact ranking heuristic:**
- `high` — project generates code that operates in the OWASP category's attack surface (e.g., SQL for A03, auth for A07)
- `medium` — category is relevant but not directly exercised by generated code
- `low` — category is not relevant to the project's generated code patterns

### REQ-KSP-602: Coverage Progression Trend

Track OWASP coverage percentage across runs:

```
OWASP Coverage Progression (last 5 runs)
═════════════════════════════════════════
                    run-091  run-092  run-093  run-094  run-095
Coverage %          30       30       30       40       40    ↑
Categories covered  3        3        3        4        4
New checks added                              lifecycle
```

**Purpose:** When new check types are implemented, they automatically increase OWASP coverage. The progression trend makes this visible and motivates check development for uncovered categories.

---

## 9. Existing Capabilities Leveraged

| Capability | Source | Kaizen Use |
|-----------|--------|------------|
| `record_gate_result()` | `security_prime/otel.py` | Per-file OTel data for L1 aggregation |
| `compute_security_score()` | `security_prime/scorer.py` | Score formula for L2 calibration |
| `compute_aggregate_score()` | `security_prime/scorer.py` | Weakest-link aggregate for L1 posture |
| `is_allowlisted()` | `security_prime/allowlist.py` | Allowlist matching for L3 hit tracking |
| `load_allowlist()` | `security_prime/allowlist.py` | Allowlist entries for L3 audit |
| `generate_security_hint()` | `security_prime/kaizen.py` | 3-level escalation for L5 effectiveness |
| `update_security_metrics()` | `security_prime/kaizen.py` | Existing `security` key in kaizen-metrics.json |
| `update_query_security_metrics()` | `security_prime/kaizen.py` | Existing `query_security` key (Query Prime Kaizen) |
| `generate_owasp_coverage()` | `security_prime/owasp_coverage.py` | Static coverage map for L6 tracking |
| `derive_security_contract()` | `security_prime/contract.py` | Contract derivation success tracking for L1 |
| `enrich_security_fields()` | `security_prime/enrichment.py` | Enrichment coverage for L1 |
| `linear_slope()` | `utils/trend_math.py` | Trend computation for L4 |
| `kaizen-metrics.json` | `prime_postmortem.py` | Run metrics archive for L4 cross-run aggregation |
| `CAUSE_TO_SUGGESTION` | `prime_postmortem.py` | Security root cause entries for Kaizen feedback loop |
| `_SEMANTIC_CATEGORY_TO_SUGGESTION` | `prime_postmortem.py` | Semantic category → suggestion mapping |
| `verify_file()` | `query_prime/security/__init__.py` | Verification with timing for L1 |
| `SecurityVerificationResult.verification_timing_ms` | `query_prime/models.py` | Per-phase timing for L1 |

---

## 10. Traceability Matrix

| Gap | Requirements | Kaizen Principle Rule | Security Prime Parent Req |
|-----|-------------|----------------------|--------------------------|
| KSP-1: No gate verdict history | REQ-KSP-100, 101, 102, 103 | Rule 1 (preserve all outputs) | SP-GT-001–007 |
| KSP-2: Static scoring thresholds | REQ-KSP-200, 201, 202 | Rule 3 (measure before and after) | SP-SCR-001–012 |
| KSP-3: No allowlist tracking | REQ-KSP-300, 301, 302 | Rule 3 (measure) + Rule 5 (feed forward) | Allowlist extension |
| KSP-4: No cross-run posture trend | REQ-KSP-400, 401, 402 | Rule 3 (measure) + Rule 6 (automate) | SP-KZ-020–021 |
| KSP-5: No prompt effectiveness | REQ-KSP-500, 501, 502 | Rule 5 (feed forward) + Rule 3 (measure) | SP-INJ-001–022, SP-KZ-010 |
| KSP-6: Static OWASP coverage | REQ-KSP-600, 601, 602 | Rule 3 (measure) + Rule 4 (attributable) | OWASP extension |

---

## 11. Verification Strategy

### Unit Tests

| Test Area | Expected Tests | Priority |
|-----------|---------------|----------|
| Gate verdict report schema (REQ-KSP-100) | 5 (schema fields, verdict counts, aggregate score, databases, timing) | P0 |
| Per-file breakdown (REQ-KSP-101) | 5 (verdict, score, findings, allowlist flag, timing) | P0 |
| Posture determination (REQ-KSP-103) | 4 (clean, degraded, critical, edge cases) | P0 |
| Score distribution stats (REQ-KSP-200) | 5 (min, max, mean, median, threshold counts) | P1 |
| Threshold sensitivity (REQ-KSP-201) | 4 (multiple thresholds, FP/FN detection, invariant violation) | P1 |
| Allowlist hit tracking (REQ-KSP-300) | 5 (hit, unhit, stale detection, multi-pattern, empty allowlist) | P1 |
| OWASP coverage report (REQ-KSP-600) | 3 (coverage %, covered/uncovered lists, impact ranking) | P1 |
| Hint escalation tracking (REQ-KSP-502) | 4 (level history, effectiveness assessment, consecutive count) | P2 |

### Integration Tests

| Test | Description |
|------|-------------|
| Gate metrics e2e | Run Prime Contractor with Security Prime → verify `security-gate-metrics.json` written with correct schema |
| Allowlist audit e2e | Run with allowlist → verify hit tracking and stale detection |
| Posture trend e2e | 3 archived runs → verify posture trend script produces correct slopes |
| Prompt effectiveness e2e | Run with P0 → verify correlation data recorded |

### Acceptance Criteria

1. AlloyDB multiline injection produces `posture_level: "critical"` in gate verdict report
2. Spanner parameterized code (with allowlist entry) produces `allowlist_hits: 1` in gate metrics
3. After 3 runs: trend script shows gate pass rate trajectory with correct slope
4. Score distribution analysis correctly reports bimodal distribution for mixed safe/unsafe files
5. Stale allowlist entry detected after 5 runs without a match
6. OWASP coverage report shows 4/10 categories covered (A02, A03, A05, A09)
7. P0 injection impact report correctly correlates P0 presence with gate pass rate

---

## 12. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) | Governing design principle (don't discard lessons across runs) |
| [ANZEN_DESIGN_PRINCIPLE.md](../../design-princples/ANZEN_DESIGN_PRINCIPLE.md) | Security correctness by design principle |
| [SECURITY_PRIME_REQUIREMENTS.md](SECURITY_PRIME_REQUIREMENTS.md) | Parent: orchestration layer that this Kaizen measures |
| [KAIZEN_QUERY_PRIME_REQUIREMENTS.md](../query-prime/KAIZEN_QUERY_PRIME_REQUIREMENTS.md) | Sibling: detection-layer Kaizen (per-check accuracy, FP tracking, scoring) |
| [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) | Sibling: code generation Kaizen (same 6-layer structure, different subject) |
| [SECURITY_PRIME_REMAINING_WORK.md](SECURITY_PRIME_REMAINING_WORK.md) | Remaining wiring work that unblocks Kaizen metrics persistence |
| `security_prime/kaizen.py` | Existing security metrics + escalation hints |
| `security_prime/scorer.py` | Scoring formula that L2 calibrates |
| `security_prime/owasp_coverage.py` | Static coverage map that L6 tracks over time |
| `security_prime/allowlist.py` | Allowlist mechanism that L3 tracks effectiveness of |
| `security_prime/otel.py` | OTel instrumentation that L1 aggregates into persistent reports |
| `query_prime/kaizen_metrics.py` | Query Prime Kaizen metrics (sibling at detection layer) |
| `utils/trend_math.py` | Shared `linear_slope()` utility for L4 trend computation |

---

## Appendix A: kaizen-metrics.json Key Coexistence

Three security-related keys coexist in `kaizen-metrics.json`, each owned by a different module:

| Key | Owner | What It Measures | When Written |
|-----|-------|-----------------|--------------|
| `security` | `security_prime/kaizen.py` | Anzen gate aggregate: injection_blocked, credential_blocked, aggregate_score, consecutive runs | After gate completes |
| `query_security` | `security_prime/kaizen.py` (via `update_query_security_metrics()`) | Query Prime per-work-item metrics: mean_score, pass_rate, by_database, by_tier | After Query Prime engine completes |
| `security_gate` | NEW (this spec) | Gate-level orchestration metrics: verdict distribution, allowlist hits, prompt effectiveness, OWASP coverage | After gate + postmortem |

All three keys are ADDITIVE — each module preserves the others when writing. Downstream consumers (Grafana dashboards, trend scripts) query the appropriate key for their concern.

## Appendix B: Relationship to SECURITY_PRIME_REMAINING_WORK.md

This Kaizen spec depends on two remaining work items being completed:

| Remaining Item | Kaizen Dependency | Impact |
|---------------|-------------------|--------|
| #5: Kaizen metrics persistence | L1, L4 | `update_security_metrics()` must be wired to produce the `security` key that L4 trends consume |
| #6: Batch postmortem security trends | L4 | Provides the run archive traversal that L4 trend analysis builds on |

**Recommended sequencing:** Complete remaining items #5 and #6 first (combined ~80 lines), then implement L1 (gate verdict report) which provides the data for all other layers.
