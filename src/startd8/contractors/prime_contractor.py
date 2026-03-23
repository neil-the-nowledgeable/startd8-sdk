import dataclasses
import enum
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..implementation_engine.budget import (
    EXISTING_FILES_BUDGET_BYTES as _EXISTING_FILES_BUDGET_BYTES,
)
from ..logging_config import get_logger
from .checkpoint import IntegrationCheckpoint
from .context_resolution import (
    ContextStrategy as ContextResolutionStrategy,
    StandaloneContextStrategy,
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
from ..repair.orchestrator import reset_circuit_breaker

logger = get_logger(__name__)

# AC-R7: Generator-native OTel observability for prime contractor
try:
    from opentelemetry import trace as _trace
    _prime_tracer = _trace.get_tracer("startd8.prime_contractor")
except ImportError:
    from .artisan_contractor import _NoOpTracer
    _prime_tracer = _NoOpTracer()

# ---------------------------------------------------------------------------
# Execution Mode Constants (F-004)
# ---------------------------------------------------------------------------

#: Execution mode for standalone operation — no pipeline context expected.
MODE_STANDALONE: str = "standalone"

#: Execution mode for pipeline operation — full seed context exploitation.
MODE_PIPELINE: str = "pipeline"

#: Set of all recognized execution modes — single source of truth for validation.
VALID_MODES: frozenset = frozenset({MODE_STANDALONE, MODE_PIPELINE})

#: CR-L2: Alias for backward compatibility — was a duplicate frozenset.
VALID_EXECUTION_MODES: frozenset = VALID_MODES

#: Internal: minimum number of pipeline signal keys (with non-None values)
#: required to trigger pipeline mode during auto-detection.
_DETECTION_THRESHOLD: int = 1

#: Plan document load cap (PC-B5). Reduces from 60KB to 16KB for token savings.
_PLAN_LOAD_MAX_BYTES: int = 16_384

#: CR-C1: Minimum quality score for accepting generation results from
#: generators that lack an internal review loop.  Results below this
#: threshold trigger an error-informed regeneration attempt.
_MIN_QUALITY_SCORE: int = 60

#: CR-C1: Quality score assumed when a generator does not provide one.
#: Set conservatively below _MIN_QUALITY_SCORE so unscored results from
#: non-reviewing generators trigger the quality gate on the first pass,
#: prompting escalation or re-generation.  PrimaryContractorCodeGenerator
#: always provides a score, so this only affects MicroPrime and custom generators.
_UNSCORED_QUALITY_FALLBACK: Optional[int] = None  # None = skip gate for unscored

#: PC-O1, PC-O3: Budget for existing file content when populating gen_context.
#: Single source of truth — imported from implementation_engine.budget.

__all__ = [
    "MODE_STANDALONE",
    "MODE_PIPELINE",
    "VALID_MODES",
    "VALID_EXECUTION_MODES",
    "ExecutionMode",
    "SeedContext",
    "PrimeContractorWorkflow",
    "PrimeContractorListener",
    "FeatureSpecUnit",
]


# ---------------------------------------------------------------------------
# KaizenConfig: Grouped configuration for Kaizen prompt capture (REQ-KZ-200)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class KaizenConfig:
    """Grouped configuration for Kaizen prompt capture and hints."""

    enabled: bool = False
    prompt_dir: Optional[Path] = None
    config: Optional[dict] = None


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
    service_communication_graph: Optional[Dict[str, Any]] = None  # REQ-SIG-201

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
# ExecutionMode Enum (F-001)
# ---------------------------------------------------------------------------

class ExecutionMode(enum.Enum):
    """Execution mode for the Prime Contractor workflow.

    STANDALONE: Current behavior — no pipeline context, zero-change default.
    PIPELINE: Full context exploitation — onboarding, architectural, calibration.
    """

    STANDALONE = "standalone"
    PIPELINE = "pipeline"


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

    def __init__(self, project_root: Optional[Path]=None, dry_run: bool=False, auto_commit: bool=False, strict_checkpoints: bool=False, max_retries: int=6, allow_dirty: bool=False, auto_stash: bool=False, code_generator: Optional[CodeGenerator]=None, instrumentor: Optional[Instrumentor]=None, size_estimator: Optional[SizeEstimator]=None, merge_strategy: Optional[MergeStrategy]=None, on_feature_complete: Optional[FeatureCompleteCallback]=None, on_checkpoint_failed: Optional[CheckpointFailedCallback]=None, max_lines_per_feature: int=150, max_tokens_per_feature: int=500, check_truncation: bool=True, resume: bool=False, cli_mode: Optional[str]=None, force_mode: Optional[str]=None, context_strategy: Optional[ContextResolutionStrategy]=None, strict_mode: bool=False, walkthrough: bool=False, repair_config: Optional[Any]=None, edit_min_pct: int=80, review_enabled: bool=True, review_agent: Optional[str]=None, quality_gate_enabled: bool=True, quality_gate_threshold: float=0.5):
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
            edit_min_pct: Min % of existing lines in edit output (PC-Q3, default: 80)
            review_enabled: If True, run LLM review after integration (REQ-RFL-125)
            review_agent: Agent spec for review (default: lead_agent)
            quality_gate_enabled: If True, re-draft on FAIL + low score (REQ-RFL-220)
            quality_gate_threshold: Disk quality score below which gate fires (default: 0.5)
        """
        self.project_root = project_root or Path.cwd()
        self.edit_min_pct = edit_min_pct
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
        # Language profile set during develop_feature(); stored here for
        # merge strategy re-selection when target language changes.
        self._language_profile = None
        self.integration_history: List[Dict] = []
        self.review_results: Dict[str, Dict[str, Any]] = {}
        self.review_enabled = review_enabled
        self._review_agent = review_agent
        self._review_adapter: Any = None  # Lazy init (PrimeReviewAdapter)
        self.quality_gate_enabled = quality_gate_enabled
        self.quality_gate_threshold = quality_gate_threshold
        self._quality_accumulator: Any = None  # RunQualityAccumulator, created per run()
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
        self.seed_service_metadata: Dict[str, Any] = {}
        self.seed_forward_manifest: Optional[Dict[str, Any]] = None  # REQ-PC-FM-002
        self.plan_document_text: Optional[str] = None
        self.force_regenerate: bool = False
        self.walkthrough: bool = walkthrough
        # Kaizen prompt capture (REQ-KZ-200) — off by default, enabled via --kaizen flag
        self._kaizen = KaizenConfig()
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
        # FR-MPA-007: Skeleton sources — populated in load_seed_context()
        self._skeleton_sources: dict[str, str] = {}
        # Complexity routing (REQ-MP-807) — off by default, enabled via enable_complexity_routing()
        self._complexity_routing_enabled = False
        self._complexity_config: Optional[Any] = None
        self._complexity_router: Optional[Any] = None
        # Micro Prime (REQ-MP-710) — off by default, enabled via enable_micro_prime()
        self._micro_prime_enabled = False
        self._original_code_generator = None
        # Element registry (ER-012) — shared across features for cross-task reuse
        self._element_registry: Optional[Any] = None
        # Tier escalation removed (AC-R3-R6): compensatory complexity that
        # masked inadequate primary model selection.  Error-informed retry
        # (with prior_error injection) is the single retry mechanism.
        # AC-R3: Content-addressable generation cache
        from .generation_cache import GenerationCache
        self._generation_cache = GenerationCache(
            cache_dir=self.project_root / ".startd8" / "state" / "generation_cache",
        )
        # Resume state: load from disk if resuming
        self._resume_mode: Optional[str] = None
        if resume:
            self._load_state_if_resuming(cli_mode=cli_mode, force_mode=force_mode)
        # REQ-TCW-400: TODO completion — off by default, enabled via enable_todo_completion()
        self._enable_todo_completion: bool = False

    def enable_todo_completion(self) -> None:
        """Enable post-generation TODO scan and task injection (REQ-TCW-400)."""
        self._enable_todo_completion = True
        logger.info("TODO completion enabled — will scan generated output for TODOs")

    def _rel_display(self, path: Path) -> str:
        """Safe relative path for display, falling back to the full path."""
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

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

        # When Micro Prime is enabled, self.code_generator is the MicroPrime
        # wrapper.  Use the original (unwrapped) generator for MODERATE/COMPLEX
        # tiers to avoid a redundant MicroPrime → fallback delegation hop.
        unwrapped = (
            self._original_code_generator
            if self._micro_prime_enabled and self._original_code_generator is not None
            else self.code_generator
        )

        self._complexity_router = ComplexityRouter(
            trivial_generator=trivial_generator,
            simple_generator=simple_generator,
            moderate_generator=unwrapped,
            complex_generator=complex_generator or unwrapped,
        )
        logger.info(
            "Complexity routing enabled (tier3_agent=%s, trivial=%s, simple=%s, "
            "moderate/complex=%s)",
            tier3_agent or "default",
            type(trivial_generator).__name__ if trivial_generator else "default",
            type(simple_generator).__name__ if simple_generator else "default",
            type(unwrapped).__name__,
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
        # ER-012: Initialize element registry for cross-feature reuse
        if getattr(self, "_element_registry", None) is None:
            try:
                from startd8.element_registry import ElementRegistry

                proj_root = getattr(self, "project_root", None)
                state_dir = (
                    proj_root / ".startd8" / "state"
                    if proj_root
                    else output_dir / ".startd8" / "state"
                )
                self._element_registry = ElementRegistry(state_dir=state_dir)
            except Exception as exc:
                logger.debug("Element registry init failed (non-fatal): %s", exc)
                self._element_registry = None

        self.code_generator = MicroPrimeCodeGenerator(
            config=mp_config,
            fallback=self._original_code_generator,
            output_dir=output_dir,
            cloud_agent_spec=cloud_agent_spec,
            element_registry=getattr(self, "_element_registry", None),
            project_root=getattr(self, "project_root", None),
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
        Also reads sibling Python files in the same directory to provide
        project-specific import context (e.g., proto module names, logging
        patterns) that grounds the LLM prompt.
        Paths outside project_root are skipped (path traversal safety).
        """
        if not feature.target_files:
            return
        root = self.project_root.resolve()
        budget = _EXISTING_FILES_BUDGET_BYTES
        existing: Dict[str, str] = {}

        # Collect target directories for sibling discovery
        target_dirs: set = set()

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
            target_dirs.add(full.parent)
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

        # Read sibling .py files in the same directories for import context
        # (Gap 2: sibling imports ground the LLM with project-specific patterns)
        for target_dir in target_dirs:
            if budget <= 0:
                break
            if not target_dir.is_dir():
                continue
            try:
                siblings = sorted(target_dir.glob("*.py"))
            except OSError:
                continue
            for sibling in siblings:
                if budget <= 0:
                    break
                if not str(sibling).startswith(str(root)):
                    continue
                try:
                    sib_rel = str(sibling.relative_to(root))
                except ValueError:
                    continue
                if sib_rel in existing:
                    continue  # already read as a target file
                if not sibling.is_file():
                    continue
                try:
                    raw = sibling.read_bytes()
                except OSError:
                    continue
                take = min(len(raw), budget)
                content = raw[:take].decode("utf-8", errors="replace")
                existing[sib_rel] = content
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

        # Resolve output_dir (consistent with element cache assembly and LLM generation)
        output_dir = self._resolve_output_dir()

        # Validate path — try output_dir first (where predecessor likely wrote),
        # then fall back to project_root for backward compatibility.
        source_path: Optional[Path] = None
        if not Path(source_file).is_absolute():
            candidate = output_dir / source_file
            if candidate.exists():
                source_path = validate_copy_path(
                    str(candidate), str(output_dir),
                )
        if source_path is None:
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

        # Write target into output_dir (consistent with normal generation paths)
        if not feature.target_files:
            raise ValueError(
                f"Feature '{feature.id}' ('{feature.name}') has no target_files for copy"
            )
        target_path = output_dir / feature.target_files[0]
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
        from .copy_detection import CopyModifySource, detect_copy, compress_reference, validate_copy_path

        predecessor = None
        deps = feature.dependencies or []
        if len(deps) == 1:
            predecessor = self.queue.get_feature(deps[0])

        cm = detect_copy(feature, predecessor=predecessor)
        if not isinstance(cm, CopyModifySource):
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

        This replaces the ad-hoc pattern of assigning workflow context
        attributes directly in runner scripts.

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
        comm_graph = seed_data.get("service_communication_graph")  # REQ-SIG-201
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
            service_communication_graph=comm_graph if isinstance(comm_graph, dict) else None,
        )

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
                from startd8.forward_manifest_extractor import SourceReconciler
                from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature

                all_targets = list({
                    f
                    for feat in self.queue.features.values()
                    for f in (feat.target_files or [])
                })
                # Bridge FeatureSpec → ParsedFeature for the reconciler API
                parsed_features = [
                    ParsedFeature(
                        feature_id=feat.id,
                        name=feat.name,
                        description=feat.description,
                        target_files=feat.target_files or [],
                    )
                    for feat in self.queue.features.values()
                ]
                # INV-12: When force_regenerate is set, exclude target files
                # to prevent prior-run output from contaminating the manifest.
                if self.force_regenerate:
                    for pf in parsed_features:
                        pf.target_files = []
                    logger.info(
                        "Fallback SOURCE_RECONCILE: --force-regenerate excludes %d target files",
                        len(all_targets),
                    )
                reconciler = SourceReconciler(project_root=self.project_root)
                new_contracts = reconciler.reconcile(parsed_features)
                # Merge new contracts into existing manifest
                existing_ids = {c.contract_id for c in self._forward_manifest.contracts}
                added = 0
                for contract in new_contracts:
                    if contract.contract_id not in existing_ids:
                        self._forward_manifest.contracts.append(contract)
                        existing_ids.add(contract.contract_id)
                        added += 1
                self._forward_manifest.stages_completed.append("SOURCE_RECONCILE")
                logger.info(
                    "Fallback SOURCE_RECONCILE: +%d contracts from project AST",
                    added,
                )
            except Exception as exc:
                logger.warning("Fallback SOURCE_RECONCILE failed: %s", exc, exc_info=True)

        # Wire forward manifest to integration engine for contract violation repair
        self._engine._forward_manifest = self._forward_manifest

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

        # --- Mottainai: Extract all available context from seed ---
        # These fields are produced by ContextCore export and threaded into
        # gen_context by _build_generation_context() to avoid re-derivation.

        # REQ-ICD-106: Security contract
        self._security_contract: dict[str, Any] | None = None
        _sc = seed_data.get("security_contract")
        if _sc and isinstance(_sc, dict):
            self._security_contract = _sc
            logger.info(
                "Security contract loaded from seed: %d database(s)",
                len(_sc.get("databases", {})),
            )

        # REQ-TCW-250: Instrumentation contract from onboarding
        self._instrumentation_contract: dict[str, Any] | None = None
        _instr_hints = onboarding.get("instrumentation_hints")
        if _instr_hints and isinstance(_instr_hints, dict):
            from startd8.validators.todo_scanner import normalize_instrumentation_data
            self._instrumentation_contract = normalize_instrumentation_data(_instr_hints)
            _mc = len((self._instrumentation_contract or {}).get("metrics", {}).get("required", []))
            logger.info("Instrumentation contract loaded from seed (%d metric entries)", _mc)

        # REQ-TCW-251: Guidance context
        self._guidance_context: dict[str, Any] | None = None
        _guidance = onboarding.get("guidance")
        if _guidance and isinstance(_guidance, dict):
            self._guidance_context = _guidance
            logger.info("Guidance context loaded from seed: %d keys", len(_guidance))

        # V2: Resolved artifact parameters (pre-computed by ContextCore)
        self._resolved_artifact_params: dict[str, Any] | None = None
        _rap = onboarding.get("resolved_artifact_parameters")
        if _rap and isinstance(_rap, dict):
            self._resolved_artifact_params = _rap
            logger.info("Resolved artifact parameters loaded: %d types", len(_rap))

        # V3: Expected output contracts (depth, tokens, completeness markers)
        self._expected_output_contracts: dict[str, Any] | None = None
        _eoc = onboarding.get("expected_output_contracts")
        if _eoc and isinstance(_eoc, dict):
            self._expected_output_contracts = _eoc
            logger.info("Expected output contracts loaded: %d types", len(_eoc))

        # V4: Design calibration hints (per-artifact-type budgets)
        self._design_calibration_hints: dict[str, Any] | None = None
        _dch = onboarding.get("design_calibration_hints")
        if _dch and isinstance(_dch, dict):
            self._design_calibration_hints = _dch
            logger.info("Design calibration hints loaded: %d types", len(_dch))

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
    # Generation Manifest (run provenance, pipeline mode only)
    # R2: Staleness detection removed — subsumed by content-addressable
    # generation cache (AC-R3). Manifest write retained for run provenance.
    # -----------------------------------------------------------------------

    _MANIFEST_SCHEMA_VERSION = "1.1.0"
    _MANIFEST_FILENAME = "generation-manifest.json"

    def _manifest_path(self) -> Path:
        """Return the path to the generation manifest file."""
        return self.project_root / ".startd8" / self._MANIFEST_FILENAME

    # ------------------------------------------------------------------
    # REQ-MP-1105: Cross-task element cache assembly
    # ------------------------------------------------------------------

    def _try_element_cache_assembly(
        self, feature: "FeatureSpec",
    ) -> Optional[GenerationResult]:
        """Attempt to assemble a feature entirely from cached element code.

        Iterates the feature's ForwardElementSpecs via the forward manifest.
        For each element with a ``source_contract_id``, checks whether the
        element registry already holds generated code (stored in
        ``entry.extra["code"]``).  If ALL elements are present and their
        checksums are current, the feature is assembled deterministically
        from cached code with zero LLM cost.

        If SOME elements hit cache, the method stores pre-fill info in
        ``feature.metadata["_prefill_elements"]`` for the generator to use
        and returns ``None`` (fall through to normal generation).

        If NONE hit cache, or if the registry / manifest is unavailable,
        returns ``None`` immediately.

        Any error is logged and the method returns ``None`` so the normal
        generation path proceeds (non-fatal).

        Args:
            feature: The feature spec being developed.

        Returns:
            A ``GenerationResult`` with ``cost_usd=0.0`` and
            ``strategy="element_reuse"`` if all elements were assembled from
            cache, or ``None`` to fall through to normal generation.
        """
        if self._element_registry is None or self._forward_manifest is None:
            return None

        try:
            fm = self._forward_manifest
            target_files = feature.target_files or []
            if not target_files:
                return None

            # Collect all element specs for this feature's target files
            all_element_specs: list = []  # list of (file_path, element_spec) tuples
            for path in target_files:
                file_spec = fm.file_specs.get(path)
                if file_spec is None:
                    continue
                for elem in file_spec.elements:
                    if elem.source_contract_id:
                        all_element_specs.append((path, elem))

            if not all_element_specs:
                return None

            # Check each element against the registry
            cached_elements: dict = {}  # element_id -> (file_path, code)
            stale_elements: list = []
            missing_elements: list = []

            for file_path, elem_spec in all_element_specs:
                eid = elem_spec.source_contract_id
                entry = self._element_registry.get(eid)
                if entry is None:
                    missing_elements.append(eid)
                    continue

                cached_code = entry.extra.get("code")
                if not cached_code:
                    missing_elements.append(eid)
                    continue

                # Gap-D: Per-element staleness check using element-level
                # context checksum instead of manifest-wide source_checksum.
                from startd8.element_registry import (
                    compute_element_context_checksum,
                    is_stale,
                )
                current_checksum = compute_element_context_checksum(
                    element_name=elem_spec.name,
                    element_kind=elem_spec.kind.value if hasattr(elem_spec.kind, "value") else str(elem_spec.kind),
                    signature=str(elem_spec.signature) if elem_spec.signature else "",
                    parent_class=elem_spec.parent_class or "",
                    bases=list(elem_spec.bases) if getattr(elem_spec, "bases", None) else None,
                    decorators=list(elem_spec.decorators) if getattr(elem_spec, "decorators", None) else None,
                )
                if is_stale(entry, current_checksum):
                    stale_elements.append(eid)
                    continue

                cached_elements[eid] = (file_path, cached_code)

            elements_total = len(all_element_specs)
            elements_from_cache = len(cached_elements)
            elements_stale = len(stale_elements)
            elements_missing = len(missing_elements)

            logger.info(
                "Element cache check for '%s': %d/%d cached, %d stale, %d missing",
                feature.name,
                elements_from_cache,
                elements_total,
                elements_stale,
                elements_missing,
            )

            # ALL elements hit cache: assemble from cached code
            if elements_from_cache == elements_total and elements_total > 0:
                return self._assemble_from_element_cache(
                    feature, cached_elements, elements_total,
                    all_element_specs,
                )

            # SOME elements hit cache: store pre-fill info for generator
            if elements_from_cache > 0:
                if feature.metadata is None:
                    feature.metadata = {}
                feature.metadata["_prefill_elements"] = {
                    eid: code for eid, (_, code) in cached_elements.items()
                }
                logger.info(
                    "Partial cache hit for '%s': %d elements pre-filled, "
                    "%d to generate",
                    feature.name,
                    elements_from_cache,
                    elements_total - elements_from_cache,
                )

            # Fall through to normal generation
            return None

        except Exception as exc:
            logger.debug(
                "Element cache assembly failed for '%s' (non-fatal): %s",
                feature.name,
                exc,
            )
            return None

    def _assemble_from_element_cache(
        self,
        feature: "FeatureSpec",
        cached_elements: dict,
        elements_total: int,
        all_element_specs: list,
    ) -> Optional[GenerationResult]:
        """Assemble a feature's files from cached element code.

        Uses the forward manifest's skeleton as the assembly scaffold and
        splices cached element code into it via ``splice_body_into_skeleton``.
        This preserves class wrappers, imports, and module structure that
        would be lost by naive concatenation.

        Falls back to ``"\\n\\n".join()`` only when no skeleton is available,
        with ``_detect_assembly_defect`` as a safety net.

        Args:
            feature: The feature being assembled.
            cached_elements: Mapping of element_id -> (file_path, code).
            elements_total: Total number of elements for metadata.
            all_element_specs: List of (file_path, ForwardElementSpec) tuples
                for all elements in this feature.

        Returns:
            A successful ``GenerationResult`` or ``None`` if assembly
            validation fails (falls through to normal generation).
        """
        try:
            from startd8.micro_prime.prime_adapter import _detect_assembly_defect
        except ImportError:
            _detect_assembly_defect = None  # type: ignore[assignment]

        try:
            from startd8.micro_prime.splicer import splice_body_into_skeleton
        except ImportError:
            splice_body_into_skeleton = None  # type: ignore[assignment]

        # Build element_id -> ForwardElementSpec lookup for splicing
        element_spec_by_id: Dict[str, Any] = {}
        for _fp, elem_spec in all_element_specs:
            if elem_spec.source_contract_id:
                element_spec_by_id[elem_spec.source_contract_id] = elem_spec

        # Group cached elements by file path, preserving element specs
        # Each entry: (element_id, code, element_spec_or_None)
        file_elements: Dict[str, list] = {}
        for eid, (file_path, code) in cached_elements.items():
            elem_spec = element_spec_by_id.get(eid)
            file_elements.setdefault(file_path, []).append((eid, code, elem_spec))

        # Resolve skeletons from seed data
        skeletons = getattr(self, "_skeleton_sources", {}) or {}

        # Write assembled files
        output_dir = (
            self.code_generator.output_dir
            if hasattr(self.code_generator, "output_dir")
            else self.project_root / "generated"
        )
        generated_files: List[Path] = []
        used_skeleton = False

        for file_path, elements in file_elements.items():
            skeleton = skeletons.get(file_path, "")

            # Option A: Skeleton-based assembly via splicer
            if skeleton and splice_body_into_skeleton is not None:
                assembled = skeleton
                splice_failures = 0
                for eid, code, elem_spec in elements:
                    if elem_spec is None:
                        logger.debug(
                            "No element spec for %s in %s — skipping splice",
                            eid, file_path,
                        )
                        splice_failures += 1
                        continue
                    splice_result = splice_body_into_skeleton(code, elem_spec, assembled)
                    if splice_result.code is not None:
                        assembled = splice_result.code
                    else:
                        logger.debug(
                            "Splice failed for %s in %s — element skipped",
                            elem_spec.name, file_path,
                        )
                        splice_failures += 1

                if splice_failures == len(elements):
                    logger.warning(
                        "All %d element splices failed for '%s' — "
                        "falling through to generation",
                        len(elements), file_path,
                    )
                    return None

                used_skeleton = True
                logger.info(
                    "Skeleton-based cache assembly for '%s': "
                    "%d/%d elements spliced",
                    file_path,
                    len(elements) - splice_failures,
                    len(elements),
                )
            else:
                # Fallback: concatenate code blocks (no skeleton available)
                assembled = "\n\n".join(code for _, code, _ in elements)
                if skeleton:
                    logger.debug(
                        "Splicer unavailable for '%s' — using concatenation",
                        file_path,
                    )
                else:
                    logger.debug(
                        "No skeleton for '%s' — using concatenation fallback",
                        file_path,
                    )

            # Option C safety net: defect detection on assembled output
            if _detect_assembly_defect is not None:
                defect = _detect_assembly_defect(assembled, file_path)
                if defect:
                    logger.warning(
                        "Element cache assembly defect in '%s': %s — "
                        "falling through to generation",
                        file_path,
                        defect,
                    )
                    return None

            target = output_dir / file_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(assembled, encoding="utf-8")
            generated_files.append(target)

        logger.info(
            "Element cache assembly complete for '%s': %d files, "
            "%d elements, $0.00 cost",
            feature.name,
            len(generated_files),
            elements_total,
        )

        return GenerationResult(
            success=True,
            generated_files=generated_files,
            cost_usd=0.0,
            input_tokens=0,
            output_tokens=0,
            iterations=0,
            model="",
            metadata={
                "strategy": "element_reuse",
                "elements_from_cache": elements_total,
                "elements_generated": 0,
                "skeleton_assembly": used_skeleton,
            },
        )

    def _write_generation_manifest(self, result_dict: Dict[str, Any]) -> None:
        """Write generation manifest to disk (pipeline mode only).

        The manifest captures run provenance (costs, features, config).
        Written with 0o600 permissions since it contains cost data.

        I/O errors are logged but do not fail the workflow.
        """
        if self.execution_mode != ExecutionMode.PIPELINE.value:
            return

        manifest = {
            "schema_version": self._MANIFEST_SCHEMA_VERSION,
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
            os.chmod(path, 0o600)
            logger.info("Generation manifest written to %s", path)
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
                if not self.develop_feature(feature, prior_error=prior_error):
                    return False
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
        draft_system, draft_mode = get_drafter_system_prompt(
            existing_files=existing_files,
            language_role=gen_context.get("language_role"),
            coding_standards=gen_context.get("coding_standards"),
        )
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
        edit_min_pct = gen_context.get("edit_min_pct", 80)
        output_format = build_output_format(
            target_files=feature.target_files,
            existing_files=existing_files,
            edit_min_pct=edit_min_pct,
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
            # Accept both "prompt_hints" (new format) and "suggestions" (legacy script format)
            if "suggestions" in config and "prompt_hints" not in config:
                config["prompt_hints"] = config.pop("suggestions")
            if "prompt_hints" in config and not isinstance(config["prompt_hints"], list):
                logger.warning("Kaizen config prompt_hints must be a list — ignoring: %s", path)
                return None
            hints = config.get("prompt_hints") or []
            if not hints:
                logger.debug("Kaizen config has 0 hints — skipping: %s", path)
                return None
            logger.info("Kaizen config loaded: %s (%d hints)", path, len(hints))
            return config
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Kaizen config invalid — proceeding without it: %s", exc)
            return None

    def _auto_discover_kaizen_config(self) -> None:
        """Auto-discover kaizen-suggestions.json from prior run output dir.

        Called during run() when no explicit --kaizen-config was provided.
        Search order:
        1. Current output dir (same-dir re-run)
        2. Sibling run directories sorted by name descending (most recent first)
        3. Parent of output dir (flat layout)

        Fail-open: logs and continues if not found or invalid.
        """
        if self._kaizen.config is not None:
            return  # Explicit config already loaded — don't override

        try:
            output_dir = self._resolve_output_dir()
        except Exception:
            return

        # Search candidates in priority order.
        # Walk up from output_dir looking for sibling run directories.
        # Handles multiple nesting depths:
        #   - Flat:   output_dir = .../run-093/                 (runs are siblings)
        #   - Nested: output_dir = .../run-095/plan-ingestion/  (runs are at grandparent)
        #   - Deep:   output_dir = .../run-099/plan-ingestion/generated/ (runs at great-grandparent)
        candidates: list[Path] = []

        # Identify the current run's root directory so we can exclude
        # our own files (which don't exist at run start but may exist
        # on re-runs or if the postmortem already wrote them).
        current_run_root = output_dir
        for _p in [output_dir] + list(output_dir.parents):
            if _p.name.startswith("run-"):
                current_run_root = _p
                break

        # Walk up to 4 ancestor levels looking for sibling run directories
        seen_ancestors: set = set()
        ancestor = output_dir
        for _depth in range(4):
            ancestor = ancestor.parent
            if not ancestor.is_dir() or ancestor in seen_ancestors:
                break
            seen_ancestors.add(ancestor)
            # Check siblings at this level — sorted descending (newest first)
            try:
                siblings = sorted(ancestor.iterdir(), reverse=True)
            except OSError:
                continue
            for sibling in siblings:
                if not sibling.is_dir() or sibling == output_dir:
                    continue
                # Skip anything inside the current run's tree
                if sibling == current_run_root:
                    continue
                try:
                    sibling.relative_to(current_run_root)
                    continue
                except ValueError:
                    pass
                try:
                    current_run_root.relative_to(sibling)
                    continue  # sibling is an ancestor of current run — skip
                except ValueError:
                    pass
                candidates.append(sibling / "kaizen-suggestions.json")
                candidates.append(sibling / "plan-ingestion" / "kaizen-suggestions.json")

        for path in candidates:
            if not path.is_file():
                continue
            loaded = self._load_kaizen_config(str(path))
            if loaded:
                self._kaizen.config = loaded
                logger.info(
                    "Kaizen auto-discovered from prior run: %s (%d hints)",
                    path,
                    len(loaded.get("prompt_hints") or []),
                )
                return

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
        if not self._kaizen.config:
            return
        try:
            seen_hashes: set = set()
            phase_counts: Dict[str, int] = {}
            hints_collected: list = []

            for h in self._kaizen.config.get("prompt_hints") or []:
                if not isinstance(h, dict):
                    continue
                phase = h.get("phase", "all")
                # Accept both "hint" (CAUSE_TO_SUGGESTION format) and
                # "suggested_action" (generate_kaizen_suggestions format)
                hint_text = h.get("hint", "") or h.get("suggested_action", "")
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
                # Also populate prior_security_findings for drafter (Issue #20:
                # drafter reads this field but it was never populated).
                sec_hints = [
                    h for h in hints_collected
                    if any(kw in h.lower() for kw in ("sql", "injection", "parameterized", "credential", "security"))
                ]
                if sec_hints:
                    gen_context["prior_security_findings"] = sec_hints
                logger.debug(
                    "Kaizen: injected %d hint(s) (%d security) into gen_context for '%s'",
                    len(hints_collected),
                    len(sec_hints),
                    gen_context.get("feature_name", "?"),
                )
        except Exception as exc:
            logger.warning("Kaizen: hint injection failed (non-fatal): %s", exc)

    def _inject_exemplar(
        self, feature: "FeatureSpec", gen_context: Dict[str, Any],
    ) -> None:
        """Inject proven exemplar into gen_context (REQ-PEP-100).

        Loads the exemplar registry, computes the task's fingerprint, finds
        the best match, and injects it as ``gen_context["exemplar"]``.
        Non-fatal — failures are logged and silently swallowed.
        """
        try:
            from startd8.exemplars.models import ConfigFingerprint
            from startd8.exemplars.registry import ExemplarRegistry

            # Locate registry file
            output_dir = getattr(self, "_output_dir", None)
            if not output_dir:
                return
            registry_path = Path(output_dir) / "exemplar-registry.json"
            if not registry_path.is_file():
                return

            registry = ExemplarRegistry.load(registry_path)
            if len(registry) == 0:
                return

            # Compute fingerprint for current task
            target_files = gen_context.get("target_files", [])
            if not target_files:
                target_files = getattr(feature, "target_files", [])
            if not target_files:
                return

            primary_file = target_files[0] if isinstance(target_files, list) else str(target_files)
            feature_meta = getattr(feature, "metadata", None) or {}
            language = feature_meta.get("language", "")
            transport = "none"
            svc_meta = feature_meta.get("service_metadata", {})
            if isinstance(svc_meta, dict):
                transport = svc_meta.get("transport_protocol", "none").lower()

            fp = ConfigFingerprint.compute(
                primary_file, language=language, transport=transport,
            )

            match = registry.find_best_match(fp)
            if not match:
                return

            match_type = registry.get_match_type(fp)

            # Build exemplar context dict for spec_builder / drafter injection
            exemplar_ctx: Dict[str, Any] = {
                "id": match.id,
                "fingerprint": str(match.fingerprint),
                "source_run_id": match.source_run_id,
                "source_feature_id": match.source_feature_id,
                "match_type": match_type,
                "scores": {
                    "requirement_score": match.scores.requirement_score,
                    "disk_quality_score": match.scores.disk_quality_score,
                },
                "code_summary": match.code_summary,
                "code_excerpt": match.code_summary,  # code_summary is the excerpt
                "language": match.fingerprint.language,
            }

            # Try to load full spec/code artifacts for richer injection
            if output_dir:
                base = Path(output_dir)
                if match.spec_artifact_path:
                    spec_file = base / match.spec_artifact_path
                    if spec_file.is_file():
                        try:
                            spec_text = spec_file.read_text(encoding="utf-8", errors="replace")
                            lines = spec_text.splitlines()[:80]
                            exemplar_ctx["spec_excerpt"] = "\n".join(lines)
                        except OSError:
                            pass
                if match.code_artifact_path:
                    code_file = base / match.code_artifact_path
                    if code_file.is_file():
                        try:
                            code_text = code_file.read_text(encoding="utf-8", errors="replace")
                            lines = code_text.splitlines()[:100]
                            exemplar_ctx["code_excerpt"] = "\n".join(lines)
                        except OSError:
                            pass

            gen_context["exemplar"] = exemplar_ctx
            logger.info(
                "Exemplar injected for '%s': %s (match=%s, score=%.2f)",
                feature.name, match.id, match_type,
                match.scores.disk_quality_score,
            )
        except Exception as exc:
            logger.warning("Exemplar injection failed (non-fatal): %s", exc)

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

        Only called when self._kaizen.enabled is True.
        """
        if not self._kaizen.enabled or self._kaizen.prompt_dir is None:
            return
        try:
            run_id = os.environ.get("KAIZEN_RUN_ID", "standalone")
            safe_fid = self._sanitize_feature_id(feature.id)
            prompt_dir = self._kaizen.prompt_dir / run_id / safe_fid

            # REQ-KZ-BUG-004: Ensure context is JSON serializable (no raw ForwardManifest objects)
            serializable_context = dict(gen_context)
            for key in ["manifest", "forward_manifest"]:
                val = serializable_context.get(key)
                if val is not None and hasattr(val, "dict"):
                    serializable_context[key] = val.dict()

            # AC-R2: Prefer generator-native prompts when available,
            # avoiding the parallel prompt-construction in _build_phase_prompts().
            gen_prompts: Dict[str, str] = {}
            if result is not None and hasattr(result, "prompts") and result.prompts:
                # Map generator prompt keys to Kaizen filename convention
                for key, content in result.prompts.items():
                    gen_prompts[f"{key}_prompt.md"] = content
            # Responses are captured independently — un-gated from prompts
            # so that micro-prime results or partial Lead Contractor results
            # still produce response files even when prompts are empty.
            if result is not None and hasattr(result, "responses") and result.responses:
                for key, content in result.responses.items():
                    gen_prompts[f"{key}_response.md"] = content
            if gen_prompts:
                prompts = gen_prompts
            else:
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
        draft_system, draft_mode = get_drafter_system_prompt(
            existing_files=existing_files,
            language_role=gen_context.get("language_role"),
            coding_standards=gen_context.get("coding_standards"),
        )
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
        edit_min_pct = gen_context.get("edit_min_pct", 80)
        output_format = build_output_format(
            target_files=feature.target_files,
            existing_files=existing_files,
            edit_min_pct=edit_min_pct,
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

        Orchestrates 9 phases (AC-R1 refactor, R2 staleness removal):
          0. Copy shortcut (identical-copy tasks bypass generation)
          1. Preflight validation
          2. Mottainai reuse (skip if generated files still current)
          3. Context assembly (build gen_context for generator)
          4. Content-addressable cache lookup (AC-R3)
          5. Complexity routing (select tier-specific generator)
          6. Element cache assembly (skip if all elements in registry)
          7. Code generation (the actual LLM call)
          8. Quality gate (reject low-score output)
          9. Result handling (persist state, accumulate cost)

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

        # Phase 1: Preflight
        should_proceed, decomposition_info = self.pre_flight_validation(feature)
        if not should_proceed:
            reason = decomposition_info.get('reason', 'Size exceeds safe limits')
            logger.error("Pre-flight failed for '%s': %s", feature.name, reason, extra={'feature_name': feature.name, 'reason': reason})
            self.queue.fail_feature(feature.id, f"Pre-flight failed: {decomposition_info.get('reason')}")
            return False
        self.queue.start_feature(feature.id)

        # Phase 0: Copy shortcut
        copy_result = self._try_copy_shortcut(feature)
        if copy_result is not None:
            return copy_result

        # Phase 0.5: Uncomment shortcut (REQ-TCW-300)
        uncomment_result = self._try_uncomment_shortcut(feature)
        if uncomment_result is not None:
            return uncomment_result

        # Phase 0.6: Deterministic build file shortcut (REQ-DFA-101a)
        # If all target files are build/config files that were already
        # generated by _ensure_dependency_file(), skip LLM generation.
        det_result = self._try_deterministic_file_shortcut(feature)
        if det_result is not None:
            return det_result

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

        self._log_element_registry_availability(feature)

        logger.info("Running code generation for '%s'...", feature.name)
        try:
            # Phase 2: Mottainai reuse
            reuse_result = self._try_mottainai_reuse(feature)
            if reuse_result is not None:
                return reuse_result

            # Phase 3: Context assembly
            gen_context = self._build_generation_context(feature, prior_error)

            # P0: Wire language profile to checkpoint and merge strategy
            self._apply_language_profile_to_engine()

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

            # Thread additional context into gen_context
            self._thread_supplemental_context(feature, gen_context)

            # Kaizen: persist real-run prompts (REQ-KZ-200) — non-fatal
            self._persist_kaizen_prompts(feature, gen_context, result=None)

            # R2: Staleness detection removed — subsumed by AC-R3 cache below.

            # Phase 4: Content-addressable cache lookup (AC-R3)
            cache_hit = self._try_generation_cache(feature, gen_context)
            if cache_hit is not None:
                self.total_cost_usd += cache_hit.cost_usd
                self.total_input_tokens += cache_hit.input_tokens
                self.total_output_tokens += cache_hit.output_tokens
                self._accept_generation_result(feature, cache_hit)
                return True

            # Phase 5: Complexity routing
            generator = self._route_complexity(feature, gen_context)

            # Phase 6: Element cache assembly
            cache_result = self._try_element_cache_assembly(feature)
            if cache_result is not None:
                result = cache_result
                self.total_cost_usd += result.cost_usd
                self.total_input_tokens += result.input_tokens
                self.total_output_tokens += result.output_tokens
                self._persist_kaizen_prompts(feature, gen_context, result=result)
                self._accept_generation_result(feature, result)
                return True

            # Phase 7: Code generation (the actual LLM call)
            with _prime_tracer.start_as_current_span(
                "prime_contractor.feature.generate",
                attributes={
                    "feature.id": feature.id,
                    "feature.name": feature.name,
                    "feature.target_files_count": len(feature.target_files or []),
                },
            ) as gen_span:
                result: GenerationResult = generator.generate(
                    task=feature.description,
                    context=gen_context,
                    target_files=feature.target_files,
                )
                gen_span.set_attribute("generation.success", result.success)
                gen_span.set_attribute("generation.cost_usd", result.cost_usd)
                gen_span.set_attribute("generation.input_tokens", result.input_tokens)
                gen_span.set_attribute("generation.output_tokens", result.output_tokens)
                gen_span.set_attribute("generation.model", result.model)

            # Kaizen: persist prompts + responses (REQ-KZ-200, 201) — non-fatal
            self._persist_kaizen_prompts(feature, gen_context, result=result)

            # Accumulate tokens/cost regardless of success so postmortem
            # cost reporting is accurate.  _accept_generation_result still
            # runs on success (sets feature status, etc.), but tokens must
            # be counted even for failed generations.
            self.total_cost_usd += result.cost_usd
            self.total_input_tokens += result.input_tokens
            self.total_output_tokens += result.output_tokens

            # Phase 8: Quality gate
            if not self._check_quality_gate(feature, result):
                return False

            # Phase 9: Result handling
            if result.success:
                self._cache_generation_result(feature, result, gen_context)
                self._accept_generation_result(feature, result)
                # Micro Prime dry-run: classification-only, skip integration
                if result.metadata and result.metadata.get("dry_run"):
                    self.queue.complete_feature(feature.id)
                    self._save_queue_state_with_mode()
                return True
            else:
                error_msg = result.error or 'Code generation failed'
                logger.error("Code generation failed for '%s': %s", feature.name, error_msg, extra={'feature_name': feature.name, 'error': error_msg})
                # Populate generated_files from the result so
                # _clean_failed_feature can find and delete them.
                if result.generated_files:
                    feature.generated_files = [str(f) for f in result.generated_files]
                self._clean_failed_feature(feature)
                self.queue.fail_feature(feature.id, error_msg)
                return False
        except Exception as e:
            error_msg = f'Exception during code generation: {e}'
            logger.error('%s', error_msg, exc_info=True, extra={'feature_name': feature.name})
            self._clean_failed_feature(feature)
            self.queue.fail_feature(feature.id, error_msg)
            return False

    # ── develop_feature phase methods (AC-R1) ─────────────────────────

    def _try_copy_shortcut(self, feature: FeatureSpec) -> Optional[bool]:
        """Phase 0: Detect and execute file-copy shortcut.

        Returns True (success), False (failure), or None (not a copy task).
        """
        # REQ-MP-1002: If copy_source_task_id is not already set, attempt
        # detection from description signals + depends_on.
        if feature.copy_source_task_id is None:
            from .copy_detection import CopySource, detect_copy

            predecessor = None
            deps = feature.dependencies or []
            if len(deps) == 1:
                predecessor = self.queue.get_feature(deps[0])
            copy_source = detect_copy(feature, predecessor=predecessor)
            if isinstance(copy_source, CopySource):
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
        return None

    def _try_uncomment_shortcut(self, feature: FeatureSpec) -> Optional[bool]:
        """Phase 0.5: Deterministic uncomment for Category A TODO tasks (REQ-TCW-300).

        Returns True (success), False (failure), or None (not an uncomment task).
        Follows the same contract as ``_try_copy_shortcut``.
        """
        if feature.metadata.get("task_type") != "uncomment":
            return None

        from startd8.validators.todo_scanner import uncomment_block, _detect_language

        target_files = feature.target_files or []
        if not target_files:
            logger.warning("Uncomment task '%s' has no target files", feature.name)
            self.queue.fail_feature(feature.id, "No target files for uncomment")
            return False

        try:
            modified_files: list[str] = []
            for tf in target_files:
                file_path = Path(tf)
                if not file_path.is_absolute():
                    file_path = self.project_root / tf
                if not file_path.is_file():
                    logger.warning("Uncomment target not found: %s", file_path)
                    continue

                content = file_path.read_text(encoding="utf-8", errors="replace")
                language = _detect_language(str(file_path))
                result, count = uncomment_block(content, language=language)
                if count > 0:
                    file_path.write_text(result, encoding="utf-8")
                    modified_files.append(str(file_path))
                    logger.info(
                        "Uncommented %d block(s) in %s (cost=$0.00)",
                        count, file_path,
                    )

            if not modified_files:
                logger.info(
                    "Uncomment shortcut for '%s': no commented-out blocks found in %d file(s)",
                    feature.name, len(target_files),
                )
            feature.generated_files = modified_files if modified_files else [str(f) for f in target_files]
            feature.status = FeatureStatus.GENERATED
            self._save_queue_state_with_mode()
            logger.info(
                "Uncomment shortcut completed for '%s': %d file(s) modified, cost=$0.00",
                feature.name, len(modified_files),
            )
            return True

        except (OSError, ValueError) as exc:
            logger.error(
                "Uncomment failed for '%s': %s", feature.name, exc,
                exc_info=True,
            )
            self.queue.fail_feature(feature.id, f"Uncomment failed: {exc}")
            return False

    # Build/config file extensions whose content is deterministically generated
    # by _ensure_dependency_file() or LanguageProfile.generate_*() methods.
    _DETERMINISTIC_BUILD_NAMES: frozenset = frozenset({
        "go.mod", "package.json", "tsconfig.json",
        "settings.gradle", "build.gradle",
    })
    _DETERMINISTIC_BUILD_EXTENSIONS: frozenset = frozenset({
        ".csproj", ".sln",
    })

    def _try_deterministic_file_shortcut(
        self, feature: "FeatureSpec",
    ) -> Optional[bool]:
        """Phase 0.6: Skip LLM for features targeting deterministic build files.

        If every target file is a build/config file that was already generated
        by ``_ensure_dependency_file()`` or a solution/project generator, mark
        the feature as GENERATED with $0.00 cost (REQ-DFA-101a).

        Returns True (success), or None (not a build-file-only feature).
        """
        target_files = feature.target_files or []
        if not target_files:
            return None

        for tf in target_files:
            p = Path(tf)
            name = p.name
            if name not in self._DETERMINISTIC_BUILD_NAMES and \
               p.suffix not in self._DETERMINISTIC_BUILD_EXTENSIONS:
                return None  # Has non-build files — proceed to LLM

        # All targets are build/config files — check if they exist on disk
        resolved: list[str] = []
        for tf in target_files:
            p = Path(tf)
            if not p.is_absolute():
                p = self._resolve_output_dir() / tf
            if not p.is_file():
                return None  # File not pre-generated — need LLM
            resolved.append(str(p))

        feature.generated_files = resolved
        feature.status = FeatureStatus.GENERATED
        self._save_queue_state_with_mode()
        logger.info(
            "Deterministic build file shortcut for '%s': %d file(s), cost=$0.00",
            feature.name, len(resolved),
        )
        return True

    def _run_todo_scan_and_inject(
        self,
        max_cost_usd: Optional[float] = None,
    ) -> tuple[int, int]:
        """Scan generated output for TODOs, derive tasks, inject and execute (REQ-TCW-203).

        Returns:
            (succeeded, failed) counts for the injected TODO tasks.
        """
        generated_dir = self._resolve_generated_dir()
        if not generated_dir or not generated_dir.is_dir():
            return 0, 0

        try:
            from startd8.validators.todo_scanner import scan_directory
            from startd8.seeds.todo_derivation import derive_tasks_from_todos

            inventory = scan_directory(
                str(generated_dir),
                instrumentation_contract=self._instrumentation_contract,
            )

            # Filter to actionable categories
            inventory.entries = [
                e for e in inventory.entries if e.category in {"A", "B"}
            ]
            inventory.compute_summary()

            # Persist inventory regardless of whether tasks are derived
            instr_dir = self._resolve_output_dir() / "instrumentation"
            instr_dir.mkdir(parents=True, exist_ok=True)
            inventory.save(instr_dir / "todo-inventory.json")

            if not inventory.entries:
                logger.info("TODO scan: no actionable TODOs in %s", generated_dir)
                return 0, 0

            logger.info(
                "TODO scan: %d entries (A=%d, B=%d)",
                inventory.summary.get("total", 0),
                inventory.summary.get("A", 0),
                inventory.summary.get("B", 0),
            )

            tasks = derive_tasks_from_todos(
                inventory,
                instrumentation_contract=self._instrumentation_contract,
                source_run_id=getattr(self, "_run_id", ""),
            )

            if not tasks:
                return 0, 0

            # Enforce max limit
            max_todo_tasks = 20
            if len(tasks) > max_todo_tasks:
                logger.warning(
                    "TODO scan produced %d tasks, limiting to %d",
                    len(tasks), max_todo_tasks,
                )
                tasks = tasks[:max_todo_tasks]

            # Write seed and inject into queue
            seed = {"schema_version": "1.0.0", "source": "todo-scan", "tasks": tasks}
            seed_path = instr_dir / "instrumentation-seed.json"
            seed_path.write_text(
                json.dumps(seed, indent=2, default=str), encoding="utf-8",
            )

            added = self.queue.add_features_from_seed(str(seed_path))
            logger.info("Injected %d TODO tasks into queue", len(added))

            # Process the injected tasks
            succeeded = 0
            failed = 0
            for spec in added:
                if max_cost_usd is not None and self.total_cost_usd >= max_cost_usd:
                    logger.warning("Cost limit reached during TODO processing")
                    break
                feature = self.queue.get_feature(spec.id)
                if feature is None:
                    continue
                reset_circuit_breaker()
                if self.process_feature(feature):
                    succeeded += 1
                else:
                    failed += 1
                    self.integration_history.append({
                        "feature_name": feature.name,
                        "feature_id": feature.id,
                        "success": False,
                        "cost_usd": getattr(feature, "_cost_usd", 0.0),
                        "error": feature.error_message,
                        "generation_metadata": (feature.metadata or {}).get(
                            "_generation_result_metadata", {},
                        ),
                        "timestamp": datetime.now().isoformat(),
                    })

            self._save_queue_state_with_mode()
            logger.info(
                "TODO completion: %d/%d succeeded",
                succeeded, succeeded + failed,
            )

            # REQ-TCW-303: Update inventory with completion status
            self._update_todo_inventory_status(
                instr_dir / "todo-inventory.json", added,
            )

            return succeeded, failed

        except Exception as exc:
            logger.error("TODO scan failed (non-fatal): %s", exc, exc_info=True)
            return 0, 0

    def _update_todo_inventory_status(
        self,
        inventory_path: Path,
        executed_specs: list,
    ) -> None:
        """Update TODO inventory entries with completion status (REQ-TCW-303).

        After TODO tasks execute, re-reads the inventory JSON and updates
        each entry's ``status`` field: ``completed`` (task passed),
        ``failed`` (task failed), or ``deferred`` (not attempted).
        """
        try:
            data = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        # Build lookup: todo_id → feature status
        status_map: dict[str, str] = {}
        for spec in executed_specs:
            feature = self.queue.get_feature(spec.id)
            if feature is None:
                continue
            # Map TODO entry IDs from the seed task's context
            todo_id = (feature.metadata or {}).get("_todo_context", {}).get("todo_id", "")
            if not todo_id:
                # Fall back: match by feature ID prefix
                todo_id = spec.id
            if feature.status and feature.status.value in ("complete", "generated"):
                status_map[spec.id] = "completed"
            elif feature.status and feature.status.value == "failed":
                status_map[spec.id] = "failed"
            else:
                status_map[spec.id] = "deferred"

        # Update entries — match by sequence (TODO-001 → first entry, etc.)
        for i, entry in enumerate(data.get("entries", [])):
            task_id = f"TODO-{i + 1:03d}"
            entry["status"] = status_map.get(task_id, "deferred")

        try:
            inventory_path.write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8",
            )
            logger.debug("TODO inventory updated with completion status: %s", inventory_path)
        except OSError as exc:
            logger.warning("Could not update TODO inventory: %s", exc)

    def _resolve_generated_dir(self) -> Optional[Path]:
        """Resolve the generated output directory."""
        try:
            generated = self._resolve_output_dir() / "generated"
            if generated.is_dir():
                return generated
        except (OSError, AttributeError):
            pass
        return None

    def _log_element_registry_availability(self, feature: FeatureSpec) -> None:
        """ER-012: Log element registry cache availability for this feature."""
        if not (self._element_registry and self.seed_forward_manifest):
            return
        try:
            fm = self.seed_forward_manifest
            manifest_obj = fm if hasattr(fm, "file_specs") else None
            if manifest_obj and hasattr(manifest_obj, "file_specs"):
                elements_from_cache = 0
                elements_total = 0
                for path in feature.target_files or []:
                    file_spec = manifest_obj.file_specs.get(path)
                    if file_spec:
                        for elem in getattr(file_spec, "elements", []):
                            elements_total += 1
                            eid = getattr(elem, "source_contract_id", None)
                            if eid:
                                cached = self._element_registry.get(eid)
                                if cached and cached.extra.get("code"):
                                    elements_from_cache += 1
                if elements_total > 0:
                    logger.info(
                        "Feature '%s': %d/%d elements available in registry",
                        feature.name, elements_from_cache, elements_total,
                    )
        except Exception as exc:
            logger.debug("Element registry pre-check failed: %s", exc)

    def _try_mottainai_reuse(self, feature: FeatureSpec) -> Optional[bool]:
        """Phase 2: Mottainai Gap 14 — skip generation if files still current.

        Returns True (reused), or None (must generate).
        """
        if not (feature.generated_files and not self.force_regenerate):
            return None

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
        return None

    def _build_generation_context(
        self, feature: FeatureSpec, prior_error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Phase 3: Build gen_context via context resolution strategy."""
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

        prior_error_feedback = None
        if prior_error:
            from startd8.workflows.builtin.prompts import format_prompt as _fmt_ctx
            prior_error_feedback = _fmt_ctx(
                "prime_context", "prior_error_feedback", prior_error=prior_error,
            ).strip()

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

        # REQ-PEM-008: Thread validation flag
        if self._validation_override is not None:
            gen_context["_run_validators"] = self._validation_override
        else:
            gen_context["_run_validators"] = (
                self.execution_mode == ExecutionMode.PIPELINE.value
            )

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

        # PC-O1: Populate existing_files for edit tasks
        self._populate_existing_files(feature, gen_context)

        # REQ-MP-701: Forward deserialized ForwardManifest for Micro Prime
        if self._forward_manifest is not None:
            gen_context["manifest"] = self._forward_manifest

        # FR-MPA-007: Forward pre-rendered skeletons from seed
        if self._skeleton_sources and "skeletons" not in gen_context:
            gen_context["skeletons"] = dict(self._skeleton_sources)

        # REQ-DDS-002: Thread design_doc_sections from feature metadata
        _design_sections = feature.metadata.get("design_doc_sections", [])
        if _design_sections:
            gen_context["design_doc_sections"] = _design_sections

        # PC-Q3: Propagate edit_min_pct from Prime config into gen_context
        gen_context["edit_min_pct"] = self.edit_min_pct

        # R-ML-003: Resolve language profile from target files.
        # Pass all batch target files as context so language-neutral files
        # (Dockerfiles, config files) can infer language from siblings.
        # Cached on first call — queue contents don't change mid-run.
        from ..languages import resolve_language
        if not hasattr(self, "_batch_target_files"):
            self._batch_target_files: Optional[List[str]] = None
            if hasattr(self, "queue") and self.queue is not None:
                self._batch_target_files = [
                    tf
                    for fspec in self.queue.features.values()
                    if fspec.target_files
                    for tf in fspec.target_files
                ]
        language_profile = resolve_language(
            feature.target_files, batch_target_files=self._batch_target_files,
        )
        self._language_profile = language_profile
        gen_context["language_profile"] = language_profile
        gen_context["language_role"] = language_profile.system_prompt_role
        gen_context["coding_standards"] = language_profile.coding_standards

        # --- Mottainai: Thread all extracted context into gen_context ---
        # Each field is injected only if present and not already set by a
        # higher-priority source (e.g., per-task enrichment from seed).

        # REQ-ICD-106: Security contract
        if self._security_contract and "security_contract" not in gen_context:
            gen_context["security_contract"] = self._security_contract

        # REQ-TCW-250: Instrumentation contract
        if self._instrumentation_contract and "instrumentation_contract" not in gen_context:
            gen_context["instrumentation_contract"] = self._instrumentation_contract

        # REQ-TCW-251: Guidance context
        if self._guidance_context and "guidance" not in gen_context:
            gen_context["guidance"] = self._guidance_context

        # V2: Pre-resolved artifact parameters
        if self._resolved_artifact_params and "resolved_artifact_parameters" not in gen_context:
            gen_context["resolved_artifact_parameters"] = self._resolved_artifact_params

        # V3: Expected output contracts
        if self._expected_output_contracts and "expected_output_contracts" not in gen_context:
            gen_context["expected_output_contracts"] = self._expected_output_contracts

        # V4: Per-task calibration from design_calibration_hints
        if self._design_calibration_hints and "implement_max_output_tokens" not in gen_context:
            _artifact_type = feature.metadata.get("artifact_type", "")
            _cal = self._design_calibration_hints.get(_artifact_type, {})
            if isinstance(_cal, dict) and _cal.get("max_tokens"):
                gen_context["implement_max_output_tokens"] = _cal["max_tokens"]

        # REQ-RFL-240: Inject within-run quality hints from accumulator
        if self._quality_accumulator is not None:
            existing_kaizen = set(
                gen_context.get("kaizen_categories", []),
            )
            hints = self._quality_accumulator.build_spec_hints(
                existing_kaizen_categories=existing_kaizen,
            )
            if hints:
                gen_context["run_quality_hints"] = hints
            trend = self._quality_accumulator.get_quality_trend()
            if trend == "declining":
                gen_context["quality_trend_warning"] = (
                    "Quality declining: last 3 features show decreasing "
                    "disk quality scores. Pay extra attention to imports, "
                    "stubs, and contract compliance."
                )

        return gen_context

    def _apply_language_profile_to_engine(self) -> None:
        """Wire resolved language profile to checkpoint and merge strategy.

        Called after ``_build_generation_context()`` sets ``self._language_profile``.
        Updates the checkpoint's language awareness and re-selects the merge
        strategy based on the target language (e.g. SimpleMerge for Go instead
        of AST merge).
        """
        profile = self._language_profile
        if profile is None:
            return

        # Wire language profile to checkpoint for syntax/lint dispatch
        self.checkpoint._language_profile = profile
        if self._engine.checkpoint is not None:
            self._engine.checkpoint._language_profile = profile

        # Wire language profile to integration engine for repair gating
        self._engine._language_profile = profile

        # Re-select merge strategy based on language preference
        lang_id = profile.language_id
        if lang_id != "python":
            registry = get_registry()
            new_strategy = registry.get_default_merge_strategy(
                language_id=lang_id,
            )()
            self.merge_strategy = new_strategy
            self._engine.merge_strategy = new_strategy
            logger.info(
                "Merge strategy re-selected for language=%s: %s",
                lang_id, type(new_strategy).__name__,
            )

        # Generate dependency file if the language profile provides one
        # and it doesn't already exist on disk (e.g. go.mod, package.json).
        # For multi-service repos, derive the service directory from
        # target_files so go.mod lands next to the source (not project root).
        self._ensure_dependency_file(profile)

    def _ensure_dependency_file(self, profile: Any) -> None:
        """Generate a language-specific dependency file if one doesn't exist.

        Writes go.mod, package.json, or build.gradle based on the language
        profile and seed service metadata. Skips if the file already exists
        or if the profile doesn't support generation.

        For multi-service repos (e.g. online-boutique), the dependency file
        is placed in the service subdirectory derived from target_files
        (e.g. ``src/shippingservice/go.mod``), not at project root.
        """
        if not hasattr(profile, "generate_dependency_file"):
            return

        build_patterns = profile.build_file_patterns
        if not build_patterns:
            return

        # Derive service directory from target_files.
        # In multi-service repos, source files live in subdirectories
        # (e.g. src/shippingservice/main.go), and the dependency file
        # (go.mod) must be co-located with the source, not at project root.
        service_dir = self.project_root
        if self._language_profile is not None:
            src_exts = set(profile.source_extensions)
            # Find common parent directory of all target source files
            target_dirs: set[Path] = set()
            for queue_feat in self.queue.features.values():
                for tf in (queue_feat.target_files or []):
                    p = Path(tf)
                    if p.suffix in src_exts:
                        abs_p = p if p.is_absolute() else (self.project_root / p)
                        target_dirs.add(abs_p.parent)
            if target_dirs:
                # Use the common parent of all target directories
                dirs_list = sorted(target_dirs)
                common = dirs_list[0]
                for d in dirs_list[1:]:
                    # Find longest common path prefix
                    try:
                        d.relative_to(common)
                    except ValueError:
                        # Not a child of common — walk up common
                        while common != self.project_root:
                            common = common.parent
                            try:
                                d.relative_to(common)
                                break
                            except ValueError:
                                continue
                service_dir = common

        # Check if any build file already exists in the service directory
        for pattern in build_patterns:
            if (service_dir / pattern).exists():
                return

        # Extract metadata for generation
        service_name = ""
        module_path = ""
        dependencies: list = []
        if self.seed_service_metadata:
            service_name = self.seed_service_metadata.get("service_name", "")
            module_path = self.seed_service_metadata.get("module_path", "")
            dependencies = self.seed_service_metadata.get("runtime_dependencies", [])

        if not service_name and not module_path:
            # Derive service_name from the service directory name
            if service_dir != self.project_root:
                service_name = service_dir.name
            else:
                return  # Not enough metadata to generate

        try:
            content = profile.generate_dependency_file(
                project_root=self.project_root,
                service_name=service_name,
                module_path=module_path,
                dependencies=dependencies,
                metadata=self.seed_service_metadata,
            )
        except Exception as exc:
            logger.warning(
                "Dependency file generation failed for %s: %s",
                profile.language_id, exc,
            )
            return

        if not content:
            return

        # Write to the service directory (e.g. src/shippingservice/go.mod)
        target = service_dir / build_patterns[0]
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            logger.info(
                "Generated %s for language=%s at %s (%d bytes)",
                target.name, profile.language_id,
                target.relative_to(self.project_root), len(content),
            )
        except OSError as exc:
            logger.warning("Failed to write %s: %s", target, exc)

    def _thread_supplemental_context(
        self, feature: FeatureSpec, gen_context: Dict[str, Any],
    ) -> None:
        """Thread reference implementation and Kaizen hints into gen_context."""
        # REQ-MP-1003: Thread reference_implementation
        ref_impl = feature.metadata.get("_reference_implementation") if feature.metadata else None
        if ref_impl:
            gen_context["reference_implementation"] = ref_impl
            logger.info(
                "Injected reference_implementation for '%s' (%d chars)",
                feature.name, len(ref_impl),
            )

        # Kaizen prompt hints injection (REQ-KZ-502) — non-fatal
        if self._kaizen.config:
            self._apply_kaizen_hints(gen_context)

        # Proven exemplar injection (REQ-PEP-100) — non-fatal
        self._inject_exemplar(feature, gen_context)

        # Dependency import threading — surface dep tasks' modules in spec prompt
        dep_imports = self._collect_dependency_imports(feature)
        if dep_imports:
            gen_context["dependency_imports"] = dep_imports

    def _collect_dependency_imports(
        self, feature: FeatureSpec,
    ) -> Dict[str, Dict[str, Any]]:
        """Extract importable module names from dependency tasks.

        For each dependency in ``feature.dependencies``, inspects the dep's
        description for ``Imports: `mod1`, `mod2``` lines and falls back to
        extracting base-class module prefixes from the forward manifest's
        ``file_specs[].elements[].bases``.

        Returns a dict keyed by dep task ID::

            {"PI-003": {"modules": ["demo_pb2", "demo_pb2_grpc"],
                        "target_files": ["src/emailservice/email_server.py"]}}
        """
        if not feature.dependencies:
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        import re
        _import_re = re.compile(r"-\s*Imports:\s*(.+)", re.IGNORECASE)

        for dep_id in feature.dependencies:
            dep = self.queue.get_feature(dep_id) if self.queue else None
            if dep is None:
                continue

            modules: set[str] = set()

            # Strategy 1: Parse "- Imports: `mod1`, `mod2`" from description
            if dep.description:
                m = _import_re.search(dep.description)
                if m:
                    raw = m.group(1)
                    # Extract backtick-quoted or bare comma-separated names
                    modules.update(
                        tok.strip().strip("`")
                        for tok in raw.split(",")
                        if tok.strip().strip("`")
                    )

            # Strategy 2: Forward manifest base-class module prefixes
            if self._forward_manifest and dep.target_files:
                for tf in dep.target_files:
                    fspec = self._forward_manifest.file_specs.get(tf)
                    if not fspec:
                        continue
                    for elem in fspec.elements:
                        for base in elem.bases:
                            if "." in base:
                                modules.add(base.split(".")[0])
                    # Also include explicit import modules from the manifest
                    for imp in fspec.imports:
                        if imp.module:
                            modules.add(imp.module)

            # Strategy 3: Service communication graph (REQ-SIG-201)
            comm_graph = (
                self._seed_context.service_communication_graph
                if self._seed_context else None
            )
            if comm_graph and dep.target_files:
                graph_services = comm_graph.get("services", {})
                for tf in dep.target_files:
                    # Match target file path components against graph service keys
                    parts = Path(tf).parts
                    for part in parts:
                        part_lower = part.lower()
                        if part_lower in graph_services:
                            svc = graph_services[part_lower]
                            modules.update(svc.get("imports", []))
                            break
                        # Try case-insensitive match against all keys
                        for svc_key in graph_services:
                            if svc_key.lower() == part_lower:
                                modules.update(graph_services[svc_key].get("imports", []))
                                break

            if modules:
                result[dep_id] = {
                    "modules": sorted(modules),
                    "target_files": dep.target_files or [],
                }
                logger.info(
                    "Dependency imports for '%s' from %s: %s",
                    feature.id, dep_id, sorted(modules),
                )

        return result

    def _route_complexity(
        self, feature: FeatureSpec, gen_context: Dict[str, Any],
    ) -> "CodeGenerator":
        """Phase 5: Select tier-specific generator via complexity routing."""
        generator = self.code_generator
        if not (self._complexity_routing_enabled and self._complexity_router is not None):
            return generator

        # Non-Python languages bypass MicroPrime — force COMPLEX tier to
        # route to LeadContractor (cloud) which has language-aware prompts.
        # MicroPrime's engine, prompts, and quality gates are Python-specific.
        #
        # Two checks: (1) resolved language profile is non-Python, OR
        # (2) ALL target files are non-Python (catches Dockerfiles, HTML,
        # go.mod, etc. that resolve as "python" because they have no
        # recognized language extension).
        from startd8.micro_prime.engine import _is_non_python_file

        _all_targets_non_python = (
            feature.target_files
            and all(_is_non_python_file(f) for f in feature.target_files)
        )
        if (
            self._micro_prime_enabled
            and (
                (self._language_profile is not None
                 and self._language_profile.language_id != "python")
                or _all_targets_non_python
            )
        ):
            from startd8.complexity.models import ComplexityTier
            tier = ComplexityTier.COMPLEX
            _lang_id = (
                self._language_profile.language_id
                if self._language_profile is not None
                else "unknown"
            )
            reason = (
                f"non-Python targets ({_lang_id}) "
                f"— MicroPrime bypass, routing to cloud"
            )
            generator = self._complexity_router.select(tier) or generator
            tier_agent_spec = self._complexity_router.select_agent_spec(tier)
            if tier_agent_spec:
                gen_context["_tier_agent_spec"] = tier_agent_spec
            if feature.metadata is None:
                feature.metadata = {}
            feature.metadata["_complexity_tier"] = tier.value
            feature.metadata["_complexity_reason"] = reason
            logger.info(
                "Complexity routing for '%s': tier=%s, reason=%s",
                feature.name, tier.value, reason,
            )
            return generator

        try:
            from startd8.complexity import (
                classify_tier,
                extract_signals_from_feature,
            )

            signals = extract_signals_from_feature(
                feature, self.project_root,
                manifest=gen_context.get("manifest"),
            )
            tier, reason = classify_tier(signals, self._complexity_config)
            generator = self._complexity_router.select(tier) or generator
            # D3: Route tier-specific agent spec for cloud escalation
            tier_agent_spec = self._complexity_router.select_agent_spec(tier)
            if tier_agent_spec:
                gen_context["_tier_agent_spec"] = tier_agent_spec
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
        return generator

    def _check_quality_gate(self, feature: FeatureSpec, result: GenerationResult) -> bool:
        """Phase 8: CR-C1 quality gate — reject low-score generation output.

        Returns True if quality is acceptable (or unscored), False if rejected.
        """
        if not (result.success and result.quality_score is not None):
            return True
        if result.quality_score >= _MIN_QUALITY_SCORE:
            return True

        logger.warning(
            "Quality gate FAILED for '%s': score=%d < threshold=%d — "
            "marking for regeneration",
            feature.name,
            result.quality_score,
            _MIN_QUALITY_SCORE,
            extra={
                "feature_name": feature.name,
                "quality_score": result.quality_score,
                "quality_threshold": _MIN_QUALITY_SCORE,
                "model": result.model,
            },
        )
        feature.generated_files = [str(f) for f in result.generated_files]
        quality_feedback = result.metadata.get("review_feedback", "")
        error_msg = (
            f"Quality score {result.quality_score}/100 below threshold "
            f"{_MIN_QUALITY_SCORE}."
        )
        if quality_feedback:
            error_msg += f" Review feedback: {quality_feedback[:500]}"
        self._clean_failed_feature(feature)
        self.queue.fail_feature(feature.id, error_msg)
        self.total_cost_usd += result.cost_usd
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        return False

    # ------------------------------------------------------------------
    # AC-R3: Content-addressable generation cache
    # ------------------------------------------------------------------

    def _make_generation_cache_key(
        self, feature: FeatureSpec, gen_context: Dict[str, Any],
    ) -> Optional[str]:
        """Compute content-addressable cache key for a feature."""
        try:
            from .generation_cache import make_cache_key
            import hashlib as _hashlib
            import json as _json

            # Context hash: hash of sorted JSON-serializable context keys
            ctx_payload = _json.dumps(
                {k: str(v) for k, v in sorted(gen_context.items())},
                sort_keys=True,
            )
            context_hash = _hashlib.sha256(ctx_payload.encode()).hexdigest()
            model = getattr(self.code_generator, "lead_agent", "") or ""
            return make_cache_key(
                feature.description, context_hash, model,
                target_files=feature.target_files or None,
            )
        except Exception as exc:
            logger.debug("Cache key computation failed: %s", exc)
            return None

    def _try_generation_cache(
        self, feature: FeatureSpec, gen_context: Dict[str, Any],
    ) -> Optional[GenerationResult]:
        """Phase 4b: Check content-addressable generation cache (AC-R3).

        Returns a GenerationResult on cache hit, None on miss.
        """
        if self.force_regenerate:
            return None
        key = self._make_generation_cache_key(feature, gen_context)
        if key is None:
            return None
        cached = self._generation_cache.get(key)
        if cached is None:
            return None
        # Reconstruct GenerationResult from cached dict
        try:
            generated_files = [Path(p) for p in cached.get("generated_files", [])]
            # Verify files still exist on disk
            if not all(f.exists() for f in generated_files):
                logger.info(
                    "Generation cache hit but files missing on disk for '%s'",
                    feature.name,
                )
                self._generation_cache.invalidate(key)
                return None
            return GenerationResult(
                success=True,
                generated_files=generated_files,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                iterations=0,
                model=cached.get("model", ""),
                metadata={
                    **cached.get("metadata", {}),
                    "cache_hit": True,
                    "cache_key": key[:12],
                },
            )
        except Exception as exc:
            logger.debug("Cache result reconstruction failed: %s", exc)
            return None

    def _cache_generation_result(
        self, feature: FeatureSpec, result: GenerationResult,
        gen_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a successful generation result in the content-addressable cache."""
        if gen_context is None:
            return
        key = self._make_generation_cache_key(feature, gen_context)
        if key is None:
            return
        self._generation_cache.put(key, {
            "success": True,
            "generated_files": [str(f) for f in result.generated_files],
            "model": result.model,
            "metadata": {
                k: v for k, v in (result.metadata or {}).items()
                if isinstance(v, (str, int, float, bool, list, dict, type(None)))
            },
            "cost_usd": result.cost_usd,
            "iterations": result.iterations,
        })

    def _accept_generation_result(
        self, feature: FeatureSpec, result: GenerationResult,
    ) -> None:
        """Phase 9: Persist a successful generation result.

        Note: token/cost accumulation now happens unconditionally in
        develop_feature() (before the success check) so that failed
        features still contribute to postmortem cost reporting.  This
        method only sets feature status and metadata.
        """
        feature.generated_files = [str(f) for f in result.generated_files]
        feature.status = FeatureStatus.GENERATED
        self._save_queue_state_with_mode()
        feature._cost_usd = result.cost_usd  # stash for history
        if result.metadata:
            if feature.metadata is None:
                feature.metadata = {}
            feature.metadata["_generation_result_metadata"] = result.metadata
        self.instrumentor.emit_metric('prime_contractor.feature_cost', result.cost_usd, {'feature_name': feature.name, 'model': result.model})
        logger.info("Code generated for '%s': cost=$%.4f, tokens=%d in / %d out, quality=%s", feature.name, result.cost_usd, result.input_tokens, result.output_tokens, result.quality_score or "unscored", extra={'feature_name': feature.name, 'cost_usd': result.cost_usd, 'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens, 'model': result.model, 'quality_score': result.quality_score})

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

    def _review_feature(
        self,
        feature: FeatureSpec,
        integration_metadata: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Run LLM review on a completed feature (REQ-RFL-125).

        Graceful degradation: returns None on any failure so review
        never blocks feature completion.
        """
        try:
            if self._review_adapter is None:
                from startd8.contractors.prime_review import PrimeReviewAdapter
                self._review_adapter = PrimeReviewAdapter(
                    review_agent=self._review_agent,
                    lead_agent=getattr(
                        self.code_generator, "lead_agent", None,
                    ),
                )
            return self._review_adapter.review_feature(
                feature, self.project_root, integration_metadata,
            )
        except Exception:
            logger.warning(
                "Review failed for %s — continuing without review",
                feature.name,
                exc_info=True,
                extra={"feature_name": feature.name},
            )
            return None

    @staticmethod
    def _build_corrective_hint(
        review: Dict[str, Any],
        score: Optional[float] = None,
        threshold: float = 0.5,
    ) -> str:
        """Build corrective hint from review issues (REQ-RFL-225).

        Extracts BLOCKING and MAJOR issues from the review and formats
        them as a P0 corrective hint for re-draft.  Capped at 800 chars.
        """
        issues = review.get("issues", [])
        if not issues:
            return ""

        lines = ["CRITICAL: Previous generation was reviewed and rejected."]
        lines.append("Fix these specific issues:")
        for issue_text in issues[:8]:  # Cap number of issues
            lines.append(f"- {issue_text}")
        if score is not None:
            lines.append(
                f"Your score was {score}. Target: {threshold}.",
            )
        hint = "\n".join(lines)
        if len(hint) > 800:
            hint = hint[:797] + "..."
        return hint

    def _attempt_quality_gate_redraft(
        self,
        feature: FeatureSpec,
        review: Dict[str, Any],
        integration_metadata: Dict[str, Any],
    ) -> bool:
        """Quality gate: re-draft if FAIL + low score (REQ-RFL-220).

        Returns True if re-draft was attempted and produced a better
        result, False otherwise.

        WARNING: ``develop_feature()`` overwrites generated files on disk.
        If re-draft integration fails or scores worse, the original disk
        files are already replaced.  The score comparison (Mottainai) uses
        metadata scores, not disk content.  A future iteration could
        snapshot original files before re-draft for true rollback.
        """
        disk_score = integration_metadata.get("disk_quality_score", 1.0)

        if (
            not self.quality_gate_enabled
            or review.get("verdict") != "FAIL"
            or disk_score >= self.quality_gate_threshold
        ):
            return False

        # Max 1 re-draft per feature
        if (feature.metadata or {}).get("_redrafted"):
            return False

        logger.warning(
            "Quality gate: %s FAIL (score %.2f < %.2f) — re-drafting",
            feature.name, disk_score, self.quality_gate_threshold,
            extra={"feature_name": feature.name},
        )

        corrective = self._build_corrective_hint(
            review, score=disk_score, threshold=self.quality_gate_threshold,
        )
        if not corrective:
            return False

        if feature.metadata is None:
            feature.metadata = {}
        feature.metadata["_redrafted"] = True
        feature.metadata["corrective_hint"] = corrective
        original_score = disk_score

        # Re-draft: reset status, inject hint, regenerate
        feature.status = FeatureStatus.PENDING
        feature.error_message = corrective

        if not self.develop_feature(feature, prior_error=corrective):
            logger.info(
                "Re-draft failed for %s — keeping original",
                feature.name,
                extra={"feature_name": feature.name},
            )
            return False

        # Re-integrate
        redraft_result = self._engine.integrate(
            FeatureSpecUnit(feature),
            attempt=feature.integration_attempts + 1,
            listener=self._prime_listener,
        )
        if not redraft_result.success:
            logger.info(
                "Re-draft integration failed for %s — keeping original",
                feature.name,
                extra={"feature_name": feature.name},
            )
            return False

        # Accept better version (Mottainai — REQ-RFL-230)
        new_score = redraft_result.metadata.get("disk_quality_score", 0)
        if new_score <= original_score:
            logger.info(
                "Re-draft scored %.2f <= original %.2f — keeping original",
                new_score, original_score,
                extra={"feature_name": feature.name},
            )
            # REQ-RFL-500: Quality gate OTel — original kept
            try:
                _span = _trace.get_current_span()
                if _span and _span.is_recording():
                    _span.set_attribute("quality_gate.triggered", True)
                    _span.set_attribute("quality_gate.pre_score", original_score)
                    _span.set_attribute("quality_gate.post_score", new_score)
                    _span.set_attribute(
                        "quality_gate.accepted_version", "original",
                    )
            except Exception:
                logger.debug("OTel quality gate attrs failed", exc_info=True)
            return False

        logger.info(
            "Re-draft improved %s: %.2f → %.2f",
            feature.name, original_score, new_score,
            extra={"feature_name": feature.name},
        )

        # REQ-RFL-500: Quality gate OTel attributes
        try:
            _span = _trace.get_current_span()
            if _span and _span.is_recording():
                _span.set_attribute("quality_gate.triggered", True)
                _span.set_attribute("quality_gate.pre_score", original_score)
                _span.set_attribute("quality_gate.post_score", new_score)
                _span.set_attribute("quality_gate.accepted_version", "redraft")
        except Exception:
            logger.debug("OTel quality gate attrs failed", exc_info=True)

        return True

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
                    _dv_issues = []
                    for iss in domain_result.issues:
                        logger.warning(
                            'Feature %s: post-gen %s: %s (line %s)',
                            feature.name, iss.validator, iss.message, iss.line,
                            extra={'feature_name': feature.name},
                        )
                        _dv_issues.append(str(iss.message)[:200])
                    # REQ-MSR-340: Persist domain validation issues
                    feature.metadata["domain_validation"] = {
                        "passed": False,
                        "issues": _dv_issues[:10],
                        "domain": (
                            self._current_enrichment.get("domain", "general")
                            if self._current_enrichment else "general"
                        ),
                    }
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
            history_entry: Dict[str, Any] = {
                'feature_name': feature.name,
                'feature_id': feature.id,
                'success': True,
                'cost_usd': getattr(feature, '_cost_usd', 0.0),
                'files': [str(f) for f in result.integrated_files],
                'generation_metadata': (feature.metadata or {}).get('_generation_result_metadata', {}),
                'timestamp': datetime.now().isoformat(),
            }
            # Thread semantic repair data for postmortem dual scoring (DC-3)
            sem_repair = result.metadata.get("semantic_repair")
            if sem_repair and sem_repair.get("issues_found", 0) > 0:
                history_entry["semantic_repair"] = sem_repair
            # Thread Anzen gate findings for postmortem → Kaizen feedback loop
            anzen_data = result.metadata.get("anzen_gate")
            if anzen_data:
                history_entry["anzen_gate"] = anzen_data
            self.integration_history.append(history_entry)

            # REQ-RFL-125: Per-feature review
            if self.review_enabled and not self.walkthrough:
                review = self._review_feature(feature, result.metadata)
                if review:
                    # Classify issues for accumulator (REQ-RFL-210)
                    if review.get("issues"):
                        try:
                            from startd8.contractors.prime_review import (
                                classify_review_issues,
                            )
                            review["classified_issues"] = (
                                classify_review_issues(review["issues"])
                            )
                        except Exception:
                            pass

                    if feature.metadata is None:
                        feature.metadata = {}
                    feature.metadata["review"] = review
                    self.review_results[feature.id] = review
                    logger.info(
                        "Review for %s: score=%s verdict=%s",
                        feature.name,
                        review.get("score"),
                        review.get("verdict"),
                        extra={"feature_name": feature.name},
                    )

                    # REQ-RFL-220: Quality gate — re-draft on FAIL + low score
                    self._attempt_quality_gate_redraft(
                        feature, review, result.metadata,
                    )

            # REQ-RFL-240: Feed signals to accumulator for next feature
            if self._quality_accumulator is not None:
                self._quality_accumulator.record(
                    feature.id,
                    result.metadata,
                    review_result=(
                        self.review_results.get(feature.id)
                        if self.review_enabled
                        else None
                    ),
                )

            # REQ-RFL-500: OTel attributes for feedback loop observability
            try:
                _span = _trace.get_current_span()
                if _span and _span.is_recording():
                    # Integration attributes
                    _dqs = result.metadata.get("disk_quality_score")
                    if _dqs is not None:
                        _span.set_attribute(
                            "integration.disk_quality_score", _dqs,
                        )
                    _compliance = result.metadata.get("disk_compliance", {})
                    _sem_count = sum(
                        len(v.get("semantic_issues", []))
                        for v in _compliance.values()
                    )
                    _span.set_attribute(
                        "integration.semantic_issue_count", _sem_count,
                    )
                    _repair_steps = sum(
                        len(s.get("steps_applied", []))
                        for s in result.metadata.get(
                            "repair_summaries", [],
                        )
                    )
                    _span.set_attribute(
                        "integration.repair_steps_applied", _repair_steps,
                    )
                    # Review attributes
                    _rev = self.review_results.get(feature.id)
                    if _rev:
                        _span.set_attribute(
                            "review.score",
                            _rev.get("score") or 0,
                        )
                        _span.set_attribute(
                            "review.verdict",
                            _rev.get("verdict", ""),
                        )
                        _span.set_attribute(
                            "review.issue_count",
                            len(_rev.get("issues", [])),
                        )
                        _span.set_attribute(
                            "review.cost_usd",
                            _rev.get("cost") or 0.0,
                        )
            except Exception:
                logger.debug("OTel feedback loop attrs failed", exc_info=True)

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
            self._clean_failed_feature(feature)
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
        # Freeze seed context at execution boundary to prevent post-execution reconfiguration
        self.seed_context.freeze()

        # REQ-RFL-200: Within-run quality accumulator (reset per run)
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        self._quality_accumulator = RunQualityAccumulator()

        # Auto-discover kaizen suggestions from prior run (REQ-KZ-501 auto-wire)
        try:
            self._auto_discover_kaizen_config()
        except Exception:
            logger.debug("Kaizen auto-discover failed (non-fatal)", exc_info=True)

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
                self._clean_failed_feature(feature)
                self.queue.fail_feature(feature.id, f'Max integration attempts exceeded ({self.max_retries})')
                self._save_queue_state_with_mode()
                features_processed += 1
                features_failed += 1
                if stop_on_failure:
                    logger.error("STOPPING: Feature '%s' failed", feature.name, extra={'feature_name': feature.name})
                    break
                continue
            features_processed += 1
            # Reset repair circuit breaker per feature — each feature is an
            # independent unit.  Import failures in emailservice should not
            # prevent lint repair in loadgenerator.  (REQ-RPL-502 scope fix)
            reset_circuit_breaker()
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

        # REQ-TCW-203: Post-generation TODO scan + task injection
        _todo_succeeded = 0
        _todo_failed = 0
        _todo_enabled = self._enable_todo_completion and not self.dry_run
        if _todo_enabled:
            _todo_succeeded, _todo_failed = self._run_todo_scan_and_inject(
                max_cost_usd=max_cost_usd,
            )
            features_processed += _todo_succeeded + _todo_failed
            features_succeeded += _todo_succeeded
            features_failed += _todo_failed

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

        # D4 + F1: Persist element registry run metrics for Kaizen analysis
        if getattr(self, "_element_registry", None) is not None:
            try:
                run_id = os.environ.get("KAIZEN_RUN_ID") or f"run-{int(time.time())}"
                self._element_registry.write_run_metrics(run_id)
                # F1: Enrich result dict with element-level status counts
                local_count = len(self._element_registry.elements_by_status("implement", "generated"))
                escalated_count = len(self._element_registry.elements_by_status("implement", "escalated"))
                result_dict_registry = {
                    "local": local_count,
                    "escalated": escalated_count,
                    "total": len(self._element_registry.all_entries()),
                }
            except (OSError, ValueError, KeyError, TypeError):
                logger.warning("Element registry run metrics failed", exc_info=True)
                result_dict_registry = None
        else:
            result_dict_registry = None

        # Phase 4: Write generation manifest (pipeline mode only)
        result_dict = {'processed': features_processed, 'succeeded': features_succeeded, 'failed': features_failed, 'progress': self.queue.get_progress(), 'history': self.integration_history, 'total_cost_usd': self.total_cost_usd, 'total_input_tokens': self.total_input_tokens, 'total_output_tokens': self.total_output_tokens}
        if result_dict_registry is not None:
            result_dict["element_registry"] = result_dict_registry
        # REQ-TCW-303: Include TODO completion status in result
        if _todo_enabled:
            result_dict["todo_completion"] = {
                "enabled": True,
                "succeeded": _todo_succeeded,
                "failed": _todo_failed,
                "executed": (_todo_succeeded + _todo_failed) > 0,
            }
        self._write_generation_manifest(result_dict)

        # Launch async post-mortem evaluation
        try:
            from .prime_postmortem import launch_prime_postmortem_async
            launch_prime_postmortem_async(
                result_dict=result_dict,
                queue=self.queue,
                seed_path=getattr(self, '_seed_path', None),
                output_dir=str(self._manifest_path().parent),
                project_root=str(self.project_root),
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

    def _clean_failed_feature(self, feature: FeatureSpec) -> int:
        """Remove artifacts for a failed feature so the next run retries cleanly.

        Deletes generated files, invalidates the generation cache entry,
        and clears ``feature.generated_files`` so that Mottainai reuse does
        not attempt to reuse broken artifacts.

        Returns:
            Count of items removed.
        """
        removed = 0
        resolved_output_dir = self._resolve_output_dir()

        # 1. Delete generated files from disk
        for fpath_str in list(feature.generated_files or []):
            fpath = Path(fpath_str)
            if not fpath.is_absolute():
                fpath = resolved_output_dir.parent / fpath
            if fpath.exists():
                try:
                    fpath.unlink()
                    logger.debug(
                        "Cleaned failed artifact: %s (feature=%s)",
                        fpath.name, feature.id,
                    )
                    removed += 1
                except OSError as exc:
                    logger.warning(
                        "Could not remove %s: %s", fpath, exc,
                    )

        # 2. Remove per-feature staging directory if it exists
        feature_staging_dir = resolved_output_dir / feature.id
        if feature_staging_dir.exists() and feature_staging_dir.is_dir():
            shutil.rmtree(feature_staging_dir, ignore_errors=True)
            logger.debug(
                "Removed staging dir: %s (feature=%s)",
                feature_staging_dir.name, feature.id,
            )
            removed += 1

        # 3. Invalidate generation cache entry
        if hasattr(self, "_generation_cache") and self._generation_cache is not None:
            try:
                gen_context = self._build_generation_context(feature)
                key = self._make_generation_cache_key(feature, gen_context)
                if key and self._generation_cache.invalidate(key):
                    logger.debug(
                        "Invalidated cache for feature '%s'", feature.id,
                    )
                    removed += 1
            except Exception:
                logger.debug(
                    "Cache invalidation skipped for '%s'", feature.id,
                    exc_info=True,
                )

        # 4. Clear the file list so Mottainai doesn't try to reuse them
        feature.generated_files = []

        if removed:
            logger.info(
                "Cleaned %d artifact(s) for failed feature '%s'",
                removed, feature.name,
            )
        return removed

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
        # R-PY-008: Language-aware cleanup patterns
        cleanup_patterns = ['__pycache__']
        if self._language_profile is not None:
            cleanup_patterns = [
                p.rstrip('/') for p in self._language_profile.cleanup_patterns
                if not p.startswith('*')  # rglob only for directory patterns
            ]
        for pattern in cleanup_patterns:
            for cleanup_dir in self.project_root.rglob(pattern):
                if cleanup_dir.is_dir():
                    shutil.rmtree(cleanup_dir)
                    logger.debug('Removed: %s', cleanup_dir.relative_to(self.project_root))
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


# [R1: FeatureProcessor class deleted — vestigial LLM-generated code, never imported/exported]

