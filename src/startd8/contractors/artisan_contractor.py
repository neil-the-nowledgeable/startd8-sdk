"""
ArtisanContractorWorkflow: Main orchestrator for contractor workflow pipelines.

This module provides a comprehensive workflow orchestrator with support for:
- Sequential phase execution with resume capability
- Dry-run mode for safe simulation
- Per-phase and total timeout enforcement
- Cost budget tracking and enforcement
- OpenTelemetry tracing instrumentation
- Checkpoint persistence for fault tolerance

Usage:
    from artisan_contractor_workflow import (
        ArtisanContractorWorkflow,
        WorkflowConfig,
        WorkflowPhase,
        AbstractPhaseHandler,
    )

    class MyHandler(AbstractPhaseHandler):
        def execute(self, phase, context, dry_run=False):
            return {"output": "done", "cost": 0.01, "metadata": {}}

    config = WorkflowConfig(dry_run=False, cost_budget=1.0, total_timeout_seconds=300)
    workflow = ArtisanContractorWorkflow(config=config)
    workflow.register_handler(WorkflowPhase.IMPLEMENT, MyHandler())
    result = workflow.execute(context={"project": "example"})
"""

from __future__ import annotations

import enum
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.protocols import (
    DRAFT_MODEL_CLAUDE_HAIKU,
    REVIEW_MODEL_CLAUDE_OPUS,
    VALIDATE_MODEL_CLAUDE_SONNET,
)

__all__ = [
    "WorkflowPhase",
    "PhaseStatus",
    "WorkflowStatus",
    "WorkflowError",
    "WorkflowTimeoutError",
    "CostBudgetExceededError",
    "PhaseExecutionError",
    "WorkflowConfig",
    "PhaseResult",
    "WorkflowCheckpoint",
    "WorkflowResult",
    "AbstractPhaseHandler",
    "CheckpointStore",
    "DefaultPhaseHandler",
    "JsonFileCheckpointStore",
    "InMemoryCheckpointStore",
    "ArtisanContractorWorkflow",
]

# OTel imports with graceful fallback
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    HAS_OTEL = True
except ImportError:  # pragma: no cover
    HAS_OTEL = False

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Context keys worth persisting in checkpoints for resume.
# Excludes "tasks", "task_index", "generation_results" because they contain
# non-serializable objects (SeedTask, Path, GenerationResult) that are reloaded
# from seed/disk via _ensure_context_loaded().
_CHECKPOINT_CONTEXT_KEYS = frozenset({
    "enriched_seed_path", "plan_title", "plan_goals", "domain_summary",
    "preflight_summary", "total_estimated_loc", "architectural_context",
    "design_calibration", "task_filter", "project_root",
    "design_results", "test_results", "review_results",
})


# ============================================================================
# ENUMS
# ============================================================================


class WorkflowPhase(enum.Enum):
    """Ordered workflow phases (generic orchestration layer).

    These seven phases are an *abstract* orchestration grouping, not
    a 1-to-1 mapping to the 9-phase artisan pipeline defined in
    ``artisan_phases/``.  Concrete handler registrations should map
    them as follows:

        PLAN      → Phase 0 (Preflight) + Phase 1 (Plan Deconstruction)
        SCAFFOLD  → Phase 2 (Lessons Discovery)
        DESIGN    → Phase 3 (Design Documentation)
        IMPLEMENT → Phase 4 (Test Construction) + Phase 5 (Development)
        TEST      → Phase 7 (Final Testing)
        REVIEW    → Phase 6 (Final Assembly & Validation)
        FINALIZE  → Phase 8 (Retrospective & Lessons)
    """

    PLAN = "plan"
    SCAFFOLD = "scaffold"
    DESIGN = "design"
    IMPLEMENT = "implement"
    TEST = "test"
    REVIEW = "review"
    FINALIZE = "finalize"

    @classmethod
    def ordered(cls) -> list[WorkflowPhase]:
        """Return phases in their canonical execution order."""
        return [
            cls.PLAN,
            cls.SCAFFOLD,
            cls.DESIGN,
            cls.IMPLEMENT,
            cls.TEST,
            cls.REVIEW,
            cls.FINALIZE,
        ]

    @classmethod
    def from_value(cls, value: str) -> WorkflowPhase:
        """Get phase enum from its string value.

        Args:
            value: String matching a phase value (case-insensitive).

        Returns:
            The corresponding WorkflowPhase.

        Raises:
            ValueError: If no phase matches the given value.
        """
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        valid = ", ".join(m.value for m in cls)
        raise ValueError(f"Unknown phase: {value!r}. Valid phases: {valid}")


