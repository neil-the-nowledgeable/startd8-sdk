"""Observability artifact validation — REQ-KZ-OBS-100–302, 710.

Structural + semantic validation for generated dashboards, alerts, and SLOs.
Each check follows validate-with-autofix: try repair → validate → report.

Pure functions — accept YAML content as strings for retroactive validation
(REQ-KZ-OBS-705a).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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
    "MetricCoverageResult",
    "compute_metric_coverage",
    "extract_referenced_metrics",
    "CoverageGateResult",
    "evaluate_coverage_gate",
    "ExtendedArtifactValidationResult",
    "validate_extended_artifact",
    "has_rate_panel",
    "has_error_panel",
    "has_duration_panel",
    "get_all_panel_exprs",
    "PortalValidationResult",
    "validate_portal",
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


class _ChecklistResult:
    """Shared check-tallying base for the structural validators (D-9).

    The three result types were ~90% identical: a running ``checks_passed`` /
    ``checks_total`` tally, an ``issues`` list, and a ``score``. This base
    centralizes that machinery so each validator just *declares its checks* via
    ``check()`` instead of repeating the ``total += 1 / passed += 1 /
    issues.append(...)`` triplet. Subclasses (below) add only their type-specific
    fields. (Plain class, not a dataclass — its annotations are NOT promoted to
    fields of the dataclass subclasses, so field order is unchanged.)
    """

    checks_passed: int
    checks_total: int
    issues: List["ObservabilityIssue"]

    @property
    def score(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0

    def check(self, check_id: str, severity: str, ok: bool, message: str = "") -> bool:
        """Record one check. Always bumps ``checks_total``; bumps ``checks_passed``
        when ``ok``; otherwise records an issue **only if a message is given**.
        An empty message yields a counted-but-unflagged check — preserving the
        dashboard validator's ``elif panels:`` third state (a check that counts
        against the total but neither passes nor raises an issue)."""
        self.checks_total += 1
        if ok:
            self.checks_passed += 1
        elif message:
            self.issues.append(ObservabilityIssue(check_id, severity, message))
        return ok

    def record_metric_checks(self, metric_issues: List["ObservabilityIssue"]) -> None:
        """OBS-203 aggregate: each found metric-name issue is a failed check; if
        none were found, a single passing check (preserves the prior tally)."""
        if metric_issues:
            self.checks_total += len(metric_issues)
            self.issues.extend(metric_issues)
        else:
            self.checks_total += 1
            self.checks_passed += 1


@dataclass
class DashboardValidationResult(_ChecklistResult):
    file_path: str
    yaml_valid: bool = False
    panel_count: int = 0
    red_coverage: float = 0.0
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)
    repairs_applied: List[str] = field(default_factory=list)


@dataclass
class AlertValidationResult(_ChecklistResult):
    file_path: str
    yaml_valid: bool = False
    rule_count: int = 0
    rule_coverage: float = 0.0
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)
    repairs_applied: List[str] = field(default_factory=list)


@dataclass
class SloValidationResult(_ChecklistResult):
    file_path: str
    yaml_valid: bool = False
    target_value: Optional[float] = None
    target_matches_manifest: bool = False
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)
    repairs_applied: List[str] = field(default_factory=list)


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

    # OBS-100a: YAML parseable (fatal — early return on failure)
    result.checks_total += 1
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        result.issues.append(ObservabilityIssue("OBS-100a", "error", f"YAML parse error: {exc}"))
        return result
    if not isinstance(data, dict):
        result.issues.append(ObservabilityIssue("OBS-100a", "error", "YAML content is not a mapping"))
        return result
    result.yaml_valid = True
    result.checks_passed += 1

    # Autofix: gridPos
    if autofix:
        data, repairs = repair_gridpos(data)
        result.repairs_applied.extend(repairs)

    panels = data.get("panels", [])
    result.panel_count = len(panels)
    n = len(panels)

    result.check("OBS-100b", "error", bool(data.get("title")), "Dashboard missing 'title'")

    uid = data.get("uid", "")
    result.check(
        "OBS-100c", "error", bool(uid) and uid.startswith("obs-"),
        f"uid '{uid}' doesn't match obs-{{service}} pattern",
    )

    result.check("OBS-100d", "error", bool(panels), "Dashboard has no panels")

    # OBS-100e–h: per-panel completeness. With NO panels these count toward the
    # total but raise no issue (empty message = the prior `elif panels:` state).
    panels_with_expr = sum(1 for p in panels if _panel_has_expr(p))
    result.check(
        "OBS-100e", "error", bool(panels) and panels_with_expr == n,
        f"{n - panels_with_expr}/{n} panels missing PromQL expr" if panels else "",
    )
    panels_with_type = sum(1 for p in panels if p.get("type"))
    result.check(
        "OBS-100f", "warning", bool(panels) and panels_with_type == n,
        f"{n - panels_with_type}/{n} panels missing visualization type" if panels else "",
    )
    panels_with_unit = sum(1 for p in panels if p.get("unit"))
    result.check(
        "OBS-100g", "warning", bool(panels) and panels_with_unit == n,
        f"{n - panels_with_unit}/{n} panels missing unit" if panels else "",
    )
    panels_with_grid = sum(1 for p in panels if p.get("gridPos"))
    result.check(
        "OBS-100h", "warning", bool(panels) and panels_with_grid == n,
        "Panels missing gridPos" if panels else "",
    )

    result.check("OBS-100i", "warning", bool(data.get("datasources")), "No datasources declared")
    result.check("OBS-100j", "info", bool(data.get("variables")), "No variables declared")

    # OBS-200a (OBS-710c): RED coverage
    red = _compute_red_coverage(panels)
    result.red_coverage = red
    missing = []
    if not has_rate_panel(panels):
        missing.append("Rate")
    if not has_error_panel(panels):
        missing.append("Errors")
    if not has_duration_panel(panels):
        missing.append("Duration")
    result.check(
        "OBS-200a", "warning", red >= 2.0 / 3.0,
        f"RED coverage {red:.0%} — missing: {', '.join(missing)}",
    )

    # OBS-203: Metric name validity (aggregate)
    all_exprs = get_all_panel_exprs(panels)
    result.record_metric_checks(
        validate_metric_names(all_exprs, service_id=service_id, transport=transport)
    )
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

    # OBS-101a: YAML parseable (fatal — early return on failure)
    result.checks_total += 1
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        result.issues.append(ObservabilityIssue("OBS-101a", "error", f"YAML parse error: {exc}"))
        return result
    if not isinstance(data, dict):
        result.issues.append(ObservabilityIssue("OBS-101a", "error", "YAML content is not a mapping"))
        return result
    result.yaml_valid = True
    result.checks_passed += 1

    # Extract rules
    groups = data.get("groups", [])
    rules: List[Dict] = []
    for g in (groups if isinstance(groups, list) else []):
        rules.extend(g.get("rules", []) if isinstance(g, dict) else [])
    result.rule_count = len(rules)

    result.check("OBS-101b", "error", bool(rules), "No alert rules found")

    for rule in rules:
        name = rule.get("alert", "")
        result.check(
            "OBS-101c", "error", bool(name) and name[0].isupper(),
            f"Rule missing or invalid alert name: '{name}'",
        )
        result.check("OBS-101d", "error", bool(rule.get("expr")), f"Rule '{name}' missing expr")
        result.check("OBS-101e", "warning", bool(rule.get("for")), f"Rule '{name}' missing 'for' duration")

        labels = rule.get("labels", {})
        severity = labels.get("severity", "")
        result.check(
            "OBS-101f", "error", severity in ("critical", "warning", "info"),
            f"Rule '{name}' missing/invalid severity label: '{severity}'",
        )
        result.check("OBS-101g", "warning", bool(labels.get("service")), f"Rule '{name}' missing service label")

        annotations = rule.get("annotations", {})
        result.check(
            "OBS-101h", "warning", bool(annotations.get("summary")),
            f"Rule '{name}' missing summary annotation",
        )

    # OBS-710d: Alert coverage (latency + error_rate + availability)
    expected = 3 if manifest_availability is not None else 1
    result.rule_coverage = min(len(rules), expected) / expected if expected else 1.0
    result.check(
        "OBS-710d", "warning", result.rule_coverage >= 1.0,
        f"Alert coverage: {len(rules)}/{expected} expected rules (rule_coverage={result.rule_coverage:.2f})",
    )

    # OBS-203: Metric name validity (aggregate)
    alert_exprs = [str(r.get("expr", "")) for r in rules if r.get("expr")]
    result.record_metric_checks(
        validate_metric_names(alert_exprs, service_id=service_id, transport=transport)
    )
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
    """Validate OpenSLO v1 YAML against OBS-102 + OBS-202 checklists.

    Supports multi-document YAML (``---`` separators) — each document is
    validated independently and results are merged.  This is common when
    a service has both availability and latency SLOs in one file.
    """
    # Multi-document support: split, validate each, merge results.
    try:
        docs = list(yaml.safe_load_all(content))
    except yaml.YAMLError:
        docs = []

    slo_docs = [d for d in docs if isinstance(d, dict)]

    if len(slo_docs) > 1:
        merged = SloValidationResult(file_path=file_path)
        for doc in slo_docs:
            doc_yaml = yaml.dump(doc, default_flow_style=False, sort_keys=False)
            sub = validate_slo(
                doc_yaml, file_path,
                manifest_availability=manifest_availability,
                autofix=autofix,
                service_id=service_id,
                transport=transport,
            )
            merged.yaml_valid = merged.yaml_valid or sub.yaml_valid
            merged.checks_passed += sub.checks_passed
            merged.checks_total += sub.checks_total
            merged.issues.extend(sub.issues)
            merged.repairs_applied.extend(sub.repairs_applied)
            if sub.target_value is not None:
                merged.target_value = sub.target_value
            if sub.target_matches_manifest:
                merged.target_matches_manifest = True
        return merged

    result = SloValidationResult(file_path=file_path)

    # OBS-102a: YAML parseable (fatal — early return on failure)
    result.checks_total += 1
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        result.issues.append(ObservabilityIssue("OBS-102a", "error", f"YAML parse error: {exc}"))
        return result
    if not isinstance(data, dict):
        result.issues.append(ObservabilityIssue("OBS-102a", "error", "YAML content is not a mapping"))
        return result
    result.yaml_valid = True
    result.checks_passed += 1

    # Autofix: SLO target from manifest
    if autofix and manifest_availability is not None:
        data, repairs = repair_slo_target(data, manifest_availability)
        result.repairs_applied.extend(repairs)

    spec = data.get("spec", {})
    metadata = data.get("metadata", {})

    result.check(
        "OBS-102b", "error", data.get("apiVersion") == "openslo/v1",
        f"apiVersion: '{data.get('apiVersion')}' (expected 'openslo/v1')",
    )
    result.check(
        "OBS-102c", "error", data.get("kind") == "SLO",
        f"kind: '{data.get('kind')}' (expected 'SLO')",
    )

    # OBS-102d: spec.target (records target_value when present)
    target = spec.get("target")
    if target is not None:
        result.target_value = float(target)
    result.check("OBS-102d", "error", target is not None, "Missing spec.target")

    result.check("OBS-102e", "error", bool(spec.get("timeWindow")), "Missing spec.timeWindow")

    indicator = spec.get("indicator", {})
    ind_spec = indicator.get("spec", {}) if isinstance(indicator, dict) else {}
    result.check(
        "OBS-102f", "error",
        bool(ind_spec.get("thresholdMetric") or ind_spec.get("ratioMetric")),
        "Missing spec.indicator with threshold/ratio metric",
    )

    result.check("OBS-102g", "warning", bool(metadata.get("name")), "Missing metadata.name")
    labels = metadata.get("labels", {})
    result.check("OBS-102h", "warning", bool(labels.get("service")), "Missing metadata.labels.service")
    result.check("OBS-102i", "info", bool(spec.get("alerting")), "Missing spec.alerting section")

    # OBS-202a (OBS-710a): target matches manifest — three-way (match / no-manifest / no-target)
    if manifest_availability is not None and result.target_value is not None:
        matches = abs(result.target_value - manifest_availability) < 0.01
        if matches:
            result.target_matches_manifest = True
        result.check(
            "OBS-202a", "error", matches,
            f"SLO target {result.target_value} doesn't match manifest availability {manifest_availability}",
        )
    elif manifest_availability is None:
        result.check("OBS-202a", "error", True)  # can't check — pass by default
    else:
        result.check("OBS-202a", "error", False, "No target to check against manifest")

    # OBS-203: Metric name validity (check SLO indicator query) — aggregate
    slo_exprs: List[str] = []
    tm = ind_spec.get("thresholdMetric", {})
    if isinstance(tm, dict):
        ms = tm.get("metricSource", {})
        if isinstance(ms, dict):
            q = ms.get("spec", {}).get("query", "")
            if q:
                slo_exprs.append(str(q))
    result.record_metric_checks(
        validate_metric_names(slo_exprs, service_id=service_id, transport=transport)
    )
    return result


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------


# Composite blend weights when semantic metric-coverage is available
# (Gap 3 / Closure 2). Structural form still dominates, but ignoring a
# service's domain metrics now visibly drags the headline number down.
_STRUCTURAL_WEIGHT = 0.7
_COVERAGE_WEIGHT = 0.3


def compute_service_composite(
    dashboard_score: float,
    alert_score: float,
    slo_score: float,
    metric_coverage: Optional[float] = None,
) -> float:
    """Per-service composite = weighted average (REQ-KZ-OBS-303).

    The structural composite is a weighted average of the three artifact
    scores (form: well-formed YAML, valid panels, etc.). When ``metric_coverage``
    is provided (Gap 3 / Closure 2), it is blended in so the headline score
    reflects *semantic relevance* — a triplet that ignores the service's domain
    metrics scores high structurally but low on coverage, and the composite
    drops accordingly. Omitting ``metric_coverage`` preserves the legacy
    structural-only behaviour for backward compatibility.
    """
    structural = (dashboard_score * 0.35) + (alert_score * 0.35) + (slo_score * 0.30)
    if metric_coverage is None:
        return structural
    return round(structural * _STRUCTURAL_WEIGHT + metric_coverage * _COVERAGE_WEIGHT, 6)


# ---------------------------------------------------------------------------
# Semantic metric-coverage check (Gap 3 / Closure 2)
# ---------------------------------------------------------------------------

_METRIC_SUFFIXES = ("_bucket", "_count", "_sum", "_total")


@dataclass
class MetricCoverageResult:
    """Fraction of a service's expected metrics referenced by its artifacts."""

    score: float = 1.0
    expected: List[str] = field(default_factory=list)
    covered: List[str] = field(default_factory=list)
    uncovered: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "expected_count": len(self.expected),
            "covered_count": len(self.covered),
            "uncovered": self.uncovered,
        }


