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

import copy
import enum
import hashlib
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

import questionary
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from startd8.contractors.context_schema import (
    PhaseContextError,
    validate_phase_boundary,
)
from startd8.contractors.protocols import (
    DRAFT_MODEL_CLAUDE_HAIKU,
    REVIEW_MODEL_CLAUDE_OPUS,
    VALIDATE_MODEL_CLAUDE_SONNET,
)
from startd8.otel import attach_context, capture_context, detach_context

__all__ = [
    "WorkflowPhase",
    "PhaseStatus",
    "WorkflowStatus",
    "WorkflowError",
    "WorkflowTimeoutError",
    "CostBudgetExceededError",
    "PhaseExecutionError",
    "InvalidTaskIdError",
    "UnresolvedDependencyError",
    "WaveMergeCollisionError",
    "QualityGateError",
    "WorkflowConfig",
    "PhaseResult",
    "InnerPhaseResult",
    "FeaturePartialResult",
    "CHECKPOINT_SCHEMA_VERSION",
    "WorkflowCheckpoint",
    "WorkflowResult",
    "AbstractPhaseHandler",
    "CheckpointStore",
    "DefaultPhaseHandler",
    "JsonFileCheckpointStore",
    "InMemoryCheckpointStore",
    "ArtisanContractorWorkflow",
]

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime cost.
_OTEL_DESCRIPTORS = {
    "spans": [
        {
            "name_pattern": "artisan.workflow.{workflow_id}",
            "kind": "INTERNAL",
            "attributes": ["workflow.id", "workflow.phase_count", "workflow.cost_budget", "workflow.dry_run"],
            "events": [],
        },
        {
            "name_pattern": "artisan.workflow.{workflow_id}.phase.{phase}",
            "kind": "INTERNAL",
            "attributes": ["phase.name", "phase.status", "phase.duration_ms", "phase.cost"],
            "events": [],
        },
    ],
}

# OTel imports with graceful fallback
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    HAS_OTEL = True
except ImportError:  # pragma: no cover
    HAS_OTEL = False

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Fraction of cost_budget at which a warning is logged.
# For example, 0.5 means "warn when 50% of the budget has been consumed".
_BUDGET_WARNING_THRESHOLD_FRACTION = 0.5

# PCA-202: Checkpoint size guard for plan_document_text.
_PLAN_DOC_CHECKPOINT_MAX_CHARS = 1000
_PLAN_DOC_TRUNCATION_MARKER = "\n... [truncated, full text in seed]"

# Context keys worth persisting in checkpoints for resume.
# Excludes "tasks", "task_index", "generation_results" because they contain
# non-serializable objects (SeedTask, Path, GenerationResult) that are reloaded
# from seed/disk via _ensure_context_loaded().
_CHECKPOINT_CONTEXT_KEYS = frozenset({
    "enriched_seed_path", "plan_title", "plan_goals", "domain_summary",
    "preflight_summary", "total_estimated_loc", "architectural_context", "project_metadata",
    "design_calibration", "task_filter", "project_root",
    "design_results", "test_results", "review_results",
    "integration_results",
    "abort_on_preflight_fail",
    # Phase 2 data flow keys — lost on resume without these:
    "source_checksum", "parameter_sources", "semantic_conventions",
    "output_conventions", "scaffold", "example_artifacts",
    "workflow_id",
    # Gate 4: per-task truncation detection results (implement → finalize)
    "truncation_flags",
    # INTEGRATE phase: staging dir location
    "_staging_dir",
    # PCA-200: project-level context fields for resume survival
    "onboarding_derivation_rules", "onboarding_resolved_parameters",
    "onboarding_output_contracts", "onboarding_calibration_hints",
    "onboarding_open_questions", "onboarding_dependency_graph",
    "service_metadata", "plan_document_text",
    # IMP-8b / IMP-9c: REFINE forwarding fields for resume survival
    "onboarding_refine_suggestions", "refine_provenance",
    # CCD: Context Correctness by Design — lane/manifest/collision data
    "shared_file_manifest", "lane_to_file_mapping", "lane_conflicts",
    "_design_lane_computation_skipped", "_design_lane_count",
    "design_mode_summary",
    # REQ-PAQ-603: quality gate traceability survives resume.
    "quality_gate_outcomes", "quality_gate_summary",
    # AR-153: bounded regenerate-with-feedback forensic transcript.
    "retry_transcripts",
})


# ============================================================================
# ENUMS
# ============================================================================


class WorkflowPhase(enum.Enum):
    """Ordered workflow phases (generic orchestration layer).

    These eight phases are an *abstract* orchestration grouping, not
    a 1-to-1 mapping to the 9-phase artisan pipeline defined in
    ``artisan_phases/``.  Concrete handler registrations should map
    them as follows:

        PLAN      → Phase 0 (Preflight) + Phase 1 (Plan Deconstruction)
        SCAFFOLD  → Phase 2 (Lessons Discovery)
        DESIGN    → Phase 3 (Design Documentation)
        IMPLEMENT → Phase 4 (Test Construction) + Phase 5 (Development)
        INTEGRATE → Merge staged files into project_root with validation
        TEST      → Phase 7 (Final Testing)
        REVIEW    → Phase 6 (Final Assembly & Validation)
        FINALIZE  → Phase 8 (Retrospective & Lessons)
    """

    PLAN = "plan"
    SCAFFOLD = "scaffold"
    DESIGN = "design"
    IMPLEMENT = "implement"
    INTEGRATE = "integrate"
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
            cls.INTEGRATE,
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
        try:
            return cls._value_map[normalized]
        except (AttributeError, KeyError):
            pass
        # Build lookup on first miss (or first call)
        cls._value_map = {m.value: m for m in cls}
        try:
            return cls._value_map[normalized]
        except KeyError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"Unknown phase: {value!r}. Valid phases: {valid}"
            ) from None


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
    FAILED_CHECKPOINT = "failed_checkpoint"
    FAILED_UNRECOVERABLE = "failed_unrecoverable"


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


class InvalidTaskIdError(ValueError):
    """Raised when a task_id contains unsafe characters."""


class UnresolvedDependencyError(ValueError):
    """Raised when depends_on references a task_id not in the task set (strict mode)."""


class WaveMergeCollisionError(RuntimeError):
    """Raised when a task ID appears in multiple waves during merge.

    This indicates a fundamental invariant violation in compute_waves() —
    the task set was not properly partitioned. Continuing would cause
    non-deterministic data corruption via silent dict.update() overwrite.
    """


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