class PhaseStatus(enum.Enum):
    """Status of a phase execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    DRY_RUN = "dry_run"


class WorkflowStatus(enum.Enum):
    """Status of the entire workflow."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BUDGET_EXCEEDED = "budget_exceeded"
    PARTIALLY_COMPLETED = "partially_completed"


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================


class WorkflowError(Exception):
    """Base exception for workflow errors.

    All workflow-specific exceptions carry an optional checkpoint that can be
    used to resume the workflow from the point of failure.
    """

    def __init__(self, message: str, checkpoint: Optional[WorkflowCheckpoint] = None):
        super().__init__(message)
        self.checkpoint = checkpoint


class WorkflowTimeoutError(WorkflowError):
    """Raised when a workflow or phase exceeds its timeout."""


class CostBudgetExceededError(WorkflowError):
    """Raised when cumulative cost exceeds the configured budget."""


class PhaseExecutionError(WorkflowError):
    """Raised when a phase fails execution after all retries are exhausted."""

    def __init__(
        self,
        message: str,
        phase: WorkflowPhase,
        original_error: Optional[Exception] = None,
        checkpoint: Optional[WorkflowCheckpoint] = None,
    ):
        super().__init__(message, checkpoint)
        self.phase = phase
        self.original_error = original_error


# ============================================================================
# DATACLASSES
# ============================================================================


@dataclass
class WorkflowConfig:
    """Configuration for the workflow orchestrator.

    Attributes:
        workflow_id: Unique identifier. Auto-generated UUID if not provided.
        dry_run: If True, handlers receive ``dry_run=True`` and results are
                 marked :pyattr:`PhaseStatus.DRY_RUN`.
        total_timeout_seconds: Wall-clock cap for the entire workflow run.
        phase_timeout_seconds: Default per-phase timeout.
        cost_budget: Maximum cumulative cost across all phases.
        max_retries_per_phase: Number of retry attempts per phase on failure.
        checkpoint_dir: Filesystem directory for JSON checkpoint files.
                        Ignored when a custom ``checkpoint_store`` is passed to
                        the orchestrator.
        tracer_name: OpenTelemetry tracer instrumentation name.
        drafter_model: Model ID for the low-cost drafter role.
        validator_model: Model ID for the validation/gating role.
        reviewer_model: Model ID for the independent review role.
        metadata: Arbitrary metadata attached to results and checkpoints.
    """

    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool = False
    total_timeout_seconds: Optional[float] = None
    phase_timeout_seconds: Optional[float] = None
    cost_budget: Optional[float] = None
    max_retries_per_phase: int = 0
    checkpoint_dir: Optional[str] = None
    tracer_name: str = "startd8.artisan_contractor"
    drafter_model: str = DRAFT_MODEL_CLAUDE_HAIKU.model_id
    validator_model: str = VALIDATE_MODEL_CLAUDE_SONNET.model_id
    reviewer_model: str = REVIEW_MODEL_CLAUDE_OPUS.model_id
    project_root: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.total_timeout_seconds is not None and self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")
        if self.phase_timeout_seconds is not None and self.phase_timeout_seconds <= 0:
            raise ValueError("phase_timeout_seconds must be positive")
        if self.cost_budget is not None and self.cost_budget < 0:
            raise ValueError("cost_budget must be non-negative")
        if self.max_retries_per_phase < 0:
            raise ValueError("max_retries_per_phase must be non-negative")


