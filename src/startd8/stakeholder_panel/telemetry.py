# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""OTel spans for the panel (FR-14).

Thin wrapper over :func:`startd8.agents.agentic_otel.span` so the panel emits an instantiation span
and a child span per query. Two constraints from the requirements:

* **No raw text in attributes (R1-F5):** callers pass only ``role_id`` / ``session_id`` / model /
  token counts / cost / grounding — never the question, answer, or brief text (spans flow to
  Loki/Tempo).
* **Status ERROR on persona failure (R2-F2):** :func:`mark_error` sets it, guarded because the
  no-op span yielded when OTel is absent has no ``set_status``.
"""

from __future__ import annotations

from typing import Any

from startd8.agents.agentic_otel import span

__all__ = [
    "span",
    "mark_error",
    "decision_event",
    "EV_REVIEWED",
    "EV_APPROVED",
    "EV_REJECTED",
]

# The human decision funnel (R4-F3): distinct events so the *human* half of the funnel is visible in
# dashboards, not just the LLM ``panel.ask``. Content-free (IDs only, per R1-F5).
EV_REVIEWED = "stakeholder.recommendation_reviewed"
EV_APPROVED = "stakeholder.recommendation_approved"
EV_REJECTED = "stakeholder.recommendation_rejected"


def mark_error(active_span: Any, message: str) -> None:
    """Set span status to ERROR if the span supports it (no-op span does not)."""
    setter = getattr(active_span, "set_status", None)
    if setter is None:
        return
    try:
        from opentelemetry import trace

        setter(trace.StatusCode.ERROR, message)
    except (
        Exception
    ):  # pragma: no cover - OTel absent or proxy quirk; telemetry must never throw
        pass


def decision_event(
    event: str, *, domain: str = "", role_id: str = "", value_path: str = ""
) -> None:
    """Emit one human-decision funnel event as a short span (R4-F3). Never throws.

    Content-free by contract (R1-F5): only ``domain`` / ``role_id`` / ``value_path`` — never the
    drafted value, rationale, or brief text (spans flow to Tempo/Loki).
    """
    try:
        with span(
            event,
            **{
                "recommend.domain": domain or None,
                "recommend.role_id": role_id or None,
                "recommend.value_path": value_path or None,
            },
        ):
            pass
    except Exception:  # pragma: no cover - telemetry must never break a CLI action
        pass
