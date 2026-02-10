"""
E2E Test Module: Full Artisan Contractor Workflow

This module provides comprehensive testing of the Artisan contractor workflow,
including mock agents, event emission, state persistence, and phase ordering.

All classes, fixtures, and tests are self-contained in this single file with
no relative imports.

Usage:
    pytest test_e2e_workflow.py -v
"""

import json
import enum
import time
from abc import ABC
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import OrderedDict

import pytest


# ============================================================================
# ENUMS
# ============================================================================

class Phase(enum.Enum):
    """Workflow phases in order of execution."""
    PLANNING = "planning"
    BUILDING = "building"
    REVIEWING = "reviewing"
    DELIVERING = "delivering"


class EventType(enum.Enum):
    """Types of events emitted during workflow execution."""
    WORKFLOW_STARTED = "workflow_started"
    PHASE_ENTERED = "phase_entered"
    PHASE_COMPLETED = "phase_completed"
    WORKFLOW_COMPLETED = "workflow_completed"
    ERROR_OCCURRED = "error_occurred"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Event:
    """Represents a lifecycle event emitted during workflow execution."""
    event_type: EventType
    phase: Optional[Phase]
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskInput:
    """Input specification for a contractor task."""
    task_id: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseResult:
    """Result returned by an agent after executing a phase."""
    phase: Phase
    success: bool
    output: Any
    error: Optional[str] = None


@dataclass
class WorkflowState:
    """
    Encapsulates state that flows through the workflow phases.

    Provides methods for setting/getting per-phase outputs and serialization.
    """
    phase_outputs: Dict[str, Any] = field(default_factory=lambda: OrderedDict())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def set_phase_output(self, phase: Phase, output: Any) -> None:
        """Store output for a specific phase."""
        self.phase_outputs[phase.value] = output

    def get_phase_output(self, phase: Phase) -> Optional[Any]:
        """Retrieve output from a specific phase, or None if not set."""
        return self.phase_outputs.get(phase.value)

    def snapshot(self) -> "WorkflowState":
        """Return a deep copy of current state for persistence verification."""
        return WorkflowState(
            phase_outputs=OrderedDict(self.phase_outputs),
            metadata=dict(self.metadata),
        )

    def to_json(self) -> str:
        """Serialize state to JSON string."""
        data = {
            "phase_outputs": dict(self.phase_outputs),
            "metadata": self.metadata,
        }
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "WorkflowState":
        """Deserialize state from JSON string."""
        data = json.loads(json_str)
        state = cls()
        state.phase_outputs = OrderedDict(data.get("phase_outputs", {}))
        state.metadata = data.get("metadata", {})
        return state


@dataclass
class Deliverable:
    """Final output produced at the end of the workflow."""
    task_id: str
    success: bool
    plan: Dict[str, Any]
    artifacts: List[str]
    review: Dict[str, Any]
    final_output: str
    state_snapshot: WorkflowState


# ============================================================================
# EVENT COLLECTOR
# ============================================================================

class EventCollector:
    """
    Collects and analyzes events emitted during workflow execution.

    Acts as a listener that can be registered with the contractor
    to capture all lifecycle events for assertion in tests.
    """

    def __init__(self) -> None:
        self.events: List[Event] = []

    def on_event(self, event: Event) -> None:
        """Callback for the contractor to emit events."""
        self.events.append(event)

    def get_events_by_type(self, event_type: EventType) -> List[Event]:
        """Return all events of a specific type."""
        return [evt for evt in self.events if evt.event_type == event_type]

    def get_event_types_in_order(self) -> List[EventType]:
        """Return event types in the order they were emitted."""
        return [evt.event_type for evt in self.events]

    def get_phases_entered(self) -> List[Phase]:
        """Return phases in the order they were entered."""
        return [
            evt.phase
            for evt in self.events
            if evt.event_type == EventType.PHASE_ENTERED
        ]

    def clear(self) -> None:
        """Clear all recorded events."""
        self.events.clear()


# ============================================================================
# AGENT BASE CLASS & IMPLEMENTATIONS
# ============================================================================

class BaseAgent(ABC):
    """
    Base class for all agents in the workflow.

    Tracks call count and received states for inspection in tests.
    """

    def __init__(self) -> None:
        self.call_count: int = 0
        self.received_states: List[WorkflowState] = []

    def execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
        """
        Execute the agent's logic.

        Records the call and state snapshot, then delegates to _do_execute.
        """
        self.call_count += 1
        self.received_states.append(state.snapshot())
        return self._do_execute(state, task)

    def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
        """Subclasses override this to provide phase-specific logic."""
        raise NotImplementedError


