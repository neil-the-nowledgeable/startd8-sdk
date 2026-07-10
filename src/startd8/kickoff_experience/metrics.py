"""Kickoff progress metrics (roadmap Tier 3 — the real OTel Meter→Mimir fix).

The kickoff `emit()` funnel records span events but **no metrics** (the "emit()=0 Mimir metrics"
gap). This module emits the handful of progress **gauges** that drive the cockpit's readiness
burndown + cost-over-time panels:

- ``kickoff.readiness.percent`` — field-level readiness (ok fraction) as a percent
- ``kickoff.session.cost_usd``  — latest kickoff session cost (USD)
- ``kickoff.proposals.pending`` — pending proposals awaiting confirmation
- ``kickoff.fields.blocked``    — blocked kickoff fields

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
