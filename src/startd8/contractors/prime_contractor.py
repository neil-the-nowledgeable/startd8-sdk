import dataclasses
import enum
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logging_config import get_logger
from .checkpoint import IntegrationCheckpoint
from .context_resolution import (
    ContextStrategy as ContextResolutionStrategy,
    StandaloneContextStrategy,
    PipelineContextStrategy,
    create_strategy,
)
from .integration_engine import IntegrationEngine
from .protocols import (
    CheckpointFailedCallback,
    CodeGenerator,
    FeatureCompleteCallback,
    GenerationResult,
    IntegrationUnit,
    Instrumentor,
    MergeStrategy,
    SizeEstimator,
)
from .queue import FeatureQueue, FeatureSpec, FeatureStatus
from .registry import get_registry

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Execution Mode Constants (F-004)
# ---------------------------------------------------------------------------

#: Execution mode for standalone operation — no pipeline context expected.
MODE_STANDALONE: str = "standalone"

#: Execution mode for pipeline operation — full seed context exploitation.
MODE_PIPELINE: str = "pipeline"

#: Set of all recognized execution modes.
VALID_MODES: frozenset = frozenset({MODE_STANDALONE, MODE_PIPELINE})

#: Valid execution modes for state persistence — single source of truth for validation.
VALID_EXECUTION_MODES: frozenset = frozenset({"standalone", "pipeline"})

#: Internal: minimum number of pipeline signal keys (with non-None values)
#: required to trigger pipeline mode during auto-detection.
_DETECTION_THRESHOLD: int = 1

#: Plan document load cap (PC-B5). Reduces from 60KB to 16KB for token savings.
_PLAN_LOAD_MAX_BYTES: int = 16_384

#: PC-O1, PC-O3: Budget for existing file content when populating gen_context.
#: Matches lead_contractor_workflow._EXISTING_FILES_BUDGET_BYTES (40KB).
_EXISTING_FILES_BUDGET_BYTES: int = 40 * 1024

__all__ = [
    "MODE_STANDALONE",
    "MODE_PIPELINE",
    "VALID_MODES",
    "VALID_EXECUTION_MODES",
    "ExecutionMode",
    "ModeConfig",
    "SeedContext",
    "PrimeContractorWorkflow",
    "PrimeContractorListener",
    "FeatureSpecUnit",
]


# ---------------------------------------------------------------------------
# SeedContext: Typed Container for Pipeline Seed Context (SeedContext-001)
# ---------------------------------------------------------------------------

# Explicit set of fields included in serialization. Using an explicit set
# rather than a naming convention to avoid silently dropping future fields.
_SERIALIZABLE_FIELDS = frozenset({
    "execution_mode",
    "onboarding_metadata",
    "architectural_context",
    "design_calibration",
    "generation_provenance",
})


