# Unified Observability Manifest — Implementation Plan

**Requirements**: `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md`
**Date**: 2026-03-20
**Estimated new code**: ~800 lines (module) + ~200 lines (script) + ~600 lines (tests)

---

## Overview

This plan wires existing ContextCore business context and instrumentation hints through to deployable observability artifacts. The system reads `onboarding-metadata.json` (produced by cap-dev-pipe Stage 4 EXPORT) and `.contextcore.yaml`, then generates alert rules, dashboard specs, and SLO definitions per service.

**New files**:
- `src/startd8/observability/artifact_generator.py` — Core generation logic (~800 lines)
- `scripts/generate_observability_artifacts.py` — CLI entry point (~200 lines)
- `tests/unit/observability/test_artifact_generator.py` — Unit tests (~600 lines)

**Modified files**:
- `.cap-dev-pipe/startd8-sdk-cap-dlv-pipe.sh` — Pipeline integration (5-10 lines)

**No modifications to**: plan ingestion, prime contractor, existing observability manifest, ContextCore.

---

## Phase 1: Input Loading + Data Models

**Goal**: Load `onboarding-metadata.json` and `.contextcore.yaml`, extract the fields needed for artifact generation, and define output data models.

**Covers**: REQ-UOM-001, REQ-UOM-002, REQ-UOM-070

### 1.1 Create `src/startd8/observability/artifact_generator.py`

```python
"""
Generate observability artifacts (alert rules, dashboard specs, SLO definitions)
from ContextCore onboarding metadata and manifest business context.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Input models — extracted from onboarding-metadata.json + .contextcore.yaml
# ---------------------------------------------------------------------------

@dataclass
class ConventionMetric:
    """A single OTel convention-based metric expected for a service."""
    name: str           # e.g. "rpc.server.duration"
    type: str           # e.g. "histogram", "counter"
    source: str         # e.g. "otel_semconv:grpc"


@dataclass
class ServiceHints:
    """Instrumentation hints for a single service."""
    service_id: str
    transport: str                              # "grpc" or "http"
    language: Optional[str] = None              # "python", "go", etc.
    detected_databases: List[str] = field(default_factory=list)
    convention_metrics: List[ConventionMetric] = field(default_factory=list)


@dataclass
class BusinessContext:
    """Business context extracted from .contextcore.yaml."""
    criticality: str = "medium"                 # critical, high, medium, low
    availability: Optional[str] = None          # e.g. "99.9" (percent)
    latency_p99: Optional[str] = None           # e.g. "500ms"
    throughput: Optional[str] = None            # e.g. "100rps"
    error_budget: Optional[str] = None          # e.g. "0.1" (percent)
    dashboard_placement: str = "standard"       # standard, overview
    owner: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    slo_window: str = "30d"                     # from strategy.objectives if available


# ---------------------------------------------------------------------------
# Output models — per-artifact generation results
# ---------------------------------------------------------------------------

@dataclass
class DerivationTrace:
    """Records how a value was derived for traceability (REQ-UOM-040)."""
    field: str          # e.g. "alert_severity"
    source: str         # e.g. "manifest.spec.business.criticality"
    transformation: str # e.g. "high → critical"
    tier: str           # "explicit", "manifest", "default"


@dataclass
class ArtifactResult:
    """Result of generating a single artifact file."""
    artifact_type: str      # "alert_rule", "dashboard_spec", "slo_definition"
    service_id: str
    output_path: str
    status: str             # "generated", "skipped", "error"
    derivations: List[DerivationTrace] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class GenerationReport:
    """Summary of all generated artifacts (REQ-UOM-004)."""
    project_id: Optional[str]
    generated_at: str
    artifacts: List[ArtifactResult] = field(default_factory=list)
    services_processed: int = 0
    services_skipped: int = 0
```

### 1.2 Input loading functions

```python
def load_onboarding_metadata(path: Path) -> Dict[str, Any]:
    """Load onboarding-metadata.json. Returns raw dict."""
    ...

def extract_service_hints(metadata: Dict[str, Any]) -> List[ServiceHints]:
    """Extract per-service instrumentation hints from onboarding metadata.

    Reads metadata["instrumentation_hints"] and converts to ServiceHints.
    Returns empty list if instrumentation_hints is absent (REQ-UOM-070).
    """
    ...

def load_business_context(
    manifest_path: Optional[Path],
    metadata: Dict[str, Any],
) -> BusinessContext:
    """Extract business context from .contextcore.yaml (preferred) or
    fall back to onboarding-metadata fields.

    Reads: spec.business.criticality, spec.requirements.*, spec.observability.*,
    strategy.objectives[].keyResults[].window (for SLO window).
    """
    ...
```

### 1.3 Criticality → severity mapping

```python
_CRITICALITY_TO_SEVERITY: Dict[str, str] = {
    "critical": "critical",
    "high": "critical",
    "medium": "warning",
    "low": "info",
}
```

### 1.4 Validation

- `load_onboarding_metadata`: Raise `FileNotFoundError` if path missing. Return empty dict on parse error with logged warning.
- `extract_service_hints`: Log warning and return `[]` if `instrumentation_hints` key absent. Skip services with no `transport` field (REQ-UOM-071).
- `load_business_context`: All fields optional. Log when defaults applied (REQ-UOM-072).

