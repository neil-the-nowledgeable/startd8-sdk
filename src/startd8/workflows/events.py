"""Lightweight workflow event structure for shared telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class WorkflowEvent:
    workflow_id: str
    agent: str
    status: str
    details: Dict[str, Any]


def log_workflow_event(event: WorkflowEvent) -> None:
    """Emit a structured workflow event."""
    logger.info(
        "workflow_event",
        extra={
            "workflow_id": event.workflow_id,
            "agent": event.agent,
            "status": event.status,
            **(event.details or {}),
        },
    )


__all__ = ["WorkflowEvent", "log_workflow_event"]
