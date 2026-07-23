# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Per-artifact generators (alerts, dashboards, SLOs, monitors, runbooks, capability index).

Extracted verbatim from ``artifact_generator.py`` (Tier-2 refactor, step 2).
"""

import dataclasses
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
from .metric_descriptor import (
    BASE_RED_KINDS,
    NON_EMITTING_CONVENTION_SURFACES,
    SPAN_METRICS_TEMPO_PROFILE,
    MetricDescriptor,
    profile_for,
    profile_for_kinds,
    profile_for_transport,
    resolve_sli_kinds,
)
from .spec import Receiver

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


def _select_importance_default(business: "BusinessContext", field_name: str) -> Optional[str]:
    """Importance-scaled default for ``field_name`` (FR-2), or ``None`` to fall through.

    The VALUES come from a config file (``config/importance_thresholds.yaml``), loaded + manifest-
    overridden by ``obs_config.load_importance_thresholds`` and carried on
    ``business.importance_thresholds`` (nested ``<criticality>.<deployment_mode|default>.<field>``).
    When the context did not load it (e.g. a directly-constructed ``BusinessContext``), the config-
    file base is loaded here — nothing is hardcoded in this module. ``deployment_mode`` is read
    ``None``-safely so this works before Increment 2 adds the field. Returns ``None`` when the
    criticality/mode/field is not in the table (e.g. ``throughput``), so the caller falls back to the
    flat ``_DEFAULT_THRESHOLDS``.
    """
    table = business.importance_thresholds
    if table is None:
        from .obs_config import load_importance_thresholds

        table = load_importance_thresholds(None)
    crit_row = table.get(business.criticality) or {}
    mode_key = getattr(business, "deployment_mode", None) or "default"
    cell = crit_row.get(mode_key) or crit_row.get("default") or {}
    return cell.get(field_name)


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
    """Resolve a threshold value with fallback tiers.

    Returns (value, tier) where tier is 'manifest', 'default:importance', or 'default'.
    Authored (manifest) values always win; when none is authored, an importance-scaled default
    (FR-2, keyed on criticality[/deployment_mode]) is preferred over the flat default.
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

    # Importance-scaled default (FR-2/FR-3): derived, never authored — emitted under a distinct
    # `default:importance` tier so it is not laundered into `tier="manifest"` (NR-4).
    importance = _select_importance_default(business, field_name)
    if importance is not None:
        mode = getattr(business, "deployment_mode", None) or "-"
        derivations.append(
            DerivationTrace(
                field=field_name,
                source="_IMPORTANCE_THRESHOLDS",
                transformation=f"{mode} + {business.criticality} → {field_name} {importance}",
                tier="default:importance",
            )
        )
        return importance, "default:importance"

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
        d = descriptor
    else:
        # #226 FR-6: honor a declared workload kind in the standalone path too (kind wins
        # over transport). Empty kinds ⇒ transport default (byte-identical to pre-#226).
        d = profile_for_kinds(service.kinds, service.transport)
    # #275: bind the SLI label VALUE to the subject's real OTel service.name (slash
    # preserved) when onboarding carries it — else the selector `service="mastodonweb"`
    # never matches `mastodon/web` telemetry. Absent/equal ⇒ the {service_id} default
    # (byte-identical). Braces escaped so `.format(service_id=...)` treats it as a literal.
    real = getattr(service, "service_name", "") or ""
    if real and real != service.service_id:
        d = dataclasses.replace(
            d, service_label_value_tpl=real.replace("{", "{{").replace("}", "}}")
        )
    return d


def _service_sli_kinds(service: ServiceHints, business: BusinessContext) -> "frozenset[str]":
    """The resolved SLI-kind set for a service (#226 FR-12), the single source used by
    the FR-12a triplet gate and the FR-13 signal-coverage gate. Unions the service's
    declared functional[] signal_kinds with its kind/transport-implied defaults."""
    frs = getattr(business, "functional_requirements", None) or ()
    signals = [
        getattr(f, "signal_kind", "")
        for f in frs
        if getattr(f, "service", None) in (None, "", service.service_id)
    ]
    resolved = resolve_sli_kinds(service.kinds, signals, service.transport)
    # #274 / REQ-CCL-106: a DECLARED non-emitting metrics_surface means the OTel-convention meter
    # metric the base RED triple queries is not emitted → drop the RED triple so no dead
    # availability/latency/throughput SLI is shipped. Declared functional signals (non-triplet)
    # are kept. Absent surface ⇒ unknown ⇒ RED stays (the #277 advisory flags the risk instead).
    if getattr(service, "metrics_surface", "") in NON_EMITTING_CONVENTION_SURFACES:
        resolved = resolved - _TRIPLET_SIGNAL_KINDS
    # #286: a RED kind bound to a declared-emitted REAL series is emitted by
    # generate_declared_base_slos against that series → drop the CONVENTION RED for that kind here
    # so we never ALSO ship a (possibly-dead) convention SLI (precedence: declared > convention).
    # Absent declared series ⇒ no-op (byte-identical to pre-#286).
    resolved = resolved - _declared_covered_kinds(service)
    return resolved


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

    # FR-12a: the SLI-kind gate is ANDed with the per-metric gate below (never
    # replaces it) — a block emits iff its SLI kind ∈ the resolved set AND its source
    # metric is present. A request service resolves to the RED triple ⇒ byte-identical.
    sli_kinds = _service_sli_kinds(service, business)

    for metric in service.convention_metrics:
        # Duration/histogram metrics → latency alert
        if (
            metric.type == "histogram"
            and "duration" in metric.name
            and latency_raw
            and "latency" in sli_kinds  # FR-12a
        ):
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
            and "availability" in sli_kinds  # FR-12a
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
            and "availability" in sli_kinds  # FR-12a
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

    # #274: on a declared non-emitting metrics_surface (traces_only/…), the convention metrics
    # are aspirational (not emitted) → skip their dashboard panels so no dead meter panel renders,
    # matching the SLO/alert suppression. `_ensure_red_coverage` below is likewise sli_kinds-gated,
    # so a traces-only dashboard carries no dead RED panel. Absent surface ⇒ unchanged.
    _panel_metrics = (
        [] if service.metrics_surface in NON_EMITTING_CONVENTION_SURFACES
        else service.convention_metrics
    )
    for metric in _panel_metrics:
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

    # Datasource UID binding (REQ_DATASOURCE_UID_BINDING FR-4): when ContextCore
    # resolved a real Grafana datasource UID for this service, inject it via
    # config_overrides (the supported path into the renderer's config.datasources)
    # under a key the base config lacks — so panels bind to the real UID. No UID ⇒
    # nothing is injected and the output is byte-identical to today's (FR-7).
    _bound: Dict[str, Any] = {}
    _prom_uid = (service.datasource_uids or {}).get("prometheus")
    if _prom_uid:
        _bound["prometheusBound"] = {"uid": _prom_uid, "type": "prometheus"}
    _loki_uid = (service.datasource_uids or {}).get("loki")
    if _loki_uid:
        _bound["lokiBound"] = {"uid": _loki_uid, "type": "loki"}
    if _bound:
        spec_dict["config_overrides"] = {"datasources": _bound}
        derivations.append(
            DerivationTrace(
                field="datasource_uid",
                source="manifest.spec.observability.datasources (or per-target)",
                transformation=", ".join(f"{k}={v['uid']}" for k, v in _bound.items()),
                tier="manifest",
            )
        )

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
    """Backfill the panels the resolved SLI-kind set implies (#226 FR-13).

    Formerly ``_ensure_red_coverage``: it unconditionally synthesized Rate/Error/
    Availability panels for *every* service, assuming every service is a request
    server. It is now **gated on the resolved SLI-kind set** (FR-12): Request-Rate
    iff ``throughput`` ∈ set, Error-Rate + the Availability(1h) gauge (FR-13a — an
    availability-kind artifact, not RED-completion) iff ``availability`` ∈ set. A
    service whose set implies neither is a **no-op** (the deletion of the
    unconditional path). Metric names/selectors come from the resolved
    :class:`MetricDescriptor` (FR-4); ``descriptor=None`` ⇒ transport/kind default.
    Byte-parity: a request service resolves to the RED triple ⇒ identical output.
    """
    descriptor = _descriptor_for(service, descriptor)
    # FR-12: what SLI kinds is this service actually observed by? (Shared resolver —
    # same set the FR-12a alert/SLO gate uses.)
    sli_kinds = _service_sli_kinds(service, business)
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
    # FR-13: the load-bearing deletion of the unconditional path. Nothing to
    # synthesize when the resolved set implies neither throughput nor availability
    # (e.g. a cron observed only by freshness/run_success) — no fabricated panels.
    want_rate = "throughput" in sli_kinds
    want_error = "availability" in sli_kinds
    if not want_rate and not want_error:
        return

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

    if not has_rate and want_rate:
        panels.append({
            "type": "timeseries",
            "title": "Request Rate",
            "expr": rate_expr,
            "unit": "reqps",
            "group": "Throughput",
        })

    if not has_error and want_error:
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

    # Availability gauge (FR-13a) — an availability-kind artifact, gated on
    # `availability` ∈ the resolved set (it fires on business.availability alone,
    # independent of has_rate/has_error, so it needs its own gate).
    if business.availability and want_error:
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