### Tests (Phase 1)

| Test | Validates |
|------|-----------|
| `test_load_onboarding_metadata_valid` | Happy path: loads JSON, returns dict |
| `test_load_onboarding_metadata_missing_file` | FileNotFoundError raised |
| `test_extract_service_hints_happy_path` | Converts instrumentation_hints → ServiceHints list |
| `test_extract_service_hints_missing_key` | Returns [] with warning log when key absent |
| `test_extract_service_hints_skips_no_transport` | Services without transport skipped |
| `test_load_business_context_from_manifest` | Reads .contextcore.yaml fields |
| `test_load_business_context_fallback_to_metadata` | Falls back when no manifest path |
| `test_load_business_context_all_defaults` | All fields default when nothing available |
| `test_criticality_to_severity_mapping` | All 4 criticality levels map correctly |

**Deliverable**: Input loading works, all data models defined, tests pass.

---

## Phase 2: Alert Rule Generation

**Goal**: For each service, generate a Prometheus alerting rule YAML file from convention metrics + SLO thresholds + criticality.

**Covers**: REQ-UOM-010, REQ-UOM-011, REQ-UOM-012

### 2.1 Approach decision: Reuse vs. inline

The ContextCore `generate_prometheus_rule(name, namespace, spec)` function produces a K8s `PrometheusRule` object. Its interface expects a `spec` dict shaped like a ProjectContext.

**Decision**: **Inline the alert rule generation** rather than importing from ContextCore. Rationale:
1. The ContextCore function is tightly coupled to its K8s CRD shape (`name`, `namespace` params, `apiVersion: monitoring.coreos.com/v1` wrapper)
2. Our inputs are `ServiceHints` + `BusinessContext`, not a ProjectContext spec
3. The core logic (parse latency threshold, compute error rate, build PromQL) is ~40 lines — simpler to write than to adapt
4. Avoids a runtime dependency on the ContextCore package from the SDK

### 2.2 Implementation

```python
def generate_alert_rules(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate Prometheus alert rules for a single service.

    Creates one alert per (convention_metric × applicable SLO threshold):
    - Duration metrics (histogram) × latencyP99 → histogram_quantile alert
    - Request count metrics (counter) × availability → error_rate alert

    Severity derived from business.criticality via _CRITICALITY_TO_SEVERITY.
    """
    ...
```

**Alert derivation logic**:

| Convention Metric Type | SLO Field | PromQL Pattern |
|------------------------|-----------|----------------|
| `*.duration` (histogram) | `latency_p99` | `histogram_quantile(0.99, rate({metric}_bucket{service="{svc}"}[5m])) > {threshold_sec}` |
| `*.request.size` / `*.response.size` | — | No alert (size metrics are informational) |
| `*.requests_per_rpc` (counter) | `availability` | `1 - (rate({metric}{service="{svc}",code=~"(UNAVAILABLE|INTERNAL)"}[5m]) / rate({metric}{service="{svc}"}[5m])) < {avail_fraction}` |
| `http.server.duration` (histogram) | `latency_p99` | `histogram_quantile(0.99, rate({metric}_bucket{service="{svc}"}[5m])) > {threshold_sec}` |

**Metric name normalization**: OTel convention names use dots (`rpc.server.duration`). Prometheus uses underscores (`rpc_server_duration`). Apply `name.replace(".", "_")` for PromQL.

**Output format** (per service file):

```yaml
# Generated by startd8 observability artifact generator
# Source: onboarding-metadata.json + .contextcore.yaml
# Service: checkout-api (transport: grpc)
#
# Derivation:
#   alert_severity: manifest.spec.business.criticality (high → critical)
#   latency_threshold: manifest.spec.requirements.latencyP99 (500ms → 0.5s)
#   availability_threshold: manifest.spec.requirements.availability (99.9 → 0.999)

groups:
  - name: checkout-api.slo
    rules:
      - alert: CheckoutApiLatencyP99High
        expr: |
          histogram_quantile(0.99,
            rate(rpc_server_duration_bucket{service="checkout-api"}[5m])
          ) > 0.5
        for: 5m
        labels:
          severity: critical
          service: checkout-api
          protocol: grpc
        annotations:
          summary: "checkout-api p99 latency exceeds 500ms"
          source: "Derived from manifest.spec.requirements.latencyP99"

      - alert: CheckoutApiAvailabilityLow
        expr: |
          (
            1 - rate(rpc_server_requests_per_rpc{service="checkout-api",grpc_code=~"Unavailable|Internal"}[5m])
              / rate(rpc_server_requests_per_rpc{service="checkout-api"}[5m])
          ) < 0.999
        for: 5m
        labels:
          severity: critical
          service: checkout-api
          protocol: grpc
        annotations:
          summary: "checkout-api availability below 99.9%"
          source: "Derived from manifest.spec.requirements.availability"
```

### 2.3 Threshold parsing helpers

```python
def _parse_duration_to_seconds(value: str) -> float:
    """Parse '500ms' → 0.5, '2s' → 2.0, '200' → 0.2 (assume ms)."""
    ...

def _parse_availability_to_fraction(value: str) -> float:
    """Parse '99.9' → 0.999, '99.95' → 0.9995."""
    ...

def _prometheus_metric_name(otel_name: str) -> str:
    """Convert OTel dot-separated name to Prometheus underscore format.
    'rpc.server.duration' → 'rpc_server_duration'
    """
    return otel_name.replace(".", "_")
```

