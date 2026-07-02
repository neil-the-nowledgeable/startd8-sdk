# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

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

__all__ = ["span", "mark_error"]


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
