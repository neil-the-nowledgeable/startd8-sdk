"""
Prime Contractor Workflow - Continuous Integration Wrapper for Code Generation.

The Prime Contractor ensures that code is integrated immediately after each
feature is developed, preventing the "backlog integration nightmare" where
multiple features developed in isolation create merge conflicts and regressions.

Key Principles:
1. INTEGRATE IMMEDIATELY: Each feature is integrated right after generation
2. CHECKPOINT VALIDATION: Code must pass all checks before next feature starts
3. FAIL FAST: Stop the pipeline if integration fails, don't accumulate problems
4. MAINLINE ALWAYS WORKS: The main codebase is always in a working state

This is the "general contractor" pattern - just as a general contractor
coordinates subcontractors and ensures each phase is complete before the
next begins, the Prime Contractor coordinates code generation tasks and
ensures each feature is integrated before moving on.

This module works standalone without ContextCore. When ContextCore is
available, it provides enhanced observability via OpenTelemetry spans.
"""

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .checkpoint import CheckpointResult, CheckpointStatus, IntegrationCheckpoint
from .protocols import (
    CheckpointFailedCallback,
    CodeGenerator,
    FeatureCompleteCallback,
    GenerationResult,
    Instrumentor,
    MergeStrategy,
    ProgressCallback,
    SizeEstimator,
)
from .queue import FeatureQueue, FeatureSpec, FeatureStatus
from .registry import get_registry

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        project_root: Optional[Path] = None,
        dry_run: bool = False,
        auto_commit: bool = False,
        strict_checkpoints: bool = False,
        max_retries: int = 2,
        allow_dirty: bool = False,
        auto_stash: bool = False,
        # Protocol adapters (optional - defaults to standalone)
        code_generator: Optional[CodeGenerator] = None,
        instrumentor: Optional[Instrumentor] = None,
        size_estimator: Optional[SizeEstimator] = None,
        merge_strategy: Optional[MergeStrategy] = None,
        # Callbacks
        on_feature_complete: Optional[FeatureCompleteCallback] = None,
        on_checkpoint_failed: Optional[CheckpointFailedCallback] = None,
        # Size limits for proactive truncation prevention
        max_lines_per_feature: int = 150,
        max_tokens_per_feature: int = 500,
        # Pre-integration truncation check
        check_truncation: bool = True,
    ):
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

        # Git safety: track stash reference for recovery
        self.stash_ref: Optional[str] = None

        # Initialize queue
        self.queue = FeatureQueue(project_root=self.project_root)

        # Initialize checkpoint runner
        self.checkpoint = IntegrationCheckpoint(
            project_root=self.project_root,
            run_tests=True,
            strict_mode=strict_checkpoints,
        )

        # Initialize adapters (use defaults if not provided)
        registry = get_registry()
        registry.discover()

        self.code_generator = code_generator
        self.instrumentor = instrumentor or registry.get_default_instrumentor()()
        self.size_estimator = size_estimator or registry.get_default_size_estimator()()
        self.merge_strategy = merge_strategy or registry.get_default_merge_strategy(
            for_python=True
        )()

        # Track integration history for conflict detection
        self.integration_history: List[Dict] = []
        self.files_modified_this_session: Dict[str, List[str]] = {}  # file -> [features]

        # Size limits for proactive truncation prevention
        self.max_lines_per_feature = max_lines_per_feature
        self.max_tokens_per_feature = max_tokens_per_feature

        # Cost tracking
        self.total_cost_usd: float = 0.0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def _rel_display(self, path: Path) -> str:
        """Safe relative path for display, falling back to the full path."""
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

    # =========================================================================
    # Git Safety Methods
    # =========================================================================

    def check_git_status(self) -> Tuple[bool, List[str]]:
        """
        Check if git repo is clean (no uncommitted changes).

        Returns:
            Tuple of (is_clean, dirty_files)
        """
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )
        dirty_files = [
            line.strip() for line in result.stdout.strip().split("\n") if line
        ]
        return len(dirty_files) == 0, dirty_files

    def create_safety_snapshot(self) -> Optional[str]:
        """
        Create a safety snapshot (git stash) before integration.

        Returns:
            Stash reference name if created, None if nothing to stash
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stash_message = f"prime-contractor-snapshot-{timestamp}"

        result = subprocess.run(
            ["git", "stash", "push", "-m", stash_message],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )

        if "No local changes to save" in result.stdout:
            return None

        if result.returncode == 0:
            self.stash_ref = stash_message
            return stash_message

        return None

    def is_file_dirty(self, path: Path) -> bool:
        """Check if a specific file has uncommitted changes."""
        result_staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only", str(path)],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )
        result_unstaged = subprocess.run(
            ["git", "diff", "--name-only", str(path)],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )
        return bool(result_staged.stdout.strip() or result_unstaged.stdout.strip())

    def protect_dirty_target(self, path: Path) -> bool:
        """
        Check if it's safe to overwrite a target file.

        Returns:
            True if safe to overwrite, False if file has uncommitted changes
        """
        if not path.exists():
            return True

        if self.is_file_dirty(path):
            logger.warning(
                "Target file has uncommitted changes: %s — commit or stash first",
                path.name,
                extra={"file_path": str(path)},
            )
            return False

        return True

    def get_recovery_status(self) -> Dict:
        """Get current recovery status information."""
        backup_files = list(self.project_root.glob("**/*.backup"))

        result = subprocess.run(
            ["git", "stash", "list"],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )
        stashes = [
            line
            for line in result.stdout.strip().split("\n")
            if line and "prime-contractor-snapshot" in line
        ]

        return {
            "stash_ref": self.stash_ref,
            "stashes": stashes,
            "backup_files": [str(f) for f in backup_files],
            "has_recovery_options": bool(stashes or backup_files),
        }

    def recover_from_stash(self) -> bool:
        """Recover from the most recent prime-contractor stash."""
        result = subprocess.run(
            ["git", "stash", "list"],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )

        for line in result.stdout.strip().split("\n"):
            if "prime-contractor-snapshot" in line:
                stash_id = line.split(":")[0]
                logger.info("Recovering from stash: %s", line)

                pop_result = subprocess.run(
                    ["git", "stash", "pop", stash_id],
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                )

                if pop_result.returncode == 0:
                    logger.info("Stash recovery successful")
                    return True
                else:
                    logger.error("Stash recovery failed: %s", pop_result.stderr)
                    return False

        logger.warning("No prime-contractor stash found")
        return False

    def recover_file_from_backup(self, file_path: Path) -> bool:
        """Recover a specific file from its .backup copy."""
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")

        if not backup_path.exists():
            logger.warning("No backup found: %s", backup_path)
            return False

        shutil.copy2(backup_path, file_path)
        logger.info("Restored %s from %s", file_path, backup_path.name)
        return True

    # =========================================================================
    # Pre-flight Validation
    # =========================================================================

    def pre_flight_validation(
        self, feature: FeatureSpec
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Perform pre-flight size estimation BEFORE code generation.

        Args:
            feature: Feature specification to validate

        Returns:
            Tuple of (should_proceed, decomposition_info)
        """
        ctx = self.instrumentor.emit_span(
            "code_generation.preflight",
            {
                "gen_ai.code.feature_name": feature.name,
                "gen_ai.code.max_lines_allowed": self.max_lines_per_feature,
            },
        )

        # Estimate output size
        estimate = self.size_estimator.estimate(
            task=feature.description,
            inputs={
                "target_files": feature.target_files,
                "required_exports": [],
            },
        )

        self.instrumentor.emit_event(
            "preflight_estimate",
            {
                "estimated_lines": estimate.lines,
                "estimated_tokens": estimate.tokens,
                "complexity": estimate.complexity,
                "confidence": estimate.confidence,
            },
        )

        logger.info(
            "Pre-flight size estimation: lines=%d, complexity=%s, confidence=%.0f%%",
            estimate.lines,
            estimate.complexity,
            estimate.confidence * 100,
            extra={
                "feature_name": feature.name,
                "estimated_lines": estimate.lines,
                "complexity": estimate.complexity,
                "confidence": estimate.confidence,
            },
        )

        if estimate.lines > self.max_lines_per_feature:
            self.instrumentor.emit_event(
                "preflight_decision",
                {
                    "decision": "DECOMPOSE_REQUIRED",
                    "reason": f"Estimated {estimate.lines} lines exceeds safe limit of {self.max_lines_per_feature}",
                },
            )

            logger.warning(
                "Estimated output (%d lines) exceeds safe limit (%d) for feature '%s' — consider splitting",
                estimate.lines,
                self.max_lines_per_feature,
                feature.name,
                extra={"feature_name": feature.name, "estimated_lines": estimate.lines},
            )

            decomposition_info = {
                "reason": f"Estimated {estimate.lines} lines exceeds limit of {self.max_lines_per_feature}",
                "estimated_lines": estimate.lines,
                "suggested_action": "Split into multiple smaller features",
            }

            if self.strict_checkpoints:
                return False, decomposition_info

        return True, None

    # =========================================================================
    # Feature Processing
    # =========================================================================

    def process_feature(self, feature: FeatureSpec) -> bool:
        """
        Process a feature through the full lifecycle.

        Returns:
            True if the feature was fully processed, False otherwise
        """
        self.instrumentor.emit_insight(
            insight_type="feature_selected",
            summary=f"Processing feature: {feature.name}",
            confidence=1.0,
            feature_id=feature.id,
            feature_name=feature.name,
            current_status=(
                feature.status.value
                if hasattr(feature.status, "value")
                else str(feature.status)
            ),
        )

        # Auto-decompose multi-file features into sequential single-file tasks
        if len(feature.target_files) > 1 and feature.status == FeatureStatus.PENDING:
            return self._process_decomposed_feature(feature)

        # Step 1: Develop if needed
        if feature.status == FeatureStatus.PENDING:
            if not self.develop_feature(feature):
                return False

        # Step 2: Integrate
        if feature.status == FeatureStatus.GENERATED:
            return self.integrate_feature(feature)

        logger.warning(
            "Feature '%s' in unexpected state: %s",
            feature.name,
            feature.status,
            extra={"feature_name": feature.name, "status": str(feature.status)},
        )
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
        logger.info(
            "Auto-decomposing '%s' into %d sub-features",
            feature.name,
            n,
            extra={"feature_name": feature.name, "sub_feature_count": n},
        )

        # Save and temporarily clear the callback so it only fires on the
        # last sub-feature (intermediate states may not build/pass tests).
        saved_callback = self.on_feature_complete

        for i, target_file in enumerate(feature.target_files):
            is_last = i == n - 1
            sub_id = f"{feature.id}__part{i + 1}"
            sub_name = f"{feature.name} ({Path(target_file).name})"

            # Read current file content (includes prior sub-feature changes)
            current_content = ""
            target_path = self.project_root / target_file
            if target_path.exists():
                current_content = target_path.read_text(encoding="utf-8")

            # Build sub-feature description with file-scoping directive
            sub_description = (
                f"{feature.description}\n\n"
                f"---\n"
                f"IMPORTANT: This is part {i + 1} of {n}. "
                f"You MUST ONLY output code for the file: {target_file}\n"
                f"Do NOT output code for any other file.\n\n"
                f"CURRENT CONTENTS of {target_file}:\n"
                f"```\n{current_content}\n```"
            )

            sub_feature = FeatureSpec(
                id=sub_id,
                name=sub_name,
                description=sub_description,
                target_files=[target_file],
                dependencies=feature.dependencies,
            )

            logger.info(
                "Sub-feature %d/%d: %s",
                i + 1,
                n,
                Path(target_file).name,
                extra={"feature_name": feature.name, "sub_index": i + 1, "target_file": target_file},
            )

            # Only fire on_feature_complete for the last sub-feature
            self.on_feature_complete = saved_callback if is_last else None

            # Develop (generate code)
            if not self.develop_feature(sub_feature):
                self.on_feature_complete = saved_callback
                self.queue.fail_feature(feature.id, f"Sub-feature {sub_id} generation failed")
                return False

            # Integrate (copy to target)
            if not self.integrate_feature(sub_feature):
                self.on_feature_complete = saved_callback
                self.queue.fail_feature(feature.id, f"Sub-feature {sub_id} integration failed")
                return False

        # Restore callback and mark parent as complete
        self.on_feature_complete = saved_callback
        self.queue.complete_feature(feature.id)
        logger.info(
            "All %d sub-features integrated for '%s'",
            n,
            feature.name,
            extra={"feature_name": feature.name, "sub_feature_count": n},
        )
        return True

    def develop_feature(self, feature: FeatureSpec) -> bool:
        """
        Develop a feature using the configured CodeGenerator.

        Returns:
            True if code generation succeeded, False otherwise
        """
        logger.info(
            "DEVELOPING FEATURE: %s",
            feature.name,
            extra={"feature_name": feature.name, "feature_id": feature.id},
        )

        # Pre-flight validation
        should_proceed, decomposition_info = self.pre_flight_validation(feature)

        if not should_proceed:
            reason = decomposition_info.get("reason", "Size exceeds safe limits")
            logger.error(
                "Pre-flight failed for '%s': %s",
                feature.name,
                reason,
                extra={"feature_name": feature.name, "reason": reason},
            )
            self.queue.fail_feature(
                feature.id, f"Pre-flight failed: {decomposition_info.get('reason')}"
            )
            return False

        # Mark as developing
        self.queue.start_feature(feature.id)

        if self.dry_run:
            logger.info(
                "[DRY RUN] Would generate code for '%s': %s...",
                feature.name,
                feature.description[:100],
                extra={"feature_name": feature.name, "dry_run": True},
            )
            simulated_files = (
                [f"generated/{feature.id}/{Path(t).name}" for t in feature.target_files]
                if feature.target_files
                else [f"generated/{feature.id}/code.py"]
            )
            feature.generated_files = simulated_files
            feature.status = FeatureStatus.GENERATED
            self.queue.save_state()
            return True

        if not self.code_generator:
            logger.error("No code generator configured for feature '%s'", feature.name)
            self.queue.fail_feature(feature.id, "No code generator configured")
            return False

        logger.info("Running code generation for '%s'...", feature.name)

        try:
            result: GenerationResult = self.code_generator.generate(
                task=feature.description,
                context={"feature_name": feature.name},
                target_files=feature.target_files,
            )

            if result.success:
                feature.generated_files = [str(f) for f in result.generated_files]
                feature.status = FeatureStatus.GENERATED
                self.queue.save_state()

                # Track costs
                self.total_cost_usd += result.cost_usd
                self.total_input_tokens += result.input_tokens
                self.total_output_tokens += result.output_tokens

                self.instrumentor.emit_metric(
                    "prime_contractor.feature_cost",
                    result.cost_usd,
                    {"feature_name": feature.name, "model": result.model},
                )

                print(f"\n✓ Code generated successfully!")
                print(f"  Cost: ${result.cost_usd:.4f}")
                print(f"  Tokens: {result.input_tokens} in / {result.output_tokens} out")
                return True
            else:
                error_msg = result.error or "Code generation failed"
                print(f"\n✗ Code generation failed: {error_msg}")
                self.queue.fail_feature(feature.id, error_msg)
                return False

        except Exception as e:
            error_msg = f"Exception during code generation: {e}"
            print(f"\n✗ {error_msg}")
            self.queue.fail_feature(feature.id, error_msg)
            return False

    def integrate_feature(self, feature: FeatureSpec) -> bool:
        """
        Integrate a single feature immediately.

        Returns:
            True if integration succeeded, False otherwise
        """
        print(f"\n{'='*70}")
        print(f"INTEGRATING FEATURE: {feature.name}")
        print(f"{'='*70}")

        # Mark as integrating
        self.queue.start_integration(feature.id)

        integrated_files = []

        for i, source_file in enumerate(feature.generated_files):
            source_path = Path(source_file)

            # Determine target path (resolve relative paths against project_root)
            if i < len(feature.target_files):
                target_path = Path(feature.target_files[i])
                if not target_path.is_absolute():
                    target_path = self.project_root / target_path
            else:
                if not source_path.exists():
                    if self.dry_run:
                        target_path = self.project_root / "src" / source_path.name
                    else:
                        print(f"  ✗ Source file not found: {source_path}")
                        continue
                else:
                    # Infer target from source
                    target_path = self.project_root / "src" / source_path.name

            if self.dry_run:
                target_rel = self._rel_display(target_path)
                if target_path.exists():
                    print(f"  [DRY RUN] Would update: {target_rel}")
                else:
                    print(f"  [DRY RUN] Would create: {target_rel}")
                integrated_files.append(target_path)
                continue

            # Live mode - check source exists
            if not source_path.exists():
                print(f"  ✗ Source file not found: {source_path}")
                continue

            # Pre-integration truncation check (W-010)
            # code_mode auto-detects from content — source code files get
            # structural-only checks (brace balance, unclosed code blocks);
            # prose/markdown files get the full heuristic suite.
            if self.check_truncation:
                from ..truncation_detection import detect_truncation, get_expected_sections_for_code
                source_content = source_path.read_text(encoding="utf-8")
                expected = get_expected_sections_for_code(source_content)
                trunc_result = detect_truncation(
                    source_content,
                    expected_sections=expected,
                    strict_mode=False,
                )
                if trunc_result.is_truncated and trunc_result.confidence >= 0.7:
                    print(
                        f"  ✗ REJECTED {source_path.name}: "
                        f"appears truncated (confidence={trunc_result.confidence:.0%})"
                    )
                    for indicator in trunc_result.indicators[:3]:
                        print(f"      {indicator}")
                    print("    Integration blocked to prevent corrupting target file.")
                    continue
                elif trunc_result.is_truncated:
                    print(
                        f"  ⚠ WARNING {source_path.name}: "
                        f"possible truncation (confidence={trunc_result.confidence:.0%})"
                    )
                    for indicator in trunc_result.indicators[:3]:
                        print(f"      {indicator}")
                    print("    Proceeding — review generated file if build fails.")

            # Target file protection
            if target_path.exists() and not self.allow_dirty:
                if not self.protect_dirty_target(target_path):
                    print(f"  Skipping {target_path.name} to protect uncommitted changes")
                    continue

            # Use merge strategy
            if self.merge_strategy.can_merge(source_path, target_path):
                result = self.merge_strategy.merge(source_path, target_path)
                if result.status.value == "success":
                    print(f"  ✓ Merged: {self._rel_display(target_path)}")
                    integrated_files.append(target_path)
                elif result.status.value == "conflict":
                    print(f"  ⚠ Merged with conflicts: {target_path.name}")
                    for conflict in result.conflicts[:3]:
                        print(f"      {conflict}")
                    integrated_files.append(target_path)
                else:
                    print(f"  ✗ Merge failed: {result.error}")
            else:
                # Simple copy if merge strategy can't handle
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                print(f"  ✓ Copied: {self._rel_display(target_path)}")
                integrated_files.append(target_path)

        if not integrated_files:
            error_msg = "No files were integrated"
            self.queue.fail_feature(feature.id, error_msg)
            self.instrumentor.emit_insight(
                insight_type="integration_failed",
                summary=f"Feature '{feature.name}' failed: no files integrated",
                confidence=1.0,
                feature_id=feature.id,
            )
            return False

        # Track modified files
        for file_path in integrated_files:
            file_str = str(file_path)
            if file_str not in self.files_modified_this_session:
                self.files_modified_this_session[file_str] = []
            self.files_modified_this_session[file_str].append(feature.name)

        # Run checkpoints
        if not self.dry_run:
            print("\nRunning integration checkpoints...")
            results = self.checkpoint.run_all_checkpoints(integrated_files, feature.name)
            all_passed = self.checkpoint.summarize_results(results)

            if not all_passed:
                failed_checks = [r for r in results if r.status == CheckpointStatus.FAILED]
                error_msg = "; ".join(r.message for r in failed_checks)

                self.queue.fail_feature(feature.id, error_msg)

                self.instrumentor.emit_insight(
                    insight_type="integration_failed",
                    summary=f"Feature '{feature.name}' failed checkpoints",
                    confidence=1.0,
                    feature_id=feature.id,
                    failed_checks=[r.name for r in failed_checks],
                )

                if self.on_checkpoint_failed:
                    self.on_checkpoint_failed(feature, results)

                return False
        else:
            print("\n[DRY RUN] Would run integration checkpoints")

        # Commit if auto-commit enabled
        if self.auto_commit and not self.dry_run:
            self._commit_feature(feature, integrated_files)

        # Mark complete
        self.queue.complete_feature(feature.id)

        # Record in history
        self.integration_history.append(
            {
                "feature": feature.name,
                "files": [str(f) for f in integrated_files],
                "timestamp": datetime.now().isoformat(),
            }
        )

        self.instrumentor.emit_insight(
            insight_type="integration_success",
            summary=f"Feature '{feature.name}' integrated successfully",
            confidence=1.0,
            feature_id=feature.id,
            files_count=len(integrated_files),
        )

        if self.on_feature_complete:
            self.on_feature_complete(feature)

        print(f"\n✓ Feature '{feature.name}' integrated successfully!")
        return True

    def _commit_feature(self, feature: FeatureSpec, files: List[Path]):
        """Commit the integrated feature to git."""
        for file_path in files:
            subprocess.run(
                ["git", "add", str(file_path)],
                cwd=self.project_root,
                capture_output=True,
            )

        commit_msg = (
            f"feat: Integrate {feature.name}\n\nIntegrated via Prime Contractor workflow"
        )
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"  ✓ Committed: {feature.name}")
        else:
            print(f"  ⚠ Commit failed: {result.stderr}")

    # =========================================================================
    # Main Workflow
    # =========================================================================

    def run(
        self,
        max_features: Optional[int] = None,
        stop_on_failure: bool = True,
    ) -> Dict:
        """
        Run the Prime Contractor workflow.

        Args:
            max_features: Maximum number of features to process (None = all)
            stop_on_failure: Stop processing if a feature fails

        Returns:
            Summary dict with results
        """
        print("\n" + "=" * 70)
        print("PRIME CONTRACTOR WORKFLOW")
        print("=" * 70)
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Auto-commit: {self.auto_commit}")
        print(f"Stop on failure: {stop_on_failure}")

        # Pre-flight check
        is_clean, dirty_files = self.check_git_status()
        if not is_clean:
            print(f"\n{'='*70}")
            if self.auto_stash:
                print("AUTO-STASH: Repository has uncommitted changes")
                stash_ref = self.create_safety_snapshot()
                if stash_ref:
                    print(f"  Stashed as: {stash_ref}")
            elif self.allow_dirty:
                print("WARNING: Repository has uncommitted changes (--allow-dirty set)")
            else:
                print("BLOCKED: Repository has uncommitted changes")
                print(f"  {len(dirty_files)} file(s) with uncommitted changes")
                return {
                    "processed": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "progress": self.queue.get_progress(),
                    "history": [],
                    "total_cost_usd": 0.0,
                    "aborted": True,
                    "abort_reason": "uncommitted_changes",
                }

        self.instrumentor.emit_insight(
            insight_type="workflow_started",
            summary=f"Starting workflow with {len(self.queue.features)} features",
            confidence=1.0,
            mode="dry_run" if self.dry_run else "live",
            feature_count=len(self.queue.features),
        )

        # Capture test baseline
        if not self.dry_run:
            print("\nCapturing test baseline for regression detection...")
            baseline = self.checkpoint.capture_test_baseline()
            print(f"  Baseline: {len(baseline)} test(s)")

        # Show queue status
        self.queue.print_status()

        # Process features
        features_processed = 0
        features_succeeded = 0
        features_failed = 0

        while True:
            if max_features and features_processed >= max_features:
                print(f"\nReached max features limit ({max_features})")
                break

            feature = self.queue.get_next_feature()

            if not feature:
                print("\nNo more features to process")
                break

            features_processed += 1
            success = self.process_feature(feature)

            if success:
                features_succeeded += 1
            else:
                features_failed += 1

                if stop_on_failure:
                    print(f"\n❌ STOPPING: Feature '{feature.name}' failed")
                    break

        # Final summary
        print("\n" + "=" * 70)
        print("WORKFLOW SUMMARY")
        print("=" * 70)
        print(f"  Features processed: {features_processed}")
        print(f"  Succeeded: {features_succeeded}")
        print(f"  Failed: {features_failed}")
        print(f"  Progress: {self.queue.get_progress():.1f}%")
        print(f"  Total cost: ${self.total_cost_usd:.4f}")
        print(
            f"  Total tokens: {self.total_input_tokens} in / {self.total_output_tokens} out"
        )

        self.instrumentor.emit_insight(
            insight_type="workflow_completed",
            summary=f"Workflow complete: {features_succeeded}/{features_processed} succeeded",
            confidence=1.0,
            processed=features_processed,
            succeeded=features_succeeded,
            failed=features_failed,
            total_cost_usd=self.total_cost_usd,
        )

        return {
            "processed": features_processed,
            "succeeded": features_succeeded,
            "failed": features_failed,
            "progress": self.queue.get_progress(),
            "history": self.integration_history,
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
        }

    def run_single_feature(self, feature_id: str) -> bool:
        """Run integration for a single specific feature."""
        feature = self.queue.features.get(feature_id)
        if not feature:
            print(f"Feature not found: {feature_id}")
            return False

        return self.integrate_feature(feature)

    def reset_failed_features(self):
        """Reset all failed features to appropriate status for retry."""
        reset_count = 0
        for feature in self.queue.features.values():
            if feature.status in (FeatureStatus.FAILED, FeatureStatus.BLOCKED):
                if feature.generated_files:
                    feature.status = FeatureStatus.GENERATED
                    print(f"  Reset {feature.name} -> GENERATED (has code)")
                else:
                    feature.status = FeatureStatus.PENDING
                    print(f"  Reset {feature.name} -> PENDING (needs development)")
                feature.error_message = None
                reset_count += 1

        self.queue.save_state()
        print(f"\nReset {reset_count} failed/blocked feature(s)")

    def full_reset(self, include_targets: bool = False) -> None:
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
        # Delete persisted state file
        if self.queue.state_file.exists():
            self.queue.state_file.unlink()
            print(f"  Removed state file: {self.queue.state_file.name}")

        # Reset in-memory queue
        self.queue.reset()

        # Clean workspace artifacts
        self.clean_workspace(include_targets=include_targets)

    def clean_workspace(self, include_targets: bool = False) -> int:
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

        # Determine output directory from the code generator or default
        output_dir = self.project_root / "generated"
        if self.code_generator and hasattr(self.code_generator, "output_dir"):
            output_dir = Path(self.code_generator.output_dir)
            if not output_dir.is_absolute():
                output_dir = self.project_root / output_dir

        # Remove generated/ directory
        if output_dir.exists() and output_dir.is_dir():
            shutil.rmtree(output_dir)
            print(f"  Removed directory: {output_dir}")
            removed += 1

        # Remove .backup files under project root
        for backup_file in self.project_root.rglob("*.backup"):
            backup_file.unlink()
            print(f"  Removed backup: {backup_file.relative_to(self.project_root)}")
            removed += 1

        # Remove __pycache__ directories under project root
        for pycache_dir in self.project_root.rglob("__pycache__"):
            if pycache_dir.is_dir():
                shutil.rmtree(pycache_dir)
                print(f"  Removed: {pycache_dir.relative_to(self.project_root)}")
                removed += 1

        # Optionally remove target files listed in the feature queue
        if include_targets:
            for feature in self.queue.features.values():
                for target_file in feature.target_files:
                    target_path = Path(target_file)
                    if not target_path.is_absolute():
                        target_path = self.project_root / target_path
                    if target_path.exists():
                        target_path.unlink()
                        print(f"  Removed target: {target_path.relative_to(self.project_root)}")
                        removed += 1

        print(f"\nCleaned {removed} item(s) from workspace")
        return removed