def _normalize_metric_name(name: str) -> str:
    """Normalize a metric name to its base form for coverage comparison.

    Converts OTel dot-notation to Prometheus underscores and strips the
    histogram/counter suffixes PromQL appends (``_bucket``/``_count``/``_sum``/
    ``_total``), so ``http.server.duration`` and ``http_server_duration_bucket``
    compare equal.
    """
    base = name.replace(".", "_")
    for suf in _METRIC_SUFFIXES:
        if base.endswith(suf):
            return base[: -len(suf)]
    return base


def extract_referenced_metrics(contents: Iterable[Optional[str]]) -> Set[str]:
    """Collect base metric names referenced across artifact contents.

    Comment lines (YAML ``#`` headers and the commented-out domain-alert TODO
    stubs) are excluded, so a metric only counts as *referenced* when it appears
    in an active expression — not merely as a suggested-but-disabled stub.
    """
    referenced: Set[str] = set()
    for content in contents:
        if not content:
            continue
        for line in content.splitlines():
            if line.lstrip().startswith("#"):
                continue
            for raw in _extract_metric_names(line):
                referenced.add(_normalize_metric_name(raw))
    return referenced


def compute_metric_coverage(
    expected_metrics: Iterable[str],
    artifact_contents: Iterable[Optional[str]],
) -> MetricCoverageResult:
    """Compute semantic metric-coverage for a service (Gap 3 / Closure 2).

    Coverage = |expected ∩ referenced| / |expected|, where ``expected`` is the
    service's declared + convention metrics and ``referenced`` is the set of
    metrics that appear in at least one active artifact expression. An empty
    expected set scores 1.0 (nothing to cover).
    """
    expected = {_normalize_metric_name(m) for m in expected_metrics if m}
    referenced = extract_referenced_metrics(artifact_contents)
    covered = expected & referenced
    uncovered = expected - referenced
    score = len(covered) / len(expected) if expected else 1.0
    return MetricCoverageResult(
        score=round(score, 4),
        expected=sorted(expected),
        covered=sorted(covered),
        uncovered=sorted(uncovered),
    )