@dataclass
class PhaseResult:
    """Result of a single phase execution."""

    phase: WorkflowPhase
    status: PhaseStatus
    start_time: str
    end_time: str
    duration_seconds: float
    cost: float = 0.0
    output: Any = None
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowCheckpoint:
    """Checkpoint for resume support.

    Serialised to and from JSON by :class:`JsonFileCheckpointStore`.
    """

    workflow_id: str
    last_completed_phase: Optional[str]
    phase_results: list[dict[str, Any]]
    cumulative_cost: float
    timestamp: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)
    context_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Final result of the entire workflow."""

    workflow_id: str
    status: WorkflowStatus
    phase_results: list[PhaseResult]
    total_cost: float
    total_duration_seconds: float
    start_time: str
    end_time: str
    resumed_from: Optional[str] = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# ABSTRACT BASE CLASSES
# ============================================================================


class AbstractPhaseHandler(ABC):
    """Abstract base class for phase handlers.

    Subclass this and implement :meth:`execute` with your phase logic.
    """

    @abstractmethod
    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute the phase logic.

        Args:
            phase: The workflow phase to execute.
            context: Shared mutable context dict passed through all phases.
            dry_run: If True, simulate execution without side effects.

        Returns:
            A dict with keys:
                - ``"output"``: Any phase output data.
                - ``"cost"``: float cost incurred (e.g. token cost).
                - ``"metadata"``: dict of optional extra metadata.
        """
        ...  # pragma: no cover

    def on_retry(self, phase: WorkflowPhase, attempt: int, error: Exception) -> None:
        """Hook called before a retry attempt.

        Override this to implement backoff, logging, or state cleanup.

        Args:
            phase: The phase being retried.
            attempt: The retry attempt number (1-indexed).
            error: The exception that triggered the retry.
        """


