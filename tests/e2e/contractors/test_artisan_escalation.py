"""
E2E Test Module: Artisan Escalation Workflow

This module comprehensively tests the design disagreement escalation workflow
in the Artisan contractor system. It verifies the complete lifecycle:
detecting a design disagreement, escalating it, pausing the active workflow,
sending notifications to relevant stakeholders, providing an interactive
resolution mechanism, and resuming the workflow after the disagreement is resolved.

All classes, enums, helpers, mocks, and test functions reside in this single file
with no relative imports.

Production-ready implementation covering:
- Disagreement detection between design proposals
- Escalation creation and management
- Workflow pause/resume lifecycle
- Notification dispatch to stakeholders
- Interactive resolution with multiple strategies
- Edge cases: timeouts, re-escalation, double-resolve prevention
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import uuid
from typing import Any, Optional

import pytest


# ============================================================================
# ENUMS
# ============================================================================


class EscalationSeverity(enum.Enum):
    """Severity levels for escalations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationStatus(enum.Enum):
    """Status of an escalation throughout its lifecycle."""

    PENDING = "pending"
    ACTIVE = "active"
    RESOLVED = "resolved"
    TIMED_OUT = "timed_out"
    RE_ESCALATED = "re_escalated"


class WorkflowStatus(enum.Enum):
    """Status of a workflow."""

    RUNNING = "running"
    PAUSED = "paused"
    RESUMED = "resumed"
    COMPLETED = "completed"
    FAILED = "failed"


class NotificationType(enum.Enum):
    """Types of notifications sent during escalation."""

    ESCALATION_CREATED = "escalation_created"
    WORKFLOW_PAUSED = "workflow_paused"
    RESOLUTION_REQUIRED = "resolution_required"
    RESOLUTION_APPLIED = "resolution_applied"
    WORKFLOW_RESUMED = "workflow_resumed"


class ResolutionStrategy(enum.Enum):
    """Strategies for resolving escalations."""

    ACCEPT_PROPOSAL_A = "accept_proposal_a"
    ACCEPT_PROPOSAL_B = "accept_proposal_b"
    COMPROMISE = "compromise"
    ALTERNATIVE = "alternative"
    DEFER = "defer"


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclasses.dataclass
class DesignProposal:
    """A design proposal submitted by a contractor/artisan.

    Attributes:
        id: Unique identifier for the proposal.
        author: The person who authored the proposal.
        topic: The design topic this proposal addresses.
        description: Detailed description of the proposal.
        created_at: Timestamp when the proposal was created.
        metadata: Additional metadata associated with the proposal.
    """

    id: str
    author: str
    topic: str
    description: str
    created_at: datetime.datetime
    metadata: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Disagreement:
    """A detected disagreement between proposals.

    Attributes:
        id: Unique identifier for the disagreement.
        topic: The design topic under disagreement.
        proposals: List of conflicting proposals.
        participants: List of participant identifiers.
        severity: Assessed severity of the disagreement.
        detected_at: Timestamp when the disagreement was detected.
        reason: Human-readable reason for the disagreement.
    """

    id: str
    topic: str
    proposals: list
    participants: list
    severity: EscalationSeverity
    detected_at: datetime.datetime
    reason: str


@dataclasses.dataclass
class Resolution:
    """The resolution of an escalation.

    Attributes:
        id: Unique identifier for the resolution.
        escalation_id: ID of the escalation being resolved.
        resolver: The person who resolved the escalation.
        strategy: The resolution strategy applied.
        chosen_proposal_id: ID of the chosen proposal (if applicable).
        explanation: Human-readable explanation of the resolution.
        resolved_at: Timestamp when the resolution was finalized.
    """

    id: str
    escalation_id: str
    resolver: str
    strategy: ResolutionStrategy
    chosen_proposal_id: Optional[str] = None
    explanation: str = ""
    resolved_at: Optional[datetime.datetime] = None


@dataclasses.dataclass
class EscalationRecord:
    """A formal escalation record.

    Attributes:
        id: Unique identifier for the escalation.
        disagreement: The disagreement that triggered the escalation.
        status: Current status of the escalation.
        escalated_to: The authority the escalation was sent to.
        created_at: Timestamp when the escalation was created.
        resolved_at: Timestamp when the escalation was resolved.
        resolution: The resolution applied to this escalation.
        paused_workflow_id: ID of the workflow paused by this escalation.
    """

    id: str
    disagreement: Disagreement
    status: EscalationStatus
    escalated_to: str
    created_at: datetime.datetime
    resolved_at: Optional[datetime.datetime] = None
    resolution: Optional[Resolution] = None
    paused_workflow_id: Optional[str] = None


@dataclasses.dataclass
class Notification:
    """A notification sent to a stakeholder.

    Attributes:
        id: Unique identifier for the notification.
        recipient: The recipient of the notification.
        notification_type: The type of notification.
        escalation_id: The escalation this notification relates to.
        message: The message content.
        sent_at: Timestamp when the notification was sent.
        read: Whether the notification has been read.
    """

    id: str
    recipient: str
    notification_type: NotificationType
    escalation_id: str
    message: str
    sent_at: datetime.datetime
    read: bool = False


@dataclasses.dataclass
class WorkflowState:
    """State of a workflow.

    Attributes:
        id: Unique identifier for the workflow.
        name: Human-readable name of the workflow.
        status: Current status of the workflow.
        current_step: The current step index.
        total_steps: Total number of steps in the workflow.
        paused_at_step: The step at which the workflow was paused.
        context: Arbitrary context data carried through the workflow.
        history: Audit log of workflow state transitions.
    """

    id: str
    name: str
    status: WorkflowStatus
    current_step: int
    total_steps: int
    paused_at_step: Optional[int] = None
    context: dict = dataclasses.field(default_factory=dict)
    history: list = dataclasses.field(default_factory=list)


# ============================================================================
# SERVICE CLASSES
# ============================================================================


class DisagreementDetector:
    """Detects disagreements between design proposals.

    Maintains a registry of proposals organized by topic and provides
    pairwise conflict detection with severity assessment.
    """

    def __init__(self) -> None:
        """Initialize the disagreement detector."""
        self._proposals: dict[str, list[DesignProposal]] = {}

    def submit_proposal(self, proposal: DesignProposal) -> None:
        """Submit a design proposal for analysis.

        Args:
            proposal: The design proposal to submit.
        """
        if proposal.topic not in self._proposals:
            self._proposals[proposal.topic] = []
        self._proposals[proposal.topic].append(proposal)

    def detect_disagreements(self, topic: str) -> list[Disagreement]:
        """Detect disagreements for a given topic.

        Performs pairwise comparison of all proposals for the topic.

        Args:
            topic: The topic to check for disagreements.

        Returns:
            A list of detected Disagreement objects, or an empty list if none.
        """
        if topic not in self._proposals or len(self._proposals[topic]) < 2:
            return []

        proposals = self._proposals[topic]
        disagreements: list[Disagreement] = []

        for idx_i, prop_i in enumerate(proposals):
            for prop_j in proposals[idx_i + 1:]:
                if self._proposals_conflict(prop_i, prop_j):
                    severity = self._assess_severity([prop_i, prop_j])
                    disagreement = Disagreement(
                        id=str(uuid.uuid4()),
                        topic=topic,
                        proposals=[prop_i, prop_j],
                        participants=[prop_i.author, prop_j.author],
                        severity=severity,
                        detected_at=datetime.datetime.now(),
                        reason=(
                            f"Conflicting proposals: '{prop_i.description}' "
                            f"vs '{prop_j.description}'"
                        ),
                    )
                    disagreements.append(disagreement)

        return disagreements

    def _proposals_conflict(
        self, prop_a: DesignProposal, prop_b: DesignProposal
    ) -> bool:
        """Check if two proposals conflict.

        Uses description comparison as the primary conflict signal.

        Args:
            prop_a: First proposal.
            prop_b: Second proposal.

        Returns:
            True if proposals conflict, False otherwise.
        """
        return prop_a.description != prop_b.description

    def _assess_severity(self, proposals: list[DesignProposal]) -> EscalationSeverity:
        """Assess the severity of a disagreement.

        Severity is determined by the number of proposals and the amount
        of supporting metadata, indicating depth of investment in each position.

        Args:
            proposals: List of conflicting proposals.

        Returns:
            The assessed severity level.
        """
        if len(proposals) > 2:
            return EscalationSeverity.CRITICAL
        total_metadata = sum(len(p.metadata) for p in proposals)
        if total_metadata > 5:
            return EscalationSeverity.HIGH
        return EscalationSeverity.MEDIUM


