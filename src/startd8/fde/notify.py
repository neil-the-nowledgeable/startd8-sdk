# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""FDE observability events (FR-27 / R5-S1).

Mirrors the Service Assistant / Semantic Compliance pattern: fire-and-forget EventBus emit
with the OTel bridge activated, so explain/preflight completion shows up in the Loki/Tempo
stack operators already use — no resident consumer required. Best-effort: never raises.
"""

from __future__ import annotations

from ..logging_config import get_logger
from typing import Optional

logger = get_logger(__name__)


def _emit(event_type_name: str, source: str, data: dict) -> None:
    try:
        from ..events import Event, EventBus, EventPriority, EventType
        from ..events.otel_bridge import OTelEventBridge

        OTelEventBridge.activate()
        EventBus.emit(
            Event(
                type=getattr(EventType, event_type_name),
                source=source,
                data=data,
                priority=EventPriority.HIGH,
            )
        )
    except Exception:  # pragma: no cover - events are best-effort
        logger.debug(
            "FDE: event emission failed for %s", event_type_name, exc_info=True
        )


def emit_explain_complete(
    run_id: str,
    output_dir: str,
    report_path: str,
    cost_usd: float = 0.0,
    evidence_available: bool = True,
) -> None:
    _emit(
        "FDE_EXPLAIN_COMPLETE",
        "ForwardDeployedEngineer",
        {
            "run_id": run_id,
            "output_dir": output_dir,
            "report_path": report_path,
            "mode": "explain",
            "cost_usd": cost_usd,
            "evidence_available": evidence_available,
        },
    )


def emit_preflight_complete(
    output_dir: str,
    report_path: str,
    landmine_count: int = 0,
    cost_usd: float = 0.0,
    plan_path: Optional[str] = None,
) -> None:
    _emit(
        "FDE_PREFLIGHT_COMPLETE",
        "ForwardDeployedEngineer",
        {
            "output_dir": output_dir,
            "report_path": report_path,
            "mode": "preflight",
            "landmine_count": landmine_count,
            "cost_usd": cost_usd,
            "plan_path": plan_path,
        },
    )