#: Per-signal_kind SLO template for the NON-request kinds (#226 FR-5). Each maps a
#: declared functional[] signal_kind to (**candidate series** (preference-ordered), shape,
#: unit). The series is bound to the service by ``_select_functional_metric``: the candidate
#: the service actually DECLARES wins (FR-6a — *source* the series, don't assume a single
#: name); else the first candidate. Candidates cover only the conventions we have EVIDENCE
#: for. The ``lag`` Kafka-JMX series were verified present in a live OTel-demo Kafka-consumer
#: fleet (2026-07-22, ``frauddetectionservice``), where every ``messaging_client_*`` /
#: ``resource_utilization_ratio`` / ``job_*`` name we assumed returned **zero** — so the
#: evidenced series lead and the (unverified) semconv-draft name is retained only as a
#: trailing candidate. Other kinds keep their single (still-unverified) convention until a
#: fleet grounds them (OQ-5). The FR's ``target`` is the threshold; ``custom`` carries its
#: own PromQL. Kinds absent here (or an FR with no ``target``) are *unfulfilled* → FR-9.
_FUNCTIONAL_SLI_TEMPLATES = {
    "queue_depth": (("messaging_client_queued_messages",), "gauge_max", "short"),
    "lag": (
        # Kafka JMX (verified real, 2026-07-22 OTel-demo) → semconv-draft (unverified).
        ("kafka_consumer_records_lag_max", "kafka_consumer_records_lag",
         "messaging_client_consumer_lag_messages"),
        "gauge_max", "short",
    ),
    "retry_rate": (("messaging_client_retries_total",), "rate", "short"),
    "saturation": (("resource_utilization_ratio",), "gauge_max", "percentunit"),
    "freshness": (("job_last_success_timestamp_seconds",), "age", "s"),
    "run_success": (("job_runs_total",), "ratio", "ratio"),
    # AI-agent / LLM-integration signal_kinds (docs/design/ai-agent-observability, FR-1).
    # UNLIKE the worker rows above these series are GROUNDED + live (verified in Mimir
    # 2026-07-22) — the SDK already emits them under `category: ai_agent_observability`
    # (costs/otel_metrics.py, session_tracking.py). Only the threshold VALUES stay deferred
    # (OQ-1). They are project/model-scoped (see _PROJECT_SCOPED_SIGNAL_KINDS), not per-service.
    "llm_cost_per_request": (("startd8_cost_per_request_USD",), "quantile", "USD"),
    "token_throughput": (("startd8_cost_output_tokens_total",), "rate", "short"),
    "context_saturation": (("startd8_context_usage_ratio",), "gauge_max", "percentunit"),
}
#: signal_kinds already covered by the convention triplet — single-sourced (metric_descriptor).
_TRIPLET_SIGNAL_KINDS = BASE_RED_KINDS

#: signal_kinds whose series are labeled model/provider/project (NOT the per-service
#: identity) — the AI-agent family (FR-2a). Their SLO query must NOT carry a `{service=...}`
#: selector (their series have no `service` label; it would match nothing), so they bind on
#: an aggregate/project scope — matching the live-verified §6 PromQL.
_PROJECT_SCOPED_SIGNAL_KINDS = frozenset(
    {"llm_cost_per_request", "token_throughput", "context_saturation"}
)


def _select_functional_metric(candidates: Tuple[str, ...], service: ServiceHints) -> str:
    """Bind a functional SLI to the series the SERVICE actually emits (FR-6a): the first
    candidate present in its declared/convention metrics wins; else the primary candidate.

    A worker often reports **no** native metrics in onboarding (OQ-5), so the fallback to
    ``candidates[0]`` is the common path — which is why the primary must be the series with
    real evidence of existing, not an aspirational one. Names compare dot/underscore-
    insensitively (OTel dotted ``kafka.consumer.records.lag.max`` vs PromQL underscored).
    """
    emitted = {
        m.name.replace(".", "_")
        for m in (list(service.convention_metrics or []) + list(service.declared_metrics or []))
    }
    for cand in candidates:
        if cand.replace(".", "_") in emitted:
            return cand
    return candidates[0]


# #286 / REQ-CCL-107: the threshold-shaped base RED kinds a declared-emitted series binds, mapped to
# the _functional_sli_query shape + the threshold field the SLO target resolves from. latency = p99
# on the histogram `_bucket`; throughput = request rate. availability is NOT here — it is a good/total
# RATIO (not a threshold shape), handled separately and only when the series carries an error_selector.
_DECLARED_SLI_SHAPE: Dict[str, Tuple[str, str]] = {
    "latency": ("quantile", "latency_p99"),
    "throughput": ("rate", "throughput"),
}


def _resolve_declared_shape(
    kind: str, series_type: str
) -> "Optional[Tuple[str, str]]":
    """Resolve the (PromQL shape, threshold field) for a declared series covering *kind*, honoring
    the series' declared ``type`` (#300 defect C).

    The kind's default shape assumes a metric family — ``latency`` ⇒ ``quantile`` (histogram_quantile
    over the ``_bucket`` series), ``throughput`` ⇒ ``rate`` (counter). A series declared as a
    ``gauge`` has neither a ``_bucket`` nor a counter to ``rate()`` — so the default shape queries a
    series that doesn't exist and the SLI returns nothing. The DECLARED type wins over the kind's
    template: a gauge binds as ``gauge_max`` (the current value), whatever kind it covers, keeping the
    threshold field so the target still resolves. Unknown kind ⇒ ``None`` (deferred by the caller)."""
    base = _DECLARED_SLI_SHAPE.get(kind)
    if base is None:
        return None
    _shape, threshold_field = base
    if series_type == "gauge":
        return ("gauge_max", threshold_field)
    return base


