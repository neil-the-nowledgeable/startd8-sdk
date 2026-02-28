"""
Pydantic v2 context contract for the artisan workflow.

Defines per-phase output models, entry requirements, and validation
functions that enforce the context dict contract at every phase boundary.

See docs/design/STARTD8_AGENT_COMMUNICATION_DESIGN.md (Layer 3) for the
design rationale and docs/ARTISAN_REQUIREMENTS.md for per-phase context keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ..exceptions import Startd8Error
from startd8.logging_config import get_logger

_logger = get_logger(__name__)


# ============================================================================
# Exception
# ============================================================================


class PhaseContextError(Startd8Error):
    """Raised when phase context validation fails.

    Attributes:
        phase: The workflow phase that failed validation.
        missing_keys: Context keys that were required but absent.
        validation_errors: Pydantic validation error details (if any).
        direction: Whether the failure was at 'entry' or 'exit'.
    """

    def __init__(
        self,
        message: str,
        *,
        phase: str = "",
        missing_keys: Optional[List[str]] = None,
        validation_errors: Optional[List[Dict[str, Any]]] = None,
        direction: str = "",
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.missing_keys = missing_keys or []
        self.validation_errors = validation_errors or []
        self.direction = direction


# ============================================================================
# Orchestrator context (injected before any phase runs)
# ============================================================================


class OrchestratorContext(BaseModel):
    """Keys injected by the orchestrator before any phase runs."""

    model_config = ConfigDict(extra="forbid")

    project_root: str
    drafter_model: str
    validator_model: str
    reviewer_model: str
    task_filter: Optional[List[str]] = None
    abort_on_preflight_fail: bool = False
    # Phase 4: ManifestRegistry instance (Optional[Any] to avoid circular import)
    project_manifests: Optional[Any] = None


# ============================================================================
# Per-phase output models
# ============================================================================


class PlanPhaseOutput(BaseModel):
    """Output of the PLAN phase. Immutable after PLAN completes."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    enriched_seed_path: str
    tasks: List[Any]  # list[SeedTask] — SeedTask is a dataclass, not Pydantic
    task_index: Dict[str, Any]
    plan_title: str
    plan_goals: List[Any]
    domain_summary: Dict[str, Any]
    preflight_summary: Dict[str, Any]
    total_estimated_loc: int
    # Optional enrichment keys (may be empty dicts if seed lacks them)
    architectural_context: Dict[str, Any] = {}
    design_calibration: Dict[str, Any] = {}
    example_artifacts: Dict[str, Any] = {}
    # Phase 2 data flow keys (from ContextCore onboarding enrichment)
    source_checksum: Optional[str] = None
    parameter_sources: Dict[str, Any] = {}
    semantic_conventions: Dict[str, Any] = {}
    output_conventions: Dict[str, Any] = {}
    # Mottainai: onboarding-metadata inventory fields forwarded into context
    # so DESIGN can fall back to them when artifact inventory is absent.
    onboarding_derivation_rules: Optional[Dict[str, Any]] = None
    onboarding_resolved_parameters: Optional[Dict[str, Any]] = None
    onboarding_output_contracts: Optional[Dict[str, Any]] = None
    onboarding_calibration_hints: Optional[Dict[str, Any]] = None
    onboarding_open_questions: Optional[List[Dict[str, Any]]] = None
    onboarding_dependency_graph: Optional[Dict[str, Any]] = None
    # Mottainai B2+B3: plan document text for DESIGN fallback when
    # artifact inventory (run-provenance.json) is unavailable.
    plan_document_text: Optional[str] = None
    # Phase 4: Aggregate manifest stats for handoff (ManifestSummarySchema)
    project_manifest_summary: Optional[Dict[str, Any]] = None

    @field_validator("tasks")
    @classmethod
    def tasks_not_empty(cls, v: List[Any]) -> List[Any]:
        if not v:
            raise ValueError("tasks list must not be empty")
        # Verify items look like SeedTask (have task_id attribute)
        for i, task in enumerate(v):
            if not hasattr(task, "task_id"):
                raise ValueError(
                    f"tasks[{i}] does not have a 'task_id' attribute — "
                    f"expected SeedTask, got {type(task).__name__}"
                )
        return v

    @field_validator("task_index")
    @classmethod
    def task_index_not_empty(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("task_index must not be empty")
        return v

    @field_validator("enriched_seed_path")
    @classmethod
    def seed_path_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("enriched_seed_path must not be empty")
        return v

    @field_validator("domain_summary")
    @classmethod
    def domain_summary_not_empty(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("domain_summary must contain at least one domain entry")
        return v

    @model_validator(mode="after")
    def check_enrichment_completeness(self) -> "PlanPhaseOutput":
        """Advisory warnings for structurally empty enrichment fields.

        These fields CAN be empty (e.g. when running without onboarding), but
        empty enrichment degrades DESIGN quality silently.  Log warnings so
        the gap is visible in workflow output.
        """
        task_count = len(self.tasks)
        if task_count and not self.architectural_context:
            _logger.warning(
                "PlanPhaseOutput: architectural_context is empty — "
                "DESIGN will lack objectives/constraints/shared-module context"
            )
        if task_count and not self.design_calibration:
            _logger.warning(
                "PlanPhaseOutput: design_calibration is empty — "
                "all %d tasks will use default output size limits",
                task_count,
            )
        return self


class FileStubResult(BaseModel):
    """Result of a single file stub render or materialize operation."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    elements_count: int
    imports_count: int
    status: Literal[
        "created", "skipped_exists", "syntax_error",
        "would_create", "would_skip_exists",
    ]
    phase: Literal["render", "materialize"] = "materialize"
    error: Optional[str] = None


class ScaffoldPhaseOutput(BaseModel):
    """Output of the SCAFFOLD phase."""

    scaffold: Dict[str, Any]
    # AR-821: importable Python packages discovered during SCAFFOLD
    module_inventory: List[str] = []
    # Deterministic file assembly results
    file_stubs: List[Dict[str, Any]] = []
    file_stubs_created: int = 0
    file_stubs_skipped: int = 0
    file_stubs_failed: int = 0
    assembly_degraded: bool = False

    @field_validator("scaffold")
    @classmethod
    def scaffold_has_required_keys(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        required = {"directories_needed", "directories_created", "project_root"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(
                f"scaffold dict missing required keys: {sorted(missing)}"
            )
        return v


class DesignPhaseOutput(BaseModel):
    """Output of the DESIGN phase."""

    design_results: Dict[str, Any]
    design_quality: Dict[str, Any] = {}

    @field_validator("design_results")
    @classmethod
    def design_results_not_empty(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("design_results must not be empty")
        # Structural check: each entry should have at least a status key
        for task_id, entry in v.items():
            if not isinstance(entry, dict):
                raise ValueError(
                    f"design_results[{task_id!r}] should be a dict, "
                    f"got {type(entry).__name__}"
                )
            if "status" not in entry:
                raise ValueError(
                    f"design_results[{task_id!r}] missing required 'status' key"
                )
        return v

    @field_validator("design_quality")
    @classmethod
    def design_quality_has_required_metrics(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        # M-3: An empty dict is treated the same as missing — required keys
        # must be present for downstream gates to function.
        required = {"total_passed", "total_failed", "agreement_rate"}
        if not v:
            raise ValueError(
                f"design_quality is empty; required keys: {sorted(required)}"
            )
        missing = required - set(v.keys())
        if missing:
            raise ValueError(
                f"design_quality missing required keys: {sorted(missing)}"
            )
        return v


class ImplementPhaseOutput(BaseModel):
    """Output of the IMPLEMENT phase.

    Note: ``generation_results`` values are ``GenerationResult`` objects
    (NamedTuples), not plain dicts.  ``arbitrary_types_allowed`` is set
    because Pydantic cannot validate NamedTuples by default.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    implementation: Dict[str, Any]
    generation_results: Dict[str, Any]
    truncation_flags: Dict[str, Any] = {}

    @model_validator(mode="after")
    def check_implement_output_consistency(self) -> "ImplementPhaseOutput":
        """Validate structural invariants of the IMPLEMENT output.

        - When generation_results is non-empty (tasks were processed),
          at least one task must have produced generated_files.
        - total_cost in the implementation dict must be non-negative if present.
        """
        # Check total_cost is non-negative if present in generation results
        for _tid, gr in self.generation_results.items():
            gr_dict = gr if isinstance(gr, dict) else {}
            task_cost = gr_dict.get("cost_usd") if gr_dict else getattr(gr, "cost_usd", None)
            if task_cost is not None and isinstance(task_cost, (int, float)) and task_cost < 0:
                raise ValueError(
                    f"generation_results['{_tid}'].cost_usd must be non-negative, "
                    f"got {task_cost}"
                )

        # Check total_cost is non-negative if present
        total_cost = self.implementation.get("total_cost")
        if total_cost is not None and isinstance(total_cost, (int, float)) and total_cost < 0:
            raise ValueError(
                f"implementation['total_cost'] must be non-negative, "
                f"got {total_cost}"
            )
        return self


class ValidationPhaseOutput(BaseModel):
    """Output of the TEST phase (named ValidationPhaseOutput to avoid pytest collection)."""

    test_results: Dict[str, Any]

    @field_validator("test_results")
    @classmethod
    def test_results_has_required_structure(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        required = {"test_plan", "total_passed", "total_failed", "per_task"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"test_results missing required keys: {sorted(missing)}")
        if not isinstance(v.get("per_task"), dict):
            raise ValueError("test_results['per_task'] must be a dict")
        return v


class ReviewPhaseOutput(BaseModel):
    """Output of the REVIEW phase."""

    review_results: Dict[str, Any]

    @field_validator("review_results")
    @classmethod
    def review_results_has_required_structure(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        required = {"review_items", "total_passed", "total_failed", "per_task"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"review_results missing required keys: {sorted(missing)}")
        if not isinstance(v.get("per_task"), dict):
            raise ValueError("review_results['per_task'] must be a dict")
        return v


class IntegratePhaseOutput(BaseModel):
    """Output model for the INTEGRATE phase."""

    integration_results: Dict[str, Any]  # task_id -> {success, integrated_files, errors, ...}

    @field_validator("integration_results")
    @classmethod
    def integration_results_has_required_structure(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        for task_id, entry in v.items():
            if not isinstance(entry, dict):
                raise ValueError(
                    f"integration_results[{task_id!r}] should be a dict, "
                    f"got {type(entry).__name__}"
                )
            required = {"success", "integrated_files", "errors"}
            missing = required - set(entry.keys())
            if missing:
                raise ValueError(
                    f"integration_results[{task_id!r}] missing required keys: "
                    f"{sorted(missing)}"
                )
            if not isinstance(entry.get("success"), bool):
                raise ValueError(
                    f"integration_results[{task_id!r}]['success'] must be a bool"
                )
            if not isinstance(entry.get("integrated_files"), list):
                raise ValueError(
                    f"integration_results[{task_id!r}]['integrated_files'] must be a list"
                )
            if not isinstance(entry.get("errors"), list):
                raise ValueError(
                    f"integration_results[{task_id!r}]['errors'] must be a list"
                )
        return v


class FinalizePhaseOutput(BaseModel):
    """Output of the FINALIZE phase."""

    workflow_summary: Dict[str, Any]

    @field_validator("workflow_summary")
    @classmethod
    def workflow_summary_has_required_structure(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        required = {"plan_title", "task_count", "status", "cost_summary"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"workflow_summary missing required keys: {sorted(missing)}")
        return v


# ============================================================================
# Phase-to-model mapping
# ============================================================================

# Import WorkflowPhase lazily to avoid circular imports at module level.
# The mapping is populated on first use via _get_phase_exit_models().

_PHASE_EXIT_MODELS: Optional[Dict[str, type]] = None


def _get_phase_exit_models() -> Dict[str, type]:
    """Return {phase_value: PydanticModel} mapping, building it once."""
    global _PHASE_EXIT_MODELS
    if _PHASE_EXIT_MODELS is None:
        _PHASE_EXIT_MODELS = {
            "plan": PlanPhaseOutput,
            "scaffold": ScaffoldPhaseOutput,
            "design": DesignPhaseOutput,
            "implement": ImplementPhaseOutput,
            "integrate": IntegratePhaseOutput,
            "test": ValidationPhaseOutput,
            "review": ReviewPhaseOutput,
            "finalize": FinalizePhaseOutput,
        }
    return _PHASE_EXIT_MODELS


# Per-phase entry requirements: context keys that MUST exist and be non-None.
# Keyed by phase value string to avoid importing WorkflowPhase at module level.
PHASE_ENTRY_REQUIREMENTS: Dict[str, List[str]] = {
    "plan": ["project_root"],
    "scaffold": ["tasks", "task_index", "project_root"],
    "design": ["tasks", "task_index"],
    "implement": ["tasks", "design_results", "project_root"],
    "integrate": ["generation_results"],
    "test": ["tasks", "generation_results"],
    "review": ["generation_results"],
    "finalize": ["tasks", "generation_results"],
}

# Maps each phase exit model to the context keys it reads.
# Used by validate_phase_exit to extract the right keys from the dict.
_PHASE_EXIT_KEYS: Dict[str, List[str]] = {
    "plan": [
        "enriched_seed_path", "tasks", "task_index", "plan_title",
        "plan_goals", "domain_summary", "preflight_summary",
        "total_estimated_loc", "architectural_context",
        "design_calibration", "example_artifacts",
        "source_checksum", "parameter_sources",
        "semantic_conventions", "output_conventions",
    ],
    "scaffold": ["scaffold"],
    "design": ["design_results", "design_quality"],
    "implement": ["implementation", "generation_results", "truncation_flags"],
    "integrate": ["integration_results"],
    "test": ["test_results"],
    "review": ["review_results"],
    "finalize": ["workflow_summary"],
}


# ============================================================================
# Validation functions
# ============================================================================


def validate_phase_entry(phase: Any, context: Dict[str, Any]) -> None:
    """Validate that *context* contains all keys required for *phase* to run.

    Args:
        phase: A ``WorkflowPhase`` enum member (or anything with a ``.value`` str).
        context: The shared mutable context dict.

    Raises:
        PhaseContextError: If any required key is missing or None.
    """
    phase_value = phase.value if hasattr(phase, "value") else str(phase)
    required = PHASE_ENTRY_REQUIREMENTS.get(phase_value, [])

    missing: List[str] = []
    for key in required:
        if key not in context or context[key] is None:
            missing.append(key)

    if missing:
        raise PhaseContextError(
            f"{phase_value.upper()} phase entry validation failed — "
            f"missing required context keys: {missing}",
            phase=phase_value,
            missing_keys=missing,
            direction="entry",
        )

    _logger.debug(
        "Phase entry validated: %s (checked %d keys)",
        phase_value,
        len(required),
    )


def validate_phase_exit(phase: Any, context: Dict[str, Any]) -> None:
    """Validate that *context* contains valid output for *phase*.

    Constructs the phase's Pydantic output model from the context dict.
    If construction fails (missing fields, wrong types), raises
    ``PhaseContextError`` with the Pydantic validation errors.

    Args:
        phase: A ``WorkflowPhase`` enum member (or anything with a ``.value`` str).
        context: The shared mutable context dict (after phase execution).

    Raises:
        PhaseContextError: If the phase's output model cannot be constructed.
    """
    phase_value = phase.value if hasattr(phase, "value") else str(phase)
    models = _get_phase_exit_models()
    model_cls = models.get(phase_value)

    if model_cls is None:
        _logger.debug(
            "No exit model registered for phase %s — skipping exit validation",
            phase_value,
        )
        return

    # Extract only the keys the model cares about from the context dict.
    keys = _PHASE_EXIT_KEYS.get(phase_value, [])
    model_data: Dict[str, Any] = {}
    for key in keys:
        if key in context:
            model_data[key] = context[key]

    try:
        model_cls.model_validate(model_data)
    except Exception as exc:
        # Extract structured errors from Pydantic ValidationError if available.
        validation_errors: List[Dict[str, Any]] = []
        if hasattr(exc, "errors"):
            validation_errors = [
                {"loc": list(e.get("loc", ())), "msg": e.get("msg", str(e)), "type": e.get("type", "")}
                for e in exc.errors()
            ]

        missing = [
            key for key in keys if key not in context or context[key] is None
        ]

        raise PhaseContextError(
            f"{phase_value.upper()} phase exit validation failed: {exc}",
            phase=phase_value,
            missing_keys=missing,
            validation_errors=validation_errors,
            direction="exit",
        ) from exc

    _logger.debug(
        "Phase exit validated: %s (%s — %d fields)",
        phase_value,
        model_cls.__name__,
        len(keys),
    )


# ============================================================================
# Contract-aware boundary validation (Layer 1 extension)
# ============================================================================


def validate_phase_boundary(
    phase: Any,
    context: Dict[str, Any],
    direction: str = "entry",
    contract_path: Optional[Path] = None,
) -> Any:
    """Unified boundary validation: legacy checks + contract entry/enrichment/exit.

    Always runs the existing blocking validation (``validate_phase_entry`` or
    ``validate_phase_exit``).  When a *contract_path* is provided and the
    ``contextcore.contracts.propagation`` package is importable, additionally
    runs ``BoundaryValidator.validate_entry()`` (required fields + quality
    gates) and ``validate_enrichment()`` on entry, or ``validate_exit()`` on
    exit.

    On entry the two contract results are merged: ``validate_entry()`` is
    authoritative for ``passed`` / ``blocking_failures``; quality violations,
    warnings and field results from enrichment are appended.

    This function preserves full backward compatibility — callers that do not
    pass *contract_path* get identical behavior to calling
    ``validate_phase_entry``/``validate_phase_exit`` directly.

    Args:
        phase: A ``WorkflowPhase`` enum member (or anything with ``.value``).
        context: The shared mutable context dict.
        direction: ``"entry"`` or ``"exit"``.
        contract_path: Optional path to a propagation contract YAML file.

    Returns:
        A ``ContractValidationResult`` if contract validation ran, else ``None``.

    Raises:
        PhaseContextError: If blocking validation fails (same as before).
    """
    # 1. Always run existing validation (blocking fields)
    if direction == "entry":
        validate_phase_entry(phase, context)  # raises PhaseContextError
    else:
        validate_phase_exit(phase, context)  # raises PhaseContextError

    # 2. If contract available, run contract-aware validation
    if contract_path is not None:
        try:
            from contextcore.contracts.propagation import (
                BoundaryValidator,
                ContractLoader,
            )
        except ImportError:
            _logger.debug(
                "contextcore.contracts.propagation not available — "
                "skipping contract validation"
            )
            return None

        phase_value = phase.value if hasattr(phase, "value") else str(phase)
        contract = ContractLoader().load(contract_path)
        validator = BoundaryValidator()

        if direction == "entry":
            entry_result = validator.validate_entry(
                phase_value, context, contract,
            )
            enrichment_result = validator.validate_enrichment(
                phase_value, context, contract,
            )
            # Merge: entry is authoritative for passed/blocking_failures;
            # append enrichment quality violations, warnings, field results.
            entry_result.quality_violations.extend(
                enrichment_result.quality_violations,
            )
            entry_result.warnings.extend(enrichment_result.warnings)
            entry_result.field_results.extend(enrichment_result.field_results)
            return entry_result
        else:
            return validator.validate_exit(phase_value, context, contract)

    return None
