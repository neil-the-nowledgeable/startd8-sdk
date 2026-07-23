"""Kickoff progress metrics (roadmap Tier 3 — the real OTel Meter→Mimir fix).

The kickoff `emit()` funnel records span events but **no metrics** (the "emit()=0 Mimir metrics"
gap). This module emits the handful of progress **gauges** that drive the cockpit's readiness
burndown + cost-over-time panels:

- ``kickoff.readiness.percent`` — field-level readiness (ok fraction) as a percent
- ``kickoff.session.cost_usd``  — latest kickoff session cost (USD)
- ``kickoff.proposals.pending`` — pending proposals awaiting confirmation
- ``kickoff.fields.blocked``    — blocked kickoff fields
- ``kickoff.facilitation.cost_usd`` — latest **facilitation** cost (USD), the one expensive path;
  carries ``posture`` + ``tier`` labels so Grafana can break spend down by scrutiny/prototype and
  premium/cheap. Emitted at facilitation completion (see ``facilitate_run._worker``) — without it the
  cost-over-time panel is blind to the biggest single kickoff spend until a portal rebuild.
- ``kickoff.facilitation.cost_usd_total`` — **cumulative** facilitation spend (#10; monotonic counter,
  same labels), for after-the-fact cost-governance alerts, e.g. ``increase(
  kickoff_facilitation_cost_usd_total{project="X"}[30d]) > CEILING``. Provisioning the alert is the
  operator's job (grafana skill); this is distinct from the fail-closed pre-spend budget gate.

Each carries a ``project`` label. In Prometheus/Mimir these become ``kickoff_readiness_percent`` etc.
(verified live: dots→underscores, no unit suffix). Emission is **best-effort + opt-in**: it calls the
SDK's idempotent ``auto_configure_otel()`` (which respects ``STARTD8_OTEL`` and only wires an exporter
when a collector is reachable), so with no collector it is a silent no-op — never load-bearing, never a
failure. The values are *snapshots* (they can go up or down), hence synchronous **gauges** (`.set()`),
not counters.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_METER_NAME = "startd8.kickoff"

# Observability manifest descriptors — consumed by ``observability/collector.py`` (this module is
# registered in its ``_INSTRUMENTED_MODULES``) so the descriptor↔emission **bijection** holds
# (REQ-OBS-SHARED-002): every instrument created in ``_gauges()`` has a matching descriptor here and
# vice versa. Zero runtime cost. Kickoff progress signals are user-facing readiness/cost gauges plus
# the cumulative facilitation-spend counter.
_OTEL_DESCRIPTORS = {
    "category": "business_observability",
    "orientation": "system",
    "metrics": [
        {
            "name": "kickoff.readiness.percent",
            "instrument": "gauge",
            "unit": "",
            "description": "Kickoff field readiness (ok fraction) as a percent",
            "meter": _METER_NAME,
            "labels": ["project"],
        },
        {
            "name": "kickoff.session.cost_usd",
            "instrument": "gauge",
            "unit": "",
            "description": "Latest kickoff session cost (USD)",
            "meter": _METER_NAME,
            "labels": ["project"],
        },
        {
            "name": "kickoff.proposals.pending",
            "instrument": "gauge",
            "unit": "",
            "description": "Pending kickoff proposals awaiting confirmation",
            "meter": _METER_NAME,
            "labels": ["project"],
        },
        {
            "name": "kickoff.fields.blocked",
            "instrument": "gauge",
            "unit": "",
            "description": "Blocked kickoff fields",
            "meter": _METER_NAME,
            "labels": ["project"],
        },
        {
            "name": "kickoff.facilitation.cost_usd",
            "instrument": "gauge",
            "unit": "",
            "description": "Latest facilitation cost (USD), labelled by posture + tier",
            "meter": _METER_NAME,
            "labels": ["project", "posture", "tier"],
        },
        {
            "name": "kickoff.facilitation.cost_usd_total",
            "instrument": "counter",
            "unit": "",
            "description": "Cumulative facilitation spend (USD), labelled by posture + tier",
            "meter": _METER_NAME,
            "labels": ["project", "posture", "tier"],
        },
        {
            "name": "kickoff.activation.open",
            "instrument": "gauge",
            "unit": "",
            "description": "Open activation conditions (firing 'alerts') from the oracle",
            "meter": _METER_NAME,
            "labels": ["project"],
        },
        {
            "name": "kickoff.activation.severity",
            "instrument": "gauge",
            "unit": "",
            "description": "Overall activation severity (0=ok, 1=attention, 2=blocked)",
            "meter": _METER_NAME,
            "labels": ["project"],
        },
    ],
}

# Lazy, process-wide instrument cache. `_tried` guards a single configure+create attempt so a missing
# collector doesn't re-probe on every emit.
_state: Dict[str, Any] = {"gauges": None, "tried": False}


def _gauges() -> Optional[Dict[str, Any]]:
    """Configure OTel (idempotent) + create/cached the kickoff gauges. None when unavailable."""
    if _state["tried"]:
        return _state["gauges"]
    _state["tried"] = True
    try:
        from ..otel import auto_configure_otel

        auto_configure_otel()  # idempotent; respects STARTD8_OTEL; auto-probes localhost:4317
        from opentelemetry import metrics

        meter = metrics.get_meter(_METER_NAME)
        _state["gauges"] = {
            "readiness": meter.create_gauge(
                "kickoff.readiness.percent", unit="",
                description="Kickoff field readiness (ok fraction) as a percent",
            ),
            "cost": meter.create_gauge(
                "kickoff.session.cost_usd", unit="",
                description="Latest kickoff session cost (USD)",
            ),
            "proposals": meter.create_gauge(
                "kickoff.proposals.pending", unit="",
                description="Pending kickoff proposals awaiting confirmation",
            ),
            "blocked": meter.create_gauge(
                "kickoff.fields.blocked", unit="",
                description="Blocked kickoff fields",
            ),
            "facilitation_cost": meter.create_gauge(
                "kickoff.facilitation.cost_usd", unit="",
                description="Latest facilitation cost (USD), labeled by posture + tier",
            ),
            # #10 — cumulative facilitation spend for cost-governance alerting (monotonic Counter, add()).
            # In Prometheus/Mimir this becomes ``kickoff_facilitation_cost_usd_total``; alert with e.g.
            # ``increase(kickoff_facilitation_cost_usd_total{project="X"}[30d]) > CEILING`` — an *after-the-
            # fact* monthly-spend alert (distinct from the fail-closed pre-spend ``ensure_blocking_budget``).
            "facilitation_cost_total": meter.create_counter(
                "kickoff.facilitation.cost_usd_total", unit="",
                description="Cumulative facilitation spend (USD), labeled by posture + tier",
            ),
            "activation_open": meter.create_gauge(
                "kickoff.activation.open", unit="",
                description="Open activation conditions (firing 'alerts') from the oracle",
            ),
            "activation_severity": meter.create_gauge(
                "kickoff.activation.severity", unit="",
                description="Overall activation severity (0=ok, 1=attention, 2=blocked)",
            ),
        }
    except Exception as exc:  # pragma: no cover - metrics are never load-bearing
        logger.debug("kickoff metrics unavailable: %s", exc)
        _state["gauges"] = None
    return _state["gauges"]


def record_kickoff_progress(
    *,
    project: str,
    readiness_percent: Optional[float] = None,
    cost_usd: Optional[float] = None,
    proposals_pending: Optional[int] = None,
    blocked: Optional[int] = None,
) -> bool:
    """Emit the kickoff progress gauges (best-effort). Returns True iff a point was recorded.

    Only the non-``None`` values are set, each labeled ``{project=...}``. Any failure is swallowed."""
    gauges = _gauges()
    if not gauges:
        return False
    try:
        attrs = {"project": str(project)}
        if readiness_percent is not None:
            gauges["readiness"].set(float(readiness_percent), attrs)
        if cost_usd is not None:
            gauges["cost"].set(float(cost_usd), attrs)
        if proposals_pending is not None:
            gauges["proposals"].set(float(proposals_pending), attrs)
        if blocked is not None:
            gauges["blocked"].set(float(blocked), attrs)
        return True
    except Exception as exc:  # pragma: no cover
        logger.debug("kickoff metrics emit skipped: %s", exc)
        return False


def record_facilitation_cost(
    *,
    project: str,
    cost_usd: float,
    posture: Optional[str] = None,
    tier: Optional[str] = None,
) -> bool:
    """Emit the facilitation cost at run completion (best-effort). Returns True iff recorded.

    Records BOTH the latest-cost **gauge** and the cumulative-spend **counter** (#10) — the single
    emission point for facilitation cost (Mottainai). Labeled ``{project, posture, tier}`` so panels +
    alerts can break spend down by scrutiny/prototype and premium/cheap. Never load-bearing."""
    gauges = _gauges()
    if not gauges:
        return False
    try:
        attrs = {"project": str(project)}
        if posture is not None:
            attrs["posture"] = str(posture)
        if tier is not None:
            attrs["tier"] = str(tier)
        gauges["facilitation_cost"].set(float(cost_usd), attrs)
        gauges["facilitation_cost_total"].add(float(cost_usd), attrs)  # #10 cumulative spend
        return True
    except Exception as exc:  # pragma: no cover
        logger.debug("facilitation cost metric skipped: %s", exc)
        return False


def record_activation(
    *,
    project: str,
    open_count: int,
    severity_code: int,
) -> bool:
    """Emit the activation gauges from an :class:`ActivationReport` (best-effort). Returns True iff recorded.

    ``severity_code`` is 0=ok / 1=attention / 2=blocked. A Grafana alert can fire on
    ``kickoff_activation_open > 0`` or ``kickoff_activation_severity >= 2`` — the same conditions the
    portable ``kickoff check`` gate evaluates, so stack and no-stack paths agree. Never load-bearing."""
    gauges = _gauges()
    if not gauges:
        return False
    try:
        attrs = {"project": str(project)}
        gauges["activation_open"].set(float(open_count), attrs)
        gauges["activation_severity"].set(float(severity_code), attrs)
        return True
    except Exception as exc:  # pragma: no cover
        logger.debug("activation metric skipped: %s", exc)
        return False


def record_from_view(view: Any, project: str) -> bool:
    """Emit a progress point from an :class:`AgenticView` (the cockpit's read-model). Best-effort."""
    if view is None:
        return False
    cost = view.snapshot.cost.cost_usd if getattr(view, "has_snapshot", False) else None
    blocked = None
    state = getattr(view, "state", None)
    if state is not None:
        blocked = state.attention_counts.get("blocked", 0)
    return record_kickoff_progress(
        project=project,
        readiness_percent=view.readiness_percent(),
        cost_usd=cost,
        proposals_pending=len(view.proposals),
        blocked=blocked,
    )