#: A PromQL matcher key at the head of a fragment — ``status`` in ``status=~"5.."`` (any of
#: ``= != =~ !~``). Used to drop a base label that the error_selector already constrains, so the
#: availability good-subset never carries two matchers for the same key (#300 defect B).
_MATCHER_KEY_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=~|!~|!=|=)")


def _equality_matchers(labels: Dict[str, str]) -> List[str]:
    """The ``key="value"`` equality matchers for a series' declared labels, **excluding empty-valued
    labels** (#300 defect A). An author writes ``labels: {method: "", status: ""}`` to declare the
    series is *dimensioned* by method/status — NOT to pin them to the empty string. Rendering
    ``{method="",status=""}`` is a correctness bug: ``method=""`` matches only series where the label
    is absent, excluding every real labelled series. An empty value ⇒ aggregate over that dimension
    (omit it from the selector); only labels with a concrete value become equality matchers. Sorted
    for deterministic output."""
    return [f'{k}="{v}"' for k, v in sorted(labels.items()) if v != ""]


def _declared_series_selector(labels: Dict[str, str]) -> str:
    """A PromQL label selector from the series' declared labels ({} ⇒ no selector). The labels are
    author-declared ground truth (job_name/queue_name/…), NOT necessarily service.name — so this
    binds where the real series actually lives. Empty-valued labels are aggregation dimensions, not
    matchers, and are omitted (#300 defect A)."""
    matchers = _equality_matchers(labels)
    return "{" + ",".join(matchers) + "}" if matchers else ""


def _declared_error_selector(labels: Dict[str, str], error_selector: str) -> str:
    """#286 v2: merge the series' base labels with its ERROR matcher fragment into one selector,
    for the availability ratio's error subset — e.g. labels ``{method="POST"}`` + ``status=~"5.."``
    ⇒ ``{method="POST",status=~"5.."}``. No labels ⇒ ``{status=~"5.."}``.

    Empty-valued labels are dropped (#300 defect A), and any base label whose key the
    ``error_selector`` already constrains is dropped too, so the good-subset never carries two
    matchers for one key (#300 defect B — e.g. ``{status=""}`` + ``status=~"5.."`` yielded the
    PromQL-rejected ``{status="",status=~"5.."}``)."""
    err_keys = set(_MATCHER_KEY_RE.findall(error_selector)) if error_selector else set()
    parts = [
        f'{k}="{v}"' for k, v in sorted(labels.items()) if v != "" and k not in err_keys
    ]
    if error_selector:
        parts.append(error_selector)
    return "{" + ",".join(parts) + "}" if parts else ""


def _declared_series_binds_availability(s: "DeclaredEmittedSeries") -> bool:
    """A series binds availability only when it both ``covers`` it AND carries an error_selector
    (a correct good/total ratio is impossible without the error subset)."""
    return "availability" in s.covers and bool(s.error_selector)


def _series_slug(name: str) -> str:
    """A name-safe token from a series name, so two declared series covering the SAME kind get
    UNIQUE SLO/SLI/alert names instead of colliding on ``{svc}-{kind}-declared`` (#286). e.g.
    ``http_request_duration_seconds`` → ``http-request-duration-seconds``."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "series"


def _declared_covered_kinds(service: ServiceHints) -> "frozenset[str]":
    """The base RED kinds a service's declared-emitted series can bind: latency/throughput (always),
    plus availability when a series carries an error_selector (#286 v2). Drives BOTH the precedence-
    suppression of the convention RED in ``_service_sli_kinds`` and emission in
    ``generate_declared_base_slos``. Empty ⇒ no declared binding (byte-identical)."""
    covered: set = set()
    for s in getattr(service, "declared_emitted_series", None) or ():
        covered |= {k for k in s.covers if k in _DECLARED_SLI_SHAPE}
        if _declared_series_binds_availability(s):
            covered.add("availability")
    return frozenset(covered)


def generate_declared_base_slos(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Emit a base RED SLO bound to an author-declared REAL emitted series (#286 / REQ-CCL-107 Part B).

    Precedence **declared > suppress > convention**: when the author declares a real series that
    ``covers`` a base RED kind, bind the SLI to ``<series>{<declared labels>}`` — instead of the
    #274 suppression or a convention metric the subject may not emit. Binds **latency** (p99 on the
    histogram ``_bucket``) and **throughput** (request rate); **availability** binds as a good/total
    ratio when the series carries an ``error_selector`` (#286 v2), else it is recorded *deferred*. No
    declared series ⇒ ``skipped`` (byte-identical to pre-#286). The convention RED for a bound kind is
    suppressed in ``_service_sli_kinds`` so this never double-emits."""
    series = getattr(service, "declared_emitted_series", None) or ()
    svc = service.service_id
    documents: List[str] = []
    bound: List[Dict[str, str]] = []
    deferred: List[Dict[str, str]] = []
    severity = _severity_for(business, [])
    # #307 §2.0: span > declared-series precedence. A kind a declared span signal owns is bound by
    # the span lane; this base lane skips it (recorded) so a kind covered by BOTH emits exactly once.
    span_owned = _declared_span_covered_kinds(service)

    def _meta(kind: str, series_name: str, slug: str) -> Dict[str, Any]:
        # #286: the series slug disambiguates two series covering the same kind (else the
        # SLO name collides on `{svc}-{kind}-declared` and an OpenSLO apply drops one).
        return {
            "name": f"{svc}-{kind}-{slug}-declared".lower().replace("_", "-"),
            "labels": {
                "service": svc, "signal_kind": kind,
                "bound_series": series_name,  # traceability to the real declared series
                "generated_by": "startd8",
            },
        }

    for s in series:
        selector = _declared_series_selector(s.labels)
        slug = _series_slug(s.name)
        # #286 backlog finding 1: the series may be OPT-IN (e.g. Mastodon DETAILED metrics, off by
        # default) — surface the enabling flag so an operator knows the bound SLO is dead until it's
        # set, instead of the flag being silently parsed-and-dropped. Advisory (not load-bearing).
        flag = s.enabling_flag
        flag_note = f" Requires the {flag} flag enabled for the series to emit." if flag else ""
        for kind in s.covers:
            if kind in span_owned:
                # §2.0: the span lane owns this kind — record the skip, don't double-emit.
                deferred.append({
                    "service": svc, "kind": kind, "series": s.name,
                    "reason_code": "superseded_by_span_binding",
                    "reason": (f"{kind!r} for {svc} is bound by a declared span signal (span-metrics, "
                               f"#307), which takes precedence over the declared Prometheus series "
                               f"{s.name!r}; this base binding is skipped."),
                })
                continue
            if kind == "availability":
                # #286 v2: a good/total ratio needs the error subset; without an error_selector a
                # correct availability ratio can't be built → honest defer (not a fabricated SLI).
                if not s.error_selector:
                    deferred.append({
                        "service": svc, "kind": kind, "series": s.name,
                        "reason_code": "availability_needs_error_selector",
                        "reason": (
                            f"availability covered by {s.name!r} but no error_selector — a correct "
                            f"good/total ratio can't be built without the error subset. Declare an "
                            f"error_selector (e.g. status=~\"5..\") on the series to bind it (#286 v2)."
                        ),
                    })
                    continue
                target, _tier = _resolve_threshold("availability", business, [])
                err_sel = _declared_error_selector(s.labels, s.error_selector)
                slo = {
                    "apiVersion": "openslo/v1", "kind": "SLO",
                    "metadata": _meta(kind, s.name, slug),
                    "spec": {
                        "description": (
                            f"availability SLO for {svc} bound to the declared emitted series "
                            f"{s.name!r} (good/total ratio, #286).{flag_note}"
                        ),
                        "target": target,
                        "timeWindow": {"duration": business.slo_window, "isRolling": True},
                        "budgetPolicy": "occurrences",
                        "indicator": {"metadata": {"name": f"{svc}-availability-{slug}-declared-sli"}, "spec": {
                            "ratioMetric": {
                                "counter": {"metricSource": {"type": "prometheus", "spec": {
                                    "query": f"rate({s.name}{selector}[5m])"}}},
                                "good": {"metricSource": {"type": "prometheus", "spec": {
                                    "query": f"rate({s.name}{err_sel}[5m])"}}},
                            },
                        }},
                        "alerting": {
                            "name": f"{svc}-availability-{slug}-declared-alert",
                            "labels": {"severity": severity},
                        },
                    },
                }
                documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))
                bound.append({"service": svc, "kind": kind, "series": s.name, "enabling_flag": flag})
                continue

            shape_field = _resolve_declared_shape(kind, s.type)
            if shape_field is None:
                # #300 D2: a non-base-RED kind is now owned by generate_declared_functional_slos
                # (bind/threshold-defer/type-mismatch/precedence-skip). The base-RED binder skips it —
                # it neither binds nor defers here, so there is exactly one owner and no double record.
                continue
            shape, threshold_field = shape_field
            query = _functional_sli_query(shape, s.name, selector)
            target, _tier = _resolve_threshold(threshold_field, business, [])
            slo = {
                "apiVersion": "openslo/v1",
                "kind": "SLO",
                "metadata": _meta(kind, s.name, slug),
                "spec": {
                    "description": (
                        f"{kind} SLO for {svc} bound to the declared emitted series "
                        f"{s.name!r} (#286).{flag_note}"
                    ),
                    "target": target,
                    "timeWindow": {"duration": business.slo_window, "isRolling": True},
                    "indicator": {
                        "metadata": {"name": f"{svc}-{kind}-{slug}-declared-sli"},
                        "spec": {
                            "thresholdMetric": {
                                "metricSource": {"type": "prometheus", "spec": {"query": query}},
                            },
                        },
                    },
                    "alerting": {
                        "name": f"{svc}-{kind}-{slug}-declared-alert",
                        "labels": {"severity": severity},
                    },
                },
            }
            documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))
            bound.append({"service": svc, "kind": kind, "series": s.name, "enabling_flag": flag})

    header = f"# Declared-emitted-series base SLOs for {service.service_id} (#286)\n"
    return ArtifactResult(
        artifact_type="slo_definition",
        service_id=service.service_id,
        output_path=f"slos/{service.service_id}-declared-base-slo.yaml",
        status="generated" if documents else "skipped",
        content=(header + "\n---\n".join(documents)) if documents else "",
        quality={"bound_declared_series": bound, "deferred_declared_kinds": deferred},
    )