### 2.4 Three-tier fallback (REQ-UOM-012)

```python
_DEFAULT_THRESHOLDS = {
    "availability": "99",
    "latency_p99": "500ms",
    "throughput": "100rps",
}
```

Resolution order per threshold:
1. CLI override (not in Phase 2, deferred to Phase 6 if needed)
2. `BusinessContext` field (from manifest)
3. `_DEFAULT_THRESHOLDS`

Each resolution logs which tier was used and records a `DerivationTrace`.

### Tests (Phase 2)

| Test | Validates |
|------|-----------|
| `test_generate_alert_rules_grpc_service` | gRPC service produces latency + availability alerts |
| `test_generate_alert_rules_http_service` | HTTP service produces http.server.duration alert |
| `test_generate_alert_rules_no_slo_uses_defaults` | Missing thresholds fall back to defaults |
| `test_generate_alert_rules_criticality_mapping` | high → critical, medium → warning, low → info |
| `test_generate_alert_rules_derivation_traces` | Each alert records derivation source + tier |
| `test_parse_duration_to_seconds` | "500ms" → 0.5, "2s" → 2.0, "200" → 0.2 |
| `test_parse_availability_to_fraction` | "99.9" → 0.999, "99.95" → 0.9995 |
| `test_prometheus_metric_name` | Dot → underscore conversion |
| `test_generate_alert_rules_no_duration_metrics` | Service with only size metrics → no latency alert |
| `test_alert_yaml_is_valid` | Output parses as valid YAML |

**Deliverable**: Alert YAML files generated per service with derivation comments.

---

## Phase 3: Dashboard Spec Generation

**Goal**: For each service, generate a `DashboardSpec` YAML file from convention metrics, compatible with the existing DashboardCreatorWorkflow.

**Covers**: REQ-UOM-020, REQ-UOM-021, REQ-UOM-022

### 3.1 Metric-to-panel mapping

```python
_INSTRUMENT_TO_PANEL: Dict[str, str] = {
    "histogram": "histogram",
    "counter": "timeseries",
    "gauge": "gauge",
    "up_down_counter": "timeseries",
    "observable_gauge": "gauge",
}

_INSTRUMENT_TO_QUERY_TEMPLATE: Dict[str, str] = {
    "histogram": 'histogram_quantile(0.99, rate({metric}_bucket{{service="{service}"}}[$__rate_interval]))',
    "counter": 'rate({metric}_total{{service="{service}"}}[$__rate_interval])',
    "gauge": '{metric}{{service="{service}"}}',
    "up_down_counter": '{metric}{{service="{service}"}}',
    "observable_gauge": '{metric}{{service="{service}"}}',
}
```

### 3.2 Implementation

```python
def generate_dashboard_spec(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate a DashboardSpec YAML for a single service.

    Creates one panel per convention metric with panel type derived from
    instrument type. Produces a YAML file compatible with DashboardCreatorWorkflow.
    """
    ...
```

**Panel generation per metric**:
1. Look up panel type from `_INSTRUMENT_TO_PANEL[metric.type]`
2. Build PromQL from `_INSTRUMENT_TO_QUERY_TEMPLATE[metric.type]` with metric name + service
3. Assign to group by category (Latency, Throughput, Size)
4. Add thresholds from `BusinessContext` if applicable (latency panels get P99 threshold line)

**DashboardSpec YAML output** (per service):

```yaml
# Generated by startd8 observability artifact generator
# Service: checkout-api (transport: grpc, language: go)
title: "checkout-api Observability"
uid: "obs-checkout-api"
description: "Auto-derived observability dashboard for checkout-api (gRPC)"
tags:
  - generated
  - observability
  - grpc
datasources:
  prometheus: prometheus
panels:
  - type: histogram
    title: "RPC Server Duration (P99)"
    expr: 'histogram_quantile(0.99, rate(rpc_server_duration_bucket{service="checkout-api"}[$__rate_interval]))'
    unit: s
    group: Latency
    thresholds:
      - value: null
        color: green
      - value: 0.5
        color: red
  - type: timeseries
    title: "RPC Requests Per RPC"
    expr: 'rate(rpc_server_requests_per_rpc_total{service="checkout-api"}[$__rate_interval])'
    unit: reqps
    group: Throughput
  - type: timeseries
    title: "RPC Request Size"
    expr: 'rate(rpc_server_request_size_total{service="checkout-api"}[$__rate_interval])'
    unit: bytes
    group: Size
  - type: timeseries
    title: "RPC Response Size"
    expr: 'rate(rpc_server_response_size_total{service="checkout-api"}[$__rate_interval])'
    unit: bytes
    group: Size
variables:
  - type: prometheusDatasource
    name: datasource
    label: Datasource
```

**Note**: This is `DashboardSpec` YAML, not Grafana JSON. It can be fed through the existing DashboardCreatorWorkflow (`/dbrd-cr8r`) to produce the final Grafana JSON, but the spec YAML itself is a useful artifact documenting expected dashboards.

### 3.3 Dashboard placement (REQ-UOM-022)

