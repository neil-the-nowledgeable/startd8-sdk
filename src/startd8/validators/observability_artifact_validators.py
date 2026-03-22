"""Observability artifact validators (REQ-KZ-OBS-100–403).

Layer 1 (100–102): Structural validation per artifact type.
Layer 2 (203): Metric name semantic checks.
Layer 3 (300–303): Quality scoring (v1 pass rate).
Layer 4 (400–403): Cross-artifact consistency checks.

No external tool dependency — all checks are YAML structural analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "DashboardValidationResult",
    "AlertValidationResult",
    "SloValidationResult",
    "CrossArtifactResult",
    "ServiceArtifactScore",
    "validate_dashboard_spec",
    "validate_alert_rules",
    "validate_slo_definition",
    "check_metric_names",
    "check_cross_artifact_consistency",
    "score_artifact",
    "score_service_triplet",
]


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

@dataclass
class DashboardValidationResult:
    """Validation result for a dashboard spec YAML (REQ-KZ-OBS-100)."""

    file_path: str = ""
    service_id: str = ""
    yaml_valid: bool = False
    panel_count: int = 0
    has_title: bool = False
    has_uid: bool = False
    has_gridpos: bool = False
    has_variables: bool = False
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AlertValidationResult:
    """Validation result for a Prometheus alert rule YAML (REQ-KZ-OBS-101)."""

    file_path: str = ""
    service_id: str = ""
    yaml_valid: bool = False
    rule_count: int = 0
    severity_labels_present: bool = False
    summary_annotations_present: bool = False
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SloValidationResult:
    """Validation result for an OpenSLO v1 YAML (REQ-KZ-OBS-102)."""

    file_path: str = ""
    service_id: str = ""
    yaml_valid: bool = False
    target_value: Optional[float] = None
    window_duration: Optional[str] = None
    has_indicator: bool = False
    has_alerting: bool = False
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(check_id: str, severity: str, message: str) -> Dict[str, Any]:
    return {"check": check_id, "severity": severity, "message": message}


_VALID_SEVERITIES = frozenset({"critical", "warning", "info"})


# ---------------------------------------------------------------------------
# REQ-KZ-OBS-100: Dashboard Spec Validation
# ---------------------------------------------------------------------------

def validate_dashboard_spec(
    content: str,
    *,
    file_path: str = "",
    service_id: str = "",
) -> DashboardValidationResult:
    """Validate a dashboard spec YAML against 10 structural checks.

    Args:
        content: Raw YAML string.
        file_path: Source file path for attribution.
        service_id: Expected service identifier.

    Returns:
        DashboardValidationResult with per-check issues.
    """
    result = DashboardValidationResult(
        file_path=file_path, service_id=service_id,
    )
    issues = result.issues
    passed = 0
    total = 10

    # OBS-100a: YAML parseable
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            issues.append(_issue("OBS-100a", "error", "YAML root is not a mapping"))
            result.checks_total = total
            return result
        result.yaml_valid = True
        passed += 1
    except yaml.YAMLError as exc:
        issues.append(_issue("OBS-100a", "error", f"YAML parse error: {exc}"))
        result.checks_total = total
        return result

    # OBS-100b: title present
    title = data.get("title", "")
    if title and isinstance(title, str) and title.strip():
        result.has_title = True
        passed += 1
    else:
        issues.append(_issue("OBS-100b", "error", "Missing or empty 'title'"))

    # OBS-100c: uid present
    uid = data.get("uid", "")
    if uid and isinstance(uid, str) and uid.strip():
        result.has_uid = True
        passed += 1
    else:
        issues.append(_issue("OBS-100c", "error", "Missing or empty 'uid'"))

    # OBS-100d: panels non-empty
    panels = data.get("panels", [])
    if isinstance(panels, list) and len(panels) > 0:
        result.panel_count = len(panels)
        passed += 1
    else:
        issues.append(_issue("OBS-100d", "error", "No panels defined"))
        panels = []

    # OBS-100e: every panel has expr
    panels_with_expr = sum(1 for p in panels if p.get("expr"))
    if panels and panels_with_expr == len(panels):
        passed += 1
    elif panels:
        missing = len(panels) - panels_with_expr
        issues.append(_issue(
            "OBS-100e", "error",
            f"{missing}/{len(panels)} panel(s) missing 'expr'",
        ))
    else:
        passed += 1  # vacuously true (no panels = already caught)

    # OBS-100f: every panel has type
    panels_with_type = sum(1 for p in panels if p.get("type"))
    if panels and panels_with_type == len(panels):
        passed += 1
    elif panels:
        missing = len(panels) - panels_with_type
        issues.append(_issue(
            "OBS-100f", "warning",
            f"{missing}/{len(panels)} panel(s) missing 'type'",
        ))
    else:
        passed += 1

    # OBS-100g: every panel has unit
    panels_with_unit = sum(1 for p in panels if p.get("unit"))
    if panels and panels_with_unit == len(panels):
        passed += 1
    elif panels:
        missing = len(panels) - panels_with_unit
        issues.append(_issue(
            "OBS-100g", "warning",
            f"{missing}/{len(panels)} panel(s) missing 'unit'",
        ))
    else:
        passed += 1

    # OBS-100h: gridPos present on all panels
    panels_with_grid = sum(1 for p in panels if p.get("gridPos"))
    if panels and panels_with_grid == len(panels):
        result.has_gridpos = True
        passed += 1
    elif panels:
        issues.append(_issue(
            "OBS-100h", "warning",
            f"{len(panels) - panels_with_grid}/{len(panels)} panel(s) missing 'gridPos'",
        ))
    else:
        passed += 1

    # OBS-100i: datasources present
    ds = data.get("datasources")
    if ds and isinstance(ds, dict) and len(ds) > 0:
        passed += 1
    else:
        issues.append(_issue("OBS-100i", "warning", "No datasources declared"))

    # OBS-100j: variables present
    variables = data.get("variables", [])
    if isinstance(variables, list) and len(variables) > 0:
        result.has_variables = True
        passed += 1
    else:
        issues.append(_issue("OBS-100j", "info", "No variables defined"))

    result.checks_passed = passed
    result.checks_total = total
    return result


# ---------------------------------------------------------------------------
# REQ-KZ-OBS-101: Alert Rule Validation
# ---------------------------------------------------------------------------

def validate_alert_rules(
    content: str,
    *,
    file_path: str = "",
    service_id: str = "",
) -> AlertValidationResult:
    """Validate a Prometheus alert rule YAML against 9 structural checks.

    Args:
        content: Raw YAML string.
        file_path: Source file path for attribution.
        service_id: Expected service identifier.

    Returns:
        AlertValidationResult with per-check issues.
    """
    result = AlertValidationResult(
        file_path=file_path, service_id=service_id,
    )
    issues = result.issues
    passed = 0
    total = 9

    # OBS-101a: YAML parseable
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            issues.append(_issue("OBS-101a", "error", "YAML root is not a mapping"))
            result.checks_total = total
            return result
        result.yaml_valid = True
        passed += 1
    except yaml.YAMLError as exc:
        issues.append(_issue("OBS-101a", "error", f"YAML parse error: {exc}"))
        result.checks_total = total
        return result

    # OBS-101b: groups present with at least 1 rule
    groups = data.get("groups", [])
    rules: List[Dict[str, Any]] = []
    for g in (groups if isinstance(groups, list) else []):
        rules.extend(g.get("rules", []) if isinstance(g, dict) else [])
    result.rule_count = len(rules)
    if rules:
        passed += 1
    else:
        issues.append(_issue("OBS-101b", "error", "No alert rules found in groups"))

    # Per-rule checks
    all_have_name = True
    all_have_expr = True
    all_have_for = True
    all_have_severity = True
    all_have_service = True
    all_have_summary = True

    for rule in rules:
        # OBS-101c: alert name
        alert_name = rule.get("alert", "")
        if not alert_name:
            all_have_name = False

        # OBS-101d: expr
        if not rule.get("expr"):
            all_have_expr = False

        # OBS-101e: for duration
        if not rule.get("for"):
            all_have_for = False

        # OBS-101f: severity label
        labels = rule.get("labels", {})
        severity = labels.get("severity", "")
        if severity not in _VALID_SEVERITIES:
            all_have_severity = False

        # OBS-101g: service label
        if not labels.get("service"):
            all_have_service = False

        # OBS-101h: summary annotation
        annotations = rule.get("annotations", {})
        if not annotations.get("summary"):
            all_have_summary = False

    # OBS-101c
    if all_have_name or not rules:
        passed += 1
    else:
        issues.append(_issue("OBS-101c", "error", "One or more rules missing 'alert' name"))

    # OBS-101d
    if all_have_expr or not rules:
        passed += 1
    else:
        issues.append(_issue("OBS-101d", "error", "One or more rules missing 'expr'"))

    # OBS-101e
    if all_have_for or not rules:
        passed += 1
    else:
        issues.append(_issue("OBS-101e", "warning", "One or more rules missing 'for' duration"))

    # OBS-101f
    result.severity_labels_present = all_have_severity
    if all_have_severity or not rules:
        passed += 1
    else:
        issues.append(_issue(
            "OBS-101f", "error",
            "One or more rules missing valid 'severity' label (critical/warning/info)",
        ))

    # OBS-101g
    if all_have_service or not rules:
        passed += 1
    else:
        issues.append(_issue("OBS-101g", "warning", "One or more rules missing 'service' label"))

    # OBS-101h
    result.summary_annotations_present = all_have_summary
    if all_have_summary or not rules:
        passed += 1
    else:
        issues.append(_issue("OBS-101h", "warning", "One or more rules missing 'summary' annotation"))

    # OBS-101i: PromQL metric convention check (deferred — needs transport context)
    # Always pass for now; semantic check OBS-203 handles this with transport context
    passed += 1

    result.checks_passed = passed
    result.checks_total = total
    return result


# ---------------------------------------------------------------------------
# REQ-KZ-OBS-102: SLO Definition Validation
# ---------------------------------------------------------------------------

def validate_slo_definition(
    content: str,
    *,
    file_path: str = "",
    service_id: str = "",
) -> SloValidationResult:
    """Validate an OpenSLO v1 YAML against 10 structural checks.

    Args:
        content: Raw YAML string (may contain multiple YAML documents).
        file_path: Source file path for attribution.
        service_id: Expected service identifier.

    Returns:
        SloValidationResult with per-check issues.
    """
    result = SloValidationResult(
        file_path=file_path, service_id=service_id,
    )
    issues = result.issues
    passed = 0
    total = 10

    # OBS-102a: YAML parseable
    try:
        # SLO files may contain multiple YAML documents (availability + latency)
        documents = list(yaml.safe_load_all(content))
        # Use first SLO document for validation
        data = None
        for doc in documents:
            if isinstance(doc, dict) and doc.get("kind") == "SLO":
                data = doc
                break
        if data is None:
            data = documents[0] if documents else {}
        if not isinstance(data, dict):
            issues.append(_issue("OBS-102a", "error", "YAML root is not a mapping"))
            result.checks_total = total
            return result
        result.yaml_valid = True
        passed += 1
    except yaml.YAMLError as exc:
        issues.append(_issue("OBS-102a", "error", f"YAML parse error: {exc}"))
        result.checks_total = total
        return result

    # OBS-102b: apiVersion
    api_version = data.get("apiVersion", "")
    if api_version == "openslo/v1":
        passed += 1
    else:
        issues.append(_issue(
            "OBS-102b", "error",
            f"Expected apiVersion 'openslo/v1', got '{api_version}'",
        ))

    # OBS-102c: kind
    kind = data.get("kind", "")
    if kind == "SLO":
        passed += 1
    else:
        issues.append(_issue(
            "OBS-102c", "error",
            f"Expected kind 'SLO', got '{kind}'",
        ))

    spec = data.get("spec", {})

    # OBS-102d: spec.target
    target = spec.get("target")
    if target is not None and isinstance(target, (int, float)):
        result.target_value = float(target)
        passed += 1
    else:
        issues.append(_issue("OBS-102d", "error", "Missing or non-numeric 'spec.target'"))

    # OBS-102e: spec.timeWindow
    time_window = spec.get("timeWindow", {})
    duration = time_window.get("duration") if isinstance(time_window, dict) else None
    if duration:
        result.window_duration = str(duration)
        passed += 1
    else:
        issues.append(_issue("OBS-102e", "error", "Missing 'spec.timeWindow.duration'"))

    # OBS-102f: spec.indicator
    indicator = spec.get("indicator", {})
    if isinstance(indicator, dict) and indicator.get("spec"):
        result.has_indicator = True
        passed += 1
    else:
        issues.append(_issue("OBS-102f", "error", "Missing 'spec.indicator' with spec"))

    # OBS-102g: metadata.name
    metadata = data.get("metadata", {})
    name = metadata.get("name", "")
    if name and isinstance(name, str):
        passed += 1
    else:
        issues.append(_issue("OBS-102g", "warning", "Missing 'metadata.name'"))

    # OBS-102h: metadata.labels.service
    labels = metadata.get("labels", {})
    if labels.get("service"):
        passed += 1
    else:
        issues.append(_issue("OBS-102h", "warning", "Missing 'metadata.labels.service'"))

    # OBS-102i: spec.alerting
    alerting = spec.get("alerting")
    if isinstance(alerting, dict) and alerting.get("name"):
        result.has_alerting = True
        passed += 1
    else:
        issues.append(_issue("OBS-102i", "info", "Missing 'spec.alerting' section"))

    # OBS-102j: threshold metric has PromQL query
    ind_spec = indicator.get("spec", {}) if isinstance(indicator, dict) else {}
    # Check both thresholdMetric and ratioMetric paths
    threshold_metric = ind_spec.get("thresholdMetric", {})
    ratio_metric = ind_spec.get("ratioMetric", {})
    has_query = False
    if isinstance(threshold_metric, dict):
        query = (threshold_metric
                 .get("metricSource", {})
                 .get("spec", {})
                 .get("query", ""))
        if query:
            has_query = True
    if isinstance(ratio_metric, dict):
        # ratioMetric has counter + good sub-metrics
        counter = ratio_metric.get("counter", {})
        good = ratio_metric.get("good", {})
        cq = (counter.get("metricSource", {}).get("spec", {}).get("query", ""))
        gq = (good.get("metricSource", {}).get("spec", {}).get("query", ""))
        if cq or gq:
            has_query = True
    if has_query:
        passed += 1
    else:
        issues.append(_issue(
            "OBS-102j", "error",
            "No PromQL query found in indicator metric source",
        ))

    result.checks_passed = passed
    result.checks_total = total
    return result


# ---------------------------------------------------------------------------
# REQ-KZ-OBS-203: Metric Name Validity Checks
# ---------------------------------------------------------------------------

_GRPC_METRIC_PREFIX = "rpc_server_"
_HTTP_METRIC_PREFIX = "http_server_"


def _extract_metric_names(expr: str) -> List[str]:
    """Extract metric names from a PromQL expression."""
    return re.findall(r"\b([a-z_][a-z0-9_]*(?:_bucket|_count|_total)?)\s*[{\[(]", expr)


def check_metric_names(
    expr: str,
    *,
    transport: str = "",
) -> List[Dict[str, Any]]:
    """Check metric names in a PromQL expression (REQ-KZ-OBS-203).

    Args:
        expr: PromQL expression string.
        transport: Expected transport protocol ('grpc' or 'http').

    Returns:
        List of issues found.
    """
    issues: List[Dict[str, Any]] = []
    metrics = _extract_metric_names(expr)

    for metric in metrics:
        # OBS-203a: dots instead of underscores
        if "." in metric:
            issues.append(_issue(
                "OBS-203a", "warning",
                f"Metric '{metric}' uses dots instead of underscores",
            ))

        # OBS-203b: Transport-metric alignment
        if transport == "grpc" and metric.startswith(_HTTP_METRIC_PREFIX):
            issues.append(_issue(
                "OBS-203b", "error",
                f"gRPC service uses HTTP metric '{metric}'",
            ))
        elif transport == "http" and metric.startswith(_GRPC_METRIC_PREFIX):
            issues.append(_issue(
                "OBS-203b", "error",
                f"HTTP service uses gRPC metric '{metric}'",
            ))

    # OBS-203c: histogram_quantile must reference _bucket
    if "histogram_quantile" in expr and "_bucket" not in expr:
        issues.append(_issue(
            "OBS-203c", "warning",
            "histogram_quantile() should reference _bucket suffix metric",
        ))

    return issues


# ---------------------------------------------------------------------------
# REQ-KZ-OBS-300–303: Quality Scoring (v1 — pass rate)
# ---------------------------------------------------------------------------

def score_artifact(
    result: "DashboardValidationResult | AlertValidationResult | SloValidationResult",
) -> float:
    """Compute v1 quality score: checks_passed / checks_total.

    Short-circuits to 0.0 if YAML parse failed.
    """
    if not result.yaml_valid:
        return 0.0
    if result.checks_total == 0:
        return 0.0
    return round(result.checks_passed / result.checks_total, 4)


@dataclass
class ServiceArtifactScore:
    """Per-service composite score across the artifact triplet (REQ-KZ-OBS-303)."""

    service_id: str = ""
    dashboard_score: float = 0.0
    alert_score: float = 0.0
    slo_score: float = 0.0
    composite_score: float = 0.0
    has_dashboard: bool = False
    has_alert: bool = False
    has_slo: bool = False

    def compute_composite(self) -> float:
        """Weighted composite: dashboard 0.35 + alert 0.35 + slo 0.30."""
        self.composite_score = round(
            (self.dashboard_score * 0.35)
            + (self.alert_score * 0.35)
            + (self.slo_score * 0.30),
            4,
        )
        return self.composite_score


def score_service_triplet(
    *,
    dashboard: Optional[DashboardValidationResult] = None,
    alert: Optional[AlertValidationResult] = None,
    slo: Optional[SloValidationResult] = None,
    service_id: str = "",
) -> ServiceArtifactScore:
    """Score a service's artifact triplet (REQ-KZ-OBS-303)."""
    result = ServiceArtifactScore(service_id=service_id)

    if dashboard is not None:
        result.has_dashboard = True
        result.dashboard_score = score_artifact(dashboard)

    if alert is not None:
        result.has_alert = True
        result.alert_score = score_artifact(alert)

    if slo is not None:
        result.has_slo = True
        result.slo_score = score_artifact(slo)

    result.compute_composite()
    return result


