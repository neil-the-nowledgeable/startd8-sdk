"""
End-to-end test module for Artisan contractor timeout enforcement.

This module validates that workflows respect configured timeout limits,
gracefully persist state on timeout, can be resumed, and return partial results.

All code is self-contained in a single file with no relative imports.

Architecture
------------
- ``WorkflowStatus``  – enum tracking lifecycle states
- ``WorkflowStep``    – immutable description of a single unit of work
- ``WorkflowState``   – mutable execution snapshot (progress, results, context)
- ``StateStore``       – thread-safe in-memory persistence layer
- ``WorkflowEngine``   – executor with cooperative timeout, state persistence,
                         and resume-from-checkpoint capability

Design decisions
~~~~~~~~~~~~~~~~
* **Cooperative cancellation** – steps are simulated via ``time.sleep`` in small
  increments so the engine can check the deadline between slices.  This avoids
  forcibly killing threads and guarantees state consistency.
* **Monotonic clock for deadlines** – ``time.monotonic()`` is immune to wall-clock
  adjustments (NTP, daylight-saving, etc.).
* **Best-effort persistence** – ``_persist`` swallows exceptions so a transient
  store failure does not abort the workflow.  In production this would emit a
  structured log / metric.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import pytest


# ============================================================================
# Enums
# ============================================================================


class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    RESUMED = "resumed"
    FAILED = "failed"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class WorkflowStep:
    """Immutable description of a single step in a workflow.

    Attributes:
        name: Human-readable identifier (must be unique within a workflow).
        duration_seconds: Simulated wall-clock cost of this step.
        result_value: Arbitrary payload produced when the step completes.
    """

    name: str
    duration_seconds: float
    result_value: Any = None


@dataclass
class WorkflowState:
    """Mutable snapshot of workflow execution progress.

    Attributes:
        workflow_id: Unique identifier for the workflow run.
        status: Current lifecycle status.
        current_step_index: Index of the *next* step to execute.
        completed_steps: Ordered list of step names that finished successfully.
        partial_results: Mapping of step name → result for completed steps.
        context: Caller-supplied metadata carried through the entire lifecycle.
        timeout_seconds: Timeout budget for the current (or most recent) run.
        total_steps: Total number of steps in the workflow definition.
        created_at: Unix timestamp when the workflow was first created.
        updated_at: Unix timestamp of the most recent state mutation.
    """

    workflow_id: str
    status: WorkflowStatus
    current_step_index: int
    completed_steps: List[str] = field(default_factory=list)
    partial_results: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 0.0
    total_steps: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0


# ============================================================================
# State Store Implementation
# ============================================================================


class StateStore:
    """Thread-safe in-memory store for workflow state persistence.

    In a production system this would be backed by a durable store (database,
    Redis, object storage, etc.).  The interface is intentionally narrow to
    make swapping implementations straightforward.
    """

    def __init__(self) -> None:
        self._store: Dict[str, WorkflowState] = {}
        self._lock = threading.Lock()

    def save(self, state: WorkflowState) -> None:
        """Persist *state*, overwriting any previous version."""
        with self._lock:
            self._store[state.workflow_id] = state

    def load(self, workflow_id: str) -> Optional[WorkflowState]:
        """Return the persisted state for *workflow_id*, or ``None``."""
        with self._lock:
            return self._store.get(workflow_id)

    def exists(self, workflow_id: str) -> bool:
        """Return ``True`` if *workflow_id* has been persisted."""
        with self._lock:
            return workflow_id in self._store

    def delete(self, workflow_id: str) -> None:
        """Remove *workflow_id* from the store (no-op if absent)."""
        with self._lock:
            self._store.pop(workflow_id, None)

    def list_all(self) -> List[str]:
        """Return a snapshot of all persisted workflow IDs."""
        with self._lock:
            return list(self._store.keys())


# ============================================================================
# Workflow Engine Implementation
# ============================================================================


class WorkflowEngine:
    """Execute workflow steps with timeout enforcement and state persistence.

    The engine uses *cooperative cancellation*: long-running steps are broken
    into short sleep increments so the deadline can be checked frequently.
    This guarantees that the engine never overshoots the timeout by more than
    ``_CANCELLATION_CHECK_INTERVAL`` seconds (plus scheduling jitter).
    """

    _CANCELLATION_CHECK_INTERVAL: float = 0.05  # seconds

    def __init__(self, state_store: StateStore) -> None:
        self._state_store = state_store
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        workflow_id: str,
        steps: List[WorkflowStep],
        timeout_seconds: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowState:
        """Start a new workflow run.

        Args:
            workflow_id: Unique identifier for this run.
            steps: Ordered list of steps to execute.
            timeout_seconds: Wall-clock budget (≥ 0).
            context: Optional caller metadata preserved across the lifecycle.

        Returns:
            Final ``WorkflowState`` — status will be ``COMPLETED`` or
            ``TIMED_OUT``.
        """
        now = time.time()
        state = WorkflowState(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            current_step_index=0,
            timeout_seconds=timeout_seconds,
            total_steps=len(steps),
            context=context if context is not None else {},
            created_at=now,
            updated_at=now,
        )

        deadline = time.monotonic() + timeout_seconds
        return self._run_steps(state, steps, 0, deadline)

    def resume(
        self,
        workflow_id: str,
        steps: List[WorkflowStep],
        timeout_seconds: Optional[float] = None,
    ) -> WorkflowState:
        """Resume a previously timed-out workflow from its checkpoint.

        Args:
            workflow_id: The workflow to resume (must exist in the store).
            steps: The *same* step list used in the original ``execute`` call.
            timeout_seconds: Fresh budget; defaults to the original timeout.

        Returns:
            Updated ``WorkflowState``.

        Raises:
            ValueError: If *workflow_id* is not found or already completed.
        """
        state = self._state_store.load(workflow_id)
        if state is None:
            raise ValueError(f"Workflow {workflow_id} not found in state store")
        if state.status == WorkflowStatus.COMPLETED:
            raise ValueError(f"Workflow {workflow_id} is already completed")

        new_timeout = timeout_seconds if timeout_seconds is not None else state.timeout_seconds
        deadline = time.monotonic() + new_timeout

        state.status = WorkflowStatus.RESUMED
        state.timeout_seconds = new_timeout
        state.updated_at = time.time()

        start_index = state.current_step_index
        return self._run_steps(state, steps, start_index, deadline)

    def get_state(self, workflow_id: str) -> Optional[WorkflowState]:
        """Retrieve the persisted state for *workflow_id*."""
        return self._state_store.load(workflow_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_steps(
        self,
        state: WorkflowState,
        steps: List[WorkflowStep],
        start_index: int,
        deadline: float,
    ) -> WorkflowState:
        """Execute steps ``[start_index:]`` with cooperative timeout.

        On timeout the state is persisted with ``TIMED_OUT`` status so a
        subsequent ``resume`` call can continue from the checkpoint.
        """
        for step_idx in range(start_index, len(steps)):
            step = steps[step_idx]

            # ---- pre-step deadline check ----
            if time.monotonic() >= deadline:
                state.status = WorkflowStatus.TIMED_OUT
                state.current_step_index = step_idx
                state.updated_at = time.time()
                self._persist(state)
                return state

            # ---- simulate step execution with cooperative cancellation ----
            elapsed = 0.0
            while elapsed < step.duration_seconds:
                if time.monotonic() >= deadline:
                    state.status = WorkflowStatus.TIMED_OUT
                    state.current_step_index = step_idx
                    state.updated_at = time.time()
                    self._persist(state)
                    return state

                sleep_duration = min(
                    self._CANCELLATION_CHECK_INTERVAL,
                    step.duration_seconds - elapsed,
                )
                time.sleep(sleep_duration)
                elapsed += sleep_duration

            # ---- step completed ----
            state.completed_steps.append(step.name)
            state.partial_results[step.name] = step.result_value
            state.current_step_index = step_idx + 1
            state.updated_at = time.time()
            self._persist(state)

        # ---- all steps finished ----
        state.status = WorkflowStatus.COMPLETED
        state.current_step_index = len(steps)
        state.updated_at = time.time()
        self._persist(state)
        return state

    def _persist(self, state: WorkflowState) -> None:
        """Best-effort persistence; failures are swallowed (log in production)."""
        try:
            self._state_store.save(state)
        except Exception:  # noqa: BLE001
            pass


# ============================================================================
# Pytest Fixtures
# ============================================================================


@pytest.fixture
def state_store() -> StateStore:
    """Provide a fresh ``StateStore`` for each test."""
    return StateStore()


@pytest.fixture
def engine(state_store: StateStore) -> WorkflowEngine:
    """Provide a fresh ``WorkflowEngine`` wired to the test ``StateStore``."""
    return WorkflowEngine(state_store)


@pytest.fixture
def slow_steps() -> List[WorkflowStep]:
    """Five steps × 0.5 s each = 2.5 s total."""
    return [
        WorkflowStep(name="slow-step-1", duration_seconds=0.5, result_value={"step": 1}),
        WorkflowStep(name="slow-step-2", duration_seconds=0.5, result_value={"step": 2}),
        WorkflowStep(name="slow-step-3", duration_seconds=0.5, result_value={"step": 3}),
        WorkflowStep(name="slow-step-4", duration_seconds=0.5, result_value={"step": 4}),
        WorkflowStep(name="slow-step-5", duration_seconds=0.5, result_value={"step": 5}),
    ]


@pytest.fixture
def fast_steps() -> List[WorkflowStep]:
    """Five steps × 0.05 s each = 0.25 s total."""
    return [
        WorkflowStep(name="fast-step-1", duration_seconds=0.05, result_value={"step": 1}),
        WorkflowStep(name="fast-step-2", duration_seconds=0.05, result_value={"step": 2}),
        WorkflowStep(name="fast-step-3", duration_seconds=0.05, result_value={"step": 3}),
        WorkflowStep(name="fast-step-4", duration_seconds=0.05, result_value={"step": 4}),
        WorkflowStep(name="fast-step-5", duration_seconds=0.05, result_value={"step": 5}),
    ]


@pytest.fixture
def mixed_steps() -> List[WorkflowStep]:
    """Alternating fast (0.05 s) and slow (0.8 s) steps."""
    return [
        WorkflowStep(name="mixed-fast-1", duration_seconds=0.05, result_value={"data": "a"}),
        WorkflowStep(name="mixed-slow-1", duration_seconds=0.8, result_value={"data": "b"}),
        WorkflowStep(name="mixed-fast-2", duration_seconds=0.05, result_value={"data": "c"}),
        WorkflowStep(name="mixed-slow-2", duration_seconds=0.8, result_value={"data": "d"}),
        WorkflowStep(name="mixed-fast-3", duration_seconds=0.05, result_value={"data": "e"}),
    ]


# ============================================================================
# Test Suite
# ============================================================================


@pytest.mark.timeout(60)
class TestArtisanTimeout:
    """Validate workflow timeout enforcement, state persistence, resume, and partial results."""

    # ------------------------------------------------------------------ #
    # Basic completion / timeout
    # ------------------------------------------------------------------ #

    def test_workflow_completes_within_timeout(
        self, engine: WorkflowEngine, fast_steps: List[WorkflowStep]
    ) -> None:
        """Fast steps (0.25 s total) with a 1 s timeout should complete normally."""
        result = engine.execute(
            workflow_id="wf-complete-001",
            steps=fast_steps,
            timeout_seconds=1.0,
        )
        assert result.status == WorkflowStatus.COMPLETED
        assert len(result.completed_steps) == len(fast_steps)
        assert len(result.partial_results) == len(fast_steps)

    def test_workflow_timeout_enforcement(
        self, engine: WorkflowEngine, slow_steps: List[WorkflowStep]
    ) -> None:
        """Slow steps (2.5 s total) with a 1 s timeout must be cut short."""
        result = engine.execute(
            workflow_id="wf-timeout-001",
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        assert result.status == WorkflowStatus.TIMED_OUT
        assert len(result.completed_steps) < len(slow_steps)
        assert len(result.partial_results) == len(result.completed_steps)

    def test_timeout_enforced_within_margin(
        self, engine: WorkflowEngine, slow_steps: List[WorkflowStep]
    ) -> None:
        """Wall-clock elapsed time should be close to the configured timeout."""
        start_time = time.time()
        result = engine.execute(
            workflow_id="wf-margin-001",
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        elapsed = time.time() - start_time

        assert result.status == WorkflowStatus.TIMED_OUT
        assert elapsed < 1.6, f"Timeout not enforced promptly: {elapsed:.3f}s"
        assert elapsed >= 1.0, f"Elapsed time less than timeout: {elapsed:.3f}s"

    # ------------------------------------------------------------------ #
    # State persistence
    # ------------------------------------------------------------------ #

    def test_state_persisted_on_timeout(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """After timeout the state must be retrievable from the store."""
        workflow_id = "wf-persist-001"
        result = engine.execute(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        assert result.status == WorkflowStatus.TIMED_OUT

        stored_state = state_store.load(workflow_id)
        assert stored_state is not None
        assert stored_state.status == WorkflowStatus.TIMED_OUT
        assert stored_state.workflow_id == workflow_id
        assert len(stored_state.completed_steps) > 0

    # ------------------------------------------------------------------ #
    # Partial results
    # ------------------------------------------------------------------ #

    def test_partial_results_on_timeout(
        self, engine: WorkflowEngine, slow_steps: List[WorkflowStep]
    ) -> None:
        """Only fully-completed steps should appear in partial_results."""
        result = engine.execute(
            workflow_id="wf-partial-001",
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        assert result.status == WorkflowStatus.TIMED_OUT
        assert len(result.partial_results) > 0
        assert len(result.partial_results) == len(result.completed_steps)
        for step_name in result.completed_steps:
            assert step_name in result.partial_results

    # ------------------------------------------------------------------ #
    # Resume after timeout
    # ------------------------------------------------------------------ #

    def test_resume_after_timeout(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """A timed-out workflow should complete when resumed with enough budget."""
        workflow_id = "wf-resume-001"

        result1 = engine.execute(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        assert result1.status == WorkflowStatus.TIMED_OUT
        assert len(result1.completed_steps) > 0

        result2 = engine.resume(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=10.0,
        )
        assert result2.status == WorkflowStatus.COMPLETED
        assert len(result2.completed_steps) == len(slow_steps)
        assert len(result2.partial_results) == len(slow_steps)

    def test_resume_continues_from_last_step(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """Resume must not re-execute already-completed steps."""
        workflow_id = "wf-resume-continue-001"

        result1 = engine.execute(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        assert result1.status == WorkflowStatus.TIMED_OUT
        last_completed_index = result1.current_step_index

        result2 = engine.resume(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=10.0,
        )
        assert result2.current_step_index == len(slow_steps)
        for idx in range(min(last_completed_index, len(result2.completed_steps))):
            step_name = result1.completed_steps[idx]
            assert step_name in result2.partial_results

    def test_resume_completes_remaining_steps(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """After a successful resume every step name must appear in completed_steps."""
        workflow_id = "wf-resume-remaining-001"

        engine.execute(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=1.0,
        )

        result2 = engine.resume(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=10.0,
        )

        assert set(result2.completed_steps) == {s.name for s in slow_steps}

    def test_partial_results_accumulate_after_resume(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        mixed_steps: List[WorkflowStep],
    ) -> None:
        """Results from both the original run and the resume must be present."""
        workflow_id = "wf-accumulate-001"

        result1 = engine.execute(
            workflow_id=workflow_id,
            steps=mixed_steps,
            timeout_seconds=0.5,
        )
        assert result1.status == WorkflowStatus.TIMED_OUT

        result2 = engine.resume(
            workflow_id=workflow_id,
            steps=mixed_steps,
            timeout_seconds=10.0,
        )
        assert result2.status == WorkflowStatus.COMPLETED

        for step_name in result1.completed_steps:
            assert step_name in result2.partial_results
            assert result2.partial_results[step_name] == result1.partial_results[step_name]

    # ------------------------------------------------------------------ #
    # Edge-case timeouts
    # ------------------------------------------------------------------ #

    def test_zero_timeout_immediate_timeout(
        self, engine: WorkflowEngine, slow_steps: List[WorkflowStep]
    ) -> None:
        """A zero-second timeout should fire immediately."""
        result = engine.execute(
            workflow_id="wf-zero-timeout-001",
            steps=slow_steps,
            timeout_seconds=0.0,
        )
        assert result.status == WorkflowStatus.TIMED_OUT
        assert len(result.completed_steps) <= 1

    def test_very_short_timeout(
        self, engine: WorkflowEngine, slow_steps: List[WorkflowStep]
    ) -> None:
        """A 0.1 s timeout with 0.5 s steps should complete at most one step."""
        result = engine.execute(
            workflow_id="wf-short-timeout-001",
            steps=slow_steps,
            timeout_seconds=0.1,
        )
        assert result.status == WorkflowStatus.TIMED_OUT
        assert len(result.completed_steps) <= 1

    # ------------------------------------------------------------------ #
    # Context propagation
    # ------------------------------------------------------------------ #

    def test_timeout_preserves_context(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """Caller-supplied context must survive timeout and resume."""
        workflow_id = "wf-context-001"
        test_context = {"user_id": "123", "request_id": "abc-def", "env": "test"}

        result1 = engine.execute(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=1.0,
            context=test_context,
        )
        assert result1.status == WorkflowStatus.TIMED_OUT
        assert result1.context == test_context

        result2 = engine.resume(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=10.0,
        )
        assert result2.context == test_context

    def test_context_none_and_empty_handling(
        self,
        engine: WorkflowEngine,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """Both ``None`` and ``{}`` contexts must normalise to an empty dict."""
        result1 = engine.execute(
            workflow_id="wf-context-none-001",
            steps=slow_steps,
            timeout_seconds=1.0,
            context=None,
        )
        assert result1.context == {}

        result2 = engine.execute(
            workflow_id="wf-context-empty-001",
            steps=slow_steps,
            timeout_seconds=1.0,
            context={},
        )
        assert result2.context == {}

    # ------------------------------------------------------------------ #
    # Multiple resume cycles
    # ------------------------------------------------------------------ #

    def test_multiple_resume_cycles(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """Three successive cycles should accumulate progress until completion."""
        workflow_id = "wf-multi-resume-001"

        result1 = engine.execute(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        assert result1.status == WorkflowStatus.TIMED_OUT
        completed_cycle1 = set(result1.completed_steps)
        assert len(completed_cycle1) > 0

        result2 = engine.resume(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        completed_cycle2 = set(result2.completed_steps)
        assert len(completed_cycle2) > len(completed_cycle1)

        result3 = engine.resume(
            workflow_id=workflow_id,
            steps=slow_steps,
            timeout_seconds=10.0,
        )
        assert result3.status == WorkflowStatus.COMPLETED
        assert len(result3.completed_steps) == len(slow_steps)

    # ------------------------------------------------------------------ #
    # Error handling
    # ------------------------------------------------------------------ #

    def test_completed_workflow_not_resumable_as_timeout(
        self,
        engine: WorkflowEngine,
        fast_steps: List[WorkflowStep],
    ) -> None:
        """Resuming an already-completed workflow must raise ``ValueError``."""
        workflow_id = "wf-already-complete-001"

        result1 = engine.execute(
            workflow_id=workflow_id,
            steps=fast_steps,
            timeout_seconds=10.0,
        )
        assert result1.status == WorkflowStatus.COMPLETED

        with pytest.raises(ValueError, match="already completed"):
            engine.resume(
                workflow_id=workflow_id,
                steps=fast_steps,
                timeout_seconds=10.0,
            )

    def test_resume_nonexistent_workflow(
        self, engine: WorkflowEngine, slow_steps: List[WorkflowStep]
    ) -> None:
        """Resuming a workflow that was never started must raise ``ValueError``."""
        with pytest.raises(ValueError, match="not found"):
            engine.resume(
                workflow_id="wf-does-not-exist",
                steps=slow_steps,
                timeout_seconds=10.0,
            )

    # ------------------------------------------------------------------ #
    # Concurrency
    # ------------------------------------------------------------------ #

    def test_concurrent_workflows_independent_timeouts(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
    ) -> None:
        """Two workflows running in parallel must maintain independent state."""
        steps_a = [
            WorkflowStep(name="wf-a-step-1", duration_seconds=0.5, result_value={"wf": "a", "step": 1}),
            WorkflowStep(name="wf-a-step-2", duration_seconds=0.5, result_value={"wf": "a", "step": 2}),
            WorkflowStep(name="wf-a-step-3", duration_seconds=0.5, result_value={"wf": "a", "step": 3}),
        ]
        steps_b = [
            WorkflowStep(name="wf-b-step-1", duration_seconds=0.2, result_value={"wf": "b", "step": 1}),
            WorkflowStep(name="wf-b-step-2", duration_seconds=0.2, result_value={"wf": "b", "step": 2}),
            WorkflowStep(name="wf-b-step-3", duration_seconds=0.2, result_value={"wf": "b", "step": 3}),
        ]

        results: Dict[str, WorkflowState] = {}

        def run_a() -> None:
            results["a"] = engine.execute("wf-concurrent-a", steps_a, timeout_seconds=0.7)

        def run_b() -> None:
            results["b"] = engine.execute("wf-concurrent-b", steps_b, timeout_seconds=0.3)

        thread_a = threading.Thread(target=run_a, daemon=False)
        thread_b = threading.Thread(target=run_b, daemon=False)
        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        assert results["a"].status == WorkflowStatus.TIMED_OUT
        assert results["b"].status == WorkflowStatus.TIMED_OUT

        state_a = state_store.load("wf-concurrent-a")
        state_b = state_store.load("wf-concurrent-b")
        assert state_a is not None and state_a.workflow_id == "wf-concurrent-a"
        assert state_b is not None and state_b.workflow_id == "wf-concurrent-b"

    # ------------------------------------------------------------------ #
    # Miscellaneous
    # ------------------------------------------------------------------ #

    def test_step_result_values_preserved(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """Each completed step's result must match the configured ``result_value``."""
        result = engine.execute(
            workflow_id="wf-results-001",
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        for step in slow_steps:
            if step.name in result.partial_results:
                assert result.partial_results[step.name] == step.result_value

    def test_timeout_maintains_step_order(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """``completed_steps`` must preserve original execution order."""
        result = engine.execute(
            workflow_id="wf-order-001",
            steps=slow_steps,
            timeout_seconds=1.0,
        )
        for idx, step_name in enumerate(result.completed_steps):
            assert step_name == slow_steps[idx].name

    def test_get_state_method(
        self,
        engine: WorkflowEngine,
        state_store: StateStore,
        slow_steps: List[WorkflowStep],
    ) -> None:
        """``get_state`` must return the same object that the store holds."""
        workflow_id = "wf-getstate-001"
        engine.execute(workflow_id=workflow_id, steps=slow_steps, timeout_seconds=1.0)

        retrieved = engine.get_state(workflow_id)
        assert retrieved is not None
        assert retrieved.status == WorkflowStatus.TIMED_OUT
        assert retrieved.workflow_id == workflow_id

    def test_single_step_workflow_timeout(self, engine: WorkflowEngine) -> None:
        """A single long step that exceeds its budget must yield zero completions."""
        steps = [
            WorkflowStep(name="single-step", duration_seconds=1.0, result_value={"single": True}),
        ]
        result = engine.execute(
            workflow_id="wf-single-001",
            steps=steps,
            timeout_seconds=0.2,
        )
        assert result.status == WorkflowStatus.TIMED_OUT
        assert len(result.completed_steps) == 0
        assert len(result.partial_results) == 0