class MockPlannerAgent(BaseAgent):
    """
    Mock agent for the PLANNING phase.

    Produces a deterministic plan dict containing steps and phase info.
    """

    def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
        plan = {
            "task_id": task.task_id,
            "steps": ["step_1_analyze", "step_2_design", "step_3_implement"],
            "estimated_phases": 3,
        }
        return PhaseResult(phase=Phase.PLANNING, success=True, output=plan)


class MockBuilderAgent(BaseAgent):
    """
    Mock agent for the BUILDING phase.

    Reads the plan from state and produces artifacts based on its steps.
    Demonstrates state dependency: expects PLANNING output to exist.
    """

    def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
        plan = state.get_phase_output(Phase.PLANNING)
        if plan is None:
            return PhaseResult(
                phase=Phase.BUILDING,
                success=False,
                output=None,
                error="No plan found in state",
            )
        artifacts = [f"artifact_for_{step}" for step in plan.get("steps", [])]
        return PhaseResult(phase=Phase.BUILDING, success=True, output=artifacts)


class MockReviewerAgent(BaseAgent):
    """
    Mock agent for the REVIEWING phase.

    Reads artifacts from state and produces a review.
    Demonstrates multi-phase state dependency.
    """

    def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
        artifacts = state.get_phase_output(Phase.BUILDING)
        if artifacts is None:
            return PhaseResult(
                phase=Phase.REVIEWING,
                success=False,
                output=None,
                error="No artifacts found",
            )
        review = {
            "artifacts_reviewed": len(artifacts),
            "approved": True,
            "comments": "All artifacts meet quality standards.",
        }
        return PhaseResult(phase=Phase.REVIEWING, success=True, output=review)


class MockFailingAgent(BaseAgent):
    """
    Mock agent that always fails.

    Used to test error handling paths. Can either raise an exception
    or return a failure result.
    """

    def __init__(self, fail_phase: Phase, use_exception: bool = True) -> None:
        super().__init__()
        self.fail_phase = fail_phase
        self.use_exception = use_exception

    def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
        if self.use_exception:
            raise RuntimeError(f"Simulated failure in {self.fail_phase.value}")
        return PhaseResult(
            phase=self.fail_phase,
            success=False,
            output=None,
            error="Simulated failure",
        )


# ============================================================================
# ARTISAN CONTRACTOR ORCHESTRATOR
# ============================================================================

