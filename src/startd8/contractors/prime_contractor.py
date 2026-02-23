import dataclasses
import enum
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logging_config import get_logger
from .checkpoint import IntegrationCheckpoint
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
from .seed_context import SeedContext

logger = get_logger(__name__)


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

    def __init__(self, project_root: Optional[Path]=None, dry_run: bool=False, auto_commit: bool=False, strict_checkpoints: bool=False, max_retries: int=6, allow_dirty: bool=False, auto_stash: bool=False, code_generator: Optional[CodeGenerator]=None, instrumentor: Optional[Instrumentor]=None, size_estimator: Optional[SizeEstimator]=None, merge_strategy: Optional[MergeStrategy]=None, on_feature_complete: Optional[FeatureCompleteCallback]=None, on_checkpoint_failed: Optional[CheckpointFailedCallback]=None, max_lines_per_feature: int=150, max_tokens_per_feature: int=500, check_truncation: bool=True):
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
        )
        self._prime_listener = PrimeContractorListener(
            queue=self.queue,
            instrumentor=self.instrumentor,
            files_modified=self.files_modified_this_session,
        )
        self._domain_checklist = None  # lazy-init DomainChecklist
        self._current_enrichment = None  # per-feature enrichment cache
        # SeedContext — typed container for pipeline context
        self.seed_context: SeedContext = SeedContext()
        # Seed-level context — set by run_prime_workflow.py after loading
        # the context seed.  Declared here so _generate_code can access
        # them directly without getattr guards.
        self.seed_onboarding: Dict[str, Any] = {}
        self.seed_architectural_context: Dict[str, Any] = {}
        self.seed_design_calibration: Dict[str, Any] = {}
        self.seed_service_metadata: Dict[str, Any] = {}
        self.plan_document_text: Optional[str] = None
        self.force_regenerate: bool = False

    def configure_seed_context(self, **kwargs: Any) -> None:
        """Configure seed context before execution. Raises if already frozen.

        Validates that all keys correspond to actual ``SeedContext`` dataclass
        fields (excluding internal ``_``-prefixed fields). This prevents
        accidental overwrite of methods or properties like ``freeze``,
        ``as_dict``, or ``is_pipeline``.

        Args:
            **kwargs: Field assignments for the seed context.

        Raises:
            ValueError: If a key is not a valid SeedContext field name.
            AttributeError: If seed_context is already frozen.

        Example:
            >>> workflow.configure_seed_context(
            ...     mode="pipeline",
            ...     project_name="myproject",
            ...     onboarding_metadata={"key": "value"},
            ... )
        """
        valid_fields = {
            f.name
            for f in dataclasses.fields(self.seed_context)
            if not f.name.startswith("_")
        }
        for key, value in kwargs.items():
            if key not in valid_fields:
                raise ValueError(
                    f"Unknown SeedContext field: '{key}'. "
                    f"Valid fields: {sorted(valid_fields)}"
                )
            setattr(self.seed_context, key, value)
        logger.info(
            "SeedContext configured",
            extra={"seed_mode": self.seed_context.mode},
        )

    # --- Backward-compatible property accessors ---
    # Rule: one read-only @property per non-internal SeedContext field.
    # These are READ-ONLY. Mutation must go through configure_seed_context()
    # or direct seed_context attribute assignment (before freeze).

    @property
    def project_name(self) -> Optional[str]:
        """Read-only accessor delegating to seed_context.project_name."""
        return self.seed_context.project_name

    @property
    def project_description(self) -> Optional[str]:
        """Read-only accessor delegating to seed_context.project_description."""
        return self.seed_context.project_description

    @property
    def onboarding_metadata(self) -> Optional[Dict[str, Any]]:
        """Read-only accessor delegating to seed_context.onboarding_metadata."""
        return self.seed_context.onboarding_metadata

    @property
    def architectural_context(self) -> Optional[Dict[str, Any]]:
        """Read-only accessor delegating to seed_context.architectural_context."""
        return self.seed_context.architectural_context

    @property
    def design_decisions(self) -> Optional[List[Dict[str, Any]]]:
        """Read-only accessor delegating to seed_context.design_decisions."""
        return self.seed_context.design_decisions

    @property
    def calibration_params(self) -> Optional[Dict[str, Any]]:
        """Read-only accessor delegating to seed_context.calibration_params."""
        return self.seed_context.calibration_params

    @property
    def quality_targets(self) -> Optional[Dict[str, Any]]:
        """Read-only accessor delegating to seed_context.quality_targets."""
        return self.seed_context.quality_targets

    @property
    def source_pipeline(self) -> Optional[str]:
        """Read-only accessor delegating to seed_context.source_pipeline."""
        return self.seed_context.source_pipeline

    @property
    def seed_version(self) -> Optional[str]:
        """Read-only accessor delegating to seed_context.seed_version."""
        return self.seed_context.seed_version

    def _rel_display(self, path: Path) -> str:
        """Safe relative path for display, falling back to the full path."""
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

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
        if feature.status == FeatureStatus.GENERATED:
            if feature.error_message and self.code_generator:
                logger.info("Feature '%s' has prior error — regenerating with feedback: %s", feature.name, feature.error_message, extra={'feature_name': feature.name, 'prior_error': feature.error_message})
                prior_error = feature.error_message
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
            if not self.integrate_feature(sub_feature):
                self.on_feature_complete = saved_callback
                self.queue.fail_feature(feature.id, f'Sub-feature {sub_id} integration failed')
                return False
        self.on_feature_complete = saved_callback
        feature._cost_usd = parent_cost
        self.queue.complete_feature(feature.id)
        logger.info("All %d sub-features integrated for '%s'", n, feature.name, extra={'feature_name': feature.name, 'sub_feature_count': n})
        return True

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

        for fpath_str in file_paths:
            fpath = Path(fpath_str)
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
        if self.dry_run:
            logger.info("[DRY RUN] Would generate code for '%s': %s...", feature.name, feature.description[:100], extra={'feature_name': feature.name, 'dry_run': True})
            simulated_files = [f'generated/{feature.id}/{Path(t).name}' for t in feature.target_files] if feature.target_files else [f'generated/{feature.id}/code.py']
            feature.generated_files = simulated_files
            feature.status = FeatureStatus.GENERATED
            self.queue.save_state()
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

            gen_context: dict = {'feature_name': feature.name}
            self._current_enrichment = None
            if feature.target_files:
                gen_context['target_file'] = feature.target_files[0]
                # Try domain-aware constraints via DomainChecklist
                enrichment = self._get_domain_enrichment(feature)
                if enrichment is not None:
                    self._current_enrichment = enrichment
                    gen_context['domain_constraints'] = enrichment.prompt_constraints
                    logger.info("Domain constraints applied for '%s': %d constraints (domain=%s)", feature.name, len(enrichment.prompt_constraints), enrichment.domain.value, extra={'feature_name': feature.name, 'domain': enrichment.domain.value})
                else:
                    from startd8.workflows.builtin.prompts import get_template as _get_ctx_template
                    gen_context['output_constraint'] = _get_ctx_template("prime_context", "output_constraint").strip()

            # Mottainai Gaps 9-13: inject seed-level context into gen_context.
            # Keys injected: project_objectives, semantic_conventions,
            # architectural_context, implement_max_output_tokens,
            # plan_context, domain_constraints (from per-task metadata).
            if self.seed_onboarding:
                objectives = self.seed_onboarding.get('project_objectives')
                if isinstance(objectives, (str, list, dict)):
                    gen_context['project_objectives'] = objectives
                sem_conv = self.seed_onboarding.get('semantic_conventions')
                if isinstance(sem_conv, (dict, list)):
                    gen_context['semantic_conventions'] = sem_conv
            if self.seed_architectural_context:
                gen_context['architectural_context'] = self.seed_architectural_context
            # Per-task calibration: implement_max_output_tokens
            task_cal = self.seed_design_calibration.get(feature.id, {})
            if isinstance(task_cal, dict) and task_cal.get('implement_max_output_tokens'):
                gen_context['implement_max_output_tokens'] = task_cal['implement_max_output_tokens']
            # Gap 13: plan document context
            if self.plan_document_text:
                gen_context['plan_context'] = self.plan_document_text
            # IMP-P2: requirements text passthrough
            if feature.metadata.get("requirements_text"):
                gen_context["requirements_text"] = feature.metadata["requirements_text"]
            # REQ-PC-014: inject service metadata for protocol/dep validation
            if self.seed_service_metadata:
                gen_context['service_metadata'] = self.seed_service_metadata
                logger.info(
                    "Context injection: service_metadata for '%s' (transport=%s, deps=%d)",
                    feature.name,
                    self.seed_service_metadata.get('transport_protocol', 'unset'),
                    len(self.seed_service_metadata.get('runtime_dependencies', [])),
                )
            # Gap 9: per-task metadata from seed enrichment
            if feature.metadata:
                meta_enrichment = feature.metadata.get('_enrichment', {})
                if isinstance(meta_enrichment, dict) and meta_enrichment:
                    gen_context.setdefault('domain_constraints', [])
                    if isinstance(gen_context['domain_constraints'], list):
                        gen_context['domain_constraints'].extend(
                            meta_enrichment.get('prompt_constraints', [])
                        )
                    # IMP-P3: Critical parameter elevation
                    resolved_params = meta_enrichment.get('resolved_parameters', [])
                    param_sources = meta_enrichment.get('parameter_sources', [])
                    if resolved_params or param_sources:
                        cp_lines = []
                        for rp in resolved_params:
                            kv = rp.get('key_value', '')
                            if kv:
                                cp_lines.append(kv)
                        for ps in param_sources:
                            kv = ps.get('key_value', '')
                            if kv and kv not in cp_lines:
                                cp_lines.append(kv)
                        if cp_lines:
                            gen_context['critical_parameters'] = cp_lines
                            gen_context['resolved_parameters'] = resolved_params

            if prior_error:
                from startd8.workflows.builtin.prompts import format_prompt as _fmt_ctx
                gen_context['prior_error_feedback'] = _fmt_ctx(
                    "prime_context", "prior_error_feedback", prior_error=prior_error,
                ).strip()
            result: GenerationResult = self.code_generator.generate(task=feature.description, context=gen_context, target_files=feature.target_files)
            if result.success:
                feature.generated_files = [str(f) for f in result.generated_files]
                feature.status = FeatureStatus.GENERATED
                self.queue.save_state()
                self.total_cost_usd += result.cost_usd
                self.total_input_tokens += result.input_tokens
                self.total_output_tokens += result.output_tokens
                feature._cost_usd = result.cost_usd  # stash for history
                self.instrumentor.emit_metric('prime_contractor.feature_cost', result.cost_usd, {'feature_name': feature.name, 'model': result.model})
                logger.info("Code generated for '%s': cost=$%.4f, tokens=%d in / %d out", feature.name, result.cost_usd, result.input_tokens, result.output_tokens, extra={'feature_name': feature.name, 'cost_usd': result.cost_usd, 'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens, 'model': result.model})
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
            gen_paths = [
                Path(f) for f in feature.generated_files
                if Path(f).exists() and Path(f).suffix == '.py'
            ]
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
            self.queue.complete_feature(feature.id)
            self.integration_history.append({
                'feature_name': feature.name,
                'feature_id': feature.id,
                'success': True,
                'cost_usd': getattr(feature, '_cost_usd', 0.0),
                'files': [str(f) for f in result.integrated_files],
                'timestamp': datetime.now().isoformat(),
            })
            if self.on_feature_complete:
                self.on_feature_complete(feature)
            return True
        else:
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
        # Freeze seed context at execution boundary to prevent mutation
        self.seed_context.freeze()
        logger.info('PRIME CONTRACTOR WORKFLOW started — mode=%s, auto_commit=%s, stop_on_failure=%s', 'DRY RUN' if self.dry_run else 'LIVE', self.auto_commit, stop_on_failure, extra={'dry_run': self.dry_run, 'auto_commit': self.auto_commit, 'seed_mode': self.seed_context.mode})
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
            if feature.integration_attempts >= MAX_INTEGRATION_ATTEMPTS:
                logger.error("Feature '%s' exceeded max integration attempts (%d)", feature.name, MAX_INTEGRATION_ATTEMPTS)
                self.queue.fail_feature(feature.id, 'Max integration attempts exceeded')
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
                self.integration_history.append({'feature_name': feature.name, 'feature_id': feature.id, 'success': False, 'cost_usd': getattr(feature, '_cost_usd', 0.0), 'error': feature.error_message, 'timestamp': datetime.now().isoformat()})
                if stop_on_failure:
                    logger.error("STOPPING: Feature '%s' failed", feature.name, extra={'feature_name': feature.name})
                    break
        logger.info('WORKFLOW SUMMARY: processed=%d, succeeded=%d, failed=%d, progress=%.1f%%, cost=$%.4f, tokens=%d in / %d out', features_processed, features_succeeded, features_failed, self.queue.get_progress(), self.total_cost_usd, self.total_input_tokens, self.total_output_tokens, extra={'processed': features_processed, 'succeeded': features_succeeded, 'failed': features_failed, 'progress': self.queue.get_progress(), 'total_cost_usd': self.total_cost_usd, 'total_input_tokens': self.total_input_tokens, 'total_output_tokens': self.total_output_tokens})
        self.instrumentor.emit_insight(insight_type='workflow_completed', summary=f'Workflow complete: {features_succeeded}/{features_processed} succeeded', confidence=1.0, processed=features_processed, succeeded=features_succeeded, failed=features_failed, total_cost_usd=self.total_cost_usd)
        return {'processed': features_processed, 'succeeded': features_succeeded, 'failed': features_failed, 'progress': self.queue.get_progress(), 'history': self.integration_history, 'total_cost_usd': self.total_cost_usd, 'total_input_tokens': self.total_input_tokens, 'total_output_tokens': self.total_output_tokens}

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
        output_dir = self.project_root / 'generated'
        if self.code_generator and hasattr(self.code_generator, 'output_dir') and (self.code_generator.output_dir is not None):
            output_dir = Path(self.code_generator.output_dir)
            if not output_dir.is_absolute():
                output_dir = self.project_root / output_dir
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