# ---------------------------------------------------------------------------
# Coverage gate — make the semantic-coverage scores actionable
# ---------------------------------------------------------------------------


@dataclass
class CoverageGateResult:
    """Outcome of evaluating coverage scores against minimum thresholds.

    A gate lets a caller (CLI / pipeline) fail when generated observability is
    structurally clean but semantically thin — low metric coverage (Gap 3) or a
    partial artifact-type contract (Gap 2) — instead of passing silently.
    """

    passed: bool
    failures: List[str] = field(default_factory=list)
    metric_coverage: Optional[float] = None
    artifact_type_coverage: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": self.failures,
            "metric_coverage": self.metric_coverage,
            "artifact_type_coverage": self.artifact_type_coverage,
        }


def evaluate_coverage_gate(
    *,
    metric_coverage: Optional[float] = None,
    artifact_type_coverage: Optional[float] = None,
    min_metric_coverage: Optional[float] = None,
    min_artifact_type_coverage: Optional[float] = None,
) -> CoverageGateResult:
    """Evaluate coverage scores against optional minimum thresholds.

    Only thresholds that are set are enforced; unset thresholds are ignored, so
    a caller that configures neither always passes (gate is opt-in). When a
    threshold is set but its score is unavailable, that is a failure — the gate
    cannot vouch for a number it does not have.
    """
    failures: List[str] = []

    if min_metric_coverage is not None:
        if metric_coverage is None:
            failures.append(
                f"metric_coverage unavailable but minimum {min_metric_coverage:.2f} required"
            )
        elif metric_coverage < min_metric_coverage:
            failures.append(
                f"metric_coverage {metric_coverage:.2f} below minimum {min_metric_coverage:.2f}"
            )

    if min_artifact_type_coverage is not None:
        if artifact_type_coverage is None:
            failures.append(
                f"artifact_type_coverage unavailable but minimum "
                f"{min_artifact_type_coverage:.2f} required"
            )
        elif artifact_type_coverage < min_artifact_type_coverage:
            failures.append(
                f"artifact_type_coverage {artifact_type_coverage:.2f} below minimum "
                f"{min_artifact_type_coverage:.2f}"
            )

    return CoverageGateResult(
        passed=not failures,
        failures=failures,
        metric_coverage=metric_coverage,
        artifact_type_coverage=artifact_type_coverage,
    )