class ArtisanContractor:
    """
    Orchestrates the end-to-end workflow through multiple phases.

    Manages state flow, invokes agents in correct order, emits lifecycle events,
    and assembles final deliverables.
    """

    PHASE_ORDER = [
        Phase.PLANNING,
        Phase.BUILDING,
        Phase.REVIEWING,
        Phase.DELIVERING,
    ]

    def __init__(
        self,
        agents: Dict[Phase, BaseAgent],
        event_listener: Optional[Callable[[Event], None]] = None,
    ) -> None:
        """
        Initialize the contractor.

        Args:
            agents: Dict mapping Phase to BaseAgent instances.
            event_listener: Optional callback for event emission.
        """
        self.agents = agents
        self.event_listener = event_listener
        self.state = WorkflowState()
        self._completed = False

    def _emit(
        self,
        event_type: EventType,
        phase: Optional[Phase] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit a lifecycle event to the registered listener.

        Args:
            event_type: Type of event.
            phase: Associated phase (if applicable).
            payload: Additional event data.
        """
        event = Event(
            event_type=event_type,
            phase=phase,
            timestamp=time.time(),
            payload=payload or {},
        )
        if self.event_listener:
            self.event_listener(event)

    def run(self, task: TaskInput) -> Deliverable:
        """
        Execute the full workflow for a given task.

        Phases are executed in order: PLANNING -> BUILDING -> REVIEWING -> DELIVERING.
        State is accumulated and passed forward through phases.

        Args:
            task: TaskInput specifying the work to be done.

        Returns:
            Deliverable with final outputs.

        Raises:
            ValueError: If required agent is missing for a non-DELIVERING phase.
            RuntimeError: If a phase agent returns success=False or raises.
        """
        # Reset state for fresh run
        self.state = WorkflowState()
        self._completed = False

        # Emit workflow start
        self._emit(EventType.WORKFLOW_STARTED, payload={"task_id": task.task_id})

        try:
            for phase in self.PHASE_ORDER:
                # Emit phase entered
                self._emit(EventType.PHASE_ENTERED, phase=phase)

                if phase == Phase.DELIVERING:
                    # Delivering phase: assemble deliverable from accumulated state
                    deliverable = self._assemble_deliverable(task)
                    self.state.set_phase_output(phase, "delivered")
                    self._emit(
                        EventType.PHASE_COMPLETED,
                        phase=phase,
                        payload={"success": True},
                    )
                    self._completed = True
                    self._emit(
                        EventType.WORKFLOW_COMPLETED,
                        payload={"task_id": task.task_id, "success": True},
                    )
                    return deliverable
                else:
                    # Execute phase via agent
                    agent = self.agents.get(phase)
                    if agent is None:
                        raise ValueError(
                            f"No agent registered for phase {phase.value}"
                        )
                    result = agent.execute(self.state, task)
                    if not result.success:
                        raise RuntimeError(
                            f"Phase {phase.value} failed: {result.error}"
                        )
                    self.state.set_phase_output(phase, result.output)
                    self._emit(
                        EventType.PHASE_COMPLETED,
                        phase=phase,
                        payload={"success": True},
                    )

        except Exception as exc:
            self._emit(
                EventType.ERROR_OCCURRED,
                payload={"error": str(exc), "task_id": task.task_id},
            )
            raise

        # This should be unreachable due to DELIVERING always returning,
        # but satisfies the type checker.
        raise RuntimeError("Workflow ended without producing a deliverable")  # pragma: no cover

    def _assemble_deliverable(self, task: TaskInput) -> Deliverable:
        """
        Assemble the final deliverable from accumulated state.

        Args:
            task: Original task input.

        Returns:
            Deliverable object with all outputs.
        """
        plan = self.state.get_phase_output(Phase.PLANNING) or {}
        artifacts = self.state.get_phase_output(Phase.BUILDING) or []
        review = self.state.get_phase_output(Phase.REVIEWING) or {}
        return Deliverable(
            task_id=task.task_id,
            success=True,
            plan=plan,
            artifacts=artifacts,
            review=review,
            final_output=f"Completed task {task.task_id} with {len(artifacts)} artifacts",
            state_snapshot=self.state.snapshot(),
        )


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def event_collector():
    """Fixture: EventCollector for capturing workflow events."""
    return EventCollector()


@pytest.fixture
def mock_agents():
    """Fixture: Standard set of mock agents for happy-path testing."""
    return {
        Phase.PLANNING: MockPlannerAgent(),
        Phase.BUILDING: MockBuilderAgent(),
        Phase.REVIEWING: MockReviewerAgent(),
    }


@pytest.fixture
def failing_agents():
    """Fixture: Agents where BUILDING phase fails via exception."""
    return {
        Phase.PLANNING: MockPlannerAgent(),
        Phase.BUILDING: MockFailingAgent(fail_phase=Phase.BUILDING, use_exception=True),
        Phase.REVIEWING: MockReviewerAgent(),
    }


@pytest.fixture
def contractor(mock_agents, event_collector):
    """Fixture: ArtisanContractor with mock agents and event listener."""
    return ArtisanContractor(
        agents=mock_agents,
        event_listener=event_collector.on_event,
    )


@pytest.fixture
def task_input():
    """Fixture: Standard TaskInput for testing."""
    return TaskInput(
        task_id="test-task-001",
        description="Implement the widget feature",
        parameters={"priority": "high", "complexity": "medium"},
    )


# ============================================================================
# TEST FUNCTIONS
# ============================================================================


def test_full_workflow_happy_path(contractor, task_input, event_collector):
    """
    Test that the complete workflow executes successfully.

    Verifies:
    - Deliverable has success=True with valid structure
    - All agents called exactly once
    - All phases completed
    """
    # Act
    deliverable = contractor.run(task_input)

    # Assert deliverable structure and content
    assert deliverable.success is True
    assert deliverable.task_id == "test-task-001"
    assert len(deliverable.artifacts) == 3
    assert deliverable.plan["steps"] == [
        "step_1_analyze",
        "step_2_design",
        "step_3_implement",
    ]
    assert deliverable.review["approved"] is True
    assert "test-task-001" in deliverable.final_output

    # Assert all agents were called exactly once
    assert contractor.agents[Phase.PLANNING].call_count == 1
    assert contractor.agents[Phase.BUILDING].call_count == 1
    assert contractor.agents[Phase.REVIEWING].call_count == 1

    # Assert events were collected
    assert len(event_collector.events) > 0


def test_phase_ordering(contractor, task_input, event_collector):
    """
    Test that phases execute in the correct order.

    Verifies the exact sequence of phase entry events.
    """
    # Act
    contractor.run(task_input)

    # Assert phase order
    phases_entered = event_collector.get_phases_entered()
    assert phases_entered == [
        Phase.PLANNING,
        Phase.BUILDING,
        Phase.REVIEWING,
        Phase.DELIVERING,
    ]


def test_state_persistence_across_phases(contractor, task_input):
    """
    Test that state produced in one phase is available in subsequent phases.

    Verifies:
    - Planning output (plan dict) is accessible in later phases
    - Building output (artifacts) is built from plan
    - Reviewing output depends on artifacts
    - Each agent received state from previous phases
    """
    # Act
    contractor.run(task_input)

    # Assert state persistence: plan created in PLANNING
    plan = contractor.state.get_phase_output(Phase.PLANNING)
    assert plan is not None
    assert plan["task_id"] == "test-task-001"
    assert len(plan["steps"]) == 3

    # Assert state persistence: artifacts derived from plan in BUILDING
    artifacts = contractor.state.get_phase_output(Phase.BUILDING)
    assert artifacts is not None
    assert len(artifacts) == 3
    assert artifacts[0] == "artifact_for_step_1_analyze"

    # Assert state persistence: review references artifacts in REVIEWING
    review = contractor.state.get_phase_output(Phase.REVIEWING)
    assert review is not None
    assert review["artifacts_reviewed"] == 3

    # Assert builder agent received state with plan but no building output yet
    builder_agent = contractor.agents[Phase.BUILDING]
    assert len(builder_agent.received_states) == 1
    received_state = builder_agent.received_states[0]
    assert received_state.get_phase_output(Phase.PLANNING) is not None
    assert received_state.get_phase_output(Phase.BUILDING) is None


def test_event_emission_sequence(contractor, task_input, event_collector):
    """
    Test that events are emitted in the correct sequence.

    Verifies the exact order of all lifecycle events.
    """
    # Act
    contractor.run(task_input)

    # Assert event sequence
    expected_sequence = [
        EventType.WORKFLOW_STARTED,
        EventType.PHASE_ENTERED,      # PLANNING
        EventType.PHASE_COMPLETED,     # PLANNING
        EventType.PHASE_ENTERED,       # BUILDING
        EventType.PHASE_COMPLETED,     # BUILDING
        EventType.PHASE_ENTERED,       # REVIEWING
        EventType.PHASE_COMPLETED,     # REVIEWING
        EventType.PHASE_ENTERED,       # DELIVERING
        EventType.PHASE_COMPLETED,     # DELIVERING
        EventType.WORKFLOW_COMPLETED,
    ]

    actual_sequence = event_collector.get_event_types_in_order()
    assert actual_sequence == expected_sequence

    # Assert correct phases are in phase_entered events
    phases_entered = event_collector.get_phases_entered()
    assert phases_entered == [
        Phase.PLANNING,
        Phase.BUILDING,
        Phase.REVIEWING,
        Phase.DELIVERING,
    ]


def test_deliverable_structure_and_content(contractor, task_input):
    """
    Test that the deliverable has correct structure and content.

    Verifies all required fields are present and have expected values.
    """
    # Act
    deliverable = contractor.run(task_input)

    # Assert deliverable structure
    assert isinstance(deliverable, Deliverable)
    assert deliverable.task_id == "test-task-001"
    assert deliverable.success is True

    # Assert plan
    assert isinstance(deliverable.plan, dict)
    assert "steps" in deliverable.plan
    assert len(deliverable.plan["steps"]) == 3

    # Assert artifacts
    assert isinstance(deliverable.artifacts, list)
    assert len(deliverable.artifacts) == 3
    assert all(isinstance(art, str) for art in deliverable.artifacts)

    # Assert review
    assert isinstance(deliverable.review, dict)
    assert deliverable.review["approved"] is True
    assert deliverable.review["artifacts_reviewed"] == 3

    # Assert final output
    assert isinstance(deliverable.final_output, str)
    assert "test-task-001" in deliverable.final_output
    assert "3 artifacts" in deliverable.final_output

    # Assert state snapshot
    assert isinstance(deliverable.state_snapshot, WorkflowState)
    assert deliverable.state_snapshot.get_phase_output(Phase.PLANNING) is not None
    assert deliverable.state_snapshot.get_phase_output(Phase.BUILDING) is not None
    assert deliverable.state_snapshot.get_phase_output(Phase.REVIEWING) is not None


def test_error_handling_emits_error_event(event_collector, failing_agents, task_input):
    """
    Test that errors in a phase are caught and emit error events.

    Verifies:
    - RuntimeError is raised when agent fails
    - ERROR_OCCURRED event is emitted
    - Earlier phase events are still recorded
    - Workflow halts at failure point
    """
    # Arrange
    contractor = ArtisanContractor(
        agents=failing_agents,
        event_listener=event_collector.on_event,
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Simulated failure"):
        contractor.run(task_input)

    # Assert error event was emitted
    error_events = event_collector.get_events_by_type(EventType.ERROR_OCCURRED)
    assert len(error_events) == 1
    assert "Simulated failure" in error_events[0].payload["error"]
    assert error_events[0].payload["task_id"] == "test-task-001"

    # Assert partial event sequence before failure
    phases_entered = event_collector.get_phases_entered()
    assert Phase.PLANNING in phases_entered
    assert Phase.BUILDING in phases_entered  # entered but failed
    assert Phase.REVIEWING not in phases_entered  # never entered

    # Assert workflow_completed was never emitted
    completed_events = event_collector.get_events_by_type(
        EventType.WORKFLOW_COMPLETED
    )
    assert len(completed_events) == 0


def test_state_serialization_persistence(contractor, task_input):
    """
    Test that workflow state can be serialized and deserialized.

    Verifies JSON round-trip preserves state data.
    """
    # Act
    contractor.run(task_input)

    # Serialize
    json_str = contractor.state.to_json()
    assert isinstance(json_str, str)

    # Verify valid JSON
    parsed = json.loads(json_str)
    assert "phase_outputs" in parsed
    assert "metadata" in parsed

    # Deserialize
    restored = WorkflowState.from_json(json_str)

    # Assert round-trip equality
    assert (
        restored.get_phase_output(Phase.PLANNING)
        == contractor.state.get_phase_output(Phase.PLANNING)
    )
    assert (
        restored.get_phase_output(Phase.BUILDING)
        == contractor.state.get_phase_output(Phase.BUILDING)
    )
    assert (
        restored.get_phase_output(Phase.REVIEWING)
        == contractor.state.get_phase_output(Phase.REVIEWING)
    )


def test_idempotent_rerun(mock_agents, event_collector, task_input):
    """
    Test that running the same contractor twice produces identical results.

    Verifies state is reset between runs and outputs are consistent.
    """
    # Arrange
    contractor = ArtisanContractor(
        agents=mock_agents,
        event_listener=event_collector.on_event,
    )

    # Act: First run
    deliverable1 = contractor.run(task_input)
    events_count_after_first = len(event_collector.events)

    # Act: Second run (clear events to test isolation)
    event_collector.clear()
    deliverable2 = contractor.run(task_input)

    # Assert deliverables are equivalent
    assert deliverable1.task_id == deliverable2.task_id
    assert deliverable1.plan == deliverable2.plan
    assert deliverable1.artifacts == deliverable2.artifacts
    assert deliverable1.review == deliverable2.review

    # Assert second run generated same event count
    assert len(event_collector.events) == events_count_after_first


def test_empty_task_input(contractor, event_collector):
    """
    Test that empty task input still completes successfully.

    Verifies mock agents don't depend on description or parameters.
    """
    # Arrange
    task = TaskInput(task_id="empty-task", description="", parameters={})

    # Act
    deliverable = contractor.run(task)

    # Assert success
    assert deliverable.success is True
    assert deliverable.task_id == "empty-task"
    assert len(deliverable.artifacts) == 3

    # Assert workflow completed
    completed_events = event_collector.get_events_by_type(
        EventType.WORKFLOW_COMPLETED
    )
    assert len(completed_events) == 1


def test_large_payload_state_persistence(event_collector):
    """
    Test that state persists correctly with large payloads.

    Verifies JSON serialization handles 1000+ steps and artifacts.
    """

    # Arrange: Create agents that produce large outputs
    class LargePlannerAgent(BaseAgent):
        def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
            large_plan = {
                "task_id": task.task_id,
                "steps": [f"step_{idx}" for idx in range(1000)],
                "estimated_phases": 1000,
            }
            return PhaseResult(phase=Phase.PLANNING, success=True, output=large_plan)

    class LargeBuilderAgent(BaseAgent):
        def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
            plan = state.get_phase_output(Phase.PLANNING)
            artifacts = [
                f"artifact_for_{step}" for step in plan.get("steps", [])
            ]
            return PhaseResult(phase=Phase.BUILDING, success=True, output=artifacts)

    class LargeReviewerAgent(BaseAgent):
        def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
            artifacts = state.get_phase_output(Phase.BUILDING)
            review = {
                "artifacts_reviewed": len(artifacts),
                "approved": True,
                "comments": "Large batch processed successfully.",
            }
            return PhaseResult(phase=Phase.REVIEWING, success=True, output=review)

    agents = {
        Phase.PLANNING: LargePlannerAgent(),
        Phase.BUILDING: LargeBuilderAgent(),
        Phase.REVIEWING: LargeReviewerAgent(),
    }
    contractor = ArtisanContractor(
        agents=agents,
        event_listener=event_collector.on_event,
    )
    task = TaskInput(task_id="large-task", description="Process 1000 items")

    # Act
    deliverable = contractor.run(task)

    # Assert large payload persisted
    assert len(deliverable.artifacts) == 1000
    assert deliverable.review["artifacts_reviewed"] == 1000

    # Assert serialization handles large state
    json_str = contractor.state.to_json()
    restored = WorkflowState.from_json(json_str)
    restored_artifacts = restored.get_phase_output(Phase.BUILDING)
    assert len(restored_artifacts) == 1000


def test_missing_agent_for_phase(mock_agents, event_collector):
    """
    Test that missing agent for a phase raises ValueError.

    Verifies ERROR_OCCURRED event is emitted.
    """
    # Arrange: Remove BUILDING agent
    incomplete_agents = {
        Phase.PLANNING: mock_agents[Phase.PLANNING],
        # Phase.BUILDING is intentionally missing
        Phase.REVIEWING: mock_agents[Phase.REVIEWING],
    }
    contractor = ArtisanContractor(
        agents=incomplete_agents,
        event_listener=event_collector.on_event,
    )
    task = TaskInput(task_id="test", description="test")

    # Act & Assert
    with pytest.raises(ValueError, match="No agent registered"):
        contractor.run(task)

    # Assert error event
    error_events = event_collector.get_events_by_type(EventType.ERROR_OCCURRED)
    assert len(error_events) == 1


def test_agent_returns_failure_status(event_collector):
    """
    Test that agent returning success=False halts workflow.

    Verifies RuntimeError is raised and ERROR_OCCURRED event emitted.
    """

    # Arrange: Agent that returns failure without exception
    class FailingBuilderAgent(BaseAgent):
        def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
            return PhaseResult(
                phase=Phase.BUILDING,
                success=False,
                output=None,
                error="Resource limit exceeded",
            )

    agents = {
        Phase.PLANNING: MockPlannerAgent(),
        Phase.BUILDING: FailingBuilderAgent(),
        Phase.REVIEWING: MockReviewerAgent(),
    }
    contractor = ArtisanContractor(
        agents=agents,
        event_listener=event_collector.on_event,
    )
    task = TaskInput(task_id="test", description="test")

    # Act & Assert
    with pytest.raises(RuntimeError, match="Resource limit exceeded"):
        contractor.run(task)

    # Assert error event
    error_events = event_collector.get_events_by_type(EventType.ERROR_OCCURRED)
    assert len(error_events) == 1
    assert "Resource limit exceeded" in error_events[0].payload["error"]


def test_contractor_without_event_listener(mock_agents, task_input):
    """
    Test that contractor works fine with no event listener.

    Verifies workflow completes successfully without event emission crashes.
    """
    # Arrange
    contractor = ArtisanContractor(agents=mock_agents, event_listener=None)

    # Act
    deliverable = contractor.run(task_input)

    # Assert
    assert deliverable.success is True
    assert len(deliverable.artifacts) == 3


def test_state_access_before_phase_runs(event_collector):
    """
    Test that accessing state before a phase runs returns None gracefully.

    Verifies no crash, returns None, and workflow continues.
    """

    # Arrange: Agent that checks for nonexistent prior phase output
    class EarlyAccessAgent(BaseAgent):
        def _do_execute(self, state: WorkflowState, task: TaskInput) -> PhaseResult:
            # Try to access REVIEWING output before REVIEWING runs
            review = state.get_phase_output(Phase.REVIEWING)
            # Should be None but not crash
            output = f"Review exists: {review is not None}"
            return PhaseResult(phase=Phase.PLANNING, success=True, output=output)

    agents = {
        Phase.PLANNING: EarlyAccessAgent(),
        Phase.BUILDING: MockBuilderAgent(),
        Phase.REVIEWING: MockReviewerAgent(),
    }
    contractor = ArtisanContractor(
        agents=agents,
        event_listener=event_collector.on_event,
    )
    task = TaskInput(task_id="test", description="test")

    # Act
    deliverable = contractor.run(task)

    # Assert: Workflow completed despite early access
    assert deliverable.success is True
    # The early access agent's output shows False
    assert "Review exists: False" == contractor.state.get_phase_output(Phase.PLANNING)


def test_task_with_special_characters(contractor, event_collector):
    """
    Test that task_id with special characters serializes correctly.

    Verifies JSON handles unicode and special characters.
    """
    # Arrange
    task = TaskInput(
        task_id="task-üñíçødé-🎯",
        description="Unicode test: 日本語, العربية, Русский",
        parameters={"emoji": "🚀", "symbol": "€¥£"},
    )

    # Act
    deliverable = contractor.run(task)

    # Assert
    assert deliverable.task_id == "task-üñíçødé-🎯"

    # Assert serialization handles unicode
    json_str = contractor.state.to_json()
    restored = WorkflowState.from_json(json_str)
    assert restored.get_phase_output(Phase.PLANNING) is not None


def test_multiple_runs_state_isolation(mock_agents, event_collector):
    """
    Test that multiple runs on same contractor instance are isolated.

    Verifies state is reset for each run.
    """
    # Arrange
    contractor = ArtisanContractor(
        agents=mock_agents,
        event_listener=event_collector.on_event,
    )

    # Act: Run with task 1
    task1 = TaskInput(task_id="task-1", description="First task")
    deliverable1 = contractor.run(task1)

    state1_plan = contractor.state.get_phase_output(Phase.PLANNING)

    event_collector.clear()

    # Act: Run with task 2
    task2 = TaskInput(task_id="task-2", description="Second task")
    deliverable2 = contractor.run(task2)

    state2_plan = contractor.state.get_phase_output(Phase.PLANNING)

    # Assert tasks are different
    assert deliverable1.task_id == "task-1"
    assert deliverable2.task_id == "task-2"

    # Assert state was reset (new plan objects with different task_ids)
    assert state1_plan["task_id"] == "task-1"
    assert state2_plan["task_id"] == "task-2"
    assert state1_plan is not state2_plan


def test_agent_call_order_matches_phase_order(mock_agents, task_input):
    """
    Test that agents are called in phase order.

    Verifies call_count on agents and order of execution via received states.
    """
    # Arrange
    contractor = ArtisanContractor(agents=mock_agents)

    # Act
    contractor.run(task_input)

    # Assert each agent was called exactly once
    planner = mock_agents[Phase.PLANNING]
    builder = mock_agents[Phase.BUILDING]
    reviewer = mock_agents[Phase.REVIEWING]

    assert planner.call_count == 1
    assert builder.call_count == 1
    assert reviewer.call_count == 1

    # Assert builder received state with planning output only
    builder_received_states = builder.received_states
    assert len(builder_received_states) == 1
    first_received = builder_received_states[0]
    assert first_received.get_phase_output(Phase.PLANNING) is not None
    assert first_received.get_phase_output(Phase.BUILDING) is None
    assert first_received.get_phase_output(Phase.REVIEWING) is None

    # Assert reviewer received state with planning and building output
    reviewer_received_states = reviewer.received_states
    assert len(reviewer_received_states) == 1
    first_received_by_reviewer = reviewer_received_states[0]
    assert first_received_by_reviewer.get_phase_output(Phase.PLANNING) is not None
    assert first_received_by_reviewer.get_phase_output(Phase.BUILDING) is not None
    assert first_received_by_reviewer.get_phase_output(Phase.REVIEWING) is None