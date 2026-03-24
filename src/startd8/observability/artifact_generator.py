"""
Generate observability artifacts (alert rules, dashboard specs, SLO definitions)
from ContextCore onboarding metadata and manifest business context.

Reads onboarding-metadata.json (from cap-dev-pipe Stage 4 EXPORT) and
.contextcore.yaml, then produces per-service artifact files.

See docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md for design.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    from startd8.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ConventionMetric:
    """A single OTel convention-based metric expected for a service."""

    name: str  # e.g. "rpc.server.duration"
    type: str  # e.g. "histogram", "counter"
    source: str  # e.g. "otel_semconv:grpc"


@dataclass
class ServiceHints:
    """Instrumentation hints for a single service."""

    service_id: str
    transport: str  # "grpc" or "http"
    language: Optional[str] = None
    detected_databases: List[str] = field(default_factory=list)
    convention_metrics: List[ConventionMetric] = field(default_factory=list)


@dataclass
class BusinessContext:
    """Business context extracted from .contextcore.yaml."""

    criticality: str = "medium"
    availability: Optional[str] = None  # e.g. "99.9"
    latency_p99: Optional[str] = None  # e.g. "500ms"
    throughput: Optional[str] = None  # e.g. "100rps"
    error_budget: Optional[str] = None  # e.g. "0.1"
    dashboard_placement: str = "standard"
    owner: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    slo_window: str = "30d"


@dataclass
class DerivationTrace:
    """Records how a value was derived for traceability (REQ-UOM-040)."""

    field: str  # e.g. "alert_severity"
    source: str  # e.g. "manifest.spec.business.criticality"
    transformation: str  # e.g. "high → critical"
    tier: str  # "explicit", "manifest", "default"


@dataclass
class ArtifactResult:
    """Result of generating a single artifact file."""

    artifact_type: str  # "alert_rule", "dashboard_spec", "slo_definition"
    service_id: str
    output_path: str  # relative path within output dir
    status: str  # "generated", "skipped", "error"
    content: str = ""  # YAML content to write
    derivations: List[DerivationTrace] = field(default_factory=list)
    error_message: Optional[str] = None
    quality: Optional[Dict[str, Any]] = None  # REQ-KZ-OBS-706a: {score, checks_passed, checks_total, issues, repairs_applied}


@dataclass
class GenerationReport:
    """Summary of all generated artifacts (REQ-UOM-004)."""

    project_id: Optional[str]
    generated_at: str
    artifacts: List[ArtifactResult] = field(default_factory=list)
    services_processed: int = 0
    services_skipped: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CRITICALITY_TO_SEVERITY: Dict[str, str] = {
    "critical": "critical",
    "high": "critical",
    "medium": "warning",
    "low": "info",
}

_DEFAULT_THRESHOLDS = {
    "availability": "99",
    "latency_p99": "500ms",
    "throughput": "100rps",
}

# OTel instrument type → Grafana panel type
_INSTRUMENT_TO_PANEL: Dict[str, str] = {
    "histogram": "histogram",
    "counter": "timeseries",
    "gauge": "gauge",
    "up_down_counter": "timeseries",
    "observable_gauge": "gauge",
}

# OTel instrument type → PromQL query template
_INSTRUMENT_TO_QUERY: Dict[str, str] = {
    "histogram": (
        "histogram_quantile(0.99, "
        'rate({metric}_bucket{{service="{service}"}}[$__rate_interval]))'
    ),
    "counter": 'rate({metric}_total{{service="{service}"}}[$__rate_interval])',
    "gauge": '{metric}{{service="{service}"}}',
    "up_down_counter": '{metric}{{service="{service}"}}',
    "observable_gauge": '{metric}{{service="{service}"}}',
}

# Metric unit hints by name pattern
_METRIC_UNITS: Dict[str, str] = {
    "duration": "s",
    "size": "bytes",
    "request": "reqps",
    "response": "bytes",
}


# ---------------------------------------------------------------------------
# Phase 1: Input loading
# ---------------------------------------------------------------------------


def load_onboarding_metadata(path: Path) -> Dict[str, Any]:
    """Load onboarding-metadata.json and return raw dict.

    Raises FileNotFoundError if path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Onboarding metadata not found: {path}")
    with open(path, "r") as f:
        data = json.load(f)
    logger.info("Loaded onboarding metadata from %s (%d top-level keys)", path, len(data))
    return data


_REQ_ID_PATTERN = re.compile(r"^req[a-z]{2,}\d+")
_RUN_ID_PATTERN = re.compile(r"/run-\d+|^run-\d+")

# Known non-service directory names that may appear in instrumentation_hints
_NON_SERVICE_NAMES = frozenset({
    "protos", "proto", "shared", "common", "lib", "libs",
    "docs", "scripts", "tools", "config", "configs",
})


def _is_non_service_entry(
    svc_id: str,
    hint: Dict[str, Any],
    metadata: Dict[str, Any],
) -> bool:
    """Check if an instrumentation_hints entry is not a real runtime service.

    Filters requirement IDs, run IDs, project-level names, and known
    non-service directories (REQ-KZ-OBS-103).
    """
    # Requirement ID pattern (reqcdpobs001..., reqpms002...)
    if _REQ_ID_PATTERN.match(svc_id):
        return True

    # Run ID pattern (online-boutique/run-093-...)
    if _RUN_ID_PATTERN.search(svc_id):
        return True

    # Project-level name match
    project_id = metadata.get("project_id", "")
    if project_id and svc_id == project_id:
        return True
    # Also match the project name portion of composite IDs
    project_name = project_id.split("/")[0] if "/" in str(project_id) else ""
    if project_name and svc_id == project_name:
        return True

    # Known non-service directory names — check both exact match and as
    # path segments so compound IDs like "online-boutique/protos" are caught.
    svc_parts = {p.lower() for p in svc_id.replace("\\", "/").split("/")}
    if svc_parts & _NON_SERVICE_NAMES:
        return True

    # Entries ending in common non-service suffixes
    svc_lower = svc_id.lower()
    if svc_lower.endswith(("-demo", "-docs", "-guidance", "-overview")):
        return True

    # Multi-word names that look like document titles, not service IDs
    # (services are typically single words or hyphenated: cartservice, email-service)
    if "guidance" in svc_lower or "objectives" in svc_lower:
        return True

    return False