class CheckpointStore(ABC):
    """Abstract base class for checkpoint persistence backends."""

    @abstractmethod
    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        """Persist a checkpoint."""
        ...  # pragma: no cover

    @abstractmethod
    def load(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        """Load a checkpoint by workflow ID. Returns None if not found."""
        ...  # pragma: no cover

    @abstractmethod
    def delete(self, workflow_id: str) -> None:
        """Delete a checkpoint by workflow ID (idempotent)."""
        ...  # pragma: no cover


# ============================================================================
# DEFAULT / BUILT-IN IMPLEMENTATIONS
# ============================================================================


class DefaultPhaseHandler(AbstractPhaseHandler):
    """A no-op phase handler that returns empty results.

    Used as fallback for phases without a registered handler.
    """

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return {
            "output": None,
            "cost": 0.0,
            "metadata": {"handler": "default", "dry_run": dry_run},
        }


class JsonFileCheckpointStore(CheckpointStore):
    """Persists checkpoints as JSON files in a directory.

    File naming convention: ``{workflow_id}.checkpoint.json``
    """

    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, workflow_id: str) -> Path:
        return self.directory / f"{workflow_id}.checkpoint.json"

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        path = self._path(checkpoint.workflow_id)
        data = json.dumps(asdict(checkpoint), indent=2, default=str)
        # Atomic-ish write: write to temp then rename
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(data, encoding="utf-8")
        tmp_path.replace(path)

    def load(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        path = self._path(workflow_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkflowCheckpoint(**data)

    def delete(self, workflow_id: str) -> None:
        path = self._path(workflow_id)
        if path.exists():
            path.unlink()


class InMemoryCheckpointStore(CheckpointStore):
    """In-memory checkpoint store, suitable for testing or ephemeral runs."""

    def __init__(self) -> None:
        self._store: dict[str, WorkflowCheckpoint] = {}

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        self._store[checkpoint.workflow_id] = checkpoint

    def load(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        return self._store.get(workflow_id)

    def delete(self, workflow_id: str) -> None:
        self._store.pop(workflow_id, None)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


class _CostTracker:
    """Internal cost accumulation and budget enforcement."""

    __slots__ = ("budget", "cumulative_cost")

    def __init__(self, budget: Optional[float] = None) -> None:
        self.budget = budget
        self.cumulative_cost: float = 0.0

    def add(self, cost: float) -> None:
        self.cumulative_cost += cost

    def set_cumulative(self, cost: float) -> None:
        self.cumulative_cost = cost

    def check_budget(self) -> bool:
        if self.budget is None:
            return True
        return self.cumulative_cost <= self.budget

    @property
    def remaining(self) -> Optional[float]:
        if self.budget is None:
            return None
        return max(0.0, self.budget - self.cumulative_cost)


class _NoOpSpan:
    """Minimal no-op span for when OTel is not available."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass


class _NoOpTracer:
    """Minimal no-op tracer for when OTel is not available."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================


class ArtisanContractorWorkflow:
    """Main orchestrator that coordinates all workflow phases.

    Features:
        - **Resume support**: Continue from a saved checkpoint or a named phase.
        - **Dry-run mode**: Simulate execution without side effects.
        - **Timeout enforcement**: Per-phase and total wall-clock limits.
        - **Cost budget tracking**: Halt when cumulative cost exceeds the budget.
        - **OpenTelemetry tracing**: Automatic span creation per phase and for
          the workflow root, with graceful degradation when OTel is absent.
        - **Checkpoint persistence**: Pluggable backends for fault tolerance.

    Example::

        config = WorkflowConfig(cost_budget=5.0, total_timeout_seconds=600)
        wf = ArtisanContractorWorkflow(config=config)
        wf.register_handler(WorkflowPhase.IMPLEMENT, MyImplementHandler())
        result = wf.execute(context={"repo": "/path/to/repo"})

    To resume after failure::

        result = wf.execute(resume_from_checkpoint=True)
    """

    def __init__(
        self,
        config: Optional[WorkflowConfig] = None,
        handlers: Optional[dict[WorkflowPhase, AbstractPhaseHandler]] = None,
        checkpoint_store: Optional[CheckpointStore] = None,
        phases: Optional[list[WorkflowPhase]] = None,
    ) -> None:
        """Initialize the workflow orchestrator.

        Args:
            config: Workflow configuration. Defaults to ``WorkflowConfig()``.
            handlers: Mapping of phase → handler. Missing phases use
                      :class:`DefaultPhaseHandler`.
            checkpoint_store: Persistence backend for checkpoints. If ``None``
                              and ``config.checkpoint_dir`` is set, a
                              :class:`JsonFileCheckpointStore` is created.
                              Otherwise :class:`InMemoryCheckpointStore`.
            phases: Ordered list of phases to execute. Defaults to
                    ``WorkflowPhase.ordered()``.
        """
        self.config = config or WorkflowConfig()
        self.phases = phases or WorkflowPhase.ordered()
        self.handlers: dict[WorkflowPhase, AbstractPhaseHandler] = dict(handlers or {})
        self._default_handler = DefaultPhaseHandler()
        self._logger = logging.getLogger(
            f"artisan_contractor.{self.config.workflow_id}"
        )

        # Checkpoint store selection
        if checkpoint_store is not None:
            self.checkpoint_store = checkpoint_store
        elif self.config.checkpoint_dir:
            self.checkpoint_store = JsonFileCheckpointStore(self.config.checkpoint_dir)
        else:
            self.checkpoint_store = InMemoryCheckpointStore()

        self._tracer: Optional[Any] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tracer(self) -> Any:
        """Get the OTel tracer (or no-op fallback)."""
        if self._tracer is None:
            if HAS_OTEL:
                self._tracer = trace.get_tracer(self.config.tracer_name)
            else:
                self._tracer = _NoOpTracer()
        return self._tracer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_handler(
        self, phase: WorkflowPhase, handler: AbstractPhaseHandler
    ) -> None:
        """Register a handler for a specific phase.

        Args:
            phase: The workflow phase.
            handler: The handler to register.
        """
        self.handlers[phase] = handler

    def execute(
        self,
        context: Optional[dict[str, Any]] = None,
        resume_from: Optional[str] = None,
        resume_from_checkpoint: bool = False,
    ) -> WorkflowResult:
        """Execute the workflow.

        Args:
            context: Shared context dict passed to all phase handlers.
                     Mutable — handlers can add/modify keys for downstream
                     phases.
            resume_from: Phase value string to resume from (e.g. ``"implement"``).
                         Phases before this are marked ``SKIPPED``.
            resume_from_checkpoint: If ``True``, load the last checkpoint for
                                    this ``workflow_id`` and resume from the
                                    phase after ``last_completed_phase``.

        Returns:
            :class:`WorkflowResult` with all phase outcomes.

        Raises:
            WorkflowTimeoutError: If total or phase timeout exceeded.
            CostBudgetExceededError: If cost budget exceeded.
            PhaseExecutionError: If a phase fails and retries are exhausted.
            ValueError: If ``resume_from`` specifies an unknown phase.
        """
        if context is None:
            context = {}

        # Inject model assignments so phase handlers can look them up
        context.setdefault("drafter_model", self.config.drafter_model)
        context.setdefault("validator_model", self.config.validator_model)
        context.setdefault("reviewer_model", self.config.reviewer_model)

        # Inject project_root for domain-aware checklist
        if self.config.project_root:
            context.setdefault("project_root", self.config.project_root)
        else:
            context.setdefault("project_root", str(Path.cwd()))

        config = self.config
        cost_tracker = _CostTracker(budget=config.cost_budget)
        phase_results: list[PhaseResult] = []
        workflow_start = time.monotonic()
        workflow_start_iso = datetime.now(timezone.utc).isoformat()
        resumed_from_value: Optional[str] = None

        # Determine start index and load checkpoint if needed
        start_index, loaded_checkpoint = self._determine_start_index(
            resume_from, resume_from_checkpoint
        )

        if loaded_checkpoint:
            cost_tracker.set_cumulative(loaded_checkpoint.cumulative_cost)
            for pr_dict in loaded_checkpoint.phase_results:
                pr_dict_copy = dict(pr_dict)
                pr_dict_copy["phase"] = WorkflowPhase.from_value(pr_dict_copy["phase"])
                pr_dict_copy["status"] = PhaseStatus(pr_dict_copy["status"])
                phase_results.append(PhaseResult(**pr_dict_copy))
            resumed_from_value = loaded_checkpoint.last_completed_phase
            # Restore persisted context keys (CLI-supplied values take precedence)
            if loaded_checkpoint.context_snapshot:
                for key, value in loaded_checkpoint.context_snapshot.items():
                    context.setdefault(key, value)
            self._logger.info(
                "Resuming workflow %s from checkpoint (after phase %s)",
                config.workflow_id,
                resumed_from_value,
            )

        if resume_from and not loaded_checkpoint:
            resumed_from_value = resume_from
            self._logger.info(
                "Resuming workflow %s from phase %s",
                config.workflow_id,
                resume_from,
            )

        # Build skipped results for phases before start_index
        if not loaded_checkpoint:
            for idx in range(start_index):
                phase_results.append(self._build_skipped_result(self.phases[idx]))

        # Start OTel root span
        root_span_context = self.tracer.start_as_current_span(
            f"workflow.{config.workflow_id}",
            attributes={
                "workflow.id": config.workflow_id,
                "workflow.dry_run": config.dry_run,
                "workflow.total_timeout": config.total_timeout_seconds or -1,
                "workflow.cost_budget": config.cost_budget or -1,
                "workflow.resume_from": resumed_from_value or "",
                "workflow.drafter_model": config.drafter_model,
                "workflow.validator_model": config.validator_model,
                "workflow.reviewer_model": config.reviewer_model,
            },
        )

        final_status = WorkflowStatus.IN_PROGRESS
        total_duration = 0.0
        workflow_end_iso = workflow_start_iso

        with root_span_context as root_span:
            try:
                for idx in range(start_index, len(self.phases)):
                    phase = self.phases[idx]

                    # Check remaining total timeout
                    elapsed = time.monotonic() - workflow_start
                    if config.total_timeout_seconds is not None:
                        remaining = config.total_timeout_seconds - elapsed
                        if remaining <= 0:
                            last_phase = (
                                self.phases[idx - 1] if idx > 0 else None
                            )
                            checkpoint = self._persist_checkpoint(
                                last_phase,
                                phase_results,
                                cost_tracker.cumulative_cost,
                                WorkflowStatus.TIMED_OUT,
                                context=context,
                            )
                            final_status = WorkflowStatus.TIMED_OUT
                            raise WorkflowTimeoutError(
                                f"Total workflow timeout "
                                f"({config.total_timeout_seconds}s) exceeded "
                                f"before phase {phase.value}",
                                checkpoint=checkpoint,
                            )
                    else:
                        remaining = None

                    self._logger.debug(
                        "Executing phase %s (index %d/%d)",
                        phase.value,
                        idx + 1,
                        len(self.phases),
                    )

                    # Execute phase
                    phase_result = self._execute_phase(phase, context, remaining)
                    phase_results.append(phase_result)

                    # Track cost
                    cost_tracker.add(phase_result.cost)

                    # Persist checkpoint after every phase
                    self._persist_checkpoint(
                        phase,
                        phase_results,
                        cost_tracker.cumulative_cost,
                        WorkflowStatus.IN_PROGRESS,
                        context=context,
                    )

                    # Check budget
                    if not cost_tracker.check_budget():
                        checkpoint = self._persist_checkpoint(
                            phase,
                            phase_results,
                            cost_tracker.cumulative_cost,
                            WorkflowStatus.BUDGET_EXCEEDED,
                            context=context,
                        )
                        final_status = WorkflowStatus.BUDGET_EXCEEDED
                        assert config.cost_budget is not None  # for type checker
                        raise CostBudgetExceededError(
                            f"Cost budget exceeded: "
                            f"{cost_tracker.cumulative_cost:.4f} > "
                            f"{config.cost_budget:.4f}",
                            checkpoint=checkpoint,
                        )

                    # Halt on phase failure (retries already exhausted)
                    if phase_result.status == PhaseStatus.FAILED:
                        checkpoint = self._persist_checkpoint(
                            phase,
                            phase_results,
                            cost_tracker.cumulative_cost,
                            WorkflowStatus.FAILED,
                            context=context,
                        )
                        final_status = WorkflowStatus.FAILED
                        raise PhaseExecutionError(
                            f"Phase {phase.value} failed: "
                            f"{phase_result.error_message}",
                            phase=phase,
                            checkpoint=checkpoint,
                        )

                    # Halt on phase timeout
                    if phase_result.status == PhaseStatus.TIMED_OUT:
                        checkpoint = self._persist_checkpoint(
                            phase,
                            phase_results,
                            cost_tracker.cumulative_cost,
                            WorkflowStatus.TIMED_OUT,
                            context=context,
                        )
                        final_status = WorkflowStatus.TIMED_OUT
                        raise WorkflowTimeoutError(
                            f"Phase {phase.value} timed out",
                            checkpoint=checkpoint,
                        )

                final_status = WorkflowStatus.COMPLETED
                # Clean up checkpoint on successful completion
                self.checkpoint_store.delete(config.workflow_id)
                self._logger.info(
                    "Workflow %s completed successfully", config.workflow_id
                )

            except (
                WorkflowTimeoutError,
                CostBudgetExceededError,
                PhaseExecutionError,
            ):
                if HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                    root_span.set_status(Status(StatusCode.ERROR))
                raise

            except Exception as err:
                final_status = WorkflowStatus.FAILED
                self._logger.exception(
                    "Workflow %s failed with unexpected error", config.workflow_id
                )
                if HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                    root_span.record_exception(err)
                    root_span.set_status(Status(StatusCode.ERROR))
                raise

            finally:
                workflow_end = time.monotonic()
                workflow_end_iso = datetime.now(timezone.utc).isoformat()
                total_duration = workflow_end - workflow_start

                if HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                    root_span.set_attribute("workflow.status", final_status.value)
                    root_span.set_attribute(
                        "workflow.total_cost", cost_tracker.cumulative_cost
                    )
                    root_span.set_attribute(
                        "workflow.total_duration_seconds", total_duration
                    )
                    root_span.set_attribute(
                        "workflow.phases_completed",
                        sum(
                            1
                            for r in phase_results
                            if r.status
                            in (PhaseStatus.COMPLETED, PhaseStatus.DRY_RUN)
                        ),
                    )

        return WorkflowResult(
            workflow_id=config.workflow_id,
            status=final_status,
            phase_results=phase_results,
            total_cost=cost_tracker.cumulative_cost,
            total_duration_seconds=total_duration,
            start_time=workflow_start_iso,
            end_time=workflow_end_iso,
            resumed_from=resumed_from_value,
            dry_run=config.dry_run,
            metadata=config.metadata,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _determine_start_index(
        self,
        resume_from: Optional[str],
        resume_from_checkpoint: bool,
    ) -> tuple[int, Optional[WorkflowCheckpoint]]:
        """Determine which phase index to start from.

        Returns:
            ``(start_index, loaded_checkpoint_or_None)``

        Raises:
            ValueError: If ``resume_from`` specifies an unknown phase.
        """
        loaded_checkpoint: Optional[WorkflowCheckpoint] = None

        if resume_from_checkpoint:
            loaded_checkpoint = self.checkpoint_store.load(self.config.workflow_id)

        if loaded_checkpoint and loaded_checkpoint.last_completed_phase:
            last_phase = WorkflowPhase.from_value(
                loaded_checkpoint.last_completed_phase
            )
            for idx, phase in enumerate(self.phases):
                if phase == last_phase:
                    return idx + 1, loaded_checkpoint
            # Phase not in current phase list — start from beginning
            return 0, loaded_checkpoint

        if loaded_checkpoint:
            return 0, loaded_checkpoint

        if resume_from:
            resume_phase = WorkflowPhase.from_value(resume_from)
            for idx, phase in enumerate(self.phases):
                if phase == resume_phase:
                    return idx, None
            raise ValueError(
                f"Phase {resume_from!r} not found in configured phases"
            )

        return 0, None

    def _execute_phase(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        remaining_total_timeout: Optional[float],
    ) -> PhaseResult:
        """Execute a single phase with timeout enforcement and retries."""
        handler = self.handlers.get(phase, self._default_handler)
        config = self.config
        max_retries = config.max_retries_per_phase
        attempt = 0

        # Determine effective timeout for this phase
        effective_timeout = config.phase_timeout_seconds
        if remaining_total_timeout is not None:
            if effective_timeout is not None:
                effective_timeout = min(effective_timeout, remaining_total_timeout)
            else:
                effective_timeout = remaining_total_timeout

        last_error: Optional[Exception] = None
        phase_start_iso = ""

        while attempt <= max_retries:
            phase_start = time.monotonic()
            phase_start_iso = datetime.now(timezone.utc).isoformat()

            span_context = self.tracer.start_as_current_span(
                f"phase.{phase.value}",
                attributes={
                    "phase.name": phase.value,
                    "phase.attempt": attempt,
                    "phase.dry_run": config.dry_run,
                    "phase.timeout": effective_timeout or -1,
                },
            )

            with span_context as span:
                try:
                    result_dict = self._run_handler_with_timeout(
                        handler, phase, context, effective_timeout
                    )

                    phase_end = time.monotonic()
                    duration = phase_end - phase_start

                    status = (
                        PhaseStatus.DRY_RUN
                        if config.dry_run
                        else PhaseStatus.COMPLETED
                    )
                    cost = float(result_dict.get("cost") or 0.0)
                    output = result_dict.get("output")
                    metadata = result_dict.get("metadata", {})

                    if HAS_OTEL and not isinstance(span, _NoOpSpan):
                        span.set_attribute("phase.status", status.value)
                        span.set_attribute("phase.cost", cost)
                        span.set_attribute("phase.duration_seconds", duration)
                        span.set_status(Status(StatusCode.OK))

                    return PhaseResult(
                        phase=phase,
                        status=status,
                        start_time=phase_start_iso,
                        end_time=datetime.now(timezone.utc).isoformat(),
                        duration_seconds=duration,
                        cost=cost,
                        output=output,
                        retry_count=attempt,
                        metadata=metadata,
                    )

                except FuturesTimeoutError:
                    phase_end = time.monotonic()
                    duration = phase_end - phase_start

                    self._logger.warning(
                        "Phase %s timed out after %.2fs (attempt %d)",
                        phase.value,
                        effective_timeout or 0,
                        attempt,
                    )

                    if HAS_OTEL and not isinstance(span, _NoOpSpan):
                        span.set_attribute(
                            "phase.status", PhaseStatus.TIMED_OUT.value
                        )
                        span.set_status(
                            Status(StatusCode.ERROR, "Phase timed out")
                        )
                        span.add_event(
                            "phase.timeout",
                            {"timeout_seconds": effective_timeout or -1},
                        )

                    return PhaseResult(
                        phase=phase,
                        status=PhaseStatus.TIMED_OUT,
                        start_time=phase_start_iso,
                        end_time=datetime.now(timezone.utc).isoformat(),
                        duration_seconds=duration,
                        error_message=(
                            f"Phase timed out after {effective_timeout}s"
                        ),
                        retry_count=attempt,
                    )

                except Exception as err:
                    phase_end = time.monotonic()
                    duration = phase_end - phase_start
                    last_error = err

                    if HAS_OTEL and not isinstance(span, _NoOpSpan):
                        span.record_exception(err)
                        span.set_attribute(
                            "phase.status", PhaseStatus.FAILED.value
                        )
                        span.set_status(Status(StatusCode.ERROR, str(err)))

                    if attempt < max_retries:
                        self._logger.info(
                            "Phase %s failed (attempt %d/%d), retrying: %s",
                            phase.value,
                            attempt + 1,
                            max_retries + 1,
                            err,
                        )
                        handler.on_retry(phase, attempt + 1, err)
                        if HAS_OTEL and not isinstance(span, _NoOpSpan):
                            span.add_event(
                                "phase.retry", {"attempt": attempt + 1}
                            )
                        attempt += 1
                        continue

                    self._logger.error(
                        "Phase %s failed after %d attempt(s): %s",
                        phase.value,
                        attempt + 1,
                        err,
                    )

                    return PhaseResult(
                        phase=phase,
                        status=PhaseStatus.FAILED,
                        start_time=phase_start_iso,
                        end_time=datetime.now(timezone.utc).isoformat(),
                        duration_seconds=duration,
                        error_message=str(err),
                        retry_count=attempt,
                    )

        # Defensive fallback (should be unreachable)
        return PhaseResult(
            phase=phase,
            status=PhaseStatus.FAILED,
            start_time=phase_start_iso,
            end_time=datetime.now(timezone.utc).isoformat(),
            duration_seconds=0.0,
            error_message=str(last_error) if last_error else "Unknown error",
            retry_count=attempt,
        )

    def _run_handler_with_timeout(
        self,
        handler: AbstractPhaseHandler,
        phase: WorkflowPhase,
        context: dict[str, Any],
        timeout: Optional[float],
    ) -> dict[str, Any]:
        """Run ``handler.execute()`` with optional thread-based timeout.

        .. warning::

            Timeouts are enforced via :class:`ThreadPoolExecutor`.  When a
            timeout fires, the handler thread is *abandoned*, not forcibly
            terminated — ``future.cancel()`` has no effect on an already-
            running task.  The thread continues executing until the handler
            returns naturally.

            **Implications:**

            * Side effects (API calls, file writes) continue after timeout.
            * At most one orphaned thread exists per timeout (bounded).
            * Retry attempts may overlap with a still-running prior attempt.

            Keep handlers fast and responsive.  For cooperative cancellation,
            check a ``threading.Event`` passed via the *context* dict.

        Raises:
            FuturesTimeoutError: If timeout exceeded.
        """
        if timeout is None:
            return handler.execute(phase, context, dry_run=self.config.dry_run)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                handler.execute, phase, context, self.config.dry_run
            )
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError:
                future.cancel()
                raise

    def _persist_checkpoint(
        self,
        last_completed_phase: Optional[WorkflowPhase],
        phase_results: list[PhaseResult],
        cumulative_cost: float,
        status: WorkflowStatus,
        context: Optional[dict[str, Any]] = None,
    ) -> WorkflowCheckpoint:
        """Build and save a checkpoint, returning it for attachment to errors."""
        # Snapshot JSON-serializable context keys for resume
        snapshot: dict[str, Any] = {}
        if context is not None:
            for key in _CHECKPOINT_CONTEXT_KEYS:
                if key not in context:
                    continue
                value = context[key]
                try:
                    json.dumps(value)  # verify serializable
                    snapshot[key] = value
                except (TypeError, ValueError, OverflowError):
                    pass  # skip non-serializable values

        checkpoint = WorkflowCheckpoint(
            workflow_id=self.config.workflow_id,
            last_completed_phase=(
                last_completed_phase.value if last_completed_phase else None
            ),
            phase_results=[
                {
                    "phase": res.phase.value,
                    "status": res.status.value,
                    "start_time": res.start_time,
                    "end_time": res.end_time,
                    "duration_seconds": res.duration_seconds,
                    "cost": res.cost,
                    "output": res.output,
                    "error_message": res.error_message,
                    "retry_count": res.retry_count,
                    "metadata": res.metadata,
                }
                for res in phase_results
            ],
            cumulative_cost=cumulative_cost,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=status.value,
            metadata=self.config.metadata,
            context_snapshot=snapshot,
        )
        try:
            self.checkpoint_store.save(checkpoint)
        except Exception:
            self._logger.warning(
                "Failed to persist checkpoint for workflow %s",
                self.config.workflow_id,
                exc_info=True,
            )
        return checkpoint

    @staticmethod
    def _build_skipped_result(phase: WorkflowPhase) -> PhaseResult:
        """Create a ``PhaseResult`` with ``SKIPPED`` status."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return PhaseResult(
            phase=phase,
            status=PhaseStatus.SKIPPED,
            start_time=now_iso,
            end_time=now_iso,
            duration_seconds=0.0,
            cost=0.0,
            output=None,
            retry_count=0,
            metadata={"reason": "skipped_on_resume"},
        )