#: #300 D2 (FR-5): the metric family each functional SLI shape requires. A declared series can only
#: bind a functional kind when its declared ``type`` matches — a gauge for gauge_max/age, a counter for
#: rate/ratio (reuses the #300-C "declared type wins over the template" insight). ``quantile`` needs a
#: histogram but no in-scope (non-project-scoped) functional kind uses it (NR-4) — reserved/forward-compat.
_SHAPE_REQUIRED_TYPE: Dict[str, str] = {
    "gauge_max": "gauge",
    "age": "gauge",
    "rate": "counter",
    "ratio": "counter",
    "quantile": "histogram",
}


def _is_declared_functional_kind(kind: str) -> bool:
    """A kind a declared series may bind as a FUNCTIONAL SLI (#300 D2/FR-1): a recognized functional
    template kind that is neither base RED (owned by the base binder) nor project-scoped (NR-4 — the
    AI-agent kinds are model/project-labeled, not per-service declared series)."""
    return (
        kind in _FUNCTIONAL_SLI_TEMPLATES
        and kind not in BASE_RED_KINDS
        and kind not in _PROJECT_SCOPED_SIGNAL_KINDS
    )


def _functional_fr_covers(business: BusinessContext, service_id: str, kind: str) -> Optional[str]:
    """#300 D2 (FR-7): the id of a functional[] FR that already covers ``(service, kind)`` — reusing
    ``generate_functional_slos``'s own service predicate so a GLOBAL (``service=None``) FR also
    suppresses the declared binding. ``None`` ⇒ no FR owns this kind (the declared binding is free to
    emit)."""
    for f in (business.functional_requirements or []):
        if f.signal_kind == kind and f.service in (None, "", service_id):
            return f.id
    return None