class QualityGateError(Exception):
    """Raised when a quality gate check fails in block mode."""

    def __init__(self, message: str, phase: WorkflowPhase, details: dict):
        super().__init__(message)
        self.phase = phase
        self.details = details


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
        feature_serial: If True, use feature-serial execution where each feature
                        completes all inner phases (DESIGN→IMPLEMENT→INTEGRATE→TEST→REVIEW)
                        before the next feature begins. If False (default), use
                        phase-serial execution where all features complete one
                        phase before moving to the next.
        metadata: Arbitrary metadata attached to results and checkpoints.
    """

    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool = False
    total_timeout_seconds: Optional[float] = None
    phase_timeout_seconds: Optional[float] = None
    cost_budget: Optional[float] = None
    max_retries_per_phase: int = 0
    checkpoint_dir: Optional[str] = ".startd8/checkpoints"
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
class InnerPhaseResult:
    """Result of a single inner phase (DESIGN/IMPLEMENT/INTEGRATE/TEST/REVIEW) for a feature.

    Used to track granular progress within feature-serial execution.
    """

    status: str  # "completed", "failed", "in_progress", "skipped"
    cost: float
    timestamp: str
    error: Optional[str] = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    # Phase-specific artifacts:
    # - design: {"design_document": str}
    # - implement: {"files_written": list[str], "partial_files": dict[str, str]}
    # - integrate: {"merged_files": list[str], "rollback_available": bool}
    # - test: {"test_results": dict, "coverage": float}
    # - review: {"score": float, "issues": list}


@dataclass
class FeaturePartialResult:
    """Accumulated partial results for a feature that didn't complete.

    Persisted for post-failure inspection and potential reuse.
    """

    feature_id: str
    started_at: str
    failed_at: Optional[str] = None
    failure_reason: Optional[str] = None
    inner_phases: dict[str, dict[str, Any]] = field(default_factory=dict)

    def fitness_summary(self) -> dict[str, Any]:
        """Generate summary for fitness evaluation.

        Returns:
            Dict with completed phases, failure info, and cost summary.
        """
        return {
            "feature_id": self.feature_id,
            "completed_phases": [
                p for p, r in self.inner_phases.items()
                if r.get("status") == "completed"
            ],
            "failed_phase": next(
                (p for p, r in self.inner_phases.items() if r.get("status") == "failed"),
                None,
            ),
            "total_cost": sum(r.get("cost", 0.0) for r in self.inner_phases.values()),
            "has_design": (
                "design" in self.inner_phases
                and self.inner_phases["design"].get("status") == "completed"
            ),
            "failure_reason": self.failure_reason,
        }


# Schema version for checkpoint format changes (bump on breaking changes)
CHECKPOINT_SCHEMA_VERSION = 4


@dataclass
class WorkflowCheckpoint:
    """Checkpoint for resume support.

    Serialised to and from JSON by :class:`JsonFileCheckpointStore`.

    Schema version history:
        v1: Original format (phase-serial execution)
        v2: Feature-serial execution with completed_features, current_feature,
            current_feature_phase, and feature_partial_results fields.
        v3: Lane-parallel execution with lane_assignments, completed_lanes,
            and lane_results fields.
        v4: Wave+Lane execution with wave_assignments, completed_waves,
            current_wave, and wave_resume_count fields.
    """

    workflow_id: str
    last_completed_phase: Optional[str]
    phase_results: list[dict[str, Any]]
    cumulative_cost: float
    timestamp: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)
    context_snapshot: dict[str, Any] = field(default_factory=dict)

    # Feature-serial execution fields (v2+)
    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    completed_features: list[str] = field(default_factory=list)
    current_feature: Optional[str] = None
    current_feature_phase: Optional[str] = None  # DESIGN/IMPLEMENT/INTEGRATE/TEST/REVIEW
    feature_partial_results: dict[str, dict[str, Any]] = field(default_factory=dict)


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

    # Handlers must opt-in for feature-serial inner-loop execution.
    # This prevents silently running incompatible custom handlers.

    # OT-710: Last entry boundary result for forensic logging.
    # Set by _execute_phase() after entry gate validation.
    _last_entry_boundary_result: Any = None

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

        # Verify checkpoint dir is writable — a read-only filesystem will
        # let mkdir succeed (exist_ok=True) but silently fail on every save.
        _probe = self.directory / ".write_probe"
        try:
            _probe.touch()
            _probe.unlink()
        except OSError as exc:
            logger.warning(
                "Checkpoint directory %s is not writable (%s) — "
                "crash recovery will not be available",
                self.directory,
                exc,
            )
            self._writable = False
        else:
            self._writable = True

    def _path(self, workflow_id: str) -> Path:
        if not _SAFE_TASK_ID_PATTERN.match(workflow_id):
            raise ValueError(
                f"Unsafe workflow_id for checkpoint path: {workflow_id!r}"
            )
        return self.directory / f"{workflow_id}.checkpoint.json"

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        if not self._writable:
            logger.debug("Checkpoint save skipped — directory not writable")
            return
        path = self._path(checkpoint.workflow_id)
        data = json.dumps(asdict(checkpoint), indent=2, default=str)
        # Atomic write: write to temp then replace().
        # os.replace() is atomic on POSIX; on Windows it is atomic
        # only when src and dst are on the same volume (which they
        # are here — same directory).  This guarantees the checkpoint
        # is either fully persisted or not persisted at all.
        tmp_path = path.with_suffix(".tmp")
        try:
            tmp_path.write_text(data, encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            logger.warning(
                "Checkpoint save failed for workflow %s: %s — "
                "workflow continues without persistence",
                checkpoint.workflow_id,
                exc,
            )
            # Clean up orphaned temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def load(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        path = self._path(workflow_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(
                "Checkpoint file for workflow %s is corrupt or unreadable: %s — "
                "treating as absent (will not resume)",
                workflow_id,
                exc,
            )
            return None

        # Backward compatibility: v1 checkpoints lack feature-serial fields
        if "schema_version" not in data:
            data["schema_version"] = 1  # Legacy checkpoint
            data.setdefault("completed_features", [])
            data.setdefault("current_feature", None)
            data.setdefault("current_feature_phase", None)
            data.setdefault("feature_partial_results", {})
            logger.debug(
                "Loaded v1 checkpoint for workflow %s — migrated to v2 schema",
                workflow_id,
            )

        # Migration chain: v1→v2 (feature-serial fields) → v2→v3 (lane fields,
        # via dataclass defaults) → v3→v4 (wave fields, below)
        if data.get("schema_version", 1) < 4:
            # Create .bak of pre-migration checkpoint for rollback safety
            bak_path = path.with_suffix(".json.bak")
            try:
                shutil.copy2(path, bak_path)
                logger.info(
                    "Created pre-migration backup: %s (schema v%d → v4)",
                    bak_path, data.get("schema_version", 1),
                )
            except OSError as e:
                logger.warning(
                    "Failed to create pre-migration backup %s: %s — "
                    "proceeding with migration",
                    bak_path, e,
                )

            data.setdefault("wave_assignments", {})
            data.setdefault("completed_waves", [])
            data.setdefault("current_wave", None)
            data.setdefault("wave_resume_count", {})
            data["schema_version"] = CHECKPOINT_SCHEMA_VERSION

        # Wave field type validation — wave mode writes N checkpoints per
        # IMPLEMENT phase (one per wave barrier plus per-lane within each wave),
        # multiplying corruption opportunities.
        if not isinstance(data.get("completed_waves", []), list) or \
           not all(isinstance(w, int) for w in data.get("completed_waves", [])):
            logger.error(
                "Checkpoint corruption: completed_waves=%r is not list[int] "
                "— treating as empty (wave will re-run from start)",
                data.get("completed_waves"),
            )
            data["completed_waves"] = []

        if data.get("current_wave") is not None and \
           not isinstance(data.get("current_wave"), int):
            logger.error(
                "Checkpoint corruption: current_wave=%r is not Optional[int] "
                "— treating as None (wave will re-run)",
                data.get("current_wave"),
            )
            data["current_wave"] = None

        if not isinstance(data.get("wave_assignments", {}), dict) or \
           not all(isinstance(k, str) and isinstance(v, int)
                   for k, v in data.get("wave_assignments", {}).items()):
            logger.error(
                "Checkpoint corruption: wave_assignments has invalid types "
                "— treating as empty (waves will be recomputed)",
            )
            data["wave_assignments"] = {}

        # Task ID content validation for checkpoint-loaded wave_assignments
        if data.get("wave_assignments"):
            for key in list(data["wave_assignments"].keys()):
                if not _SAFE_TASK_ID_PATTERN.match(key):
                    logger.error(
                        "Checkpoint corruption: wave_assignments key %r contains "
                        "unsafe characters — clearing wave_assignments",
                        key,
                    )
                    data["wave_assignments"] = {}
                    break

        # Filter out unknown keys to tolerate future schema additions or
        # manual edits without crashing on TypeError.
        known_fields = {f.name for f in fields(WorkflowCheckpoint)}
        unknown = set(data.keys()) - known_fields
        if unknown:
            logger.warning(
                "Checkpoint for workflow %s contains unknown fields %s — "
                "ignoring them (possible future schema or manual edit)",
                workflow_id,
                sorted(unknown),
            )
            data = {k: v for k, v in data.items() if k in known_fields}

        logger.info(
            "Loaded checkpoint for workflow %s (schema v%d)",
            workflow_id,
            data.get("schema_version", 1),
        )
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
# TASK ID SAFETY PATTERN
# ============================================================================

# Safe task ID pattern: alphanumerics, dots, underscores, hyphens.
# Rejects path separators, shell metacharacters, null bytes, format strings.
# Canonical definition — imported by context_seed_handlers.py and
# plan_ingestion_workflow.py via artisan_contractor._SAFE_TASK_ID_PATTERN.
_SAFE_TASK_ID_PATTERN = re.compile(r'^[A-Za-z0-9._-]+$')


# ============================================================================
# WAVE COMPUTATION PROTOCOL AND ALGORITHM
# ============================================================================













# ============================================================================
# MODULE-LEVEL CONSTANTS FOR CONTEXT FIELD MANAGEMENT
# ============================================================================

# Task-keyed fields: dicts where keys are task_ids.
# Used by _isolate_context_for_lane() and _merge_lane_results().

# File-keyed fields: dicts where keys are file paths, not task IDs.
# Merged with last-write-wins semantics (no collision assertion).

# Read-only global fields: set once during PLAN/SCAFFOLD, should not
# be modified by lane threads during IMPLEMENT waves.


# ============================================================================
# LANE-PARALLEL HELPERS
# ============================================================================








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
        if cost < 0:
            logger.warning("Negative cost %s clamped to 0", cost)
            cost = 0.0
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

    def get_span_context(self) -> None:
        return None

    def is_recording(self) -> bool:
        return False


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
        contract_path: Optional[Path] = None,
        quality_gate: Optional[str] = None,
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
            contract_path: Path to a context propagation contract YAML file.
                           When provided, enrichment fields are validated at
                           phase boundaries and propagation events are emitted.
                           When ``None`` (default), auto-discovers
                           ``contracts/artisan-pipeline.contract.yaml`` adjacent
                           to this module if it exists.
            quality_gate: Behavior on DESIGN/TEST/REVIEW quality failures.
                          ``"skip"`` = no check (legacy behavior).
                          ``"warn"`` = log WARNING, continue (default).
                          ``"block"`` = raise :class:`QualityGateError`.
        """
        self.config = config or WorkflowConfig()
        gate_mode = quality_gate
        if gate_mode is None:
            gate_mode = os.getenv("STARTD8_QUALITY_GATE_MODE", "warn")
        gate_mode = str(gate_mode).strip().lower()
        if gate_mode not in {"skip", "warn", "block"}:
            raise ValueError(
                f"quality_gate must be one of skip|warn|block, got {gate_mode!r}"
            )
        self._quality_gate = gate_mode
        self.phases = phases or WorkflowPhase.ordered()
        self.handlers: dict[WorkflowPhase, AbstractPhaseHandler] = dict(handlers or {})
        self._default_handler = DefaultPhaseHandler()

        # Auto-discover contract YAML when no explicit path is provided.
        # Mirrors the discovery pattern in context_seed_handlers.py.
        if contract_path is None:
            _default = Path(__file__).parent / "contracts" / "artisan-pipeline.contract.yaml"
            if _default.exists():
                contract_path = _default
        self._contract_path = contract_path
        self._logger = get_logger(__name__)

        # Checkpoint store selection
        if checkpoint_store is not None:
            self.checkpoint_store = checkpoint_store
        elif self.config.checkpoint_dir:
            self.checkpoint_store = JsonFileCheckpointStore(self.config.checkpoint_dir)
        else:
            self.checkpoint_store = InMemoryCheckpointStore()

        # Error store — writes to .startd8/task_errors/ under project_root
        self._error_store: Optional[Any] = None  # Lazy init on first error

        # One-shot guard: emit budget-approaching warning at most once.
        self._budget_warning_emitted: bool = False

        self._tracer: Optional[Any] = None
        # REQ-PAQ-603: runtime gate traceability.
        self._quality_gate_outcomes: list[dict[str, Any]] = []
        self._quality_gate_violations: list[dict[str, Any]] = []
        self._active_workflow_context: Optional[dict[str, Any]] = None

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

    # Sentinel indicating error store init was attempted and failed.
    _ERROR_STORE_UNAVAILABLE = object()

    @property
    def error_store(self) -> Any:
        """Lazy-initialised :class:`TaskErrorStore` for persisting errors."""
        if self._error_store is None:
            try:
                from startd8.storage.error_store import TaskErrorStore

                project_root = self.config.project_root or str(Path.cwd())
                self._error_store = TaskErrorStore(project_root=project_root)
            except Exception as exc:
                self._logger.warning(
                    "TaskErrorStore unavailable: %s — errors will not be "
                    "persisted to disk",
                    exc,
                )
                self._error_store = self._ERROR_STORE_UNAVAILABLE
        if self._error_store is self._ERROR_STORE_UNAVAILABLE:
            return None
        return self._error_store

    def _record_error(
        self,
        source: str,
        error_message: str,
        *,
        exception: Optional[Exception] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        """Best-effort error recording — never raises.

        Skipped when ``dry_run=True`` to prevent test executions from
        polluting the production error store.
        """
        if self.config.dry_run:
            return
        try:
            store = self.error_store
            if store is None:
                return
            ctx: dict[str, Any] = extra or {}
            store.record_error(
                workflow_id=self.config.workflow_id,
                source=source,
                error_message=error_message,
                context=ctx,
                exception=exception,
            )
        except Exception:
            self._logger.debug(
                "Failed to persist error record", exc_info=True,
            )

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
        self._active_workflow_context = context
        self._quality_gate_outcomes = []
        self._quality_gate_violations = []

        # Inject workflow_id so phase handlers can reference it
        context.setdefault("workflow_id", self.config.workflow_id)

        # Inject model assignments so phase handlers can look them up
        context.setdefault("drafter_model", self.config.drafter_model)
        context.setdefault("validator_model", self.config.validator_model)
        context.setdefault("reviewer_model", self.config.reviewer_model)

        # Inject project_root for domain-aware checklist
        if self.config.project_root:
            context.setdefault("project_root", self.config.project_root)
        else:
            context.setdefault("project_root", str(Path.cwd()))
        # REQ-PAQ-603: centralized gate traceability context envelope.
        context.setdefault("quality_gate_outcomes", [])
        context.setdefault(
            "quality_gate_summary",
            {
                "policy_mode": self._quality_gate,
                "gate_count": 0,
                "violation_count": 0,
                "violations": [],
            },
        )

        # Phase 4: Load ManifestRegistry from cache (never blocking)
        try:
            from startd8.utils.manifest_registry import ManifestRegistry
            registry = ManifestRegistry.from_cache(Path(context["project_root"]))
            context["project_manifests"] = registry
            if registry:
                logger.info(
                    "manifest.load",
                    extra={"files": len(registry.files()), "surface": "artisan_contractor"},
                )
            else:
                logger.info(
                    "manifest.fallback",
                    extra={"surface": "artisan_contractor", "reason": "cache_miss"},
                )
        except Exception as exc:
            context["project_manifests"] = None
            logger.info(
                "manifest.fallback",
                extra={"surface": "artisan_contractor", "reason": "load_error",
                       "error": str(exc)},
            )

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
            # Include feature-serial resume coordinates when present so users can
            # quickly see exactly where execution will restart.
            if (
                loaded_checkpoint.current_feature is not None
                or loaded_checkpoint.current_feature_phase is not None
            ):
                self._logger.info(
                    "Resuming workflow %s from checkpoint "
                    "(after phase %s, feature=%s, inner_phase=%s, completed_features=%d)",
                    config.workflow_id,
                    resumed_from_value,
                    loaded_checkpoint.current_feature,
                    loaded_checkpoint.current_feature_phase,
                    len(loaded_checkpoint.completed_features),
                )
            else:
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

        # Emit telemetry status banner
        try:
            from startd8.otel import get_otel_runtime_state, format_telemetry_banner
            _telem_state = get_otel_runtime_state()
            self._logger.info(format_telemetry_banner(_telem_state))
        except Exception:
            self._logger.debug("Telemetry banner unavailable", exc_info=True)

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
                # All execution now defaults to feature-serial mode
                final_status = self._execute_workflow(
                    context=context,
                    phase_results=phase_results,
                    cost_tracker=cost_tracker,
                    workflow_start=workflow_start,
                    start_index=start_index,
                    loaded_checkpoint=loaded_checkpoint,
                )

                if final_status == WorkflowStatus.COMPLETED:
                    # Clean up checkpoint on successful completion
                    self.checkpoint_store.delete(config.workflow_id)
                    self._logger.info(
                        "Workflow %s completed successfully", config.workflow_id
                    )

            except (
                WorkflowTimeoutError,
                CostBudgetExceededError,
                PhaseExecutionError,
            ) as known_err:
                if HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                    root_span.set_status(Status(StatusCode.ERROR))
                self._record_error(
                    source=getattr(known_err, "phase", WorkflowPhase.PLAN).value
                    if isinstance(known_err, PhaseExecutionError)
                    else "workflow",
                    error_message=str(known_err),
                    exception=known_err,
                    extra={"cost": cost_tracker.cumulative_cost},
                )
                raise

            except Exception as err:
                final_status = WorkflowStatus.FAILED
                self._logger.exception(
                    "Workflow %s failed with unexpected error", config.workflow_id
                )
                if HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                    root_span.record_exception(err)
                    root_span.set_status(Status(StatusCode.ERROR))
                self._record_error(
                    source="workflow",
                    error_message=str(err),
                    exception=err,
                    extra={"cost": cost_tracker.cumulative_cost},
                )
                raise

            finally:
                workflow_end = time.monotonic()
                workflow_end_iso = datetime.now(timezone.utc).isoformat()
                total_duration = workflow_end - workflow_start
                self._active_workflow_context = None

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

        result_metadata = copy.deepcopy(config.metadata)
        result_metadata["quality_gate"] = {
            "policy_mode": self._quality_gate,
            "gate_count": len(self._quality_gate_outcomes),
            "violation_count": len(self._quality_gate_violations),
            "violations": list(self._quality_gate_violations),
            "outcomes": list(self._quality_gate_outcomes),
        }

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
            metadata=result_metadata,
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

        For phase-serial mode:
            Uses ``last_completed_phase`` to skip already-completed phases.

        For feature-serial mode:
            Uses ``last_completed_phase`` for global phases (PLAN, SCAFFOLD,
            FINALIZE) and ``completed_features`` for feature-level resume.
            Feature-level resume is handled in ``_execute_feature_serial_loop()``.

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
            # Checkpoint exists but no last_completed_phase — may be v2 with
            # feature-serial state. Return checkpoint so callers can inspect
            # completed_features.
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

    def _commit_changes(
        self,
        phase: WorkflowPhase,
        feature_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Commit changes to git after the FINALIZE phase completes.

        Only commits once per feature/task at the end of the pipeline
        (FINALIZE phase), not at every intermediate phase boundary.
        Intermediate state is preserved by the checkpoint system.
        """
        if self.config.dry_run:
            return

        # Only commit after FINALIZE — intermediate phases use checkpoints
        if phase != WorkflowPhase.FINALIZE:
            return

        # Respect --no-auto-commit (propagated via context)
        ctx = context or {}
        if ctx.get("auto_commit") is False:
            self._logger.info("Auto-commit disabled (--no-auto-commit)")
            return

        # Do not commit if any task failed review.
        # review_results structure: {"per_task": {"PI-005": {"passed": True}}, ...}
        review_results = ctx.get("review_results", {})
        per_task = review_results.get("per_task", {}) if isinstance(review_results, dict) else {}
        if per_task:
            any_failed = any(
                not entry.get("passed", False)
                for entry in per_task.values()
                if isinstance(entry, dict)
            )
            if any_failed:
                self._logger.warning(
                    "Skipping auto-commit: one or more tasks failed review"
                )
                return

        project_root = Path(self.config.project_root or ".")

        # Only commit if we are in a git repo
        if not (project_root / ".git").exists():
            return

        try:
            # Check for changes
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                check=True,
            )

            if not status.stdout.strip():
                return  # No changes to commit

            # Add all changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(project_root),
                check=True,
                capture_output=True,
                text=True,
            )

            # Build a meaningful per-feature commit message from context
            msg = self._build_commit_message(feature_id, context)

            # Commit
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=str(project_root),
                check=True,
                capture_output=True,
                text=True,
            )
            self._logger.info(
                "Committed changes for phase %s%s",
                phase.value,
                f" (feature {feature_id})" if feature_id else "",
            )

        except Exception as e:  # Covers CalledProcessError, FileNotFoundError, etc.
            # Construct a clear error message
            if isinstance(e, subprocess.CalledProcessError):
                stderr = e.stderr
                if isinstance(stderr, bytes):
                    stderr = stderr.decode()
                stderr = stderr.strip() if stderr else ""

                stdout = e.stdout
                if isinstance(stdout, bytes):
                    stdout = stdout.decode()
                stdout = stdout.strip() if stdout else ""

                error_msg = f"Git commit failed (exit code {e.returncode}):\nSTDOUT: {stdout}\nSTDERR: {stderr}"
            elif isinstance(e, FileNotFoundError):
                error_msg = "Git executable not found."
            else:
                error_msg = f"Unexpected error during git commit: {e}"

            self._logger.error(error_msg)

            # If interactive, prompt the user whether to continue
            if sys.stdin.isatty():
                try:
                    should_continue = questionary.confirm(
                        "Git commit failed. Do you want to continue the workflow anyway?",
                        default=False
                    ).ask()

                    if not should_continue:
                        raise WorkflowError(
                            "Workflow aborted by user after git commit failure."
                        ) from e

                    self._logger.info("User chose to continue despite git commit failure.")
                    return
                except Exception as prompt_err:
                    self._logger.warning(
                        "Could not prompt user: %s. Continuing workflow.", prompt_err
                    )
            else:
                self._logger.warning(
                    "Non-interactive session: continuing workflow despite git failure."
                )

    def _build_commit_message(
        self,
        feature_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """Build a descriptive commit message from task context.

        Format: ``feat(<task_id>): <title>``  with review score in body.
        Falls back to generic message if context is unavailable.
        """
        ctx = context or {}
        tasks = ctx.get("tasks") or []

        # Find the task matching this feature/filter
        task_id = feature_id
        if not task_id:
            _filter = ctx.get("task_filter")
            if isinstance(_filter, list) and len(_filter) == 1:
                task_id = _filter[0]
            elif isinstance(_filter, str):
                task_id = _filter
        task_title = ""
        if task_id and tasks:
            for t in tasks:
                tid = getattr(t, "task_id", None) or (t.get("task_id") if isinstance(t, dict) else None)
                if tid == task_id:
                    task_title = getattr(t, "title", None) or (t.get("title", "") if isinstance(t, dict) else "")
                    break

        # If single-task run with no feature_id, use the first (only) task
        if not task_id and len(tasks) == 1:
            t = tasks[0]
            task_id = getattr(t, "task_id", None) or (t.get("task_id") if isinstance(t, dict) else None)
            task_title = getattr(t, "title", None) or (t.get("title", "") if isinstance(t, dict) else "")

        if task_id and task_title:
            return f"feat({task_id}): {task_title}"
        elif task_id:
            return f"feat({task_id}): Artisan pipeline completed"
        else:
            return "feat: Artisan pipeline completed"

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
        workflow_id = context.get("workflow_id") or self.config.workflow_id

        while attempt <= max_retries:
            phase_start = time.monotonic()
            phase_start_iso = datetime.now(timezone.utc).isoformat()
            phase_success = False
            phase_outcome = PhaseStatus.FAILED.value
            phase_duration_ms: Optional[int] = None

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
                    self._logger.info(
                        "Starting phase: %s",
                        phase.value,
                        extra={
                            "phase": phase.value,
                            "workflow_id": workflow_id,
                            "attempt": attempt + 1,
                        },
                    )
                    # --- Context contract: entry validation ---
                    # validate_phase_boundary runs legacy validation
                    # internally, then contract entry + enrichment when
                    # a contract_path is configured.
                    with self.tracer.start_as_current_span(
                        "gate.entry",
                        attributes={"gate.phase": phase.value},
                    ) as gate_entry_span:
                        entry_result = validate_phase_boundary(
                            phase, context, "entry", self._contract_path
                        )
                        if entry_result:
                            _entry_propagation_status = (
                                entry_result.propagation_status.value
                                if hasattr(entry_result, "propagation_status")
                                else "unknown"
                            )
                            _entry_violations = list(
                                getattr(entry_result, "blocking_failures", []) or []
                            )
                            _entry_extra = {
                                "phase": phase.value,
                                "passed": entry_result.passed,
                                "gate.phase": phase.value,
                                "gate.entry.passed": entry_result.passed,
                                "gate.propagation_status": _entry_propagation_status,
                                "gate.violations": _entry_violations,
                            }
                            if entry_result.passed:
                                self._logger.info(
                                    "gate.entry.passed=true phase=%s",
                                    phase.value,
                                    extra=_entry_extra,
                                )
                            else:
                                self._logger.warning(
                                    "gate.entry.passed=false phase=%s violations=%s",
                                    phase.value,
                                    _entry_violations,
                                    extra=_entry_extra,
                                )
                            gate_entry_span.set_attribute(
                                "gate.passed", entry_result.passed
                            )
                            gate_entry_span.set_attribute(
                                "gate.propagation_status",
                                _entry_propagation_status,
                            )
                            try:
                                from contextcore.contracts.propagation.otel import (
                                    emit_boundary_result,
                                )
                                emit_boundary_result(entry_result)
                            except ImportError:
                                pass
                            if not entry_result.passed:
                                raise PhaseContextError(
                                    f"{phase.value.upper()} contract entry "
                                    f"validation failed: "
                                    f"{entry_result.blocking_failures}",
                                    phase=phase.value,
                                    missing_keys=entry_result.blocking_failures,
                                    direction="entry",
                                )

                    # OT-710: Store boundary result for forensic logging
                    from startd8.contractors.forensic_log import (
                        set_boundary_result as _set_br,
                        reset_boundary_result as _reset_br,
                    )
                    handler._last_entry_boundary_result = entry_result
                    _br_token = _set_br(entry_result)
                    try:
                        result_dict = self._run_handler_with_timeout(
                            handler, phase, context, effective_timeout
                        )
                    finally:
                        _reset_br(_br_token)

                    # --- Context contract: exit validation ---
                    # validate_phase_boundary runs legacy validation
                    # internally, then contract exit when configured.
                    with self.tracer.start_as_current_span(
                        "gate.exit",
                        attributes={"gate.phase": phase.value},
                    ) as gate_exit_span:
                        exit_result = validate_phase_boundary(
                            phase, context, "exit", self._contract_path
                        )
                        if exit_result:
                            _exit_propagation_status = (
                                exit_result.propagation_status.value
                                if hasattr(exit_result, "propagation_status")
                                else "unknown"
                            )
                            _exit_violations = list(
                                getattr(exit_result, "blocking_failures", []) or []
                            )
                            _exit_extra = {
                                "phase": phase.value,
                                "passed": exit_result.passed,
                                "gate.phase": phase.value,
                                "gate.exit.passed": exit_result.passed,
                                "gate.propagation_status": _exit_propagation_status,
                                "gate.violations": _exit_violations,
                            }
                            if exit_result.passed:
                                self._logger.info(
                                    "gate.exit.passed=true phase=%s",
                                    phase.value,
                                    extra=_exit_extra,
                                )
                            else:
                                self._logger.warning(
                                    "gate.exit.passed=false phase=%s violations=%s",
                                    phase.value,
                                    _exit_violations,
                                    extra=_exit_extra,
                                )
                            gate_exit_span.set_attribute(
                                "gate.passed", exit_result.passed
                            )
                            gate_exit_span.set_attribute(
                                "gate.propagation_status",
                                _exit_propagation_status,
                            )
                            try:
                                from contextcore.contracts.propagation.otel import (
                                    emit_boundary_result,
                                )
                                emit_boundary_result(exit_result)
                            except ImportError:
                                pass

                    phase_end = time.monotonic()
                    duration = phase_end - phase_start

                    status = (
                        PhaseStatus.DRY_RUN
                        if config.dry_run
                        else PhaseStatus.COMPLETED
                    )
                    phase_success = True
                    phase_outcome = status.value
                    raw_cost = result_dict.get("cost")
                    try:
                        cost = float(raw_cost) if raw_cost is not None else 0.0
                    except (TypeError, ValueError):
                        self._logger.warning(
                            "Phase %s returned non-numeric cost %r, treating as 0.0",
                            phase.value, raw_cost,
                        )
                        cost = 0.0
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
                    phase_duration_ms = int(duration * 1000)
                    phase_outcome = PhaseStatus.TIMED_OUT.value

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

                    timeout_msg = f"Phase timed out after {effective_timeout}s"
                    self._record_error(
                        source=phase.value,
                        error_message=timeout_msg,
                        extra={"attempt": attempt, "duration_seconds": duration},
                    )

                    return PhaseResult(
                        phase=phase,
                        status=PhaseStatus.TIMED_OUT,
                        start_time=phase_start_iso,
                        end_time=datetime.now(timezone.utc).isoformat(),
                        duration_seconds=duration,
                        error_message=timeout_msg,
                        retry_count=attempt,
                    )

                except Exception as err:
                    phase_end = time.monotonic()
                    duration = phase_end - phase_start
                    phase_duration_ms = int(duration * 1000)
                    last_error = err

                    if HAS_OTEL and not isinstance(span, _NoOpSpan):
                        span.record_exception(err)
                        span.set_attribute(
                            "phase.status", PhaseStatus.FAILED.value
                        )
                        span.set_status(Status(StatusCode.ERROR, str(err)))

                    if attempt < max_retries:
                        phase_outcome = "retrying"
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
                    phase_outcome = PhaseStatus.FAILED.value

                    self._record_error(
                        source=phase.value,
                        error_message=str(err),
                        exception=err,
                        extra={
                            "attempt": attempt + 1,
                            "duration_seconds": duration,
                        },
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
                finally:
                    if phase_duration_ms is None:
                        phase_duration_ms = int((time.monotonic() - phase_start) * 1000)
                    self._logger.info(
                        "Finished phase: %s (%s)",
                        phase.value,
                        "success" if phase_success else "failure",
                        extra={
                            "phase": phase.value,
                            "success": phase_success,
                            "duration_ms": phase_duration_ms,
                            "workflow_id": workflow_id,
                            "status": phase_outcome,
                            "attempt": attempt + 1,
                        },
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

        # OT-103/OT-104: Propagate OTel context + boundary result to worker thread
        parent_ctx = capture_context()
        from startd8.contractors.forensic_log import (
            get_boundary_result as _get_br,
            set_boundary_result as _set_br,
            reset_boundary_result as _reset_br,
        )
        parent_br = _get_br()

        def _handler_with_context() -> dict[str, Any]:
            token = attach_context(parent_ctx)
            br_token = _set_br(parent_br)
            try:
                return handler.execute(phase, context, dry_run=self.config.dry_run)
            finally:
                _reset_br(br_token)
                detach_context(token)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_handler_with_context)
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
        *,
        completed_features: Optional[list[str]] = None,
        current_feature: Optional[str] = None,
        current_feature_phase: Optional[str] = None,
        feature_partial_results: Optional[dict[str, dict[str, Any]]] = None,
    ) -> WorkflowCheckpoint:
        """Build and save a checkpoint, returning it for attachment to errors.

        Args:
            last_completed_phase: The last global phase that completed successfully.
            phase_results: List of phase results so far.
            cumulative_cost: Total cost accumulated.
            status: Current workflow status.
            context: Optional workflow context dict for snapshotting.
            completed_features: List of feature IDs that completed all inner phases.
            current_feature: Feature ID currently being processed (if any).
            current_feature_phase: Inner phase for current feature (DESIGN/IMPLEMENT/INTEGRATE/TEST/REVIEW).
            feature_partial_results: Partial results for features that failed mid-execution.

        Returns:
            The persisted WorkflowCheckpoint.
        """
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
                    self._logger.debug(
                        "Checkpoint context key %r not serializable, skipping", key,
                    )

            # PCA-202: truncate plan_document_text to prevent checkpoint bloat.
            pdt = snapshot.get("plan_document_text")
            if isinstance(pdt, str) and len(pdt) > _PLAN_DOC_CHECKPOINT_MAX_CHARS:
                snapshot["plan_document_text"] = (
                    pdt[:_PLAN_DOC_CHECKPOINT_MAX_CHARS]
                    + _PLAN_DOC_TRUNCATION_MARKER
                )
                snapshot["_plan_doc_truncated"] = True

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
            # Feature-serial fields (v2+)
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            completed_features=completed_features or [],
            current_feature=current_feature,
            current_feature_phase=current_feature_phase,
            feature_partial_results=feature_partial_results or {},        )
        try:
            self.checkpoint_store.save(checkpoint)
        except (OSError, TypeError, ValueError):
            self._logger.error(
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

    # ------------------------------------------------------------------
    # Execution mode methods
    # ------------------------------------------------------------------


    def _execute_global_phase(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        phase_results: list[PhaseResult],
        cost_tracker: "_CostTracker",
        workflow_start: float,
        mode_label: str,
        **extra_checkpoint_kwargs: Any,
    ) -> None:
        """Execute a single global phase with timeout, checkpoint, and error handling.

        This is the shared implementation for global phases (PLAN, SCAFFOLD,
        FINALIZE) across all execution modes. It handles:
        1. Timeout check before execution
        2. Phase execution and result recording
        3. Checkpoint persistence after completion
        4. Raising PhaseExecutionError / WorkflowTimeoutError on failure

        Args:
            phase: The global phase to execute.
            context: Shared mutable context dict.
            phase_results: List to append the phase result to.
            cost_tracker: Cost accumulator for budget enforcement.
            workflow_start: Monotonic time when workflow started.
            mode_label: Log prefix for the execution mode (e.g. "Feature-serial").
            **extra_checkpoint_kwargs: Additional kwargs passed to _persist_checkpoint
                (e.g. completed_features, lane_assignments, wave state).

        Raises:
            WorkflowTimeoutError: If timeout expires before or during execution.
            PhaseExecutionError: If the phase fails.
        """
        config = self.config
        phase_idx = self.phases.index(phase)

        elapsed = time.monotonic() - workflow_start
        if config.total_timeout_seconds is not None:
            remaining = config.total_timeout_seconds - elapsed
            if remaining <= 0:
                checkpoint = self._persist_checkpoint(
                    self.phases[phase_idx - 1] if phase_idx > 0 else None,
                    phase_results,
                    cost_tracker.cumulative_cost,
                    WorkflowStatus.TIMED_OUT,
                    context=context,
                    **extra_checkpoint_kwargs,
                )
                raise WorkflowTimeoutError(
                    f"Timeout before global phase {phase.value}",
                    checkpoint=checkpoint,
                )
        else:
            remaining = None

        self._logger.info("%s: executing global phase %s", mode_label, phase.value)

        phase_result = self._execute_phase(phase, context, remaining)
        phase_results.append(phase_result)
        cost_tracker.add(phase_result.cost)

        if phase_result.status == PhaseStatus.COMPLETED:
            self._commit_changes(phase, context=context)

        # Persist checkpoint after global phase
        self._persist_checkpoint(
            phase,
            phase_results,
            cost_tracker.cumulative_cost,
            WorkflowStatus.IN_PROGRESS,
            context=context,
            **extra_checkpoint_kwargs,
        )

        if phase_result.status == PhaseStatus.FAILED:
            checkpoint = self._persist_checkpoint(
                phase,
                phase_results,
                cost_tracker.cumulative_cost,
                WorkflowStatus.FAILED,
                context=context,
                **extra_checkpoint_kwargs,
            )
            raise PhaseExecutionError(
                f"Global phase {phase.value} failed: {phase_result.error_message}",
                phase=phase,
                checkpoint=checkpoint,
            )

        if phase_result.status == PhaseStatus.TIMED_OUT:
            checkpoint = self._persist_checkpoint(
                phase,
                phase_results,
                cost_tracker.cumulative_cost,
                WorkflowStatus.TIMED_OUT,
                context=context,
                **extra_checkpoint_kwargs,
            )
            raise WorkflowTimeoutError(
                f"Global phase {phase.value} timed out",
                checkpoint=checkpoint,
            )

    def _check_quality_gate(
        self,
        phase: WorkflowPhase,
        phase_result: "PhaseResult",
    ) -> None:
        """Check quality gate after DESIGN, TEST, or REVIEW phases.

        Compares ``total_failed`` in the phase output dict against zero.
        Behavior depends on ``self._quality_gate``:

        * ``"skip"`` — no-op.
        * ``"warn"`` — log WARNING with details.
        * ``"block"`` — raise :class:`QualityGateError`.

        Args:
            phase: The workflow phase that just completed.
            phase_result: Result from the completed phase.

        Raises:
            QualityGateError: When ``quality_gate == "block"`` and failures
                              are detected.
        """
        if phase not in (WorkflowPhase.DESIGN, WorkflowPhase.TEST, WorkflowPhase.REVIEW):
            return

        signal_map = {
            WorkflowPhase.DESIGN: "design_quality.total_failed",
            WorkflowPhase.TEST: "test_results.total_failed",
            WorkflowPhase.REVIEW: "review_results.total_failed",
        }

        if not phase_result.output or not isinstance(phase_result.output, dict):
            outcome = {
                "gate_id": f"artisan.{phase.value}.quality",
                "contract_signal_id": signal_map[phase],
                "phase": phase.value,
                "policy_mode": self._quality_gate,
                "threshold": {"metric": "total_failed", "operator": "eq", "value": 0},
                "observed_value": None,
                "decision": "unevaluated",
                "violated": False,
                "details": {"reason": "missing_or_non_dict_output"},
            }
            self._record_quality_gate_outcome(outcome)
            return

        total_failed = int(phase_result.output.get("total_failed", 0) or 0)
        details: dict[str, Any] = {
            "total_failed": total_failed,
            "total_passed": int(phase_result.output.get("total_passed", 0) or 0),
        }

        if phase == WorkflowPhase.DESIGN:
            per_task = phase_result.output.get("per_task", {})
            failed_designs = [
                tid for tid, info in per_task.items() if not info.get("passed")
            ]
            details["failed_designs"] = failed_designs
            details["agreement_rate"] = phase_result.output.get("agreement_rate", 0.0)
            msg = f"DESIGN quality gate: {total_failed} task(s) failed design quality"
        elif phase == WorkflowPhase.TEST:
            per_task = phase_result.output.get("per_task", {})
            failed_tasks = [
                tid for tid, info in per_task.items() if not info.get("passed")
            ]
            details["failed_tasks"] = failed_tasks
            msg = f"TEST quality gate: {total_failed} task(s) failed validation"
        else:
            per_task = phase_result.output.get("per_task", {})
            failed_reviews = {
                tid: info.get("score", "?")
                for tid, info in per_task.items()
                if not info.get("passed")
            }
            details["failed_reviews"] = failed_reviews
            msg = f"REVIEW quality gate: {total_failed} task(s) failed review"

        if self._quality_gate == "skip":
            decision = "skipped"
        elif total_failed == 0:
            decision = "pass"
        elif self._quality_gate == "block":
            decision = "block"
        else:
            decision = "warn"

        outcome = {
            "gate_id": f"artisan.{phase.value}.quality",
            "contract_signal_id": signal_map[phase],
            "phase": phase.value,
            "policy_mode": self._quality_gate,
            "threshold": {"metric": "total_failed", "operator": "eq", "value": 0},
            "observed_value": total_failed,
            "decision": decision,
            "violated": total_failed > 0,
            "message": msg,
            "details": details,
        }
        self._record_quality_gate_outcome(outcome)

        if self._quality_gate == "skip" or total_failed == 0:
            return

        if self._quality_gate == "block":
            self._logger.error("QUALITY GATE BLOCKED: %s", msg)
            raise QualityGateError(msg, phase=phase, details=details)
        self._logger.warning("QUALITY GATE WARNING: %s — %s", msg, details)

    def _record_quality_gate_outcome(self, outcome: dict[str, Any]) -> None:
        """Store quality gate outcomes for workflow/finalize traceability."""
        self._quality_gate_outcomes.append(outcome)
        if outcome.get("violated"):
            self._quality_gate_violations.append(outcome)

        if self._active_workflow_context is not None:
            ctx_outcomes = self._active_workflow_context.setdefault(
                "quality_gate_outcomes", []
            )
            if isinstance(ctx_outcomes, list):
                ctx_outcomes.append(outcome)
            self._active_workflow_context["quality_gate_summary"] = {
                "policy_mode": self._quality_gate,
                "gate_count": len(self._quality_gate_outcomes),
                "violation_count": len(self._quality_gate_violations),
                "violations": list(self._quality_gate_violations),
            }

        try:
            from startd8.contractors.forensic_log import emit_quality_gate_log

            emit_quality_gate_log(
                gate_id=str(outcome.get("gate_id")),
                phase=str(outcome.get("phase")),
                policy_mode=str(outcome.get("policy_mode")),
                threshold=outcome.get("threshold"),
                observed_value=outcome.get("observed_value"),
                decision=str(outcome.get("decision")),
                violated=bool(outcome.get("violated")),
                contract_signal_id=str(outcome.get("contract_signal_id")),
                details=outcome.get("details", {}),
            )
        except Exception:
            self._logger.debug("quality gate forensic emission failed", exc_info=True)


    def _execute_workflow(
        self,
        context: dict[str, Any],
        phase_results: list[PhaseResult],
        cost_tracker: "_CostTracker",
        workflow_start: float,
        start_index: int,
        loaded_checkpoint: Optional[WorkflowCheckpoint],
    ) -> WorkflowStatus:
        """Execute phases in feature-serial order.

        Each feature completes DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW
        before the next feature begins. PLAN and SCAFFOLD run globally first;
        FINALIZE runs globally at the end.

        Args:
            context: Shared mutable context dict.
            phase_results: List to append phase results to.
            cost_tracker: Cost accumulator for budget enforcement.
            workflow_start: Monotonic time when workflow started (for timeout).
            start_index: Phase index to start from (for resume).
            loaded_checkpoint: Optional checkpoint with feature-serial state.

        Returns:
            Final WorkflowStatus.

        Raises:
            WorkflowTimeoutError: If timeout exceeded.
            CostBudgetExceededError: If budget exceeded.
            PhaseExecutionError: If a phase fails.
        """
        config = self.config
        
        # Determine which global phases to skip based on checkpoint
        last_global_phase_idx = -1
        if loaded_checkpoint and loaded_checkpoint.last_completed_phase:
            for idx, phase in enumerate(self.phases):
                if phase.value == loaded_checkpoint.last_completed_phase:
                    last_global_phase_idx = idx
                    break

        # Execute global start phases (PLAN, SCAFFOLD)
        _fs_checkpoint_kwargs = dict(
            current_feature=None, current_feature_phase=None,
        )
        for phase in self.GLOBAL_START_PHASES:
            if phase not in self.phases:
                continue

            phase_idx = self.phases.index(phase)

            # Skip if already completed (from checkpoint)
            if phase_idx <= last_global_phase_idx:
                self._logger.debug(
                    "Feature-serial: skipping already-completed global phase %s",
                    phase.value,
                )
                continue

            self._execute_global_phase(
                phase, context, phase_results, cost_tracker,
                workflow_start, "Feature-serial",
                **_fs_checkpoint_kwargs,
            )

        # Execute feature-serial inner loop
        (
            feature_status,
            completed_features,
            feature_partial_results,
            current_feature,
            current_feature_phase,
        ) = (
            self._execute_inner_loop(
                context=context,
                phase_results=phase_results,
                cost_tracker=cost_tracker,
                workflow_start=workflow_start,
                loaded_checkpoint=loaded_checkpoint,
            )
        )

        # If feature loop failed, persist checkpoint and raise
        if feature_status != WorkflowStatus.COMPLETED:
            last_global = (
                self.GLOBAL_START_PHASES[-1]
                if self.GLOBAL_START_PHASES[-1] in self.phases
                else None
            )
            checkpoint = self._persist_checkpoint(
                last_global,
                phase_results,
                cost_tracker.cumulative_cost,
                feature_status,
                context=context,
                completed_features=completed_features,
                current_feature=current_feature,
                current_feature_phase=current_feature_phase,
                feature_partial_results=feature_partial_results,
            )
            if feature_status == WorkflowStatus.FAILED:
                raise PhaseExecutionError(
                    f"Feature-serial execution failed after {len(completed_features)} features",
                    phase=WorkflowPhase.IMPLEMENT,  # Approximate
                    checkpoint=checkpoint,
                )
            if feature_status == WorkflowStatus.TIMED_OUT:
                raise WorkflowTimeoutError(
                    "Feature-serial execution timed out",
                    checkpoint=checkpoint,
                )
            if feature_status == WorkflowStatus.BUDGET_EXCEEDED:
                assert config.cost_budget is not None  # for type checker
                raise CostBudgetExceededError(
                    "Feature-serial execution exceeded cost budget: "
                    f"{cost_tracker.cumulative_cost:.4f} > {config.cost_budget:.4f}",
                    checkpoint=checkpoint,
                )

        # Execute global end phases (FINALIZE)
        _fs_end_kwargs = dict(
            completed_features=completed_features,
            current_feature=None,
            current_feature_phase=None,
            feature_partial_results=feature_partial_results,
        )
        for phase in self.GLOBAL_END_PHASES:
            if phase not in self.phases:
                continue

            self._execute_global_phase(
                phase, context, phase_results, cost_tracker,
                workflow_start, "Feature-serial",
                **_fs_end_kwargs,
            )

        return WorkflowStatus.COMPLETED

    # ------------------------------------------------------------------
    # Lane-parallel execution
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Wave+Lane parallel execution
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Feature-serial execution helpers
    # ------------------------------------------------------------------

    # Inner phases executed per-feature in feature-serial and wave modes.
    # PLAN and SCAFFOLD run once globally; FINALIZE runs once at the end.
    INNER_PHASES: tuple[WorkflowPhase, ...] = (
        WorkflowPhase.DESIGN,
        WorkflowPhase.IMPLEMENT,
        WorkflowPhase.INTEGRATE,
        WorkflowPhase.TEST,
        WorkflowPhase.REVIEW,
    )
    RETRY_SOURCE_PHASES: tuple[WorkflowPhase, ...] = (
        WorkflowPhase.INTEGRATE,
        WorkflowPhase.TEST,
        WorkflowPhase.REVIEW,
    )

    # Global phases that run once at the start (before feature loop)
    GLOBAL_START_PHASES: tuple[WorkflowPhase, ...] = (
        WorkflowPhase.PLAN, WorkflowPhase.SCAFFOLD,
    )
    # Global phases that run once at the end (after feature loop)
    GLOBAL_END_PHASES: tuple[WorkflowPhase, ...] = (WorkflowPhase.FINALIZE,)

    def _execute_feature(
        self,
        feature_id: str,
        context: dict[str, Any],
        remaining_total_timeout: Optional[float],
        cost_tracker: "_CostTracker",
    ) -> tuple[bool, WorkflowStatus, dict[str, dict[str, Any]]]:
        """Execute all inner phases for a single feature.

        This is the core of feature-serial execution: each feature goes through
        DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW before the next feature begins.

        Args:
            feature_id: The task/feature ID to execute.
            context: Shared mutable context dict.
            remaining_total_timeout: Time budget remaining (or None for unlimited).
            cost_tracker: Cost accumulator for budget enforcement.

        Returns:
            Tuple of:
                - success: whether all inner phases completed
                - terminal_status: COMPLETED, FAILED, TIMED_OUT, or BUDGET_EXCEEDED
                - inner_results: per-inner-phase results
        """
        inner_results: dict[str, dict[str, Any]] = {}

        self._logger.info(
            "Feature-serial: starting feature %s (inner phases: %s)",
            feature_id,
            [p.value for p in self.INNER_PHASES],
        )

        # Filter context to just this feature for the inner loop
        # The handlers need to know which feature to process
        context["current_feature_id"] = feature_id
        max_regen_retries = max(0, int(self.config.max_retries_per_phase))
        regen_retry_count = 0
        phase_index = 0

        try:
            while phase_index < len(self.INNER_PHASES):
                inner_phase = self.INNER_PHASES[phase_index]
                phase_start = datetime.now(timezone.utc).isoformat()
                context["current_feature_phase"] = inner_phase.value

                self._logger.debug(
                    "Feature %s: executing inner phase %s",
                    feature_id,
                    inner_phase.value,
                )

                try:
                    phase_result = self._execute_phase(
                        inner_phase, context, remaining_total_timeout
                    )

                    if phase_result.status == PhaseStatus.COMPLETED:
                        self._commit_changes(inner_phase, feature_id=feature_id, context=context)

                    # Record the inner phase result
                    inner_results[inner_phase.value] = {
                        "status": phase_result.status.value,
                        "cost": phase_result.cost,
                        "timestamp": phase_start,
                        "error": phase_result.error_message,
                        "artifacts": phase_result.output or {},
                    }

                    # Track cost
                    cost_tracker.add(phase_result.cost)

                    # Quality gate check for design/test/review in
                    # feature-serial and wave-parallel modes.
                    gate_error: Optional[QualityGateError] = None
                    if inner_phase in (
                        WorkflowPhase.DESIGN,
                        WorkflowPhase.TEST,
                        WorkflowPhase.REVIEW,
                    ):
                        try:
                            self._check_quality_gate(inner_phase, phase_result)
                        except QualityGateError as exc:
                            gate_error = exc

                    # AR-153: bounded regenerate-with-feedback retries driven
                    # by INTEGRATE/TEST/REVIEW failures.
                    retry_feedback = self._build_regenerate_feedback(
                        feature_id=feature_id,
                        phase=inner_phase,
                        phase_result=phase_result,
                        gate_error=gate_error,
                    )
                    if retry_feedback is not None:
                        if regen_retry_count < max_regen_retries:
                            regen_retry_count += 1
                            retry_feedback["attempt"] = regen_retry_count
                            context["prior_error_feedback"] = retry_feedback[
                                "prior_error_feedback"
                            ]
                            context["retry_feedback"] = retry_feedback
                            context["_retry_attempt"] = regen_retry_count
                            self._append_retry_transcript(
                                context=context,
                                feature_id=feature_id,
                                transcript_entry={
                                    "attempt": regen_retry_count,
                                    "source_phase": inner_phase.value,
                                    "failed_tasks": retry_feedback.get("failed_tasks", []),
                                    "summary": retry_feedback.get("summary", ""),
                                    "outcome": "retrying",
                                },
                            )
                            self._logger.warning(
                                "Feature %s: AR-153 retry %d/%d triggered by %s failure",
                                feature_id,
                                regen_retry_count,
                                max_regen_retries,
                                inner_phase.value,
                            )
                            phase_index = self.INNER_PHASES.index(WorkflowPhase.IMPLEMENT)
                            continue

                        self._append_retry_transcript(
                            context=context,
                            feature_id=feature_id,
                            transcript_entry={
                                "attempt": regen_retry_count,
                                "source_phase": inner_phase.value,
                                "failed_tasks": retry_feedback.get("failed_tasks", []),
                                "summary": retry_feedback.get("summary", ""),
                                "outcome": "retry_budget_exhausted",
                            },
                        )
                        inner_results[inner_phase.value]["status"] = "failed"
                        inner_results[inner_phase.value]["retry_exhausted"] = True
                        inner_results[inner_phase.value]["error"] = retry_feedback.get(
                            "summary", phase_result.error_message or "quality failure"
                        )
                        return False, WorkflowStatus.FAILED, inner_results

                    # Check for phase failure
                    if phase_result.status == PhaseStatus.FAILED:
                        inner_results[inner_phase.value]["status"] = "failed"
                        self._logger.warning(
                            "Feature %s: inner phase %s failed: %s",
                            feature_id,
                            inner_phase.value,
                            phase_result.error_message,
                        )
                        return False, WorkflowStatus.FAILED, inner_results
                    if phase_result.status == PhaseStatus.TIMED_OUT:
                        inner_results[inner_phase.value]["status"] = "timed_out"
                        self._logger.warning(
                            "Feature %s: inner phase %s timed out: %s",
                            feature_id,
                            inner_phase.value,
                            phase_result.error_message,
                        )
                        return False, WorkflowStatus.TIMED_OUT, inner_results

                    # Check budget after each inner phase
                    if not cost_tracker.check_budget():
                        inner_results[inner_phase.value]["status"] = "budget_exceeded"
                        self._logger.warning(
                            "Feature %s: budget exceeded during inner phase %s",
                            feature_id,
                            inner_phase.value,
                        )
                        return False, WorkflowStatus.BUDGET_EXCEEDED, inner_results
                    phase_index += 1

                except Exception as err:
                    inner_results[inner_phase.value] = {
                        "status": "failed",
                        "cost": 0.0,  # Actual cost unknown -- phase may have incurred partial cost
                        "timestamp": phase_start,
                        "error": str(err),
                        "artifacts": {},
                    }
                    self._logger.exception(
                        "Feature %s: unexpected error in inner phase %s",
                        feature_id,
                        inner_phase.value,
                    )
                    return False, WorkflowStatus.FAILED, inner_results
        finally:
            # Avoid leaking feature-scoped context into subsequent global phases.
            context.pop("current_feature_id", None)
            context.pop("current_feature_phase", None)
            context.pop("_retry_attempt", None)
            context.pop("retry_feedback", None)

        # All inner phases succeeded
        self._logger.info(
            "Feature-serial: feature %s completed all inner phases successfully",
            feature_id,
        )
        return True, WorkflowStatus.COMPLETED, inner_results

    @staticmethod
    def _append_retry_transcript(
        context: dict[str, Any],
        feature_id: str,
        transcript_entry: dict[str, Any],
    ) -> None:
        """AR-153: persist retry transcript details for forensics/resume."""
        transcripts = context.setdefault("retry_transcripts", {})
        if not isinstance(transcripts, dict):
            transcripts = {}
            context["retry_transcripts"] = transcripts
        feature_entries = transcripts.setdefault(feature_id, [])
        if isinstance(feature_entries, list):
            feature_entries.append(transcript_entry)

    def _build_regenerate_feedback(
        self,
        feature_id: str,
        phase: WorkflowPhase,
        phase_result: PhaseResult,
        gate_error: Optional[QualityGateError] = None,
    ) -> Optional[dict[str, Any]]:
        """AR-153: normalize INTEGRATE/TEST/REVIEW failures into retry feedback."""
        if phase not in self.RETRY_SOURCE_PHASES:
            return None

        failed_tasks: list[str] = []
        details: dict[str, Any] = {}
        summary: Optional[str] = None

        if phase_result.status in (PhaseStatus.FAILED, PhaseStatus.TIMED_OUT):
            summary = (
                phase_result.error_message
                or f"{phase.value} phase did not complete successfully"
            )

        output = phase_result.output if isinstance(phase_result.output, dict) else {}
        if phase == WorkflowPhase.INTEGRATE:
            for task_id, task_result in output.items():
                if not isinstance(task_result, dict):
                    continue
                if task_result.get("success") is False:
                    failed_tasks.append(task_id)
            if failed_tasks:
                details["integration_failures"] = {
                    task_id: output.get(task_id) for task_id in failed_tasks
                }
                summary = summary or (
                    f"INTEGRATE failures for {len(failed_tasks)} task(s): "
                    + ", ".join(failed_tasks)
                )
        elif phase == WorkflowPhase.TEST:
            per_task = output.get("per_task", {})
            if isinstance(per_task, dict):
                for task_id, task_result in per_task.items():
                    if isinstance(task_result, dict) and task_result.get("passed") is False:
                        failed_tasks.append(task_id)
            total_failed = int(output.get("total_failed", 0) or 0)
            if total_failed > 0:
                details["total_failed"] = total_failed
                details["test_failures"] = {
                    task_id: per_task.get(task_id) for task_id in failed_tasks
                } if isinstance(per_task, dict) else {}
                summary = summary or (
                    f"TEST phase reported {total_failed} failed task(s)"
                )
        elif phase == WorkflowPhase.REVIEW:
            per_task = output.get("per_task", {})
            if isinstance(per_task, dict):
                for task_id, task_result in per_task.items():
                    if isinstance(task_result, dict) and task_result.get("passed") is False:
                        failed_tasks.append(task_id)
            total_failed = int(output.get("total_failed", 0) or 0)
            if total_failed > 0:
                details["total_failed"] = total_failed
                details["review_failures"] = {
                    task_id: per_task.get(task_id) for task_id in failed_tasks
                } if isinstance(per_task, dict) else {}
                summary = summary or (
                    f"REVIEW phase reported {total_failed} failed task(s)"
                )

        if gate_error is not None:
            details["quality_gate"] = {
                "phase": gate_error.phase.value,
                "details": gate_error.details,
            }
            summary = summary or str(gate_error)

        if summary is None:
            return None

        prior_error_feedback = (
            f"Feature: {feature_id}\n"
            f"Source phase: {phase.value}\n"
            f"Failure summary: {summary}\n"
            f"Failed tasks: {', '.join(failed_tasks) if failed_tasks else feature_id}\n"
            "Regenerate implementation and address these failures before proceeding."
        )
        return {
            "feature_id": feature_id,
            "source_phase": phase.value,
            "summary": summary,
            "failed_tasks": failed_tasks,
            "details": details,
            "prior_error_feedback": prior_error_feedback,
        }

    def _build_feature_partial_result(
        self,
        feature_id: str,
        inner_results: dict[str, dict[str, Any]],
        failure_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a serializable partial result for a failed feature.

        Args:
            feature_id: The feature that failed.
            inner_results: Results from inner phases that ran.
            failure_reason: Optional description of why the feature failed.

        Returns:
            Dict suitable for storage in feature_partial_results.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        partial = FeaturePartialResult(
            feature_id=feature_id,
            started_at=inner_results.get("design", {}).get("timestamp", now_iso),
            failed_at=now_iso,
            failure_reason=failure_reason,
            inner_phases=inner_results,
        )
        # Return as dict for JSON serialization
        return {
            "feature_id": partial.feature_id,
            "started_at": partial.started_at,
            "failed_at": partial.failed_at,
            "failure_reason": partial.failure_reason,
            "inner_phases": partial.inner_phases,
            "fitness_summary": partial.fitness_summary(),
        }

    def _execute_inner_loop(
        self,
        context: dict[str, Any],
        phase_results: list[PhaseResult],
        cost_tracker: "_CostTracker",
        workflow_start: float,
        loaded_checkpoint: Optional[WorkflowCheckpoint],
        *,
        lane_checkpoint_extras: Optional[dict[str, Any]] = None,
        checkpoint_lock: Optional[threading.Lock] = None,
    ) -> tuple[
        WorkflowStatus,
        list[str],
        dict[str, dict[str, Any]],
        Optional[str],
        Optional[str],
    ]:
        """Execute the feature-serial inner loop.

        This method orchestrates feature-serial execution where each feature
        completes DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW before the next feature
        begins. Global phases (PLAN, SCAFFOLD, FINALIZE) are handled by the
        caller.

        Args:
            context: Shared mutable context dict containing "tasks" list.
            phase_results: List to append synthetic phase results to.
            cost_tracker: Cost accumulator for budget enforcement.
            workflow_start: Monotonic time when workflow started (for timeout).
            loaded_checkpoint: Optional checkpoint with resume state.

        Returns:
            Tuple of:
                - final_status: WorkflowStatus (COMPLETED, FAILED, etc.)
                - completed_features: List of feature IDs that succeeded
                - feature_partial_results: Dict of partial results for failed features
                - current_feature: Feature ID currently in-progress at termination
                - current_feature_phase: Inner phase at termination (if known)
        """
        config = self.config
        completed_features: list[str] = []
        feature_partial_results: dict[str, dict[str, Any]] = {}
        current_feature: Optional[str] = None
        inner_results: dict[str, dict[str, Any]] = {}
        final_status = WorkflowStatus.IN_PROGRESS

        # Restore state from checkpoint if resuming
        if loaded_checkpoint:
            completed_features = list(loaded_checkpoint.completed_features)
            feature_partial_results = dict(loaded_checkpoint.feature_partial_results)
            self._logger.info(
                "Feature-serial: resuming with %d completed features",
                len(completed_features),
            )

        # Get ordered feature list from context
        tasks = context.get("tasks") or []
        if not tasks:
            self._logger.warning("Feature-serial: no tasks in context")
            return (
                WorkflowStatus.COMPLETED,
                completed_features,
                feature_partial_results,
                None,
                None,
            )

        # Build feature ID list (tasks are already topologically sorted by PLAN phase)
        feature_ids = [t.task_id for t in tasks]
        completed_set = set(completed_features)

        self._logger.info(
            "Feature-serial: executing %d features (%d already completed)",
            len(feature_ids),
            len(completed_features),
        )

        for feature_id in feature_ids:
            # Skip already-completed features (from checkpoint)
            if feature_id in completed_set:
                self._logger.debug(
                    "Feature-serial: skipping already-completed feature %s",
                    feature_id,
                )
                continue

            current_feature = feature_id

            # Check remaining total timeout
            elapsed = time.monotonic() - workflow_start
            if config.total_timeout_seconds is not None:
                remaining = config.total_timeout_seconds - elapsed
                if remaining <= 0:
                    self._logger.warning(
                        "Feature-serial: timeout before feature %s",
                        feature_id,
                    )
                    final_status = WorkflowStatus.TIMED_OUT
                    break
            else:
                remaining = None

            # Execute the feature's inner loop
            success, terminal_status, inner_results = self._execute_feature(
                feature_id, context, remaining, cost_tracker
            )

            if success:
                completed_features.append(feature_id)
                completed_set.add(feature_id)
                self._logger.info(
                    "Feature-serial: feature %s completed (%d/%d)",
                    feature_id,
                    len(completed_features),
                    len(feature_ids),
                )
            else:
                # Feature failed — persist partial results for inspection
                failure_reason = self._extract_failure_reason(inner_results)
                feature_partial_results[feature_id] = self._build_feature_partial_result(
                    feature_id, inner_results, failure_reason
                )

                self._logger.warning(
                    "Feature-serial: feature %s failed: %s",
                    feature_id,
                    failure_reason,
                )

                # Per user decision: restart failed feature from beginning
                # (partial results are preserved for inspection but discarded
                # for reuse by default)
                final_status = terminal_status
                current_feature = feature_id
                break

            # Persist checkpoint after each feature completes
            _extras = lane_checkpoint_extras or {}
            _ckpt_kwargs = dict(
                last_completed_phase=WorkflowPhase.SCAFFOLD,
                phase_results=phase_results,
                cumulative_cost=cost_tracker.cumulative_cost,
                status=WorkflowStatus.IN_PROGRESS,
                context=context,
                completed_features=completed_features,
                current_feature=None,
                current_feature_phase=None,
                feature_partial_results=feature_partial_results,
                **_extras,
            )
            if checkpoint_lock is not None:
                with checkpoint_lock:
                    self._persist_checkpoint(**_ckpt_kwargs)
            else:
                self._persist_checkpoint(**_ckpt_kwargs)

        # All features completed successfully
        if final_status == WorkflowStatus.IN_PROGRESS:
            final_status = WorkflowStatus.COMPLETED
            self._logger.info(
                "Feature-serial: all %d features completed successfully",
                len(completed_features),
            )

        current_feature_phase: Optional[str] = None
        if final_status != WorkflowStatus.COMPLETED and current_feature:
            current_feature_phase = self._extract_terminal_phase(inner_results)
        return (
            final_status,
            completed_features,
            feature_partial_results,
            current_feature,
            current_feature_phase,
        )

    @staticmethod
    def _extract_failure_reason(inner_results: dict[str, dict[str, Any]]) -> str:
        """Extract a human-readable failure reason from inner phase results."""
        for phase_name, result in inner_results.items():
            if result.get("status") == "failed":
                error = result.get("error", "Unknown error")
                return f"{phase_name} phase failed: {error}"
        return "Unknown failure"

    @staticmethod
    def _extract_terminal_phase(inner_results: dict[str, dict[str, Any]]) -> Optional[str]:
        """Return the inner phase where execution terminated."""
        for phase_name, result in inner_results.items():
            status = result.get("status")
            if status in {"failed", "timed_out", "budget_exceeded"}:
                return phase_name
        return None
