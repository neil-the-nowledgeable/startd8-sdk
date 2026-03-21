# Kaizen for Observability Artifacts — Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
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
| REQ-KZ-OBS-100 | Dashboard spec structural validation | startd8-sdk | PLANNED |
| REQ-KZ-OBS-101 | Alert rule structural validation | startd8-sdk | PLANNED |
| REQ-KZ-OBS-102 | SLO definition structural validation | startd8-sdk | PLANNED |
| REQ-KZ-OBS-103 | Non-service entry detection | startd8-sdk | PARTIAL (Fix 2) |
| **Layer 2 — Semantic Validators** | | | |
| REQ-KZ-OBS-200 | Dashboard completeness checks | startd8-sdk | PLANNED |
| REQ-KZ-OBS-201 | Alert threshold alignment checks | startd8-sdk | PLANNED |
| REQ-KZ-OBS-202 | SLO target alignment checks | startd8-sdk | PLANNED |
| REQ-KZ-OBS-203 | Metric name validity checks | startd8-sdk | PLANNED |
| **Layer 3 — Quality Scoring** | | | |
| REQ-KZ-OBS-300 | Dashboard quality score formula | startd8-sdk | PLANNED |
| REQ-KZ-OBS-301 | Alert quality score formula | startd8-sdk | PLANNED |
| REQ-KZ-OBS-302 | SLO quality score formula | startd8-sdk | PLANNED |
| REQ-KZ-OBS-303 | Per-service composite artifact score | startd8-sdk | PLANNED |
| **Layer 4 — Cross-Artifact Consistency** | | | |
| REQ-KZ-OBS-400 | Dashboard ↔ Alert alignment check | startd8-sdk | PLANNED |
| REQ-KZ-OBS-401 | Alert ↔ SLO alignment check | startd8-sdk | PLANNED |
| REQ-KZ-OBS-402 | Dashboard ↔ SLO alignment check | startd8-sdk | PLANNED |
| REQ-KZ-OBS-403 | Manifest derivation completeness check | startd8-sdk | PLANNED |
| **Layer 5 — Postmortem Integration** | | | |
| REQ-KZ-OBS-500 | Artifact scores in kaizen-metrics.json | startd8-sdk | PLANNED |
| REQ-KZ-OBS-501 | Per-service artifact triplet evaluation | startd8-sdk | PLANNED |
| REQ-KZ-OBS-502 | Observability quality in postmortem summary | startd8-sdk | PLANNED |
| **Layer 6 — Feedback Loop** | | | |
| REQ-KZ-OBS-600 | Artifact-specific CAUSE_TO_SUGGESTION entries | startd8-sdk | PLANNED |
| REQ-KZ-OBS-601 | Observability quality in kaizen-trends.json | cap-dev-pipe | PLANNED |

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

Per-artifact-type composite scores. Equivalent to Phase E (`compute_disk_quality_score()`) in code generation.

### REQ-KZ-OBS-300: Dashboard Quality Score

```
dashboard_score = (structural_validity  x 0.25)
               + (red_coverage          x 0.30)
               + (manifest_alignment    x 0.25)
               + (layout_completeness   x 0.10)
               + (navigation            x 0.10)
```

| Component | Score Range | How Computed |
|-----------|-----------|--------------|
| `structural_validity` | 0.0 or 1.0 | YAML parses, has title, uid, ≥1 panel with expr |
| `red_coverage` | 0.0 – 1.0 | `(RED signals present) / 3`. Rate=1, Errors=1, Duration=1. Minimum 2/3 for passing |
| `manifest_alignment` | 0.0 – 1.0 | Latency threshold matches manifest. Transport-correct metrics. No phantom services |
| `layout_completeness` | 0.0 or 1.0 | All panels have `gridPos`. 0.0 if any panel lacks positioning |
| `navigation` | 0.0 or 1.0 | Dashboard has `links` or `dataLinks` to related dashboards. 0.0 if none |

**Short-circuit:** YAML parse failure → 0.0. Phantom service → 0.0.

### REQ-KZ-OBS-301: Alert Quality Score

```
alert_score = (structural_validity  x 0.30)
            + (threshold_alignment  x 0.30)
            + (label_completeness   x 0.20)
            + (annotation_quality   x 0.20)
```

| Component | Score Range | How Computed |
|-----------|-----------|--------------|
| `structural_validity` | 0.0 or 1.0 | YAML parses, ≥1 group with ≥1 rule, each rule has alert name + expr |
| `threshold_alignment` | 0.0 – 1.0 | `1.0 - (mismatched_thresholds / total_thresholds)`. Thresholds checked against manifest derivation rules |
| `label_completeness` | 0.0 – 1.0 | `(present_labels) / (required_labels)`. Required: `severity`, `service`. Optional: `protocol`, `team` |
| `annotation_quality` | 0.0 – 1.0 | `(present_annotations) / (required_annotations)`. Required: `summary`. Optional: `runbook_url`, `dashboard_url`, `source` |

**Short-circuit:** YAML parse failure → 0.0. No rules → 0.0.

### REQ-KZ-OBS-302: SLO Quality Score

```
slo_score = (structural_validity  x 0.25)
          + (target_accuracy      x 0.35)
          + (schema_compliance    x 0.20)
          + (alert_integration    x 0.20)
```

| Component | Score Range | How Computed |
|-----------|-----------|--------------|
| `structural_validity` | 0.0 or 1.0 | YAML parses, has apiVersion + kind + spec.target + spec.indicator |
| `target_accuracy` | 0.0 or 1.0 | SLO `target` exactly matches `manifest.spec.requirements.availability` × 100. Mismatch → 0.0 |
| `schema_compliance` | 0.0 – 1.0 | OpenSLO v1 required fields present: metadata.name, spec.timeWindow, spec.budgetPolicy, spec.indicator.spec.thresholdMetric |
| `alert_integration` | 0.0 or 1.0 | `spec.alerting` section present with severity label. 0.0 if absent |

**Short-circuit:** YAML parse failure → 0.0. Missing target → 0.0.

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

**Check:** Every `derivation_rules` entry in the observability manifest MUST trace to at least one used value in at least one artifact.

**Rationale:** Derivation rules that produce values consumed by no artifact indicate either dead rules or missing artifact features.

**Output:** List of `unused_derivations` — derivation rules whose output field doesn't appear in any artifact.

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
    "phantom_services_resolved": true,
    "red_coverage_improving": true
  }
}
```

**Calculation:** Same `_linear_slope()` function used for code generation success rate, applied to `avg_composite_score` across runs that produced observability artifacts.

---

## 9. Traceability Matrix

| Kaizen Code Phase | Code Generation Equivalent | Observability Artifact Equivalent |
|---|---|---|
| Phase A (Registry) | `set_phase_status("implement", "generated")` metadata | `ArtifactResult.derivations` traceability |
| Phase B (Disk Validation) | `DiskComplianceResult` | `DashboardValidationResult`, `AlertValidationResult`, `SloValidationResult` |
| Phase C (Feedback) | `CAUSE_TO_SUGGESTION` → kaizen hints | `obs_*` entries in `CAUSE_TO_SUGGESTION` |
| Phase D (Semantic) | `run_semantic_checks()` — 4 Python / 8 C# checks | REQ-KZ-OBS-200–203 semantic validators |
| Phase E (Scoring) | `compute_disk_quality_score()` | REQ-KZ-OBS-300–303 per-type + composite scoring |

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
