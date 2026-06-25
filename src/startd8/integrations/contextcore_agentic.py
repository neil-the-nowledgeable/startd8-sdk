"""Optional ContextCore integration for the agentic loop (Phase 2, FR-CC1/CC2).

A **pure outer layer**: `agents/agentic.py` imports NOTHING from here (FR-S12 guard). These wrap a run
*from above* — observing its event stream and recording it as a tracked ContextCore task. ContextCore
is optional: `TaskTrackerWrapper` already degrades to a logging no-op when the package is absent, and
every emit here is additionally wrapped defensively so a ContextCore API drift can never break a run.

- **FR-CC1 `ContextCoreProgressObserver`** — consumes the FR-S1 event stream and emits progress
  (turn/tool events) to ContextCore. Pure observer: reads events, drives nothing.
- **FR-CC2 `ContextCoreAgenticAdapter`** — runs an `AgenticSession` as a tracked ContextCore task,
  SpanState-v2 compliant: `task.created` zero-point event at start, validated status transitions,
  terminal `done`/`cancelled` from the run's stop_reason.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from ..logging_config import get_logger
from ..models import CompactionEvent, RunComplete, ToolCallResult, ToolCallStarted, TurnComplete
from .contextcore import TaskTrackerWrapper

logger = get_logger(__name__)

# Canonical SpanState-v2 task-status transitions (LL h2a-03: reject illegal transitions so the
# cross-agent audit trail can't be corrupted). Terminal states have no outgoing transitions.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "todo": {"in_progress", "cancelled"},
    "in_progress": {"in_review", "blocked", "done", "cancelled"},
    "in_review": {"in_progress", "done", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
}


@runtime_checkable
class ProgressEmitter(Protocol):
    """Structural contract a progress observer satisfies. Injected from above — never imported by the
    core loop. Any object with ``on_event(event)`` works."""

    def on_event(self, event: Any) -> None: ...


class ContextCoreProgressObserver:
    """FR-CC1: emit agentic-run progress to ContextCore as events. Pure observer, idempotent-ish
    (events carry stable turn/tool keys), and defensively no-op when ContextCore is unavailable."""

    def __init__(self, tracker: TaskTrackerWrapper, task_id: str) -> None:
        self._tracker = tracker
        self._task_id = task_id
        self._turns = 0

    def on_event(self, event: Any) -> None:
        try:
            if isinstance(event, ToolCallStarted):
                self._tracker.add_event(
                    self._task_id, "agentic.tool_call_started", {"tool": event.name, "call_id": event.id}
                )
            elif isinstance(event, ToolCallResult):
                self._tracker.add_event(
                    self._task_id, "agentic.tool_call_result", {"tool": event.name, "ok": event.ok}
                )
            elif isinstance(event, TurnComplete):
                self._turns += 1
                self._tracker.add_event(self._task_id, "agentic.turn_complete", {"turn": self._turns})
            elif isinstance(event, CompactionEvent):
                self._tracker.add_event(
                    self._task_id, "agentic.compaction", {"attempt": event.attempt}
                )
        except (ImportError, TypeError, AttributeError) as exc:  # LL sdk-12: defensive, never crash
            logger.debug("ContextCore progress emit skipped (%s): %s", type(exc).__name__, exc)


class ContextCoreAgenticAdapter:
    """FR-CC2: run an `AgenticSession` as a tracked ContextCore task (optional outer layer).

    Usage::

        adapter = ContextCoreAgenticAdapter(session, project_id="proj", task_id="run-1")
        result = await adapter.run("How ready is this project?", on_event=render)
    """

    def __init__(
        self,
        session: Any,  # AgenticSession (untyped to avoid importing the loop into this optional layer)
        project_id: str,
        task_id: str,
        *,
        title: Optional[str] = None,
        task_type: str = "task",
        local_storage: Optional[str] = None,
        tracker: Optional[TaskTrackerWrapper] = None,
    ) -> None:
        self._session = session
        self._task_id = task_id
        self._title = title or f"agentic run {task_id}"
        self._task_type = task_type
        self._tracker = tracker or TaskTrackerWrapper(project_id, local_storage=local_storage)
        self._observer = ContextCoreProgressObserver(self._tracker, task_id)
        self._status: Optional[str] = None

    def _transition(self, new_status: str) -> None:
        if self._status is not None and new_status not in _VALID_TRANSITIONS.get(self._status, set()):
            logger.warning(
                "ContextCore task %s: invalid transition %s -> %s (forcing)",
                self._task_id, self._status, new_status,
            )
        self._status = new_status
        self._tracker.update_status(self._task_id, new_status)

    async def run(self, user_message: str, *, on_event=None) -> Any:
        """Run the session as a tracked task; ``on_event`` (optional) forwards each event for live
        render (the observer tees its own copy). Returns the run's ``AgenticResult``."""
        self._tracker.start_task(self._task_id, self._title, task_type=self._task_type)
        # LL h2a-01: zero-point task.created event at run START (drives burndown / task-awareness).
        self._tracker.add_event(
            self._task_id, "task.created",
            {"task.type": self._task_type, "task.status": "todo", "task.percent_complete": 0},
        )
        self._transition("in_progress")

        result = None
        try:
            async for event in self._session.stream(user_message):
                self._observer.on_event(event)
                if on_event is not None:
                    on_event(event)
                if isinstance(event, RunComplete):
                    result = event.result
        except Exception as exc:  # the run itself failed
            self._tracker.fail_task(self._task_id, f"agentic run errored: {exc}")
            self._transition("cancelled")
            raise

        if result is not None and getattr(result, "ok", False):
            self._transition("done")
            self._tracker.complete_task(self._task_id)
        else:
            reason = getattr(result, "stop_reason", "unknown")
            self._tracker.fail_task(self._task_id, f"agentic run did not complete: {reason}")
            self._transition("cancelled")
        return result