- `criticality: critical|high` + `dashboardPlacement: overview` → add tag `overview` to DashboardSpec for placement routing
- Default: `standard` placement (no special tag)

### Tests (Phase 3)

| Test | Validates |
|------|-----------|
| `test_generate_dashboard_spec_grpc` | gRPC service → 4 panels (duration, requests, req_size, resp_size) |
| `test_generate_dashboard_spec_http` | HTTP service → 3 panels (duration, req_size, resp_size) |
| `test_panel_type_from_instrument` | histogram→histogram, counter→timeseries, gauge→gauge |
| `test_dashboard_spec_yaml_valid` | Output parses as valid YAML |
| `test_dashboard_spec_compatible_with_model` | Output loads into DashboardSpec Pydantic model |
| `test_dashboard_spec_threshold_from_slo` | Latency panel gets threshold from business.latency_p99 |
| `test_dashboard_placement_critical` | Critical service gets overview tag |
| `test_dashboard_spec_derivation_traces` | Derivation traces recorded |

**Deliverable**: DashboardSpec YAML files generated per service, loadable by DashboardCreatorWorkflow.

---

## Phase 4: SLO Definition Generation

**Goal**: For each SLO-relevant business requirement, generate an SLO definition YAML per service using convention metrics.

**Covers**: REQ-UOM-030, REQ-UOM-031

### 4.1 SLO shape (OpenSLO-inspired, practical subset)

```yaml
# Generated by startd8 observability artifact generator
# Service: checkout-api
# Derivation:
#   availability_target: manifest.spec.requirements.availability (99.9)
#   latency_target: manifest.spec.requirements.latencyP99 (500ms)
#   window: manifest.strategy.objectives[0].keyResults[0].window (30d)

apiVersion: openslo/v1
kind: SLO
metadata:
  name: checkout-api-availability
  labels:
    service: checkout-api
    protocol: grpc
    generated_by: startd8
spec:
  description: "Availability SLO for checkout-api"
  target: 99.9
  timeWindow:
    duration: 30d
    isRolling: true
  budgetPolicy: occurrences
  indicator:
    metadata:
      name: checkout-api-availability-sli
    spec:
      ratioMetric:
        counter:
          metricSource:
            type: prometheus
            spec:
              query: 'rate(rpc_server_requests_per_rpc{service="checkout-api"}[5m])'
        good:
          metricSource:
            type: prometheus
            spec:
              query: 'rate(rpc_server_requests_per_rpc{service="checkout-api",grpc_code!~"Unavailable|Internal"}[5m])'
  alerting:
    name: checkout-api-availability-alert
    labels:
      severity: critical
---
apiVersion: openslo/v1
kind: SLO
metadata:
  name: checkout-api-latency-p99
  labels:
    service: checkout-api
    protocol: grpc
    generated_by: startd8
spec:
  description: "P99 latency SLO for checkout-api"
  target: 99.0
  timeWindow:
    duration: 30d
    isRolling: true
  budgetPolicy: timeslices
  indicator:
    metadata:
      name: checkout-api-latency-sli
    spec:
      thresholdMetric:
        metricSource:
          type: prometheus
          spec:
            query: 'histogram_quantile(0.99, rate(rpc_server_duration_bucket{service="checkout-api"}[5m]))'
        threshold: 0.5
        operator: lte
  alerting:
    name: checkout-api-latency-alert
    labels:
      severity: critical
```

### 4.2 Implementation

```python
def generate_slo_definitions(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate OpenSLO-format SLO definitions for a single service.

    Produces one SLO per applicable business requirement:
    - availability → ratio-based SLO (good requests / total requests)
    - latency_p99 → threshold-based SLO (P99 under threshold)

    Uses convention metrics from service hints for the PromQL queries.
    """
    ...
```

**SLO derivation logic**:

| Business Requirement | SLO Type | Convention Metric Used | Query Pattern |
|----------------------|----------|------------------------|---------------|
| `availability` | Ratio (good/total) | First counter metric for protocol | good = requests without error codes |
| `latency_p99` | Threshold | First histogram metric for protocol | P99 under threshold |

**Metric selection**: For each SLO, select the appropriate metric from the service's `convention_metrics`:
- Availability → first metric with `type: counter` (typically `rpc.server.requests_per_rpc` or `http.server.duration` counts)
- Latency → first metric with `type: histogram` (typically `rpc.server.duration` or `http.server.duration`)

### 4.3 Window resolution

1. Check `strategy.objectives[].keyResults[].window` for matching `metricKey` (availability, latency)
2. Fall back to `BusinessContext.slo_window` (default: "30d")
3. Record which tier was used in `DerivationTrace`

### Tests (Phase 4)

| Test | Validates |
|------|-----------|
| `test_generate_slo_availability` | Availability SLO with ratio metric |
| `test_generate_slo_latency` | Latency SLO with threshold metric |
| `test_generate_slo_both` | Service with both requirements → 2 SLOs in one file |
| `test_generate_slo_no_requirements` | No requirements → uses defaults, logs warning |
| `test_generate_slo_window_from_objectives` | Window pulled from strategy.objectives |
| `test_generate_slo_window_default` | Falls back to 30d |
| `test_slo_yaml_valid` | Output parses as valid YAML |
| `test_slo_alert_severity_from_criticality` | Alert severity matches criticality |