def generate_declared_functional_slos(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Emit a FUNCTIONAL SLO bound to an author-declared REAL emitted series (#300 D2 / defect-D uplift).

    The complement of ``generate_declared_base_slos``: where that binds the base RED kinds, this binds a
    declared series that ``covers`` a recognized **functional** kind (saturation/queue_depth/lag/…) — the
    series already grounds the query, so deferring it (pre-D2) left value on the floor. Per ``(series,
    covered-kind)`` (FR-1), gated by declared-type↔shape compatibility (FR-5), suppressed when a
    functional[] FR already owns the kind (FR-7). The **query is always determinable** and is bound via
    ``_functional_sli_query`` (FR-2); the **target comes only from the author** (``series.target``, FR-3)
    — with a target the SLO is graded and emitted; without one the SLI is *threshold-deferred* (no SLO on
    disk — a null-target OpenSLO doc is malformed) and travels in ``deferred_declared_kinds`` carrying its
    grounded query (FR-4/OQ-5). The SDK never synthesizes a functional target (NR-1). No functional-
    covering declared series ⇒ ``skipped`` and no ``bound_declared_functional`` key (byte-identical, FR-9)."""
    series = getattr(service, "declared_emitted_series", None) or ()
    svc = service.service_id
    documents: List[str] = []
    bound: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    severity = _severity_for(business, [])

    for s in series:
        selector = _declared_series_selector(s.labels)
        slug = _series_slug(s.name)
        flag = s.enabling_flag
        flag_note = f" Requires the {flag} flag enabled for the series to emit." if flag else ""
        for kind in s.covers:
            # Base RED (incl. availability) is the base binder's; project-scoped AI-agent kinds are NR-4.
            if kind in BASE_RED_KINDS:
                continue
            if kind in _PROJECT_SCOPED_SIGNAL_KINDS:
                deferred.append({
                    "service": svc, "kind": kind, "series": s.name,
                    "reason_code": "functional_kind_project_scoped",
                    "reason": (
                        f"{kind!r} is a project/model-scoped AI-agent kind, not a per-service declared "
                        f"series (NR-4); it is not bound from {s.name!r}."
                    ),
                })
                continue
            if not _is_declared_functional_kind(kind):
                deferred.append({
                    "service": svc, "kind": kind, "series": s.name,
                    "reason_code": "unknown_kind",
                    "reason": (
                        f"{kind!r} is not a base RED kind and has no known functional profile; "
                        f"{s.name!r} grounds no SLI (check the declared covers value)."
                    ),
                })
                continue

            # FR-7: a functional[] FR covering the same (service, kind) wins — skip, recorded.
            winning_fr = _functional_fr_covers(business, svc, kind)
            if winning_fr is not None:
                deferred.append({
                    "service": svc, "kind": kind, "series": s.name,
                    "reason_code": "functional_fr_precedence_skip", "winning_fr": winning_fr,
                    "reason": (
                        f"{kind!r} for {svc} is already covered by functional[] FR {winning_fr!r}; "
                        f"the declared-series binding is skipped to avoid a double SLO (FR precedence)."
                    ),
                })
                continue

            _candidates, shape, _unit = _FUNCTIONAL_SLI_TEMPLATES[kind]
            required_type = _SHAPE_REQUIRED_TYPE.get(shape)
            # FR-5: the declared type must match the kind's shape family (a counter can't gauge_max).
            if s.type != required_type:
                deferred.append({
                    "service": svc, "kind": kind, "series": s.name,
                    "reason_code": "functional_type_shape_mismatch",
                    "reason": (
                        f"{kind!r} uses the {shape!r} shape which needs a {required_type!r} series, but "
                        f"{s.name!r} is declared type {s.type or 'unspecified'!r}; not bound."
                    ),
                })
                continue

            # FR-2: the grounded query is always determinable from the declared series + its selector.
            query = _functional_sli_query(shape, s.name, selector)

            # FR-3/FR-4: target from the author, else threshold-deferred (query travels in the gap).
            if s.target is None:
                deferred.append({
                    "service": svc, "kind": kind, "series": s.name, "query": query,
                    "threshold_deferred": True,
                    "reason_code": "functional_bound_threshold_deferred",
                    "reason": (
                        f"{kind!r} SLI for {svc} is grounded on {s.name!r} but has no target — set "
                        f"`target` on the declared series to emit a graded SLO (NR-1: no default "
                        f"threshold is invented)."
                    ),
                })
                continue

            name = f"{svc}-{kind}-{slug}-declared-functional".lower().replace("_", "-")
            slo = {
                "apiVersion": "openslo/v1",
                "kind": "SLO",
                "metadata": {
                    "name": name,
                    "labels": {
                        "service": svc, "signal_kind": kind,
                        "bound_series": s.name, "generated_by": "startd8",
                    },
                },
                "spec": {
                    "description": (
                        f"{kind} SLO for {svc} bound to the declared emitted series "
                        f"{s.name!r} (#300 D2).{flag_note}"
                    ),
                    "target": s.target,
                    "timeWindow": {"duration": business.slo_window, "isRolling": True},
                    "indicator": {
                        "metadata": {"name": f"{svc}-{kind}-{slug}-declared-functional-sli"},
                        "spec": {
                            "thresholdMetric": {
                                "metricSource": {"type": "prometheus", "spec": {"query": query}},
                            },
                        },
                    },
                    "alerting": {
                        "name": f"{svc}-{kind}-{slug}-declared-functional-alert",
                        "labels": {"severity": severity},
                    },
                },
            }
            documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))
            bound.append({
                "service": svc, "kind": kind, "series": s.name,
                "query": query, "threshold": "authored", "enabling_flag": flag,
            })

    # FR-9: no bound quality key when nothing bound (absent, not empty-list — an empty list is a diff).
    quality: Dict[str, Any] = {}
    if bound:
        quality["bound_declared_functional"] = bound
    if deferred:
        quality["deferred_declared_kinds"] = deferred
    header = f"# Declared-emitted-series FUNCTIONAL SLOs for {service.service_id} (#300 D2)\n"
    return ArtifactResult(
        artifact_type="slo_definition",
        service_id=service.service_id,
        output_path=f"slos/{service.service_id}-declared-functional-slo.yaml",
        status="generated" if documents else "skipped",
        content=(header + "\n---\n".join(documents)) if documents else "",
        quality=quality,
    )


# --- #307: declared span-metrics SLI binding ------------------------------------

def _span_descriptor(service: ServiceHints) -> MetricDescriptor:
    """The span-metrics descriptor for a service (#307 FR-3): the fixed Tempo profile, NOT the
    service's base-RED ``descriptors[svc]``, with the real ``service.name`` (#275) bound as the label
    value (same replace pattern as ``_descriptor_for``)."""
    d = profile_for(SPAN_METRICS_TEMPO_PROFILE)
    real = getattr(service, "service_name", "") or ""
    if real and real != service.service_id:
        d = dataclasses.replace(
            d, service_label_value_tpl=real.replace("{", "{{").replace("}", "}}")
        )
    return d


def _span_selector(descriptor: MetricDescriptor, service_id: str, signal: "DeclaredSpanSignal",
                   *, error: bool = False) -> str:
    """The PromQL selector for a declared span signal: identity + descriptor extra_selectors
    (server-kind filter) + ``span_name`` + the signal's non-empty attributes (#300-A discipline),
    plus the error matcher when *error* (signal's ``error_selector`` overrides the descriptor's)."""
    parts = [descriptor.service_matcher(service_id), *descriptor.extra_selectors,
             f'span_name="{signal.name}"']
    parts += [f'{k}="{v}"' for k, v in sorted(signal.attributes.items()) if v != ""]
    if error:
        err = signal.error_selector or descriptor.error_selector
        if err:
            parts.append(err)
    return "{" + ",".join(parts) + "}"


def _declared_span_covered_kinds(service: ServiceHints) -> "frozenset[str]":
    """The base RED kinds a service's declared SPAN signals bind (#307). The single de-dup authority
    (§2.0): the base #286 and functional #300 declared binders consult this to SKIP a kind the span
    lane owns — span > declared-series precedence — so a kind covered by BOTH lanes emits ONCE."""
    covered: set = set()
    for s in getattr(service, "declared_span_signals", None) or ():
        covered |= {k for k in s.covers if k in BASE_RED_KINDS}
    return frozenset(covered)


def generate_declared_span_slos(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Emit a base RED SLO bound to an author-declared SPAN via span-metrics (#307 / option-b1 Part B).

    The trace-surface sibling of ``generate_declared_base_slos``: for each declared span signal and each
    base RED kind it covers, bind an SLI to ``traces_spanmetrics_*{service_name="<real>",
    span_name="<declared>"}`` (FR-4) — carrying the real ``service.name`` (#275), on the fixed Tempo
    descriptor (FR-3), latency threshold scaled to the descriptor unit (FR-5). Precedence span >
    declared-series > convention (§2.0). v1 = per-span RED only; a span covering a functional kind is
    deferred (out of v1 scope). No declared span signals ⇒ ``skipped``, no key (byte-identical, FR-8)."""
    signals = getattr(service, "declared_span_signals", None) or ()
    svc = service.service_id
    d = _span_descriptor(service)
    documents: List[str] = []
    bound: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    severity = _severity_for(business, [])

    latency_raw, _ = _resolve_threshold("latency_p99", business, [])
    avail_target, _ = _resolve_threshold("availability", business, [])
    tput_target, _ = _resolve_threshold("throughput", business, [])

    def _meta(kind: str, slug: str, query: str) -> Dict[str, Any]:
        return {
            "name": f"{svc}-{kind}-{slug}-declared-span".lower().replace("_", "-"),
            "labels": {"service": svc, "signal_kind": kind, "bound_span": slug,
                       "generated_by": "startd8"},
        }

    for sig in signals:
        slug = _series_slug(sig.name)
        flag = sig.enabling_flag
        flag_note = f" Requires the {flag} span-metrics connector/flag enabled." if flag else ""
        sel = _span_selector(d, svc, sig)
        for kind in sig.covers:
            if kind not in BASE_RED_KINDS:
                deferred.append({
                    "service": svc, "kind": kind, "series": sig.name,
                    "reason_code": "span_non_red_deferred_v1",
                    "reason": (f"span {sig.name!r} covers {kind!r} — v1 binds per-span RED only "
                               f"(latency/throughput/availability); functional-over-span is deferred."),
                })
                continue

            if kind == "latency":
                threshold = d.scale_threshold_seconds(_parse_duration_to_seconds(latency_raw)) \
                    if latency_raw else None
                query = (f"histogram_quantile({d.quantile}, sum by (le) "
                         f"(rate({d.latency_bucket_metric}{sel}[{d.rate_window}])))")
                target: Any = threshold
            elif kind == "throughput":
                query = f"sum(rate({d.throughput_metric}{sel}[{d.rate_window}]))"
                target = tput_target
            else:  # availability — good/total error-ratio (#286 v2 orientation, FR-4)
                err = sig.error_selector or d.error_selector
                if not err:
                    deferred.append({
                        "service": svc, "kind": kind, "series": sig.name,
                        "reason_code": "availability_needs_error_selector",
                        "reason": (f"availability for span {sig.name!r} needs an error dimension; "
                                   f"neither the signal nor the descriptor declares one."),
                    })
                    continue
                err_sel = _span_selector(d, svc, sig, error=True)
                query = None  # ratioMetric below
                target = avail_target
                slo = {
                    "apiVersion": "openslo/v1", "kind": "SLO",
                    "metadata": _meta(kind, slug, ""),
                    "spec": {
                        "description": (f"availability SLO for {svc} bound to span-metrics of span "
                                        f"{sig.name!r} (good/total ratio, #307).{flag_note}"),
                        "target": target,
                        "timeWindow": {"duration": business.slo_window, "isRolling": True},
                        "budgetPolicy": "occurrences",
                        "indicator": {"metadata": {"name": f"{svc}-availability-{slug}-declared-span-sli"},
                                      "spec": {"ratioMetric": {
                            "counter": {"metricSource": {"type": "prometheus", "spec": {
                                "query": f"rate({d.throughput_metric}{sel}[{d.rate_window}])"}}},
                            "good": {"metricSource": {"type": "prometheus", "spec": {
                                "query": f"rate({d.throughput_metric}{err_sel}[{d.rate_window}])"}}},
                        }}},
                        "alerting": {"name": f"{svc}-availability-{slug}-declared-span-alert",
                                     "labels": {"severity": severity}},
                    },
                }
                documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))
                bound.append({"service": svc, "kind": kind, "series": sig.name,
                              "query": f"rate({d.throughput_metric}{sel}[{d.rate_window}])",
                              "enabling_flag": flag})
                continue

            slo = {
                "apiVersion": "openslo/v1", "kind": "SLO",
                "metadata": _meta(kind, slug, query),
                "spec": {
                    "description": (f"{kind} SLO for {svc} bound to span-metrics of span "
                                    f"{sig.name!r} (#307).{flag_note}"),
                    "target": target,
                    "timeWindow": {"duration": business.slo_window, "isRolling": True},
                    "indicator": {"metadata": {"name": f"{svc}-{kind}-{slug}-declared-span-sli"},
                                  "spec": {"thresholdMetric": {"metricSource": {
                                      "type": "prometheus", "spec": {"query": query}}}}},
                    "alerting": {"name": f"{svc}-{kind}-{slug}-declared-span-alert",
                                 "labels": {"severity": severity}},
                },
            }
            documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))
            bound.append({"service": svc, "kind": kind, "series": sig.name,
                          "query": query, "enabling_flag": flag})

    quality: Dict[str, Any] = {}
    if bound:
        quality["bound_declared_span"] = bound
    if deferred:
        quality["deferred_declared_kinds"] = deferred
    header = f"# Declared-span-metrics SLOs for {service.service_id} (#307)\n"
    return ArtifactResult(
        artifact_type="slo_definition",
        service_id=service.service_id,
        output_path=f"slos/{service.service_id}-declared-span-slo.yaml",
        status="generated" if documents else "skipped",
        content=(header + "\n---\n".join(documents)) if documents else "",
        quality=quality,
    )


