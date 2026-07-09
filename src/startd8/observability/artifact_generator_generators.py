# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Per-artifact generators (alerts, dashboards, SLOs, monitors, runbooks, capability index).

Extracted verbatim from ``artifact_generator.py`` (Tier-2 refactor, step 2).
"""

import json  # noqa: F401
import logging
import os
import re  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any, Dict, List, Optional, Set, Tuple  # noqa: F401

import yaml  # noqa: F401

from .taxonomy_enums import Category, Orientation, RouteState  # noqa: F401
from .artifact_generator_models import *  # noqa: F401,F403
from .metric_descriptor import MetricDescriptor, profile_for_transport

try:
    from startd8.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:  # pragma: no cover
    logger = logging.getLogger(__name__)


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


_INSTRUMENT_TO_PANEL: Dict[str, str] = {
    "histogram": "histogram",
    "counter": "timeseries",
    "gauge": "gauge",
    "up_down_counter": "timeseries",
    "observable_gauge": "gauge",
}


# PromQL query templates keyed by instrument type. The ``{selector}`` slot is a
# full ``{...}`` label selector built from the resolved MetricDescriptor (FR-4),
# so the service-identity label key (``service`` vs ``service_name``) and any
# compound matchers flow in rather than being hardcoded. For the semconv default
# the selector is ``{service="<svc>"}`` — byte-identical to the prior templates.
_INSTRUMENT_TO_QUERY: Dict[str, str] = {
    "histogram": (
        "histogram_quantile(0.99, "
        "rate({metric}_bucket{selector}[$__rate_interval]))"
    ),
    "counter": "rate({metric}_total{selector}[$__rate_interval])",
    "gauge": "{metric}{selector}",
    "up_down_counter": "{metric}{selector}",
    "observable_gauge": "{metric}{selector}",
}


_METRIC_UNITS: Dict[str, str] = {
    "duration": "s",
    "size": "bytes",
    "request": "reqps",
    "response": "bytes",
}


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

    default = (business.default_thresholds or _DEFAULT_THRESHOLDS).get(field_name)
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
    severity = (business.severity_map or _CRITICALITY_TO_SEVERITY).get(business.criticality, "warning")
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


def _descriptor_for(
    service: ServiceHints, descriptor: Optional[MetricDescriptor]
) -> MetricDescriptor:
    """Resolve the effective MetricDescriptor for a service (Step 3, FR-4).

    The orchestrator (``artifact_generator.py``) builds the descriptor once per
    service via ``resolve_descriptor`` and threads it in. When a generator is
    called standalone (tests, older call sites) with ``descriptor=None``, fall
    back to the transport default (``semconv-{transport}``), which reproduces the
    pre-Step-3 hardcoded behavior byte-for-byte.
    """
    if descriptor is not None:
        return descriptor
    return profile_for_transport(service.transport)


def _derivation_comment(derivations: List[DerivationTrace]) -> str:
    """Build a YAML comment block documenting derivation traces."""
    lines = ["# Derivation:"]
    for d in derivations:
        lines.append(f"#   {d.field}: {d.source} ({d.transformation}) [{d.tier}]")
    return "\n".join(lines)


def generate_alert_rules(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Generate Prometheus alert rules for a single service.

    Creates alerts for duration metrics (latency) and request count metrics
    (availability) using the resolved :class:`MetricDescriptor` (FR-4). The
    descriptor supplies metric names, the service-identity label, the error
    selector, and the latency unit; ``descriptor=None`` falls back to the
    transport default (``semconv-{transport}``) for byte-identical back-compat.
    """
    descriptor = _descriptor_for(service, descriptor)
    derivations: List[DerivationTrace] = []
    severity = _severity_for(business, derivations)
    rules: List[Dict[str, Any]] = []

    # Descriptor-sourced metric shapes (FR-4): names, selectors, unit.
    latency_bucket = descriptor.latency_bucket_metric
    throughput_metric = descriptor.throughput_metric
    total_selector = descriptor.selector(service.service_id)
    error_selector = descriptor.selector(service.service_id, error=True)

    # Resolve thresholds
    latency_raw, _ = _resolve_threshold("latency_p99", business, derivations)
    avail_raw, _ = _resolve_threshold("availability", business, derivations)

    for metric in service.convention_metrics:
        # Duration/histogram metrics → latency alert
        if metric.type == "histogram" and "duration" in metric.name and latency_raw:
            # FR-4a: emit the threshold in the descriptor's native unit
            # (500ms → 0.5 for seconds descriptors, 500 for millisecond ones).
            threshold = descriptor.scale_threshold_seconds(
                _parse_duration_to_seconds(latency_raw)
            )
            rules.append(
                {
                    "alert": _alert_name(service.service_id, "LatencyP99High"),
                    "expr": (
                        f"histogram_quantile(0.99,\n"
                        f'  rate({latency_bucket}{total_selector}[5m])\n'
                        f") > {threshold}"
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
            avail_frac = _parse_availability_to_fraction(avail_raw)
            error_threshold = round(1.0 - avail_frac, 4)
            rules.append(
                {
                    "alert": _alert_name(service.service_id, "ErrorRateHigh"),
                    "expr": (
                        f"(\n"
                        f'  rate({throughput_metric}{error_selector}[5m])\n'
                        f'  / rate({throughput_metric}{total_selector}[5m])\n'
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
            avail_frac = _parse_availability_to_fraction(avail_raw)
            rules.append(
                {
                    "alert": _alert_name(service.service_id, "AvailabilityLow"),
                    "expr": (
                        f"(\n"
                        f'  1 - rate({throughput_metric}{error_selector}[5m])\n'
                        f'    / rate({throughput_metric}{total_selector}[5m])\n'
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

    # REQ-OAG-205 / REQ-CDP-OBS-003 / FR-CONS-2: runbook_url base resolves env >
    # manifest > omit (OQ-8 resolved, pipeline-requirements R2-F1). Never emit the dead
    # `runbooks.example.com` placeholder.
    runbook_base = (
        os.environ.get("OBS_RUNBOOK_BASE") or business.runbook_base or ""
    ).rstrip("/")
    if runbook_base:
        for rule in rules:
            rule.setdefault("annotations", {})["runbook_url"] = (
                f"{runbook_base}/{service.service_id}/{rule['alert']}"
            )

    # Domain-metric alerts are now ACTIVE rules, rendered from observability.yaml via the
    # ObservabilitySpec (alert_renderer.render_domain_alert_rules). The old commented-out
    # `_domain_alert_todo_block` stubs are removed (M3 — accidental-complexity AC-2/AC-6:
    # declared metrics no longer get asymmetric stub-vs-rule handling on the alert path).

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

    Delegates to the transport's default convention profile
    (``profile_for_transport(...).error_selector``) — the single source of
    truth for error selectors (FR-4). Retained as a thin shim so existing
    call sites and tests that import it keep working; new code SHOULD read
    ``descriptor.error_selector`` directly.

    gRPC codes per OTel semantic conventions (server-side failures only):
    Unavailable/Internal/Unimplemented/DataLoss; Unknown is excluded as
    ambiguous. HTTP uses ``status=~"5.."``.
    """
    return profile_for_transport(transport).error_selector


def generate_dashboard_spec(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Generate a DashboardSpec YAML for a single service.

    Produces one panel per convention metric with panel type derived from
    instrument type. Query selectors bind to the resolved
    :class:`MetricDescriptor` (FR-4); ``descriptor=None`` falls back to the
    transport default for byte-identical back-compat. Output is compatible with
    DashboardCreatorWorkflow.
    """
    descriptor = _descriptor_for(service, descriptor)
    selector = descriptor.selector(service.service_id)
    derivations: List[DerivationTrace] = []
    panels: List[Dict[str, Any]] = []

    # Base name the histogram_quantile ``_bucket`` templates build on. For a
    # duration histogram this is the descriptor's latency metric (span-metrics:
    # ``duration_milliseconds``; semconv: ``rpc_server_duration`` — byte-identical
    # to the old ``_prom_name(metric.name)`` for the semconv default).
    latency_base = descriptor.latency_bucket_metric
    if latency_base.endswith("_bucket"):
        latency_base = latency_base[: -len("_bucket")]

    for metric in service.convention_metrics:
        prom = _prom_name(metric.name)
        is_latency = metric.type == "histogram" and "duration" in metric.name
        metric_base = latency_base if is_latency else prom
        panel_type = _INSTRUMENT_TO_PANEL.get(metric.type, "timeseries")
        query_tpl = _INSTRUMENT_TO_QUERY.get(metric.type)
        if not query_tpl:
            continue

        query = query_tpl.format(metric=metric_base, selector=selector)
        # FR-4a: latency panels carry the descriptor's native unit (s vs ms);
        # non-latency panels keep name-inferred units. For the semconv default
        # descriptor.latency_unit == "s", matching _metric_unit("*.duration").
        unit = descriptor.latency_unit if is_latency else _metric_unit(metric.name)

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
                # FR-4a: threshold in the descriptor's native unit.
                threshold = descriptor.scale_threshold_seconds(
                    _parse_duration_to_seconds(latency_raw)
                )
                panel["thresholds"] = [
                    {"value": None, "color": "green"},
                    {"value": threshold, "color": "red"},
                ]

        panels.append(panel)

        # Add p50 and p95 quantile panels for duration histograms
        # (p99 is the primary panel above; p50/p95 support incident response)
        if "duration" in metric.name and metric.type == "histogram":
            for quantile, label in [(0.50, "p50"), (0.95, "p95")]:
                q_query = (
                    f"histogram_quantile({quantile}, "
                    f"rate({metric_base}_bucket{selector}[$__rate_interval]))"
                )
                panels.append({
                    "type": "timeseries",
                    "title": f"{_panel_title(metric.name)} ({label})",
                    "expr": q_query,
                    "unit": unit,
                    "group": group,
                })

    # Synthesize RED-completing panels if missing (REQ-KZ-OBS-200a)
    _ensure_red_coverage(panels, service, business, derivations, descriptor)

    # Closure 1 / Gap 1: add domain panels for manifest_declared metrics,
    # grouped by intent (Cost & Tokens, Sessions, Health, Progress). These are
    # additive — the convention-based RED panels above remain the baseline.
    _add_domain_panels(panels, service, derivations, descriptor)

    # REQ-OAG-107: DB latency panels when databases were detected.
    _add_database_panels(panels, service, derivations, descriptor)

    if not panels:
        return ArtifactResult(
            artifact_type="dashboard_spec",
            service_id=service.service_id,
            output_path=f"dashboards/{service.service_id}-dashboard-spec.yaml",
            status="skipped",
            derivations=derivations,
            error_message="No convention metrics to build panels from",
        )

    # REQ-OAG-105 / Gap 5: stamp gridPos on every panel at generation time.
    _assign_gridpos(panels)

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
        # Datasource name resolves env > manifest > default (OQ-8 resolved, REQ-CDP-OBS-002
        # / R2-F2 / FR-CONS-3): OBS_PROM_DATASOURCE → spec.observability.prometheusDatasource
        # → "prometheus".
        "datasources": {
            "prometheus": (
                os.environ.get("OBS_PROM_DATASOURCE")
                or business.prometheus_datasource
                or "prometheus"
            )
        },
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


def _domain_metric_type(metric: ConventionMetric) -> str:
    """Resolve the instrument type of a declared metric.

    Prefers the explicit ``type`` field; falls back to inferring from the
    Prometheus-style name suffix when type is absent.
    """
    if metric.type:
        return metric.type
    name = metric.name.lower()
    if name.endswith("_total"):
        return "counter"
    if name.endswith(("_ratio", "_percent", "_status", "_count")):
        return "gauge"
    return "gauge"


def _domain_panel_group(metric_name: str) -> str:
    """Group a declared metric into an intent-based dashboard row.

    Domain metrics describe product behaviour, so they are grouped by what the
    operator cares about (cost, sessions, health, progress) rather than by RED.
    """
    name = metric_name.lower()
    if "cost" in name or "token" in name:
        return "Cost & Tokens"
    if "session" in name:
        return "Sessions"
    if "truncation" in name or "context_usage" in name or "context_ratio" in name:
        return "Health"
    if "task" in name or "progress" in name or "status" in name or "completeness" in name:
        return "Progress"
    return "Domain Metrics"


def _domain_unit(metric_name: str) -> str:
    """Infer a Grafana unit for a declared metric from its name."""
    name = metric_name.lower()
    if "ratio" in name or "percent" in name:
        return "percentunit"
    if name.endswith("_ms") or "_time_ms" in name:
        return "ms"
    if "cost" in name:
        return "none"
    return "short"


def _domain_query(
    metric: ConventionMetric,
    service_id: str,
    descriptor: Optional[MetricDescriptor] = None,
) -> str:
    """Build a PromQL query for a declared metric.

    Counters become rate panels; gauges/ratios are read directly. Declared
    metric names are already Prometheus-style, so (unlike convention metrics)
    no ``_total`` suffix is appended to names that already carry it.

    The service-identity selector is sourced from the resolved
    :class:`MetricDescriptor` (FR-4); ``descriptor=None`` falls back to the
    ``service=`` semconv key for byte-identical back-compat.
    """
    name = metric.name
    mtype = _domain_metric_type(metric)
    if descriptor is not None:
        label = descriptor.selector(service_id)
    else:
        label = f'{{service="{service_id}"}}'
    if mtype == "counter":
        target = name if name.endswith("_total") else f"{name}_total"
        return f"rate({target}{label}[$__rate_interval])"
    return f"{name}{label}"


def _pascal(text: str) -> str:
    """Convert a snake/dot/dash name to PascalCase (startd8_cost_total → Startd8CostTotal)."""
    cleaned = text.replace(".", " ").replace("_", " ").replace("-", " ")
    return "".join(w.title() for w in cleaned.split())


def _add_domain_panels(
    panels: List[Dict[str, Any]],
    service: ServiceHints,
    derivations: List[DerivationTrace],
    descriptor: Optional[MetricDescriptor] = None,
) -> None:
    """Append a panel per manifest_declared metric (Closure 1 / Gap 1).

    Mutates ``panels`` in place. Skips declared metrics whose query already
    appears among existing panels (dedup against convention panels), so a
    metric is never visualised twice. Selectors bind to *descriptor* (FR-4).
    """
    if not service.declared_metrics:
        return

    existing_exprs = {str(p.get("expr", "")) for p in panels}
    added = 0
    for metric in service.declared_metrics:
        query = _domain_query(metric, service.service_id, descriptor)
        if query in existing_exprs:
            continue
        mtype = _domain_metric_type(metric)
        unit = _domain_unit(metric.name)
        # Ratios/percents read best on a gauge; counters (rate) and other
        # gauges read best as a timeseries.
        if unit == "percentunit":
            panel_type = "gauge"
        elif mtype == "counter":
            panel_type = "timeseries"
        else:
            panel_type = "timeseries"
        panels.append(
            {
                "type": panel_type,
                "title": _panel_title(metric.name),
                "expr": query,
                "unit": unit,
                "group": _domain_panel_group(metric.name),
            }
        )
        existing_exprs.add(query)
        added += 1

    if added:
        derivations.append(
            DerivationTrace(
                field="domain_panels",
                source=f"instrumentation_hints.{service.service_id}.metrics.manifest_declared",
                transformation=f"{added} declared metrics → panels",
                tier="manifest",
            )
        )


def _add_database_panels(
    panels: List[Dict[str, Any]],
    service: ServiceHints,
    derivations: List[DerivationTrace],
    descriptor: Optional[MetricDescriptor] = None,
) -> None:
    """Add a DB latency panel per detected database (REQ-OAG-107).

    Only fires when the service has ``detected_databases``. Uses the OTel
    ``db.client.operation.duration`` histogram scoped by the descriptor's
    service-identity label and ``db_system`` label key (FR-1a);
    ``descriptor=None`` falls back to ``service`` / ``db_system`` for
    byte-identical back-compat.
    """
    if not service.detected_databases:
        return
    descriptor = _descriptor_for(service, descriptor)
    service_matcher = descriptor.service_matcher(service.service_id)
    db_key = descriptor.db_system_label_key
    for db in service.detected_databases:
        expr = (
            "histogram_quantile(0.99, "
            f'rate(db_client_operation_duration_bucket{{{service_matcher},'
            f'{db_key}="{db}"}}[$__rate_interval]))'
        )
        panels.append(
            {
                "type": "timeseries",
                "title": f"{db.title()} Operation Latency (p99)",
                "expr": expr,
                "unit": "s",
                "group": "Database",
            }
        )
    derivations.append(
        DerivationTrace(
            field="database_panels",
            source=f"instrumentation_hints.{service.service_id}.detected_databases",
            transformation=f"{len(service.detected_databases)} databases → latency panels",
            tier="manifest",
        )
    )


def _assign_gridpos(panels: List[Dict[str, Any]]) -> None:
    """Assign a 2-column grid layout to every panel (REQ-OAG-105).

    Positions are stamped at generation time so each panel ships deployable,
    which also makes the downstream ``repair_gridpos`` autofix a no-op — closing
    Gap 5 at the source rather than relying on a repair that did not fire.
    Mirrors the repair schema (half-width 12, height 8) for layout consistency.
    Panels that already carry a ``gridPos`` are left untouched.
    """
    w, h = 12, 8
    for i, panel in enumerate(panels):
        panel.setdefault(
            "gridPos", {"h": h, "w": w, "x": (i % 2) * 12, "y": (i // 2) * h}
        )


def _ensure_red_coverage(
    panels: List[Dict[str, Any]],
    service: ServiceHints,
    business: BusinessContext,
    derivations: List[DerivationTrace],
    descriptor: Optional[MetricDescriptor] = None,
) -> None:
    """Synthesize missing Rate and Error panels for RED coverage (REQ-KZ-OBS-200a).

    Inspects existing panels to determine which RED signals are present,
    then adds synthetic panels for any that are missing. Metric names, the
    service-identity selector, and the error selector are sourced from the
    resolved :class:`MetricDescriptor` (FR-4); ``descriptor=None`` falls back to
    the transport default for byte-identical back-compat.
    """
    descriptor = _descriptor_for(service, descriptor)
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

    # Descriptor-sourced throughput metric + selectors (FR-4). For the semconv
    # default this is rpc_server_duration_count / http_server_duration_count with
    # a {service="..."} selector — byte-identical to the prior hardcoded branch.
    throughput_metric = descriptor.throughput_metric
    total_selector = descriptor.selector(service.service_id)
    error_selector = descriptor.selector(service.service_id, error=True)

    rate_expr = (
        f'sum(rate({throughput_metric}'
        f'{total_selector}[$__rate_interval]))'
    )
    error_expr = (
        f'sum(rate({throughput_metric}'
        f'{error_selector}[$__rate_interval]))\n'
        f'/ sum(rate({throughput_metric}'
        f'{total_selector}[$__rate_interval]))'
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
            # [1h] window is intentionally kept (context-specific, not a
            # descriptor axis); only the metric name + selectors bind to the
            # descriptor (FR-4).
            avail_gauge_expr = (
                f"(\n"
                f"  sum(rate({throughput_metric}"
                f'{total_selector}[1h]))\n'
                f"  - sum(rate({throughput_metric}"
                f'{error_selector}[1h]))\n'
                f")\n"
                f"/ sum(rate({throughput_metric}"
                f'{total_selector}[1h]))\n'
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


def generate_slo_definitions(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Generate OpenSLO-format SLO definitions for a single service.

    Produces one SLO per applicable business requirement:
    - availability → ratio-based SLO (good/total requests)
    - latency_p99 → threshold-based SLO (P99 under threshold)

    Metric names, selectors, error selector, and the latency threshold unit are
    sourced from the resolved :class:`MetricDescriptor` (FR-4 / FR-4a);
    ``descriptor=None`` falls back to the transport default for byte-identical
    back-compat.
    """
    descriptor = _descriptor_for(service, descriptor)
    total_selector = descriptor.selector(service.service_id)
    error_selector = descriptor.selector(service.service_id, error=True)
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
        # Throughput counter from the descriptor (FR-4). When the counter was
        # derived from a duration histogram, the semconv default resolves to
        # ``*_duration_count`` — the same name the prior _prom_name+_count path
        # produced; span-metrics resolves to ``calls_total``.
        if "duration" in counter_metric.name:
            prom = descriptor.throughput_metric
        else:
            prom = _prom_name(counter_metric.name)
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
                                            f'{total_selector}[5m])'
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
                                            f'{error_selector}[5m])'
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
        # Latency histogram bucket base from the descriptor (FR-4). Byte-identical
        # to _prom_name(histogram_metric.name) for the semconv default.
        latency_bucket_base = descriptor.latency_bucket_metric
        if latency_bucket_base.endswith("_bucket"):
            latency_bucket_base = latency_bucket_base[: -len("_bucket")]
        prom = latency_bucket_base
        # FR-4a: threshold in the descriptor's native unit (s vs ms).
        threshold = descriptor.scale_threshold_seconds(
            _parse_duration_to_seconds(latency_raw)
        )

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
                                        f'{total_selector}[5m]))'
                                    ),
                                },
                            },
                            "threshold": threshold,
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


def _target_for(service_id: str, targets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The `spec.targets[]` entry for a service: name match, else the sole target, else None."""
    for t in targets:
        if isinstance(t, dict) and str(t.get("name", "")) == service_id:
            return t
    return targets[0] if len(targets) == 1 and isinstance(targets[0], dict) else None


def generate_service_monitor(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate a Prometheus-Operator ServiceMonitor CRD for a service.

    Scrape interval from `spec.observability.metricsInterval` and namespace from the
    matching `spec.targets[]` entry (FR-CONS-1), falling back to today's defaults.
    """
    derivations: List[DerivationTrace] = []
    scrape_interval = business.metrics_interval or "30s"
    target = _target_for(service.service_id, business.targets)
    namespace = str(target["namespace"]) if target and target.get("namespace") else None

    metadata: Dict[str, Any] = {
        "name": service.service_id,
        "labels": {
            "app": service.service_id,
            "managed-by": "startd8-observability",
        },
    }
    if namespace:
        metadata["namespace"] = namespace

    doc: Dict[str, Any] = {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "ServiceMonitor",
        "metadata": metadata,
        "spec": {
            "selector": {"matchLabels": {"app": service.service_id}},
            "endpoints": [
                {"port": "metrics", "path": "/metrics", "interval": scrape_interval}
            ],
        },
    }
    derivations.append(
        DerivationTrace(
            field="service_monitor.selector",
            source="service_id",
            transformation=f"app={service.service_id}",
            tier="default",
        )
    )
    derivations.append(DerivationTrace(
        field="scrape_interval",
        source="manifest.spec.observability.metricsInterval" if business.metrics_interval else "default",
        transformation=f"interval={scrape_interval}",
        tier="manifest" if business.metrics_interval else "default",
    ))
    if namespace:
        derivations.append(DerivationTrace(
            field="namespace", source="manifest.spec.targets[].namespace",
            transformation=f"namespace={namespace}", tier="manifest",
        ))
    header = (
        f"# Generated by startd8 observability artifact generator\n"
        f"# Service: {service.service_id} (transport: {service.transport})\n"
        f"{_derivation_comment(derivations)}\n\n"
    )
    return ArtifactResult(
        artifact_type="service_monitor",
        service_id=service.service_id,
        output_path=f"service-monitors/{service.service_id}-servicemonitor.yaml",
        status="generated",
        content=header + yaml.dump(doc, default_flow_style=False, sort_keys=False),
        derivations=derivations,
    )


# A channel identifier shaped like an email routes to email_configs, not slack_configs
# (REQ-CDP-OBS-005 allows Slack names, PagerDuty keys, or email addresses).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def generate_notification_policy(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate an Alertmanager routing policy scoped to a service.

    Routes to the manifest's `spec.observability.alertChannels` (FR-CONS-1), falling
    back to `metadata.owners[].slack`. Owner emails (and email-shaped channels) become
    `email_configs`. The channel is the per-project input; the Slack webhook *transport*
    is an environment secret (OQ-6), referenced as `${SLACK_API_URL}` — NOT a fabricated
    `REPLACE_WITH_WEBHOOK_URL`. With no channels resolvable, the receiver carries no
    transport and `alertChannels` is recorded as unresolved REQUIRED (REQ-CDP-INT-007).
    """
    derivations: List[DerivationTrace] = []
    severity = _severity_for(business, derivations)
    receiver = f"{service.service_id}-{severity}"

    channels = business.routing_channels()
    slack_channels = [c for c in channels if not _EMAIL_RE.match(c)]
    channel_emails = [c for c in channels if _EMAIL_RE.match(c)]
    owner_emails = [
        str(o["email"]) for o in business.owners
        if isinstance(o, dict) and o.get("email")
    ]
    all_emails = list(dict.fromkeys(owner_emails + channel_emails))

    receiver_doc: Dict[str, Any] = {"name": receiver}
    if slack_channels:
        receiver_doc["slack_configs"] = [
            {"channel": ch, "api_url": "${SLACK_API_URL}", "send_resolved": True}
            for ch in slack_channels
        ]
    if channels:
        derivations.append(DerivationTrace(
            field="alert_channels", source="manifest.spec.observability.alertChannels",
            transformation=f"slack={slack_channels} email={channel_emails}", tier="manifest",
        ))
    else:
        derivations.append(DerivationTrace(
            field="alert_channels", source="manifest.spec.observability.alertChannels",
            transformation="unresolved_required (REQ-CDP-INT-007) — no transport emitted",
            tier="default",
        ))
    if all_emails:
        receiver_doc["email_configs"] = [{"to": e} for e in all_emails]
        derivations.append(DerivationTrace(
            field="owner_contacts",
            source="manifest.metadata.owners[].email + email-shaped alertChannels",
            transformation=f"email → {all_emails}", tier="manifest",
        ))

    doc: Dict[str, Any] = {
        "route": {
            "routes": [
                {
                    "matchers": [f"service = {service.service_id}"],
                    "receiver": receiver,
                    "group_by": ["alertname", "service"],
                    "group_wait": "30s",
                    "repeat_interval": "4h",
                }
            ]
        },
        "receivers": [receiver_doc],
    }
    header_lines = [
        "# Generated by startd8 observability artifact generator",
        f"# Service: {service.service_id} — notification routing by severity",
    ]
    if channels:
        header_lines.append(
            "# Channels from manifest; set the SLACK_API_URL secret at deploy time "
            "(the webhook transport is environment config, not a per-project input)."
        )
    else:
        header_lines.append(
            "# UNRESOLVED REQUIRED PARAM: no alertChannels (or owners[].slack) in the "
            "manifest — receiver has no transport. Populate spec.observability.alertChannels "
            "upstream (REQ-CDP-OBS-005). No webhook URL was fabricated."
        )
    header = "\n".join(header_lines) + f"\n{_derivation_comment(derivations)}\n\n"
    return ArtifactResult(
        artifact_type="notification_policy",
        service_id=service.service_id,
        output_path=f"notifications/{service.service_id}-notification-policy.yaml",
        status="generated",
        content=header + yaml.dump(doc, default_flow_style=False, sort_keys=False),
        derivations=derivations,
    )


def generate_loki_rule(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Generate a Loki ruler alerting rule for a service's error logs.

    Log selector derived from `spec.targets[].name` (FR-CONS-1, REQ-CDP-OBS-006),
    falling back to the service_id. The LogQL *stream label key* comes from the
    descriptor (FR-1a) — it may differ from the PromQL label key. ``descriptor=
    None`` falls back to the ``service`` key for byte-identical back-compat.
    """
    descriptor = _descriptor_for(service, descriptor)
    stream_key = descriptor.logql_stream_key()
    derivations: List[DerivationTrace] = []
    severity = _severity_for(business, derivations)
    target = _target_for(service.service_id, business.targets)
    selector_name = str(target["name"]) if target and target.get("name") else service.service_id
    if target and target.get("name"):
        derivations.append(DerivationTrace(
            field="loki.selector", source="manifest.spec.targets[].name",
            transformation=f'{stream_key}="{selector_name}"', tier="manifest",
        ))
    expr = (
        f'sum(rate({{{stream_key}="{selector_name}"}} |= "error" [5m])) > 0'
    )
    doc: Dict[str, Any] = {
        "groups": [
            {
                "name": f"{service.service_id}.logs",
                "rules": [
                    {
                        "alert": _alert_name(service.service_id, "HighErrorLogRate"),
                        "expr": expr,
                        "for": "5m",
                        "labels": {"severity": severity, "service": service.service_id},
                        "annotations": {
                            "summary": (
                                f"{service.service_id} is emitting error-level logs"
                            ),
                            "dashboard_url": f"/d/obs-{service.service_id}",
                        },
                    }
                ],
            }
        ]
    }
    header = (
        f"# Generated by startd8 observability artifact generator\n"
        f"# Service: {service.service_id} — Loki log-based alerting\n"
        f"{_derivation_comment(derivations)}\n\n"
    )
    return ArtifactResult(
        artifact_type="loki_rule",
        service_id=service.service_id,
        output_path=f"loki-rules/{service.service_id}-loki-rules.yaml",
        status="generated",
        content=header + yaml.dump(doc, default_flow_style=False, sort_keys=False),
        derivations=derivations,
    )


def generate_runbook(
    service: ServiceHints,
    business: BusinessContext,
) -> ArtifactResult:
    """Generate an incident runbook (markdown) for a service."""
    derivations: List[DerivationTrace] = []
    severity = _severity_for(business, derivations)
    avail = business.availability or "—"
    latency = business.latency_p99 or "—"
    lines = [
        f"# Runbook: {service.service_id}",
        "",
        f"> Generated by startd8 observability artifact generator.",
        "",
        "## Service summary",
        "",
        f"- **Transport:** {service.transport}",
        f"- **Language:** {service.language or 'unknown'}",
        f"- **Criticality:** {business.criticality} (alert severity: {severity})",
        f"- **Availability target:** {avail}",
        f"- **Latency p99 target:** {latency}",
    ]
    if service.detected_databases:
        lines.append(f"- **Databases:** {', '.join(service.detected_databases)}")
    lines += [
        "",
        "## Dashboards",
        "",
        f"- Grafana: `/d/obs-{service.service_id}`",
        "",
        "## Alerts",
        "",
        f"- Latency / error-rate / availability alerts fire at severity "
        f"**{severity}** (see `alerts/{service.service_id}-alerts.yaml`).",
        "",
        "## First response",
        "",
        "1. Open the dashboard above; check the RED panels (rate, errors, duration).",
        "2. Correlate with recent deploys and the error-rate panel.",
        "3. Check logs for error spikes "
        f"(`{{service=\"{service.service_id}\"}} |= \"error\"`).",
        "",
        "## Escalation",
        "",
        f"- {'Page on-call immediately.' if severity == 'critical' else 'Notify the owning team.'}",
    ]
    # Escalation contacts from metadata.owners (FR-CONS-1), else spec.business.owner.
    owner_lines: List[str] = []
    for o in business.owners:
        if not isinstance(o, dict):
            continue
        parts = []
        if o.get("team"):
            parts.append(f"team **{o['team']}**")
        if o.get("email"):
            parts.append(str(o["email"]))
        if o.get("slack"):
            parts.append(str(o["slack"]))
        if parts:
            owner_lines.append("- Contact: " + " · ".join(parts))
    if owner_lines:
        derivations.append(DerivationTrace(
            field="escalation.contacts", source="manifest.metadata.owners",
            transformation=f"{len(owner_lines)} owner(s)", tier="manifest",
        ))
    elif business.owner:
        owner_lines = [f"- Owner: {business.owner}"]
    else:
        owner_lines = ["- Owner: _not set — populate manifest.metadata.owners (REQ-CDP-OBS-007)_"]
    lines += owner_lines + [""]
    return ArtifactResult(
        artifact_type="runbook",
        service_id=service.service_id,
        output_path=f"runbooks/{service.service_id}-runbook.md",
        status="generated",
        content="\n".join(lines),
        derivations=derivations,
    )


_ARTIFACT_TYPE_TO_CATEGORY = {
    "dashboard": "observe",
    "dashboard_spec": "observe",
    "alert_rule": "observe",
    "prometheus_rule": "observe",
    "slo_definition": "observe",
    "loki_rule": "observe",
    "service_monitor": "integration",
    "notification_policy": "action",
    "runbook": "reference",
}


_CAPABILITY_INDEX_EXCLUDE = frozenset({"capability_index", "dashboard_spec"})


def generate_capability_index(
    services: List[ServiceHints],
    business: BusinessContext,
    report: GenerationReport,
) -> ArtifactResult:
    """Generate a conformant capability-index manifest for the provisioned
    observability (Run-007 Finding 2).

    Emits the schema the contract declares — ``manifest_id``, ``version``, and a
    ``capabilities[]`` list (each entry carries ``capability_id``, ``category``,
    ``maturity``, ``summary``, ``evidence``) — describing what observability was
    provisioned, rather than the previous ad-hoc inventory which did not match
    the ``[capabilities, version, manifest_id]`` contract and would not parse as
    a capability index.
    """
    project_id = business.project_id or report.project_id or "project"
    # Single-token slug for capability ids (strip run-id / path noise).
    slug = re.split(r"[/\\]", str(project_id))[0] or "project"

    capabilities: List[Dict[str, Any]] = []
    seen: set = set()
    for a in report.artifacts:
        if a.status != "generated" or a.artifact_type in _CAPABILITY_INDEX_EXCLUDE:
            continue
        cap_id = f"{slug}.observability.{a.service_id}.{a.artifact_type}"
        if cap_id in seen:
            continue
        seen.add(cap_id)
        capabilities.append(
            {
                "capability_id": cap_id,
                "category": _ARTIFACT_TYPE_TO_CATEGORY.get(a.artifact_type, "observe"),
                "maturity": "beta",
                "summary": (
                    f"{a.artifact_type.replace('_', ' ')} provisioned for "
                    f"{a.service_id}"
                ),
                "evidence": [a.output_path],
            }
        )

    doc: Dict[str, Any] = {
        "manifest_id": f"{slug}.observability.agent",
        "name": f"{business.project_name or slug} Observability Capabilities",
        "version": "1.0.0",
        "capabilities": capabilities,
    }
    header = (
        f"# Generated by startd8 observability artifact generator\n"
        f"# Capability index for observability provisioned on {project_id}\n\n"
    )
    return ArtifactResult(
        artifact_type="capability_index",
        service_id=project_id,
        output_path="capability-index.yaml",
        status="generated",
        content=header + yaml.dump(doc, default_flow_style=False, sort_keys=False),
    )