**Deliverable**: OpenSLO YAML files generated per service.

---

## Phase 5: Orchestration + Index File

**Goal**: Wire the three generators together with a top-level orchestrator that produces the index file.

**Covers**: REQ-UOM-003, REQ-UOM-004, REQ-UOM-041

### 5.1 Orchestrator

```python
def generate_observability_artifacts(
    onboarding_metadata_path: Path,
    output_dir: Path,
    manifest_path: Optional[Path] = None,
    dry_run: bool = False,
) -> GenerationReport:
    """Top-level orchestrator.

    1. Load inputs (onboarding metadata + business context)
    2. Extract per-service hints
    3. For each service: generate alerts, dashboard spec, SLO definitions
    4. Write index file (observability-manifest.yaml)
    5. Return generation report
    """
    metadata = load_onboarding_metadata(onboarding_metadata_path)
    services = extract_service_hints(metadata)
    business = load_business_context(manifest_path, metadata)

    if not services:
        logger.warning("No instrumentation hints found; producing zero artifacts")
        return GenerationReport(...)

    results: List[ArtifactResult] = []
    for service in services:
        results.append(generate_alert_rules(service, business))
        results.append(generate_dashboard_spec(service, business))
        results.append(generate_slo_definitions(service, business))

    if not dry_run:
        _write_artifacts(results, output_dir)
        _write_index(results, business, output_dir)

    return GenerationReport(
        project_id=business.project_id,
        generated_at=_utc_now_iso(),
        artifacts=results,
        services_processed=len(services),
        services_skipped=sum(1 for s in services if not s.transport),
    )
```

### 5.2 File writing

```python
def _write_artifacts(results: List[ArtifactResult], output_dir: Path) -> None:
    """Write generated YAML artifacts to disk.

    Creates subdirectories: alerts/, dashboards/, slos/
    """
    ...

def _write_index(
    results: List[ArtifactResult],
    business: BusinessContext,
    output_dir: Path,
) -> None:
    """Write observability-manifest.yaml index file (REQ-UOM-004).

    Contains: project metadata, list of generated artifacts with status,
    all derivation rules applied across all artifacts.
    """
    ...
```

### 5.3 Index file format

```yaml
# observability-manifest.yaml
# Generated by startd8 observability artifact generator

manifest_id: observability-artifacts
version: "1.0.0"
project_id: online-boutique
generated_at: "2026-03-20T14:30:00Z"
source:
  onboarding_metadata: pipeline-output/run-084/onboarding-metadata.json
  manifest: .contextcore.yaml

summary:
  services_processed: 5
  services_skipped: 0
  artifacts_generated: 15
  artifacts_skipped: 0
  artifacts_errored: 0

artifacts:
  - type: alert_rule
    service: checkout-api
    path: alerts/checkout-api-alerts.yaml
    status: generated
  - type: dashboard_spec
    service: checkout-api
    path: dashboards/checkout-api-dashboard-spec.yaml
    status: generated
  - type: slo_definition
    service: checkout-api
    path: slos/checkout-api-slo.yaml
    status: generated
  # ... repeated for each service

derivation_rules:
  - field: alert_severity
    source: manifest.spec.business.criticality
    transformation: "high → critical"
    tier: manifest
    applied_to: [checkout-api, payment-api, shipping-api]
  - field: latency_threshold
    source: manifest.spec.requirements.latencyP99
    transformation: "500ms → 0.5s"
    tier: manifest
    applied_to: [checkout-api, payment-api]
  - field: availability_threshold
    source: _DEFAULT_THRESHOLDS.availability
    transformation: "99 → 0.99"
    tier: default
    applied_to: [email-service]
```

### Tests (Phase 5)

| Test | Validates |
|------|-----------|
| `test_orchestrator_happy_path` | 2 services → 6 artifacts + index file |
| `test_orchestrator_no_services` | Empty hints → 0 artifacts, warning logged |
| `test_orchestrator_dry_run` | dry_run=True → no files written |
| `test_orchestrator_partial_failure` | 1 service errors → other services still generated |
| `test_index_file_structure` | Index YAML has expected sections |
| `test_index_derivation_rules_deduped` | Same derivation applied to 3 services → single entry with applied_to list |
| `test_output_directory_structure` | alerts/, dashboards/, slos/ subdirs created |

**Deliverable**: End-to-end generation from inputs to files on disk.

---

## Phase 6: CLI Script + Drift Detection

**Goal**: Create the CLI entry point with argparse and `--check` mode.

**Covers**: REQ-UOM-002, REQ-UOM-060, REQ-UOM-061

### 6.1 Create `scripts/generate_observability_artifacts.py`