def _functional_sli_query(shape: str, metric: str, selector: str) -> str:
    """PromQL for a functional SLI by its shape (#226 FR-5), bound to *selector*."""
    if shape == "gauge_max":
        return f"max({metric}{selector})"
    if shape == "rate":
        return f"sum(rate({metric}{selector}[5m]))"
    if shape == "age":
        return f"time() - max({metric}{selector})"
    if shape == "ratio":
        return f"sum(rate({metric}{selector}[$__rate_interval]))"
    if shape == "quantile":
        # AI FR-1a: a latency-analog on a histogram — p99 of the `_bucket` series. Matches
        # the live-verified §6 expression for llm_cost_per_request (cost/call p99).
        return (
            f"histogram_quantile(0.99, sum by (le) "
            f"(rate({metric}_bucket{selector}[5m])))"
        )
    return f"{metric}{selector}"


def generate_functional_slos(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Emit an SLO per declared functional[] FR whose signal_kind is a NON-request
    kind (#226 FR-5) — queue_depth/retry_rate/freshness/run_success/lag/saturation.

    Convention-sourced series (FR-6a) bound to the service; the FR's ``target`` is the
    threshold (or, for ``custom``, its own PromQL). FRs scoped to another service, or
    whose signal_kind is in the convention triplet, are skipped. FRs the emitter cannot
    ground (unknown signal_kind, or missing target) are recorded ``unfulfilled`` in
    ``quality`` for FR-9 — never emitted as a fabricated artifact. No functional[] ⇒
    ``skipped`` (byte-identical to pre-#226; this generator adds nothing).
    """
    descriptor = _descriptor_for(service, descriptor)
    selector = descriptor.selector(service.service_id)
    frs = [
        f
        for f in (business.functional_requirements or [])
        if f.service in (None, "", service.service_id)
        and f.signal_kind not in _TRIPLET_SIGNAL_KINDS
    ]
    if not frs:
        return ArtifactResult(
            artifact_type="slo_definition", service_id=service.service_id,
            output_path="", status="skipped",
        )

    documents: List[str] = []
    emitted_fr_ids: List[str] = []
    unfulfilled: List[Dict[str, str]] = []
    for fr in frs:
        kind = fr.signal_kind
        if kind == "custom" and fr.target:
            query = fr.target
        elif kind in _FUNCTIONAL_SLI_TEMPLATES and fr.target:
            candidates, shape, _unit = _FUNCTIONAL_SLI_TEMPLATES[kind]
            metric = _select_functional_metric(candidates, service)
            # FR-2a: AI-agent series are model/project-labeled, not per-service — a
            # `{service=...}` selector would match nothing. Bind them on an aggregate scope.
            _sel = "" if kind in _PROJECT_SCOPED_SIGNAL_KINDS else selector
            query = _functional_sli_query(shape, metric, _sel)
        else:
            unfulfilled.append(
                {"id": fr.id, "signal_kind": kind, "reason": "no groundable series/target"}
            )
            continue

        slo = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {
                "name": f"{service.service_id}-{kind}-{fr.id}".lower().replace("_", "-"),
                "labels": {
                    "service": service.service_id,
                    "signal_kind": kind,
                    "source_fr": fr.id,  # FR-8: traceability to the originating FR
                    "generated_by": "startd8",
                },
            },
            "spec": {
                "description": fr.description or f"{kind} SLO for {service.service_id} ({fr.id})",
                "target": fr.target,
                "timeWindow": {"duration": business.slo_window, "isRolling": True},
                "indicator": {
                    "metadata": {"name": f"{service.service_id}-{kind}-sli"},
                    "spec": {
                        "thresholdMetric": {
                            "metricSource": {"type": "prometheus", "spec": {"query": query}},
                        },
                    },
                },
                "alerting": {
                    "name": f"{service.service_id}-{kind}-alert",
                    "labels": {"severity": _severity_for(business, [])},
                },
            },
        }
        documents.append(yaml.dump(slo, default_flow_style=False, sort_keys=False))
        emitted_fr_ids.append(fr.id)

    header = f"# Functional-requirement SLOs for {service.service_id} (#226 FR-5)\n"
    return ArtifactResult(
        artifact_type="slo_definition",
        service_id=service.service_id,
        output_path=f"slos/{service.service_id}-functional-slo.yaml",
        status="generated" if documents else "skipped",
        content=(header + "\n---\n".join(documents)) if documents else "",
        quality={"emitted_fr_ids": emitted_fr_ids, "unfulfilled": unfulfilled},
    )


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
    sli_kinds = _service_sli_kinds(service, business)  # FR-12a gate (ANDed below)
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
    if counter_metric and avail_raw and "availability" in sli_kinds:  # FR-12a
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
    if histogram_metric and latency_raw and "latency" in sli_kinds:  # FR-12a
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


# REQ_NOTIFICATION_POLICY FR-4 — the single type→receiver renderer, keyed on the
# DECLARED `Receiver.type` (NOT guessed from string shape). Per OQ-1a the per-type target
# is carried by overloading the single `Receiver.target` string; each renderer maps it to
# that type's correct Alertmanager field. Adding a type is a dict entry, not an if/elif
# branch (R1-F2 / the Accidental-Complexity anti-principle). Every entry references the
# secret via `Receiver.target` (`${VAR}`) — never fabricated (NR-2).
def _cfg_slack(r: Receiver) -> Tuple[str, Dict[str, Any]]:
    # For slack the receiver `name` IS the channel id (#chan); `target` is the api_url secret.
    return "slack_configs", {"channel": r.name, "api_url": r.target, "send_resolved": True}


def _cfg_email(r: Receiver) -> Tuple[str, Dict[str, Any]]:
    return "email_configs", {"to": r.target}


def _cfg_pagerduty(r: Receiver) -> Tuple[str, Dict[str, Any]]:
    return "pagerduty_configs", {"routing_key": r.target, "send_resolved": True}


def _cfg_opsgenie(r: Receiver) -> Tuple[str, Dict[str, Any]]:
    return "opsgenie_configs", {"api_key": r.target, "send_resolved": True}


def _cfg_webhook(r: Receiver) -> Tuple[str, Dict[str, Any]]:
    return "webhook_configs", {"url": r.target, "send_resolved": True}


def _cfg_msteams(r: Receiver) -> Tuple[str, Dict[str, Any]]:
    return "msteams_configs", {"webhook_url": r.target, "send_resolved": True}


# type (declared, lowercased) → renderer. Absent/`""`/unknown ⇒ UNRESOLVED-REQUIRED (FR-3).
_RECEIVER_RENDERERS: Dict[str, Any] = {
    "slack": _cfg_slack,
    "email": _cfg_email,
    "pagerduty": _cfg_pagerduty,
    "opsgenie": _cfg_opsgenie,
    "webhook": _cfg_webhook,
    "msteams": _cfg_msteams,
}

# The exact loud placeholder prefix (FR-3/FR-3a, R1-F7) — reused verbatim, never reinvented.
_UNRESOLVED_PREFIX = "# UNRESOLVED REQUIRED PARAM:"


def _receiver_applies_to(receiver: Receiver, severity: str) -> bool:
    """FR-7 tiering from the AUTHORED `Receiver.severities`. An empty `severities`
    means the receiver applies to ALL severities (OQ-3 default — no surprising
    filtering); otherwise it applies only to the listed severities."""
    if not receiver.severities:
        return True
    return severity in receiver.severities


def generate_notification_policy(
    service: ServiceHints,
    business: BusinessContext,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Generate an Alertmanager routing policy scoped to a service (REQ_NOTIFICATION_POLICY).

    Binds to the AUTHORED `Receiver{name,type,target,severities}` (`spec.py`, parsed by the
    single canonical entry point `from_observability_yaml` and threaded via
    `business.receivers`). For each routed channel id (FR-6: `alertChannels` →
    `owners[].slack` fallback via `routing_channels()`; the contacts roster is a future
    input, not built here) the DECLARED `type` selects the correct `*_configs`, pulling the
    secret from `Receiver.target` (FR-4/FR-5).

    Loud-fail (FR-3/FR-3a), NEVER a silent Slack default:
      * a routed channel with no matching receiver (dangling ref), OR
      * a receiver whose `type` is `""` (parser default), OR an unknown type
    is emitted as `# UNRESOLVED REQUIRED PARAM:` — reference-secrets-never-fabricate (NR-2).

    Routes are tiered by severity (FR-7) from `Receiver.severities`; the matcher label is the
    descriptor's `service_label_key` (FR-8: `service` vs `service_name` for span-metrics).
    """
    descriptor = _descriptor_for(service, descriptor)
    label_key = descriptor.service_label_key
    derivations: List[DerivationTrace] = []
    severity = _severity_for(business, derivations)

    by_name = {r.name: r for r in business.receivers}
    channels = business.routing_channels()

    # Grouping (FR-9): overridable from business.notification_grouping, not hardcoded literals.
    grouping = business.notification_grouping or {}
    group_by = grouping.get("group_by")
    group_by = list(group_by) if isinstance(group_by, list) else [label_key, "alertname"]
    group_wait = str(grouping.get("group_wait")) if grouping.get("group_wait") else "30s"
    repeat_interval = (
        str(grouping.get("repeat_interval")) if grouping.get("repeat_interval") else "4h"
    )

    # Resolve each routed channel ONCE (FR-3/FR-3a/FR-4): channel id → (config_key, config,
    # receiver), or record it UNRESOLVED-REQUIRED. Never a silent Slack default. Resolving up
    # front (rather than per tier) avoids re-work and a dedup hack, and lets each tier just
    # filter the already-resolved set by `Receiver.severities`.
    resolved: List[Tuple[str, Dict[str, Any], Receiver]] = []
    unresolved: List[str] = []
    for ch in dict.fromkeys(channels):  # de-dup channel ids, preserve order
        receiver = by_name.get(ch)
        if receiver is None:  # dangling ref: routed but not declared (FR-3a)
            unresolved.append(f"{ch} (no matching receiver in alerting.receivers)")
            continue
        renderer = _RECEIVER_RENDERERS.get(receiver.type.strip().lower())
        if renderer is None:  # type=="" (parser default) or unknown type (FR-3)
            unresolved.append(f"{ch} (unresolvable channel type {receiver.type or '(none declared)'!r})")
            continue
        key, cfg = renderer(receiver)
        resolved.append((key, cfg, receiver))

    # FR-7 tiering: the alert generator labels EVERY alert for this service with the single
    # `_severity_for(business)` value — there is no per-alert warning/critical split today — so
    # we emit exactly ONE route, at that severity. A synthetic `warning` tier would be a route
    # that no generated alert can ever match (a silently-dead route). The tiering that DOES work
    # is per-receiver filtering: `Receiver.severities` decides which channels apply (a receiver
    # declaring `severities: [critical]` pages on a critical service; a chat-only receiver with
    # no `severities` always applies). Multi-severity route tiers are forward-looking — they
    # become meaningful only if/when alerts carry varied severities.
    tiers = [severity]

    receiver_docs: List[Dict[str, Any]] = []
    routes: List[Dict[str, Any]] = []
    for tier in tiers:
        applicable = [(k, cfg) for (k, cfg, r) in resolved if _receiver_applies_to(r, tier)]
        if not applicable:
            continue  # no channel applies to this severity → no empty-receiver route
        rname = f"{service.service_id}-{tier}"
        rdoc: Dict[str, Any] = {"name": rname}
        for key, cfg in applicable:
            rdoc.setdefault(key, []).append(cfg)
        receiver_docs.append(rdoc)
        routes.append({
            "matchers": [f"{label_key} = {service.service_id}", f"severity = {tier}"],
            "receiver": rname,
            "group_by": list(group_by),  # fresh list per route → no YAML anchor/alias
            "group_wait": group_wait,
            "repeat_interval": repeat_interval,
            "continue": True,
        })
        derivations.append(DerivationTrace(
            field="alert_channels",
            source="observability.yaml alerting.receivers (declared type+target)",
            transformation=f"tier={tier} matcher={label_key}={service.service_id}",
            tier="manifest",
        ))

    seen_resolved = bool(receiver_docs)

    doc: Dict[str, Any] = {"route": {"routes": routes}, "receivers": receiver_docs}

    header_lines = [
        "# Generated by startd8 observability artifact generator",
        f"# Service: {service.service_id} — notification routing by severity",
    ]
    if seen_resolved:
        header_lines.append(
            "# Channels bound to authored alerting.receivers (declared type + ${SECRET} "
            "target); secrets are referenced, never fabricated, and set at deploy time."
        )
    if unresolved:
        for u in unresolved:
            header_lines.append(f"{_UNRESOLVED_PREFIX} {u} — declare it in "
                                "observability.yaml alerting.receivers with a known "
                                "type (slack/email/pagerduty/opsgenie/webhook/msteams) "
                                "and an env-indirected target. No transport was fabricated.")
        derivations.append(DerivationTrace(
            field="alert_channels", source="routing_channels ↔ alerting.receivers join",
            transformation=f"unresolved_required (FR-3/FR-3a): {unresolved}", tier="default",
        ))
    if not channels:
        header_lines.append(
            f"{_UNRESOLVED_PREFIX} no alertChannels (or owners[].slack) in the manifest — "
            "no channels to route. Populate spec.observability.alertChannels upstream."
        )
        derivations.append(DerivationTrace(
            field="alert_channels", source="manifest.spec.observability.alertChannels",
            transformation="unresolved_required — no channels", tier="default",
        ))
    elif resolved and not receiver_docs:
        # Channels resolved to receivers, but none declare `severities` matching this
        # service's alert severity — so nothing routes. Flag it loudly, don't emit a
        # silent empty policy (Context-Correctness — no silent gap).
        header_lines.append(
            f"{_UNRESOLVED_PREFIX} all resolved receivers are filtered out for severity "
            f"'{severity}' (their Receiver.severities do not include it) — no channel would "
            f"be notified. Add '{severity}' to a receiver's severities, or leave it empty to "
            "apply to all severities."
        )
        derivations.append(DerivationTrace(
            field="alert_channels", source="Receiver.severities filter",
            transformation=f"all_filtered_for_severity={severity}", tier="default",
        ))

    header = "\n".join(header_lines) + f"\n{_derivation_comment(derivations)}\n\n"
    return ArtifactResult(
        artifact_type="notification_policy",
        service_id=service.service_id,
        output_path=f"notifications/{service.service_id}-notification-policy.yaml",
        status="generated",
        content=header + yaml.dump(doc, default_flow_style=False, sort_keys=False),
        derivations=derivations,
    )


def _log_selector(
    service: ServiceHints, target: Optional[Dict[str, Any]]
) -> Tuple[str, str, str]:
    """The LogQL stream-selector VALUE + its ``(source, tier)`` for a service's logs (#278).

    Precedence: the real OTel ``service.name`` (matches real log streams + the metric SLIs, #275)
    when declared > an explicit ``spec.targets[].name`` > the sanitized ``service_id``. Shared by the
    loki-rule alert (`generate_loki_rule`) AND the runbook's operator log-query hint
    (`generate_runbook`) so the two never drift — a paged operator's manual query matches the same
    streams the alert fired on."""
    real = getattr(service, "service_name", "") or ""
    if real and real != service.service_id:
        return real, "instrumentation_hints[svc].service_name", "manifest"
    if target and target.get("name"):
        return str(target["name"]), "manifest.spec.targets[].name", "manifest"
    return service.service_id, "service_id", "default"


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
    # #278: bind the LogQL stream selector to the real OTel service.name (slash preserved) when
    # onboarding declares it (REQ-CCL-105) — mirroring the #275 metric-SLI fix — so a log-based alert
    # matches the SAME telemetry the metric SLIs do, instead of falling through to the sanitized
    # service_id. The shared `_log_selector` keeps this in lockstep with the runbook's log-query hint.
    selector_name, _sel_source, _sel_tier = _log_selector(service, target)
    derivations.append(DerivationTrace(
        field="loki.selector", source=_sel_source,
        transformation=f'{stream_key}="{selector_name}"', tier=_sel_tier,
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
    # #278: the operator's copy-paste log query must select the SAME stream the loki-rule alert
    # fires on — the real service.name, not the sanitized service_id (shared with generate_loki_rule).
    log_selector, _, _ = _log_selector(service, _target_for(service.service_id, business.targets))
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
        f"(`{{service=\"{log_selector}\"}} |= \"error\"`).",
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
