"""Observability artifact validation — REQ-KZ-OBS-100–302, 710.

Structural + semantic validation for generated dashboards, alerts, and SLOs.
Each check follows validate-with-autofix: try repair → validate → report.

Pure functions — accept YAML content as strings for retroactive validation
(REQ-KZ-OBS-705a).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "ObservabilityIssue",
    "DashboardValidationResult",
    "AlertValidationResult",
    "SloValidationResult",
    "CrossArtifactResult",
    "validate_dashboard",
    "validate_alerts",
    "validate_slo",
    "validate_cross_artifact_consistency",
    "validate_metric_names",
    "validate_derivation_completeness",
    "repair_gridpos",
    "repair_slo_target",
    "compute_service_composite",
    "has_rate_panel",
    "has_error_panel",
    "has_duration_panel",
    "get_all_panel_exprs",
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservabilityIssue:
    """A single issue found during observability artifact validation."""

    check: str       # e.g. "OBS-100d"
    severity: str    # "error", "warning", "info"
    message: str


@dataclass
class DashboardValidationResult:
    file_path: str
    yaml_valid: bool = False
    panel_count: int = 0
    red_coverage: float = 0.0
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)
    repairs_applied: List[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0


@dataclass
class AlertValidationResult:
    file_path: str
    yaml_valid: bool = False
    rule_count: int = 0
    rule_coverage: float = 0.0
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)
    repairs_applied: List[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0


@dataclass
class SloValidationResult:
    file_path: str
    yaml_valid: bool = False
    target_value: Optional[float] = None
    target_matches_manifest: bool = False
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)
    repairs_applied: List[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0


# ---------------------------------------------------------------------------
# Repair functions (idempotent, called before validation)
# ---------------------------------------------------------------------------


def repair_gridpos(dashboard: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Inject default 2×2 grid layout if panels lack gridPos (OBS-710b)."""
    panels = dashboard.get("panels", [])
    if not panels:
        return dashboard, []

    needs_repair = any("gridPos" not in p for p in panels)
    if not needs_repair:
        return dashboard, []

    w, h = 12, 8  # half-width, standard height
    for i, panel in enumerate(panels):
        if "gridPos" not in panel:
            col = (i % 2) * 12
            row = (i // 2) * h
            panel["gridPos"] = {"h": h, "w": w, "x": col, "y": row}

    logger.info("repair_gridpos: injected gridPos for %d panels", len(panels))
    return dashboard, ["gridpos_injected"]


def repair_slo_target(
    slo: Dict[str, Any],
    manifest_availability: Optional[float],
) -> Tuple[Dict[str, Any], List[str]]:
    """Fix SLO target to match manifest availability (OBS-710a safety net)."""
    if manifest_availability is None:
        return slo, []

    spec = slo.get("spec", {})
    current = spec.get("target")
    if current is not None and abs(float(current) - manifest_availability) > 0.01:
        old = current
        spec["target"] = manifest_availability
        logger.info(
            "repair_slo_target: %s → %s (from manifest)",
            old, manifest_availability,
        )
        return slo, [f"slo_target_{old}_to_{manifest_availability}"]

    return slo, []


def _repair_bucket_suffix(expr: str) -> str:
    """Append _bucket to histogram_quantile metric references if missing."""
    def _fix(m: re.Match) -> str:
        metric = m.group(1)
        if not metric.endswith("_bucket"):
            return m.group(0).replace(metric, metric + "_bucket")
        return m.group(0)

    return re.sub(
        r'histogram_quantile\([^,]+,\s*(?:rate|increase)\((\w+)\{',
        _fix,
        expr,
    )


# ---------------------------------------------------------------------------
# Dashboard validation (REQ-KZ-OBS-100 + OBS-200)
# ---------------------------------------------------------------------------


def validate_dashboard(
    content: str,
    file_path: str = "",
    *,
    autofix: bool = True,
    service_id: str = "",
    transport: Optional[str] = None,
) -> DashboardValidationResult:
    """Validate a dashboard spec YAML against the OBS-100 + OBS-200 checklists."""
    result = DashboardValidationResult(file_path=file_path)
    issues = result.issues
    passed = 0
    total = 0

    # OBS-100a: YAML parseable
    total += 1
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            issues.append(ObservabilityIssue("OBS-100a", "error", "YAML content is not a mapping"))
            result.checks_total = total
            return result
        result.yaml_valid = True
        passed += 1
    except yaml.YAMLError as exc:
        issues.append(ObservabilityIssue("OBS-100a", "error", f"YAML parse error: {exc}"))
        result.checks_total = total
        return result

    # Autofix: gridPos
    if autofix:
        data, repairs = repair_gridpos(data)
        result.repairs_applied.extend(repairs)

    panels = data.get("panels", [])
    result.panel_count = len(panels)

    # OBS-100b: title present
    total += 1
    if data.get("title"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-100b", "error", "Dashboard missing 'title'"))

    # OBS-100c: uid matches obs-{service}
    total += 1
    uid = data.get("uid", "")
    if uid and uid.startswith("obs-"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-100c", "error", f"uid '{uid}' doesn't match obs-{{service}} pattern"))

    # OBS-100d: panels non-empty
    total += 1
    if panels:
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-100d", "error", "Dashboard has no panels"))

    # OBS-100e: each panel has expr
    total += 1
    panels_with_expr = sum(1 for p in panels if _panel_has_expr(p))
    if panels and panels_with_expr == len(panels):
        passed += 1
    elif panels:
        issues.append(ObservabilityIssue(
            "OBS-100e", "error",
            f"{len(panels) - panels_with_expr}/{len(panels)} panels missing PromQL expr",
        ))

    # OBS-100f: panel has type
    total += 1
    panels_with_type = sum(1 for p in panels if p.get("type"))
    if panels and panels_with_type == len(panels):
        passed += 1
    elif panels:
        issues.append(ObservabilityIssue(
            "OBS-100f", "warning",
            f"{len(panels) - panels_with_type}/{len(panels)} panels missing visualization type",
        ))

    # OBS-100g: panel has unit
    total += 1
    panels_with_unit = sum(1 for p in panels if p.get("unit"))
    if panels and panels_with_unit == len(panels):
        passed += 1
    elif panels:
        issues.append(ObservabilityIssue(
            "OBS-100g", "warning",
            f"{len(panels) - panels_with_unit}/{len(panels)} panels missing unit",
        ))

    # OBS-100h: gridPos present (after autofix)
    total += 1
    panels_with_grid = sum(1 for p in panels if p.get("gridPos"))
    if panels and panels_with_grid == len(panels):
        passed += 1
    elif panels:
        issues.append(ObservabilityIssue("OBS-100h", "warning", "Panels missing gridPos"))

    # OBS-100i: datasources
    total += 1
    if data.get("datasources"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-100i", "warning", "No datasources declared"))

    # OBS-100j: variables
    total += 1
    if data.get("variables"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-100j", "info", "No variables declared"))

    # OBS-200a (OBS-710c): RED coverage
    total += 1
    red = _compute_red_coverage(panels)
    result.red_coverage = red
    if red >= 2.0 / 3.0:
        passed += 1
    else:
        missing = []
        if not has_rate_panel(panels):
            missing.append("Rate")
        if not has_error_panel(panels):
            missing.append("Errors")
        if not has_duration_panel(panels):
            missing.append("Duration")
        issues.append(ObservabilityIssue(
            "OBS-200a", "warning",
            f"RED coverage {red:.0%} — missing: {', '.join(missing)}",
        ))

    # OBS-203: Metric name validity
    all_exprs = get_all_panel_exprs(panels)
    metric_issues = validate_metric_names(all_exprs, service_id=service_id, transport=transport)
    for mi in metric_issues:
        total += 1
        issues.append(mi)
    if not metric_issues:
        # All metric checks passed — count as 1 aggregate check
        total += 1
        passed += 1

    result.checks_passed = passed
    result.checks_total = total
    return result


# ---------------------------------------------------------------------------
# Alert validation (REQ-KZ-OBS-101 + OBS-201)
# ---------------------------------------------------------------------------


def validate_alerts(
    content: str,
    file_path: str = "",
    *,
    manifest_availability: Optional[float] = None,
    service_id: str = "",
    transport: Optional[str] = None,
) -> AlertValidationResult:
    """Validate Prometheus alert rule YAML against OBS-101 + OBS-201 checklists."""
    result = AlertValidationResult(file_path=file_path)
    issues = result.issues
    passed = 0
    total = 0

    # OBS-101a: YAML parseable
    total += 1
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            issues.append(ObservabilityIssue("OBS-101a", "error", "YAML content is not a mapping"))
            result.checks_total = total
            return result
        result.yaml_valid = True
        passed += 1
    except yaml.YAMLError as exc:
        issues.append(ObservabilityIssue("OBS-101a", "error", f"YAML parse error: {exc}"))
        result.checks_total = total
        return result

    # Extract rules
    groups = data.get("groups", [])
    rules: List[Dict] = []
    for g in (groups if isinstance(groups, list) else []):
        rules.extend(g.get("rules", []) if isinstance(g, dict) else [])
    result.rule_count = len(rules)

    # OBS-101b: groups with rules
    total += 1
    if rules:
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-101b", "error", "No alert rules found"))

    for rule in rules:
        # OBS-101c: alert name
        total += 1
        name = rule.get("alert", "")
        if name and name[0].isupper():
            passed += 1
        else:
            issues.append(ObservabilityIssue("OBS-101c", "error", f"Rule missing or invalid alert name: '{name}'"))

        # OBS-101d: expr
        total += 1
        if rule.get("expr"):
            passed += 1
        else:
            issues.append(ObservabilityIssue("OBS-101d", "error", f"Rule '{name}' missing expr"))

        # OBS-101e: for duration
        total += 1
        if rule.get("for"):
            passed += 1
        else:
            issues.append(ObservabilityIssue("OBS-101e", "warning", f"Rule '{name}' missing 'for' duration"))

        # OBS-101f: severity label
        total += 1
        labels = rule.get("labels", {})
        severity = labels.get("severity", "")
        if severity in ("critical", "warning", "info"):
            passed += 1
        else:
            issues.append(ObservabilityIssue("OBS-101f", "error", f"Rule '{name}' missing/invalid severity label: '{severity}'"))

        # OBS-101g: service label
        total += 1
        if labels.get("service"):
            passed += 1
        else:
            issues.append(ObservabilityIssue("OBS-101g", "warning", f"Rule '{name}' missing service label"))

        # OBS-101h: summary annotation
        total += 1
        annotations = rule.get("annotations", {})
        if annotations.get("summary"):
            passed += 1
        else:
            issues.append(ObservabilityIssue("OBS-101h", "warning", f"Rule '{name}' missing summary annotation"))

    # OBS-710d: Alert coverage (latency + error_rate + availability)
    total += 1
    expected = 1
    if manifest_availability is not None:
        expected = 3  # latency + error_rate + availability
    result.rule_coverage = min(len(rules), expected) / expected if expected else 1.0
    if result.rule_coverage >= 1.0:
        passed += 1
    else:
        issues.append(ObservabilityIssue(
            "OBS-710d", "warning",
            f"Alert coverage: {len(rules)}/{expected} expected rules (rule_coverage={result.rule_coverage:.2f})",
        ))

    # OBS-203: Metric name validity
    alert_exprs = [str(r.get("expr", "")) for r in rules if r.get("expr")]
    metric_issues = validate_metric_names(alert_exprs, service_id=service_id, transport=transport)
    for mi in metric_issues:
        total += 1
        issues.append(mi)
    if not metric_issues:
        total += 1
        passed += 1

    result.checks_passed = passed
    result.checks_total = total
    return result


# ---------------------------------------------------------------------------
# SLO validation (REQ-KZ-OBS-102 + OBS-202)
# ---------------------------------------------------------------------------


def validate_slo(
    content: str,
    file_path: str = "",
    *,
    manifest_availability: Optional[float] = None,
    autofix: bool = True,
    service_id: str = "",
    transport: Optional[str] = None,
) -> SloValidationResult:
    """Validate OpenSLO v1 YAML against OBS-102 + OBS-202 checklists."""
    result = SloValidationResult(file_path=file_path)
    issues = result.issues
    passed = 0
    total = 0

    # OBS-102a: YAML parseable
    total += 1
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            issues.append(ObservabilityIssue("OBS-102a", "error", "YAML content is not a mapping"))
            result.checks_total = total
            return result
        result.yaml_valid = True
        passed += 1
    except yaml.YAMLError as exc:
        issues.append(ObservabilityIssue("OBS-102a", "error", f"YAML parse error: {exc}"))
        result.checks_total = total
        return result

    # Autofix: SLO target from manifest
    if autofix and manifest_availability is not None:
        data, repairs = repair_slo_target(data, manifest_availability)
        result.repairs_applied.extend(repairs)

    spec = data.get("spec", {})
    metadata = data.get("metadata", {})

    # OBS-102b: apiVersion openslo/v1
    total += 1
    if data.get("apiVersion") == "openslo/v1":
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102b", "error", f"apiVersion: '{data.get('apiVersion')}' (expected 'openslo/v1')"))

    # OBS-102c: kind SLO
    total += 1
    if data.get("kind") == "SLO":
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102c", "error", f"kind: '{data.get('kind')}' (expected 'SLO')"))

    # OBS-102d: spec.target
    total += 1
    target = spec.get("target")
    if target is not None:
        result.target_value = float(target)
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102d", "error", "Missing spec.target"))

    # OBS-102e: spec.timeWindow
    total += 1
    if spec.get("timeWindow"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102e", "error", "Missing spec.timeWindow"))

    # OBS-102f: spec.indicator
    total += 1
    indicator = spec.get("indicator", {})
    ind_spec = indicator.get("spec", {}) if isinstance(indicator, dict) else {}
    if ind_spec.get("thresholdMetric") or ind_spec.get("ratioMetric"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102f", "error", "Missing spec.indicator with threshold/ratio metric"))

    # OBS-102g: metadata.name
    total += 1
    if metadata.get("name"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102g", "warning", "Missing metadata.name"))

    # OBS-102h: metadata.labels.service
    total += 1
    labels = metadata.get("labels", {})
    if labels.get("service"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102h", "warning", "Missing metadata.labels.service"))

    # OBS-102i: spec.alerting
    total += 1
    if spec.get("alerting"):
        passed += 1
    else:
        issues.append(ObservabilityIssue("OBS-102i", "info", "Missing spec.alerting section"))

    # OBS-202a (OBS-710a): target matches manifest
    total += 1
    if manifest_availability is not None and result.target_value is not None:
        if abs(result.target_value - manifest_availability) < 0.01:
            result.target_matches_manifest = True
            passed += 1
        else:
            issues.append(ObservabilityIssue(
                "OBS-202a", "error",
                f"SLO target {result.target_value} doesn't match manifest availability {manifest_availability}",
            ))
    elif manifest_availability is None:
        passed += 1  # can't check — pass by default
    else:
        issues.append(ObservabilityIssue("OBS-202a", "error", "No target to check against manifest"))

    # OBS-203: Metric name validity (check SLO indicator query)
    slo_exprs: List[str] = []
    tm = ind_spec.get("thresholdMetric", {})
    if isinstance(tm, dict):
        ms = tm.get("metricSource", {})
        if isinstance(ms, dict):
            q = ms.get("spec", {}).get("query", "")
            if q:
                slo_exprs.append(str(q))
    metric_issues = validate_metric_names(slo_exprs, service_id=service_id, transport=transport)
    for mi in metric_issues:
        total += 1
        issues.append(mi)
    if not metric_issues:
        total += 1
        passed += 1

    result.checks_passed = passed
    result.checks_total = total
    return result


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------


def compute_service_composite(
    dashboard_score: float,
    alert_score: float,
    slo_score: float,
) -> float:
    """Per-service composite = weighted average (REQ-KZ-OBS-303)."""
    return (dashboard_score * 0.35) + (alert_score * 0.35) + (slo_score * 0.30)


# ---------------------------------------------------------------------------
# Cross-artifact consistency checks (REQ-KZ-OBS-400–403)
# ---------------------------------------------------------------------------


@dataclass
class CrossArtifactResult:
    """Results from cross-artifact consistency validation."""

    unvisualized_alerts: List[str] = field(default_factory=list)
    unalerted_slos: List[str] = field(default_factory=list)
    misaligned_thresholds: List[str] = field(default_factory=list)
    unused_derivations: List[str] = field(default_factory=list)
    consumed_incorrect: List[str] = field(default_factory=list)
    missing_availability_slos: List[str] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return (
            len(self.unvisualized_alerts)
            + len(self.unalerted_slos)
            + len(self.misaligned_thresholds)
            + len(self.unused_derivations)
            + len(self.consumed_incorrect)
            + len(self.missing_availability_slos)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unvisualized_alerts": len(self.unvisualized_alerts),
            "unalerted_slos": len(self.unalerted_slos),
            "misaligned_thresholds": len(self.misaligned_thresholds),
            "unused_derivations": len(self.unused_derivations),
            "missing_availability_slos": len(self.missing_availability_slos),
        }


def validate_cross_artifact_consistency(
    dashboard_content: Optional[str],
    alert_content: Optional[str],
    slo_content: Optional[str],
    service_id: str = "",
    manifest_availability: Optional[float] = None,
) -> CrossArtifactResult:
    """Check consistency across a service's artifact triplet (REQ-KZ-OBS-400–402, OBS-202d).

    Args:
        dashboard_content: Dashboard spec YAML string (or None if missing).
        alert_content: Alert rules YAML string (or None if missing).
        slo_content: SLO definition YAML string (or None if missing).
        service_id: Service identifier for logging.
        manifest_availability: Availability requirement from manifest (e.g. 99.9).
            When set and the SLO content lacks an availability (ratio-based) SLO,
            an OBS-202d warning is emitted.

    Returns:
        CrossArtifactResult with any alignment issues found.
    """
    result = CrossArtifactResult()

    # Parse all available artifacts
    dashboard = _safe_yaml_load(dashboard_content) if dashboard_content else None
    alerts = _safe_yaml_load(alert_content) if alert_content else None
    slo = _safe_yaml_load(slo_content) if slo_content else None

    # Extract metrics from each artifact type
    dashboard_metrics = set()
    if dashboard and isinstance(dashboard, dict):
        for expr in get_all_panel_exprs(dashboard.get("panels", [])):
            dashboard_metrics.update(_extract_metric_names(expr))

    alert_metrics = set()
    alert_rules = []
    if alerts and isinstance(alerts, dict):
        for g in alerts.get("groups", []):
            if isinstance(g, dict):
                for rule in g.get("rules", []):
                    alert_rules.append(rule)
                    expr = rule.get("expr", "")
                    alert_metrics.update(_extract_metric_names(str(expr)))

    slo_metrics = set()
    if slo and isinstance(slo, dict):
        spec = slo.get("spec", {})
        indicator = spec.get("indicator", {})
        if isinstance(indicator, dict):
            ind_spec = indicator.get("spec", {})
            tm = ind_spec.get("thresholdMetric", {})
            if isinstance(tm, dict):
                ms = tm.get("metricSource", {})
                if isinstance(ms, dict):
                    q = ms.get("spec", {}).get("query", "")
                    slo_metrics.update(_extract_metric_names(str(q)))

    # OBS-400: Dashboard ↔ Alert — alert metrics should appear in dashboard
    if dashboard_metrics and alert_metrics:
        for metric in alert_metrics:
            if metric not in dashboard_metrics:
                result.unvisualized_alerts.append(
                    f"{service_id}: alert metric '{metric}' not in any dashboard panel"
                )

    # OBS-401: Alert ↔ SLO — SLO indicator metrics should have alerts
    if alert_metrics and slo_metrics:
        for metric in slo_metrics:
            if metric not in alert_metrics:
                result.unalerted_slos.append(
                    f"{service_id}: SLO indicator metric '{metric}' has no corresponding alert"
                )

    # OBS-402: Dashboard ↔ SLO — threshold alignment
    if dashboard and slo:
        slo_target = slo.get("spec", {}).get("target")
        if slo_target is not None:
            panels = dashboard.get("panels", []) if isinstance(dashboard, dict) else []
            for panel in panels:
                thresholds = panel.get("thresholds", [])
                for t in thresholds:
                    if isinstance(t, dict) and t.get("value") is not None:
                        try:
                            panel_threshold = float(t["value"])
                            # Check if this looks like an availability threshold
                            if 90.0 <= panel_threshold <= 100.0:
                                if abs(panel_threshold - float(slo_target)) > 0.01:
                                    result.misaligned_thresholds.append(
                                        f"{service_id}: panel threshold {panel_threshold} "
                                        f"vs SLO target {slo_target}"
                                    )
                        except (ValueError, TypeError):
                            pass

    # OBS-202d: Missing availability SLO — services with an availability
    # requirement SHOULD have a ratio-based availability SLO in addition
    # to a latency threshold SLO.
    if manifest_availability is not None and slo_content:
        slo_data = slo if slo else _safe_yaml_load(slo_content)
        has_availability_slo = False
        if slo_data and isinstance(slo_data, dict):
            # Check for ratioMetric (availability) vs thresholdMetric (latency)
            spec = slo_data.get("spec", {})
            indicator = spec.get("indicator", {})
            if isinstance(indicator, dict):
                ind_spec = indicator.get("spec", {})
                if ind_spec.get("ratioMetric"):
                    has_availability_slo = True
            # Also check metadata.name for "availability" pattern
            name = slo_data.get("metadata", {}).get("name", "")
            if "availability" in name.lower():
                has_availability_slo = True
        if not has_availability_slo:
            result.missing_availability_slos.append(
                f"{service_id}: manifest requires {manifest_availability}% availability "
                f"but only latency SLO generated (OBS-202d)"
            )

    return result


def _extract_metric_names(expr: str) -> List[str]:
    """Extract Prometheus metric names from a PromQL expression."""
    # Match metric_name{...} or metric_name[...] or bare metric_name in functions
    return re.findall(r'([a-z_][a-z0-9_]*(?:_bucket|_total|_count|_sum)?)\s*[{\[\(]', expr)


def _safe_yaml_load(content: Optional[str]) -> Optional[Dict]:
    """Safe YAML load returning None on failure."""
    if not content:
        return None
    try:
        data = yaml.safe_load(content)
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


# ---------------------------------------------------------------------------
# Metric name validity checks (REQ-KZ-OBS-203)
# ---------------------------------------------------------------------------

# OTel dot-notation → Prometheus underscore mapping
_PROM_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')
_DOT_METRIC_RE = re.compile(r'[a-z]+\.[a-z]+\.[a-z]')

# Transport → expected metric prefix
_TRANSPORT_METRIC_PREFIX: Dict[str, str] = {
    "grpc": "rpc_server_",
    "http": "http_server_",
}


def validate_metric_names(
    exprs: List[str],
    service_id: str = "",
    transport: Optional[str] = None,
) -> List[ObservabilityIssue]:
    """Validate metric names in PromQL expressions (REQ-KZ-OBS-203a/b/c).

    Checks:
      OBS-203a: Prometheus naming convention (lowercase + underscores)
      OBS-203b: Transport-metric alignment (gRPC→rpc_server_*, HTTP→http_server_*)
      OBS-203c: _bucket suffix in histogram_quantile() calls

    Args:
        exprs: List of PromQL expression strings.
        service_id: Service identifier for messages.
        transport: Service transport type ("grpc" or "http").

    Returns:
        List of ObservabilityIssue for any violations found.
    """
    issues: List[ObservabilityIssue] = []

    for expr in exprs:
        metrics = _extract_metric_names(expr)

        for metric in metrics:
            # OBS-203a: Prometheus naming convention
            if _DOT_METRIC_RE.search(metric):
                issues.append(ObservabilityIssue(
                    "OBS-203a", "warning",
                    f"Metric '{metric}' uses dot notation; "
                    f"Prometheus convention requires underscores "
                    f"(e.g., '{metric.replace('.', '_')}')",
                ))

            # OBS-203b: Transport-metric alignment
            if transport:
                expected_prefix = _TRANSPORT_METRIC_PREFIX.get(transport)
                if expected_prefix:
                    # Only check server-side metrics (skip generic ones like 'rate', 'sum')
                    if ("server" in metric or "client" in metric) and \
                            not metric.startswith(expected_prefix):
                        issues.append(ObservabilityIssue(
                            "OBS-203b", "error",
                            f"Service '{service_id}' uses {transport} but "
                            f"metric '{metric}' doesn't match expected prefix "
                            f"'{expected_prefix}*'",
                        ))

        # OBS-203c: _bucket suffix in histogram_quantile()
        hq_matches = re.findall(
            r'histogram_quantile\([^,]+,\s*(?:rate|increase)\((\w+)\{',
            expr,
        )
        for metric in hq_matches:
            if not metric.endswith("_bucket"):
                issues.append(ObservabilityIssue(
                    "OBS-203c", "warning",
                    f"histogram_quantile() references '{metric}' "
                    f"without _bucket suffix (should be '{metric}_bucket')",
                ))

    return issues


# ---------------------------------------------------------------------------
# Manifest derivation completeness (REQ-KZ-OBS-403)
# ---------------------------------------------------------------------------


def validate_derivation_completeness(
    derivation_rules: List[Dict[str, Any]],
    artifacts: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """Check every derivation rule traces to a consumed value (REQ-KZ-OBS-403).

    Args:
        derivation_rules: List of derivation rule dicts from observability-manifest.yaml.
            Each has: field, source, transformation, tier, applied_to.
        artifacts: List of artifact dicts with at least 'content' (YAML string),
            'artifact_type', 'service_id'.

    Returns:
        Tuple of (unused_derivations, consumed_incorrect).
        unused_derivations: rules whose output field doesn't appear in any artifact.
        consumed_incorrect: rules whose value appears but with a mismatched value.
    """
    unused: List[str] = []
    incorrect: List[str] = []

    # Build a map of derivation field → expected value
    for rule in derivation_rules:
        rule_field = rule.get("field", "")
        rule_value = str(rule.get("transformation", ""))
        applied_to = rule.get("applied_to", [])

        if not rule_field or not rule_value:
            continue

        # Check if this derivation is consumed by any artifact
        consumed = False
        for artifact in artifacts:
            content = artifact.get("content", "")
            svc = artifact.get("service_id", "")
            if applied_to and svc not in applied_to:
                continue

            if not content:
                continue

            # Check consumption based on field type
            if rule_field == "alert_severity":
                # Should appear as severity label in alerts
                if "severity:" in content:
                    consumed = True
                    # Check value: "high → critical" means severity should be "critical"
                    expected_sev = rule_value.split("→")[-1].strip() if "→" in rule_value else rule_value
                    if f"severity: {expected_sev}" not in content:
                        # Check YAML-parsed value
                        data = _safe_yaml_load(content)
                        if data:
                            for g in data.get("groups", [{}]):
                                for r in (g.get("rules", []) if isinstance(g, dict) else []):
                                    actual = r.get("labels", {}).get("severity", "")
                                    if actual and actual != expected_sev:
                                        incorrect.append(
                                            f"Rule '{rule_field}': expected severity "
                                            f"'{expected_sev}' but found '{actual}' "
                                            f"in {svc}"
                                        )

            elif rule_field == "latency_p99":
                # Should appear as threshold in alerts/dashboards
                if rule_value.replace("ms", "") in content or rule_value in content:
                    consumed = True

            elif rule_field == "availability":
                # Should appear as SLO target or error budget
                if rule_value in content:
                    consumed = True

            elif rule_field == "slo_window":
                # Should appear as timeWindow duration
                if rule_value in content:
                    consumed = True

            elif rule_field == "dashboard_placement":
                # Consumed as tag/metadata — just check presence
                consumed = True  # Always consumed by generation logic

        if not consumed:
            unused.append(
                f"Derivation '{rule_field}' ({rule_value}) not consumed by "
                f"any artifact for services: {applied_to}"
            )

    return unused, incorrect


# ---------------------------------------------------------------------------
# RED coverage helpers
# ---------------------------------------------------------------------------


def _panel_has_expr(panel: Dict[str, Any]) -> bool:
    """Check if a panel has a PromQL expression (in expr or targets)."""
    if panel.get("expr"):
        return True
    for target in panel.get("targets", []):
        if isinstance(target, dict) and target.get("expr"):
            return True
    return False


def get_all_panel_exprs(panels: List[Dict[str, Any]]) -> List[str]:
    """Extract all PromQL expressions from panels."""
    exprs = []
    for p in panels:
        if p.get("expr"):
            exprs.append(str(p["expr"]))
        for t in p.get("targets", []):
            if isinstance(t, dict) and t.get("expr"):
                exprs.append(str(t["expr"]))
    return exprs


def has_rate_panel(panels: List[Dict[str, Any]]) -> bool:
    """Check for a request rate panel (R in RED)."""
    for expr in get_all_panel_exprs(panels):
        if "rate(" in expr and "_count" in expr and "status" not in expr.lower():
            return True
    return False


def has_error_panel(panels: List[Dict[str, Any]]) -> bool:
    """Check for an error rate panel (E in RED)."""
    for expr in get_all_panel_exprs(panels):
        e = expr.lower()
        if ("error" in e or "status_code" in e or "status_code!=" in e
                or 'status_code!="ok"' in e or "status!=" in e):
            return True
    return False


def has_duration_panel(panels: List[Dict[str, Any]]) -> bool:
    """Check for a latency/duration panel (D in RED)."""
    for expr in get_all_panel_exprs(panels):
        if "histogram_quantile" in expr or "duration" in expr.lower():
            return True
    return False


def _compute_red_coverage(panels: List[Dict[str, Any]]) -> float:
    """Compute RED method coverage as fraction (0.0–1.0)."""
    signals = 0
    if has_rate_panel(panels):
        signals += 1
    if has_error_panel(panels):
        signals += 1
    if has_duration_panel(panels):
        signals += 1
    return signals / 3.0