```python
#!/usr/bin/env python3
"""Generate observability artifacts from ContextCore onboarding metadata.

Usage:
  # Generate artifacts
  python3 scripts/generate_observability_artifacts.py \
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \
      --output-dir pipeline-output/run-084/observability

  # Generate with manifest for direct SLO reads
  python3 scripts/generate_observability_artifacts.py \
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \
      --manifest .contextcore.yaml \
      --output-dir pipeline-output/run-084/observability

  # Drift detection
  python3 scripts/generate_observability_artifacts.py \
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \
      --output-dir pipeline-output/run-084/observability \
      --check

  # Dry run
  python3 scripts/generate_observability_artifacts.py \
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \
      --output-dir pipeline-output/run-084/observability \
      --dry-run
"""

import argparse
import sys
from pathlib import Path

from startd8.observability.artifact_generator import (
    generate_observability_artifacts,
    check_drift,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate observability artifacts from ContextCore onboarding metadata"
    )
    parser.add_argument(
        "--onboarding-metadata",
        required=True,
        help="Path to onboarding-metadata.json from cap-dev-pipe Stage 4 EXPORT",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to .contextcore.yaml for direct SLO/criticality reads (optional)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for generated artifacts",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift against previously generated artifacts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be generated without writing files",
    )
    args = parser.parse_args()

    onboarding = Path(args.onboarding_metadata)
    output = Path(args.output_dir)
    manifest = Path(args.manifest) if args.manifest else None

    if args.check:
        return check_drift(onboarding, output, manifest)

    report = generate_observability_artifacts(
        onboarding_metadata_path=onboarding,
        output_dir=output,
        manifest_path=manifest,
        dry_run=args.dry_run,
    )

    # Print summary
    print(f"Services processed: {report.services_processed}")
    print(f"Services skipped:   {report.services_skipped}")
    generated = sum(1 for a in report.artifacts if a.status == "generated")
    skipped = sum(1 for a in report.artifacts if a.status == "skipped")
    errored = sum(1 for a in report.artifacts if a.status == "error")
    print(f"Artifacts: {generated} generated, {skipped} skipped, {errored} errors")

    return 1 if errored > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
```

### 6.2 Drift detection

```python
def check_drift(
    onboarding_metadata_path: Path,
    output_dir: Path,
    manifest_path: Optional[Path] = None,
) -> int:
    """Compare freshly generated artifacts against existing ones in output_dir.

    Reports at artifact level (REQ-UOM-061):
    - New services (alerts/dashboards/SLOs for services not previously generated)
    - Removed services (previously generated, no longer in hints)
    - Threshold changes (SLO target or alert threshold changed)

    Returns 0 if no drift, 1 if drift detected.
    """
    ...
```