# ---------------------------------------------------------------------------
# Extended-artifact content validation (Run-007 Finding 1)
#
# Scores any generated artifact against its declared contract — the
# completeness_markers it must contain and its max_lines budget — so the five
# non-triplet types (service_monitor, loki_rule, notification_policy, runbook,
# capability_index) and the Grafana JSON are checked, not just present.
# ---------------------------------------------------------------------------


@dataclass
class ExtendedArtifactValidationResult:
    """Result of scoring an artifact against its expected_output_contract."""

    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 1.0

    def to_quality(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "checks_passed": self.checks_passed,
            "checks_total": self.checks_total,
            "issues": [
                {"check": i.check, "severity": i.severity, "message": i.message}
                for i in self.issues
            ],
            "repairs_applied": [],
        }


def validate_extended_artifact(
    content: str,
    contract: Dict[str, Any],
) -> ExtendedArtifactValidationResult:
    """Validate an artifact's content against its declared output contract.

    Two dimensions:
    - **completeness_markers**: each required marker (a YAML key, markdown
      heading, or PromQL/LogQL token) must appear in the content. One check per
      marker.
    - **max_lines**: the content must not exceed the contract's line budget
      (one check, only when ``max_lines`` is declared).

    Marker matching is a case-sensitive substring test, which is uniform across
    YAML keys (``panels:``), markdown sections (``## Risks``), and expression
    tokens (``expr``). An empty/contract-less input scores 1.0 (nothing to check).
    """
    result = ExtendedArtifactValidationResult()
    markers = contract.get("completeness_markers") or []

    for marker in markers:
        result.checks_total += 1
        if marker and str(marker) in content:
            result.checks_passed += 1
        else:
            result.issues.append(
                ObservabilityIssue(
                    "OBS-EXT-100", "warning", f"missing completeness marker '{marker}'"
                )
            )

    max_lines = contract.get("max_lines")
    if isinstance(max_lines, int) and max_lines > 0:
        result.checks_total += 1
        line_count = content.count("\n") + 1 if content else 0
        if line_count <= max_lines:
            result.checks_passed += 1
        else:
            result.issues.append(
                ObservabilityIssue(
                    "OBS-EXT-101",
                    "warning",
                    f"{line_count} lines exceeds max_lines {max_lines}",
                )
            )

    return result


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


