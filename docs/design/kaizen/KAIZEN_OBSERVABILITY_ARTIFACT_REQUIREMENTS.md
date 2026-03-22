# Kaizen for Observability Artifacts — Requirements

> **Version:** 1.3.0
> **Status:** DRAFT — Layer 7 simplified (validate-with-autofix, v1 pass-rate scoring) + plan-derived insights (§9b) 2026-03-21
> **Date:** 2026-03-21
> **Parent:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) (code generation Kaizen)
> **Sibling:** [UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md](../UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md) (generation pipeline)
> **Iteration Plan:** [OBSERVABILITY_ARTIFACT_ITERATION_PLAN.md](../OBSERVABILITY_ARTIFACT_ITERATION_PLAN.md) (functional requirements)
> **Scope:** Quality measurement, scoring, validation, postmortem evaluation, and feedback loops for generated observability artifacts (dashboards, alerts, SLOs)
> **Implementation Home:** `startd8-sdk` (validators + postmortem) + `cap-dev-pipe` (trend aggregation)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Disk Validation (REQ-KZ-OBS-1xx)](#3-layer-1--disk-validation-req-kz-obs-1xx)
4. [Layer 2 — Semantic Validators (REQ-KZ-OBS-2xx)](#4-layer-2--semantic-validators-req-kz-obs-2xx)
5. [Layer 3 — Quality Scoring (REQ-KZ-OBS-3xx)](#5-layer-3--quality-scoring-req-kz-obs-3xx)
6. [Layer 4 — Cross-Artifact Consistency (REQ-KZ-OBS-4xx)](#6-layer-4--cross-artifact-consistency-req-kz-obs-4xx)
7. [Layer 5 — Postmortem Integration (REQ-KZ-OBS-5xx)](#7-layer-5--postmortem-integration-req-kz-obs-5xx)
8. [Layer 6 — Feedback Loop (REQ-KZ-OBS-6xx)](#8-layer-6--feedback-loop-req-kz-obs-6xx)
9. [Traceability Matrix](#9-traceability-matrix)
10. [Verification Strategy](#10-verification-strategy)

---

## 1. Overview

### 1.1 Problem Statement

The code generation Kaizen system (REQ-KZ-100–601) provides comprehensive quality measurement for generated source code: disk validation, semantic checks, composite scoring, postmortem evaluation, cross-run trends, and feedback loops. No equivalent system exists for the three observability artifact types produced by the pipeline:

| Artifact Type | Format | Generator | Quality Gate Today |
|---------------|--------|-----------|-------------------|
| **Dashboard Specs** | DashboardSpec YAML | `generate_dashboard_spec()` | None — any output is accepted |
| **Alert Rules** | Prometheus YAML | `generate_alert_rules()` | None — any output is accepted |
| **SLO Definitions** | OpenSLO v1 YAML | `generate_slo_definitions()` | None — any output is accepted |

Run-092 demonstrated the gap: phantom services (`protos`, `multiserviceprojectguidance`) produced valid YAML artifacts that scored "generated" in the manifest but would produce empty dashboards and never-firing alerts if deployed.

### 1.2 Relationship to Existing Requirements

```
KAIZEN_PRIME_REQUIREMENTS.md (REQ-KZ-100–601)
├── Scoped to: generated source code (.py, .cs, .go, .java, .js)
├── Phases: A (registry enrichment), B (disk validation), C (feedback),
│           D (semantic checks), E (dual scoring)
└── Per-language: KAIZEN_PYTHON_REQUIREMENTS.md, KAIZEN_CSHARP_REQUIREMENTS.md, ...

UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md (REQ-UOM-001–072)
├── Scoped to: generation pipeline (input handling, three generators, drift detection)
└── Does NOT define quality scoring, postmortem, or feedback

OBSERVABILITY_ARTIFACT_ITERATION_PLAN.md (REQ-OAG-100–304)
├── Scoped to: functional requirements per artifact type (what panels, what alerts)
└── Does NOT define quality measurement or cross-run improvement

THIS DOCUMENT (REQ-KZ-OBS-100–600)
├── Scoped to: quality measurement system for observability artifacts
├── Mirrors KAIZEN_PRIME_REQUIREMENTS.md structure (6 layers)
└── Per-artifact-type (dashboard, alert, SLO) instead of per-language
```

### 1.3 Design Principles

1. **Same framework, different subject.** Reuse the Kaizen infrastructure (postmortem evaluator, kaizen-metrics.json, kaizen-trends, CAUSE_TO_SUGGESTION) — don't build a parallel system.
2. **Deterministic validation.** All checks are structural YAML analysis or manifest cross-referencing. No LLM calls for quality assessment.
3. **Artifact-type-specific validators.** Each artifact type has its own validation checklist, scoring formula, and root causes — mirroring the language-specific pattern in code generation.
4. **Manifest is ground truth.** The observability manifest's derivation rules define what each artifact *should* contain. Validation checks artifacts against these rules.

### 1.4 Key Characteristics

| Property | Value |
|----------|-------|
| Artifact types | 3 (dashboard_spec, alert_rule, slo_definition) |
| Validation approach | YAML structural analysis + manifest cross-reference |
| Scoring formula | Per-artifact-type composite (weighted components) |
| Postmortem integration | Artifact scores appended to existing `kaizen-metrics.json` |
| Feedback loop | Artifact-specific entries in `CAUSE_TO_SUGGESTION` |

---

## 2. Status Dashboard

| Req ID | Description | Impl Home | Status |
|--------|-------------|-----------|--------|
| **Layer 1 — Disk Validation** | | | |
| REQ-KZ-OBS-100 | Dashboard spec structural validation | startd8-sdk | **DONE** (observability_artifact_checks.py) |
| REQ-KZ-OBS-101 | Alert rule structural validation | startd8-sdk | **DONE** (observability_artifact_checks.py) |
| REQ-KZ-OBS-102 | SLO definition structural validation | startd8-sdk | **DONE** (observability_artifact_checks.py) |
| REQ-KZ-OBS-103 | Non-service entry detection | startd8-sdk | **DONE** (artifact_generator.py phantom filter) |
| **Layer 2 — Semantic Validators** | | | |
| REQ-KZ-OBS-200 | Dashboard completeness checks | startd8-sdk | **DONE** (RED coverage in validate_dashboard) |
| REQ-KZ-OBS-201 | Alert threshold alignment checks | startd8-sdk | **DONE** (validate_alerts coverage check) |
| REQ-KZ-OBS-202 | SLO target alignment checks | startd8-sdk | **DONE** (validate_slo target check) |
| REQ-KZ-OBS-203 | Metric name validity checks | startd8-sdk | **DONE** (validate_metric_names: naming, transport, _bucket) |
| **Layer 3 — Quality Scoring** | | | |
| REQ-KZ-OBS-300 | Dashboard quality score formula | startd8-sdk | **DONE** (v1 pass-rate in DashboardValidationResult.score) |
| REQ-KZ-OBS-301 | Alert quality score formula | startd8-sdk | **DONE** (v1 pass-rate in AlertValidationResult.score) |
| REQ-KZ-OBS-302 | SLO quality score formula | startd8-sdk | **DONE** (v1 pass-rate in SloValidationResult.score) |
| REQ-KZ-OBS-303 | Per-service composite artifact score | startd8-sdk | **DONE** (compute_service_composite) |
| **Layer 4 — Cross-Artifact Consistency** | | | |
| REQ-KZ-OBS-400 | Dashboard ↔ Alert alignment check | startd8-sdk | **DONE** (validate_cross_artifact_consistency) |
| REQ-KZ-OBS-401 | Alert ↔ SLO alignment check | startd8-sdk | **DONE** (validate_cross_artifact_consistency) |
| REQ-KZ-OBS-402 | Dashboard ↔ SLO alignment check | startd8-sdk | **DONE** (validate_cross_artifact_consistency) |
| REQ-KZ-OBS-403 | Manifest derivation completeness check | startd8-sdk | **DONE** (validate_derivation_completeness) |
| **Layer 5 — Postmortem Integration** | | | |
| REQ-KZ-OBS-500 | Artifact scores in kaizen-metrics.json | startd8-sdk | **DONE** (_write_quality_to_kaizen_metrics) |
| REQ-KZ-OBS-501 | Per-service artifact triplet evaluation | startd8-sdk | **DONE** (service_evaluations in kaizen-metrics) |
| REQ-KZ-OBS-502 | Observability quality in postmortem summary | startd8-sdk | **DONE** (render_postmortem_summary obs section) |
| **Layer 6 — Feedback Loop** | | | |
| REQ-KZ-OBS-600 | Artifact-specific CAUSE_TO_SUGGESTION entries | startd8-sdk | **DONE** (6 obs_ entries in CAUSE_TO_SUGGESTION) |
| REQ-KZ-OBS-601 | Observability quality in kaizen-trends.json | cap-dev-pipe | **DONE** (build_observability_section in batch_postmortem) |
| **Layer 7 — First-Class Pipeline Citizenship** | | | |
| REQ-KZ-OBS-700 | Post-generation validation gate | startd8-sdk | **DONE** (_repair_and_validate in artifact_generator) |
| REQ-KZ-OBS-710 | Deterministic repair steps (SLO target, metric name, gridPos) | startd8-sdk | **DONE** (repair_gridpos, repair_slo_target, _repair_bucket_suffix) |
| REQ-KZ-OBS-720 | Semantic checks (RED coverage, SLO alignment, alert coverage, transport) | startd8-sdk | **DONE** (validate_dashboard/alerts/slo semantic checks) |
| REQ-KZ-OBS-730 | Quality score computation (post-write) | startd8-sdk | **DONE** (quality_summary in index + observability-quality.json) |
| **Layer 7a — Plan-Derived Quick Wins** | | | |
| REQ-KZ-OBS-700a | Pipeline wiring: pass --manifest to generator | cap-dev-pipe | **RESOLVED** (2026-03-21, SDK reinstall) |
| REQ-KZ-OBS-704 | Manifest path propagation requirement | cap-dev-pipe | **VERIFIED** (run-atomic.sh:474) |
| REQ-KZ-OBS-705 | Retroactive validation (accept YAML content, not just paths) | startd8-sdk | **DONE** (validators accept string content) |
| REQ-KZ-OBS-706 | ArtifactResult extension (validation, repairs_applied, quality_score) | startd8-sdk | **DONE** (quality: Optional[Dict] field) |
| REQ-KZ-OBS-711 | Generator alert coverage (latency + error_rate + availability) | startd8-sdk | **DONE** (3-alert generation + RED panel synthesis) |

---

## 3. Layer 1 — Disk Validation (REQ-KZ-OBS-1xx)

Structural validation of generated artifacts. Equivalent to Phase B (`DiskComplianceResult`) in code generation. Each artifact type has its own validation checklist.

### REQ-KZ-OBS-100: Dashboard Spec Validation

Dashboard spec YAML files MUST be validated against the following checklist:

| Check | ID | Severity | Pass Criteria |
|-------|----|----------|---------------|
| YAML parseable | OBS-100a | error | `yaml.safe_load()` succeeds |
| `title` present | OBS-100b | error | Non-empty string |
| `uid` present | OBS-100c | error | Non-empty string matching `obs-{service}` pattern |
| `panels` non-empty | OBS-100d | error | At least 1 panel defined |
| Panel has `expr` | OBS-100e | error | Every panel has a PromQL expression |
| Panel has `type` | OBS-100f | warning | Every panel has a visualization type |
| Panel has `unit` | OBS-100g | warning | Every panel has a unit (s, bytes, reqps, etc.) |
| `gridPos` present | OBS-100h | warning | Every panel has grid positioning |
| `datasources` present | OBS-100i | warning | At least one datasource declared |
| `variables` present | OBS-100j | info | At least one variable (datasource selector) |

**Output model:**

```python
@dataclass
class DashboardValidationResult:
    file_path: str
    service_id: str
    yaml_valid: bool
    panel_count: int
    has_title: bool
    has_uid: bool
    has_gridpos: bool
    has_variables: bool
    checks_passed: int
    checks_total: int
    issues: List[Dict[str, Any]]  # [{check, severity, message}]
```

### REQ-KZ-OBS-101: Alert Rule Validation

Prometheus alert rule YAML files MUST be validated against the following checklist:

| Check | ID | Severity | Pass Criteria |
|-------|----|----------|---------------|
| YAML parseable | OBS-101a | error | `yaml.safe_load()` succeeds |
| `groups` present | OBS-101b | error | At least 1 group with at least 1 rule |
| Rule has `alert` name | OBS-101c | error | Non-empty PascalCase alert name |
| Rule has `expr` | OBS-101d | error | Non-empty PromQL expression |
| Rule has `for` duration | OBS-101e | warning | Duration string present (e.g., `5m`) |
| Rule has `severity` label | OBS-101f | error | One of: `critical`, `warning`, `info` |
| Rule has `service` label | OBS-101g | warning | Service identifier label |
| Rule has `summary` annotation | OBS-101h | warning | Human-readable summary |
| PromQL metric exists in convention | OBS-101i | warning | Metric name matches a convention metric for the service's transport |

**Output model:**

```python
@dataclass
class AlertValidationResult:
    file_path: str
    service_id: str
    yaml_valid: bool
    rule_count: int
    severity_labels_present: bool
    summary_annotations_present: bool
    checks_passed: int
    checks_total: int
    issues: List[Dict[str, Any]]
```

### REQ-KZ-OBS-102: SLO Definition Validation

OpenSLO v1 YAML files MUST be validated against the following checklist:

| Check | ID | Severity | Pass Criteria |
|-------|----|----------|---------------|
| YAML parseable | OBS-102a | error | `yaml.safe_load()` succeeds |
| `apiVersion: openslo/v1` | OBS-102b | error | Correct OpenSLO version |
| `kind: SLO` | OBS-102c | error | Correct kind |
| `spec.target` present | OBS-102d | error | Numeric target value |
| `spec.timeWindow` present | OBS-102e | error | Duration + rolling flag |
| `spec.indicator` present | OBS-102f | error | SLI with threshold metric |
| `metadata.name` present | OBS-102g | warning | Follows `{service}-{type}-{metric}` pattern |
| `metadata.labels.service` | OBS-102h | warning | Service identifier label |
| `spec.alerting` present | OBS-102i | info | Alert integration defined |
| Threshold metric has PromQL | OBS-102j | error | `spec.indicator.spec.thresholdMetric.metricSource.spec.query` is non-empty |

**Output model:**

```python
@dataclass
class SloValidationResult:
    file_path: str
    service_id: str
    yaml_valid: bool
    target_value: Optional[float]
    window_duration: Optional[str]
    has_indicator: bool
    has_alerting: bool
    checks_passed: int
    checks_total: int
    issues: List[Dict[str, Any]]
```

### REQ-KZ-OBS-103: Non-Service Entry Detection

The artifact generator MUST detect and skip non-service entries before generating artifacts.

**Acceptance criteria:**
- Entries where `service_id` matches a requirement ID pattern (`req*`, `REQ-*`) are skipped
- Entries where `service_id` matches a run ID pattern (`*/run-*`) are skipped
- Entries where `service_id` is a known non-service directory (`protos`, `proto`, `shared`, `common`, `lib`, `docs`) are skipped
- Entries where `service_id` matches a project-level name (e.g., matches `project_id` from the manifest) are skipped
- Skipped entries are counted in `manifest.summary.services_skipped`
- Skipped entries are logged at INFO level with the skip reason

---

## 4. Layer 2 — Semantic Validators (REQ-KZ-OBS-2xx)

Semantic checks go beyond structural validity to detect artifacts that parse correctly but are functionally wrong. Equivalent to Phase D (semantic checks) in code generation.

### REQ-KZ-OBS-200: Dashboard Completeness Checks

| Check | ID | Severity | Description |
|-------|----|----------|-------------|
| RED method coverage | OBS-200a | warning | Dashboard MUST have panels covering at least 2 of 3 RED signals: Rate, Errors, Duration |
| Latency quantile coverage | OBS-200b | info | Latency panels SHOULD include p99 at minimum; p50 + p95 recommended |
| Phantom service detection | OBS-200c | error | Service name in PromQL MUST correspond to a real runtime service (not `protos`, `multiserviceprojectguidance`) |
| Metric name validity | OBS-200d | warning | Metric names in `expr` MUST use Prometheus naming convention (lowercase, underscores) and match known OTel semantic conventions |
| Threshold-manifest alignment | OBS-200e | warning | Latency threshold in panels MUST match `manifest.spec.requirements.latency_p99` |

### REQ-KZ-OBS-201: Alert Threshold Alignment Checks

| Check | ID | Severity | Description |
|-------|----|----------|-------------|
| Latency threshold matches manifest | OBS-201a | warning | Alert expr threshold MUST equal `latency_p99` from derivation rules |
| Severity matches criticality | OBS-201b | warning | Alert `severity` label MUST match the `alert_severity` derivation rule |
| Missing error rate alert | OBS-201c | warning | Services with `availability` requirement SHOULD have an error rate alert |
| Missing availability alert | OBS-201d | info | Services with `availability` requirement SHOULD have an availability alert |

### REQ-KZ-OBS-202: SLO Target Alignment Checks

| Check | ID | Severity | Description |
|-------|----|----------|-------------|
| Target matches availability | OBS-202a | error | SLO `spec.target` MUST match `manifest.spec.requirements.availability` (e.g., 99.9, not hardcoded 99.0) |
| Window matches derivation | OBS-202b | warning | SLO `timeWindow.duration` MUST match the `slo_window` derivation rule |
| Threshold matches latency_p99 | OBS-202c | warning | Latency SLO threshold MUST match `manifest.spec.requirements.latency_p99` |
| Missing availability SLO | OBS-202d | warning | Services with `availability` requirement SHOULD have an availability (ratio-based) SLO in addition to latency |

### REQ-KZ-OBS-203: Metric Name Validity Checks

| Check | ID | Severity | Description |
|-------|----|----------|-------------|
| Prometheus naming convention | OBS-203a | warning | Metric names MUST use lowercase with underscores (e.g., `rpc_server_duration_bucket`, not `rpc.server.duration`) |
| Transport-metric alignment | OBS-203b | error | gRPC services MUST use `rpc_server_*` metrics; HTTP services MUST use `http_server_*` metrics |
| Metric suffix validity | OBS-203c | warning | Histogram metrics MUST reference `_bucket` suffix in `histogram_quantile()` calls |

---

## 5. Layer 3 — Quality Scoring (REQ-KZ-OBS-3xx)

Per-artifact-type quality scores. Two tiers: v1 (simple pass rate) and v2 (weighted composite).

### REQ-KZ-OBS-300–302: Quality Scoring — v1 (Simple Pass Rate)

For initial implementation, each artifact type uses the same simple formula:

```
artifact_score = checks_passed / checks_total
```

Where `checks_passed` and `checks_total` come from the validation result (Layer 1 + Layer 2 checks combined). This is sufficient to discriminate between good and bad artifacts, is self-evident to interpret, and requires no weight calibration.

**Short-circuit:** YAML parse failure → 0.0. Phantom service → 0.0.

### REQ-KZ-OBS-300–302: Quality Scoring — v2 (Weighted Composite, Future)

Once v1 scoring produces data across 10+ runs, calibrate weighted composites:

**Dashboard (v2):**
```
dashboard_score = (structural_validity × 0.25) + (red_coverage × 0.30)
               + (manifest_alignment × 0.25) + (layout_completeness × 0.10) + (navigation × 0.10)
```

**Alerts (v2):**
```
alert_score = (structural_validity × 0.30) + (threshold_alignment × 0.30)
            + (rule_coverage × 0.20) + (label_completeness × 0.10) + (annotation_quality × 0.10)
```

**SLOs (v2):**
```
slo_score = (structural_validity × 0.25) + (target_accuracy × 0.35)
          + (schema_compliance × 0.20) + (alert_integration × 0.20)
```

**v2 is deferred until v1 pass-rate data from 10+ runs reveals which components need independent weighting.** v1 pass-rate already captures the essential quality signal.

### REQ-KZ-OBS-303: Per-Service Composite Artifact Score

Each service receives a composite score across its artifact triplet:

```
service_obs_score = (dashboard_score x 0.35)
                  + (alert_score     x 0.35)
                  + (slo_score       x 0.30)
```

Services without all three artifacts receive a proportional penalty:
- Missing dashboard: `dashboard_score = 0.0`
- Missing alert: `alert_score = 0.0`
- Missing SLO: `slo_score = 0.0`

---

## 6. Layer 4 — Cross-Artifact Consistency (REQ-KZ-OBS-4xx)

Cross-artifact alignment checks verify that the three artifact types tell a consistent story. Equivalent to cross-feature pattern detection in code generation.

### REQ-KZ-OBS-400: Dashboard ↔ Alert Alignment

**Check:** Every alert rule's PromQL metric SHOULD appear in at least one dashboard panel.

**Rationale:** An alert that fires but has no corresponding dashboard panel forces operators to investigate blind. The dashboard should visualize what the alert measures.

**Output:** List of `unvisualized_alerts` — alert rules with metrics not present in any dashboard panel.

### REQ-KZ-OBS-401: Alert ↔ SLO Alignment

**Check:** Every SLO's indicator metric SHOULD have a corresponding alert rule that fires before the error budget is exhausted.

**Rationale:** An SLO without a pre-emptive alert means the team only learns about budget consumption after the fact.

**Output:** List of `unalerted_slos` — SLOs with indicator metrics not covered by any alert.

### REQ-KZ-OBS-402: Dashboard ↔ SLO Alignment

**Check:** Dashboard availability gauges (if present) SHOULD use the same threshold as the SLO target.

**Rationale:** A dashboard showing 99.0% availability as "green" when the SLO requires 99.9% creates a false sense of health.

**Output:** List of `misaligned_thresholds` — dashboard panel thresholds that don't match SLO targets.

### REQ-KZ-OBS-403: Manifest Derivation Completeness

**Check:** Every `derivation_rules` entry in the observability manifest MUST trace to at least one correctly-consumed value in at least one artifact.

**Rationale:** Derivation rules that produce values consumed by no artifact indicate either dead rules or missing artifact features. Rules whose values are consumed but with wrong values (e.g., `availability: 99.9` consumed as `target: 99.0`) indicate generator bugs.

**Output:**
- `unused_derivations` — rules whose output field doesn't appear in any artifact
- `consumed_incorrect` — rules whose output field appears but with a mismatched value (cross-referenced with OBS-202a/OBS-201a checks)

---

## 7. Layer 5 — Postmortem Integration (REQ-KZ-OBS-5xx)

Artifact quality scores integrated into the existing postmortem pipeline. Equivalent to `PrimePostMortemEvaluator` integration in code generation.

### REQ-KZ-OBS-500: Artifact Scores in kaizen-metrics.json

The existing `kaizen-metrics.json` MUST be extended with observability artifact quality metrics:

```json
{
  "observability_artifacts": {
    "services_evaluated": 4,
    "services_with_complete_triplet": 3,
    "phantom_services_detected": 1,
    "avg_dashboard_score": 0.72,
    "avg_alert_score": 0.85,
    "avg_slo_score": 0.90,
    "avg_composite_score": 0.82,
    "cross_artifact_issues": {
      "unvisualized_alerts": 2,
      "unalerted_slos": 1,
      "misaligned_thresholds": 1,
      "unused_derivations": 0
    }
  }
}
```

### REQ-KZ-OBS-501: Per-Service Artifact Triplet Evaluation

The postmortem evaluator MUST produce a per-service artifact quality assessment:

```json
{
  "service_id": "cartservice",
  "dashboard_score": 0.85,
  "alert_score": 0.90,
  "slo_score": 0.95,
  "composite_score": 0.90,
  "issues": [
    {"check": "OBS-200a", "severity": "warning", "message": "Missing error rate panel (RED coverage: 2/3)"}
  ],
  "cross_artifact_issues": []
}
```

### REQ-KZ-OBS-502: Observability Quality in Postmortem Summary

The existing `prime-postmortem-summary.md` MUST include an "Observability Artifacts" section when artifacts were generated:

```markdown
## Observability Artifacts

- Services evaluated: 4 (1 phantom skipped)
- Average dashboard score: 0.72
- Average alert score: 0.85
- Average SLO score: 0.90
- Cross-artifact issues: 4
```

---

## 8. Layer 6 — Feedback Loop (REQ-KZ-OBS-6xx)

Artifact-specific feedback entries for the Kaizen improvement system. Equivalent to `CAUSE_TO_SUGGESTION` entries in code generation.

### REQ-KZ-OBS-600: Artifact-Specific CAUSE_TO_SUGGESTION Entries

The following root cause codes MUST be added to `CAUSE_TO_SUGGESTION` in `prime_postmortem.py`:

| Root Cause Code | Phase | Hint |
|-----------------|-------|------|
| `obs_phantom_service` | artifact_gen | "Service '{service}' is not a runtime service — add to non-service skip list" |
| `obs_missing_red_panels` | artifact_gen | "Dashboard for '{service}' is missing RED method panels. Add error rate and request rate panels alongside latency" |
| `obs_slo_target_mismatch` | artifact_gen | "SLO target {actual} does not match manifest availability {expected}. Use manifest value" |
| `obs_threshold_mismatch` | artifact_gen | "Alert/dashboard threshold {actual} does not match manifest latency_p99 {expected}" |
| `obs_missing_availability_slo` | artifact_gen | "Service '{service}' has availability requirement but no availability SLO" |
| `obs_transport_metric_mismatch` | artifact_gen | "Service '{service}' uses {transport} but metrics reference wrong protocol family" |

### REQ-KZ-OBS-601: Observability Quality in kaizen-trends.json

The existing `kaizen-trends.json` MUST include observability artifact quality trends when artifacts are present:

```json
{
  "observability_trend": {
    "avg_composite_slope": 0.05,
    "avg_dashboard_slope": 0.03,
    "avg_alert_slope": 0.01,
    "avg_slo_slope": 0.08,
    "phantom_services_resolved": true,
    "phantom_ratio_slope": -0.05,
    "phantom_services_per_run": [7, 5, 2, 0],
    "red_coverage_improving": true
  }
}
```

**Calculation:** Same `_linear_slope()` function used for code generation success rate, applied to per-artifact-type scores and composite across runs. `phantom_ratio_slope` tracks `phantom_services_detected / total_services` per run — a negative slope means phantom filtering is improving.

---

## 9. First-Class Pipeline Citizenship — Validation and Repair

### 9.0 Current State

As of run-093, observability artifacts have **zero validation, zero quality gates, zero repair, and zero semantic checks**. The generation pipeline is:

```
generate_alert_rules() → write YAML → done  (no validation)
generate_dashboard_spec() → write YAML → done  (no validation)
generate_slo_definitions() → write YAML → done  (no validation)
```

Compare with source code, which has: syntax check → lint → semantic checks → repair pipeline (fence strip, AST validate, import fix, lint fix) → contract violation repair → Anzen security gate → quality scoring → postmortem. Observability artifacts get none of this.

### REQ-KZ-OBS-700: Post-Generation Validation Gate

The artifact generator MUST validate each generated artifact immediately after generation and before writing to disk.

| ID | Requirement |
|----|-------------|
| OBS-700a | After `generate_dashboard_spec()` returns, run `validate_dashboard()` (REQ-KZ-OBS-100 checklist). If any error-severity check fails, log WARNING and set `status="validation_warning"` in ArtifactResult. |
| OBS-700b | After `generate_alert_rules()` returns, run `validate_alerts()` (REQ-KZ-OBS-101 checklist). Same error handling. |
| OBS-700c | After `generate_slo_definitions()` returns, run `validate_slo()` (REQ-KZ-OBS-102 checklist). Same error handling. |
| OBS-700d | Validation results SHALL be attached to `ArtifactResult` as a `validation` field containing the validation result dataclass. |
| OBS-700e | Validation SHALL NOT block generation (graduated enforcement: warn-by-default). Artifacts with validation warnings are still written but flagged for postmortem evaluation. |
| OBS-700f | A `--strict` mode SHALL cause validation failures to set `status="error"` and skip writing the artifact. |

### REQ-KZ-OBS-710: Validate-with-Autofix (Combined Repair + Semantic Checks)

Each validation check follows a single pattern: **try to autofix → validate → report**. This replaces the original three-layer approach (repair → validate → semantic check) which created redundant passes over the same data.

| ID | Check | Autofix? | Severity | Description |
|----|-------|----------|----------|-------------|
| OBS-710a | SLO target alignment | Yes (from manifest) | error | If `spec.target` doesn't match `manifest.availability`, autofix to manifest value. Safety net — generator should produce correct value when SDK is properly installed. |
| OBS-710b | gridPos presence | Yes (inject 2×2 grid) | warning | If dashboard panels lack `gridPos`, inject default layout. Only genuine post-generation repair — generator doesn't produce layout info. |
| OBS-710c | RED coverage | No (generator must fix) | warning | Dashboard MUST cover ≥2/3 RED signals. Missing signals logged with specific PromQL guidance. |
| OBS-710d | Alert coverage | No (generator must fix) | warning | Services with `availability` requirement MUST have latency + error_rate alerts. |
| OBS-710e | Transport-metric alignment | No | error | gRPC → `rpc_server_*`, HTTP → `http_server_*`. |
| OBS-710f | Metric name format | Yes (via `_prom_name()`) | warning | Convert OTel dot notation to Prometheus underscore. Uses existing function. |
| OBS-710g | `_bucket` suffix | Yes (append) | warning | `histogram_quantile()` metric references must include `_bucket` suffix. |

**Design decisions:**
- Repair and validation are ONE pass, not three separate layers. Each check: autofix if possible → validate → append to issues list.
- Autofixes are idempotent. Each logs at INFO with old→new values.
- Checks the generator CANNOT self-fix (RED coverage, alert coverage) are flagged as issues for the Kaizen feedback loop to address via generator improvements (REQ-KZ-OBS-711).
- `ArtifactResult` gains ONE field: `quality: Optional[Dict]` containing `{score, checks_passed, checks_total, issues, repairs_applied}`.

### REQ-KZ-OBS-730: Quality Score Computation (Post-Write)

After artifacts are written, compute per-artifact and per-service scores using the formulas in REQ-KZ-OBS-300–303.

| ID | Requirement |
|----|-------------|
| OBS-730a | Scores SHALL be computed by `scripts/generate_observability_artifacts.py` after all artifacts are written. |
| OBS-730b | Scores SHALL be written to `{output_dir}/observability-quality.json` alongside the artifacts. |
| OBS-730c | The generation script SHALL print a quality summary: per-service composite score, aggregate score, and top issues. |
| OBS-730d | `observability-quality.json` SHALL be consumed by the postmortem evaluator (REQ-KZ-OBS-500) to populate `kaizen-metrics.json`. |

---

## 9b. Plan-Derived Requirements (from implementation planning)

These requirements emerged from the implementation plan and address gaps not visible from the requirements alone. See [OBSERVABILITY_ARTIFACT_VALIDATION_PLAN.md](./OBSERVABILITY_ARTIFACT_VALIDATION_PLAN.md) for the full analysis.

### REQ-KZ-OBS-700a: Pipeline Wiring Quick Win (P0)

Before implementing any SDK validation/repair/scoring, the pipeline MUST be fixed to pass the manifest:

| ID | Requirement |
|----|-------------|
| OBS-700a-1 | The SDK MUST be installed from the latest source on the Python interpreter the pipeline uses. **RESOLVED** (2026-03-21): installed on system Python 3.14. Prior runs used stale SDK missing phantom filtering + Security Prime + correct `load_business_context()`. |
| OBS-700a-2 | The pipeline script `run-atomic.sh:474` already passes `--manifest` correctly. **VERIFIED** (2026-03-21): `load_business_context()` correctly reads `availability: 99.9` from `.contextcore.yaml` with current code. Run-093's SLO target=99.0 was caused by the stale SDK, not a wiring gap. |

**Impact:** SDK reinstall alone resolves phantom filtering (7/9 → 0/9), SLO target mismatch (99.0 → 99.9), and Security Prime activation. The next run will produce correct values without any code changes. What remains is building validation/repair/scoring infrastructure (~380 lines).

### REQ-KZ-OBS-704: Manifest Path Propagation

| ID | Requirement |
|----|-------------|
| OBS-704a | `generate_observability_artifacts()` SHOULD auto-discover `.contextcore.yaml` when `--manifest` is not explicitly provided, as a safety net. Pipeline already passes `--manifest` (verified in `run-atomic.sh:474`), so this is defense-in-depth, not the primary path. |
| OBS-704b | When auto-discovery finds a manifest, log at INFO. When not found, log WARNING with the default values that will be used. |

### REQ-KZ-OBS-705: Retroactive Validation

| ID | Requirement |
|----|-------------|
| OBS-705a | Validators MUST accept YAML content as a string, not only file paths. This enables retroactive scoring of prior run artifacts. |
| OBS-705b | A standalone script (`scripts/validate_observability_artifacts.py`) SHOULD accept an `--artifacts-dir` argument and produce `observability-quality.json` for any existing artifact directory. |

### REQ-KZ-OBS-706: ArtifactResult Extension

| ID | Requirement |
|----|-------------|
| OBS-706a | `ArtifactResult` SHALL gain ONE field: `quality: Optional[Dict]` containing `{score: float, checks_passed: int, checks_total: int, issues: List[Dict], repairs_applied: List[str]}`. One field, not three — minimal dataclass change, quality data co-located. |
| OBS-706b | Autofixes that modify content SHALL log at INFO with field changed and old→new values. |

### REQ-KZ-OBS-710 (revised): Repair Step Clarifications

| ID | Revision |
|----|----------|
| OBS-710a (revised) | SLO target repair is a SAFETY NET. With the SDK properly installed AND `--manifest` already passed by `run-atomic.sh`, the target is correct at generation time. Repair catches edge cases where the manifest is unavailable or the value changed between generation and validation. |
| OBS-710b (revised) | Uses the existing `_otel_to_prom()` function in `artifact_generator.py`. No new conversion logic needed. |
| OBS-710e (revised) | Repair steps run INLINE in the generator loop (not via a separate orchestrator). Each repair that modifies content logs at INFO. |

### REQ-KZ-OBS-711: Generator Alert Coverage (Future)

| ID | Requirement |
|----|-------------|
| OBS-711a | The alert generator SHOULD produce at minimum: latency P99 alert + error rate alert + availability alert when the manifest specifies an `availability` requirement. |
| OBS-711b | This is a generator enhancement, not a repair step. Repair cannot add missing alerts — only fix existing ones. |
| OBS-711c | Tracked for future implementation after validation/scoring infrastructure is in place. |

---

## 10. Traceability Matrix

| Kaizen Code Phase | Code Generation Equivalent | Observability Artifact Equivalent | Status |
|---|---|---|---|
| Phase A (Registry) | `set_phase_status("implement", "generated")` metadata | `ArtifactResult.derivations` traceability | **DONE** |
| Phase B (Disk Validation) | `DiskComplianceResult` | `DashboardValidationResult`, `AlertValidationResult`, `SloValidationResult` (REQ-KZ-OBS-700) | **DONE** |
| Phase C (Feedback) | `CAUSE_TO_SUGGESTION` → kaizen hints | `obs_*` entries in `CAUSE_TO_SUGGESTION` (REQ-KZ-OBS-600) | **DONE** (6 entries) |
| Phase D (Semantic) | `run_semantic_checks()` — 4 Python / 8 C# checks | REQ-KZ-OBS-720 semantic validators (RED coverage, SLO alignment, alert coverage) | **DONE** |
| Phase E (Scoring) | `compute_disk_quality_score()` | REQ-KZ-OBS-730 per-type + composite scoring | **DONE** (v1 pass-rate) |
| Repair | `repair/orchestrator.py` → fence strip, AST, lint, import | REQ-KZ-OBS-710 → SLO target, gridPos, bucket suffix | **DONE** |
| Gate | Anzen gate (Security Prime) → PASS/FAIL | REQ-KZ-OBS-700 → validation gate (warn-by-default) | **DONE** (--strict PLANNED) |

---

## 10. Verification Strategy

### Unit Tests

| Test Area | Expected Tests | Priority |
|-----------|---------------|----------|
| Dashboard validation (REQ-KZ-OBS-100) | 10 (one per check) | P0 |
| Alert validation (REQ-KZ-OBS-101) | 9 (one per check) | P0 |
| SLO validation (REQ-KZ-OBS-102) | 10 (one per check) | P0 |
| Non-service filtering (REQ-KZ-OBS-103) | 5 (known patterns) | P0 |
| Dashboard scoring (REQ-KZ-OBS-300) | 5 (component isolation + composite) | P1 |
| Alert scoring (REQ-KZ-OBS-301) | 5 | P1 |
| SLO scoring (REQ-KZ-OBS-302) | 5 | P1 |
| Cross-artifact checks (REQ-KZ-OBS-400–403) | 8 | P1 |
| Postmortem integration (REQ-KZ-OBS-500–502) | 3 | P2 |

### Integration Tests

| Test | Description |
|------|-------------|
| Run-092 regression | Validate run-092 artifacts produce expected scores (phantom service detected, RED coverage gap flagged, SLO target mismatch caught) |
| Full pipeline | Run plan ingestion with Fix 0 + Fix 4 → verify artifact scores in kaizen-metrics.json |

### Acceptance Criteria

1. Run-092's `protos` and `multiserviceprojectguidance` score 0.0 (phantom service detection)
2. Run-092's `cartservice` dashboard scores < 0.7 (missing error rate + request rate panels)
3. Run-092's SLOs score < 1.0 (target 99.0 vs requirement 99.9 mismatch)
4. `kaizen-metrics.json` includes `observability_artifacts` section after scoring runs
5. Cross-artifact checks flag at least 1 unvisualized alert (error rate) per service