**Drift detection approach**:
1. Load existing `observability-manifest.yaml` from `output_dir`
2. Generate fresh artifacts (in memory, don't write)
3. Compare artifact lists by `(artifact_type, service_id)` key
4. For matching pairs, compare threshold values from derivation traces
5. Report additions, removals, and changes

### Tests (Phase 6)

| Test | Validates |
|------|-----------|
| `test_cli_happy_path` | Script runs, returns 0, creates files |
| `test_cli_missing_onboarding` | Returns non-zero with error message |
| `test_cli_dry_run` | No files written, summary printed |
| `test_cli_check_no_drift` | Returns 0 when artifacts match |
| `test_cli_check_new_service` | Returns 1, reports new service |
| `test_cli_check_removed_service` | Returns 1, reports removed service |
| `test_cli_check_threshold_change` | Returns 1, reports threshold change |

**Deliverable**: CLI script with --check, --dry-run, and normal generation modes.

---

## Phase 7: Pipeline Integration

**Goal**: Wire the generator into the cap-dev-pipe wrapper script.

**Covers**: REQ-UOM-050, REQ-UOM-051, REQ-UOM-052

### 7.1 Modify `.cap-dev-pipe/startd8-sdk-cap-dlv-pipe.sh`

Add after the EXPORT stage call and before plan ingestion:

```bash
# --- Stage 4.5: OBSERVABILITY ARTIFACTS (optional) ---
if [[ "${SKIP_OBSERVABILITY:-false}" != "true" ]]; then
    echo "--- Stage 4.5: Generate observability artifacts ---"
    _OBS_ONBOARDING="$_OUTPUT_DIR/onboarding-metadata.json"
    _OBS_MANIFEST="$_OUTPUT_DIR/.contextcore.yaml"
    _OBS_OUTPUT="$_OUTPUT_DIR/observability"

    if [[ -f "$_OBS_ONBOARDING" ]]; then
        python3 scripts/generate_observability_artifacts.py \
            --onboarding-metadata "$_OBS_ONBOARDING" \
            --manifest "$_OBS_MANIFEST" \
            --output-dir "$_OBS_OUTPUT" || {
            echo "WARNING: Observability artifact generation failed (non-fatal)"
        }
    else
        echo "SKIP: No onboarding-metadata.json found"
    fi
fi
```

**Design decisions**:
- Non-fatal: Failure produces a warning, doesn't block the pipeline
- Skippable: `SKIP_OBSERVABILITY=true` env var to bypass
- Uses existing output directory convention
- Reads files already produced by EXPORT stage

### 7.2 Provenance extension (REQ-UOM-052)

If `observability-manifest.yaml` was successfully generated, append its path to `run-provenance.json`:

```python
# In generate_observability_artifacts(), after writing index:
_append_to_provenance(
    provenance_path=output_dir.parent / "run-provenance.json",
    artifact_id="observability-manifest",
    artifact_path=str(output_dir / "observability-manifest.yaml"),
    stage="4.5",
    role="observability-artifacts-index",
)
```

This is a best-effort append — if `run-provenance.json` doesn't exist or can't be modified, log a warning and continue.

### Tests (Phase 7)

Pipeline integration is validated manually against a real cap-dev-pipe run. No automated test for the shell script modification, but the Python `_append_to_provenance` function gets a unit test:

| Test | Validates |
|------|-----------|
| `test_append_to_provenance_happy_path` | Appends entry to existing provenance JSON |
| `test_append_to_provenance_missing_file` | Logs warning, doesn't fail |

**Deliverable**: Pipeline runs end-to-end with observability artifact generation between EXPORT and INGESTION.

---

## Phase Dependency Graph

```
Phase 1: Input Loading + Data Models
    │
    ├──→ Phase 2: Alert Rule Generation
    │
    ├──→ Phase 3: Dashboard Spec Generation
    │
    └──→ Phase 4: SLO Definition Generation
              │
              ▼
         Phase 5: Orchestration + Index File
              │
              ▼
         Phase 6: CLI Script + Drift Detection
              │
              ▼
         Phase 7: Pipeline Integration
```

Phases 2, 3, 4 are independent and can be implemented in parallel after Phase 1.

---

## Validation Criteria

### Per-Phase Exit Criteria

| Phase | Exit Criteria |
|-------|---------------|
| 1 | Input loading tests pass. ServiceHints and BusinessContext correctly extracted from real onboarding-metadata.json structure. |
| 2 | Alert YAML files parse as valid YAML. PromQL expressions are syntactically correct. Derivation traces present. |
| 3 | DashboardSpec YAML loads into existing `DashboardSpec` Pydantic model without validation errors. |
| 4 | SLO YAML parses as valid YAML. Conforms to OpenSLO v1 shape. |
| 5 | End-to-end: 2+ services → 6+ artifact files + 1 index file in correct directory structure. |
| 6 | CLI script: `--check` returns 0 when re-run against own output. `--dry-run` writes no files. |
| 7 | Cap-dev-pipe wrapper runs without error. `observability/` directory appears in pipeline output. |

### Integration Validation

After all phases, validate against real pipeline output:
1. Run `contextcore manifest export` on a project with services (e.g., online-boutique)
2. Run `generate_observability_artifacts.py` against the export output
3. Verify: alert rules reference correct convention metrics for each service's protocol
4. Verify: dashboard specs load into DashboardCreatorWorkflow without error
5. Verify: SLO definitions have correct targets from manifest requirements
6. Run `--check` mode against the output (should return 0)
7. Modify a manifest SLO threshold, regenerate, run `--check` (should return 1 with specific change reported)

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| `onboarding-metadata.json` schema changes in ContextCore | Read only 3 fields (instrumentation_hints, service_communication_graph, derivation_rules). Defensive `.get()` access. |
| DashboardSpec model changes in SDK | Phase 3 test loads generated YAML into model — catches incompatibility at test time. |
| Convention metric names change in OTel spec | Metric names come from ContextCore's `_PROTOCOL_METRICS` table, not hardcoded here. We consume whatever hints provide. |
| PromQL syntax errors in generated queries | Phase 2/3 tests include PromQL syntax validation (balanced braces, valid function names). |
| Pipeline wrapper script has diverged from symlinked canonical | Modify via the symlink target (`~/Documents/dev/cap-dev-pipe/`), not the local copy. |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}` for plan).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-29

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-29 (UTC)
- **Scope**: Plan review driven by `OBSERVABILITY_GENERATION_GAP_ANALYSIS.md` (run `run-003-20260528T2314`). Maps the gap findings to concrete plan tasks. Pairs with REQUIREMENTS R1-F1..R1-F4. Gap 5 (gridPos autofix inert) is a plain implementation bug with no FR — captured as plan task R1-S5.

**Executive summary**

- The Implementation Sequence (steps 2–4) sources artifacts from **convention metrics only** ("Build `DashboardSpec` from convention metrics per service"). No step reads `manifest_declared` — so the plan, as written, would reproduce the run-003 boilerplate even if executed perfectly. Needs an explicit task (R1-S1) implementing REQUIREMENTS R1-F1.
- No plan task implements a semantic/coverage score; the only quality surface is structural validation. R1-S2 adds it.
- No plan task reconciles the generated index against the declared 8-type contract; the index reports clean success. R1-S3 adds the honest-skip reporting.
- The Risk Mitigation table *names* a "Phase 3 test loads generated YAML into model" but no task makes it an executable acceptance gate, and the spec-vs-Grafana-JSON contract drift is untracked. R1-S4 tasks it.
- The gridPos autofix is wired (`artifact_generator.py:1121–1134`, `autofix=True`) but inert: run-003's `observability-quality.json` shows `OBS-100h` present with `repairs_applied: []`. Plain bug → R1-S5.

**Numbered suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add a task: extend `extract_service_hints` (`artifact_generator.py:226–283`) to carry `manifest_declared` metrics on `ServiceHints` (alongside `convention_metrics`), and extend `generate_dashboard_spec` / `generate_alert_rules` / `generate_slo_definitions` to emit panels/alerts/SLIs from them. Amend Implementation Sequence steps 2–4 from "convention metrics" to "convention + declared metrics." | Implements REQUIREMENTS R1-F1 — the single highest-leverage fix. Today line 256 reads only `convention_based`; this is the seam. Without changing the plan's "convention metrics" wording the implementer will faithfully reproduce the blind spot. | Implementation Sequence steps 2–4; new task in the phase decomposition | Unit test on the extended extractor: `ServiceHints.declared_metrics` populated from a fixture; generator output references them. End-to-end: re-run on `run-003` metadata → dashboard contains `startd8_cost_total`. |
| R1-S2 | Validation | high | Add a task implementing a **metric-coverage scorer** in `validators/observability_artifact_checks.py` (or a sibling) and wiring it into `_write_quality_report`: compute referenced-vs-available metric ratio per service, emit `metric_coverage_score`, fold into composite. | Implements REQUIREMENTS R1-F2. The validator currently scores structure only (OBS-100/101/200/710). A new dimension is needed so the score reflects relevance. | New task after the artifact-generation phase | Regression proof: scorer run on the **current** run-003 artifacts yields low metric coverage (≈0.23); post-R1-S1 run yields high coverage. |
| R1-S3 | Ops | medium | Add a task to `_write_index` / `_write_quality_report` (`artifact_generator.py:1378+`) that reads the onboarding metadata's declared `artifact_types` and emits a `status: skipped` artifact entry (with `reason`) for each declared type the triplet generator does not produce; update `summary.artifacts_skipped` accordingly. | Implements REQUIREMENTS R1-F3. Preserves the §7 Non-Goal (no new generators) while ending the clean-success-on-3/8 reporting. The data is already in the metadata (`artifact_types`, `coverage.gaps`). | New task in the index/reporting step (Sequence step 5) | Test: onboarding metadata with 8 declared `artifact_types` → manifest shows 5 `skipped` entries; `artifacts_skipped == 5`. |
| R1-S4 | Validation | medium | Promote the Risk-table line "Phase 3 test loads generated YAML into model" into an explicit task: a round-trip test that loads each generated `*-dashboard-spec.yaml` into `dashboard_creator/models.py:DashboardSpec` and asserts zero validation errors; plus a doc note reconciling the spec-YAML output path with the onboarding contract's declared Grafana-JSON path and the `/dbrd-cr8r` hand-off. | Implements REQUIREMENTS R1-F4. A risk-table sentence is not a test; the contract drift (YAML spec vs declared `grafana/dashboards/{target}-dashboard.json`) is currently unowned. | Phase 3 testing section; Risk Mitigation row upgraded to a task | `DashboardSpec`-parse test green on a generated artifact; note committed under `docs/design/notes/`. |
| R1-S5 | Risks | low | Add a bug-fix task: the gridPos autofix (`artifact_generator.py:1121–1134`, `validators/...repair_gridpos`) runs with `autofix=True` but does not take effect — run-003 shows `OBS-100h` present and `repairs_applied: []`. Verify `repair_gridpos` mutates the parsed spec and that re-validation runs on the repaired content; populate `repairs_applied`. | Plain implementation bug, no FR needed. Currently every generated dashboard ships without panel layout despite a repair existing. | New hardening task (or fold into R1-S1's dashboard work) | Regression: a regenerated dashboard has `gridPos` on every panel and `OBS-100h` no longer appears; `repairs_applied` non-empty when a fix is made. |

**Endorsements**: (none — R1 is the first round.)

**Disagreements**: (none — first round.)

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement section in `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` to plan step(s)/task(s) and assesses coverage **as of pre-R1-triage** (i.e., what the plan covers today). Gaps are linked to the closing suggestion ID.

| Requirement Section | Plan Step(s) / Task(s) | Coverage | Gap / Closing Suggestion |
| ---- | ---- | ---- | ---- |
| §6.1 Core artifact generator script | Impl Sequence 1 (wire inputs) | Full | — |
| §6.2 Alert rule generation | Impl Sequence 2 | **Partial** | Convention-only; declared metrics not alerted → **R1-S1** (FR R1-F1) |
| §6.3 Dashboard spec generation | Impl Sequence 3 | **Partial** | "from convention metrics" only; declared metrics + `dashboard_hints` unused → **R1-S1** (FR R1-F1). Output-format/`DashboardSpec` round-trip unbound → **R1-S4** (FR R1-F4) |
| §6.4 SLO definition generation | Impl Sequence 4 | **Partial** | Convention-only; declared user-facing metrics get no SLI → **R1-S1** (FR R1-F1) |
| §6.5 Derivation traceability | Derivation-rule tracing (manifest headers) | Full | — (works; verified in run-003 provenance) |
| §6.6 Pipeline integration | Impl Sequence 7 | Full | — |
| §6.7 Drift detection | Impl Sequence 6 (`--check`) | Full | — |
| §6.8 Graceful degradation | Skip/empty handling | **Partial** | No reconciliation against declared 8-type contract; index reports clean success on 3/8 → **R1-S3** (FR R1-F3) |
| §Part 3 "dashboard_hints … missing link" | (none) | **Gap** | Declared-metric consumption has zero plan task → **R1-S1** (FR R1-F1) |
| Quality scoring (validators) | Structural checks (OBS-100/101/200/710) | **Partial** | Structural only; no semantic/metric-coverage dimension → **R1-S2** (FR R1-F2) |
| gridPos autofix correctness | Risk table (implied) | **Gap (bug)** | Autofix inert in run-003 → **R1-S5** (no FR; plain bug) |
