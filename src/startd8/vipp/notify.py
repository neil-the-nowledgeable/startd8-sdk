# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""VIPP negotiation events (FR-17 — lightweight observability).

One structured event per negotiation: counts + label only, **no free-text** (matching the host
privacy posture). Best-effort over the SDK EventBus when present; always logs via ``get_logger`` so
an operator can reconstruct "what did the VIPP decide" from Loki + the durable ``dispositions.json``.
The full FR-17 audit surface is fleshed out in M6.
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
    # FR-17-lite: the structured log line IS the v1 event (get_logger → OTel/Loki). The SDK EventBus
    # API is `EventBus.emit(Event(...))` with a fixed EventType enum (no VIPP type today); wiring a
    # first-class EventType + a subscriber-asserting test is M6 scope (full FR-17). Logging here is
    # the working, tested surface — no dead "best-effort emit" that silently never fires (was H2).
    logger.info("%s %s", EV_NEGOTIATE_COMPLETE, payload)