@dataclasses.dataclass
class SeedContext:
    """Typed container for pipeline seed context.

    Mutable during setup phase; call freeze() before execution begins.
    In standalone mode, all context fields remain None.

    **Shallow freeze only:** After freeze(), attribute reassignment is blocked,
    but in-place mutation of mutable values (e.g., ``ctx.onboarding_metadata['k'] = v``)
    is NOT prevented. If deep immutability is required in the future, property
    accessors can return ``types.MappingProxyType`` wrappers.

    **Unhashable:** This class supports ``__eq__`` for testing but is not hashable,
    since instances are mutable before freeze.
    """

    # Execution mode
    execution_mode: str = "standalone"

    # Domain context fields — all Optional for standalone compatibility
    onboarding_metadata: Optional[Dict[str, Any]] = None
    architectural_context: Optional[Dict[str, Any]] = None
    design_calibration: Optional[Dict[str, Any]] = None
    generation_provenance: Optional[Dict[str, Any]] = None

    # Lifecycle control — init=False prevents callers from constructing
    # pre-frozen instances via SeedContext(_frozen=True).
    _frozen: bool = dataclasses.field(default=False, init=False, repr=False, compare=False)

    # Explicitly unhashable: mutable before freeze, so hashing would be unsound.
    __hash__ = None

    def freeze(self) -> None:
        """Transition to immutable state. Called once before execution begins.

        Performs consistency validation before freezing:
        - Warns if execution_mode is 'pipeline' but all context fields are None,
          which likely indicates misconfiguration.
        """
        self._check_consistency()
        object.__setattr__(self, '_frozen', True)

    def _check_consistency(self) -> None:
        """Validate semantic consistency. Called by freeze().

        Emits warnings (not errors) to catch likely misconfiguration without
        being overly prescriptive at the dataclass level.
        """
        if self.execution_mode == "pipeline":
            context_fields = [
                self.onboarding_metadata,
                self.architectural_context,
                self.design_calibration,
                self.generation_provenance,
            ]
            if all(f is None for f in context_fields):
                logger.warning(
                    "SeedContext frozen in pipeline mode with all context fields None; "
                    "this likely indicates misconfiguration — expected at least one "
                    "context field to be populated",
                    extra={"seed_exec_mode": self.execution_mode},
                )

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    @property
    def is_pipeline_mode(self) -> bool:
        return self.execution_mode == "pipeline"

    @property
    def is_standalone_mode(self) -> bool:
        return self.execution_mode == "standalone"

    def __setattr__(self, name: str, value: Any) -> None:
        # Bootstrap ordering note: During dataclass-generated __init__, fields
        # are assigned via __setattr__ in declaration order. Because _frozen has
        # init=False, it is set in __init__ (to its default False) AFTER all
        # init=True fields. However, even if ordering were different, the
        # getattr(..., False) guard returns False when _frozen doesn't yet exist
        # on the instance, allowing initial assignment to proceed. This is
        # intentional and correct, but depends on getattr's default.
        if getattr(self, '_frozen', False) and name != '_frozen':
            raise AttributeError(
                f"SeedContext is frozen; cannot set '{name}' after execution begins"
            )
        object.__setattr__(self, name, value)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize domain fields (excludes lifecycle internals).

        Uses the explicit _SERIALIZABLE_FIELDS set rather than a naming
        convention, so future fields must be explicitly opted in.
        """
        return {
            name: getattr(self, name)
            for name in _SERIALIZABLE_FIELDS
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeedContext":
        """Construct from dictionary, ignoring unknown keys.

        Only keys present in _SERIALIZABLE_FIELDS are passed to the constructor.
        This uses an explicit allowlist rather than introspecting field names,
        ensuring future internal fields are not accidentally deserialized.
        """
        filtered = {k: v for k, v in data.items() if k in _SERIALIZABLE_FIELDS}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# ExecutionMode Enum and ModeConfig Dataclass (F-001)
# ---------------------------------------------------------------------------

class ExecutionMode(enum.Enum):
    """Execution mode for the Prime Contractor workflow.

    STANDALONE: Current behavior — no pipeline context, zero-change default.
    PIPELINE: Full context exploitation — onboarding, architectural, calibration.
    """

    STANDALONE = "standalone"
    PIPELINE = "pipeline"


@dataclass(frozen=True)
class ModeConfig:
    """Immutable per-mode configuration for Prime Contractor execution.

    Constructed via ModeConfig.for_mode() factory for correct defaults,
    or directly for testing. Override individual fields via
    dataclasses.replace(config, field=value).

    Attributes:
        mode: Active execution mode (STANDALONE or PIPELINE)
        use_onboarding_context: Exploit onboarding metadata (False for STANDALONE, True for PIPELINE)
        use_architectural_context: Exploit architectural context (False for STANDALONE, True for PIPELINE)
        use_design_calibration: Exploit design calibration (False for STANDALONE, True for PIPELINE)
        enable_provenance_tracking: Track generation provenance (False for STANDALONE, True for PIPELINE)
        enable_post_validation: Enable post-generation validation hookpoints (False for STANDALONE, True for PIPELINE)
        max_context_depth: Pipeline context traversal depth (0 for STANDALONE, 3 for PIPELINE)
    """

    mode: ExecutionMode = ExecutionMode.STANDALONE
    use_onboarding_context: bool = False
    use_architectural_context: bool = False
    use_design_calibration: bool = False
    enable_provenance_tracking: bool = False
    enable_post_validation: bool = False
    max_context_depth: int = 0

    @classmethod
    def for_mode(cls, mode: ExecutionMode) -> "ModeConfig":
        """Factory: build ModeConfig with correct per-mode defaults.

        Args:
            mode: ExecutionMode (STANDALONE or PIPELINE)

        Returns:
            ModeConfig instance with mode-appropriate defaults
        """
        if mode is ExecutionMode.PIPELINE:
            return cls(
                mode=ExecutionMode.PIPELINE,
                use_onboarding_context=True,
                use_architectural_context=True,
                use_design_calibration=True,
                enable_provenance_tracking=True,
                enable_post_validation=True,
                max_context_depth=3,
            )
        # STANDALONE: all defaults are already correct (False/0)
        return cls(mode=ExecutionMode.STANDALONE)

    @classmethod
    def from_string(cls, mode_str: str) -> "ModeConfig":
        """Construct from CLI string argument.

        Args:
            mode_str: String representation of ExecutionMode (case-insensitive, whitespace-tolerant)

        Returns:
            ModeConfig instance with mode-appropriate defaults

        Raises:
            ValueError: If mode_str is not a valid ExecutionMode value
        """
        try:
            mode = ExecutionMode(mode_str.lower().strip())
        except ValueError:
            valid = ", ".join(m.value for m in ExecutionMode)
            raise ValueError(
                f"Invalid execution mode '{mode_str}'. Valid modes: {valid}"
            )
        return cls.for_mode(mode)


_EDIT_FIRST_VALIDATED: bool = True  # F-000: Remove after edit-first pipeline validated; see lifecycle in design doc


# ---------------------------------------------------------------------------
# Adapters: bridge FeatureSpec → IntegrationUnit / IntegrationListener
# ---------------------------------------------------------------------------

class FeatureSpecUnit:
    """Thin property wrapper: FeatureSpec → IntegrationUnit.

    NOT a serialization boundary — forwards everything, Mottainai-compliant.
    """

    __slots__ = ("_feature",)

    def __init__(self, feature: FeatureSpec) -> None:
        self._feature = feature

    @property
    def id(self) -> str:
        return self._feature.id

    @property
    def name(self) -> str:
        return self._feature.name

    @property
    def generated_files(self) -> List[str]:
        return self._feature.generated_files

    @property
    def target_files(self) -> List[str]:
        return self._feature.target_files

    @property
    def context(self) -> Dict[str, Any]:
        return self._feature.metadata


class PrimeContractorListener:
    """Bridge IntegrationEngine events → queue + instrumentor."""

    def __init__(
        self,
        queue: FeatureQueue,
        instrumentor: Any,
        files_modified: Dict[str, List[str]],
    ) -> None:
        self._queue = queue
        self._instrumentor = instrumentor
        self._files_modified = files_modified

    def on_integration_started(self, unit: IntegrationUnit) -> None:
        self._queue.start_integration(unit.id)

    def on_file_integrated(
        self, unit: IntegrationUnit, source: Path, target: Path,
    ) -> None:
        key = str(target)
        if key not in self._files_modified:
            self._files_modified[key] = []
        self._files_modified[key].append(unit.name)

    def on_checkpoint_result(self, unit: IntegrationUnit, result: Any) -> None:
        pass  # gate emission handled inside engine

    def on_integration_failed(self, unit: IntegrationUnit, error: str) -> None:
        self._queue.fail_feature(unit.id, error)
        self._instrumentor.emit_insight(
            insight_type="integration_failed",
            summary=f"Feature '{unit.name}' failed: {error}",
            confidence=1.0,
            feature_id=unit.id,
        )

    def on_integration_completed(
        self, unit: IntegrationUnit, files: List[Path],
    ) -> None:
        self._instrumentor.emit_insight(
            insight_type="integration_success",
            summary=f"Feature '{unit.name}' integrated successfully",
            confidence=1.0,
            feature_id=unit.id,
            files_count=len(files),
        )

class PrimeContractorWorkflow:
    """
    Orchestrates code generation with continuous integration.

    Instead of generating all features and then integrating them in a batch
    (which causes conflicts), this workflow:

    1. Takes one feature at a time
    2. Generates the code (via CodeGenerator)
    3. Integrates it immediately (via MergeStrategy)
    4. Runs checkpoints to validate
    5. Only proceeds to next feature if checkpoints pass

    This prevents the exact problem where multiple changes to the same file
    create conflicts that require careful manual merging.

    Example:
        workflow = PrimeContractorWorkflow()
        workflow.queue.add_feature("auth", "Add authentication")
        workflow.queue.add_feature("logout", "Add logout", dependencies=["auth"])
        result = workflow.run()

    With ContextCore (enhanced observability):
        from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor

        workflow = PrimeContractorWorkflow(
            instrumentor=ContextCoreInstrumentor(project_id="myproject"),
        )
        result = workflow.run()  # Emits spans to Tempo
    """

    # -----------------------------------------------------------------------
    # Mode Detection (F-004)
    # -----------------------------------------------------------------------

    #: Seed content keys whose presence signals pipeline mode.
    #: Defined as a class attribute so subclasses can extend or override
    #: the signal set without modifying module-level state.
    _PIPELINE_SIGNAL_KEYS: frozenset = frozenset({
        "onboarding_metadata",
        "architectural_context",
        "design_calibration",
    })

    @classmethod
    def _detect_mode(
        cls,
        seed_content: Dict[str, Any],
        mode_override: Optional[str] = None,
    ) -> str:
        """Infer execution mode from seed content signals.

        Args:
            seed_content: Dictionary of seed/context data passed to the workflow.
                Must be a ``dict``. Passing ``None`` or a non-dict type raises
                ``TypeError``.
            mode_override: Explicit mode string. When provided and valid, bypasses
                auto-detection entirely. An empty string is treated as an invalid
                mode (not as "no override").

        Returns:
            One of MODE_STANDALONE or MODE_PIPELINE.

        Raises:
            TypeError: If *seed_content* is not a ``dict``.
            ValueError: If *mode_override* is not a recognized mode.

        Signal presence semantics:
            A signal key is considered **present** when it exists in
            *seed_content* and its value ``is not None``.  This uses an
            explicit ``None`` check rather than a general truthy check, so
            values like ``0``, ``False``, or ``[]`` are treated as present
            (the signal was intentionally provided, even if empty).  Empty
            strings and empty dicts *are* counted as present under this rule.
            Callers who want to suppress a signal should omit the key entirely
            or set it to ``None``.
        """
        # --- Input guard ---
        if not isinstance(seed_content, dict):
            raise TypeError(
                f"seed_content must be a dict, got {type(seed_content).__name__}"
            )

        # --- Override path (highest priority) ---
        if mode_override is not None:
            normalized = mode_override.strip().lower()
            if normalized not in VALID_MODES:
                raise ValueError(
                    f"Invalid mode override {mode_override!r}; "
                    f"expected one of {sorted(VALID_MODES)}"
                )
            logger.info(
                "Mode override applied",
                extra={
                    "detection_source": "override",
                    "resolved_mode": normalized,
                    "override_value": mode_override,
                },
            )
            return normalized

        # --- Auto-detection path ---
        signal_keys = cls._PIPELINE_SIGNAL_KEYS
        detected_signals = signal_keys & set(seed_content.keys())
        # Explicit None check: a key is present if its value is not None.
        # This intentionally counts falsy-but-non-None values (e.g., {},
        # "", [], 0, False) as present — the signal was provided.
        present_signals = frozenset(
            key for key in detected_signals
            if seed_content[key] is not None
        )

        if len(present_signals) >= _DETECTION_THRESHOLD:
            resolved = MODE_PIPELINE
        else:
            resolved = MODE_STANDALONE

        logger.info(
            "Mode auto-detected",
            extra={
                "detection_source": "auto",
                "resolved_mode": resolved,
                "signals_checked": sorted(signal_keys),
                "signals_present": sorted(present_signals),
                "signal_count": len(present_signals),
                "detection_threshold": _DETECTION_THRESHOLD,
            },
        )
        return resolved

    def __init__(self, project_root: Optional[Path]=None, dry_run: bool=False, auto_commit: bool=False, strict_checkpoints: bool=False, max_retries: int=6, allow_dirty: bool=False, auto_stash: bool=False, code_generator: Optional[CodeGenerator]=None, instrumentor: Optional[Instrumentor]=None, size_estimator: Optional[SizeEstimator]=None, merge_strategy: Optional[MergeStrategy]=None, on_feature_complete: Optional[FeatureCompleteCallback]=None, on_checkpoint_failed: Optional[CheckpointFailedCallback]=None, max_lines_per_feature: int=150, max_tokens_per_feature: int=500, check_truncation: bool=True, resume: bool=False, cli_mode: Optional[str]=None, force_mode: Optional[str]=None, context_strategy: Optional[ContextResolutionStrategy]=None, strict_mode: bool=False, walkthrough: bool=False, repair_config: Optional[Any]=None):
        """
        Initialize the Prime Contractor workflow.

        Args:
            project_root: Root directory of the project
            dry_run: If True, preview changes without executing
            auto_commit: If True, commit each feature after integration
            strict_checkpoints: If True, fail on checkpoint warnings
            max_retries: Maximum retry attempts per feature
            allow_dirty: If True, proceed with uncommitted changes
            auto_stash: If True, stash uncommitted changes before proceeding
            code_generator: Custom code generation backend
            instrumentor: Custom instrumentation backend
            size_estimator: Custom size estimation backend
            merge_strategy: Custom merge strategy
            on_feature_complete: Callback when feature completes
            on_checkpoint_failed: Callback when checkpoints fail
            max_lines_per_feature: Safe line limit for LLM output (default: 150)
            max_tokens_per_feature: Safe token limit for size estimation (default: 500)
            check_truncation: Validate generated files for truncation before integration (default: True)
            resume: If True, resume from persisted state
            cli_mode: Execution mode from CLI argument
            force_mode: Force override of persisted execution mode
            context_strategy: Custom context resolution strategy (default: StandaloneContextStrategy)
            strict_mode: If True, raise on strategy resolution failures (default: False for production, True for CI/testing)
            walkthrough: If True, persist all LLM prompts without making API calls
        """
        self.project_root = project_root or Path.cwd()
        self.dry_run = dry_run
        self.auto_commit = auto_commit
        self.strict_checkpoints = strict_checkpoints
        self.max_retries = max_retries
        self.allow_dirty = allow_dirty
        self.auto_stash = auto_stash
        self.on_feature_complete = on_feature_complete
        self.on_checkpoint_failed = on_checkpoint_failed
        self.check_truncation = check_truncation
        self.stash_ref: Optional[str] = None
        self.queue = FeatureQueue(project_root=self.project_root)
        self.checkpoint = IntegrationCheckpoint(project_root=self.project_root, run_tests=True, strict_mode=strict_checkpoints)
        registry = get_registry()
        registry.discover()
        self.code_generator = code_generator
        self.instrumentor = instrumentor or registry.get_default_instrumentor()()
        import os as _os
        _os.environ.setdefault('STARTD8_OTEL', 'auto')
        from ..otel import auto_configure_otel
        auto_configure_otel()
        self.size_estimator = size_estimator or registry.get_default_size_estimator()()
        self.merge_strategy = merge_strategy or registry.get_default_merge_strategy(for_python=True)()
        self.integration_history: List[Dict] = []
        self.files_modified_this_session: Dict[str, List[str]] = {}
        self.max_lines_per_feature = max_lines_per_feature
        self.max_tokens_per_feature = max_tokens_per_feature
        self.total_cost_usd: float = 0.0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        # Repair pipeline config (REQ-RPL-200)
        self._repair_config = repair_config
        # IntegrationEngine — delegates snapshot/merge/checkpoint/rollback
        self._engine = IntegrationEngine(
            project_root=self.project_root,
            merge_strategy=self.merge_strategy,
            checkpoint=self.checkpoint,
            dry_run=self.dry_run,
            auto_commit=self.auto_commit,
            allow_dirty=self.allow_dirty,
            check_truncation=self.check_truncation,
            strict_checkpoints=self.strict_checkpoints,
            repair_config=self._repair_config,
        )
        self._prime_listener = PrimeContractorListener(
            queue=self.queue,
            instrumentor=self.instrumentor,
            files_modified=self.files_modified_this_session,
        )
        self._domain_checklist = None  # lazy-init DomainChecklist
        self._current_enrichment = None  # per-feature enrichment cache
        # SeedContext — structured container for pipeline context (replaces ad-hoc attributes)
        self._seed_context: Optional[SeedContext] = None
        # Backward-compat ad-hoc attributes (deprecated, use seed_context via properties instead)
        self.seed_onboarding: Dict[str, Any] = {}
        self.seed_architectural_context: Dict[str, Any] = {}
        self.seed_design_calibration: Dict[str, Any] = {}
        self.seed_service_metadata: Dict[str, Any] = {}
        self.seed_forward_manifest: Optional[Dict[str, Any]] = None  # REQ-PC-FM-002
        self.plan_document_text: Optional[str] = None
        self.force_regenerate: bool = False
        self.walkthrough: bool = walkthrough
        # Kaizen prompt capture (REQ-KZ-200) — off by default, enabled via --kaizen flag
        self._kaizen_enabled: bool = False
        self._kaizen_prompt_dir: Optional[Path] = None
        # Kaizen config (REQ-KZ-502) — loaded from kaizen-config.json when --kaizen-config is set
        self._kaizen_config: Optional[dict] = None
        # Validation overrides (Phase 5: --validate / --no-validate / --strict-validation)
        self._validation_override: Optional[bool] = None  # None = use mode default
        self.strict_validation: bool = False
        # Context strategy injection (F-007)
        if context_strategy is not None and not isinstance(context_strategy, ContextResolutionStrategy):
            raise TypeError(
                f"context_strategy must implement ContextResolutionStrategy, "
                f"got {type(context_strategy).__name__}"
            )
        self._context_strategy = context_strategy or StandaloneContextStrategy()
        self._strict_mode = strict_mode
        # ForwardManifest (REQ-MP-701) — deserialized once in load_seed_context()
        self._forward_manifest = None
        # Complexity routing (REQ-MP-807) — off by default, enabled via enable_complexity_routing()
        self._complexity_routing_enabled = False
        self._complexity_config: Optional[Any] = None
        self._complexity_router: Optional[Any] = None
        # Micro Prime (REQ-MP-710) — off by default, enabled via enable_micro_prime()
        self._micro_prime_enabled = False
        self._original_code_generator = None
        # Tier escalation (REQ-RPL-500) — generator saved before escalation
        self._pre_escalation_generator = None
        self._escalation_threshold: int = 2  # attempts before escalation
        # Resume state: load from disk if resuming
        self._resume_mode: Optional[str] = None
        if resume:
            self._load_state_if_resuming(cli_mode=cli_mode, force_mode=force_mode)

    def _rel_display(self, path: Path) -> str:
        """Safe relative path for display, falling back to the full path."""
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

    # -----------------------------------------------------------------------
    # Tier Escalation (REQ-RPL-500)
    # -----------------------------------------------------------------------

    def _maybe_escalate_generator(self, feature: "FeatureSpec") -> bool:
        """Escalate code generator to a higher-capability model if warranted.

        Returns True if escalation was applied, False otherwise.
        Escalation triggers when integration_attempts >= _escalation_threshold,
        indicating error-informed regen already failed.
        """
        if feature.integration_attempts < self._escalation_threshold:
            return False
        if self._pre_escalation_generator is not None:
            return False  # Already escalated

        current_spec = getattr(self.code_generator, "lead_agent", None)
        if not current_spec:
            return False

        try:
            from ..model_catalog import get_escalation_target
        except ImportError:
            return False

        escalated_spec = get_escalation_target(str(current_spec))
        if not escalated_spec:
            logger.info(
                "No escalation target for '%s' (already flagship or unknown)",
                current_spec,
            )
            return False

        # Build an escalated generator with the same settings
        try:
            from .generators.lead_contractor import PrimaryContractorCodeGenerator

            drafter_spec = getattr(self.code_generator, "drafter_agent", None)
            self._pre_escalation_generator = self.code_generator
            self.code_generator = PrimaryContractorCodeGenerator(
                lead_agent=escalated_spec,
                drafter_agent=str(drafter_spec) if drafter_spec else escalated_spec,
                max_iterations=getattr(self.code_generator, "max_iterations", 3),
                pass_threshold=getattr(self.code_generator, "pass_threshold", 80),
                output_dir=getattr(self.code_generator, "output_dir", None),
                max_tokens=getattr(self.code_generator, "max_tokens", None),
            )
            logger.info(
                "Tier escalation for '%s': %s -> %s (attempt %d)",
                feature.name, current_spec, escalated_spec,
                feature.integration_attempts,
                extra={
                    "feature_name": feature.name,
                    "original_model": str(current_spec),
                    "escalated_model": escalated_spec,
                    "attempt": feature.integration_attempts,
                },
            )
            if feature.metadata is None:
                feature.metadata = {}
            feature.metadata["_tier_escalated"] = True
            feature.metadata["_escalated_from"] = str(current_spec)
            feature.metadata["_escalated_to"] = escalated_spec
            return True
        except Exception as exc:
            logger.warning(
                "Tier escalation failed for '%s': %s", feature.name, exc,
            )
            return False

    def _restore_generator(self) -> None:
        """Restore the original code generator after escalation."""
        if self._pre_escalation_generator is not None:
            self.code_generator = self._pre_escalation_generator
            self._pre_escalation_generator = None

    # -----------------------------------------------------------------------
    # Complexity Routing (REQ-MP-807)
    # -----------------------------------------------------------------------

    def enable_complexity_routing(
        self,
        config: Optional[Any] = None,
        tier3_agent: Optional[str] = None,
        trivial_generator: Optional[Any] = None,
        simple_generator: Optional[Any] = None,
    ) -> None:
        """Enable per-feature complexity-based model routing.

        Args:
            config: A ``ComplexityRoutingConfig`` instance, or ``None``
                for defaults.
            tier3_agent: Agent spec for the COMPLEX tier generator.
                When ``None`` the default code generator is used for all
                tiers (routing still classifies, but doesn't change the
                generator).
            trivial_generator: Code generator for TRIVIAL tier elements
                (e.g. MicroPrimeCodeGenerator).  Falls back to moderate
                when ``None``.
            simple_generator: Code generator for SIMPLE tier elements
                (e.g. MicroPrimeCodeGenerator).  Falls back to moderate
                when ``None``.
        """
        from startd8.complexity import (
            ComplexityRoutingConfig,
            ComplexityRouter,
        )

        self._complexity_routing_enabled = True
        self._complexity_config = config or ComplexityRoutingConfig()

        complex_generator = None
        if tier3_agent is not None:
            from startd8.contractors.generators import (
                PrimaryContractorCodeGenerator,
            )

            complex_generator = PrimaryContractorCodeGenerator(
                lead_agent=tier3_agent,
                output_dir=(
                    self.code_generator.output_dir
                    if hasattr(self.code_generator, "output_dir")
                    else Path("generated")
                ),
            )

        self._complexity_router = ComplexityRouter(
            trivial_generator=trivial_generator,
            simple_generator=simple_generator,
            moderate_generator=self.code_generator,
            complex_generator=complex_generator or self.code_generator,
        )
        logger.info(
            "Complexity routing enabled (tier3_agent=%s, trivial=%s, simple=%s)",
            tier3_agent or "default",
            type(trivial_generator).__name__ if trivial_generator else "default",
            type(simple_generator).__name__ if simple_generator else "default",
        )

    # -----------------------------------------------------------------------
    # Micro Prime Activation (REQ-MP-710)
    # -----------------------------------------------------------------------

    def enable_micro_prime(self, config: Optional[Any] = None) -> None:
        """Enable local-first generation via Micro Prime.

        Wraps the current ``code_generator`` as the fallback for
        MODERATE/COMPLEX elements.  TRIVIAL and SIMPLE elements are
        handled locally via Ollama.

        Must be called **before** ``enable_complexity_routing()`` so the
        router sees the wrapped generator.

        Args:
            config: A ``MicroPrimeConfig`` instance, or ``None`` for defaults.
        """
        if self._micro_prime_enabled:
            logger.info("Micro Prime already enabled — skipping")
            return

        try:
            from startd8.micro_prime.models import MicroPrimeConfig
            from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator
        except ImportError:
            logger.warning(
                "micro_prime package not available — cannot enable Micro Prime",
            )
            return

        cloud_agent_spec = None
        if config is None:
            try:
                from startd8.micro_prime.config_loader import (
                    load_micro_prime_settings,
                )
                mp_config, cloud_agent_spec = load_micro_prime_settings(
                    self.project_root,
                )
            except Exception as exc:
                logger.warning(
                    "Micro Prime config load failed (non-fatal): %s", exc,
                )
                mp_config = MicroPrimeConfig()
        else:
            mp_config = config or MicroPrimeConfig()
        self._original_code_generator = self.code_generator

        output_dir = (
            self.code_generator.output_dir
            if hasattr(self.code_generator, "output_dir")
            else Path("generated")
        )
        self.code_generator = MicroPrimeCodeGenerator(
            config=mp_config,
            fallback=self._original_code_generator,
            output_dir=output_dir,
            cloud_agent_spec=cloud_agent_spec,
        )
        self._micro_prime_enabled = True
        logger.info(
            "Micro Prime enabled: model=%s, templates=%s, repair=%s, cloud_escalation=%s",
            mp_config.model,
            mp_config.templates_enabled,
            mp_config.repair_enabled,
            "enabled" if cloud_agent_spec else "disabled",
        )

    def disable_micro_prime(self) -> None:
        """Disable Micro Prime, restoring the original code generator."""
        if not self._micro_prime_enabled or self._original_code_generator is None:
            return
        self.code_generator = self._original_code_generator
        self._original_code_generator = None
        self._micro_prime_enabled = False
        logger.info("Micro Prime disabled — original code generator restored")

    # -----------------------------------------------------------------------
    # Context Strategy: Resolution and Validation (F-007)
    # -----------------------------------------------------------------------

    def _resolve_context(
        self,
        feature_data: Dict[str, Any],
        seed_data: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Resolve context via strategy, with fallback and validation.

        Delegates to self._context_strategy.resolve_task_context() with
        fallback to StandaloneContextStrategy on failure (unless strict_mode).

        Args:
            feature_data: Feature dict (name, id, target_files, etc.).
            seed_data: Seed dict (onboarding_metadata, architectural_context, etc.).
            **kwargs: Passed through to resolve_task_context().

        Returns:
            gen_context dict from the strategy.
        """
        try:
            resolved = self._context_strategy.resolve_task_context(
                feature_data=feature_data,
                seed_data=seed_data,
                **kwargs,
            )
        except Exception as exc:
            if self._strict_mode:
                raise
            logger.error(
                "Context strategy resolution failed, falling back to standalone",
                extra={
                    "strategy_type": type(self._context_strategy).__name__,
                    "error_detail": str(exc),
                    "fallback_event": True,
                },
            )
            self._emit_fallback_metric(
                strategy_type=type(self._context_strategy).__name__
            )
            resolved = StandaloneContextStrategy().resolve_task_context(
                feature_data=feature_data,
                seed_data=seed_data,
                **kwargs,
            )

        if not self._is_valid_resolved_context(resolved):
            if self._strict_mode:
                raise ValueError(
                    f"Strategy returned invalid resolved context: "
                    f"not a dict or empty (type={type(resolved).__name__})"
                )
            logger.error(
                "Strategy returned invalid resolved context, falling back to standalone",
                extra={
                    "strategy_type": type(self._context_strategy).__name__,
                    "fallback_event": True,
                },
            )
            self._emit_fallback_metric(
                strategy_type=type(self._context_strategy).__name__
            )
            resolved = StandaloneContextStrategy().resolve_task_context(
                feature_data=feature_data,
                seed_data=seed_data,
                **kwargs,
            )

        return resolved

    @staticmethod
    def _is_valid_resolved_context(resolved: Any) -> bool:
        """Validate that a resolved context is a non-empty dict.

        Args:
            resolved: Result from strategy.resolve_context().

        Returns:
            True if valid, False otherwise.
        """
        return isinstance(resolved, dict)

    def _populate_existing_files(
        self,
        feature: FeatureSpec,
        gen_context: Dict[str, Any],
    ) -> None:
        """Populate gen_context with existing file contents for edit tasks (PC-O1).

        Reads target_files under project_root within _EXISTING_FILES_BUDGET_BYTES.
        Paths outside project_root are skipped (path traversal safety).
        """
        if not feature.target_files:
            return
        root = self.project_root.resolve()
        budget = _EXISTING_FILES_BUDGET_BYTES
        existing: Dict[str, str] = {}
        for rel_path in feature.target_files:
            if budget <= 0:
                logger.debug(
                    "Existing files budget exhausted for '%s', skipping remaining",
                    feature.name,
                )
                break
            full = (root / rel_path).resolve()
            if not str(full).startswith(str(root)):
                logger.warning(
                    "Target file %s is outside project root — skipping",
                    rel_path,
                )
                continue
            if not full.is_file():
                continue
            try:
                raw = full.read_bytes()
            except OSError as exc:
                logger.warning("Could not read %s: %s", rel_path, exc)
                continue
            take = min(len(raw), budget)
            content = raw[:take].decode("utf-8", errors="replace")
            existing[rel_path] = content
            budget -= take
        if existing:
            gen_context["existing_files"] = existing

    @staticmethod
    def _emit_fallback_metric(strategy_type: str) -> None:
        """Emit a structured metric/log for strategy fallback events.

        This function is the single point for observability on fallback
        occurrences. Integrate with your metrics system (e.g., StatsD,
        Prometheus counter) as appropriate.

        Args:
            strategy_type: Name of the strategy that failed
        """
        logger.warning(
            "METRIC: context_strategy_fallback",
            extra={
                "metric_name": "context_strategy_fallback_total",
                "strategy_type": strategy_type,
                "fallback_event": True,
            },
        )

    # -----------------------------------------------------------------------
    # State Persistence: Mode Serialization/Deserialization (F-005)
    # -----------------------------------------------------------------------

    def _load_state_if_resuming(
        self,
        cli_mode: Optional[str] = None,
        force_mode: Optional[str] = None,
    ) -> None:
        """Load persisted workflow state if resuming from checkpoint.

        Reads `.prime_contractor_state.json` if it exists, extracting the
        persisted execution_mode. Applies mode restoration policy:
        - Default: persisted mode wins (for consistency)
        - With --force-mode: CLI override wins

        Args:
            cli_mode: Mode string from CLI argument (if provided)
            force_mode: Force override mode (bypasses persisted mode)
        """
        state_file = self.queue.state_file
        if not state_file.exists():
            logger.debug(
                "No persisted state found at %s; starting fresh",
                state_file,
            )
            return

        try:
            import json
            with open(state_file, 'r') as f:
                state_dict = json.load(f)
            logger.debug("Loaded persisted state from %s", state_file)
        except (OSError, ValueError) as e:
            logger.error(
                "Failed to load persisted state from %s: %s",
                state_file, e,
                exc_info=True,
            )
            return

        # Extract and validate execution_mode
        raw_mode = state_dict.get("execution_mode", "standalone")

        # Type coercion: handle non-string values (null → None, int → "123", etc.)
        loaded_mode = str(raw_mode) if raw_mode is not None else "standalone"

        # Validate against known modes
        if loaded_mode not in VALID_EXECUTION_MODES:
            logger.warning(
                "Unknown execution_mode '%s' (type: %s) in state file, defaulting to 'standalone'",
                loaded_mode,
                type(raw_mode).__name__,
                extra={
                    "persisted_mode": loaded_mode,
                    "persisted_mode_raw_type": type(raw_mode).__name__,
                },
            )
            loaded_mode = "standalone"

        # Apply mode restoration policy
        self._restore_mode(
            loaded_mode,
            cli_mode=cli_mode,
            force_mode=force_mode,
        )

    def _restore_mode(
        self,
        loaded_mode: str,
        cli_mode: Optional[str] = None,
        force_mode: Optional[str] = None,
    ) -> None:
        """Restore execution mode from persisted state with policy handling.

        This is the single point of responsibility for:
        1. Applying the persisted mode or CLI override
        2. Handling CLI mode override policy (persisted wins by default, CLI via --force-mode)
        3. Propagating mode to SeedContext

        Args:
            loaded_mode: Validated mode string from state file.
            cli_mode: Mode string from CLI arguments, if provided.
            force_mode: Force override mode (bypasses persisted mode).
        """
        effective_mode = loaded_mode

        # --- Force mode override (highest priority) ---
        if force_mode:
            if force_mode not in VALID_EXECUTION_MODES:
                logger.error(
                    "Invalid --force-mode '%s'; expected one of %s",
                    force_mode,
                    sorted(VALID_EXECUTION_MODES),
                )
                return
            logger.warning(
                "Resume: --force-mode overriding persisted execution_mode '%s' with '%s'. "
                "Intermediate state may be inconsistent.",
                loaded_mode,
                force_mode,
                extra={
                    "persisted_mode": loaded_mode,
                    "forced_mode": force_mode,
                },
            )
            effective_mode = force_mode

        # --- CLI mode override policy (persisted wins by default) ---
        elif cli_mode and cli_mode != loaded_mode:
            logger.warning(
                "Resume: persisted execution_mode '%s' overrides requested mode '%s' for consistency. "
                "Use --force-mode to override the persisted mode.",
                loaded_mode,
                cli_mode,
                extra={
                    "persisted_mode": loaded_mode,
                    "requested_mode": cli_mode,
                },
            )
            # effective_mode stays as loaded_mode (persisted wins)

        # --- Propagate to SeedContext ---
        # SeedContext is initialized during __init__ before state loading.
        # At resume time, self._seed_context is guaranteed to exist via the
        # seed_context property accessor.
        self.seed_context.execution_mode = effective_mode

        # Store for later use (e.g., in add_features_from_seed)
        self._resume_mode = effective_mode

        logger.info(
            "Restored execution mode '%s' from persisted state",
            effective_mode,
            extra={"execution_mode": effective_mode},
        )

    def _save_state_with_mode(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Augment state dictionary with execution_mode before persistence.

        This method is called by code that saves workflow state to disk.
        It injects the current execution_mode into the state dict to enable
        consistent resume behavior.

        Args:
            state_dict: Base state dictionary (usually from queue or workflow).

        Returns:
            Augmented state_dict with execution_mode added.
        """
        # execution_mode must be the string representation for JSON serialization
        state_dict["execution_mode"] = self.execution_mode
        return state_dict

    _FILE_COPY_READ_TIMEOUT_S: int = 30

    def _handle_file_copy(self, feature: FeatureSpec) -> Optional[GenerationResult]:
        """Handle file-copy tasks by copying predecessor output (REQ-MP-1002).

        Raises:
            ValueError: If predecessor not found, not complete, source file
                cannot be inferred, or target_files is empty.
            FileNotFoundError: If the source file does not exist on disk.
            FileExistsError: If target exists and ``copy_overwrite=False``.
            TimeoutError: If reading the source file exceeds the timeout.
            OSError: If SHA-256 verification fails after write.
        """
        import concurrent.futures
        import hashlib

        from .copy_detection import validate_copy_path

        predecessor_id = feature.copy_source_task_id
        # Look up predecessor
        predecessor = self.queue.get_feature(predecessor_id)
        if predecessor is None:
            raise ValueError(f"Copy source task '{predecessor_id}' not found in queue")
        if predecessor.status != FeatureStatus.COMPLETE:
            raise ValueError(
                f"Copy source task '{predecessor_id}' not complete "
                f"(status={predecessor.status.value})"
            )

        # Determine source file
        source_file = feature.copy_source_file
        if source_file is None:
            if len(predecessor.generated_files) == 1:
                source_file = predecessor.generated_files[0]
            else:
                raise ValueError(
                    f"Cannot infer copy source: predecessor '{predecessor_id}' "
                    f"has {len(predecessor.generated_files)} generated files"
                )

        # Validate path
        workspace = str(self.project_root)
        source_path = validate_copy_path(source_file, workspace)

        # Read with timeout
        def _read_file():
            return source_path.read_bytes()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_read_file)
            try:
                source_content = future.result(timeout=self._FILE_COPY_READ_TIMEOUT_S)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"Reading copy source '{source_file}' timed out after "
                    f"{self._FILE_COPY_READ_TIMEOUT_S}s"
                )

        # Write target
        if not feature.target_files:
            raise ValueError(
                f"Feature '{feature.id}' ('{feature.name}') has no target_files for copy"
            )
        target_path = Path(self.project_root) / feature.target_files[0]
        target_path.parent.mkdir(parents=True, exist_ok=True)

        copy_overwrite = (
            feature.metadata.get("copy_overwrite", True)
            if feature.metadata
            else True
        )
        if copy_overwrite:
            target_path.write_bytes(source_content)
        else:
            # TOCTOU-safe exclusive creation
            try:
                with open(target_path, "xb") as f:
                    f.write(source_content)
            except FileExistsError:
                raise FileExistsError(
                    f"Target '{target_path}' already exists and copy_overwrite=False"
                )

        # SHA-256 verify
        source_hash = hashlib.sha256(source_content).hexdigest()
        target_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
        if source_hash != target_hash:
            raise OSError(
                f"SHA-256 mismatch after copy: source={source_hash}, "
                f"target={target_hash}"
            )

        return GenerationResult(
            success=True,
            generated_files=[target_path],
            cost_usd=0.0,
            input_tokens=0,
            output_tokens=0,
            iterations=0,
            model="",
            metadata={
                "strategy": "file_copy",
                "copy_source_task_id": predecessor_id,
                "sha256": source_hash,
            },
        )

    def _inject_copy_and_modify_context(self, feature: FeatureSpec) -> None:
        """Detect copy-and-modify tasks and stash predecessor output in metadata (REQ-MP-1003).

        If the feature has both duplication and modification signals in its
        description, reads the predecessor's generated output and stores a
        (possibly compressed) version in ``feature.metadata["_reference_implementation"]``.
        The value is later threaded into ``gen_context`` before code generation.

        Non-fatal: logs a warning and continues without reference on any error.
        """
        from .copy_detection import detect_copy_and_modify, compress_reference, validate_copy_path

        predecessor = None
        deps = feature.dependencies or []
        if len(deps) == 1:
            predecessor = self.queue.get_feature(deps[0])

        cm = detect_copy_and_modify(feature, predecessor=predecessor)
        if cm is None:
            return

        # Look up predecessor and read its output.
        pred = self.queue.get_feature(cm.predecessor_id)
        if pred is None or pred.status != FeatureStatus.COMPLETE:
            logger.warning(
                "copy_and_modify: predecessor '%s' not found or not complete — skipping injection",
                cm.predecessor_id,
            )
            return

        # Determine source file path.
        source_file = cm.source_file
        if not source_file:
            if len(pred.generated_files) == 1:
                source_file = pred.generated_files[0]
            else:
                logger.warning(
                    "copy_and_modify: cannot infer source file for '%s' — skipping injection",
                    feature.name,
                )
                return

        try:
            source_path = validate_copy_path(source_file, str(self.project_root))
            if not source_path.is_file():
                logger.warning(
                    "copy_and_modify: source file '%s' not found on disk — skipping injection",
                    source_path,
                )
                return
            source_code = source_path.read_text(encoding="utf-8", errors="replace")
        except (ValueError, OSError) as exc:
            logger.warning(
                "copy_and_modify: failed to read predecessor output for '%s': %s",
                feature.name, exc,
            )
            return

        compressed = compress_reference(source_code)
        if feature.metadata is None:
            feature.metadata = {}
        feature.metadata["_reference_implementation"] = compressed
        feature.metadata["_copy_and_modify_source"] = cm.predecessor_id
        logger.info(
            "copy_and_modify: stashed reference for '%s' from '%s' (%d → %d chars)",
            feature.name, cm.predecessor_id, len(source_code), len(compressed),
        )

    def _save_queue_state_with_mode(self) -> None:
        """Save queue state with execution_mode injected.

        Calls queue.save_state() to persist features, then augments the state
        file with execution_mode. This is called after features are queued
        to ensure the mode is persisted for potential resume scenarios.

        In dry-run mode, state is NOT persisted — dry-run should not leave
        side effects that cause ``--list`` to report tasks as done.
        """
        if self.dry_run:
            return

        import json

        # First, let the queue save its state normally
        self.queue.save_state()

        # Then, read it back, inject execution_mode, and write it again
        state_file = self.queue.state_file
        try:
            with open(state_file, 'r') as f:
                state_dict = json.load(f)
        except (OSError, ValueError) as e:
            logger.error(
                "Failed to read state file %s for mode injection: %s",
                state_file, e,
                exc_info=True,
            )
            return

        # Inject execution mode
        state_dict["execution_mode"] = self.execution_mode

        # Write back to disk
        try:
            with open(state_file, 'w') as f:
                json.dump(state_dict, f, indent=2)
            logger.debug(
                "Saved state with execution_mode '%s' to %s",
                self.execution_mode,
                state_file,
            )
        except OSError as e:
            logger.error(
                "Failed to write state file %s: %s",
                state_file, e,
                exc_info=True,
            )

    # -----------------------------------------------------------------------
    # SeedContext Lifecycle Management (SeedContext-002 through -006)
    # -----------------------------------------------------------------------

    def _init_seed_context(self, **kwargs: Any) -> None:
        """Initialize seed context. Called during setup phase.

        Raises RuntimeError if called after the seed context has been frozen
        (i.e., after execution has begun), preventing accidental re-initialization.

        Raises RuntimeError if a seed context already exists (including one
        created by lazy initialization), to surface missing-init bugs early
        rather than silently replacing context.

        Args:
            **kwargs: Fields to populate in SeedContext
                (execution_mode, onboarding_metadata, architectural_context,
                design_calibration, generation_provenance)
        """
        if self._seed_context is not None:
            if self._seed_context.is_frozen:
                raise RuntimeError(
                    "Cannot re-initialize SeedContext after execution has begun "
                    "(context is frozen)"
                )
            raise RuntimeError(
                "SeedContext already initialized; cannot re-initialize. "
                "Use update_context() to modify fields during setup phase."
            )
        self._seed_context = SeedContext(**kwargs)
        logger.debug(
            "SeedContext initialized",
            extra={
                "seed_exec_mode": self._seed_context.execution_mode,
                "seed_has_onboarding": self._seed_context.onboarding_metadata is not None,
                "seed_has_arch_ctx": self._seed_context.architectural_context is not None,
                "seed_has_calibration": self._seed_context.design_calibration is not None,
                "seed_has_provenance": self._seed_context.generation_provenance is not None,
            }
        )

    @property
    def seed_context(self) -> SeedContext:
        """Access the full seed context container.

        If _init_seed_context was never called, this lazily creates a default
        standalone SeedContext. Note: this means a missing _init_seed_context
        call silently degrades to standalone mode rather than failing. This is
        intentional for backward compatibility but callers should prefer
        explicit initialization via _init_seed_context().
        """
        if self._seed_context is None:
            logger.debug(
                "SeedContext accessed before explicit initialization; "
                "creating default standalone context"
            )
            self._seed_context = SeedContext()  # standalone default
        return self._seed_context

    def update_context(self, **kwargs: Any) -> None:
        """Update seed context fields during setup phase (before freeze).

        Provides a clean write path without requiring callers to reach into
        the private _seed_context attribute directly.

        Raises AttributeError if the context is frozen.
        Raises AttributeError if an unknown field name is provided.

        Args:
            **kwargs: Fields to update (execution_mode, onboarding_metadata,
                architectural_context, design_calibration, generation_provenance)

        Example:
            contractor.update_context(
                onboarding_metadata={"project": "test"},
                architectural_context={"patterns": ["strategy"]},
            )
        """
        ctx = self.seed_context  # ensure initialized
        valid_fields = {f.name for f in dataclasses.fields(ctx) if not f.name.startswith('_')}
        for key, value in kwargs.items():
            if key not in valid_fields:
                raise AttributeError(
                    f"Unknown SeedContext field: '{key}'. "
                    f"Valid fields: {sorted(valid_fields)}"
                )
            setattr(ctx, key, value)  # will raise if frozen

    def _sync_legacy_attributes(self) -> None:
        """Sync legacy ad-hoc attributes to SeedContext for backward compatibility.

        Called at setup boundary to ensure any code that assigned to
        self.seed_onboarding, self.seed_architectural_context, etc. directly
        is reflected in the typed SeedContext container.

        This is a one-time sync; post-execution updates to legacy attributes
        are ignored (they do not affect the frozen SeedContext).
        """
        try:
            if self.seed_onboarding and not self.seed_context.onboarding_metadata:
                self.seed_context.onboarding_metadata = self.seed_onboarding
                logger.debug("Synced legacy seed_onboarding to SeedContext")
            if self.seed_architectural_context and not self.seed_context.architectural_context:
                self.seed_context.architectural_context = self.seed_architectural_context
                logger.debug("Synced legacy seed_architectural_context to SeedContext")
            if self.seed_design_calibration and not self.seed_context.design_calibration:
                self.seed_context.design_calibration = self.seed_design_calibration
                logger.debug("Synced legacy seed_design_calibration to SeedContext")
        except AttributeError:
            # Already frozen, ignore
            pass

    def load_seed_context(
        self,
        seed_data: Dict[str, Any],
        cli_mode: Optional[str] = None,
        seed_path: Optional[str] = None,
    ) -> None:
        """Load seed context from raw seed data with mode auto-detection.

        Extracts context fields from the seed dictionary, auto-detects
        execution mode from seed signals (unless cli_mode overrides), and
        initializes the SeedContext container. Also populates backward-compat
        legacy attributes and loads plan document text if referenced.

        This replaces the ad-hoc pattern of assigning workflow.seed_onboarding,
        workflow.seed_architectural_context, etc. in runner scripts.

        Args:
            seed_data: Raw seed JSON dictionary (from prime-context-seed.json).
            cli_mode: CLI-specified execution mode override ('standalone' or
                'pipeline'). When None, mode is auto-detected from seed signals.
            seed_path: Path to the seed file, stashed for postmortem use.
        """
        # Stash seed path for postmortem requirement matching
        if seed_path:
            self._seed_path = str(seed_path)

        # Extract context fields
        onboarding = seed_data.get("onboarding") or {}
        architectural_context = seed_data.get("architectural_context") or {}
        design_calibration = seed_data.get("design_calibration") or {}
        service_metadata = seed_data.get("service_metadata") or {}
        forward_manifest = seed_data.get("forward_manifest")  # REQ-PC-FM-002

        # Determine execution mode
        if cli_mode is not None:
            if cli_mode not in VALID_EXECUTION_MODES:
                raise ValueError(
                    f"Invalid cli_mode {cli_mode!r}; "
                    f"expected one of {sorted(VALID_EXECUTION_MODES)}"
                )
            mode = cli_mode
        else:
            has_pipeline_signals = bool(
                onboarding or architectural_context or design_calibration
            )
            mode = "pipeline" if has_pipeline_signals else "standalone"

        logger.info(
            "Execution mode: %s%s",
            mode,
            " (CLI override)" if cli_mode else " (auto-detected)",
        )

        # Initialize SeedContext (typed container)
        self._init_seed_context(
            execution_mode=mode,
            onboarding_metadata=onboarding or None,
            architectural_context=architectural_context or None,
            design_calibration=design_calibration or None,
        )

        # Backward-compat legacy attributes (deprecated)
        self.seed_onboarding = onboarding
        self.seed_architectural_context = architectural_context
        self.seed_design_calibration = design_calibration
        self.seed_service_metadata = service_metadata
        self.seed_forward_manifest = forward_manifest if isinstance(forward_manifest, dict) else None

        # Deserialize raw dict to ForwardManifest once at load time (REQ-MP-701).
        # Stored separately from seed_forward_manifest (raw dict kept for
        # backward compatibility with context strategies).
        self._forward_manifest = None
        if self.seed_forward_manifest:
            try:
                from startd8.forward_manifest import ForwardManifest

                self._forward_manifest = ForwardManifest.model_validate(
                    self.seed_forward_manifest
                )
                logger.info(
                    "ForwardManifest deserialized: %d file specs, %d contracts",
                    len(self._forward_manifest.file_specs),
                    len(self._forward_manifest.contracts),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to deserialize ForwardManifest, "
                    "micro-prime will delegate to fallback: %s",
                    exc,
                )

        # Fallback SOURCE_RECONCILE: enrich manifest with AST if not already done
        if (
            self._forward_manifest is not None
            and "SOURCE_RECONCILE" not in self._forward_manifest.stages_completed
        ):
            try:
                from startd8.forward_manifest_extractor import (
                    SourceReconcileConfig,
                    SourceReconciler,
                )

                all_targets = list({
                    f
                    for feat in self.queue.features.values()
                    for f in (feat.target_files or [])
                })
                # INV-12: When force_regenerate is set, exclude target files
                # to prevent prior-run output from contaminating the manifest.
                reconcile_config = SourceReconcileConfig()
                if self.force_regenerate:
                    reconcile_config.exclude_files = set(all_targets)
                    logger.info(
                        "Fallback SOURCE_RECONCILE: --force-regenerate excludes %d target files",
                        len(all_targets),
                    )
                reconciler = SourceReconciler()
                stats = reconciler.reconcile(
                    self._forward_manifest, self.project_root, all_targets,
                    config=reconcile_config,
                )
                self._forward_manifest.stages_completed.append("SOURCE_RECONCILE")
                logger.info(
                    "Fallback SOURCE_RECONCILE: +%d elements, +%d imports from %d files",
                    stats.elements_added,
                    stats.imports_added,
                    stats.files_scanned,
                )
            except Exception as exc:
                logger.warning("Fallback SOURCE_RECONCILE failed: %s", exc, exc_info=True)

        # FR-MPA-007: Extract pre-rendered skeleton sources from seed artifacts
        # so MicroPrimeCodeGenerator can skip _generate_skeletons() fallback.
        self._skeleton_sources: dict[str, str] = (
            (seed_data.get("artifacts") or {}).get("skeleton_sources") or {}
        )
        if self._skeleton_sources:
            logger.info(
                "Loaded %d pre-rendered skeleton source(s) from seed",
                len(self._skeleton_sources),
            )

        # Plan document text (not part of SeedContext — load if referenced)
        plan_doc_path = (seed_data.get("artifacts") or {}).get(
            "plan_document_path"
        )
        self.plan_document_text = None
        if plan_doc_path:
            resolved = Path(plan_doc_path).resolve()
            # Validate against project_root to prevent path traversal [O11Y Leg 8 #5]
            if not str(resolved).startswith(str(self.project_root.resolve())):
                logger.warning(
                    "Plan document path %s is outside project root %s — skipping",
                    plan_doc_path, self.project_root,
                )
            else:
                try:
                    _text = resolved.read_text(encoding="utf-8")
                    # Cap at 16KB (PC-B5) to reduce spec prompt tokens
                    self.plan_document_text = _text[:_PLAN_LOAD_MAX_BYTES]
                except OSError as exc:
                    logger.warning(
                        "Could not load plan document %s: %s", plan_doc_path, exc,
                    )

    @property
    def execution_mode(self) -> str:
        """Execution mode from seed context (via property accessor)."""
        return self.seed_context.execution_mode

    @property
    def onboarding_metadata(self) -> Optional[Dict[str, Any]]:
        """Onboarding metadata from seed context (via property accessor)."""
        return self.seed_context.onboarding_metadata

    @property
    def architectural_context(self) -> Optional[Dict[str, Any]]:
        """Architectural context from seed context (via property accessor)."""
        return self.seed_context.architectural_context

    @property
    def design_calibration(self) -> Optional[Dict[str, Any]]:
        """Design calibration from seed context (via property accessor)."""
        return self.seed_context.design_calibration

    @property
    def generation_provenance(self) -> Optional[Dict[str, Any]]:
        """Generation provenance from seed context (via property accessor)."""
        return self.seed_context.generation_provenance

    # -----------------------------------------------------------------------
    # Context building is now delegated to self._context_strategy via
    # resolve_task_context() — see develop_feature(). Phase 2 wiring.
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Phase 4: Generation Manifest, Staleness Detection, Validation Hookpoint
    # -----------------------------------------------------------------------

    _MANIFEST_SCHEMA_VERSION = "1.0.0"
    _MANIFEST_FILENAME = "generation-manifest.json"

    def _compute_source_checksum(self) -> str:
        """Compute SHA-256 of canonical seed JSON for staleness detection.

        Uses sorted keys for canonical representation so that logically
        identical seeds produce the same checksum regardless of dict ordering.
        """
        seed_dict = self.seed_context.to_dict() if self._seed_context else {}
        canonical = json.dumps(seed_dict, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _manifest_path(self) -> Path:
        """Return the path to the generation manifest file."""
        return self.project_root / ".startd8" / self._MANIFEST_FILENAME

    def _read_existing_manifest(self) -> Optional[Dict[str, Any]]:
        """Read existing generation manifest, returning None if absent or corrupt."""
        path = self._manifest_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Could not read generation manifest at %s: %s",
                path, exc,
            )
            return None

    def _check_staleness(self, feature: FeatureSpec) -> bool:
        """Check if a feature can be reused from a previous generation.

        Returns True if the feature should be regenerated, False if cached
        results can be reused.

        Conditions for reuse (all must hold):
        - Pipeline mode active
        - force_regenerate is False
        - Existing manifest exists and is parsable
        - source_checksum matches current seed's checksum
        - Feature ID appears in the manifest's feature list

        Returns:
            True if feature needs regeneration, False if cache is valid.
        """
        if self.force_regenerate:
            logger.info(
                "Staleness check: forced regeneration for '%s'", feature.name,
            )
            return True

        if self.execution_mode != ExecutionMode.PIPELINE.value:
            return True  # Standalone always regenerates

        manifest = self._read_existing_manifest()
        if manifest is None:
            logger.info("Staleness check: no provenance — regenerating '%s'", feature.name)
            return True

        manifest_checksum = manifest.get("source_checksum")
        if not manifest_checksum:
            logger.info("Staleness check: no checksum in manifest — regenerating '%s'", feature.name)
            return True

        current_checksum = self._compute_source_checksum()
        if manifest_checksum != current_checksum:
            logger.info(
                "Staleness check: stale (checksum mismatch) — regenerating '%s'",
                feature.name,
            )
            return True

        # Check if feature was previously generated
        features_in_manifest = manifest.get("features", {})
        if feature.id not in features_in_manifest:
            logger.info(
                "Staleness check: feature '%s' not in manifest — regenerating",
                feature.name,
            )
            return True

        logger.info("Staleness check: current — reusing cached '%s'", feature.name)
        return False

    def _write_generation_manifest(self, result_dict: Dict[str, Any]) -> None:
        """Write generation manifest to disk (pipeline mode only).

        The manifest captures provenance for staleness detection and
        reproducibility. Written with 0o600 permissions since it contains
        cost data.

        I/O errors are logged but do not fail the workflow.
        """
        if self.execution_mode != ExecutionMode.PIPELINE.value:
            return

        manifest = {
            "schema_version": self._MANIFEST_SCHEMA_VERSION,
            "source_checksum": self._compute_source_checksum(),
            "execution_mode": self.execution_mode,
            "effective_config": {
                "mode": self.execution_mode,
                "strategy": self._context_strategy.mode,
                "dry_run": self.dry_run,
                "max_retries": self.max_retries,
                "check_truncation": self.check_truncation,
            },
            "features": {},
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Per-feature entries from integration history
        for entry in self.integration_history:
            fid = entry.get("feature_id", "")
            if fid:
                manifest["features"][fid] = {
                    "name": entry.get("feature_name", ""),
                    "success": entry.get("success", False),
                    "cost_usd": entry.get("cost_usd", 0.0),
                    "model": entry.get("model", "unknown"),
                }

        path = self._manifest_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(manifest, indent=2, default=str),
                encoding="utf-8",
            )
            # Restrict permissions: cost data is sensitive
            os.chmod(path, 0o600)
            logger.info(
                "Generation manifest written to %s (checksum=%s)",
                path, manifest["source_checksum"][:12],
            )
        except OSError as exc:
            logger.warning(
                "Failed to write generation manifest to %s: %s",
                path, exc,
            )

    def check_git_status(self) -> Tuple[bool, List[str]]:
        """
        Check if git repo is clean (no uncommitted changes).

        Excludes the queue state file (.prime_contractor_state.json) from the
        dirty check — it is written by add_features_from_seed() before run()
        and would always trigger a false positive.

        Returns:
            Tuple of (is_clean, dirty_files)
        """
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, cwd=self.project_root, timeout=300)
        state_basename = self.queue.state_file.name
        dirty_files = [
            line.strip() for line in result.stdout.strip().split('\n')
            if line and not line.strip().endswith(state_basename)
        ]
        return (len(dirty_files) == 0, dirty_files)

    def create_safety_snapshot(self) -> Optional[str]:
        """
        Create a safety snapshot (git stash) before integration.

        Returns:
            Stash reference name if created, None if nothing to stash
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        stash_message = f'prime-contractor-snapshot-{timestamp}'
        result = subprocess.run(['git', 'stash', 'push', '-m', stash_message], capture_output=True, text=True, cwd=self.project_root, timeout=300)
        if 'No local changes to save' in result.stdout:
            return None
        if result.returncode == 0:
            self.stash_ref = stash_message
            return stash_message
        return None

    def get_recovery_status(self) -> Dict:
        """Get current recovery status information."""
        backup_files = list(self.project_root.glob('**/*.backup'))
        snapshot_files = list(self.project_root.rglob('*.pre_integration'))
        result = subprocess.run(['git', 'stash', 'list'], capture_output=True, text=True, cwd=self.project_root, timeout=300)
        stashes = [line for line in result.stdout.strip().split('\n') if line and 'prime-contractor-snapshot' in line]
        return {'stash_ref': self.stash_ref, 'stashes': stashes, 'backup_files': [str(f) for f in backup_files], 'snapshot_files': [str(f) for f in snapshot_files], 'has_recovery_options': bool(stashes or backup_files or snapshot_files)}

    def recover_from_stash(self) -> bool:
        """Recover from the most recent prime-contractor stash."""
        result = subprocess.run(['git', 'stash', 'list'], capture_output=True, text=True, cwd=self.project_root, timeout=300)
        for line in result.stdout.strip().split('\n'):
            if 'prime-contractor-snapshot' in line:
                stash_id = line.split(':')[0]
                logger.info('Recovering from stash: %s', line)
                pop_result = subprocess.run(['git', 'stash', 'pop', stash_id], capture_output=True, text=True, cwd=self.project_root, timeout=300)
                if pop_result.returncode == 0:
                    logger.info('Stash recovery successful')
                    return True
                else:
                    logger.error('Stash recovery failed: %s', pop_result.stderr)
                    return False
        logger.warning('No prime-contractor stash found')
        return False

    def recover_file_from_backup(self, file_path: Path) -> bool:
        """Recover a specific file from its .backup copy."""
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        if not backup_path.exists():
            logger.warning('No backup found: %s', backup_path)
            return False
        shutil.copy2(backup_path, file_path)
        logger.info('Restored %s from %s', file_path, backup_path.name)
        return True

    def pre_flight_validation(self, feature: FeatureSpec) -> Tuple[bool, Optional[Dict]]:
        """
        Perform pre-flight size estimation BEFORE code generation.

        Args:
            feature: Feature specification to validate

        Returns:
            Tuple of (should_proceed, decomposition_info)
        """
        self.instrumentor.emit_span('code_generation.preflight', {'gen_ai.code.feature_name': feature.name, 'gen_ai.code.max_lines_allowed': self.max_lines_per_feature})
        estimate = self.size_estimator.estimate(task=feature.description, inputs={'target_files': feature.target_files, 'required_exports': []})
        self.instrumentor.emit_event('preflight_estimate', {'estimated_lines': estimate.lines, 'estimated_tokens': estimate.tokens, 'complexity': estimate.complexity, 'confidence': estimate.confidence})
        logger.info('Pre-flight size estimation: lines=%d, complexity=%s, confidence=%.0f%%', estimate.lines, estimate.complexity, estimate.confidence * 100, extra={'feature_name': feature.name, 'estimated_lines': estimate.lines, 'complexity': estimate.complexity, 'confidence': estimate.confidence})
        if estimate.lines > self.max_lines_per_feature:
            self.instrumentor.emit_event('preflight_decision', {'decision': 'DECOMPOSE_REQUIRED', 'reason': f'Estimated {estimate.lines} lines exceeds safe limit of {self.max_lines_per_feature}'})
            logger.warning("Estimated output (%d lines) exceeds safe limit (%d) for feature '%s' — consider splitting", estimate.lines, self.max_lines_per_feature, feature.name, extra={'feature_name': feature.name, 'estimated_lines': estimate.lines})
            decomposition_info = {'reason': f'Estimated {estimate.lines} lines exceeds limit of {self.max_lines_per_feature}', 'estimated_lines': estimate.lines, 'suggested_action': 'Split into multiple smaller features'}
            if self.strict_checkpoints:
                return (False, decomposition_info)
        return (True, None)

    def process_feature(self, feature: FeatureSpec) -> bool:
        """
        Process a feature through the full lifecycle.

        If a GENERATED feature has a prior error_message (from a failed
        checkpoint), it is regenerated with the error injected as feedback
        so the LLM can fix the issue rather than blindly retrying the same
        broken code.

        Returns:
            True if the feature was fully processed, False otherwise
        """
        self.instrumentor.emit_insight(insight_type='feature_selected', summary=f'Processing feature: {feature.name}', confidence=1.0, feature_id=feature.id, feature_name=feature.name, current_status=feature.status.value if hasattr(feature.status, 'value') else str(feature.status))
        if len(feature.target_files) > 1 and feature.status == FeatureStatus.PENDING:
            return self._process_decomposed_feature(feature)
        if feature.status == FeatureStatus.PENDING:
            if not self.develop_feature(feature):
                return False
        if feature.status == FeatureStatus.COMPLETE:
            return True  # Dry-run or other early-completion path
        if feature.status == FeatureStatus.GENERATED:
            if self.walkthrough:
                self.queue.complete_feature(feature.id)
                self._save_queue_state_with_mode()
                return True
            if feature.error_message and self.code_generator:
                logger.info("Feature '%s' has prior error — regenerating with feedback: %s", feature.name, feature.error_message, extra={'feature_name': feature.name, 'prior_error': feature.error_message})
                prior_error = feature.error_message
                # REQ-RPL-204: Enrich prior_error with structured repair context
                rc = (feature.metadata or {}).pop("_repair_context", None)
                if rc:
                    prior_error += (
                        f"\n\n[Structured repair context]\n"
                        f"Steps applied: {rc.get('repair_steps_applied', [])}\n"
                        f"Files modified: {rc.get('repair_files_modified', [])}\n"
                        f"Duration: {rc.get('repair_duration_ms', 0):.0f}ms\n"
                        f"Error: {rc.get('repair_error', 'N/A')}"
                    )
                feature.error_message = None
                feature.status = FeatureStatus.PENDING
                # REQ-RPL-500: Tier escalation — if error-informed regen already
                # failed (attempts >= 2), escalate to a higher-capability model.
                escalated = self._maybe_escalate_generator(feature)
                if not self.develop_feature(feature, prior_error=prior_error):
                    if escalated:
                        self._restore_generator()
                    return False
                if escalated:
                    self._restore_generator()
            return self.integrate_feature(feature)
        logger.warning("Feature '%s' in unexpected state: %s", feature.name, feature.status, extra={'feature_name': feature.name, 'status': str(feature.status)})
        return False

    def _process_decomposed_feature(self, feature: FeatureSpec) -> bool:
        """
        Decompose a multi-file feature into sequential single-file sub-features.

        Each sub-feature targets exactly one file, gets the full parent feature
        description as context, and includes a directive to only produce code
        for that file. Sub-features run sequentially so later ones see changes
        from earlier ones on disk.

        Returns:
            True if all sub-features succeeded, False otherwise
        """
        n = len(feature.target_files)
        logger.info("Auto-decomposing '%s' into %d sub-features", feature.name, n, extra={'feature_name': feature.name, 'sub_feature_count': n})
        saved_callback = self.on_feature_complete
        parent_cost = 0.0
        for i, target_file in enumerate(feature.target_files):
            is_last = i == n - 1
            sub_id = f'{feature.id}__part{i + 1}'
            sub_name = f'{feature.name} ({Path(target_file).name})'
            current_content = ''
            target_path = self.project_root / target_file
            if target_path.is_file():
                current_content = target_path.read_text(encoding='utf-8')
            sub_description = f'{feature.description}\n\n---\nIMPORTANT: This is part {i + 1} of {n}. You MUST ONLY output code for the file: {target_file}\nDo NOT output code for any other file.\n\nCURRENT CONTENTS of {target_file}:\n```\n{current_content}\n```'
            sub_feature = FeatureSpec(id=sub_id, name=sub_name, description=sub_description, target_files=[target_file], dependencies=feature.dependencies)
            logger.info('Sub-feature %d/%d: %s', i + 1, n, Path(target_file).name, extra={'feature_name': feature.name, 'sub_index': i + 1, 'target_file': target_file})
            self.on_feature_complete = saved_callback if is_last else None
            if not self.develop_feature(sub_feature):
                self.on_feature_complete = saved_callback
                self.queue.fail_feature(feature.id, f'Sub-feature {sub_id} generation failed')
                return False
            parent_cost += getattr(sub_feature, '_cost_usd', 0.0)
            if not self.walkthrough:
                if not self.integrate_feature(sub_feature):
                    self.on_feature_complete = saved_callback
                    self.queue.fail_feature(feature.id, f'Sub-feature {sub_id} integration failed')
                    return False
        self.on_feature_complete = saved_callback
        feature._cost_usd = parent_cost
        self.queue.complete_feature(feature.id)
        self._save_queue_state_with_mode()
        logger.info("All %d sub-features integrated for '%s'", n, feature.name, extra={'feature_name': feature.name, 'sub_feature_count': n})
        return True

    def _resolve_output_dir(self) -> Path:
        """Resolve the code generator's output_dir to an absolute path.

        Falls back to ``self.project_root / 'generated'`` when no code
        generator is configured or it has no ``output_dir``.
        """
        if self.code_generator and hasattr(self.code_generator, 'output_dir'):
            od = self.code_generator.output_dir
            if od is not None:
                p = Path(od)
                return p if p.is_absolute() else self.project_root / p
        return self.project_root / 'generated'

    def _check_file_provenance(
        self,
        file_paths: List[str],
    ) -> Dict[str, str]:
        """Check provenance/staleness of existing generated files.

        Classifies each file as:
        - "current": file exists and is newer than generation results state
        - "stale": file exists but is older than generation results state
        - "missing": file does not exist or is empty

        Uses mtime of ``.startd8/state/generation_results.json`` as the
        staleness reference.  Used by Mottainai reuse logic to avoid reusing
        stale generated files.
        """
        classifications: Dict[str, str] = {}
        seed_mtime: Optional[float] = None

        # Try generation results state file for mtime comparison
        state_dir = self.project_root / ".startd8" / "state"
        gen_results_path = state_dir / "generation_results.json"
        try:
            seed_mtime = gen_results_path.stat().st_mtime
        except OSError:
            pass

        resolved_output_dir = self._resolve_output_dir()

        for fpath_str in file_paths:
            fpath = Path(fpath_str)
            if not fpath.is_absolute():
                fpath = resolved_output_dir.parent / fpath
            try:
                file_stat = fpath.stat()
            except OSError:
                classifications[fpath_str] = "missing"
                continue

            if file_stat.st_size <= 0:
                classifications[fpath_str] = "missing"
                continue

            if seed_mtime is not None and file_stat.st_mtime < seed_mtime:
                classifications[fpath_str] = "stale"
            else:
                classifications[fpath_str] = "current"

        return classifications

    # ------------------------------------------------------------------
    # Walkthrough Mode: Prompt Persistence
    # ------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Kaizen: Prompt Building and Persistence Helpers (REQ-KZ-200, 201, 202)
    # -----------------------------------------------------------------------

    @staticmethod
    def _sanitize_feature_id(feature_id: str) -> str:
        """Sanitize feature_id for safe use as a filesystem path component.

        Removes path separators and dotdot sequences to prevent path traversal.
        Collapses runs of non-alphanumeric characters (except .-_) to underscores.
        Returns 'unknown' if the result would be empty.

        Returns:
            A filesystem-safe string usable as a single directory name.
        """
        import re as _re
        # Strip leading/trailing whitespace and path separators
        safe = feature_id.strip().strip("/\\")
        # Remove any path separator components (dotdot protection)
        safe = safe.replace("..", "").replace("/", "_").replace("\\", "_")
        # Collapse runs of characters not safe in directory names
        safe = _re.sub(r"[^\w.\-]", "_", safe)
        safe = _re.sub(r"_+", "_", safe).strip("_")
        return safe or "unknown"

    def _build_phase_prompts(
        self,
        feature: "FeatureSpec",
        gen_context: Dict[str, Any],
    ) -> Dict[str, str]:
        """Build all three LeadContractorWorkflow phase prompts as text.

        Returns:
            dict[str, str] mapping filename to content. Keys are:
                - "spec_user_prompt.md"
                - "spec_system_prompt.md"
                - "draft_system_prompt.md"
                - "draft_user_prompt.md"
                - "review_system_prompt.md"
                - "review_user_prompt.md"

        Note: build_spec_prompt mutates a copy of gen_context, so the original
        is passed through a dict() copy internally.
        """
        from ..implementation_engine import spec_builder
        from ..implementation_engine.drafter import (
            get_drafter_system_prompt,
            build_output_format,
            build_existing_files_section,
        )
        from ..implementation_engine.prompts import get_template

        prompts: Dict[str, str] = {}

        # --- Spec phase ---
        try:
            spec_prompt = spec_builder.build_spec_prompt(
                task_description=feature.description,
                context=dict(gen_context),  # copy — build_spec_prompt mutates context
                output_format=None,
            )
        except Exception as exc:
            spec_prompt = f"[Error building spec prompt: {exc}]"
            logger.warning(
                "Prompt build: spec prompt failed for '%s': %s", feature.name, exc,
            )
        prompts["spec_user_prompt.md"] = spec_prompt
        prompts["spec_system_prompt.md"] = (
            "# Spec System Prompt\n\nThe spec phase embeds the role directive "
            "in the user prompt. There is no separate system prompt."
        )

        # --- Draft phase ---
        existing_files = gen_context.get("existing_files")
        draft_system, draft_mode = get_drafter_system_prompt(existing_files=existing_files)
        logger.info("Prompt build: drafter mode=%s for '%s'", draft_mode, feature.name)
        prompts["draft_system_prompt.md"] = draft_system

        is_edit = bool(existing_files)
        template_key = "draft_edit" if is_edit else "draft"
        try:
            draft_template = get_template(template_key)
        except Exception as exc:
            draft_template = f"[Could not load template '{template_key}']"
            logger.warning(
                "Prompt build: draft template '%s' failed for '%s': %s",
                template_key, feature.name, exc, exc_info=True,
            )
        existing_section = build_existing_files_section(existing_files=existing_files)
        output_format = build_output_format(
            target_files=feature.target_files,
            existing_files=existing_files,
        )
        prompts["draft_user_prompt.md"] = (
            f"# Draft User Prompt\n\n"
            f"**Template:** `{template_key}`\n\n"
            f"## Existing Files Section\n\n{existing_section}\n\n"
            f"## Output Format\n\n{output_format}\n\n"
            f"## Template (with placeholders)\n\n"
            f"The `{{spec_output}}` placeholder will be replaced with "
            f"the spec phase output.\n\n"
            f"```\n{draft_template}\n```"
        )

        # --- Review phase ---
        try:
            review_system = get_template("review_system")
        except Exception as exc:
            review_system = "[Could not load review_system template]"
            logger.warning(
                "Prompt build: review_system failed for '%s': %s",
                feature.name, exc, exc_info=True,
            )
        prompts["review_system_prompt.md"] = review_system

        try:
            review_template = get_template("review")
        except Exception as exc:
            review_template = "[Could not load review template]"
            logger.warning(
                "Prompt build: review template failed for '%s': %s",
                feature.name, exc, exc_info=True,
            )
        prompts["review_user_prompt.md"] = (
            f"# Review User Prompt\n\n"
            f"**Template:** `review`\n\n"
            f"The `{{spec_output}}` and `{{implementation}}` placeholders "
            f"will be replaced with actual spec and draft outputs at runtime.\n\n"
            f"```\n{review_template}\n```"
        )

        return prompts

    def _write_prompt_files(
        self,
        output_dir: Path,
        feature: "FeatureSpec",
        prompts: Dict[str, str],
        gen_context: Dict[str, Any],
    ) -> None:
        """Write prompt files and metadata.json to output_dir.

        metadata.json schema (consumed by Layer 6 extract_prompt_characteristics):
            {
                "feature_id": str,
                "feature_name": str,
                "target_files": list[str],
                "context_keys": list[str],       # keys in gen_context at capture time
                "has_existing_files": bool,       # True if target files existed on disk
                "target_file_count": int,         # len(target_files)
                "execution_mode": str,
                "lead_agent_spec": str,
                "drafter_agent_spec": str,
                "timestamp": str,                 # ISO-8601 UTC
            }

        Args:
            output_dir: Directory to write into (must already exist or be createable).
            feature: FeatureSpec being captured.
            prompts: dict[filename, content] from _build_phase_prompts().
            gen_context: Resolved gen_context for this feature (used for metadata only).
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in prompts.items():
            (output_dir / filename).write_text(content, encoding="utf-8")

        is_edit = bool(gen_context.get("existing_files"))
        agent_spec = str(getattr(self.code_generator, "lead_agent", None) or "unknown")
        drafter_spec = str(getattr(self.code_generator, "drafter_agent", None) or "unknown")

        metadata: Dict[str, Any] = {
            "feature_id": feature.id,
            "feature_name": feature.name,
            "target_files": feature.target_files or [],
            "target_file_count": len(feature.target_files or []),
            "context_keys": list(gen_context.keys()),
            "has_existing_files": is_edit,
            "execution_mode": self.execution_mode,
            "lead_agent_spec": agent_spec,
            "drafter_agent_spec": drafter_spec,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, default=str), encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Kaizen: Config Loading and Hint Injection (REQ-KZ-502)
    # -----------------------------------------------------------------------

    #: Maximum prompt hints to inject per phase (REQ-KZ-502 dedup/cap)
    _MAX_KAIZEN_HINTS_PER_PHASE: int = 5

    def _load_kaizen_config(self, path: str) -> Optional[dict]:
        """Load and validate kaizen-config.json. Fail-open (returns None on error).

        Validates schema_version == '1.0' and that prompt_hints is a list.
        Logs a warning and returns None on any error so that the workflow
        continues as if no config were present (REQ-KZ-502 fail-open).
        """
        try:
            config = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                logger.warning("Kaizen config must be a JSON object — ignoring: %s", path)
                return None
            if config.get("schema_version") != "1.0":
                logger.warning(
                    "Kaizen config schema_version != '1.0' — ignoring: %s (got %s)",
                    path, config.get("schema_version"),
                )
                return None
            if "prompt_hints" in config and not isinstance(config["prompt_hints"], list):
                logger.warning("Kaizen config prompt_hints must be a list — ignoring: %s", path)
                return None
            logger.info("Kaizen config loaded: %s (%d hints)", path, len(config.get("prompt_hints") or []))
            return config
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Kaizen config invalid — proceeding without it: %s", exc)
            return None

    def _apply_kaizen_hints(self, gen_context: Dict[str, Any]) -> None:
        """Inject kaizen prompt hints from _kaizen_config into gen_context (REQ-KZ-502).

        Injects all hints regardless of their ``phase`` label, because
        ``generator.generate()`` internally manages all phases (spec, draft, review)
        in a single call; there is no per-phase injection point available here.
        Future work could pass phase-specific contexts if the generator API exposes them.

        Deduplicates by SHA-256 content hash (truncated to 16 hex chars) and
        caps at _MAX_KAIZEN_HINTS_PER_PHASE hints per declared phase bucket to
        avoid overwhelming the prompt.  Hints are injected as
        gen_context[\"kaizen_hints\"], a newline-joined bullet list.

        Failures are non-fatal — logged and silently ignored.
        """
        if not self._kaizen_config:
            return
        try:
            seen_hashes: set = set()
            phase_counts: Dict[str, int] = {}
            hints_collected: list = []

            for h in self._kaizen_config.get("prompt_hints") or []:
                if not isinstance(h, dict):
                    continue
                phase = h.get("phase", "all")
                hint_text = h.get("hint", "")
                if not hint_text:
                    continue
                # Deduplicate by content hash
                content_hash = hashlib.sha256(hint_text.encode("utf-8")).hexdigest()[:16]
                if content_hash in seen_hashes:
                    continue
                seen_hashes.add(content_hash)
                # Per-phase cap
                count = phase_counts.get(phase, 0)
                if count >= self._MAX_KAIZEN_HINTS_PER_PHASE:
                    continue
                phase_counts[phase] = count + 1
                hints_collected.append(hint_text)

            if hints_collected:
                gen_context["kaizen_hints"] = "\n".join(f"- {h}" for h in hints_collected)
                logger.debug(
                    "Kaizen: injected %d hint(s) into gen_context for '%s'",
                    len(hints_collected),
                    gen_context.get("feature_name", "?"),
                )
        except Exception as exc:
            logger.warning("Kaizen: hint injection failed (non-fatal): %s", exc)

    def _persist_kaizen_prompts(
        self,
        feature: "FeatureSpec",
        gen_context: Dict[str, Any],
        result: Optional[Any] = None,
    ) -> None:
        """Persist real-run prompts and LLM responses for Kaizen analysis.

        Captures six prompt files + metadata.json (REQ-KZ-200, 202) and,
        when raw_response data is available in result.metadata, also writes
        redacted response files (REQ-KZ-201).

        Output path: {_kaizen_prompt_dir}/{run_id}/{sanitized_feature_id}/
        The run_id subdirectory provides run isolation (R1-S1).
        Failures are non-fatal — logged and silently swallowed.

        Only called when self._kaizen_enabled is True.
        """
        if not self._kaizen_enabled or self._kaizen_prompt_dir is None:
            return
        try:
            run_id = os.environ.get("KAIZEN_RUN_ID", "standalone")
            safe_fid = self._sanitize_feature_id(feature.id)
            prompt_dir = self._kaizen_prompt_dir / run_id / safe_fid

            # REQ-KZ-BUG-004: Ensure context is JSON serializable (no raw ForwardManifest objects)
            serializable_context = dict(gen_context)
            for key in ["manifest", "forward_manifest"]:
                val = serializable_context.get(key)
                if val is not None and hasattr(val, "dict"):
                    serializable_context[key] = val.dict()

            prompts = self._build_phase_prompts(feature, serializable_context)
            self._write_prompt_files(prompt_dir, feature, prompts, serializable_context)
            if result is not None:
                self._capture_response_files(prompt_dir, feature, result)
            logger.debug(
                "Kaizen: persisted prompts for '%s' -> %s", feature.name, prompt_dir,
            )
        except Exception as exc:
            logger.warning(
                "Kaizen: prompt persistence failed for '%s' (non-fatal): %s",
                feature.name, exc,
            )

    # -----------------------------------------------------------------------
    # Kaizen: Redaction and Response Capture (REQ-KZ-201, 204)
    # -----------------------------------------------------------------------

    @staticmethod
    def _load_redaction_config() -> list:
        """Load redaction patterns from KAIZEN_REDACTIONS env path (REQ-KZ-204).

        Reads a JSON file whose path is in the KAIZEN_REDACTIONS env var.
        Expected format: list of regex strings, or a dict with a 'patterns' key.
        On any error (missing env, bad path, bad JSON, bad type) logs a warning
        and returns an empty list (fail-safe, not fail-closed).

        Returns:
            List of raw regex pattern strings.
        """
        import re as _re
        redactions_path = os.environ.get("KAIZEN_REDACTIONS", "").strip()
        if not redactions_path:
            return []
        path = Path(redactions_path)
        if not path.is_file():
            logger.warning(
                "Kaizen: KAIZEN_REDACTIONS points to missing file '%s' — no redaction applied",
                redactions_path,
            )
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Kaizen: failed to parse KAIZEN_REDACTIONS file '%s': %s — no redaction applied",
                redactions_path, exc,
            )
            return []
        if isinstance(raw, dict):
            raw = raw.get("patterns", [])
        if not isinstance(raw, list):
            logger.warning(
                "Kaizen: KAIZEN_REDACTIONS must be a JSON list or {patterns:[...]} — got %s",
                type(raw).__name__,
            )
            return []
        # Validate each entry is a compilable regex string
        patterns: list = []
        for entry in raw:
            if not isinstance(entry, str):
                logger.warning("Kaizen: skipping non-string pattern %r in redaction config", entry)
                continue
            try:
                _re.compile(entry)  # validate only; compiled lazily in _apply_redaction
            except _re.error as exc:
                logger.warning("Kaizen: invalid redaction pattern %r: %s", entry, exc)
                continue
            patterns.append(entry)
        return patterns

    @staticmethod
    def _apply_redaction(text: str, patterns: list) -> str:
        """Apply redaction patterns to text, replacing matches with [REDACTED] (REQ-KZ-204).

        Args:
            text: The raw text to redact.
            patterns: List of raw regex strings from _load_redaction_config().
                      An empty list is a no-op.

        Returns:
            Redacted string. The original is not mutated.
        """
        if not patterns:
            return text
        import re as _re
        result = text
        for raw_pattern in patterns:
            try:
                result = _re.sub(raw_pattern, "[REDACTED]", result)
            except _re.error as exc:
                # Pattern compiled successfully at load time; sub errors are defensive
                logger.warning("Kaizen: redaction pattern %r failed during apply: %s", raw_pattern, exc)
        return result

    #: Maximum bytes to write for a single raw response (2 MB — REQ-KZ-201)
    _KAIZEN_RESPONSE_MAX_BYTES: int = 2 * 1024 * 1024
    #: Sentinel appended when a response is truncated (REQ-KZ-201)
    _KAIZEN_TRUNCATION_SENTINEL: str = "\n\n[KAIZEN: response truncated — exceeded 2 MiB capture limit]"

    def _capture_response_files(
        self,
        prompt_dir: Path,
        feature: "FeatureSpec",
        result: Any,
    ) -> None:
        """Write raw LLM response file(s) from result.metadata (REQ-KZ-201, 204).

        Reads result.metadata.get('raw_response') or per-phase keys
        ('spec_raw_response', 'draft_raw_response', 'review_raw_response').
        Applies:
          - Encoding guard: any bytes decoded as UTF-8 replacing errors (R2-S9)
          - 2 MiB size guard with truncation sentinel (REQ-KZ-201)
          - Redaction before write (R2-S3)
        Writes a sidecar .meta.json with truncated/size info alongside each response.

        Failures are non-fatal — swallowed by the caller's try/except.
        """
        metadata: Dict[str, Any] = getattr(result, "metadata", {}) or {}
        redaction_patterns = self._load_redaction_config()

        # Support per-phase keys and a single aggregate key
        phase_keys = {
            "spec": metadata.get("spec_raw_response"),
            "draft": metadata.get("draft_raw_response"),
            "review": metadata.get("review_raw_response"),
        }
        # Fall back to single aggregate response if no per-phase data
        if not any(v for v in phase_keys.values()):
            aggregate = metadata.get("raw_response")
            if aggregate is not None:
                phase_keys = {"draft": aggregate}  # attribute to draft phase by convention

        for phase, raw in phase_keys.items():
            if raw is None:
                continue

            # --- Encoding guard (R2-S9) ---
            if isinstance(raw, bytes):
                text = raw.decode("utf-8", errors="replace")
            elif isinstance(raw, str):
                # Round-trip through bytes to normalize surrogates / replacement chars
                text = raw.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            else:
                logger.warning(
                    "Kaizen: raw_response for phase '%s' of '%s' has unexpected type %s — skipping",
                    phase, feature.name, type(raw).__name__,
                )
                continue

            # --- 2 MiB size guard (REQ-KZ-201) ---
            raw_bytes = text.encode("utf-8")
            truncated = len(raw_bytes) > self._KAIZEN_RESPONSE_MAX_BYTES
            if truncated:
                # Truncate at byte boundary, decode back
                text = raw_bytes[: self._KAIZEN_RESPONSE_MAX_BYTES].decode(
                    "utf-8", errors="replace"
                ) + self._KAIZEN_TRUNCATION_SENTINEL

            # --- Redaction before write (R2-S3) ---
            text = self._apply_redaction(text, redaction_patterns)

            # Write response file
            response_path = prompt_dir / f"{phase}_response.md"
            response_path.write_text(text, encoding="utf-8")

            # Write sidecar meta
            meta_path = prompt_dir / f"{phase}_response.meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "phase": phase,
                        "feature_id": feature.id,
                        "original_bytes": len(raw_bytes),
                        "captured_bytes": len(text.encode("utf-8")),
                        "truncated": truncated,
                        "redaction_patterns_applied": len(redaction_patterns),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    def _persist_walkthrough_prompts(
        self,
        feature: FeatureSpec,
        gen_context: dict[str, Any] | None = None,
    ) -> None:
        """Persist all LLM prompts for a feature without making LLM calls.

        Captures the 3 LeadContractorWorkflow phases (spec, draft, review)
        as markdown files plus a metadata.json summary.

        Args:
            feature: The feature spec to persist prompts for.
            gen_context: Optional generation context dict containing
                existing_files, design_doc_sections, etc.

        Output directory: .startd8/walkthrough/prime/{feature.id}/
        """
        if gen_context is None:
            gen_context = {}
        wt_dir = self.project_root / ".startd8" / "walkthrough" / "prime" / feature.id
        wt_dir.mkdir(parents=True, exist_ok=True)

        # Local imports to avoid circular deps (matches existing pattern)
        from ..implementation_engine import spec_builder
        from ..implementation_engine.drafter import (
            get_drafter_system_prompt,
            build_output_format,
            build_existing_files_section,
        )
        from ..implementation_engine.prompts import get_template

        # --- Spec phase ---
        try:
            # build_spec_prompt pops keys from context, so pass a copy
            spec_prompt = spec_builder.build_spec_prompt(
                task_description=feature.description,
                context=dict(gen_context),
                output_format=None,
            )
        except Exception as exc:
            spec_prompt = f"[Error building spec prompt: {exc}]"
            logger.warning(
                "Walkthrough: spec prompt build failed for '%s': %s",
                feature.name, exc,
            )

        (wt_dir / "spec_user_prompt.md").write_text(spec_prompt, encoding="utf-8")
        (wt_dir / "spec_system_prompt.md").write_text(
            "# Spec System Prompt\n\nThe spec phase embeds the role directive "
            "in the user prompt. There is no separate system prompt.",
            encoding="utf-8",
        )

        # --- Draft phase ---
        existing_files = gen_context.get("existing_files")
        draft_system, draft_mode = get_drafter_system_prompt(existing_files=existing_files)
        logger.info("Walkthrough: drafter mode=%s for '%s'", draft_mode, feature.name)
        (wt_dir / "draft_system_prompt.md").write_text(
            draft_system, encoding="utf-8",
        )

        is_edit = bool(existing_files)
        template_key = "draft_edit" if is_edit else "draft"
        try:
            draft_template = get_template(template_key)
        except Exception as exc:
            draft_template = f"[Could not load template '{template_key}']"
            logger.warning(
                "Walkthrough: draft template '%s' load failed for '%s': %s",
                template_key, feature.name, exc, exc_info=True,
            )

        existing_section = build_existing_files_section(
            existing_files=existing_files,
        )
        output_format = build_output_format(
            target_files=feature.target_files,
            existing_files=existing_files,
        )
        draft_user = (
            f"# Draft User Prompt\n\n"
            f"**Template:** `{template_key}`\n\n"
            f"## Existing Files Section\n\n{existing_section}\n\n"
            f"## Output Format\n\n{output_format}\n\n"
            f"## Template (with placeholders)\n\n"
            f"The `{{spec_output}}` placeholder will be replaced with "
            f"the spec phase output.\n\n"
            f"```\n{draft_template}\n```"
        )
        (wt_dir / "draft_user_prompt.md").write_text(
            draft_user, encoding="utf-8",
        )

        # --- Review phase ---
        try:
            review_system = get_template("review_system")
        except Exception as exc:
            review_system = "[Could not load review_system template]"
            logger.warning(
                "Walkthrough: review_system template load failed for '%s': %s",
                feature.name, exc, exc_info=True,
            )
        (wt_dir / "review_system_prompt.md").write_text(
            review_system, encoding="utf-8",
        )

        try:
            review_template = get_template("review")
        except Exception as exc:
            review_template = "[Could not load review template]"
            logger.warning(
                "Walkthrough: review template load failed for '%s': %s",
                feature.name, exc, exc_info=True,
            )
        review_user = (
            f"# Review User Prompt\n\n"
            f"**Template:** `review`\n\n"
            f"The `{{spec_output}}` and `{{implementation}}` placeholders "
            f"will be replaced with actual spec and draft outputs at "
            f"runtime.\n\n"
            f"```\n{review_template}\n```"
        )
        (wt_dir / "review_user_prompt.md").write_text(
            review_user, encoding="utf-8",
        )

        # --- Metadata ---
        agent_spec = str(getattr(self.code_generator, "lead_agent", None) or "unknown")
        drafter_spec = str(getattr(self.code_generator, "drafter_agent", None) or "unknown")

        metadata = {
            "feature_id": feature.id,
            "feature_name": feature.name,
            "target_files": feature.target_files,
            "lead_agent_spec": agent_spec,
            "drafter_agent_spec": drafter_spec,
            "context_keys": list(gen_context.keys()),
            "has_existing_files": is_edit,
            "execution_mode": self.execution_mode,
        }
        (wt_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, default=str), encoding="utf-8",
        )

        logger.info(
            "Walkthrough: persisted prompts for '%s' -> %s",
            feature.name, wt_dir,
        )

    def develop_feature(self, feature: FeatureSpec, prior_error: Optional[str]=None) -> bool:
        """
        Develop a feature using the configured CodeGenerator.

        Args:
            prior_error: If provided, error feedback from a previous failed
                attempt (e.g., checkpoint lint/import errors). Injected into
                the generation context so the LLM can avoid the same mistake.

        Returns:
            True if code generation succeeded, False otherwise
        """
        is_retry = prior_error is not None
        label = 'RE-DEVELOPING' if is_retry else 'DEVELOPING'
        logger.info('%s FEATURE: %s', label, feature.name, extra={'feature_name': feature.name, 'feature_id': feature.id, 'is_retry': is_retry})
        should_proceed, decomposition_info = self.pre_flight_validation(feature)
        if not should_proceed:
            reason = decomposition_info.get('reason', 'Size exceeds safe limits')
            logger.error("Pre-flight failed for '%s': %s", feature.name, reason, extra={'feature_name': feature.name, 'reason': reason})
            self.queue.fail_feature(feature.id, f"Pre-flight failed: {decomposition_info.get('reason')}")
            return False
        self.queue.start_feature(feature.id)
        # Phase 0 (REQ-MP-1002): File copy early-exit for identical-copy tasks.
        # If copy_source_task_id is not already set, attempt detection from
        # description signals + depends_on.  This bridges the gap where plan
        # ingestion produces "Identical copy" language but doesn't set the
        # explicit field.
        if feature.copy_source_task_id is None:
            from .copy_detection import detect_copy_task

            predecessor = None
            deps = feature.dependencies or []
            if len(deps) == 1:
                predecessor = self.queue.get_feature(deps[0])
            copy_source = detect_copy_task(feature, predecessor=predecessor)
            if copy_source is not None:
                feature.copy_source_task_id = copy_source.predecessor_id
                if copy_source.source_file:
                    feature.copy_source_file = copy_source.source_file
                logger.info(
                    "Copy detection: '%s' identified as identical copy of '%s'",
                    feature.name, copy_source.predecessor_id,
                )
        if feature.copy_source_task_id is not None:
            try:
                copy_result = self._handle_file_copy(feature)
                if copy_result is not None:
                    feature.generated_files = [str(f) for f in copy_result.generated_files]
                    feature.status = FeatureStatus.GENERATED
                    self._save_queue_state_with_mode()
                    self.total_cost_usd += copy_result.cost_usd  # 0.0
                    logger.info(
                        "File copy completed for '%s' from predecessor '%s': cost=$0.00",
                        feature.name, feature.copy_source_task_id,
                    )
                    return True
            except (ValueError, FileNotFoundError, TimeoutError, OSError) as exc:
                logger.error(
                    "File copy failed for '%s': %s", feature.name, exc,
                    exc_info=True,
                )
                self.queue.fail_feature(feature.id, f"File copy failed: {exc}")
                return False
        # REQ-MP-1003: Detect copy-and-modify tasks — inject predecessor as reference.
        self._inject_copy_and_modify_context(feature)

        if self.dry_run:
            logger.info("[DRY RUN] Would generate code for '%s': %s...", feature.name, feature.description[:100], extra={'feature_name': feature.name, 'dry_run': True})
            simulated_files = [f'generated/{feature.id}/{Path(t).name}' for t in feature.target_files] if feature.target_files else [f'generated/{feature.id}/code.py']
            feature.generated_files = simulated_files
            feature.status = FeatureStatus.GENERATED
            self._save_queue_state_with_mode()
            return True
        if not self.code_generator:
            logger.error("No code generator configured for feature '%s'", feature.name)
            self.queue.fail_feature(feature.id, 'No code generator configured')
            return False
        logger.info("Running code generation for '%s'...", feature.name)
        try:
            # Mottainai Gap 14: skip generation if files already exist on disk.
            # Now with provenance/staleness awareness (Task 6).
            if feature.generated_files and not self.force_regenerate:
                provenance = self._check_file_provenance(feature.generated_files)
                all_current = all(v == "current" for v in provenance.values())
                has_stale = any(v == "stale" for v in provenance.values())
                has_missing = any(v == "missing" for v in provenance.values())

                if all_current:
                    preview = feature.generated_files[:3]
                    suffix = f" ... (+{len(feature.generated_files) - 3})" if len(feature.generated_files) > 3 else ""
                    logger.info(
                        "Mottainai: reusing %d existing generated file(s) for '%s': %s%s",
                        len(feature.generated_files), feature.name, preview, suffix,
                    )
                    feature.status = FeatureStatus.GENERATED
                    self.queue.save_state()
                    return True
                elif has_stale and not has_missing:
                    stale_files = [f for f, v in provenance.items() if v == "stale"]
                    logger.warning(
                        "Mottainai: %d stale file(s) for '%s' — regenerating: %s",
                        len(stale_files), feature.name, stale_files[:3],
                    )
                elif has_missing:
                    missing = [f for f, v in provenance.items() if v == "missing"]
                    logger.info(
                        "Mottainai: %d missing file(s) for '%s' — generating: %s",
                        len(missing), feature.name, missing[:3],
                    )

            # Build gen_context via strategy (Phase 2: FR-004/FR-005/FR-006)
            self._current_enrichment = None
            domain_constraints_list = None
            output_constraint_str = None
            if feature.target_files:
                enrichment = self._get_domain_enrichment(feature)
                if enrichment is not None:
                    self._current_enrichment = enrichment
                    domain_constraints_list = enrichment.prompt_constraints
                    logger.info("Domain constraints applied for '%s': %d constraints (domain=%s)", feature.name, len(enrichment.prompt_constraints), enrichment.domain.value, extra={'feature_name': feature.name, 'domain': enrichment.domain.value})
                else:
                    from startd8.workflows.builtin.prompts import get_template as _get_ctx_template
                    output_constraint_str = _get_ctx_template("prime_context", "output_constraint").strip()

            # Pre-format prior error feedback (prompt template dependency stays here)
            prior_error_feedback = None
            if prior_error:
                from startd8.workflows.builtin.prompts import format_prompt as _fmt_ctx
                prior_error_feedback = _fmt_ctx(
                    "prime_context", "prior_error_feedback", prior_error=prior_error,
                ).strip()

            # Assemble seed data dict for strategy (avoids SeedContext import cycle)
            seed_data = {
                "onboarding_metadata": self.onboarding_metadata,
                "architectural_context": self.architectural_context,
                "design_calibration": self.design_calibration,
                "plan_document_text": self.plan_document_text,
                "service_metadata": self.seed_service_metadata,
                "forward_manifest": self.seed_forward_manifest,  # REQ-PC-FM-003
            }
            feature_data = {
                "name": feature.name,
                "id": feature.id,
                "target_files": feature.target_files,
                "description": feature.description,
                "metadata": feature.metadata,
            }

            gen_context = self._context_strategy.resolve_task_context(
                feature_data=feature_data,
                seed_data=seed_data,
                domain_constraints=domain_constraints_list,
                output_constraint=output_constraint_str,
                prior_error_feedback=prior_error_feedback,
            )

            # REQ-PEM-008: Thread validation flag to LeadContractorWorkflow
            # for spec-to-draft validation gating. Pipeline mode enables it;
            # standalone skips (consistent with ModeConfig.enable_post_validation).
            # CLI --validate/--no-validate override the mode default.
            if self._validation_override is not None:
                gen_context["_run_validators"] = self._validation_override
            else:
                gen_context["_run_validators"] = (
                    self.execution_mode == ExecutionMode.PIPELINE.value
                )

            # Log service metadata injection (kept at workflow level for observability)
            if self.seed_service_metadata and "service_metadata" in gen_context:
                logger.info(
                    "Context injection: service_metadata for '%s' (transport=%s, deps=%d)",
                    feature.name,
                    self.seed_service_metadata.get('transport_protocol', 'unset'),
                    len(self.seed_service_metadata.get('runtime_dependencies', [])),
                )

            logger.info(
                "Context resolved via %s strategy for '%s' (%d keys)",
                self._context_strategy.mode,
                feature.name,
                len(gen_context),
                extra={"strategy_mode": self._context_strategy.mode, "context_keys": list(gen_context.keys())},
            )

            # PC-O1: Populate existing_files for edit tasks when target_files exist
            self._populate_existing_files(feature, gen_context)

            # REQ-MP-701: Forward deserialized ForwardManifest for Micro Prime
            if self._forward_manifest is not None:
                gen_context["manifest"] = self._forward_manifest

            # FR-MPA-007: Forward pre-rendered skeletons from seed so
            # MicroPrimeCodeGenerator skips _generate_skeletons() fallback.
            if self._skeleton_sources and "skeletons" not in gen_context:
                gen_context["skeletons"] = dict(self._skeleton_sources)

            # REQ-DDS-002: Thread design_doc_sections from feature metadata
            _design_sections = feature.metadata.get("design_doc_sections", [])
            if _design_sections:
                gen_context["design_doc_sections"] = _design_sections

            # Walkthrough mode: persist prompts, skip LLM calls
            if self.walkthrough:
                self._persist_walkthrough_prompts(feature, gen_context)
                feature.generated_files = [
                    f"walkthrough/{feature.id}/{Path(t).name}"
                    for t in feature.target_files
                ] if feature.target_files else [
                    f"walkthrough/{feature.id}/code.py"
                ]
                feature.status = FeatureStatus.GENERATED
                self._save_queue_state_with_mode()
                return True

            # REQ-MP-1003: Thread reference_implementation into gen_context
            ref_impl = feature.metadata.get("_reference_implementation") if feature.metadata else None
            if ref_impl:
                gen_context["reference_implementation"] = ref_impl
                logger.info(
                    "Injected reference_implementation for '%s' (%d chars)",
                    feature.name, len(ref_impl),
                )

            # Kaizen prompt hints injection (REQ-KZ-502) — non-fatal, hints added to gen_context
            if self._kaizen_config:
                self._apply_kaizen_hints(gen_context)

            # Kaizen: persist real-run prompts (REQ-KZ-200) — non-fatal
            # Captured here even if cached, so we have the prompt for correlation analysis.
            self._persist_kaizen_prompts(feature, gen_context, result=None)

            # Phase 4: Staleness detection — skip generation if cached result is current
            if not self._check_staleness(feature):
                feature.status = FeatureStatus.GENERATED
                self._save_queue_state_with_mode()
                return gen_context

            # Phase 5: Complexity routing — select tier-specific generator
            generator = self.code_generator
            if self._complexity_routing_enabled and self._complexity_router is not None:
                try:
                    from startd8.complexity import (
                        classify_tier,
                        extract_signals_from_feature,
                    )

                    signals = extract_signals_from_feature(
                        feature, self.project_root,
                    )
                    tier, reason = classify_tier(signals, self._complexity_config)
                    generator = self._complexity_router.select(tier) or generator
                    # Stash classification in feature metadata for forensics
                    if feature.metadata is None:
                        feature.metadata = {}
                    feature.metadata["_complexity_tier"] = tier.value
                    feature.metadata["_complexity_reason"] = reason
                    feature.metadata["_complexity_signals"] = signals.to_dict()
                    logger.info(
                        "Complexity routing for '%s': tier=%s, reason=%s",
                        feature.name,
                        tier.value,
                        reason,
                    )
                except Exception as exc:  # Catch-all: graceful fallback to default generator
                    logger.warning(
                        "Complexity routing failed for '%s', using default generator: %s",
                        feature.name,
                        exc,
                        exc_info=True,
                    )

            result: GenerationResult = generator.generate(
                task=feature.description,
                context=gen_context,
                target_files=feature.target_files,
            )

            # Kaizen: persist real-run prompts + responses (REQ-KZ-200, 201) — non-fatal
            # Captured regardless of success/fail so we can analyze why it failed.
            self._persist_kaizen_prompts(feature, gen_context, result=result)

            if result.success:
                feature.generated_files = [str(f) for f in result.generated_files]
                feature.status = FeatureStatus.GENERATED
                self._save_queue_state_with_mode()
                self.total_cost_usd += result.cost_usd
                self.total_input_tokens += result.input_tokens
                self.total_output_tokens += result.output_tokens
                feature._cost_usd = result.cost_usd  # stash for history
                if result.metadata:
                    if feature.metadata is None:
                        feature.metadata = {}
                    feature.metadata["_generation_result_metadata"] = result.metadata
                self.instrumentor.emit_metric('prime_contractor.feature_cost', result.cost_usd, {'feature_name': feature.name, 'model': result.model})
                logger.info("Code generated for '%s': cost=$%.4f, tokens=%d in / %d out", feature.name, result.cost_usd, result.input_tokens, result.output_tokens, extra={'feature_name': feature.name, 'cost_usd': result.cost_usd, 'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens, 'model': result.model})
                
                # Micro Prime dry-run: classification-only, skip integration
                if result.metadata and result.metadata.get("dry_run"):
                    self.queue.complete_feature(feature.id)
                    self._save_queue_state_with_mode()
                    return True
                return True
            else:
                error_msg = result.error or 'Code generation failed'
                logger.error("Code generation failed for '%s': %s", feature.name, error_msg, extra={'feature_name': feature.name, 'error': error_msg})
                self.queue.fail_feature(feature.id, error_msg)
                return False
        except Exception as e:
            error_msg = f'Exception during code generation: {e}'
            logger.error('%s', error_msg, exc_info=True, extra={'feature_name': feature.name})
            self.queue.fail_feature(feature.id, error_msg)
            return False

    def _get_domain_enrichment(self, feature: FeatureSpec):
        """Lazy-init DomainChecklist and return enrichment for a feature."""
        if self._domain_checklist is None:
            try:
                from .artisan_phases.domain_checklist import DomainChecklist
                self._domain_checklist = DomainChecklist(project_root=self.project_root)
            except Exception as exc:
                logger.debug("DomainChecklist unavailable: %s", exc)
                self._domain_checklist = False  # sentinel: don't retry
                return None
        if self._domain_checklist is False:
            return None
        try:
            return self._domain_checklist.get_enrichment(feature.id, feature.target_files)
        except Exception as exc:
            logger.debug("Domain enrichment failed for '%s': %s", feature.name, exc)
            return None

    def integrate_feature(self, feature: FeatureSpec) -> bool:
        """
        Integrate a single feature immediately.

        Delegates to IntegrationEngine for the full
        snapshot → validate → merge → checkpoint → commit/rollback pipeline.

        Domain post-validation (advisory) stays here because it depends on
        ``_current_enrichment`` which is PrimeContractor-specific context.

        Returns:
            True if integration succeeded, False otherwise
        """
        logger.info(
            'INTEGRATING FEATURE: %s', feature.name,
            extra={'feature_name': feature.name, 'feature_id': feature.id},
        )

        # Domain post-validation — advisory only, before engine runs
        if not self.dry_run and self._current_enrichment is not None:
            resolved_output_dir = self._resolve_output_dir()
            gen_paths = []
            for f in feature.generated_files:
                p = Path(f)
                if not p.is_absolute():
                    p = resolved_output_dir.parent / p
                if p.exists() and p.suffix == '.py':
                    gen_paths.append(p)
            for gen_path in gen_paths:
                code = gen_path.read_text(encoding='utf-8')
                from .artisan_phases.domain_checklist import validate_generated_code
                domain_result = validate_generated_code(
                    code, self._current_enrichment,
                )
                if not domain_result.passed:
                    for iss in domain_result.issues:
                        logger.warning(
                            'Feature %s: post-gen %s: %s (line %s)',
                            feature.name, iss.validator, iss.message, iss.line,
                            extra={'feature_name': feature.name},
                        )
                else:
                    logger.info(
                        'Domain validation passed for %s', feature.name,
                        extra={'feature_name': feature.name},
                    )

        unit = FeatureSpecUnit(feature)
        result = self._engine.integrate(
            unit,
            attempt=feature.integration_attempts + 1,
            listener=self._prime_listener,
        )

        if result.success:
            # R2-S4: If repair succeeded, the listener already incremented
            # integration_attempts via start_integration(). Decrement to
            # avoid consuming a retry slot for a successful repair.
            if result.metadata.get("repair_success"):
                feature.integration_attempts = max(
                    0, feature.integration_attempts - 1,
                )
            self.queue.complete_feature(feature.id)
            self.integration_history.append({
                'feature_name': feature.name,
                'feature_id': feature.id,
                'success': True,
                'cost_usd': getattr(feature, '_cost_usd', 0.0),
                'files': [str(f) for f in result.integrated_files],
                'generation_metadata': (feature.metadata or {}).get('_generation_result_metadata', {}),
                'timestamp': datetime.now().isoformat(),
            })
            if self.on_feature_complete:
                self.on_feature_complete(feature)
            return True
        else:
            # REQ-RPL-204: Structured repair context for retry enrichment
            if result.metadata.get("repair_attempted") and not result.metadata.get("repair_success"):
                repair_context = {
                    "repair_attempted": True,
                    "repair_steps_applied": result.metadata.get("repair_steps", []),
                    "repair_files_modified": result.metadata.get("repair_files_modified", []),
                    "repair_duration_ms": result.metadata.get("repair_duration_ms") or 0,
                    "repair_error": result.metadata.get("repair_error"),
                }
                # Sanitize diagnostic strings
                try:
                    from ..repair.diagnostics import sanitize_diagnostic
                    if repair_context.get("repair_error"):
                        repair_context["repair_error"] = sanitize_diagnostic(
                            str(repair_context["repair_error"]),
                        )
                except ImportError:
                    logger.debug("repair.diagnostics not available — skipping sanitization")

                if feature.metadata is None:
                    feature.metadata = {}
                feature.metadata["_repair_context"] = repair_context

                # Backward-compatible string error_message
                repair_detail = (
                    f"Repair attempted (steps: {result.metadata.get('repair_steps', [])}) "
                    f"but failed"
                )
                if result.metadata.get("repair_error"):
                    repair_detail += f": {result.metadata['repair_error']}"
                feature.error_message = (
                    (feature.error_message or "") + f" | {repair_detail}"
                ).lstrip(" | ")
            if result.checkpoint_results and self.on_checkpoint_failed:
                self.on_checkpoint_failed(feature, result.checkpoint_results)
            return False

    def run(self, max_features: Optional[int]=None, stop_on_failure: bool=True, max_cost_usd: Optional[float]=None) -> Dict:
        """
        Run the Prime Contractor workflow.

        Args:
            max_features: Maximum number of features to process (None = all)
            stop_on_failure: Stop processing if a feature fails
            max_cost_usd: Hard ceiling on total workflow cost in USD (None = no limit)

        Returns:
            Summary dict with results
        """
        # Sync any legacy ad-hoc attributes to SeedContext before freezing
        self._sync_legacy_attributes()
        # Freeze seed context at execution boundary to prevent post-execution reconfiguration
        self.seed_context.freeze()
        logger.info(
            'PRIME CONTRACTOR WORKFLOW started — mode=%s, execution=%s, auto_commit=%s, stop_on_failure=%s',
            self.seed_context.execution_mode,
            'DRY RUN' if self.dry_run else 'LIVE',
            self.auto_commit,
            stop_on_failure,
            extra={
                'dry_run': self.dry_run,
                'auto_commit': self.auto_commit,
                'seed_exec_mode': self.seed_context.execution_mode,
            }
        )
        is_clean, dirty_files = self.check_git_status()
        if not is_clean:
            if self.auto_stash:
                logger.info('Auto-stashing: repository has uncommitted changes')
                stash_ref = self.create_safety_snapshot()
                if stash_ref:
                    logger.info('Stashed as: %s', stash_ref)
            elif self.allow_dirty:
                logger.warning('Repository has uncommitted changes (--allow-dirty set)')
            else:
                logger.error('BLOCKED: Repository has %d file(s) with uncommitted changes', len(dirty_files), extra={'dirty_files': dirty_files[:10]})
                return {'processed': 0, 'succeeded': 0, 'failed': 0, 'progress': self.queue.get_progress(), 'history': [], 'total_cost_usd': 0.0, 'aborted': True, 'abort_reason': 'uncommitted_changes'}
        self.instrumentor.emit_insight(insight_type='workflow_started', summary=f'Starting workflow with {len(self.queue.features)} features', confidence=1.0, mode='dry_run' if self.dry_run else 'live', feature_count=len(self.queue.features))
        if not self.dry_run:
            logger.info('Capturing test baseline for regression detection...')
            baseline = self.checkpoint.capture_test_baseline()
            logger.info('Test baseline captured: %d test(s)', len(baseline))
        self.queue.print_status()
        features_processed = 0
        features_succeeded = 0
        features_failed = 0
        while True:
            if max_features and features_processed >= max_features:
                logger.info('Reached max features limit (%d)', max_features)
                break
            if max_cost_usd is not None and self.total_cost_usd >= max_cost_usd:
                logger.error('Cost limit reached: $%.2f >= $%.2f — stopping workflow', self.total_cost_usd, max_cost_usd)
                break
            feature = self.queue.get_next_feature()
            if not feature:
                logger.info('No more features to process')
                break
            if feature.integration_attempts >= self.max_retries:
                logger.error("Feature '%s' exceeded max integration attempts (%d)", feature.name, self.max_retries)
                self.queue.fail_feature(feature.id, f'Max integration attempts exceeded ({self.max_retries})')
                self._save_queue_state_with_mode()
                features_processed += 1
                features_failed += 1
                if stop_on_failure:
                    logger.error("STOPPING: Feature '%s' failed", feature.name, extra={'feature_name': feature.name})
                    break
                continue
            features_processed += 1
            success = self.process_feature(feature)
            if success:
                features_succeeded += 1
            else:
                features_failed += 1
                self.integration_history.append({'feature_name': feature.name, 'feature_id': feature.id, 'success': False, 'cost_usd': getattr(feature, '_cost_usd', 0.0), 'error': feature.error_message, 'generation_metadata': (feature.metadata or {}).get('_generation_result_metadata', {}), 'timestamp': datetime.now().isoformat()})
                if stop_on_failure:
                    logger.error("STOPPING: Feature '%s' failed", feature.name, extra={'feature_name': feature.name})
                    break
        # Save final state with execution_mode
        self._save_queue_state_with_mode()

        logger.info(
            'WORKFLOW SUMMARY: processed=%d, succeeded=%d, failed=%d, progress=%.1f%%, cost=$%.4f, tokens=%d in / %d out',
            features_processed, features_succeeded, features_failed,
            self.queue.get_progress(), self.total_cost_usd,
            self.total_input_tokens, self.total_output_tokens,
            extra={
                'processed': features_processed,
                'succeeded': features_succeeded,
                'failed': features_failed,
                'progress': self.queue.get_progress(),
                'total_cost_usd': self.total_cost_usd,
                'total_input_tokens': self.total_input_tokens,
                'total_output_tokens': self.total_output_tokens,
                'seed_exec_mode': self.seed_context.execution_mode,
            }
        )
        self.instrumentor.emit_insight(insight_type='workflow_completed', summary=f'Workflow complete: {features_succeeded}/{features_processed} succeeded', confidence=1.0, processed=features_processed, succeeded=features_succeeded, failed=features_failed, total_cost_usd=self.total_cost_usd)

        # Log tier distribution if complexity routing was active
        if self._complexity_routing_enabled:
            try:
                from startd8.complexity import ComplexityTier, log_tier_distribution

                tiers = []
                for f in self.queue.features.values():
                    tier_val = (f.metadata or {}).get("_complexity_tier")
                    if tier_val:
                        try:
                            tiers.append(ComplexityTier(tier_val))
                        except ValueError:
                            pass
                if tiers:
                    log_tier_distribution(tiers)
            except Exception:
                logger.debug("Tier distribution logging failed", exc_info=True)

        # Phase 4: Write generation manifest (pipeline mode only)
        result_dict = {'processed': features_processed, 'succeeded': features_succeeded, 'failed': features_failed, 'progress': self.queue.get_progress(), 'history': self.integration_history, 'total_cost_usd': self.total_cost_usd, 'total_input_tokens': self.total_input_tokens, 'total_output_tokens': self.total_output_tokens}
        self._write_generation_manifest(result_dict)

        # Launch async post-mortem evaluation
        try:
            from .prime_postmortem import launch_prime_postmortem_async
            launch_prime_postmortem_async(
                result_dict=result_dict,
                queue=self.queue,
                seed_path=getattr(self, '_seed_path', None),
                output_dir=str(self._manifest_path().parent),
            )
        except Exception:
            logger.warning("Prime postmortem launch failed", exc_info=True)

        return result_dict

    def run_single_feature(self, feature_id: str) -> bool:
        """Run integration for a single specific feature."""
        feature = self.queue.features.get(feature_id)
        if not feature:
            logger.warning('Feature not found: %s', feature_id)
            return False
        return self.integrate_feature(feature)

    def reset_failed_features(self):
        """Reset all failed/stuck features to appropriate status for retry.

        Preserves error_message so that the next attempt can use it as
        feedback context for regeneration (error-informed retry).
        """
        reset_count = 0
        for feature in self.queue.features.values():
            if feature.status in (FeatureStatus.FAILED, FeatureStatus.BLOCKED, FeatureStatus.INTEGRATING, FeatureStatus.DEVELOPING):
                if feature.generated_files:
                    feature.status = FeatureStatus.GENERATED
                    logger.info('Reset %s -> GENERATED (has code, prior error preserved)', feature.name)
                else:
                    feature.status = FeatureStatus.PENDING
                    logger.info('Reset %s -> PENDING (needs development)', feature.name)
                reset_count += 1
        self.queue.save_state()
        logger.info('Reset %d failed/blocked feature(s)', reset_count)

    def full_reset(self, include_targets: bool=False) -> None:
        """
        Reset workflow state **and** clean generated artifacts.

        Combines ``queue.reset()`` (reverts all features to PENDING) with
        ``clean_workspace()`` (removes generated/, .backup, __pycache__).
        This is the method that ``--reset-state`` should call instead of
        just deleting the state JSON.

        Args:
            include_targets: If True, also delete target files listed in
                the feature queue.  Use with caution.
        """
        if self.queue.state_file.exists():
            self.queue.state_file.unlink()
            logger.info('Removed state file: %s', self.queue.state_file.name)
        self.queue.reset()
        self.clean_workspace(include_targets=include_targets)

    def clean_workspace(self, include_targets: bool=False) -> int:
        """
        Remove generated artifacts from previous runs.

        Deletes:
        - generated/ staging directory (or configured output_dir)
        - .backup files under project root
        - __pycache__ directories under project root

        Optionally (when include_targets=True):
        - Target files listed in the feature queue

        Args:
            include_targets: If True, also delete target files from the queue.
                Use with caution — target files may contain hand-written code.

        Returns:
            Count of items removed.
        """
        removed = 0
        output_dir = self._resolve_output_dir()
        if output_dir.exists() and output_dir.is_dir():
            shutil.rmtree(output_dir)
            logger.info('Removed directory: %s', output_dir)
            removed += 1
        for backup_file in self.project_root.rglob('*.backup'):
            backup_file.unlink()
            logger.debug('Removed backup: %s', backup_file.relative_to(self.project_root))
            removed += 1
        for snapshot_file in self.project_root.rglob('*.pre_integration'):
            snapshot_file.unlink()
            logger.debug('Removed snapshot: %s', snapshot_file.relative_to(self.project_root))
            removed += 1
        self._engine._pre_integration_snapshots.clear()
        for pycache_dir in self.project_root.rglob('__pycache__'):
            if pycache_dir.is_dir():
                shutil.rmtree(pycache_dir)
                logger.debug('Removed: %s', pycache_dir.relative_to(self.project_root))
                removed += 1
        if include_targets:
            for feature in self.queue.features.values():
                for target_file in feature.target_files:
                    target_path = Path(target_file)
                    if not target_path.is_absolute():
                        target_path = self.project_root / target_path
                    if target_path.is_file():
                        target_path.unlink()
                        logger.info('Removed target: %s', target_path.relative_to(self.project_root))
                        removed += 1
        logger.info('Cleaned %d item(s) from workspace', removed)
        return removed

class FeatureProcessor:
    """
    Processes decomposed features according to enterprise requirements.
    
    This processor implements a five-stage pipeline:
    1. Input Validation - Ensures data integrity
    2. Normalization - Standardizes format
    3. Enrichment - Adds metadata and context
    4. Analysis - Derives insights (type, dependencies, complexity)
    5. Finalization - Returns processed feature
    
    Thread-safe for concurrent processing scenarios.
    """
    FEATURE_TYPES = ['frontend', 'backend', 'data', 'testing', 'devops', 'general']
    REQUIRED_FIELDS = ['id', 'description', 'parent_feature_id']
    COMPLEXITY_KEYWORDS = ['integrate', 'complex', 'multiple', 'various', 'comprehensive', 'advanced', 'sophisticated', 'intricate', 'elaborate', 'extensive']
    TYPE_KEYWORDS = {'frontend': ['ui', 'interface', 'display', 'view', 'component', 'screen', 'frontend'], 'backend': ['api', 'endpoint', 'service', 'backend', 'server', 'microservice'], 'data': ['database', 'schema', 'migration', 'query', 'storage', 'data'], 'testing': ['test', 'validation', 'verify', 'check', 'assert', 'quality'], 'devops': ['deploy', 'infrastructure', 'configuration', 'pipeline', 'ci/cd']}
    VERSION = '1.0.0'
    MAX_DESCRIPTION_LENGTH = 1000
    PRIORITY_MIN = 1
    PRIORITY_MAX = 5
    COMPLEXITY_MIN = 1
    COMPLEXITY_MAX = 10

    def __init__(self):
        """Initialize the FeatureProcessor."""
        logger.info(f'FeatureProcessor initialized (version {self.VERSION})')

    def _process_decomposed_feature(self, feature: Dict[str, Any], parent_context: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        """
        Process a single decomposed feature with comprehensive validation and enrichment.

        Args:
            feature: Raw decomposed feature dictionary containing:
                - id (str): Unique identifier
                - description (str): Feature description text
                - parent_feature_id (str): ID of parent feature
                - type (str, optional): Feature type
                - priority (int, optional): Priority level (1-5)
            parent_context: Optional context from parent feature for inheritance.
                Expected to contain fields like "tags", "category".

        Returns:
            Dict[str, Any]: Processed feature with all enrichments applied:
                - All original fields (normalized)
                - metadata: Processing information and status
                - dependencies: Extracted feature dependencies
                - complexity_score: Calculated complexity (1-10)
                - type: Inferred or validated feature type

        Raises:
            ValueError: If required fields are missing or validation fails
            TypeError: If field types are incorrect

        Example:
            >>> processor = FeatureProcessor()
            >>> feature = {
            ...     "id": "FEAT-001",
            ...     "description": "Create API endpoint",
            ...     "parent_feature_id": "EPIC-100"
            ... }
            >>> result = processor._process_decomposed_feature(feature)
        """
        if parent_context is None:
            parent_context = {}
        processed_feature = feature.copy()
        original_id = processed_feature.get('id', 'N/A')
        warnings = []
        try:
            logger.debug(f"Processing feature '{original_id}': Stage 1 - Validation")
            self._validate_feature_fields(processed_feature)
            if not processed_feature.get('description', '').strip():
                raise ValueError(f"Feature '{original_id}': Description cannot be empty")
            parent_id = processed_feature.get('parent_feature_id')
            if not isinstance(parent_id, str) or not parent_id.strip():
                raise ValueError(f"Feature '{original_id}': Invalid or empty parent_feature_id")
            additional_fields = {}
            standard_fields = {'id', 'description', 'type', 'parent_feature_id', 'priority'}
            keys_to_remove = []
            for key, value in processed_feature.items():
                if key not in standard_fields:
                    additional_fields[key] = value
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del processed_feature[key]
            if additional_fields:
                processed_feature['additional_fields'] = additional_fields
                logger.debug(f"Feature '{original_id}': Moved {len(additional_fields)} extra fields")
            logger.debug(f"Processing feature '{original_id}': Stage 2 - Normalization")
            processed_feature['description'] = self._normalize_description(processed_feature['description'])
            logger.debug(f"Processing feature '{original_id}': Stage 3 - Enrichment")
            processed_feature['metadata'] = {'processed_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'), 'processing_status': 'success', 'version': self.VERSION, 'warnings': warnings}
            for key, value in parent_context.items():
                if key not in processed_feature or processed_feature[key] is None:
                    processed_feature[key] = value
                    logger.debug(f"Feature '{original_id}': Inherited '{key}' from parent context")
            processed_feature = self._process_priority(processed_feature, original_id, warnings)
            logger.debug(f"Processing feature '{original_id}': Stage 4 - Analysis")
            processed_feature = self._process_feature_type(processed_feature, original_id, warnings)
            dependencies = self._extract_dependencies(processed_feature['description'])
            processed_feature['dependencies'] = dependencies
            if dependencies:
                logger.info(f"Feature '{original_id}': Found {len(dependencies)} dependencies")
                if original_id in dependencies:
                    warning_msg = f"Feature '{original_id}' has a circular dependency on itself"
                    warnings.append(warning_msg)
                    logger.warning(warning_msg)
            complexity_score = self._calculate_complexity_score(processed_feature['description'], dependencies)
            processed_feature['complexity_score'] = complexity_score
            logger.info(f"Feature '{original_id}': Complexity score = {complexity_score}")
            processed_feature['metadata']['warnings'] = warnings
            logger.info(f"Feature '{original_id}': Successfully processed")
        except (ValueError, TypeError) as e:
            logger.error(f"Feature '{original_id}': Processing failed - {e}")
            processed_feature = self._create_error_response(processed_feature, feature, original_id, str(e))
            raise
        except Exception as e:
            logger.error(f"Feature '{original_id}': Unexpected error - {e}", exc_info=True)
            processed_feature = self._create_error_response(processed_feature, feature, original_id, f'Unexpected error: {str(e)}')
            raise
        return processed_feature

    def _validate_feature_fields(self, feature: Dict[str, Any]) -> None:
        """
        Validate required fields exist and have correct types.

        Args:
            feature: Feature dictionary to validate

        Raises:
            ValueError: If required field is missing or invalid
            TypeError: If field has incorrect type
        """
        feature_id = feature.get('id', 'N/A')
        for field in self.REQUIRED_FIELDS:
            if field not in feature or feature[field] is None:
                raise ValueError(f"Feature '{feature_id}': Missing required field '{field}'")
        if not isinstance(feature['id'], str):
            raise TypeError(f"Feature '{feature_id}': Field 'id' must be a string")
        if not isinstance(feature['description'], str):
            raise TypeError(f"Feature '{feature_id}': Field 'description' must be a string")
        if not isinstance(feature['parent_feature_id'], str):
            raise TypeError(f"Feature '{feature_id}': Field 'parent_feature_id' must be a string")
        if 'priority' in feature and feature['priority'] is not None:
            if not isinstance(feature['priority'], int):
                try:
                    int(feature['priority'])
                except (ValueError, TypeError):
                    raise TypeError(f"Feature '{feature_id}': Field 'priority' must be an integer")
        if len(feature['description']) > self.MAX_DESCRIPTION_LENGTH:
            logger.warning(f"Feature '{feature_id}': Description exceeds {self.MAX_DESCRIPTION_LENGTH} characters")

    def _normalize_description(self, description: str) -> str:
        """
        Normalize feature description text.

        - Trims leading/trailing whitespace
        - Replaces multiple spaces with single space
        - Preserves original casing for domain-specific terms

        Args:
            description: Raw description text

        Returns:
            str: Normalized description
        """
        description = description.strip()
        description = re.sub('\\s+', ' ', description)
        return description

    def _process_priority(self, feature: Dict[str, Any], feature_id: str, warnings: List[str]) -> Dict[str, Any]:
        """
        Process and validate priority field.

        Args:
            feature: Feature dictionary
            feature_id: Feature identifier for logging
            warnings: List to append warnings to

        Returns:
            Dict[str, Any]: Feature with processed priority
        """
        if 'priority' not in feature or feature['priority'] is None:
            feature['priority'] = 3
            logger.info(f"Feature '{feature_id}': Priority defaulted to 3")
        else:
            priority = feature['priority']
            if not isinstance(priority, int):
                try:
                    priority = int(priority)
                except (ValueError, TypeError):
                    raise TypeError(f"Feature '{feature_id}': Priority must be an integer")
            if not self.PRIORITY_MIN <= priority <= self.PRIORITY_MAX:
                clamped = max(self.PRIORITY_MIN, min(priority, self.PRIORITY_MAX))
                warning_msg = f'Priority {priority} out of range ({self.PRIORITY_MIN}-{self.PRIORITY_MAX}), clamped to {clamped}'
                warnings.append(warning_msg)
                feature['priority'] = clamped
                logger.warning(f"Feature '{feature_id}': {warning_msg}")
            else:
                feature['priority'] = priority
        return feature

    def _process_feature_type(self, feature: Dict[str, Any], feature_id: str, warnings: List[str]) -> Dict[str, Any]:
        """
        Process and validate feature type field.

        Args:
            feature: Feature dictionary
            feature_id: Feature identifier for logging
            warnings: List to append warnings to

        Returns:
            Dict[str, Any]: Feature with processed type
        """
        if 'type' not in feature or not feature['type']:
            inferred_type = self._infer_feature_type(feature['description'])
            feature['type'] = inferred_type
            if inferred_type == 'general':
                warnings.append("Feature type could not be inferred, defaulted to 'general'")
                logger.info(f"Feature '{feature_id}': Type defaulted to 'general'")
            else:
                logger.info(f"Feature '{feature_id}': Type inferred as '{inferred_type}'")
        elif feature['type'] not in self.FEATURE_TYPES:
            warning_msg = f"Provided type '{feature['type']}' is not recognized, defaulted to 'general'"
            warnings.append(warning_msg)
            feature['type'] = 'general'
            logger.warning(f"Feature '{feature_id}': {warning_msg}")
        else:
            logger.info(f"Feature '{feature_id}': Using provided type '{feature['type']}'")
        return feature

    def _infer_feature_type(self, description: str) -> str:
        """
        Infer feature type from description using keyword matching.

        Uses case-insensitive word boundary matching to identify feature type
        based on domain-specific keywords.

        Args:
            description: Feature description text

        Returns:
            str: Inferred feature type (one of FEATURE_TYPES)
        """
        description_lower = description.lower()
        type_scores = {ftype: 0 for ftype in self.FEATURE_TYPES}
        for ftype, keywords in self.TYPE_KEYWORDS.items():
            for keyword in keywords:
                if re.search('\\b' + re.escape(keyword) + '\\b', description_lower):
                    type_scores[ftype] += 1
        max_score = max(type_scores.values())
        if max_score == 0:
            return 'general'
        for ftype in self.FEATURE_TYPES:
            if type_scores.get(ftype, 0) == max_score:
                return ftype
        return 'general'

    def _extract_dependencies(self, description: str) -> List[str]:
        """
        Extract dependency references from description.

        Identifies dependencies through:
        - Explicit phrases: "depends on", "requires", "integrates with", etc.
        - Capitalized component names: "Analytics API", "Database Migration"

        Args:
            description: Feature description text

        Returns:
            List[str]: List of unique dependency identifiers
        """
        dependencies = []
        description_lower = description.lower()
        explicit_patterns = ['depends on ([\\w\\s-]+?)(?:\\.|,|$|\\s(?:and|or|to|for))', 'requires ([\\w\\s-]+?)(?:\\.|,|$|\\s(?:and|or|to|for))', 'integrates with ([\\w\\s-]+?)(?:\\.|,|$|\\s(?:and|or|to|for))', 'uses ([\\w\\s-]+?)(?:\\.|,|$|\\s(?:and|or|to|for))', 'built on ([\\w\\s-]+?)(?:\\.|,|$|\\s(?:and|or|to|for))']
        for pattern in explicit_patterns:
            matches = re.findall(pattern, description_lower)
            for match in matches:
                dep_name = match.strip()
                if dep_name and dep_name not in dependencies:
                    dependencies.append(dep_name)
        potential_deps = re.findall('\\b([A-Z][a-z]+(?:[\\s-]+[A-Z][a-z]+)*)\\b', description)
        exclude_words = {'a', 'an', 'the', 'for', 'with', 'and', 'or', 'this', 'that', 'create', 'build', 'implement', 'add', 'update', 'feature'}
        for dep in potential_deps:
            cleaned_dep = dep.strip()
            if cleaned_dep and cleaned_dep not in dependencies and (cleaned_dep.lower() not in exclude_words) and (len(cleaned_dep) > 2):
                dependencies.append(cleaned_dep)
        seen = set()
        unique_deps = []
        for dep in dependencies:
            dep_lower = dep.lower()
            if dep_lower not in seen:
                seen.add(dep_lower)
                unique_deps.append(dep.strip())
        return unique_deps

    def _count_complexity_keywords(self, description: str) -> int:
        """
        Count complexity-indicating keywords in description.

        Args:
            description: Feature description text

        Returns:
            int: Count of complexity keywords found
        """
        count = 0
        description_lower = description.lower()
        for keyword in self.COMPLEXITY_KEYWORDS:
            if re.search('\\b' + re.escape(keyword) + '\\b', description_lower):
                count += 1
        return count

    def _calculate_complexity_score(self, description: str, dependencies: List[str]) -> int:
        """
        Calculate complexity score on 1-10 scale.

        Scoring factors:
        - Description length (up to 5 points)
        - Dependency count (up to 3 points)
        - Complexity keywords (up to 2 points)

        Args:
            description: Feature description text
            dependencies: List of feature dependencies

        Returns:
            int: Complexity score (1-10)
        """
        base_score = min(len(description) / 20, 5)
        dependency_score = min(len(dependencies) * 0.5, 3)
        keyword_count = self._count_complexity_keywords(description)
        keyword_score = min(keyword_count * 0.5, 2)
        total_score = base_score + dependency_score + keyword_score
        final_score = max(self.COMPLEXITY_MIN, min(round(total_score), self.COMPLEXITY_MAX))
        return final_score

    def _create_error_response(self, processed_feature: Dict[str, Any], original_feature: Dict[str, Any], feature_id: str, error_message: str) -> Dict[str, Any]:
        """
        Create consistent error response structure.

        Args:
            processed_feature: Partially processed feature
            original_feature: Original input feature
            feature_id: Feature identifier
            error_message: Error description

        Returns:
            Dict[str, Any]: Feature with error metadata
        """
        if 'metadata' not in processed_feature:
            processed_feature['metadata'] = {}
        processed_feature['metadata'].update({'processing_status': 'failed', 'error': error_message, 'processed_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'), 'version': self.VERSION, 'warnings': []})
        processed_feature.setdefault('id', feature_id)
        processed_feature.setdefault('description', original_feature.get('description'))
        processed_feature.setdefault('parent_feature_id', original_feature.get('parent_feature_id'))
        processed_feature.setdefault('type', 'general')
        processed_feature.setdefault('priority', 3)
        processed_feature.setdefault('dependencies', [])
        processed_feature.setdefault('complexity_score', 0)
        return processed_feature
logger = get_logger(__name__)
MAX_INTEGRATION_ATTEMPTS = 6