# ---------------------------------------------------------------------------
# Portal validation (REQ-OBP-104)
# ---------------------------------------------------------------------------


@dataclass
class PortalValidationResult:
    """Validation result for onboarding portal dashboard JSON."""

    file_path: str
    json_valid: bool = False
    panel_count: int = 0
    text_panel_count: int = 0
    has_overview: bool = False
    has_service_inventory: bool = False
    checks_passed: int = 0
    checks_total: int = 0
    issues: List[ObservabilityIssue] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0


def validate_portal(
    content: str,
    file_path: str = "",
    *,
    expected_service_count: Optional[int] = None,
) -> PortalValidationResult:
    """Validate onboarding portal dashboard JSON (REQ-OBP-104a).

    Checks:
    - OBP-104-1: JSON is valid and has panels
    - OBP-104-2: Has at least one text panel
    - OBP-104-3: Has "Project Overview" panel
    - OBP-104-4: Has "Service Inventory" or service-related panel
    - OBP-104-5: Service count matches expected (when provided)
    - OBP-104-6: Has dashboard title containing "Portal"
    """
    import json as _json

    result = PortalValidationResult(file_path=file_path)

    # OBP-104-1: Valid JSON with panels
    result.checks_total += 1
    try:
        dashboard = _json.loads(content)
        result.json_valid = True
        result.checks_passed += 1
    except (ValueError, TypeError):
        result.issues.append(ObservabilityIssue(
            "OBP-104-1", "error", "Portal content is not valid JSON",
        ))
        return result

    panels = dashboard.get("panels", [])
    result.panel_count = len(panels)

    # OBP-104-2: At least one text panel
    result.checks_total += 1
    text_panels = [p for p in panels if p.get("type") == "text"]
    result.text_panel_count = len(text_panels)
    if text_panels:
        result.checks_passed += 1
    else:
        result.issues.append(ObservabilityIssue(
            "OBP-104-2", "error", "Portal has no text panels",
        ))

    # OBP-104-3: Has "Project Overview" panel
    result.checks_total += 1
    panel_titles = [p.get("title", "") for p in panels]
    if "Project Overview" in panel_titles:
        result.has_overview = True
        result.checks_passed += 1
    else:
        result.issues.append(ObservabilityIssue(
            "OBP-104-3", "warning", "Portal missing 'Project Overview' panel",
        ))

    # OBP-104-4: Has service-related panel
    result.checks_total += 1
    has_services = any(
        "service" in t.lower() or "inventory" in t.lower()
        for t in panel_titles
    )
    if has_services:
        result.has_service_inventory = True
        result.checks_passed += 1
    else:
        result.issues.append(ObservabilityIssue(
            "OBP-104-4", "warning",
            "Portal missing service inventory panel",
        ))

    # OBP-104-5: Service count match (when expected count provided)
    if expected_service_count is not None:
        result.checks_total += 1
        # Count service rows in the service inventory text panel
        for p in text_panels:
            title = p.get("title", "")
            if "service" in title.lower() and "inventory" in title.lower():
                content_text = p.get("options", {}).get("content", "")
                # Count data rows (lines starting with |, excluding header/separator)
                data_rows = [
                    line for line in content_text.split("\n")
                    if line.startswith("|") and not line.startswith("|-")
                    and "Service" not in line.split("|")[1] if "|" in line
                ]
                # Subtract header row
                row_count = max(0, len(data_rows) - 1)
                if row_count == expected_service_count:
                    result.checks_passed += 1
                else:
                    result.issues.append(ObservabilityIssue(
                        "OBP-104-5", "warning",
                        f"Service count mismatch: expected {expected_service_count}, "
                        f"found {row_count} rows in inventory",
                    ))
                break
        else:
            # No service inventory panel found — already flagged in OBP-104-4
            pass

    # OBP-104-6: Dashboard title contains "Portal"
    result.checks_total += 1
    title = dashboard.get("title", "")
    if "portal" in title.lower():
        result.checks_passed += 1
    else:
        result.issues.append(ObservabilityIssue(
            "OBP-104-6", "info",
            f"Dashboard title '{title}' does not contain 'Portal'",
        ))

    return result