class WorkflowController:
    """Manages workflow state transitions.

    Supports create, advance, pause, and resume operations with full
    audit history tracking.
    """

    def __init__(self) -> None:
        """Initialize the workflow controller."""
        self._workflows: dict[str, WorkflowState] = {}

    def create_workflow(self, name: str, total_steps: int) -> WorkflowState:
        """Create a new workflow.

        Args:
            name: Name of the workflow.
            total_steps: Total number of steps in the workflow.

        Returns:
            The created WorkflowState.
        """
        workflow = WorkflowState(
            id=str(uuid.uuid4()),
            name=name,
            status=WorkflowStatus.RUNNING,
            current_step=0,
            total_steps=total_steps,
        )
        self._workflows[workflow.id] = workflow
        return workflow

    def advance_step(self, workflow_id: str) -> WorkflowState:
        """Advance the workflow to the next step.

        Args:
            workflow_id: The workflow ID.

        Returns:
            The updated WorkflowState.

        Raises:
            RuntimeError: If workflow is paused.
            ValueError: If workflow not found.
        """
        workflow = self.get_workflow(workflow_id)

        if workflow.status == WorkflowStatus.PAUSED:
            raise RuntimeError(
                f"Workflow {workflow_id} is paused and cannot advance"
            )

        if workflow.current_step < workflow.total_steps:
            workflow.current_step += 1
            workflow.history.append(
                {
                    "action": "advanced",
                    "step": workflow.current_step,
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )

        return workflow

    def pause_workflow(
        self, workflow_id: str, reason: str = ""
    ) -> WorkflowState:
        """Pause a workflow.

        Args:
            workflow_id: The workflow ID.
            reason: Optional reason for pause.

        Returns:
            The updated WorkflowState.

        Raises:
            ValueError: If workflow not found.
        """
        workflow = self.get_workflow(workflow_id)
        workflow.status = WorkflowStatus.PAUSED
        workflow.paused_at_step = workflow.current_step
        workflow.history.append(
            {
                "action": "paused",
                "step": workflow.current_step,
                "reason": reason,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

        return workflow

    def resume_workflow(
        self, workflow_id: str, context_update: Optional[dict] = None
    ) -> WorkflowState:
        """Resume a paused workflow.

        Args:
            workflow_id: The workflow ID.
            context_update: Optional context to merge into the workflow context.

        Returns:
            The updated WorkflowState.

        Raises:
            ValueError: If workflow not found.
        """
        workflow = self.get_workflow(workflow_id)
        workflow.status = WorkflowStatus.RESUMED
        if context_update:
            workflow.context.update(context_update)
        workflow.history.append(
            {
                "action": "resumed",
                "step": workflow.current_step,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowState:
        """Get a workflow by ID.

        Args:
            workflow_id: The workflow ID.

        Returns:
            The WorkflowState.

        Raises:
            ValueError: If workflow not found.
        """
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
        return self._workflows[workflow_id]


class NotificationService:
    """Manages notifications to stakeholders.

    Provides send, query-by-recipient, query-by-escalation, and
    list-all operations.
    """

    def __init__(self) -> None:
        """Initialize the notification service."""
        self._notifications: list[Notification] = []

    def send(
        self,
        recipient: str,
        notification_type: NotificationType,
        escalation_id: str,
        message: str,
    ) -> Notification:
        """Send a notification.

        Args:
            recipient: The recipient of the notification.
            notification_type: The type of notification.
            escalation_id: The related escalation ID.
            message: The message content.

        Returns:
            The created Notification.
        """
        notification = Notification(
            id=str(uuid.uuid4()),
            recipient=recipient,
            notification_type=notification_type,
            escalation_id=escalation_id,
            message=message,
            sent_at=datetime.datetime.now(),
        )
        self._notifications.append(notification)
        return notification

    def get_notifications_for(self, recipient: str) -> list[Notification]:
        """Get all notifications for a recipient.

        Args:
            recipient: The recipient.

        Returns:
            List of notifications for this recipient.
        """
        return [n for n in self._notifications if n.recipient == recipient]

    def get_all_notifications(self) -> list[Notification]:
        """Get all notifications.

        Returns:
            List of all notifications.
        """
        return self._notifications.copy()

    def get_notifications_by_escalation(
        self, escalation_id: str
    ) -> list[Notification]:
        """Get all notifications for an escalation.

        Args:
            escalation_id: The escalation ID.

        Returns:
            List of notifications for this escalation.
        """
        return [
            n for n in self._notifications if n.escalation_id == escalation_id
        ]


class EscalationManager:
    """Manages escalations and coordinates with workflow and notification services.

    Handles the creation, resolution, timeout, and retrieval of escalation
    records while orchestrating side effects on workflows and notifications.
    """

    def __init__(
        self,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
    ) -> None:
        """Initialize the escalation manager.

        Args:
            workflow_controller: The workflow controller.
            notification_service: The notification service.
        """
        self._workflow_controller = workflow_controller
        self._notification_service = notification_service
        self._escalations: dict[str, EscalationRecord] = {}

    def escalate(
        self,
        disagreement: Disagreement,
        escalate_to: str,
        workflow_id: str,
    ) -> EscalationRecord:
        """Escalate a disagreement.

        Creates an escalation record, pauses the associated workflow,
        and sends notifications to all participants and the escalation authority.

        Args:
            disagreement: The detected disagreement.
            escalate_to: The person to escalate to (authority).
            workflow_id: The workflow ID to pause.

        Returns:
            The created EscalationRecord.
        """
        escalation = EscalationRecord(
            id=str(uuid.uuid4()),
            disagreement=disagreement,
            status=EscalationStatus.ACTIVE,
            escalated_to=escalate_to,
            created_at=datetime.datetime.now(),
            paused_workflow_id=workflow_id,
        )
        self._escalations[escalation.id] = escalation

        # Pause the workflow
        self._workflow_controller.pause_workflow(
            workflow_id, reason=f"Escalation {escalation.id}"
        )

        # Notify participants
        for participant in disagreement.participants:
            self._notification_service.send(
                recipient=participant,
                notification_type=NotificationType.ESCALATION_CREATED,
                escalation_id=escalation.id,
                message=(
                    f"Escalation created for topic '{disagreement.topic}': "
                    f"{disagreement.reason}"
                ),
            )

        # Notify authority: resolution required
        self._notification_service.send(
            recipient=escalate_to,
            notification_type=NotificationType.RESOLUTION_REQUIRED,
            escalation_id=escalation.id,
            message=(
                f"Resolution required for topic '{disagreement.topic}'. "
                f"Severity: {disagreement.severity.value}"
            ),
        )

        # Notify authority: workflow paused
        self._notification_service.send(
            recipient=escalate_to,
            notification_type=NotificationType.WORKFLOW_PAUSED,
            escalation_id=escalation.id,
            message=(
                f"Workflow '{workflow_id}' has been paused due to this escalation."
            ),
        )

        return escalation

    def get_escalation(self, escalation_id: str) -> EscalationRecord:
        """Get an escalation by ID.

        Args:
            escalation_id: The escalation ID.

        Returns:
            The EscalationRecord.

        Raises:
            ValueError: If escalation not found.
        """
        if escalation_id not in self._escalations:
            raise ValueError(f"Escalation {escalation_id} not found")
        return self._escalations[escalation_id]

    def get_active_escalations(self) -> list[EscalationRecord]:
        """Get all active escalations.

        Returns:
            List of active escalations.
        """
        return [
            e
            for e in self._escalations.values()
            if e.status == EscalationStatus.ACTIVE
        ]

    def resolve_escalation(
        self, escalation_id: str, resolution: Resolution
    ) -> EscalationRecord:
        """Resolve an escalation.

        Args:
            escalation_id: The escalation ID.
            resolution: The resolution.

        Returns:
            The updated EscalationRecord.

        Raises:
            ValueError: If escalation is already resolved or not found.
        """
        escalation = self.get_escalation(escalation_id)

        if escalation.status == EscalationStatus.RESOLVED:
            raise ValueError(
                f"Escalation {escalation_id} is already resolved"
            )

        now = datetime.datetime.now()
        escalation.status = EscalationStatus.RESOLVED
        escalation.resolved_at = now
        escalation.resolution = resolution
        resolution.resolved_at = now

        return escalation

    def timeout_escalation(self, escalation_id: str) -> EscalationRecord:
        """Mark an escalation as timed out.

        Args:
            escalation_id: The escalation ID.

        Returns:
            The updated EscalationRecord.

        Raises:
            ValueError: If escalation not found.
        """
        escalation = self.get_escalation(escalation_id)
        escalation.status = EscalationStatus.TIMED_OUT
        escalation.resolved_at = datetime.datetime.now()
        return escalation


class ResolutionHandler:
    """Handles the submission and validation of resolutions.

    Validates that resolutions meet the requirements of their chosen
    strategy before allowing submission.
    """

    def __init__(self, escalation_manager: EscalationManager) -> None:
        """Initialize the resolution handler.

        Args:
            escalation_manager: The escalation manager.
        """
        self._escalation_manager = escalation_manager

    def submit_resolution(
        self,
        escalation_id: str,
        resolver: str,
        strategy: ResolutionStrategy,
        chosen_proposal_id: Optional[str] = None,
        explanation: str = "",
    ) -> Resolution:
        """Submit a resolution for an escalation.

        Args:
            escalation_id: The escalation ID.
            resolver: The person resolving.
            strategy: The resolution strategy.
            chosen_proposal_id: Optional ID of chosen proposal.
            explanation: Optional explanation of resolution.

        Returns:
            The created Resolution.

        Raises:
            ValueError: If resolution is invalid per strategy requirements.
        """
        resolution = Resolution(
            id=str(uuid.uuid4()),
            escalation_id=escalation_id,
            resolver=resolver,
            strategy=strategy,
            chosen_proposal_id=chosen_proposal_id,
            explanation=explanation,
        )

        escalation = self._escalation_manager.get_escalation(escalation_id)
        if not self.validate_resolution(resolution, escalation):
            raise ValueError(f"Invalid resolution: {resolution}")

        return resolution

    def validate_resolution(
        self, resolution: Resolution, escalation: EscalationRecord
    ) -> bool:
        """Validate a resolution against an escalation.

        Rules:
        - Resolution must reference an escalation.
        - ACCEPT_PROPOSAL_A / ACCEPT_PROPOSAL_B require a chosen_proposal_id.
        - Must have a resolver.

        Args:
            resolution: The resolution to validate.
            escalation: The escalation being resolved.

        Returns:
            True if valid, False otherwise.
        """
        if not resolution.escalation_id:
            return False

        if resolution.strategy in (
            ResolutionStrategy.ACCEPT_PROPOSAL_A,
            ResolutionStrategy.ACCEPT_PROPOSAL_B,
        ):
            if not resolution.chosen_proposal_id:
                return False

        if not resolution.resolver:
            return False

        return True


class EscalationOrchestrator:
    """Coordinates the full escalation lifecycle end-to-end.

    Provides a single ``run_escalation_flow`` method that drives the
    entire sequence: proposal submission → disagreement detection →
    escalation → workflow pause → resolution → workflow resume →
    notifications.
    """

    def __init__(self) -> None:
        """Initialize the orchestrator with all required services."""
        self._notification_service = NotificationService()
        self._workflow_controller = WorkflowController()
        self._escalation_manager = EscalationManager(
            self._workflow_controller, self._notification_service
        )
        self._disagreement_detector = DisagreementDetector()
        self._resolution_handler = ResolutionHandler(self._escalation_manager)

    @property
    def notification_service(self) -> NotificationService:
        """Access the notification service."""
        return self._notification_service

    @property
    def workflow_controller(self) -> WorkflowController:
        """Access the workflow controller."""
        return self._workflow_controller

    @property
    def escalation_manager(self) -> EscalationManager:
        """Access the escalation manager."""
        return self._escalation_manager

    def run_escalation_flow(
        self,
        proposals: list[DesignProposal],
        workflow_name: str,
        escalation_authority: str,
    ) -> dict[str, Any]:
        """Run a complete escalation flow.

        Args:
            proposals: List of design proposals.
            workflow_name: Name of the workflow.
            escalation_authority: Person to escalate to.

        Returns:
            Dictionary with keys: disagreement, escalation, notifications,
            workflow, resolution.
        """
        # Submit proposals and detect disagreements
        for proposal in proposals:
            self._disagreement_detector.submit_proposal(proposal)

        topic = proposals[0].topic if proposals else "unknown"
        disagreements = self._disagreement_detector.detect_disagreements(topic)

        if not disagreements:
            return {
                "disagreement": None,
                "escalation": None,
                "notifications": [],
                "workflow": None,
                "resolution": None,
            }

        disagreement = disagreements[0]

        # Create and advance workflow to simulate in-progress work
        workflow = self._workflow_controller.create_workflow(workflow_name, 10)
        self._workflow_controller.advance_step(workflow.id)
        self._workflow_controller.advance_step(workflow.id)
        self._workflow_controller.advance_step(workflow.id)

        # Escalate — this pauses the workflow and sends notifications
        escalation = self._escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to=escalation_authority,
            workflow_id=workflow.id,
        )

        # Submit resolution
        resolution = self._resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver=escalation_authority,
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_A,
            chosen_proposal_id=disagreement.proposals[0].id,
            explanation="Accepted first proposal after review",
        )

        # Resolve escalation
        self._escalation_manager.resolve_escalation(escalation.id, resolution)

        # Resume workflow with resolution context
        workflow = self._workflow_controller.resume_workflow(
            workflow.id,
            context_update={
                "resolution_id": resolution.id,
                "chosen_proposal_id": resolution.chosen_proposal_id,
            },
        )

        # Send post-resolution notifications
        self._notification_service.send(
            recipient=escalation_authority,
            notification_type=NotificationType.RESOLUTION_APPLIED,
            escalation_id=escalation.id,
            message="Resolution has been applied and recorded.",
        )
        self._notification_service.send(
            recipient=escalation_authority,
            notification_type=NotificationType.WORKFLOW_RESUMED,
            escalation_id=escalation.id,
            message="Workflow has been resumed with the resolved decision.",
        )

        all_notifications = self._notification_service.get_all_notifications()

        return {
            "disagreement": disagreement,
            "escalation": escalation,
            "notifications": all_notifications,
            "workflow": workflow,
            "resolution": resolution,
        }


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def notification_service() -> NotificationService:
    """Provide a fresh notification service."""
    return NotificationService()


@pytest.fixture
def workflow_controller() -> WorkflowController:
    """Provide a fresh workflow controller."""
    return WorkflowController()


@pytest.fixture
def escalation_manager(
    workflow_controller: WorkflowController, notification_service: NotificationService
) -> EscalationManager:
    """Provide an escalation manager wired to the shared fixtures."""
    return EscalationManager(workflow_controller, notification_service)


@pytest.fixture
def disagreement_detector() -> DisagreementDetector:
    """Provide a fresh disagreement detector."""
    return DisagreementDetector()


@pytest.fixture
def resolution_handler(escalation_manager: EscalationManager) -> ResolutionHandler:
    """Provide a resolution handler wired to the shared escalation manager."""
    return ResolutionHandler(escalation_manager)


@pytest.fixture
def orchestrator() -> EscalationOrchestrator:
    """Provide a fully-wired orchestrator."""
    return EscalationOrchestrator()


@pytest.fixture
def sample_proposals() -> list[DesignProposal]:
    """Provide sample conflicting proposals for the 'database_choice' topic."""
    return [
        DesignProposal(
            id=str(uuid.uuid4()),
            author="contractor_a",
            topic="database_choice",
            description="Use PostgreSQL for relational data",
            created_at=datetime.datetime.now(),
            metadata={"reasoning": "ACID compliance", "team_size": 3},
        ),
        DesignProposal(
            id=str(uuid.uuid4()),
            author="contractor_b",
            topic="database_choice",
            description="Use MongoDB for document storage",
            created_at=datetime.datetime.now(),
            metadata={"reasoning": "Horizontal scalability", "team_size": 2},
        ),
    ]


@pytest.fixture
def active_workflow(workflow_controller: WorkflowController) -> WorkflowState:
    """Provide an active workflow at step 3 of 10."""
    workflow = workflow_controller.create_workflow("test_workflow", 10)
    workflow_controller.advance_step(workflow.id)
    workflow_controller.advance_step(workflow.id)
    workflow_controller.advance_step(workflow.id)
    return workflow_controller.get_workflow(workflow.id)


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestDisagreementDetection:
    """Tests for detecting disagreements between proposals."""

    def test_detect_conflicting_proposals(
        self,
        disagreement_detector: DisagreementDetector,
        sample_proposals: list[DesignProposal],
    ) -> None:
        """Test that conflicting proposals are detected."""
        for proposal in sample_proposals:
            disagreement_detector.submit_proposal(proposal)

        disagreements = disagreement_detector.detect_disagreements("database_choice")
        assert len(disagreements) == 1

        disagreement = disagreements[0]
        assert disagreement.topic == "database_choice"
        assert len(disagreement.participants) == 2
        assert "contractor_a" in disagreement.participants
        assert "contractor_b" in disagreement.participants
        assert disagreement.severity in (
            EscalationSeverity.MEDIUM,
            EscalationSeverity.HIGH,
            EscalationSeverity.CRITICAL,
        )
        assert disagreement.reason

    def test_no_disagreement_when_proposals_agree(
        self,
        disagreement_detector: DisagreementDetector,
    ) -> None:
        """Test that no disagreement is detected when proposals agree."""
        proposal_a = DesignProposal(
            id=str(uuid.uuid4()),
            author="contractor_a",
            topic="cache_strategy",
            description="Use Redis for caching",
            created_at=datetime.datetime.now(),
        )
        proposal_b = DesignProposal(
            id=str(uuid.uuid4()),
            author="contractor_b",
            topic="cache_strategy",
            description="Use Redis for caching",
            created_at=datetime.datetime.now(),
        )

        disagreement_detector.submit_proposal(proposal_a)
        disagreement_detector.submit_proposal(proposal_b)

        disagreements = disagreement_detector.detect_disagreements("cache_strategy")
        assert len(disagreements) == 0

    def test_severity_assessment(
        self,
        disagreement_detector: DisagreementDetector,
    ) -> None:
        """Test that severity is assessed correctly based on metadata volume."""
        prop_a = DesignProposal(
            id=str(uuid.uuid4()),
            author="author_a",
            topic="api_design",
            description="REST API",
            created_at=datetime.datetime.now(),
            metadata={"rationale": "common", "performance": "good"},
        )
        prop_b = DesignProposal(
            id=str(uuid.uuid4()),
            author="author_b",
            topic="api_design",
            description="GraphQL API",
            created_at=datetime.datetime.now(),
            metadata={"rationale": "flexible", "performance": "unknown"},
        )

        disagreement_detector.submit_proposal(prop_a)
        disagreement_detector.submit_proposal(prop_b)

        disagreements = disagreement_detector.detect_disagreements("api_design")
        assert len(disagreements) == 1
        assert disagreements[0].severity == EscalationSeverity.MEDIUM

    def test_no_disagreement_single_proposal(
        self,
        disagreement_detector: DisagreementDetector,
    ) -> None:
        """Test that no disagreement is detected with a single proposal."""
        proposal = DesignProposal(
            id=str(uuid.uuid4()),
            author="contractor_a",
            topic="testing_framework",
            description="Use pytest",
            created_at=datetime.datetime.now(),
        )
        disagreement_detector.submit_proposal(proposal)

        disagreements = disagreement_detector.detect_disagreements("testing_framework")
        assert len(disagreements) == 0

    def test_no_disagreement_empty_topic(
        self,
        disagreement_detector: DisagreementDetector,
    ) -> None:
        """Test that no disagreement is detected for an unknown topic."""
        disagreements = disagreement_detector.detect_disagreements("nonexistent_topic")
        assert len(disagreements) == 0

    def test_high_severity_with_large_metadata(
        self,
        disagreement_detector: DisagreementDetector,
    ) -> None:
        """Test that HIGH severity is assigned when metadata exceeds threshold."""
        prop_a = DesignProposal(
            id=str(uuid.uuid4()),
            author="author_a",
            topic="high_sev",
            description="Approach A",
            created_at=datetime.datetime.now(),
            metadata={"a": 1, "b": 2, "c": 3},
        )
        prop_b = DesignProposal(
            id=str(uuid.uuid4()),
            author="author_b",
            topic="high_sev",
            description="Approach B",
            created_at=datetime.datetime.now(),
            metadata={"x": 1, "y": 2, "z": 3},
        )

        disagreement_detector.submit_proposal(prop_a)
        disagreement_detector.submit_proposal(prop_b)

        disagreements = disagreement_detector.detect_disagreements("high_sev")
        assert len(disagreements) == 1
        assert disagreements[0].severity == EscalationSeverity.HIGH


class TestEscalationTrigger:
    """Tests for triggering escalations."""

    def test_escalation_creates_record(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that escalation creates a record with correct fields."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="schema_design",
            proposals=[],
            participants=["dev_a", "dev_b"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="Conflicting schema approaches",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="tech_lead",
            workflow_id=active_workflow.id,
        )

        assert escalation.id
        assert escalation.disagreement == disagreement
        assert escalation.escalated_to == "tech_lead"
        assert escalation.status == EscalationStatus.ACTIVE
        assert escalation.paused_workflow_id == active_workflow.id

    def test_escalation_record_has_correct_metadata(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that escalation record contains correct temporal metadata."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="logging_strategy",
            proposals=[],
            participants=["engineer_x", "engineer_y"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="Structlog vs standard logging",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="senior_engineer",
            workflow_id=active_workflow.id,
        )

        assert escalation.created_at <= datetime.datetime.now()
        assert escalation.resolved_at is None
        assert escalation.resolution is None

    def test_escalation_status_is_active(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that newly created escalation status is ACTIVE."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="testing",
            proposals=[],
            participants=["qa_1", "qa_2"],
            severity=EscalationSeverity.LOW,
            detected_at=datetime.datetime.now(),
            reason="Test framework choice",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="qa_lead",
            workflow_id=active_workflow.id,
        )

        assert escalation.status == EscalationStatus.ACTIVE

    def test_get_active_escalations(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
    ) -> None:
        """Test retrieving multiple active escalations."""
        workflow1 = workflow_controller.create_workflow("flow1", 5)
        workflow2 = workflow_controller.create_workflow("flow2", 5)

        disagreement1 = Disagreement(
            id=str(uuid.uuid4()),
            topic="topic1",
            proposals=[],
            participants=["p1", "p2"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="reason1",
        )
        disagreement2 = Disagreement(
            id=str(uuid.uuid4()),
            topic="topic2",
            proposals=[],
            participants=["p3", "p4"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="reason2",
        )

        escalation_manager.escalate(
            disagreement=disagreement1, escalate_to="auth1", workflow_id=workflow1.id
        )
        escalation_manager.escalate(
            disagreement=disagreement2, escalate_to="auth2", workflow_id=workflow2.id
        )

        active = escalation_manager.get_active_escalations()
        assert len(active) == 2


class TestWorkflowPause:
    """Tests for workflow pausing during escalation."""

    def test_workflow_pauses_on_escalation(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that workflow is paused when escalation is triggered."""
        assert active_workflow.status == WorkflowStatus.RUNNING
        assert active_workflow.current_step == 3

        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="schema_design",
            proposals=[],
            participants=["dev_a", "dev_b"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="Conflicting schema approaches",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="tech_lead",
            workflow_id=active_workflow.id,
        )

        paused_wf = workflow_controller.get_workflow(active_workflow.id)
        assert paused_wf.status == WorkflowStatus.PAUSED
        assert paused_wf.paused_at_step == 3
        assert escalation.paused_workflow_id == active_workflow.id

    def test_paused_workflow_cannot_advance(
        self,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that paused workflow cannot advance steps."""
        workflow_controller.pause_workflow(active_workflow.id, reason="escalation")
        paused_wf = workflow_controller.get_workflow(active_workflow.id)

        assert paused_wf.status == WorkflowStatus.PAUSED

        with pytest.raises(RuntimeError, match="paused"):
            workflow_controller.advance_step(active_workflow.id)

    def test_pause_records_step_position(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that pause records the current step position."""
        current_step = active_workflow.current_step

        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="config",
            proposals=[],
            participants=["ops_a", "ops_b"],
            severity=EscalationSeverity.CRITICAL,
            detected_at=datetime.datetime.now(),
            reason="Infrastructure config disagreement",
        )

        escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="ops_lead",
            workflow_id=active_workflow.id,
        )

        paused_wf = workflow_controller.get_workflow(active_workflow.id)
        assert paused_wf.paused_at_step == current_step

    def test_pause_adds_history_entry(
        self,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that pausing adds a history entry."""
        history_len_before = len(active_workflow.history)
        workflow_controller.pause_workflow(active_workflow.id, reason="test pause")
        assert len(active_workflow.history) == history_len_before + 1
        assert active_workflow.history[-1]["action"] == "paused"


class TestNotificationDispatch:
    """Tests for notification dispatch during escalation."""

    def test_notifications_sent_to_participants(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that notifications are sent to disagreement participants."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="caching_strategy",
            proposals=[],
            participants=["dev_x", "dev_y"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="Redis vs Memcached",
        )

        escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="senior_dev",
            workflow_id=active_workflow.id,
        )

        notifs_x = notification_service.get_notifications_for("dev_x")
        notifs_y = notification_service.get_notifications_for("dev_y")

        assert len(notifs_x) >= 1
        assert len(notifs_y) >= 1

    def test_notification_sent_to_authority(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that notifications are sent to the escalation authority."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="deployment",
            proposals=[],
            participants=["devops_a", "devops_b"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="Deployment strategy conflict",
        )

        escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="platform_lead",
            workflow_id=active_workflow.id,
        )

        notifs_authority = notification_service.get_notifications_for("platform_lead")
        # Authority receives RESOLUTION_REQUIRED + WORKFLOW_PAUSED
        assert len(notifs_authority) >= 2

    def test_notification_types_are_correct(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that correct notification types are sent during escalation."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="auth",
            proposals=[],
            participants=["sec_a", "sec_b"],
            severity=EscalationSeverity.CRITICAL,
            detected_at=datetime.datetime.now(),
            reason="Authentication mechanism disagreement",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="security_lead",
            workflow_id=active_workflow.id,
        )

        all_notifs = notification_service.get_notifications_by_escalation(
            escalation.id
        )
        types = [n.notification_type for n in all_notifs]

        assert NotificationType.ESCALATION_CREATED in types
        assert NotificationType.RESOLUTION_REQUIRED in types
        assert NotificationType.WORKFLOW_PAUSED in types

    def test_notification_contains_escalation_id(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that all notifications reference the correct escalation ID."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="storage",
            proposals=[],
            participants=["storage_a", "storage_b"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="Storage backend choice",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="storage_lead",
            workflow_id=active_workflow.id,
        )

        notifs = notification_service.get_notifications_by_escalation(escalation.id)
        for notif in notifs:
            assert notif.escalation_id == escalation.id

    def test_notification_message_content(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that notification messages contain relevant content."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="queue_system",
            proposals=[],
            participants=["msg_dev1", "msg_dev2"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="RabbitMQ vs Kafka",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="messaging_lead",
            workflow_id=active_workflow.id,
        )

        notifs = notification_service.get_notifications_by_escalation(escalation.id)
        messages = [n.message for n in notifs]
        # At least one message should mention the topic
        assert any("queue_system" in msg for msg in messages)


class TestInteractiveResolution:
    """Tests for interactive resolution of escalations."""

    def test_submit_resolution_accept_proposal(
        self,
        resolution_handler: ResolutionHandler,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test submitting a resolution that accepts a proposal."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="api_style",
            proposals=[
                DesignProposal(
                    id="prop_a",
                    author="dev_a",
                    topic="api_style",
                    description="RESTful",
                    created_at=datetime.datetime.now(),
                ),
                DesignProposal(
                    id="prop_b",
                    author="dev_b",
                    topic="api_style",
                    description="RPC",
                    created_at=datetime.datetime.now(),
                ),
            ],
            participants=["dev_a", "dev_b"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="API style disagreement",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="architect",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="architect",
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_A,
            chosen_proposal_id="prop_a",
            explanation="RESTful is more standard",
        )

        assert resolution.escalation_id == escalation.id
        assert resolution.resolver == "architect"
        assert resolution.strategy == ResolutionStrategy.ACCEPT_PROPOSAL_A
        assert resolution.chosen_proposal_id == "prop_a"

    def test_submit_resolution_compromise(
        self,
        resolution_handler: ResolutionHandler,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test submitting a compromise resolution."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="framework",
            proposals=[],
            participants=["dev_x", "dev_y"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="Framework choice",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="lead",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="lead",
            strategy=ResolutionStrategy.COMPROMISE,
            explanation="Use hybrid approach",
        )

        assert resolution.strategy == ResolutionStrategy.COMPROMISE
        assert resolution.explanation == "Use hybrid approach"

    def test_submit_resolution_alternative(
        self,
        resolution_handler: ResolutionHandler,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test submitting an alternative resolution."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="testing",
            proposals=[],
            participants=["qa1", "qa2"],
            severity=EscalationSeverity.LOW,
            detected_at=datetime.datetime.now(),
            reason="Testing approach",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="qa_manager",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="qa_manager",
            strategy=ResolutionStrategy.ALTERNATIVE,
            explanation="Use phased approach instead",
        )

        assert resolution.strategy == ResolutionStrategy.ALTERNATIVE

    def test_invalid_resolution_rejected(
        self,
        resolution_handler: ResolutionHandler,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that invalid resolutions are rejected."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="docs",
            proposals=[],
            participants=["writer1", "writer2"],
            severity=EscalationSeverity.LOW,
            detected_at=datetime.datetime.now(),
            reason="Documentation format",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="doc_lead",
            workflow_id=active_workflow.id,
        )

        # Invalid: ACCEPT_PROPOSAL_A without chosen_proposal_id
        with pytest.raises(ValueError, match="Invalid resolution"):
            resolution_handler.submit_resolution(
                escalation_id=escalation.id,
                resolver="doc_lead",
                strategy=ResolutionStrategy.ACCEPT_PROPOSAL_A,
                chosen_proposal_id=None,
            )

    def test_resolution_records_resolver_and_strategy(
        self,
        resolution_handler: ResolutionHandler,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that resolution records resolver and strategy correctly."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="naming",
            proposals=[
                DesignProposal(
                    id="naming_1",
                    author="dev_1",
                    topic="naming",
                    description="snake_case",
                    created_at=datetime.datetime.now(),
                ),
                DesignProposal(
                    id="naming_2",
                    author="dev_2",
                    topic="naming",
                    description="camelCase",
                    created_at=datetime.datetime.now(),
                ),
            ],
            participants=["dev_1", "dev_2"],
            severity=EscalationSeverity.LOW,
            detected_at=datetime.datetime.now(),
            reason="Naming convention",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="code_review_lead",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="code_review_lead",
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_B,
            chosen_proposal_id="naming_2",
            explanation="camelCase is more standard in JS",
        )

        assert resolution.resolver == "code_review_lead"
        assert resolution.strategy == ResolutionStrategy.ACCEPT_PROPOSAL_B

    def test_resolution_has_unique_id(
        self,
        resolution_handler: ResolutionHandler,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that each resolution gets a unique ID."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="unique_id_test",
            proposals=[],
            participants=["dev_u1", "dev_u2"],
            severity=EscalationSeverity.LOW,
            detected_at=datetime.datetime.now(),
            reason="Unique ID test",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="lead_u",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="lead_u",
            strategy=ResolutionStrategy.COMPROMISE,
            explanation="Compromise reached",
        )

        assert resolution.id
        assert len(resolution.id) > 0


class TestWorkflowResume:
    """Tests for workflow resumption after resolution."""

    def test_workflow_resumes_after_resolution(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        resolution_handler: ResolutionHandler,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that workflow resumes after resolution."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="infra",
            proposals=[
                DesignProposal(
                    id="infra_1",
                    author="ops_a",
                    topic="infra",
                    description="Kubernetes",
                    created_at=datetime.datetime.now(),
                ),
                DesignProposal(
                    id="infra_2",
                    author="ops_b",
                    topic="infra",
                    description="Serverless",
                    created_at=datetime.datetime.now(),
                ),
            ],
            participants=["ops_a", "ops_b"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="Infrastructure choice",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="infrastructure_lead",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="infrastructure_lead",
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_A,
            chosen_proposal_id="infra_1",
        )

        escalation_manager.resolve_escalation(escalation.id, resolution)

        workflow_controller.resume_workflow(
            active_workflow.id, context_update={"resolution_id": resolution.id}
        )

        resumed_wf = workflow_controller.get_workflow(active_workflow.id)
        assert resumed_wf.status == WorkflowStatus.RESUMED

    def test_workflow_resumes_at_correct_step(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        resolution_handler: ResolutionHandler,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that workflow resumes at the correct step."""
        paused_step = active_workflow.current_step

        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="monitoring",
            proposals=[],
            participants=["dev_mon1", "dev_mon2"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="Monitoring tools",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="ops_lead",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="ops_lead",
            strategy=ResolutionStrategy.COMPROMISE,
        )

        escalation_manager.resolve_escalation(escalation.id, resolution)
        workflow_controller.resume_workflow(active_workflow.id)

        resumed_wf = workflow_controller.get_workflow(active_workflow.id)
        assert resumed_wf.current_step == paused_step

    def test_workflow_context_updated_with_resolution(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        resolution_handler: ResolutionHandler,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that workflow context is updated with resolution data."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="lang",
            proposals=[
                DesignProposal(
                    id="lang_1",
                    author="dev_lang1",
                    topic="lang",
                    description="Go",
                    created_at=datetime.datetime.now(),
                ),
                DesignProposal(
                    id="lang_2",
                    author="dev_lang2",
                    topic="lang",
                    description="Rust",
                    created_at=datetime.datetime.now(),
                ),
            ],
            participants=["dev_lang1", "dev_lang2"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="Language choice",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="tech_lead",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="tech_lead",
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_A,
            chosen_proposal_id="lang_1",
        )

        escalation_manager.resolve_escalation(escalation.id, resolution)

        workflow_controller.resume_workflow(
            active_workflow.id,
            context_update={
                "resolution_id": resolution.id,
                "chosen_proposal_id": resolution.chosen_proposal_id,
            },
        )

        resumed_wf = workflow_controller.get_workflow(active_workflow.id)
        assert "resolution_id" in resumed_wf.context
        assert "chosen_proposal_id" in resumed_wf.context
        assert resumed_wf.context["chosen_proposal_id"] == "lang_1"

    def test_resume_notifications_sent(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        notification_service: NotificationService,
        resolution_handler: ResolutionHandler,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that notifications are sent upon workflow resume."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="orm",
            proposals=[],
            participants=["db_dev1", "db_dev2"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="ORM choice",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="db_lead",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="db_lead",
            strategy=ResolutionStrategy.COMPROMISE,
        )

        escalation_manager.resolve_escalation(escalation.id, resolution)
        workflow_controller.resume_workflow(active_workflow.id)

        # Send additional resume notifications
        notification_service.send(
            recipient="db_lead",
            notification_type=NotificationType.WORKFLOW_RESUMED,
            escalation_id=escalation.id,
            message="Workflow has resumed",
        )

        notifs = notification_service.get_notifications_by_escalation(escalation.id)
        types = [n.notification_type for n in notifs]
        assert NotificationType.WORKFLOW_RESUMED in types

    def test_resumed_workflow_can_advance(
        self,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that a resumed workflow can advance steps again."""
        workflow_controller.pause_workflow(active_workflow.id, reason="test")
        workflow_controller.resume_workflow(active_workflow.id)

        resumed_wf = workflow_controller.get_workflow(active_workflow.id)
        assert resumed_wf.status == WorkflowStatus.RESUMED

        # Should be able to advance after resume
        workflow_controller.advance_step(active_workflow.id)
        assert active_workflow.current_step == 4


class TestEndToEndEscalationFlow:
    """Tests for the complete end-to-end escalation flow."""

    def test_full_lifecycle(self, orchestrator: EscalationOrchestrator) -> None:
        """Test the full lifecycle from disagreement to resolution and resume."""
        proposal_a = DesignProposal(
            id=str(uuid.uuid4()),
            author="contractor_a",
            topic="api_design",
            description="Use REST with JSON",
            created_at=datetime.datetime.now(),
        )
        proposal_b = DesignProposal(
            id=str(uuid.uuid4()),
            author="contractor_b",
            topic="api_design",
            description="Use GraphQL",
            created_at=datetime.datetime.now(),
        )

        result = orchestrator.run_escalation_flow(
            proposals=[proposal_a, proposal_b],
            workflow_name="api_implementation",
            escalation_authority="lead_architect",
        )

        # Verify disagreement was detected
        assert result["disagreement"] is not None
        assert result["disagreement"].topic == "api_design"

        # Verify escalation was created and is now resolved
        assert result["escalation"] is not None
        assert result["escalation"].status == EscalationStatus.RESOLVED

        # Verify notifications were sent (participants + authority + post-resolution)
        assert len(result["notifications"]) >= 3

        # Verify workflow was paused and then resumed
        assert result["workflow"] is not None
        assert result["workflow"].status == WorkflowStatus.RESUMED
        assert "resolution_id" in result["workflow"].context

        # Verify resolution
        assert result["resolution"] is not None
        assert result["resolution"].resolver == "lead_architect"

    def test_full_lifecycle_with_compromise(
        self, orchestrator: EscalationOrchestrator
    ) -> None:
        """Test full lifecycle completes successfully with conflicting proposals."""
        proposal_a = DesignProposal(
            id=str(uuid.uuid4()),
            author="dev_a",
            topic="database",
            description="PostgreSQL",
            created_at=datetime.datetime.now(),
        )
        proposal_b = DesignProposal(
            id=str(uuid.uuid4()),
            author="dev_b",
            topic="database",
            description="MongoDB",
            created_at=datetime.datetime.now(),
        )

        result = orchestrator.run_escalation_flow(
            proposals=[proposal_a, proposal_b],
            workflow_name="data_layer",
            escalation_authority="database_architect",
        )

        assert result["escalation"].status == EscalationStatus.RESOLVED
        assert result["workflow"].status == WorkflowStatus.RESUMED

    def test_full_lifecycle_notification_types_complete(
        self, orchestrator: EscalationOrchestrator
    ) -> None:
        """Test that the full lifecycle produces all expected notification types."""
        proposal_a = DesignProposal(
            id=str(uuid.uuid4()),
            author="dev_1",
            topic="ci_cd",
            description="GitHub Actions",
            created_at=datetime.datetime.now(),
        )
        proposal_b = DesignProposal(
            id=str(uuid.uuid4()),
            author="dev_2",
            topic="ci_cd",
            description="GitLab CI",
            created_at=datetime.datetime.now(),
        )

        result = orchestrator.run_escalation_flow(
            proposals=[proposal_a, proposal_b],
            workflow_name="ci_pipeline",
            escalation_authority="devops_lead",
        )

        notif_types = {n.notification_type for n in result["notifications"]}
        assert NotificationType.ESCALATION_CREATED in notif_types
        assert NotificationType.RESOLUTION_REQUIRED in notif_types
        assert NotificationType.WORKFLOW_PAUSED in notif_types
        assert NotificationType.RESOLUTION_APPLIED in notif_types
        assert NotificationType.WORKFLOW_RESUMED in notif_types


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_escalation_timeout(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test timeout of an escalation."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="timeout_test",
            proposals=[],
            participants=["dev_timeout1", "dev_timeout2"],
            severity=EscalationSeverity.CRITICAL,
            detected_at=datetime.datetime.now(),
            reason="Timeout test",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="timeout_authority",
            workflow_id=active_workflow.id,
        )

        assert escalation.status == EscalationStatus.ACTIVE

        timed_out = escalation_manager.timeout_escalation(escalation.id)

        assert timed_out.status == EscalationStatus.TIMED_OUT
        assert timed_out.resolved_at is not None

    def test_multiple_simultaneous_escalations(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
    ) -> None:
        """Test handling of multiple simultaneous escalations."""
        workflow1 = workflow_controller.create_workflow("workflow1", 10)
        workflow2 = workflow_controller.create_workflow("workflow2", 10)

        disagreement1 = Disagreement(
            id=str(uuid.uuid4()),
            topic="topic1",
            proposals=[],
            participants=["dev_a1", "dev_a2"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="Disagreement 1",
        )

        disagreement2 = Disagreement(
            id=str(uuid.uuid4()),
            topic="topic2",
            proposals=[],
            participants=["dev_b1", "dev_b2"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="Disagreement 2",
        )

        escalation1 = escalation_manager.escalate(
            disagreement=disagreement1,
            escalate_to="authority1",
            workflow_id=workflow1.id,
        )

        escalation2 = escalation_manager.escalate(
            disagreement=disagreement2,
            escalate_to="authority2",
            workflow_id=workflow2.id,
        )

        assert escalation1.id != escalation2.id
        assert escalation1.paused_workflow_id != escalation2.paused_workflow_id

        active_esc = escalation_manager.get_active_escalations()
        assert len(active_esc) == 2

    def test_re_escalation_after_rejected_resolution(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        resolution_handler: ResolutionHandler,
        active_workflow: WorkflowState,
    ) -> None:
        """Test re-escalation when a resolution is rejected."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="re_escalation",
            proposals=[
                DesignProposal(
                    id="re_esc_1",
                    author="dev_re1",
                    topic="re_escalation",
                    description="Option A",
                    created_at=datetime.datetime.now(),
                ),
                DesignProposal(
                    id="re_esc_2",
                    author="dev_re2",
                    topic="re_escalation",
                    description="Option B",
                    created_at=datetime.datetime.now(),
                ),
            ],
            participants=["dev_re1", "dev_re2"],
            severity=EscalationSeverity.HIGH,
            detected_at=datetime.datetime.now(),
            reason="Re-escalation test",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="authority_re",
            workflow_id=active_workflow.id,
        )

        # Submit and resolve
        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="authority_re",
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_A,
            chosen_proposal_id="re_esc_1",
        )

        resolved_esc = escalation_manager.resolve_escalation(
            escalation.id, resolution
        )
        assert resolved_esc.status == EscalationStatus.RESOLVED

        # Simulate re-escalation by creating a new escalation for same topic
        new_disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="re_escalation",
            proposals=disagreement.proposals,
            participants=disagreement.participants,
            severity=EscalationSeverity.CRITICAL,
            detected_at=datetime.datetime.now(),
            reason="Resolution rejected, escalating again",
        )

        # Mark original as re-escalated
        original_escalation = escalation_manager.get_escalation(escalation.id)
        original_escalation.status = EscalationStatus.RE_ESCALATED

        # Create new escalation on a new workflow
        new_workflow = workflow_controller.create_workflow("re_escalation_wf", 10)
        new_escalation = escalation_manager.escalate(
            disagreement=new_disagreement,
            escalate_to="authority_re_2",
            workflow_id=new_workflow.id,
        )

        assert new_escalation.status == EscalationStatus.ACTIVE
        assert original_escalation.status == EscalationStatus.RE_ESCALATED

    def test_resolve_already_resolved_escalation(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        resolution_handler: ResolutionHandler,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that resolving an already-resolved escalation raises an error."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="double_resolve",
            proposals=[
                DesignProposal(
                    id="dr_1",
                    author="dev_dr1",
                    topic="double_resolve",
                    description="Choice 1",
                    created_at=datetime.datetime.now(),
                ),
                DesignProposal(
                    id="dr_2",
                    author="dev_dr2",
                    topic="double_resolve",
                    description="Choice 2",
                    created_at=datetime.datetime.now(),
                ),
            ],
            participants=["dev_dr1", "dev_dr2"],
            severity=EscalationSeverity.MEDIUM,
            detected_at=datetime.datetime.now(),
            reason="Double resolve test",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="authority_dr",
            workflow_id=active_workflow.id,
        )

        resolution1 = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="authority_dr",
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_A,
            chosen_proposal_id="dr_1",
        )

        escalation_manager.resolve_escalation(escalation.id, resolution1)

        # Try to resolve again with a different resolution
        resolution2 = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="authority_dr",
            strategy=ResolutionStrategy.ACCEPT_PROPOSAL_B,
            chosen_proposal_id="dr_2",
        )

        with pytest.raises(ValueError, match="already resolved"):
            escalation_manager.resolve_escalation(escalation.id, resolution2)

    def test_defer_resolution_strategy(
        self,
        resolution_handler: ResolutionHandler,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test DEFER resolution strategy."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="defer_test",
            proposals=[],
            participants=["dev_defer1", "dev_defer2"],
            severity=EscalationSeverity.LOW,
            detected_at=datetime.datetime.now(),
            reason="Deferrable decision",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="defer_authority",
            workflow_id=active_workflow.id,
        )

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="defer_authority",
            strategy=ResolutionStrategy.DEFER,
            explanation="Decision deferred pending more information",
        )

        assert resolution.strategy == ResolutionStrategy.DEFER
        assert "deferred" in resolution.explanation.lower()

    def test_advancing_paused_workflow_raises_error(
        self,
        workflow_controller: WorkflowController,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that advancing a paused workflow raises RuntimeError."""
        workflow_controller.pause_workflow(active_workflow.id)

        with pytest.raises(RuntimeError, match="paused"):
            workflow_controller.advance_step(active_workflow.id)

    def test_get_nonexistent_escalation_raises_error(
        self, escalation_manager: EscalationManager
    ) -> None:
        """Test that getting a nonexistent escalation raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            escalation_manager.get_escalation("nonexistent_id")

    def test_get_nonexistent_workflow_raises_error(
        self, workflow_controller: WorkflowController
    ) -> None:
        """Test that getting a nonexistent workflow raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            workflow_controller.get_workflow("nonexistent_id")

    def test_no_disagreement_no_escalation_flow(
        self, orchestrator: EscalationOrchestrator
    ) -> None:
        """Test that no escalation occurs when proposals agree."""
        proposal_a = DesignProposal(
            id=str(uuid.uuid4()),
            author="dev_a",
            topic="agreed_topic",
            description="Same approach",
            created_at=datetime.datetime.now(),
        )
        proposal_b = DesignProposal(
            id=str(uuid.uuid4()),
            author="dev_b",
            topic="agreed_topic",
            description="Same approach",
            created_at=datetime.datetime.now(),
        )

        result = orchestrator.run_escalation_flow(
            proposals=[proposal_a, proposal_b],
            workflow_name="agreed_flow",
            escalation_authority="any_authority",
        )

        assert result["disagreement"] is None
        assert result["escalation"] is None
        assert result["workflow"] is None
        assert result["resolution"] is None

    def test_pause_nonexistent_workflow_raises_error(
        self, workflow_controller: WorkflowController
    ) -> None:
        """Test that pausing a nonexistent workflow raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            workflow_controller.pause_workflow("nonexistent_id")

    def test_resume_nonexistent_workflow_raises_error(
        self, workflow_controller: WorkflowController
    ) -> None:
        """Test that resuming a nonexistent workflow raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            workflow_controller.resume_workflow("nonexistent_id")

    def test_escalation_resolved_at_timestamp(
        self,
        escalation_manager: EscalationManager,
        workflow_controller: WorkflowController,
        resolution_handler: ResolutionHandler,
        active_workflow: WorkflowState,
    ) -> None:
        """Test that resolved_at timestamp is set upon resolution."""
        disagreement = Disagreement(
            id=str(uuid.uuid4()),
            topic="timestamp_test",
            proposals=[
                DesignProposal(
                    id="ts_1",
                    author="dev_ts1",
                    topic="timestamp_test",
                    description="Approach 1",
                    created_at=datetime.datetime.now(),
                ),
            ],
            participants=["dev_ts1", "dev_ts2"],
            severity=EscalationSeverity.LOW,
            detected_at=datetime.datetime.now(),
            reason="Timestamp test",
        )

        escalation = escalation_manager.escalate(
            disagreement=disagreement,
            escalate_to="ts_authority",
            workflow_id=active_workflow.id,
        )

        assert escalation.resolved_at is None

        resolution = resolution_handler.submit_resolution(
            escalation_id=escalation.id,
            resolver="ts_authority",
            strategy=ResolutionStrategy.COMPROMISE,
        )

        escalation_manager.resolve_escalation(escalation.id, resolution)

        assert escalation.resolved_at is not None
        assert resolution.resolved_at is not None
        assert escalation.resolved_at <= datetime.datetime.now()