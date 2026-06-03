"""EventBus notification for the Service Assistant (FR-6, supplementary).

The EventBus has no guaranteed resident consumer, so these events are *supplementary*
to the authoritative on-disk triage artifact (FR-7). They serve optional in-process
subscribers and enter the persisted in-memory history (HIGH priority).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from ..events import Event, EventBus, EventPriority, EventType
from .detector import DetectionResult
from .models import EmittedEvent, Verdict

SOURCE = "ServiceAssistant"


def _payload(detection: DetectionResult, verdict: Verdict, triage_path: str, project_id: Optional[str]) -> dict:
    return {
        "run_id": detection.run_id,
        "output_dir": str(detection.output_dir),
        "status": detection.status,
        "aggregate_verdict": verdict.aggregate_verdict,
        "failed": verdict.failed,
        "triage_artifact_path": triage_path,
        "project_id": project_id,
    }


def emit_events(
    detection: DetectionResult,
    verdict: Verdict,
    triage_path: str,
    project_id: Optional[str] = None,
) -> List[EmittedEvent]:
    """Emit the run/post-mortem/failure events appropriate to this detection."""
    # Ensure EventBus events bridge to OTel/Tempo (idempotent). Mirrors the
    # ecosystem's Squirrel pattern: triage signals are observable as span events
    # + the startd8.events.total counter, not just in-memory history.
    try:
        from ..events.otel_bridge import OTelEventBridge

        OTelEventBridge.activate()
    except Exception:  # pragma: no cover - bridge is best-effort
        pass

    payload = _payload(detection, verdict, triage_path, project_id)
    emitted: List[EmittedEvent] = []

    def _fire(event_type: EventType) -> None:
        EventBus.emit(
            Event(type=event_type, source=SOURCE, data=dict(payload), priority=EventPriority.HIGH)
        )
        emitted.append(
            EmittedEvent(
                type=event_type.name,
                priority=EventPriority.HIGH.value.upper(),
                at=datetime.now(timezone.utc).isoformat(),
            )
        )

    if detection.run_sentinel_present:
        _fire(EventType.RUN_DETECTED)
    if detection.postmortem_present:
        _fire(EventType.POSTMORTEM_AVAILABLE)
    if detection.hard_abort or verdict.aggregate_verdict in ("FAIL", "ABORTED"):
        _fire(EventType.RUN_FAILED)

    return emitted
