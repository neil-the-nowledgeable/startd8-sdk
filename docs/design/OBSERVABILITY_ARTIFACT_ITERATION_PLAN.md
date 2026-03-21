# Observability Artifact Iteration Plan

**Date**: 2026-03-21
**Status**: ACTIVE
**Input**: Run-090 (Python), Run-091 (C#), Run-092 (Go) quality reviews + OBSERVABILITY_PIPELINE_FIX_LIST.md
**Goal**: Iteratively improve each artifact type (Dashboards, Alerts, SLOs) across each pipeline phase until the artifacts are production-deployable.

---

## Current State Assessment

| Artifact Type | Format | Quality Grade | Key Gap |
|---------------|--------|---------------|---------|
| **Dashboard Specs** | DashboardSpec YAML | D+ | Latency-only panels, no RED method, no layout, phantom services |
| **Alert Rules** | Prometheus YAML | B- | Only latency alerts, no error rate or availability |
| **SLO Definitions** | OpenSLO v1 YAML | B | Target 99.0 != requirement 99.9, latency-only |
| **Manifest Index** | YAML | A | Clean, all paths resolve, derivation rules documented |

### Pipeline Integration Status

| Fix | Status | Impact |
|-----|--------|--------|
| Fix 0 (`self._cfg` assignment) | **TODO** | Blocks ALL downstream threading |
| Fix 1 (`--generation-profile`) | **DONE** | TODO completion now runs |
| Fix 2 (non-service filtering) | Partial | `protos` + `multiserviceprojectguidance` leak through |
| Fix 3 (per-task enrichment) | Code done, blocked by Fix 0 | |
| Fix 4 (contractor injection) | TODO (3 lines) | |

**Critical path**: Fix 0 (1 line) → Fix 4 (3 lines) → full pipeline value.

---

## Iteration Structure

Each artifact type iterates through 3 phases:

1. **Requirements** — What should the artifact contain? What inputs drive it?
2. **Generation** — Does `artifact_generator.py` produce correct output?
3. **Validation** — Does the output pass quality checks? Can it be deployed?

We iterate across artifact types in this order (highest impact first):

```
Round 1: Fix prerequisites (Fix 0, Fix 2, Fix 4)
Round 2: Dashboard Specs (biggest quality gap)
Round 3: Alert Rules (medium gap)
Round 4: SLO Definitions (smallest gap)
Round 5: Cross-artifact consistency + deployment verification
```

---

## Round 1: Prerequisites

### 1.1 Fix 0 — `self._cfg` Assignment

**File**: `src/startd8/workflows/builtin/plan_ingestion_workflow.py`
**Change**: 1 line — `self._cfg = cfg` after `cfg = PlanIngestionConfig.from_dict(config)`
**Unblocks**: Observability contract, security contract, generation profile flowing to emitter

### 1.2 Fix 2 — Non-Service Filtering

**File**: `src/startd8/observability/artifact_generator.py`
**Problem**: `protos` (shared proto definitions) and `multiserviceprojectguidance` (cross-cutting concern doc) produce phantom artifacts.
**Requirements**:
- REQ-OAG-001: `extract_service_hints()` MUST skip entries where `service_id` matches known non-service patterns: proto directories, requirement IDs (`req*`), project-level entries, run IDs
- REQ-OAG-002: Add configurable `_NON_SERVICE_PATTERNS` regex list
- REQ-OAG-003: Manifest `summary.services_skipped` MUST count filtered entries

### 1.3 Fix 4 — Contractor Injection

**File**: `src/startd8/contractors/prime_contractor.py`
**Change**: 3 lines in `_build_generation_context()` — inject `self._observability_contract` into `gen_context`

---

## Round 2: Dashboard Specs

### 2.1 Requirements Review

Current dashboard specs produce 3-4 histogram panels per service. A production service dashboard needs:

| Panel Category | Current | Required | Source |
|----------------|---------|----------|--------|
| **Latency** (p50, p95, p99) | 1 (p99 only) | 3 | Convention metrics + manifest latency_p99 |
| **Error Rate** | 0 | 1 | `rate(rpc_server_status{grpc_status!="OK"}[5m])` or HTTP 5xx |
| **Request Rate** | 0 | 1 | `rate(rpc_server_duration_count[5m])` or HTTP request count |
| **Availability** | 0 | 1 | 1 - error_rate, gauge with manifest availability target |
| **Active Connections** | 0 | 0-1 | Optional, transport-dependent |
| **DB Latency** | 0 | 0-1 | Only when `detected_databases` is non-empty |

**New requirements:**

| ID | Requirement |
|----|-------------|
| REQ-OAG-100 | Dashboard specs MUST include RED method panels: Rate, Errors, Duration |
| REQ-OAG-101 | Latency panels MUST include p50, p95, p99 quantiles (not just p99) |
| REQ-OAG-102 | Error rate panel MUST use transport-appropriate metric (gRPC status codes vs HTTP 5xx) |
| REQ-OAG-103 | Request rate panel MUST use `_count` suffix of the duration histogram |
| REQ-OAG-104 | Availability gauge MUST derive threshold from `manifest.spec.requirements.availability` |
| REQ-OAG-105 | Dashboard specs MUST include `gridPos` for all panels (4-column layout: 2 stats top, 4 panels middle, table bottom) |
| REQ-OAG-106 | Dashboard specs MUST include a `$service` variable when the dashboard is transport-scoped (not service-specific) |
| REQ-OAG-107 | DB latency panel MUST be generated when `detected_databases` is non-empty |
| REQ-OAG-108 | Dashboard `uid` MUST follow `obs-{service}` convention (current) |
| REQ-OAG-109 | Dashboard specs MUST include `links:` to related service dashboards derived from `service_communication_graph` |

### 2.2 Generation Changes

**File**: `src/startd8/observability/artifact_generator.py` — `generate_dashboard_spec()`

| Change | Description | LOC estimate |
|--------|-------------|-------------|
| Add error rate panel | Transport-aware: `grpc_status!="OK"` vs `http_server_status=~"5.."` | ~15 |
| Add request rate panel | `rate({duration_metric}_count{...}[5m])` | ~10 |
| Add availability gauge | `1 - error_rate`, threshold from manifest | ~15 |
| Add p50/p95 panels | Same histogram_quantile pattern, different quantile values | ~10 |
| Add gridPos | Standard 4-column layout function | ~20 |
| Add DB latency panel | Conditional on `detected_databases` | ~15 |
| Add cross-nav links | From `service_communication_graph` | ~15 |

### 2.3 Validation Criteria

- [ ] Every dashboard has >= 5 panels (latency p99, error rate, request rate, availability, size)
- [ ] All panels have `gridPos` with non-overlapping positions
- [ ] gRPC dashboards use `rpc_server_*` metrics; HTTP use `http_server_*`
- [ ] Availability gauge threshold matches manifest value
- [ ] No phantom services (protos, multiserviceprojectguidance) have dashboards

---

## Round 3: Alert Rules

### 3.1 Requirements Review

Current alert rules produce 1 latency alert per service. A production alert set needs:

| Alert Type | Current | Required | Derivation |
|------------|---------|----------|------------|
| **Latency P99 High** | 1 | 1 | `histogram_quantile(0.99, ...) > latency_p99` |
| **Error Rate High** | 0 | 1 | Transport-specific error rate > threshold (default 1%) |
| **Availability Below SLO** | 0 | 1 | `1 - error_rate < availability` over SLO window |
| **Request Rate Anomaly** | 0 | 0-1 | Optional: rate drops below baseline by >50% |

**New requirements:**

| ID | Requirement |
|----|-------------|
| REQ-OAG-200 | Alert rules MUST include error rate alert per service |
| REQ-OAG-201 | Error rate alert MUST use transport-appropriate error detection |
| REQ-OAG-202 | Alert rules MUST include availability alert derived from `manifest.spec.requirements.availability` |
| REQ-OAG-203 | Availability alert `for` duration MUST be >= 10m (avoid flapping) |
| REQ-OAG-204 | Alert severity MUST be derived from `manifest.spec.business.criticality` (existing — verify) |
| REQ-OAG-205 | Alert annotations MUST include `runbook_url` placeholder |
| REQ-OAG-206 | Alert annotations MUST include `dashboard_url` linking to the service dashboard |

### 3.2 Generation Changes

**File**: `src/startd8/observability/artifact_generator.py` — `generate_alert_rules()`

| Change | Description | LOC estimate |
|--------|-------------|-------------|
| Add error rate alert | `rate(rpc_server_status{grpc_status!="OK"}[5m]) / rate(rpc_server_duration_count[5m]) > 0.01` | ~20 |
| Add availability alert | `1 - error_rate < availability_target` | ~15 |
| Add runbook_url annotation | Placeholder `https://runbooks.example.com/{service}/{alert_name}` | ~3 |
| Add dashboard_url annotation | `/d/obs-{service}` | ~3 |

### 3.3 Validation Criteria

- [ ] Every service has >= 2 alerts (latency + error rate)
- [ ] Services with availability requirement have 3 alerts
- [ ] Alert thresholds match manifest values
- [ ] All alerts have `severity`, `service`, `protocol` labels
- [ ] All alerts have `summary`, `runbook_url`, `dashboard_url` annotations

---

## Round 4: SLO Definitions

### 4.1 Requirements Review

Current SLOs produce 1 latency SLO per service. Issues:
- `target: 99.0` when manifest says `availability: 99.9` (10x too lenient)
- No availability SLO (only latency)

| SLO Type | Current | Required | Derivation |
|----------|---------|----------|------------|
| **Latency P99** | 1 (target wrong) | 1 | threshold from `latency_p99`, target from `availability` |
| **Availability** | 0 | 1 | error-budget based, window from manifest or default 30d |

**New requirements:**

| ID | Requirement |
|----|-------------|
| REQ-OAG-300 | SLO `target` MUST match `manifest.spec.requirements.availability` (99.9 → 99.9, not hardcoded 99.0) |
| REQ-OAG-301 | Each service MUST have an availability SLO in addition to latency |
| REQ-OAG-302 | Availability SLO MUST use ratio-based measurement: `good_events / total_events` |
| REQ-OAG-303 | SLO `timeWindow.duration` MUST be derived from `manifest.strategy.objectives[].keyResults[].window` (existing — verify) |
| REQ-OAG-304 | SLO alert severity MUST match the alert rule severity for the same service |

### 4.2 Generation Changes

**File**: `src/startd8/observability/artifact_generator.py` — `generate_slo_definitions()`

| Change | Description | LOC estimate |
|--------|-------------|-------------|
| Fix target derivation | Use `_parse_availability_to_fraction()` * 100 instead of hardcoded 99.0 | ~3 |
| Add availability SLO | Ratio-based: good = non-error requests, total = all requests | ~25 |

### 4.3 Validation Criteria

- [ ] Every service has >= 2 SLOs (latency + availability)
- [ ] SLO targets match manifest values exactly
- [ ] SLO windows match derivation rules
- [ ] SLO alert severity is consistent with alert rules

---

## Round 5: Cross-Artifact Consistency

After Rounds 2-4, verify cross-artifact alignment:

| Check | Description |
|-------|-------------|
| Dashboard ↔ Alert | Every alert rule has a corresponding dashboard panel showing the same metric |
| Alert ↔ SLO | Every SLO has a corresponding alert that fires when the SLO is at risk |
| Dashboard ↔ SLO | Dashboard availability gauge threshold matches SLO target |
| Manifest ↔ All | Every `derivation_rules` entry in the manifest traces to a used value in at least one artifact |
| Service filter consistency | All three generators skip the same non-service entries |

### Deployment Verification

- [ ] Dashboard specs compile to valid Grafana JSON via direct JSON generator
- [ ] Alert rules load without error in Prometheus/Mimir
- [ ] SLO definitions validate against OpenSLO schema
- [ ] All artifacts import into local Grafana stack

---

## Execution Order

| Step | Round | Effort | Blocks |
|------|-------|--------|--------|
| 1 | R1: Fix 0 (`self._cfg`) | 1 line | R2-R5 pipeline data |
| 2 | R1: Fix 2 (non-service filter) | ~20 lines | R2-R4 clean services |
| 3 | R1: Fix 4 (contractor injection) | 3 lines | R2-R4 prompt quality |
| 4 | R2: Dashboard RED panels | ~100 lines | R5 dashboard↔alert check |
| 5 | R3: Alert error rate + availability | ~40 lines | R5 alert↔SLO check |
| 6 | R4: SLO target fix + availability SLO | ~30 lines | R5 SLO↔alert check |
| 7 | R5: Cross-artifact validation | ~50 lines | Deployment |
| 8 | R5: Deployment verification | Manual | Done |

**Total estimate**: ~245 lines of production code + tests.