def extract_service_hints(metadata: Dict[str, Any]) -> List[ServiceHints]:
    """Extract per-service instrumentation hints from onboarding metadata.

    Returns empty list if instrumentation_hints key is absent (REQ-UOM-070).
    Skips services with no transport field (REQ-UOM-071).
    Skips non-service entries (REQ-KZ-OBS-103).
    """
    raw_hints = metadata.get("instrumentation_hints")
    if not raw_hints:
        logger.warning(
            "No instrumentation_hints in onboarding metadata; "
            "producing zero artifacts"
        )
        return []

    services: List[ServiceHints] = []
    skipped_non_service = 0
    for svc_id, hint in raw_hints.items():
        # REQ-KZ-OBS-103: Filter non-service entries
        if _is_non_service_entry(svc_id, hint, metadata):
            logger.info("Skipping non-service entry: %s", svc_id)
            skipped_non_service += 1
            continue

        transport = hint.get("transport")
        if not transport:
            logger.warning("Service %s has no transport field; skipping", svc_id)
            continue

        metrics_raw = hint.get("metrics", {}).get("convention_based", [])
        convention_metrics = [
            ConventionMetric(
                name=m.get("name", ""),
                type=m.get("type", ""),
                source=m.get("source", ""),
            )
            for m in metrics_raw
            if m.get("name")
        ]

        services.append(
            ServiceHints(
                service_id=svc_id,
                transport=transport,
                language=hint.get("language"),
                detected_databases=hint.get("detected_databases", []),
                convention_metrics=convention_metrics,
            )
        )

    logger.info(
        "Extracted hints for %d services (%d skipped)",
        len(services),
        len(raw_hints) - len(services),
    )
    return services


def load_business_context(
    manifest_path: Optional[Path],
    metadata: Dict[str, Any],
) -> BusinessContext:
    """Extract business context from .contextcore.yaml or onboarding metadata.

    Prefers manifest for direct reads; falls back to metadata fields.
    All fields are optional — defaults applied with log warnings (REQ-UOM-072).
    """
    ctx = BusinessContext()

    # Try manifest first
    manifest: Dict[str, Any] = {}
    if manifest_path and manifest_path.exists():
        with open(manifest_path, "r") as f:
            manifest = yaml.safe_load(f) or {}
        logger.info("Loaded business context from manifest: %s", manifest_path)

    spec = manifest.get("spec", {})
    business = spec.get("business", {})
    requirements = spec.get("requirements", {})
    observability = spec.get("observability", {})
    project = spec.get("project", {})

    ctx.project_id = project.get("id") or metadata.get("project_id")
    ctx.project_name = project.get("name")
    ctx.criticality = business.get("criticality", "medium")
    ctx.owner = business.get("owner")
    ctx.dashboard_placement = observability.get("dashboardPlacement", "standard")

    # SLO thresholds from requirements
    ctx.availability = requirements.get("availability")
    ctx.latency_p99 = requirements.get("latencyP99")
    ctx.throughput = requirements.get("throughput")
    ctx.error_budget = requirements.get("errorBudget")

    # SLO window from strategy objectives if available
    strategy = manifest.get("strategy", {})
    for obj in strategy.get("objectives", []):
        for kr in obj.get("keyResults", []):
            if kr.get("window"):
                ctx.slo_window = kr["window"]
                break

    # Log defaults
    if not ctx.availability:
        logger.info("No availability threshold in manifest; will use default (99%%)")
    if not ctx.latency_p99:
        logger.info("No latencyP99 in manifest; will use default (500ms)")

    return ctx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_duration_to_seconds(value: str) -> float:
    """Parse '500ms' → 0.5, '2s' → 2.0, '200' → 0.2 (assume ms if bare number)."""
    value = value.strip().lower()
    if value.endswith("ms"):
        return float(value[:-2]) / 1000.0
    if value.endswith("s"):
        return float(value[:-1])
    # Bare number: assume milliseconds
    return float(value) / 1000.0


def _parse_availability_to_fraction(value: str) -> float:
    """Parse '99.9' → 0.999, '99.95' → 0.9995.

    Rounds to 6 decimal places to avoid IEEE 754 artifacts like
    0.9990000000000001 in generated YAML/PromQL.
    """
    return round(float(value.strip()) / 100.0, 6)


def _prom_name(otel_name: str) -> str:
    """Convert OTel dot-separated name to Prometheus underscore format."""
    return otel_name.replace(".", "_")


def _resolve_threshold(
    field_name: str,
    business: BusinessContext,
    derivations: List[DerivationTrace],
) -> Tuple[Optional[str], str]:
    """Resolve a threshold value with three-tier fallback.

    Returns (value, tier) where tier is 'manifest' or 'default'.
    """
    biz_value = getattr(business, field_name, None)
    if biz_value is not None:
        derivations.append(
            DerivationTrace(
                field=field_name,
                source=f"manifest.spec.requirements.{field_name}",
                transformation=f"{biz_value}",
                tier="manifest",
            )
        )
        return biz_value, "manifest"

    default = _DEFAULT_THRESHOLDS.get(field_name)
    if default is not None:
        derivations.append(
            DerivationTrace(
                field=field_name,
                source=f"_DEFAULT_THRESHOLDS.{field_name}",
                transformation=f"{default} (default)",
                tier="default",
            )
        )
        return default, "default"

    return None, "none"


def _severity_for(business: BusinessContext, derivations: List[DerivationTrace]) -> str:
    """Derive alert severity from criticality."""
    severity = _CRITICALITY_TO_SEVERITY.get(business.criticality, "warning")
    derivations.append(
        DerivationTrace(
            field="alert_severity",
            source="manifest.spec.business.criticality",
            transformation=f"{business.criticality} → {severity}",
            tier="manifest",
        )
    )
    return severity