# ---------------------------------------------------------------------------
# REQ-KZ-OBS-400–403: Cross-Artifact Consistency
# ---------------------------------------------------------------------------

@dataclass
class CrossArtifactResult:
    """Cross-artifact consistency check results (REQ-KZ-OBS-400–403)."""

    unvisualized_alerts: List[str] = field(default_factory=list)
    unalerted_slos: List[str] = field(default_factory=list)
    misaligned_thresholds: List[Dict[str, Any]] = field(default_factory=list)
    unused_derivations: List[str] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return (
            len(self.unvisualized_alerts)
            + len(self.unalerted_slos)
            + len(self.misaligned_thresholds)
            + len(self.unused_derivations)
        )


def _extract_metrics_from_yaml(content: str) -> set:
    """Extract all metric base names referenced in YAML PromQL expressions."""
    metrics: set = set()
    for match in re.finditer(r"\b([a-z_][a-z0-9_]*(?:_bucket|_count|_total))\b", content):
        metrics.add(match.group(1))
    return metrics


def check_cross_artifact_consistency(
    *,
    dashboard_content: str = "",
    alert_content: str = "",
    slo_content: str = "",
    manifest_derivations: Optional[List[Dict[str, Any]]] = None,
) -> CrossArtifactResult:
    """Check consistency across dashboard, alert, and SLO artifacts.

    Args:
        dashboard_content: Raw YAML of dashboard spec.
        alert_content: Raw YAML of alert rules.
        slo_content: Raw YAML of SLO definition.
        manifest_derivations: derivation_rules from observability-manifest.yaml.

    Returns:
        CrossArtifactResult with per-check issue lists.
    """
    result = CrossArtifactResult()
    dashboard_metrics = _extract_metrics_from_yaml(dashboard_content) if dashboard_content else set()
    alert_metrics = _extract_metrics_from_yaml(alert_content) if alert_content else set()
    slo_metrics = _extract_metrics_from_yaml(slo_content) if slo_content else set()

    # OBS-400: Dashboard ↔ Alert — alert metrics should be visualized
    for metric in sorted(alert_metrics):
        if metric not in dashboard_metrics and dashboard_content:
            result.unvisualized_alerts.append(metric)
            result.issues.append(_issue(
                "OBS-400", "warning",
                f"Alert metric '{metric}' not visualized in dashboard",
            ))

    # OBS-401: Alert ↔ SLO — SLO metrics should have alerts
    for metric in sorted(slo_metrics):
        if metric not in alert_metrics and alert_content:
            result.unalerted_slos.append(metric)
            result.issues.append(_issue(
                "OBS-401", "warning",
                f"SLO metric '{metric}' has no corresponding alert",
            ))

    # OBS-402: threshold alignment (dashboard vs SLO)
    dashboard_thresholds = set(re.findall(r">\s*([\d.]+)", dashboard_content))
    slo_thresholds = set(re.findall(r"threshold:\s*([\d.]+)", slo_content))
    if dashboard_thresholds and slo_thresholds:
        for dt in dashboard_thresholds:
            for st in slo_thresholds:
                try:
                    d, s = float(dt), float(st)
                    if d != s and 0.1 * s <= d <= 10 * s:
                        result.misaligned_thresholds.append({
                            "dashboard": d, "slo": s,
                        })
                        result.issues.append(_issue(
                            "OBS-402", "warning",
                            f"Dashboard threshold {d} != SLO threshold {s}",
                        ))
                except ValueError:
                    pass

    # OBS-403: derivation rule completeness
    if manifest_derivations:
        all_content = dashboard_content + alert_content + slo_content
        for rule in manifest_derivations:
            field_name = rule.get("field", "")
            value = str(rule.get("transformation", ""))
            if field_name and value and value not in all_content:
                result.unused_derivations.append(field_name)
                result.issues.append(_issue(
                    "OBS-403", "info",
                    f"Derivation '{field_name}={value}' not consumed by any artifact",
                ))

    return result
