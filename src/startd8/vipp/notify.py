# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""VIPP negotiation events (FR-17 observability).

One structured event per negotiation: counts + label only, **no free-text** (matching the host
privacy posture, `proposals.py:208`). Emitted on the SDK ``EventBus`` (real
``EventBus.emit(Event(...))`` — M6) AND logged via ``get_logger`` so an operator can reconstruct
"what did the VIPP decide and why" from Loki + the durable, source-labeled ``dispositions.{json,md}``
audit. ``project_id`` is the ``correlation_id`` (the join key, FR-14).
"""

from __future__ import annotations

from typing import Any, Dict

from ..logging_config import get_logger

logger = get_logger(__name__)

EV_NEGOTIATE_COMPLETE = "vipp.negotiate.complete"


def emit_negotiate_complete(
    project_id: str,
    report_path: str,
    *,
    counts: Dict[str, int],
    envelope_seq: int,
    cost_usd: float = 0.0,
    llm_used: bool = False,
) -> None:
    payload: Dict[str, Any] = {
        "project_id": project_id,
        "envelope_seq": envelope_seq,
        "counts": counts,
        "cost_usd": cost_usd,
        "llm_used": llm_used,
        "report": report_path,
    }
    logger.info("%s %s", EV_NEGOTIATE_COMPLETE, payload)
    try:  # real EventBus emission (FR-17); never fail the negotiation on telemetry
        from ..events import Event, EventBus, EventType

        EventBus.emit(
            Event(
                type=EventType.VIPP_NEGOTIATE_COMPLETE,
                source="vipp",
                data=payload,
                correlation_id=project_id,  # the project.id join key (FR-14)
            )
        )
    except Exception:  # pragma: no cover - EventBus optional/disabled
        logger.debug("VIPP: EventBus emit skipped", exc_info=True)