def _metric_unit(metric_name: str) -> str:
    """Infer unit from metric name patterns."""
    for pattern, unit in _METRIC_UNITS.items():
        if pattern in metric_name:
            return unit
    return ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derivation_comment(derivations: List[DerivationTrace]) -> str:
    """Build a YAML comment block documenting derivation traces."""
    lines = ["# Derivation:"]
    for d in derivations:
        lines.append(f"#   {d.field}: {d.source} ({d.transformation}) [{d.tier}]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2: Alert rule generation
# ---------------------------------------------------------------------------


def generate_alert_rules(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate Prometheus alert rules for a single service.

    Creates alerts for duration metrics (latency) and request count metrics
    (availability) using convention-based metrics from service hints.
    """
    derivations: List[DerivationTrace] = []
    severity = _severity_for(business, derivations)
    rules: List[Dict[str, Any]] = []

    # Resolve thresholds
    latency_raw, _ = _resolve_threshold("latency_p99", business, derivations)
    avail_raw, _ = _resolve_threshold("availability", business, derivations)

    for metric in service.convention_metrics:
        prom = _prom_name(metric.name)

        # Duration/histogram metrics → latency alert
        if metric.type == "histogram" and "duration" in metric.name and latency_raw:
            threshold_sec = _parse_duration_to_seconds(latency_raw)
            rules.append(
                {
                    "alert": _alert_name(service.service_id, "LatencyP99High"),
                    "expr": (
                        f"histogram_quantile(0.99,\n"
                        f'  rate({prom}_bucket{{service="{service.service_id}"}}[5m])\n'
                        f") > {threshold_sec}"
                    ),
                    "for": "5m",
                    "labels": {
                        "severity": severity,
                        "service": service.service_id,
                        "protocol": service.transport,
                    },
                    "annotations": {
                        "summary": (
                            f"{service.service_id} p99 latency exceeds {latency_raw}"
                        ),
                        "source": "Derived from manifest.spec.requirements.latencyP99",
                        "dashboard_url": f"/d/obs-{service.service_id}",
                    },
                }
            )

        # Histogram duration metric → error rate alert (derived from _count)
        # The histogram's _count tracks total requests; with a status filter
        # we can derive error rate even without a dedicated counter metric.
        if (
            metric.type == "histogram"
            and "duration" in metric.name
            and avail_raw
            and not any(r.get("alert", "").endswith("ErrorRateHigh") for r in rules)
        ):
            error_filter = _error_filter_for_protocol(service.transport)
            avail_frac = _parse_availability_to_fraction(avail_raw)
            error_threshold = round(1.0 - avail_frac, 4)
            rules.append(
                {
                    "alert": _alert_name(service.service_id, "ErrorRateHigh"),
                    "expr": (
                        f"(\n"
                        f'  rate({prom}_count{{service="{service.service_id}",{error_filter}}}[5m])\n'
                        f'  / rate({prom}_count{{service="{service.service_id}"}}[5m])\n'
                        f") > {error_threshold}"
                    ),
                    "for": "5m",
                    "labels": {
                        "severity": severity,
                        "service": service.service_id,
                        "protocol": service.transport,
                    },
                    "annotations": {
                        "summary": (
                            f"{service.service_id} error rate exceeds "
                            f"{error_threshold * 100:.1f}%"
                        ),
                        "source": "Derived from manifest.spec.requirements.availability",
                        "dashboard_url": f"/d/obs-{service.service_id}",
                    },
                }
            )

        # Histogram duration metric → availability alert (derived from _count)
        # Success ratio = 1 - (error_count / total_count); alert when below target.
        if (
            metric.type == "histogram"
            and "duration" in metric.name
            and avail_raw
            and not any(r.get("alert", "").endswith("AvailabilityLow") for r in rules)
        ):
            error_filter = _error_filter_for_protocol(service.transport)
            avail_frac = _parse_availability_to_fraction(avail_raw)
            rules.append(
                {
                    "alert": _alert_name(service.service_id, "AvailabilityLow"),
                    "expr": (
                        f"(\n"
                        f'  1 - rate({prom}_count{{service="{service.service_id}",{error_filter}}}[5m])\n'
                        f'    / rate({prom}_count{{service="{service.service_id}"}}[5m])\n'
                        f") < {avail_frac}"
                    ),
                    "for": "5m",
                    "labels": {
                        "severity": severity,
                        "service": service.service_id,
                        "protocol": service.transport,
                    },
                    "annotations": {
                        "summary": (
                            f"{service.service_id} availability below {avail_raw}%"
                        ),
                        "source": "Derived from manifest.spec.requirements.availability",
                        "dashboard_url": f"/d/obs-{service.service_id}",
                    },
                }
            )

    if not rules:
        return ArtifactResult(
            artifact_type="alert_rule",
            service_id=service.service_id,
            output_path=f"alerts/{service.service_id}-alerts.yaml",
            status="skipped",
            derivations=derivations,
            error_message="No alertable metrics found",
        )

    content_dict = {
        "groups": [
            {
                "name": f"{service.service_id}.slo",
                "rules": rules,
            }
        ]
    }

    header = (
        f"# Generated by startd8 observability artifact generator\n"
        f"# Service: {service.service_id} (transport: {service.transport})\n"
        f"{_derivation_comment(derivations)}\n\n"
    )
    body = yaml.dump(content_dict, default_flow_style=False, sort_keys=False)

    return ArtifactResult(
        artifact_type="alert_rule",
        service_id=service.service_id,
        output_path=f"alerts/{service.service_id}-alerts.yaml",
        status="generated",
        content=header + body,
        derivations=derivations,
    )


def _alert_name(service_id: str, suffix: str) -> str:
    """Build PascalCase alert name from service id + suffix."""
    parts = service_id.replace("-", " ").replace("_", " ").title().replace(" ", "")
    return f"{parts}{suffix}"


def _error_filter_for_protocol(transport: str) -> str:
    """Return the PromQL label filter for error responses by protocol.

    gRPC codes per OTel semantic conventions (server-side failures only):
    - Unavailable (14): service not reachable
    - Internal (13): unhandled server error
    - Unimplemented (12): method not supported
    - DataLoss (15): unrecoverable data loss
    Unknown (2) is excluded — it is ambiguous and often client-side.
    """
    if transport == "grpc":
        return 'grpc_code=~"Unavailable|Internal|Unimplemented|DataLoss"'
    # HTTP
    return 'status=~"5.."'


# ---------------------------------------------------------------------------
# Phase 3: Dashboard spec generation
# ---------------------------------------------------------------------------


def generate_dashboard_spec(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate a DashboardSpec YAML for a single service.

    Produces one panel per convention metric with panel type derived from
    instrument type. Output is compatible with DashboardCreatorWorkflow.
    """
    derivations: List[DerivationTrace] = []
    panels: List[Dict[str, Any]] = []

    for metric in service.convention_metrics:
        prom = _prom_name(metric.name)
        panel_type = _INSTRUMENT_TO_PANEL.get(metric.type, "timeseries")
        query_tpl = _INSTRUMENT_TO_QUERY.get(metric.type)
        if not query_tpl:
            continue

        query = query_tpl.format(metric=prom, service=service.service_id)
        unit = _metric_unit(metric.name)

        # Infer group from metric name
        group = _panel_group(metric.name)

        panel: Dict[str, Any] = {
            "type": panel_type,
            "title": _panel_title(metric.name),
            "expr": query,
            "unit": unit,
            "group": group,
        }

        # Add latency threshold line if applicable
        if "duration" in metric.name and metric.type == "histogram":
            latency_raw, _ = _resolve_threshold("latency_p99", business, derivations)
            if latency_raw:
                threshold_sec = _parse_duration_to_seconds(latency_raw)
                panel["thresholds"] = [
                    {"value": None, "color": "green"},
                    {"value": threshold_sec, "color": "red"},
                ]

        panels.append(panel)

        # Add p50 and p95 quantile panels for duration histograms
        # (p99 is the primary panel above; p50/p95 support incident response)
        if "duration" in metric.name and metric.type == "histogram":
            for quantile, label in [(0.50, "p50"), (0.95, "p95")]:
                q_query = (
                    f"histogram_quantile({quantile}, "
                    f'rate({prom}_bucket{{service="{service.service_id}"}}[$__rate_interval]))'
                )
                panels.append({
                    "type": "timeseries",
                    "title": f"{_panel_title(metric.name)} ({label})",
                    "expr": q_query,
                    "unit": unit,
                    "group": group,
                })

    # Synthesize RED-completing panels if missing (REQ-KZ-OBS-200a)
    _ensure_red_coverage(panels, service, business, derivations)

    if not panels:
        return ArtifactResult(
            artifact_type="dashboard_spec",
            service_id=service.service_id,
            output_path=f"dashboards/{service.service_id}-dashboard-spec.yaml",
            status="skipped",
            derivations=derivations,
            error_message="No convention metrics to build panels from",
        )

    # Build tags
    tags = ["generated", "observability", service.transport]
    if business.criticality in ("critical", "high"):
        if business.dashboard_placement == "overview":
            tags.append("overview")

    derivations.append(
        DerivationTrace(
            field="dashboard_placement",
            source="manifest.spec.observability.dashboardPlacement",
            transformation=f"{business.dashboard_placement}",
            tier="manifest",
        )
    )

    spec_dict: Dict[str, Any] = {
        "title": f"{service.service_id} Observability",
        "uid": f"obs-{service.service_id}",
        "description": (
            f"Auto-derived observability dashboard for "
            f"{service.service_id} ({service.transport})"
        ),
        "tags": tags,
        "datasources": {"prometheus": "prometheus"},
        "panels": panels,
        "variables": [
            {"type": "prometheusDatasource", "name": "datasource", "label": "Datasource"}
        ],
    }

    header = (
        f"# Generated by startd8 observability artifact generator\n"
        f"# Service: {service.service_id} "
        f"(transport: {service.transport}"
        f"{', language: ' + service.language if service.language else ''})\n"
        f"{_derivation_comment(derivations)}\n\n"
    )
    body = yaml.dump(spec_dict, default_flow_style=False, sort_keys=False)

    return ArtifactResult(
        artifact_type="dashboard_spec",
        service_id=service.service_id,
        output_path=f"dashboards/{service.service_id}-dashboard-spec.yaml",
        status="generated",
        content=header + body,
        derivations=derivations,
    )


def _panel_title(metric_name: str) -> str:
    """Build human-readable panel title from OTel metric name."""
    # "rpc.server.duration" → "RPC Server Duration"
    return metric_name.replace(".", " ").replace("_", " ").title()


def _panel_group(metric_name: str) -> str:
    """Infer dashboard row group from metric name."""
    name_lower = metric_name.lower()
    if "duration" in name_lower:
        return "Latency"
    if "request" in name_lower and "size" in name_lower:
        return "Size"
    if "response" in name_lower and "size" in name_lower:
        return "Size"
    if "request" in name_lower:
        return "Throughput"
    return "General"


def _ensure_red_coverage(
    panels: List[Dict[str, Any]],
    service: ServiceHints,
    business: BusinessContext,
    derivations: List[DerivationTrace],
) -> None:
    """Synthesize missing Rate and Error panels for RED coverage (REQ-KZ-OBS-200a).

    Inspects existing panels to determine which RED signals are present,
    then adds synthetic panels for any that are missing. Panels are derived
    from the service's transport type (gRPC vs HTTP).
    """
    # Shared RED detection — single source of truth with the validator
    try:
        from startd8.validators.observability_artifact_checks import (
            has_rate_panel, has_error_panel,
        )
        has_rate = has_rate_panel(panels)
        has_error = has_error_panel(panels)
    except ImportError:
        # Fallback inline detection if validator not available
        exprs = [str(p.get("expr", "")).lower() for p in panels]
        has_rate = any("rate(" in e and "_count" in e and "status" not in e for e in exprs)
        has_error = any("error" in e or "status_code" in e for e in exprs)

    if has_rate and has_error:
        return  # Already have full RED coverage

    # Determine metric prefix from transport
    error_filter = _error_filter_for_protocol(service.transport)
    if service.transport == "grpc":
        duration_metric = "rpc_server_duration"
    else:
        duration_metric = "http_server_duration"

    rate_expr = (
        f'sum(rate({duration_metric}_count'
        f'{{service="{service.service_id}"}}[$__rate_interval]))'
    )
    error_expr = (
        f'sum(rate({duration_metric}_count'
        f'{{service="{service.service_id}",'
        f'{error_filter}}}[$__rate_interval]))\n'
        f'/ sum(rate({duration_metric}_count'
        f'{{service="{service.service_id}"}}[$__rate_interval]))'
    )

    if not has_rate:
        panels.append({
            "type": "timeseries",
            "title": "Request Rate",
            "expr": rate_expr,
            "unit": "reqps",
            "group": "Throughput",
        })

    if not has_error:
        error_panel: Dict[str, Any] = {
            "type": "timeseries",
            "title": "Error Rate",
            "expr": error_expr,
            "unit": "percentunit",
            "group": "Errors",
        }
        # Add error budget threshold from availability requirement
        if business.availability:
            try:
                avail = float(business.availability)
                error_budget = round(1.0 - round(avail / 100.0, 6), 6)
                error_panel["thresholds"] = [
                    {"value": None, "color": "green"},
                    {"value": error_budget, "color": "red"},
                ]
            except (ValueError, TypeError):
                pass
        panels.append(error_panel)

    # Availability gauge — shows current availability vs SLO target
    if business.availability:
        try:
            avail_target = round(float(business.availability) / 100.0, 6)
            avail_gauge_expr = (
                f"(\n"
                f"  sum(rate({duration_metric}_count"
                f'{{service="{service.service_id}"}}[1h]))\n'
                f"  - sum(rate({duration_metric}_count"
                f'{{service="{service.service_id}",'
                f'{_error_filter_for_protocol(service.transport)}}}[1h]))\n'
                f")\n"
                f"/ sum(rate({duration_metric}_count"
                f'{{service="{service.service_id}"}}[1h]))\n'
                f"or vector(1)"
            )
            panels.append({
                "type": "gauge",
                "title": "Availability (1h)",
                "expr": avail_gauge_expr,
                "unit": "percentunit",
                "group": "Availability",
                "thresholds": [
                    {"value": None, "color": "red"},
                    {"value": avail_target, "color": "green"},
                ],
            })
        except (ValueError, TypeError):
            pass


# ---------------------------------------------------------------------------
# Phase 4: SLO definition generation
# ---------------------------------------------------------------------------


def generate_slo_definitions(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate OpenSLO-format SLO definitions for a single service.

    Produces one SLO per applicable business requirement:
    - availability → ratio-based SLO (good/total requests)
    - latency_p99 → threshold-based SLO (P99 under threshold)
    """
    derivations: List[DerivationTrace] = []
    documents: List[str] = []

    # Find the right metrics for each SLO type
    histogram_metric = None
    counter_metric = None
    for m in service.convention_metrics:
        if m.type == "histogram" and "duration" in m.name and not histogram_metric:
            histogram_metric = m
        if m.type == "counter" and not counter_metric:
            counter_metric = m

    # Fallback: derive counter from histogram duration metric's _count suffix.
    # OTel histograms always have a _count companion that tracks total
    # requests — the alert generator already uses this (e.g.
    # rpc_server_duration_count).  When onboarding metadata only reports
    # histogram types (common for gRPC/HTTP convention metrics), synthesize
    # a counter reference so the availability SLO can be generated.
    if counter_metric is None and histogram_metric is not None:
        counter_metric = ConventionMetric(
            name=histogram_metric.name,
            type="counter",
            source=histogram_metric.source,
        )
        logger.info(
            "Derived counter metric from histogram %s for %s availability SLO",
            histogram_metric.name, service.service_id,
        )

    avail_raw, _ = _resolve_threshold("availability", business, derivations)
    latency_raw, _ = _resolve_threshold("latency_p99", business, derivations)
    severity = _severity_for(business, derivations)

    window = business.slo_window
    derivations.append(
        DerivationTrace(
            field="slo_window",
            source="manifest.strategy.objectives[].keyResults[].window",
            transformation=window,
            tier="manifest" if window != "30d" else "default",
        )
    )

    # Availability SLO
    if counter_metric and avail_raw:
        prom = _prom_name(counter_metric.name)
        # When the counter was derived from a histogram, the Prometheus name
        # needs a _count suffix (e.g. rpc_server_duration_count) — same
        # pattern the alert generator uses for error rate and availability.
        if "duration" in counter_metric.name and not prom.endswith("_count"):
            prom = f"{prom}_count"
        error_filter = _error_filter_for_protocol(service.transport)
        avail_target = float(avail_raw)

        slo = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {
                "name": f"{service.service_id}-availability",
                "labels": {
                    "service": service.service_id,
                    "protocol": service.transport,
                    "generated_by": "startd8",
                },
            },
            "spec": {
                "description": f"Availability SLO for {service.service_id}",
                "target": avail_target,
                "timeWindow": {"duration": window, "isRolling": True},
                "budgetPolicy": "occurrences",
                "indicator": {
                    "metadata": {
                        "name": f"{service.service_id}-availability-sli",
                    },
                    "spec": {
                        "ratioMetric": {
                            "counter": {
                                "metricSource": {
                                    "type": "prometheus",
                                    "spec": {
                                        "query": (
                                            f'rate({prom}'
                                            f'{{service="{service.service_id}"}}[5m])'
                                        ),
                                    },
                                },
                            },
                            "good": {
                                "metricSource": {
                                    "type": "prometheus",
                                    "spec": {
                                        "query": (
                                            f'rate({prom}'
                                            f'{{service="{service.service_id}",'
                                            f"{error_filter}"
                                            f"}}[5m])"
                                        ),
                                    },
                                },
                            },
                        },
                    },
                },
                "alerting": {
                    "name": f"{service.service_id}-availability-alert",
                    "labels": {"severity": severity},
                },
            },
        }
        documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))
    elif avail_raw and not counter_metric:
        logger.warning(
            "Skipping availability SLO for %s: no counter metric available "
            "(no explicit counter AND no histogram to derive from)",
            service.service_id,
        )

    # Latency SLO
    if histogram_metric and latency_raw:
        prom = _prom_name(histogram_metric.name)
        threshold_sec = _parse_duration_to_seconds(latency_raw)

        slo = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {
                "name": f"{service.service_id}-latency-p99",
                "labels": {
                    "service": service.service_id,
                    "protocol": service.transport,
                    "generated_by": "startd8",
                },
            },
            "spec": {
                "description": f"P99 latency SLO for {service.service_id}",
                "target": round(float(avail_raw), 2) if avail_raw else 99.0,
                "timeWindow": {"duration": window, "isRolling": True},
                "budgetPolicy": "occurrences",
                "indicator": {
                    "metadata": {
                        "name": f"{service.service_id}-latency-sli",
                    },
                    "spec": {
                        "thresholdMetric": {
                            "metricSource": {
                                "type": "prometheus",
                                "spec": {
                                    "query": (
                                        f"histogram_quantile(0.99, "
                                        f"rate({prom}_bucket"
                                        f'{{service="{service.service_id}"}}[5m]))'
                                    ),
                                },
                            },
                            "threshold": threshold_sec,
                            "operator": "lte",
                        },
                    },
                },
                "alerting": {
                    "name": f"{service.service_id}-latency-alert",
                    "labels": {"severity": severity},
                },
            },
        }
        documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))

    if not documents:
        return ArtifactResult(
            artifact_type="slo_definition",
            service_id=service.service_id,
            output_path=f"slos/{service.service_id}-slo.yaml",
            status="skipped",
            derivations=derivations,
            error_message="No SLO-eligible metrics or thresholds",
        )

    header = (
        f"# Generated by startd8 observability artifact generator\n"
        f"# Service: {service.service_id}\n"
        f"{_derivation_comment(derivations)}\n\n"
    )
    content = header + "---\n".join(documents)

    return ArtifactResult(
        artifact_type="slo_definition",
        service_id=service.service_id,
        output_path=f"slos/{service.service_id}-slo.yaml",
        status="generated",
        content=content,
        derivations=derivations,
    )


# ---------------------------------------------------------------------------
# Phase 4.5: Validate-with-autofix (REQ-KZ-OBS-700 + 710)
# ---------------------------------------------------------------------------


def _repair_and_validate(
    result: ArtifactResult,
    business: BusinessContext,
    transport: Optional[str] = None,
) -> ArtifactResult:
    """Apply autofix repairs, validate, compute score. Modifies result in-place.

    Runs after each generate_*() call, before disk write. Attaches
    quality dict to ArtifactResult for postmortem consumption.
    """
    if result.status != "generated" or not result.content:
        return result

    try:
        from startd8.validators.observability_artifact_checks import (
            validate_dashboard,
            validate_alerts,
            validate_slo,
        )
    except ImportError:
        return result  # validators not available — degrade gracefully

    avail = None
    if business.availability:
        try:
            avail = float(business.availability)
        except (ValueError, TypeError):
            pass

    vr = None

    if result.artifact_type == "dashboard_spec":
        vr = validate_dashboard(
            result.content, result.output_path, autofix=True,
            service_id=result.service_id, transport=transport,
        )
        # If gridPos was injected, update content with repaired YAML
        if vr.repairs_applied:
            try:
                repaired = yaml.safe_load(result.content)
                from startd8.validators.observability_artifact_checks import repair_gridpos
                repaired, _ = repair_gridpos(repaired)
                result.content = yaml.dump(repaired, default_flow_style=False, sort_keys=False)
            except Exception:
                pass

    elif result.artifact_type == "alert_rule":
        vr = validate_alerts(
            result.content, result.output_path,
            manifest_availability=avail,
            service_id=result.service_id, transport=transport,
        )

    elif result.artifact_type == "slo_definition":
        vr = validate_slo(
            result.content, result.output_path,
            manifest_availability=avail,
            autofix=True,
            service_id=result.service_id, transport=transport,
        )
        # If SLO target was repaired, update content
        if vr.repairs_applied:
            try:
                from startd8.validators.observability_artifact_checks import repair_slo_target
                repaired = yaml.safe_load(result.content)
                repaired, _ = repair_slo_target(repaired, avail)
                result.content = yaml.dump(repaired, default_flow_style=False, sort_keys=False)
            except Exception:
                pass

    if vr is not None:
        result.quality = {
            "score": round(vr.score, 4),
            "checks_passed": vr.checks_passed,
            "checks_total": vr.checks_total,
            "issues": [
                {"check": i.check, "severity": i.severity, "message": i.message}
                for i in vr.issues
            ],
            "repairs_applied": vr.repairs_applied,
        }
        # Log quality summary
        if vr.issues:
            issue_summary = ", ".join(
                f"{i.check}({i.severity[0]})" for i in vr.issues[:3]
            )
            logger.info(
                "Artifact quality: %s %s score=%.0f%% issues=[%s]",
                result.artifact_type, result.service_id,
                vr.score * 100, issue_summary,
            )

    return result


def _generate_one(
    gen_fn: Any,
    service: ServiceHints,
    business: BusinessContext,
    artifact_type: str,
    output_prefix: str,
) -> ArtifactResult:
    """Generate, validate, and score a single artifact. Catches exceptions."""
    try:
        result = gen_fn(service, business)
        return _repair_and_validate(result, business, transport=service.transport)
    except Exception:
        logger.exception("%s generation failed for %s", artifact_type, service.service_id)
        return ArtifactResult(
            artifact_type=artifact_type,
            service_id=service.service_id,
            output_path=f"{output_prefix}/{service.service_id}-{output_prefix}.yaml",
            status="error",
            error_message="Generation raised exception",
        )


# ---------------------------------------------------------------------------
# Phase 4b: Portal artifact generation (REQ-OBP-103)
# ---------------------------------------------------------------------------


def _generate_portal_artifact(
    business: BusinessContext,
    services: List[ServiceHints],
    report: GenerationReport,
    metadata: Dict[str, Any],
    output_dir: Path,
    *,
    persona: str = "operator",
    provision_url: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[ArtifactResult]:
    """Generate an onboarding portal via DashboardCreatorWorkflow.

    Builds a DashboardSpec dict from pipeline context, then routes through
    the Jsonnet → Grafana JSON pipeline for compilation and optional provisioning.

    Returns ArtifactResult or None on failure.
    """
    try:
        from startd8.observability.portal_spec_builder import build_portal_spec
    except ImportError:
        logger.warning("portal_spec_builder not available; skipping portal generation")
        return None

    project_id = business.project_id or "unknown"

    try:
        spec_dict = build_portal_spec(
            business, services, report, metadata, persona=persona,
        )
    except Exception:
        logger.exception("Portal spec build failed for %s", project_id)
        return ArtifactResult(
            artifact_type="portal",
            service_id=project_id,
            output_path=f"portal/{project_id}-portal.json",
            status="error",
            error_message="Portal spec build raised exception",
        )

    # Route through DashboardCreatorWorkflow
    portal_output_dir = output_dir / "portal"
    portal_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow

        workflow = DashboardCreatorWorkflow()
        config: Dict[str, Any] = {
            "spec": spec_dict,
            "output_dir": str(portal_output_dir),
            "dry_run": dry_run,
        }
        if provision_url:
            config["provision"] = True
            config["grafana_url"] = provision_url

        result = workflow.run(config)

        if result.success:
            uid = spec_dict.get("uid", f"portal-{project_id}")
            json_path = portal_output_dir / f"{uid}.json"
            content = ""
            if json_path.is_file():
                content = json_path.read_text()

            logger.info("Portal generated: %s", json_path)
            return ArtifactResult(
                artifact_type="portal",
                service_id=project_id,
                output_path=f"portal/{uid}.json",
                status="generated",
                content=content,
            )
        else:
            error_msg = result.output.get("error", "Unknown workflow error") if isinstance(result.output, dict) else str(result.output)
            logger.error("Portal workflow failed: %s", error_msg)
            return ArtifactResult(
                artifact_type="portal",
                service_id=project_id,
                output_path=f"portal/{project_id}-portal.json",
                status="error",
                error_message=str(error_msg),
            )
    except Exception:
        logger.exception("Portal generation failed for %s", project_id)
        return ArtifactResult(
            artifact_type="portal",
            service_id=project_id,
            output_path=f"portal/{project_id}-portal.json",
            status="error",
            error_message="DashboardCreatorWorkflow raised exception",
        )


# ---------------------------------------------------------------------------
# Phase 5: Orchestration + index file
# ---------------------------------------------------------------------------


def generate_observability_artifacts(
    onboarding_metadata_path: Path,
    output_dir: Path,
    manifest_path: Optional[Path] = None,
    dry_run: bool = False,
    portal: bool = False,
    portal_persona: str = "operator",
    portal_provision_url: Optional[str] = None,
) -> GenerationReport:
    """Top-level orchestrator.

    1. Load inputs (onboarding metadata + business context)
    2. Extract per-service hints
    3. For each service: generate alerts, dashboard spec, SLO definitions
    4. Write files and index
    5. Return generation report
    """
    metadata = load_onboarding_metadata(onboarding_metadata_path)
    services = extract_service_hints(metadata)
    business = load_business_context(manifest_path, metadata)

    report = GenerationReport(
        project_id=business.project_id,
        generated_at=_utc_now_iso(),
    )

    if not services:
        logger.warning("No services found; producing zero artifacts")
        return report

    # Per-service artifact generators — adding a new type is a tuple, not a code block
    _GENERATORS = [
        (generate_alert_rules, "alert_rule", "alerts"),
        (generate_dashboard_spec, "dashboard_spec", "dashboards"),
        (generate_slo_definitions, "slo_definition", "slos"),
    ]

    for service in services:
        for gen_fn, artifact_type, output_prefix in _GENERATORS:
            report.artifacts.append(
                _generate_one(gen_fn, service, business, artifact_type, output_prefix)
            )

    report.services_processed = len(services)
    report.services_skipped = len(
        [s for s in services if not s.convention_metrics]
    )

    # Portal generation — after per-service artifacts (REQ-OBP-103a)
    if portal:
        portal_result = _generate_portal_artifact(
            business, services, report, metadata, output_dir,
            persona=portal_persona,
            provision_url=portal_provision_url,
            dry_run=dry_run,
        )
        if portal_result is not None:
            report.artifacts.append(portal_result)

    if not dry_run:
        _write_artifacts(report.artifacts, output_dir)
        _write_index(report, business, onboarding_metadata_path, output_dir)
        _write_quality_report(report.artifacts, output_dir)

    return report


def _write_artifacts(artifacts: List[ArtifactResult], output_dir: Path) -> None:
    """Write generated YAML artifacts to disk."""
    for artifact in artifacts:
        if artifact.status != "generated" or not artifact.content:
            continue
        dest = output_dir / artifact.output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(artifact.content)
        logger.info("Wrote %s", dest)


def _write_index(
    report: GenerationReport,
    business: BusinessContext,
    onboarding_path: Path,
    output_dir: Path,
) -> None:
    """Write observability-manifest.yaml index file (REQ-UOM-004)."""
    # Collect unique derivation rules, deduplicating by (field, source, transformation)
    seen_rules: Dict[str, Dict[str, Any]] = {}
    for artifact in report.artifacts:
        for d in artifact.derivations:
            key = f"{d.field}|{d.source}|{d.transformation}"
            if key not in seen_rules:
                seen_rules[key] = {
                    "field": d.field,
                    "source": d.source,
                    "transformation": d.transformation,
                    "tier": d.tier,
                    "applied_to": [],
                }
            if artifact.service_id not in seen_rules[key]["applied_to"]:
                seen_rules[key]["applied_to"].append(artifact.service_id)

    generated = sum(1 for a in report.artifacts if a.status == "generated")
    skipped = sum(1 for a in report.artifacts if a.status == "skipped")
    errored = sum(1 for a in report.artifacts if a.status == "error")

    index: Dict[str, Any] = {
        "manifest_id": "observability-artifacts",
        "version": "1.0.0",
        "project_id": report.project_id,
        "generated_at": report.generated_at,
        "source": {
            "onboarding_metadata": str(onboarding_path),
        },
        "summary": {
            "services_processed": report.services_processed,
            "services_skipped": report.services_skipped,
            "artifacts_generated": generated,
            "artifacts_skipped": skipped,
            "artifacts_errored": errored,
        },
        "artifacts": [
            {
                "type": a.artifact_type,
                "service": a.service_id,
                "path": a.output_path,
                "status": a.status,
                **({"quality_score": a.quality["score"]} if a.quality else {}),
            }
            for a in report.artifacts
        ],
        "derivation_rules": list(seen_rules.values()),
    }

    # Quality summary (REQ-KZ-OBS-730)
    scored = [a for a in report.artifacts if a.quality]
    if scored:
        by_type: Dict[str, List[float]] = {}
        for a in scored:
            by_type.setdefault(a.artifact_type, []).append(a.quality["score"])
        quality_summary: Dict[str, Any] = {}
        for atype, scores in by_type.items():
            quality_summary[f"avg_{atype}_score"] = round(sum(scores) / len(scores), 4)
        all_scores = [a.quality["score"] for a in scored]
        quality_summary["avg_composite_score"] = round(sum(all_scores) / len(all_scores), 4)
        quality_summary["artifacts_scored"] = len(scored)
        quality_summary["total_issues"] = sum(
            len(a.quality.get("issues", [])) for a in scored
        )
        quality_summary["total_repairs"] = sum(
            len(a.quality.get("repairs_applied", [])) for a in scored
        )
        index["quality_summary"] = quality_summary

    dest = output_dir / "observability-manifest.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)

    header = "# observability-manifest.yaml\n# Generated by startd8 observability artifact generator\n\n"
    body = yaml.dump(index, default_flow_style=False, sort_keys=False)
    dest.write_text(header + body)
    logger.info("Wrote index: %s", dest)


def _write_quality_report(
    artifacts: List[ArtifactResult],
    output_dir: Path,
) -> None:
    """Write standalone observability-quality.json (REQ-KZ-OBS-730b).

    Produces a per-service breakdown of quality scores, issues, and repairs
    alongside the aggregate summary.  Uses ``compute_service_composite`` from
    ``startd8.validators.observability_artifact_checks`` when available;
    otherwise falls back to a simple average.
    """
    try:
        from startd8.validators.observability_artifact_checks import (
            compute_service_composite,
        )
    except ImportError:  # pragma: no cover
        compute_service_composite = None  # type: ignore[assignment]

    scored = [a for a in artifacts if a.quality and a.status == "generated"]
    if not scored:
        return

    # ---- per-service breakdown ----
    services: Dict[str, Dict[str, Any]] = {}
    for a in scored:
        svc = services.setdefault(a.service_id, {})
        svc[a.artifact_type] = {
            "score": a.quality["score"],
            "checks_passed": a.quality.get("checks_passed", 0),
            "checks_total": a.quality.get("checks_total", 0),
            "issues": a.quality.get("issues", []),
            "repairs_applied": a.quality.get("repairs_applied", []),
        }

    # compute per-service composite
    for svc_id, svc_data in services.items():
        dash_score = svc_data.get("dashboard_spec", {}).get("score", 0.0)
        alert_score = svc_data.get("alert_rule", {}).get("score", 0.0)
        slo_score = svc_data.get("slo_definition", {}).get("score", 0.0)
        if compute_service_composite is not None:
            composite = compute_service_composite(dash_score, alert_score, slo_score)
        else:
            present = [
                s
                for s in (dash_score, alert_score, slo_score)
                if s > 0.0
            ]
            composite = sum(present) / len(present) if present else 0.0
        svc_data["composite_score"] = round(composite, 4)

    # ---- aggregate ----
    by_type: Dict[str, List[float]] = {}
    total_issues = 0
    total_repairs = 0
    for a in scored:
        by_type.setdefault(a.artifact_type, []).append(a.quality["score"])
        total_issues += len(a.quality.get("issues", []))
        total_repairs += len(a.quality.get("repairs_applied", []))

    aggregate: Dict[str, Any] = {}
    for atype, scores in by_type.items():
        aggregate[f"avg_{atype}_score"] = round(sum(scores) / len(scores), 4)

    composites = [s["composite_score"] for s in services.values()]
    aggregate["avg_composite_score"] = (
        round(sum(composites) / len(composites), 4) if composites else 0.0
    )
    aggregate["total_issues"] = total_issues
    aggregate["total_repairs"] = total_repairs

    report: Dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": _utc_now_iso(),
        "services": services,
        "aggregate": aggregate,
    }

    dest = output_dir / "observability-quality.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + "\n")
    logger.info("Wrote quality report: %s", dest)


# ---------------------------------------------------------------------------
# Phase 6: Drift detection
# ---------------------------------------------------------------------------


def check_drift(
    onboarding_metadata_path: Path,
    output_dir: Path,
    manifest_path: Optional[Path] = None,
) -> int:
    """Compare freshly generated artifacts against existing ones in output_dir.

    Returns 0 if no drift, 1 if drift detected.
    """
    index_path = output_dir / "observability-manifest.yaml"
    if not index_path.exists():
        print(f"No existing index at {index_path}; cannot check drift")
        return 1

    with open(index_path, "r") as f:
        existing_index = yaml.safe_load(f) or {}

    # Generate fresh (in memory)
    report = generate_observability_artifacts(
        onboarding_metadata_path=onboarding_metadata_path,
        output_dir=output_dir,
        manifest_path=manifest_path,
        dry_run=True,
    )

    # Build keyed sets for comparison
    existing_keys = {
        (a["type"], a["service"])
        for a in existing_index.get("artifacts", [])
        if a.get("status") == "generated"
    }
    fresh_keys = {
        (a.artifact_type, a.service_id)
        for a in report.artifacts
        if a.status == "generated"
    }

    new_artifacts = fresh_keys - existing_keys
    removed_artifacts = existing_keys - fresh_keys
    drift_found = False

    if new_artifacts:
        drift_found = True
        print(f"NEW artifacts ({len(new_artifacts)}):")
        for art_type, svc in sorted(new_artifacts):
            print(f"  + {art_type} for {svc}")

    if removed_artifacts:
        drift_found = True
        print(f"REMOVED artifacts ({len(removed_artifacts)}):")
        for art_type, svc in sorted(removed_artifacts):
            print(f"  - {art_type} for {svc}")

    # Check threshold changes in derivation rules
    existing_rules = {
        (r.get("field"), r.get("source")): r.get("transformation")
        for r in existing_index.get("derivation_rules", [])
    }
    fresh_rules: Dict[tuple, str] = {}
    for a in report.artifacts:
        for d in a.derivations:
            key = (d.field, d.source)
            fresh_rules[key] = d.transformation

    for key, fresh_val in fresh_rules.items():
        existing_val = existing_rules.get(key)
        if existing_val and existing_val != fresh_val:
            drift_found = True
            print(f"CHANGED: {key[0]} ({key[1]}): {existing_val} → {fresh_val}")

    if not drift_found:
        print("No drift detected")
        return 0

    return 1


# ---------------------------------------------------------------------------
# Provenance extension (REQ-UOM-052)
# ---------------------------------------------------------------------------


def _append_to_provenance(
    provenance_path: Path,
    output_dir: Path,
) -> None:
    """Best-effort append observability artifacts to run-provenance.json."""
    if not provenance_path.exists():
        logger.info("No run-provenance.json at %s; skipping provenance append", provenance_path)
        return

    try:
        with open(provenance_path, "r") as f:
            provenance = json.load(f)

        inventory = provenance.get("artifact_inventory", [])
        inventory.append(
            {
                "stage": "4.5",
                "id": "observability-manifest",
                "path": str(output_dir / "observability-manifest.yaml"),
                "role": "observability-artifacts-index",
            }
        )
        provenance["artifact_inventory"] = inventory

        with open(provenance_path, "w") as f:
            json.dump(provenance, f, indent=2)
        logger.info("Appended observability entry to %s", provenance_path)
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to append to provenance at %s", provenance_path, exc_info=True)
