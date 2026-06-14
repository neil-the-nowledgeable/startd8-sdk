"""
ContextCore Integration for StartD8 SDK.

Provides adapters and utilities for tracking StartD8 workflows as ContextCore tasks,
enabling unified project observability through OpenTelemetry spans.

Core Concept:
    Tasks ARE Spans - Each workflow execution becomes a ContextCore task span,
    with phases, reviews, and costs tracked as span events and attributes.

Ownership boundary (REQ-PRO-001, Project Observability):
    This adapter is an OPTIONAL import with graceful degradation — startd8 writes
    state files and emits spans; ContextCore reads them and OWNS the metric-ified
    gauges, live progress, and burndown dashboards. The seam is one-directional:
    startd8 does not reach into ContextCore beyond this wrapper, and the
    observability generator surfaces the ``contextcore_*`` gauges as
    ContextCore-owned (``route_state=contextcore_owned``), excluded from startd8's
    artifact-coverage denominator (REQ-OAT-052), not as a startd8 emission.

Components:
    - ContextCoreConfig: Configuration for ContextCore integration
    - WorkflowTaskSpec: Specification for a single workflow task
    - ContextCoreWorkflowAdapter: Wraps any workflow for task tracking
    - ContextCoreTaskRunner: Runs multiple tasks with dependency resolution

Example (Single Task):
    from startd8.integrations.contextcore import ContextCoreWorkflowAdapter, ContextCoreConfig
    from startd8.workflows.builtin import PrimaryContractorWorkflow

    config = ContextCoreConfig(
        project_id="my-project",
        sprint_id="sprint-3",
    )
    adapter = ContextCoreWorkflowAdapter(PrimaryContractorWorkflow(), config)

    result = adapter.run_as_task(
        task_id="SDK-102",
        task_title="Implement rate limiter",
        workflow_config={"task_description": "Implement rate limiter using token bucket"},
    )

Example (Task List):
    from startd8.integrations.contextcore import ContextCoreTaskRunner, WorkflowTaskSpec

    runner = ContextCoreTaskRunner(
        project_id="my-project",
        sprint_id="sprint-3",
    )

    tasks = [
        WorkflowTaskSpec(
            task_id="SDK-101",
            title="Add session tracking",
            config={"task_description": "Add project context to SessionTracker"},
            story_points=2,
        ),
        WorkflowTaskSpec(
            task_id="SDK-102",
            title="Update MetricsHandler",
            config={"task_description": "Add per-project metrics"},
            depends_on=["SDK-101"],
            story_points=3,
        ),
    ]

    results = runner.run_all(tasks)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union
import os
import logging

from ..workflows.base import WorkflowBase, ProgressCallback
from ..workflows.models import WorkflowResult, ProjectContext
from ..logging_config import get_logger
from .tracking_redaction import redact_text, redact_evidence

logger = get_logger(__name__)

# Evidence dataclass fields ContextCore accepts; filter caller dicts to these (T0.3).
_EVIDENCE_FIELDS = {"type", "ref", "description", "query", "timestamp"}


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class ContextCoreConfig:
    """
    Configuration for ContextCore integration.

    Attributes:
        project_id: ContextCore project identifier (required)
        project_name: Human-readable project name
        sprint_id: Current sprint ID for task organization
        otlp_endpoint: OpenTelemetry endpoint for trace export
        local_storage: Path for local task state (if OTLP unavailable)
        auto_create_task: Create task span automatically on workflow start
        auto_complete_task: Complete task span automatically on success
        emit_insights: Emit decision/lesson insights to ContextCore
        default_task_type: Default task type for workflows
    """
    project_id: str
    project_name: Optional[str] = None
    sprint_id: Optional[str] = None
    otlp_endpoint: str = "localhost:4317"
    local_storage: Optional[str] = None
    auto_create_task: bool = True
    auto_complete_task: bool = True
    emit_insights: bool = True
    default_task_type: str = "task"

    def __post_init__(self):
        """Set defaults from environment if not provided."""
        if not self.local_storage:
            self.local_storage = os.environ.get("CONTEXTCORE_LOCAL_STORAGE")
        if not self.project_name:
            self.project_name = self.project_id


@dataclass
class WorkflowTaskSpec:
    """
    Specification for a single workflow task.

    Used by ContextCoreTaskRunner to define task batches.

    Attributes:
        task_id: Unique task identifier (e.g., "SDK-102")
        title: Human-readable task title
        config: Workflow configuration (task_description, context, etc.)
        task_type: Task type (epic, story, task, subtask, bug, spike)
        parent_id: Parent task/story ID for hierarchy
        depends_on: List of task IDs this task depends on
        story_points: Estimated effort
        priority: Task priority (critical, high, medium, low)
        assignee: Person assigned to the task
        labels: Tags for categorization
        url: Link to external issue tracker
    """
    task_id: str
    title: str
    config: Dict[str, Any]
    task_type: str = "task"
    parent_id: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    story_points: Optional[int] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    url: Optional[str] = None

    def to_workflow_config(self) -> Dict[str, Any]:
        """Convert to workflow config dictionary."""
        # Start with the user-provided config
        workflow_config = dict(self.config)

        # Ensure task_description is set
        if "task_description" not in workflow_config:
            workflow_config["task_description"] = self.title

        return workflow_config


# ============================================================================
# Task Tracker Wrapper
# ============================================================================

class TaskTrackerWrapper:
    """
    Wrapper for ContextCore TaskTracker.

    Handles graceful degradation when ContextCore is not installed.
    """

    def __init__(
        self,
        project_id: str,
        local_storage: Optional[str] = None,
    ):
        self.project_id = project_id
        self.local_storage = local_storage
        self._tracker = None
        self._emitter = None
        self._enabled = False

        self._initialize()

    def _initialize(self):
        """Try to initialize ContextCore components."""
        try:
            from contextcore import TaskTracker

            # Set local storage env if provided
            if self.local_storage:
                os.environ["CONTEXTCORE_LOCAL_STORAGE"] = self.local_storage

            self._tracker = TaskTracker(project=self.project_id)
            self._enabled = True
            logger.info(f"ContextCore TaskTracker initialized for project: {self.project_id}")

            # Try to initialize insight emitter
            try:
                from contextcore.agent import InsightEmitter
                self._emitter = InsightEmitter(
                    project_id=self.project_id,
                    agent_id="startd8-workflow"
                )
            except ImportError:
                logger.debug("InsightEmitter not available")

        except ImportError:
            logger.warning("ContextCore not installed - task tracking disabled")
            logger.info("Install with: pip install contextcore")
            self._enabled = False
        except Exception as e:
            logger.warning(f"Failed to initialize ContextCore: {e}")
            self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if ContextCore tracking is enabled."""
        return self._enabled

    def start_task(
        self,
        task_id: str,
        title: str,
        task_type: str = "task",
        parent_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        story_points: Optional[int] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        url: Optional[str] = None,
    ) -> bool:
        """Start a task span."""
        if not self._enabled:
            logger.info(f"[mock] Start task: {task_id} - {title}")
            return False

        try:
            self._tracker.start_task(
                task_id=task_id,
                title=title,
                task_type=task_type,
                parent_id=parent_id,
                sprint_id=sprint_id,
                depends_on=depends_on,
                story_points=story_points,
                priority=priority,
                assignee=assignee,
                labels=labels,
                url=url,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start task: {e}")
            return False

    def update_status(self, task_id: str, status: str) -> bool:
        """Update task status."""
        if not self._enabled:
            logger.info(f"[mock] Update status: {task_id} -> {status}")
            return False

        try:
            self._tracker.update_status(task_id, status)
            return True
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            return False

    def add_event(
        self,
        task_id: str,
        event_name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add an event to the task span."""
        if not self._enabled:
            logger.info(f"[mock] Add event: {task_id} - {event_name}")
            return False

        try:
            span = self._tracker._get_span(task_id)
            if span:
                span.add_event(event_name, attributes=attributes or {})
            return True
        except Exception as e:
            logger.error(f"Failed to add event: {e}")
            return False

    def complete_task(self, task_id: str) -> bool:
        """Complete a task."""
        if not self._enabled:
            logger.info(f"[mock] Complete task: {task_id}")
            return False

        try:
            self._tracker.complete_task(task_id)
            return True
        except Exception as e:
            logger.error(f"Failed to complete task: {e}")
            return False

    def fail_task(self, task_id: str, reason: str) -> bool:
        """Mark task as failed/cancelled."""
        if not self._enabled:
            logger.info(f"[mock] Fail task: {task_id} - {reason}")
            return False

        try:
            self._tracker.cancel_task(task_id, reason=reason)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel task: {e}")
            return False

    def emit_decision(
        self,
        summary: str,
        confidence: float = 0.9,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Emit a decision insight.

        Args:
            summary: Brief description of the decision
            confidence: Confidence score (0.0-1.0)
            context: Optional context dict. Keys like 'task_id', 'cost', 'time_ms'
                    are converted to rationale string for InsightEmitter.
        """
        if not self._enabled or not self._emitter:
            logger.info(f"[mock] Emit decision: {summary}")
            return False

        try:
            # Convert context dict to rationale string (InsightEmitter doesn't have 'context' param)
            rationale = None
            if context:
                rationale = ", ".join(f"{k}={v}" for k, v in context.items())

            self._emitter.emit_decision(
                summary=summary,
                confidence=confidence,
                rationale=rationale,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to emit decision: {e}")
            return False

    def shutdown(self):
        """Shutdown the tracker."""
        if self._enabled and self._tracker:
            try:
                self._tracker.shutdown()
            except Exception:
                pass


# ============================================================================
# Workflow Adapter
# ============================================================================

class ContextCoreWorkflowAdapter:
    """
    Wraps any StartD8 workflow to track execution as a ContextCore task.

    This adapter:
    1. Creates a task span when workflow starts
    2. Updates task status through workflow phases
    3. Emits events for significant workflow steps
    4. Completes/fails the task based on workflow result

    Example:
        adapter = ContextCoreWorkflowAdapter(
            workflow=PrimaryContractorWorkflow(),
            config=ContextCoreConfig(project_id="my-project"),
        )

        result = adapter.run_as_task(
            task_id="SDK-102",
            task_title="Implement rate limiter",
            workflow_config={
                "task_description": "Implement rate limiter using token bucket",
                # Optional — omit to use Models.PRIMARY_CONTRACTOR_DRAFTER (catalog default).
                "drafter_agent": "gemini:gemini-2.5-flash-lite",
            },
        )
    """

    def __init__(
        self,
        workflow: WorkflowBase,
        config: ContextCoreConfig,
    ):
        """
        Initialize the adapter.

        Args:
            workflow: The workflow to wrap
            config: ContextCore configuration
        """
        self.workflow = workflow
        self.config = config
        self._tracker: Optional[TaskTrackerWrapper] = None

    def _get_tracker(self) -> TaskTrackerWrapper:
        """Get or create the task tracker."""
        if self._tracker is None:
            self._tracker = TaskTrackerWrapper(
                project_id=self.config.project_id,
                local_storage=self.config.local_storage,
            )
        return self._tracker

    def run_as_task(
        self,
        task_id: str,
        task_title: Optional[str] = None,
        workflow_config: Optional[Dict[str, Any]] = None,
        task_type: str = "task",
        parent_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        story_points: Optional[int] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        url: Optional[str] = None,
        agents: Optional[List] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """
        Execute the workflow as a ContextCore task.

        Args:
            task_id: Unique task identifier
            task_title: Task title (defaults to task_description from config)
            workflow_config: Workflow configuration dictionary
            task_type: Type of task (epic, story, task, etc.)
            parent_id: Parent task ID
            depends_on: Tasks this depends on
            story_points: Estimated effort
            priority: Task priority
            assignee: Assigned person
            labels: Task labels
            url: External URL
            agents: Pre-resolved agents (passed to workflow)
            on_progress: Progress callback

        Returns:
            WorkflowResult with project_context populated
        """
        workflow_config = workflow_config or {}
        tracker = self._get_tracker()

        # Determine task title
        title = task_title or workflow_config.get("task_description", task_id)

        # Start the task span
        if self.config.auto_create_task:
            tracker.start_task(
                task_id=task_id,
                title=title,
                task_type=task_type or self.config.default_task_type,
                parent_id=parent_id,
                sprint_id=self.config.sprint_id,
                depends_on=depends_on,
                story_points=story_points,
                priority=priority,
                assignee=assignee,
                labels=labels,
                url=url,
            )
            tracker.update_status(task_id, "in_progress")

        # Wrap progress callback to add task events
        def tracking_progress(current: int, total: int, message: str):
            # Call original callback
            if on_progress:
                on_progress(current, total, message)

            # Add task event
            tracker.add_event(
                task_id,
                f"workflow.progress",
                {"step": current, "total": total, "message": message}
            )

        try:
            # Execute the workflow
            result = self.workflow.run(
                config=workflow_config,
                agents=agents,
                on_progress=tracking_progress,
            )

            # Post-execution tracking
            if self.config.auto_complete_task:
                if result.success:
                    # Add completion event with metrics
                    tracker.add_event(
                        task_id,
                        "workflow.completed",
                        {
                            "workflow_id": result.workflow_id,
                            "total_cost": result.metrics.total_cost,
                            "total_time_ms": result.metrics.total_time_ms,
                            "step_count": result.metrics.step_count,
                            "input_tokens": result.metrics.input_tokens,
                            "output_tokens": result.metrics.output_tokens,
                        }
                    )

                    # Emit decision insight
                    if self.config.emit_insights:
                        tracker.emit_decision(
                            summary=f"Completed workflow for: {title[:100]}",
                            confidence=0.9,
                            context={
                                "task_id": task_id,
                                "cost": result.metrics.total_cost,
                                "time_ms": result.metrics.total_time_ms,
                            }
                        )

                    tracker.complete_task(task_id)
                else:
                    tracker.fail_task(task_id, result.error or "Workflow failed")

            # Set project context on result
            result.project_context = ProjectContext(
                project_id=self.config.project_id,
                project_name=self.config.project_name,
                task_id=task_id,
                sprint_id=self.config.sprint_id,
            )

            return result

        except Exception as e:
            # Track failure
            if self.config.auto_complete_task:
                tracker.fail_task(task_id, str(e))
            raise

    def shutdown(self):
        """Shutdown the tracker."""
        if self._tracker:
            self._tracker.shutdown()


# ============================================================================
# Task Runner
# ============================================================================

@dataclass
class TaskExecutionResult:
    """Result of executing a single task in a batch."""
    task_id: str
    success: bool
    result: Optional[WorkflowResult] = None
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


class ContextCoreTaskRunner:
    """
    Run multiple workflow tasks with dependency resolution.

    Tasks are executed in order, respecting dependencies. If a task fails,
    dependent tasks are skipped.

    Example:
        runner = ContextCoreTaskRunner(
            project_id="my-project",
            sprint_id="sprint-3",
        )

        tasks = [
            WorkflowTaskSpec(
                task_id="SDK-101",
                title="Add session tracking",
                config={"task_description": "Add project context to SessionTracker"},
            ),
            WorkflowTaskSpec(
                task_id="SDK-102",
                title="Update MetricsHandler",
                config={"task_description": "Add per-project metrics"},
                depends_on=["SDK-101"],
            ),
        ]

        results = runner.run_all(tasks, workflow=PrimaryContractorWorkflow())
    """

    def __init__(
        self,
        project_id: str,
        project_name: Optional[str] = None,
        sprint_id: Optional[str] = None,
        local_storage: Optional[str] = None,
        emit_insights: bool = True,
    ):
        """
        Initialize the task runner.

        Args:
            project_id: ContextCore project ID
            project_name: Human-readable project name
            sprint_id: Sprint ID for task organization
            local_storage: Path for local task storage
            emit_insights: Whether to emit decision insights
        """
        self.config = ContextCoreConfig(
            project_id=project_id,
            project_name=project_name,
            sprint_id=sprint_id,
            local_storage=local_storage,
            emit_insights=emit_insights,
        )
        self._completed_tasks: Dict[str, TaskExecutionResult] = {}
        self._failed_tasks: set = set()

    def run_all(
        self,
        tasks: List[WorkflowTaskSpec],
        workflow: Optional[WorkflowBase] = None,
        workflow_class: Optional[Type[WorkflowBase]] = None,
        on_task_complete: Optional[Callable[[str, TaskExecutionResult], None]] = None,
        on_progress: Optional[ProgressCallback] = None,
        stop_on_failure: bool = False,
    ) -> Dict[str, TaskExecutionResult]:
        """
        Execute all tasks in dependency order.

        Args:
            tasks: List of task specifications
            workflow: Workflow instance to use (shared across tasks)
            workflow_class: Workflow class to instantiate per task
            on_task_complete: Callback called after each task
            on_progress: Progress callback for individual workflows
            stop_on_failure: Stop execution if any task fails

        Returns:
            Dictionary mapping task_id to TaskExecutionResult
        """
        if not workflow and not workflow_class:
            # Default to PrimaryContractorWorkflow
            from ..workflows.builtin import PrimaryContractorWorkflow
            workflow = PrimaryContractorWorkflow()

        # Build task map for dependency resolution
        task_map = {t.task_id: t for t in tasks}

        # Topological sort for dependency order
        ordered_tasks = self._topological_sort(tasks)

        logger.info(f"Running {len(tasks)} tasks for project {self.config.project_id}")

        results: Dict[str, TaskExecutionResult] = {}

        for i, task_spec in enumerate(ordered_tasks):
            task_id = task_spec.task_id

            # Check if dependencies are satisfied
            skip_reason = self._check_dependencies(task_spec)
            if skip_reason:
                result = TaskExecutionResult(
                    task_id=task_id,
                    success=False,
                    skipped=True,
                    skip_reason=skip_reason,
                )
                results[task_id] = result
                self._completed_tasks[task_id] = result

                if on_task_complete:
                    on_task_complete(task_id, result)

                logger.warning(f"Skipping task {task_id}: {skip_reason}")
                continue

            # Create workflow instance if using class
            wf = workflow if workflow else workflow_class()

            # Create adapter
            adapter = ContextCoreWorkflowAdapter(wf, self.config)

            logger.info(f"[{i+1}/{len(tasks)}] Starting task: {task_id} - {task_spec.title}")

            try:
                workflow_result = adapter.run_as_task(
                    task_id=task_id,
                    task_title=task_spec.title,
                    workflow_config=task_spec.to_workflow_config(),
                    task_type=task_spec.task_type,
                    parent_id=task_spec.parent_id,
                    depends_on=task_spec.depends_on,
                    story_points=task_spec.story_points,
                    priority=task_spec.priority,
                    assignee=task_spec.assignee,
                    labels=task_spec.labels,
                    url=task_spec.url,
                    on_progress=on_progress,
                )

                result = TaskExecutionResult(
                    task_id=task_id,
                    success=workflow_result.success,
                    result=workflow_result,
                    error=workflow_result.error,
                )

                if not workflow_result.success:
                    self._failed_tasks.add(task_id)

            except Exception as e:
                logger.error(f"Task {task_id} failed with exception: {e}")
                result = TaskExecutionResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                )
                self._failed_tasks.add(task_id)

            results[task_id] = result
            self._completed_tasks[task_id] = result

            if on_task_complete:
                on_task_complete(task_id, result)

            # Log result
            status = "✅" if result.success else "❌"
            cost = result.result.metrics.total_cost if result.result else 0
            time_ms = result.result.metrics.total_time_ms if result.result else 0
            logger.info(f"{status} {task_id}: {time_ms}ms, ${cost:.4f}")

            # Stop on failure if requested
            if stop_on_failure and not result.success:
                logger.warning(f"Stopping execution due to task failure: {task_id}")
                break

            # Shutdown adapter
            adapter.shutdown()

        return results

    def _check_dependencies(self, task: WorkflowTaskSpec) -> Optional[str]:
        """Check if task dependencies are satisfied."""
        for dep_id in task.depends_on:
            if dep_id in self._failed_tasks:
                return f"Dependency {dep_id} failed"
            if dep_id not in self._completed_tasks:
                return f"Dependency {dep_id} not found"
            if self._completed_tasks[dep_id].skipped:
                return f"Dependency {dep_id} was skipped"
            if not self._completed_tasks[dep_id].success:
                return f"Dependency {dep_id} did not succeed"
        return None

    def _topological_sort(self, tasks: List[WorkflowTaskSpec]) -> List[WorkflowTaskSpec]:
        """Sort tasks by dependencies (topological order)."""
        task_map = {t.task_id: t for t in tasks}
        visited = set()
        result = []

        def visit(task_id: str):
            if task_id in visited:
                return
            visited.add(task_id)

            task = task_map.get(task_id)
            if task:
                for dep_id in task.depends_on:
                    if dep_id in task_map:
                        visit(dep_id)
                result.append(task)

        for task in tasks:
            visit(task.task_id)

        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        total = len(self._completed_tasks)
        succeeded = sum(1 for r in self._completed_tasks.values() if r.success)
        failed = sum(1 for r in self._completed_tasks.values() if not r.success and not r.skipped)
        skipped = sum(1 for r in self._completed_tasks.values() if r.skipped)

        total_cost = sum(
            r.result.metrics.total_cost
            for r in self._completed_tasks.values()
            if r.result
        )
        total_time_ms = sum(
            r.result.metrics.total_time_ms
            for r in self._completed_tasks.values()
            if r.result
        )

        return {
            "project_id": self.config.project_id,
            "sprint_id": self.config.sprint_id,
            "total_tasks": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "total_cost": total_cost,
            "total_time_ms": total_time_ms,
            "success_rate": (succeeded / total * 100) if total > 0 else 0,
        }


# ============================================================================
# Utility Functions
# ============================================================================

def load_tasks_from_yaml(path: str) -> List[WorkflowTaskSpec]:
    """
    Load task specifications from a YAML file.

    Expected format:
        tasks:
          - task_id: SDK-101
            title: Add session tracking
            config:
              task_description: Add project context to SessionTracker
            story_points: 2
          - task_id: SDK-102
            title: Update MetricsHandler
            depends_on:
              - SDK-101

    Args:
        path: Path to YAML file

    Returns:
        List of WorkflowTaskSpec instances
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML required for YAML loading. Install with: pip install pyyaml")

    with open(path, 'r') as f:
        data = yaml.safe_load(f)

    tasks = []
    for task_data in data.get("tasks", []):
        tasks.append(WorkflowTaskSpec(
            task_id=task_data["task_id"],
            title=task_data["title"],
            config=task_data.get("config", {}),
            task_type=task_data.get("task_type", "task"),
            parent_id=task_data.get("parent_id"),
            depends_on=task_data.get("depends_on", []),
            story_points=task_data.get("story_points"),
            priority=task_data.get("priority"),
            assignee=task_data.get("assignee"),
            labels=task_data.get("labels", []),
            url=task_data.get("url"),
        ))

    return tasks


# ============================================================================
# ContextCore Task Source
# ============================================================================

@dataclass
class ContextCoreTaskSource:
    """
    Load tasks directly from a ContextCore project's state files.

    ContextCore stores active tasks as JSON files in ~/.contextcore/state/<project>/
    Each file contains task attributes that can be used to generate workflow configs.

    Example:
        source = ContextCoreTaskSource(project_id="my-project")
        tasks = source.get_pending_tasks()

        runner = ContextCoreTaskRunner(project_id="my-project")
        results = runner.run_all(tasks)

    Task Description Mapping:
        By default, uses task.title as task_description. For more control:
        - Set 'task.description' attribute on ContextCore tasks
        - Or provide a custom description_extractor function

    Workflow Prompt Generation:
        ContextCore tasks can include a 'task.prompt' attribute with detailed
        implementation instructions. If not present, the task title is used.
    """
    project_id: str
    state_dir: Optional[str] = None
    status_filter: List[str] = field(default_factory=lambda: ["todo", "backlog"])

    def __post_init__(self):
        """Initialize the state directory path."""
        if not self.state_dir:
            self.state_dir = os.path.expanduser("~/.contextcore/state")
        self._project_dir = Path(self.state_dir) / self.project_id

    def get_all_tasks(self) -> List[WorkflowTaskSpec]:
        """
        Get all active tasks from the ContextCore project.

        Returns:
            List of WorkflowTaskSpec instances
        """
        if not self._project_dir.exists():
            logger.warning(f"ContextCore project directory not found: {self._project_dir}")
            return []

        tasks = []
        for file_path in self._project_dir.glob("*.json"):
            task_spec = self._load_task_from_file(file_path)
            if task_spec:
                tasks.append(task_spec)

        logger.info(f"Loaded {len(tasks)} tasks from ContextCore project: {self.project_id}")
        return tasks

    def get_pending_tasks(self) -> List[WorkflowTaskSpec]:
        """
        Get tasks with status in status_filter (default: 'todo' or 'backlog').

        Returns:
            List of WorkflowTaskSpec for pending tasks
        """
        all_tasks = self.get_all_tasks()
        pending = [t for t in all_tasks if self._matches_status_filter(t)]
        logger.info(f"Found {len(pending)} pending tasks (status in {self.status_filter})")
        return pending

    def get_task_by_id(self, task_id: str) -> Optional[WorkflowTaskSpec]:
        """
        Get a specific task by ID.

        Args:
            task_id: Task identifier

        Returns:
            WorkflowTaskSpec or None if not found
        """
        file_path = self._project_dir / f"{task_id}.json"
        if file_path.exists():
            return self._load_task_from_file(file_path)
        return None

    def _load_task_from_file(self, file_path: Path) -> Optional[WorkflowTaskSpec]:
        """Load a task from a JSON state file."""
        try:
            import json
            with open(file_path) as f:
                data = json.load(f)

            attrs = data.get("attributes", {})
            task_id = attrs.get("task.id", file_path.stem)
            title = attrs.get("task.title", task_id)

            # Build workflow config
            # Priority: task.prompt > task.description > task.title
            task_description = (
                attrs.get("task.prompt") or
                attrs.get("task.description") or
                title
            )

            config = {
                "task_description": task_description,
            }

            # Add context from task attributes
            context = {}
            if attrs.get("task.context"):
                context = attrs.get("task.context")
            if attrs.get("task.language"):
                context["language"] = attrs.get("task.language")
            if attrs.get("task.framework"):
                context["framework"] = attrs.get("task.framework")
            if attrs.get("task.file"):
                context["file"] = attrs.get("task.file")

            if context:
                config["context"] = context

            # Pass through all original task attributes for consumer access
            for key, value in attrs.items():
                if key not in config:
                    config[key] = value

            # Parse depends_on from task attributes
            depends_on = []
            if "task.depends_on" in attrs:
                dep_value = attrs["task.depends_on"]
                if isinstance(dep_value, list):
                    depends_on = dep_value
                elif isinstance(dep_value, str):
                    depends_on = [d.strip() for d in dep_value.split(",")]

            # Parse labels
            labels = []
            if "task.labels" in attrs:
                label_value = attrs["task.labels"]
                if isinstance(label_value, list):
                    labels = label_value
                elif isinstance(label_value, str):
                    labels = [l.strip() for l in label_value.split(",")]

            return WorkflowTaskSpec(
                task_id=task_id,
                title=title,
                config=config,
                task_type=attrs.get("task.type", "task"),
                parent_id=attrs.get("task.parent_id"),
                depends_on=depends_on,
                story_points=attrs.get("task.story_points"),
                priority=attrs.get("task.priority"),
                assignee=attrs.get("task.assignee"),
                labels=labels,
                url=attrs.get("task.url"),
            )

        except Exception as e:
            logger.error(f"Failed to load task from {file_path}: {e}")
            return None

    def _matches_status_filter(self, task: WorkflowTaskSpec) -> bool:
        """Check if task matches the status filter."""
        # Re-read status from file since WorkflowTaskSpec doesn't store it
        file_path = self._project_dir / f"{task.task_id}.json"
        if not file_path.exists():
            return False

        try:
            import json
            with open(file_path) as f:
                data = json.load(f)
            status = data.get("attributes", {}).get("task.status", "unknown")
            return status in self.status_filter
        except Exception:
            return False


def run_contextcore_project(
    project_id: str,
    sprint_id: Optional[str] = None,
    workflow: Optional[WorkflowBase] = None,
    status_filter: Optional[List[str]] = None,
    stop_on_failure: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Run all pending tasks from a ContextCore project through the Primary Contractor workflow.

    This is a convenience function that:
    1. Loads pending tasks from ContextCore state files
    2. Sorts them by dependencies
    3. Executes each through the workflow
    4. Updates task status in ContextCore on completion

    Args:
        project_id: ContextCore project ID
        sprint_id: Optional sprint ID for filtering/organization
        workflow: Workflow to use (defaults to PrimaryContractorWorkflow)
        status_filter: Task statuses to include (default: ["todo", "backlog"])
        stop_on_failure: Stop if a task fails
        dry_run: If True, only list tasks without executing

    Returns:
        Dictionary with results and summary

    Example:
        # Run all pending tasks in a project
        results = run_contextcore_project("my-project", sprint_id="sprint-3")

        # Dry run to see what would be executed
        results = run_contextcore_project("my-project", dry_run=True)
    """
    # Load tasks from ContextCore
    source = ContextCoreTaskSource(
        project_id=project_id,
        status_filter=status_filter or ["todo", "backlog"],
    )

    tasks = source.get_pending_tasks()

    if not tasks:
        logger.info(f"No pending tasks found in project: {project_id}")
        return {
            "project_id": project_id,
            "sprint_id": sprint_id,
            "tasks_found": 0,
            "dry_run": dry_run,
            "results": {},
        }

    # Log task summary
    logger.info(f"Found {len(tasks)} pending tasks in project: {project_id}")
    for task in tasks:
        deps = f" (depends on: {', '.join(task.depends_on)})" if task.depends_on else ""
        logger.info(f"  - {task.task_id}: {task.title}{deps}")

    if dry_run:
        return {
            "project_id": project_id,
            "sprint_id": sprint_id,
            "tasks_found": len(tasks),
            "dry_run": True,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "task_type": t.task_type,
                    "depends_on": t.depends_on,
                    "story_points": t.story_points,
                    "priority": t.priority,
                }
                for t in tasks
            ],
            "results": {},
        }

    # Set up default workflow
    if workflow is None:
        from ..workflows.builtin import PrimaryContractorWorkflow
        workflow = PrimaryContractorWorkflow()

    # Create runner
    runner = ContextCoreTaskRunner(
        project_id=project_id,
        sprint_id=sprint_id,
    )

    # Execute tasks
    results = runner.run_all(
        tasks=tasks,
        workflow=workflow,
        stop_on_failure=stop_on_failure,
    )

    summary = runner.get_summary()

    return {
        "project_id": project_id,
        "sprint_id": sprint_id,
        "tasks_found": len(tasks),
        "dry_run": False,
        "summary": summary,
        "results": {
            task_id: {
                "success": r.success,
                "error": r.error,
                "skipped": r.skipped,
                "cost": r.result.metrics.total_cost if r.result else 0,
                "time_ms": r.result.metrics.total_time_ms if r.result else 0,
            }
            for task_id, r in results.items()
        },
    }


# ============================================================================
# Agent Insight Bridge
# ============================================================================

@dataclass
class InsightRecord:
    """Represents a retrieved insight from ContextCore."""
    insight_id: str
    insight_type: str  # "decision", "lesson", "question"
    summary: str
    timestamp: datetime
    confidence: Optional[float] = None
    category: Optional[str] = None
    applies_to: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    agent_id: Optional[str] = None


class AgentInsightBridge:
    """
    Bridge between StartD8 agent reasoning and ContextCore insights.

    Allows agent decisions, lessons, and questions to be:
    - Emitted as insights during workflow execution
    - Queried later via TraceQL for retrospective analysis

    Features:
    - emit_decision(): Record agent decisions with confidence scores
    - emit_lesson(): Record lessons learned during execution
    - emit_question(): Record blocking questions needing human input
    - query_decisions(): Retrieve past decisions by project/time/confidence
    - query_lessons(): Retrieve lessons by category or file applicability

    Example:
        bridge = AgentInsightBridge(project_id="my-project", agent_id="claude")

        # Emit during workflow
        bridge.emit_decision(
            summary="Selected Redis for caching based on latency requirements",
            confidence=0.9,
            alternatives_considered=["Memcached", "In-memory"],
        )

        # Query later
        decisions = bridge.query_decisions(time_range="7d", confidence_min=0.8)
        for d in decisions:
            print(f"{d.timestamp}: {d.summary} (confidence: {d.confidence})")
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the insight bridge.

        Args:
            project_id: Project identifier for scoping insights
            agent_id: Agent identifier (e.g., "claude", "gpt4", "my-agent")
            session_id: Optional session identifier for grouping related insights
        """
        self.project_id = project_id
        self.agent_id = agent_id
        self.session_id = session_id or f"session-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self._emitter = None
        self._querier = None
        self._enabled = False

        self._initialize()

    def _initialize(self):
        """Try to initialize ContextCore insight components."""
        try:
            from contextcore.agent import InsightEmitter, InsightQuerier

            self._emitter = InsightEmitter(
                project_id=self.project_id,
                agent_id=self.agent_id,
            )
            self._querier = InsightQuerier()
            self._enabled = True
            logger.info(f"AgentInsightBridge initialized for project: {self.project_id}")

        except ImportError:
            logger.warning("ContextCore agent module not available - insights disabled")
            logger.info("Install with: pip install contextcore")
            self._enabled = False
        except Exception as e:
            logger.warning(f"Failed to initialize insight bridge: {e}")
            self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if insight bridge is enabled."""
        return self._enabled

    def _emit(
        self,
        insight_type: str,
        summary: str,
        confidence: float,
        *,
        audience: Optional[str] = None,
        rationale: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        supersedes: Optional[str] = None,
        applies_to: Optional[List[str]] = None,
        category: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> bool:
        """Single emission chokepoint → ``InsightEmitter.emit()`` (FR-27, CRP R1-F6/F9).

        Every public ``emit_*`` method routes through here, so there is exactly one code path to
        ContextCore. That is what makes the legacy ``emit_question`` bug (it called a non-existent
        ``InsightEmitter.emit_question``) evaporate. All free text, rationale, and evidence refs are
        redacted (FR-19) before they leave the process.
        """
        if not self._enabled or not self._emitter:
            logger.info(f"[mock] Emit {insight_type}: {summary} (confidence: {confidence})")
            return False

        try:
            try:
                from contextcore.agent import InsightType, InsightAudience, Evidence
            except ImportError:  # pragma: no cover - exercised only without contextcore.agent re-exports
                from contextcore.agent.insights import InsightType, InsightAudience, Evidence

            itype = InsightType(insight_type)
            aud = InsightAudience(audience) if audience else InsightAudience.BOTH

            kwargs: Dict[str, Any] = {"audience": aud}
            red_rationale = redact_text(rationale)
            if red_rationale:
                kwargs["rationale"] = red_rationale
            ev = redact_evidence(evidence)
            if ev:
                kwargs["evidence"] = [
                    Evidence(**{k: v for k, v in e.items() if k in _EVIDENCE_FIELDS}) for e in ev
                ]
            if supersedes:
                kwargs["supersedes"] = supersedes
            if applies_to:
                kwargs["applies_to"] = applies_to
            if category:
                kwargs["category"] = category
            if input_tokens is not None:
                kwargs["input_tokens"] = input_tokens
            if output_tokens is not None:
                kwargs["output_tokens"] = output_tokens
            if model:
                kwargs["model"] = model
            if provider:
                kwargs["provider"] = provider

            self._emitter.emit(itype, redact_text(summary), confidence, **kwargs)
            return True

        except Exception as e:
            logger.error(f"Failed to emit {insight_type} insight: {e}")
            return False

    def emit_decision(
        self,
        summary: str,
        confidence: float = 0.8,
        context: Optional[Dict[str, Any]] = None,
        alternatives_considered: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        rationale: Optional[str] = None,
        *,
        evidence: Optional[List[Dict[str, Any]]] = None,
        audience: Optional[str] = None,
        supersedes: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> bool:
        """Emit an agent decision as an insight (``insight.type=decision``).

        Args (legacy signature preserved; ``evidence``/``audience``/``supersedes`` added per
        FR-27b/FR-15/FR-16; ``input_tokens``/``output_tokens``/``model``/``provider`` added per
        FR-18/R2-F4 — REQUIRED on the decision path feeding the FR-22 cost-per-decision panel,
        mapped by ContextCore to ``gen_ai.usage.*``):
            summary: Brief description of the decision made
            confidence: Confidence score (0.0-1.0)
            context: Additional context dictionary (folded into rationale)
            alternatives_considered: Alternatives that were evaluated
            task_id: Optional task ID to link this decision to
            rationale: Explanation of why this decision was made
            evidence: List of ``{type, ref, description?}`` supporting refs
            audience: ``"agent"`` | ``"human"`` | ``"both"``
            supersedes: ID of an insight this decision overrides
            input_tokens/output_tokens/model/provider: token/cost attribution for the agent view
        """
        full_context = dict(context or {})
        if alternatives_considered:
            full_context["alternatives_considered"] = alternatives_considered
        if task_id:
            full_context["task_id"] = task_id
        if not rationale and full_context:
            rationale = ", ".join(f"{k}={v}" for k, v in full_context.items())
        return self._emit(
            "decision", summary, confidence,
            rationale=rationale, evidence=evidence, audience=audience, supersedes=supersedes,
            input_tokens=input_tokens, output_tokens=output_tokens, model=model, provider=provider,
        )

    def emit_lesson(
        self,
        summary: str,
        category: str = "general",
        applies_to: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        *,
        evidence: Optional[List[Dict[str, Any]]] = None,
        audience: Optional[str] = None,
        supersedes: Optional[str] = None,
    ) -> bool:
        """Emit a lesson learned (``insight.type=lesson``)."""
        rationale = f"task_id={task_id}" if task_id else None
        return self._emit(
            "lesson", summary, 0.9,
            category=category, applies_to=applies_to, rationale=rationale,
            evidence=evidence, audience=audience, supersedes=supersedes,
        )

    def emit_question(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
        blocking: bool = False,
        task_id: Optional[str] = None,
        options: Optional[List[str]] = None,
        *,
        evidence: Optional[List[Dict[str, Any]]] = None,
        supersedes: Optional[str] = None,
    ) -> bool:
        """Emit a question needing human input (``insight.type=question``).

        Fixed (FR-28): previously called a non-existent ``InsightEmitter.emit_question``; now routes
        through the generic ``_emit`` chokepoint. Questions target the human audience.
        """
        parts: List[str] = []
        if blocking:
            parts.append("blocking=True")
        if task_id:
            parts.append(f"task_id={task_id}")
        if options:
            parts.append(f"options={options}")
        if context:
            parts.append(", ".join(f"{k}={v}" for k, v in context.items()))
        rationale = "; ".join(parts) or None
        return self._emit(
            "question", question, 1.0,
            audience="human", rationale=rationale, evidence=evidence, supersedes=supersedes,
        )

    def emit_risk(
        self,
        summary: str,
        confidence: float = 0.8,
        task_id: Optional[str] = None,
        *,
        rationale: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        audience: Optional[str] = None,
        supersedes: Optional[str] = None,
    ) -> bool:
        """Emit a risk (``insight.type=risk``) — e.g. the FR-44/45 CRITICAL items."""
        if task_id and not rationale:
            rationale = f"task_id={task_id}"
        return self._emit(
            "risk", summary, confidence,
            rationale=rationale, evidence=evidence, audience=audience, supersedes=supersedes,
        )

    def emit_blocker(
        self,
        summary: str,
        confidence: float = 1.0,
        task_id: Optional[str] = None,
        *,
        rationale: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        audience: Optional[str] = None,
        supersedes: Optional[str] = None,
    ) -> bool:
        """Emit a blocker (``insight.type=blocker``) — e.g. a per-cell terminal failure."""
        if task_id and not rationale:
            rationale = f"task_id={task_id}"
        return self._emit(
            "blocker", summary, confidence,
            rationale=rationale, evidence=evidence, audience=audience, supersedes=supersedes,
        )

    def emit_progress(
        self,
        summary: str,
        confidence: float = 1.0,
        task_id: Optional[str] = None,
        *,
        rationale: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        audience: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> bool:
        """Emit a progress insight (``insight.type=progress``); carries token/cost for FR-18."""
        if task_id and not rationale:
            rationale = f"task_id={task_id}"
        return self._emit(
            "progress", summary, confidence,
            rationale=rationale, evidence=evidence, audience=audience,
            input_tokens=input_tokens, output_tokens=output_tokens, model=model, provider=provider,
        )

    def emit_discovery(
        self,
        summary: str,
        confidence: float = 0.8,
        task_id: Optional[str] = None,
        *,
        rationale: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        audience: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> bool:
        """Emit a discovery insight (``insight.type=discovery``); carries token/cost for FR-18."""
        if task_id and not rationale:
            rationale = f"task_id={task_id}"
        return self._emit(
            "discovery", summary, confidence,
            rationale=rationale, evidence=evidence, audience=audience,
            input_tokens=input_tokens, output_tokens=output_tokens, model=model, provider=provider,
        )

    def query_decisions(
        self,
        time_range: str = "7d",
        confidence_min: Optional[float] = None,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[InsightRecord]:
        """
        Query past decisions for this project.

        Args:
            time_range: Time range to query (e.g., "1h", "7d", "30d")
            confidence_min: Minimum confidence threshold (0.0-1.0)
            task_id: Optional filter by task ID
            limit: Maximum number of results

        Returns:
            List of InsightRecord objects for matching decisions
        """
        if not self._enabled or not self._querier:
            logger.info(f"[mock] Query decisions: time_range={time_range}")
            return []

        try:
            raw_results = self._querier.query(
                project_id=self.project_id,
                insight_type="decision",
                time_range=time_range,
            )

            # Convert to InsightRecord and apply filters
            decisions = []
            for raw in raw_results[:limit]:
                record = self._convert_to_record(raw, "decision")

                # Apply confidence filter
                if confidence_min is not None and record.confidence is not None:
                    if record.confidence < confidence_min:
                        continue

                # Apply task_id filter
                if task_id and record.task_id != task_id:
                    continue

                decisions.append(record)

            return decisions

        except Exception as e:
            logger.error(f"Failed to query decisions: {e}")
            return []

    def query_lessons(
        self,
        category: Optional[str] = None,
        applies_to: Optional[str] = None,
        time_range: str = "30d",
        limit: int = 100,
    ) -> List[InsightRecord]:
        """
        Query past lessons for this project.

        Args:
            category: Filter by category (e.g., "testing", "architecture")
            applies_to: Filter by file or component path
            time_range: Time range to query (e.g., "7d", "30d")
            limit: Maximum number of results

        Returns:
            List of InsightRecord objects for matching lessons
        """
        if not self._enabled or not self._querier:
            logger.info(f"[mock] Query lessons: category={category}, time_range={time_range}")
            return []

        try:
            raw_results = self._querier.query(
                project_id=self.project_id,
                insight_type="lesson",
                time_range=time_range,
                applies_to=applies_to,
            )

            # Convert to InsightRecord and apply filters
            lessons = []
            for raw in raw_results[:limit]:
                record = self._convert_to_record(raw, "lesson")

                # Apply category filter
                if category and record.category != category:
                    continue

                lessons.append(record)

            return lessons

        except Exception as e:
            logger.error(f"Failed to query lessons: {e}")
            return []

    def query_questions(
        self,
        blocking_only: bool = False,
        answered: Optional[bool] = None,
        time_range: str = "7d",
        limit: int = 100,
    ) -> List[InsightRecord]:
        """
        Query past questions for this project.

        Args:
            blocking_only: Only return blocking questions
            answered: Filter by answered status (None = all)
            time_range: Time range to query
            limit: Maximum number of results

        Returns:
            List of InsightRecord objects for matching questions
        """
        if not self._enabled or not self._querier:
            logger.info(f"[mock] Query questions: blocking_only={blocking_only}")
            return []

        try:
            raw_results = self._querier.query(
                project_id=self.project_id,
                insight_type="question",
                time_range=time_range,
            )

            # Convert to InsightRecord and apply filters
            questions = []
            for raw in raw_results[:limit]:
                record = self._convert_to_record(raw, "question")

                # Apply blocking filter
                if blocking_only:
                    if not record.context.get("blocking", False):
                        continue

                questions.append(record)

            return questions

        except Exception as e:
            logger.error(f"Failed to query questions: {e}")
            return []

    def _convert_to_record(self, raw: Any, insight_type: str) -> InsightRecord:
        """Convert raw query result to InsightRecord."""
        # Handle different possible formats from ContextCore
        if hasattr(raw, 'to_dict'):
            data = raw.to_dict()
        elif isinstance(raw, dict):
            data = raw
        else:
            data = {"summary": str(raw)}

        return InsightRecord(
            insight_id=data.get("id", data.get("insight_id", "")),
            insight_type=insight_type,
            summary=data.get("summary", ""),
            timestamp=data.get("timestamp", datetime.now(timezone.utc)),
            confidence=data.get("confidence"),
            category=data.get("category"),
            applies_to=data.get("applies_to", []),
            context=data.get("context", {}),
            task_id=data.get("task_id") or data.get("context", {}).get("task_id"),
            agent_id=data.get("agent_id") or data.get("context", {}).get("agent_id"),
        )

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get a summary of insights emitted in this session.

        Returns:
            Dictionary with counts and highlights from this session
        """
        if not self._enabled:
            return {"enabled": False, "session_id": self.session_id}

        # Query this session's insights
        decisions = self.query_decisions(time_range="1d")
        lessons = self.query_lessons(time_range="1d")
        questions = self.query_questions(time_range="1d")

        # Filter to this session
        session_decisions = [d for d in decisions if d.context.get("session_id") == self.session_id]
        session_lessons = [l for l in lessons if l.context.get("session_id") == self.session_id]
        session_questions = [q for q in questions if q.context.get("session_id") == self.session_id]

        return {
            "enabled": True,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "agent_id": self.agent_id,
            "decisions_count": len(session_decisions),
            "lessons_count": len(session_lessons),
            "questions_count": len(session_questions),
            "high_confidence_decisions": [
                d.summary for d in session_decisions
                if d.confidence and d.confidence >= 0.9
            ],
            "blocking_questions": [
                q.summary for q in session_questions
                if q.context.get("blocking")
            ],
        }
