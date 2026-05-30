"""
PrimaryContractorContextCoreWorkflow - Primary Contractor with ContextCore Task Tracking.

Extends the Primary Contractor pattern with integrated task tracking via ContextCore.
Tasks are modeled as OpenTelemetry spans, enabling unified project observability.

Features:
- Creates ContextCore task span when workflow starts
- Updates task status at each workflow phase
- Emits insights for key decisions (spec approach, review verdicts)
- Completes/fails task when workflow finishes
- Supports local storage (file-based) or OTLP export (Tempo)

Pattern:
1. Start ContextCore task → status: "pending"
2. Claude creates spec → status: "in_progress", event: "spec_created"
3. Drafter implements → event: "draft_N_created"
4. Claude reviews → event: "review_N_complete" (includes score)
5. Loop until pass or max iterations
6. Claude integrates → event: "integration_complete"
7. Complete task → status: "completed" or "failed"

Usage:
    result = workflow.run(
        config={
            "task_description": "Implement rate limiter",
            "task_id": "P1-RATELIMIT",
            "project_id": "contextcore",
            "parent_id": "PHASE-1",  # Optional parent task/story
            "drafter_agent": "openai:gpt-4o-mini",
        }
    )
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import os

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    WorkflowMetadata,
    WorkflowInput,
    WorkflowResult,
    WorkflowMetrics,
    StepResult,
    AgentCount,
    ValidationResult,
    ProjectContext,
)
from ...agents import BaseAgent
from ...utils.agent_resolution import resolve_agent_spec
from ...logging_config import get_logger

# Import existing Primary Contractor components
from .primary_contractor_workflow import (
    PrimaryContractorWorkflow,
    SPEC_PROMPT_TEMPLATE,
    DRAFT_PROMPT_TEMPLATE,
    REVIEW_PROMPT_TEMPLATE,
    INTEGRATION_PROMPT_TEMPLATE,
)
from .primary_contractor_models import (
    PrimaryContractorResult,
    WorkflowPhase,
)

logger = get_logger(__name__)


class ContextCoreTaskTracker:
    """
    Wrapper for ContextCore task tracking.

    Handles both cases:
    - ContextCore installed: Uses TaskTracker and InsightEmitter
    - ContextCore not installed: Logs operations without tracking
    """

    def __init__(
        self,
        project_id: str,
        task_id: str,
        parent_id: Optional[str] = None,
        local_storage: Optional[str] = None,
    ):
        self.project_id = project_id
        self.task_id = task_id
        self.parent_id = parent_id
        self.local_storage = local_storage or os.environ.get("CONTEXTCORE_LOCAL_STORAGE")
        self._tracker = None
        self._emitter = None
        self._enabled = False

        self._initialize()

    def _initialize(self):
        """Try to initialize ContextCore components."""
        try:
            from contextcore import TaskTracker
            from contextcore.agent import InsightEmitter

            # Set local storage env if provided
            if self.local_storage:
                os.environ["CONTEXTCORE_LOCAL_STORAGE"] = self.local_storage

            self._tracker = TaskTracker(project=self.project_id)
            self._emitter = InsightEmitter(
                project_id=self.project_id,
                agent_id="startd8-primary-contractor"
            )
            self._enabled = True
            logger.info(f"ContextCore tracking enabled for task {self.task_id}")

        except ImportError:
            logger.warning("ContextCore not installed - task tracking disabled")
            self._enabled = False
        except Exception as e:
            logger.warning(f"Failed to initialize ContextCore: {e}")
            self._enabled = False

    def start_task(self, title: str, task_type: str = "task") -> bool:
        """Start tracking the task."""
        if not self._enabled:
            logger.info(f"[mock] Start task: {self.task_id} - {title}")
            return False

        try:
            self._tracker.start_task(
                task_id=self.task_id,
                title=title,
                task_type=task_type,
                parent_id=self.parent_id,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start task: {e}")
            return False

    def update_status(self, status: str) -> bool:
        """Update task status."""
        if not self._enabled:
            logger.info(f"[mock] Update status: {self.task_id} -> {status}")
            return False

        try:
            self._tracker.update_status(self.task_id, status)
            return True
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            return False

    def add_event(self, event_name: str, attributes: Optional[Dict[str, Any]] = None) -> bool:
        """Add an event to the task span."""
        if not self._enabled:
            logger.info(f"[mock] Add event: {self.task_id} - {event_name}")
            return False

        try:
            self._tracker.add_event(self.task_id, event_name, attributes or {})
            return True
        except Exception as e:
            logger.error(f"Failed to add event: {e}")
            return False

    def complete_task(self) -> bool:
        """Mark task as completed."""
        if not self._enabled:
            logger.info(f"[mock] Complete task: {self.task_id}")
            return False

        try:
            self._tracker.complete_task(self.task_id)
            return True
        except Exception as e:
            logger.error(f"Failed to complete task: {e}")
            return False

    def fail_task(self, reason: str) -> bool:
        """Mark task as failed."""
        if not self._enabled:
            logger.info(f"[mock] Fail task: {self.task_id} - {reason}")
            return False

        try:
            self._tracker.cancel_task(self.task_id, reason=reason)
            return True
        except Exception as e:
            logger.error(f"Failed to fail task: {e}")
            return False

    def emit_decision(
        self,
        summary: str,
        confidence: float = 0.9,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Emit a decision insight."""
        if not self._enabled or not self._emitter:
            logger.info(f"[mock] Emit decision: {summary} (confidence: {confidence})")
            return False

        try:
            self._emitter.emit_decision(
                summary=summary,
                confidence=confidence,
                context=context or {},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to emit decision: {e}")
            return False

    def emit_lesson(
        self,
        summary: str,
        category: str = "workflow",
        applies_to: Optional[List[str]] = None,
    ) -> bool:
        """Emit a lesson learned insight."""
        if not self._enabled or not self._emitter:
            logger.info(f"[mock] Emit lesson: {summary}")
            return False

        try:
            self._emitter.emit_lesson(
                summary=summary,
                category=category,
                applies_to=applies_to or [],
            )
            return True
        except Exception as e:
            logger.error(f"Failed to emit lesson: {e}")
            return False


class PrimaryContractorContextCoreWorkflow(PrimaryContractorWorkflow):
    """
    Primary Contractor workflow with integrated ContextCore task tracking.

    Extends PrimaryContractorWorkflow to automatically track workflow execution
    as ContextCore task spans, enabling project observability integration.

    Additional Config:
        {
            "task_id": "string - ContextCore task ID (required for tracking)",
            "project_id": "string - ContextCore project ID (default: 'default')",
            "parent_id": "string - Parent task/story ID (optional)",
            "local_storage": "string - Path for local storage (optional)",
            "emit_insights": true - Whether to emit decision insights (default: true),
        }

    Example:
        result = workflow.run(
            config={
                "task_description": "Implement rate limiter",
                "task_id": "P1-RATELIMIT",
                "project_id": "my-project",
                "parent_id": "PHASE-1",
                "drafter_agent": "openai:gpt-4o-mini",
            }
        )
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        """Override metadata to include ContextCore inputs."""
        base = super().metadata

        # Add ContextCore-specific inputs
        contextcore_inputs = [
            WorkflowInput(
                name="task_id",
                type="string",
                required=False,
                description="ContextCore task ID for tracking (enables task-as-span tracking)"
            ),
            WorkflowInput(
                name="project_id",
                type="string",
                required=False,
                default="default",
                description="ContextCore project ID"
            ),
            WorkflowInput(
                name="parent_id",
                type="string",
                required=False,
                description="Parent task/story ID in ContextCore hierarchy"
            ),
            WorkflowInput(
                name="local_storage",
                type="string",
                required=False,
                description="Path for local task storage (if OTLP unavailable)"
            ),
            WorkflowInput(
                name="emit_insights",
                type="boolean",
                required=False,
                default=True,
                description="Whether to emit decision/lesson insights"
            ),
        ]

        return WorkflowMetadata(
            workflow_id="primary-contractor-contextcore",
            name="Primary Contractor with ContextCore Tracking",
            description="Cost-efficient multi-agent pattern with integrated task-as-spans tracking",
            version="1.0.0",
            capabilities=base.capabilities + ["contextcore-tracking", "task-as-spans", "observability"],
            tags=base.tags + ["contextcore", "observability", "project-tracking"],
            requires_agents=base.requires_agents,
            agent_count=base.agent_count,
            min_agents=base.min_agents,
            max_agents=base.max_agents,
            inputs=base.inputs + contextcore_inputs,
        )

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute with ContextCore task tracking."""

        # Extract ContextCore config
        task_id = config.get("task_id")
        project_id = config.get("project_id", "default")
        parent_id = config.get("parent_id")
        local_storage = config.get("local_storage")
        emit_insights = config.get("emit_insights", True)

        # Initialize tracker (if task_id provided)
        tracker: Optional[ContextCoreTaskTracker] = None
        if task_id:
            tracker = ContextCoreTaskTracker(
                project_id=project_id,
                task_id=task_id,
                parent_id=parent_id,
                local_storage=local_storage,
            )

            # Start the task
            task_title = f"Primary Contractor: {config.get('task_description', 'Unknown')[:50]}"
            tracker.start_task(task_title, task_type="task")
            tracker.update_status("in_progress")

        # Wrap progress callback to add task events
        original_on_progress = on_progress

        def tracking_progress(current: int, total: int, message: str):
            # Call original callback
            if original_on_progress:
                original_on_progress(current, total, message)

            # Add task event
            if tracker:
                tracker.add_event(
                    f"progress_{current}",
                    {"current": current, "total": total, "message": message}
                )

        try:
            # Execute the base workflow
            result = super()._execute(config, agents, tracking_progress)

            # Post-execution tracking
            if tracker:
                if result.success:
                    # Emit insights for successful workflow
                    if emit_insights and result.steps:
                        # Extract key decisions from steps
                        spec_step = next(
                            (s for s in result.steps if s.step_name == "spec_creation"),
                            None
                        )
                        if spec_step:
                            tracker.emit_decision(
                                summary=f"Created implementation spec for: {config.get('task_description', 'task')[:100]}",
                                confidence=0.9,
                                context={
                                    "agent": spec_step.agent_name,
                                    "tokens": spec_step.output_tokens,
                                }
                            )

                        # Find final review
                        review_steps = [s for s in result.steps if "review" in s.step_name]
                        if review_steps:
                            final_review = review_steps[-1]
                            # Extract score from metadata if available
                            score = final_review.metadata.get("score", "unknown")
                            tracker.emit_decision(
                                summary=f"Implementation passed review with score: {score}",
                                confidence=0.85,
                                context={
                                    "iterations": len(review_steps),
                                    "final_score": score,
                                }
                            )

                    tracker.complete_task()
                else:
                    tracker.fail_task(result.error or "Workflow failed")

            # Add ContextCore context to result
            result.project_context = ProjectContext(
                project_id=project_id,
                task_id=task_id,
            )

            return result

        except Exception as e:
            # Track failure
            if tracker:
                tracker.fail_task(str(e))
            raise

    async def _aexecute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute with ContextCore task tracking (async, FR-150)."""

        task_id = config.get("task_id")
        project_id = config.get("project_id", "default")
        parent_id = config.get("parent_id")
        local_storage = config.get("local_storage")
        emit_insights = config.get("emit_insights", True)

        tracker: Optional[ContextCoreTaskTracker] = None
        if task_id:
            tracker = ContextCoreTaskTracker(
                project_id=project_id,
                task_id=task_id,
                parent_id=parent_id,
                local_storage=local_storage,
            )

            task_title = f"Primary Contractor: {config.get('task_description', 'Unknown')[:50]}"
            tracker.start_task(task_title, task_type="task")
            tracker.update_status("in_progress")

        original_on_progress = on_progress

        def tracking_progress(current: int, total: int, message: str):
            if original_on_progress:
                original_on_progress(current, total, message)
            if tracker:
                tracker.add_event(
                    f"progress_{current}",
                    {"current": current, "total": total, "message": message}
                )

        try:
            result = await super()._aexecute(config, agents, tracking_progress)

            if tracker:
                if result.success:
                    if emit_insights and result.steps:
                        spec_step = next(
                            (s for s in result.steps if s.step_name == "spec_creation"),
                            None
                        )
                        if spec_step:
                            tracker.emit_decision(
                                summary=f"Created implementation spec for: {config.get('task_description', 'task')[:100]}",
                                confidence=0.9,
                                context={
                                    "agent": spec_step.agent_name,
                                    "tokens": spec_step.output_tokens,
                                }
                            )

                        review_steps = [s for s in result.steps if "review" in s.step_name]
                        if review_steps:
                            final_review = review_steps[-1]
                            score = final_review.metadata.get("score", "unknown")
                            tracker.emit_decision(
                                summary=f"Implementation passed review with score: {score}",
                                confidence=0.85,
                                context={
                                    "iterations": len(review_steps),
                                    "final_score": score,
                                }
                            )

                    tracker.complete_task()
                else:
                    tracker.fail_task(result.error or "Workflow failed")

            result.project_context = ProjectContext(
                project_id=project_id,
                task_id=task_id,
            )

            return result

        except Exception as e:
            if tracker:
                tracker.fail_task(str(e))
            raise

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate config including ContextCore fields."""
        # First validate base config
        base_result = super().validate_config(config)
        if not base_result.valid:
            return base_result

        errors = []

        # Validate ContextCore-specific fields
        task_id = config.get("task_id")
        project_id = config.get("project_id")

        # If task_id is provided, it should be a non-empty string
        if task_id is not None and (not isinstance(task_id, str) or not task_id.strip()):
            errors.append("task_id must be a non-empty string if provided")

        # project_id should be a non-empty string if provided
        if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
            errors.append("project_id must be a non-empty string if provided")

        # Warn if task_id not provided (tracking disabled)
        if not task_id:
            logger.info("task_id not provided - ContextCore tracking will be disabled")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()


# Backward-compat alias (Phase 4 rename: Lead → Primary)
LeadContractorContextCoreWorkflow = PrimaryContractorContextCoreWorkflow
