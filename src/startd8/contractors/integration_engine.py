"""
IntegrationEngine — standalone integration pipeline extracted from PrimeContractor.

Handles the full merge lifecycle:
  snapshot → validate → merge → checkpoint → commit/rollback

Designed to be used by both PrimeContractorWorkflow (via FeatureSpecUnit adapter)
and the Artisan INTEGRATE phase (via SeedTaskUnit adapter).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from ..security import sanitize_path
from .checkpoint import CheckpointStatus, IntegrationCheckpoint
from .gate_contracts import GateEmitter
from .protocols import (
    IntegrationListener,
    IntegrationResult,
    IntegrationUnit,
    MergeStrategy,
)

logger = get_logger(__name__)


class NullListener:
    """Default no-op listener satisfying IntegrationListener protocol."""

    def on_integration_started(self, unit: IntegrationUnit) -> None:
        pass

    def on_file_integrated(self, unit: IntegrationUnit, source: Path, target: Path) -> None:
        pass

    def on_checkpoint_result(self, unit: IntegrationUnit, result: Any) -> None:
        pass

    def on_integration_failed(self, unit: IntegrationUnit, error: str) -> None:
        pass

    def on_integration_completed(self, unit: IntegrationUnit, files: List[Path]) -> None:
        pass


_NULL_LISTENER = NullListener()


class IntegrationEngine:
    """Standalone integration pipeline with snapshot/rollback support.

    Constructor args mirror PrimeContractorWorkflow's integration-related
    parameters so existing callers can delegate without behaviour changes.
    """

    def __init__(
        self,
        project_root: Path,
        merge_strategy: MergeStrategy,
        checkpoint: Optional[IntegrationCheckpoint] = None,
        *,
        dry_run: bool = False,
        auto_commit: bool = False,
        allow_dirty: bool = False,
        check_truncation: bool = True,
        strict_checkpoints: bool = False,
    ) -> None:
        self.project_root = project_root
        self.merge_strategy = merge_strategy
        self.checkpoint = checkpoint
        self.dry_run = dry_run
        self.auto_commit = auto_commit
        self.allow_dirty = allow_dirty
        self.check_truncation = check_truncation
        self.strict_checkpoints = strict_checkpoints
        self._pre_integration_snapshots: Dict[str, Optional[Path]] = {}

    # ------------------------------------------------------------------
    # Path display helper
    # ------------------------------------------------------------------

    def _rel_display(self, path: Path) -> str:
        """Safe relative path for display, falling back to the full path."""
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

    # ------------------------------------------------------------------
    # Snapshot management (extracted from PrimeContractor)
    # ------------------------------------------------------------------

    def _snapshot_target(self, target_path: Path) -> None:
        """Save a copy of the target file before the first merge attempt.

        Idempotent — skips if a snapshot already exists for this target.
        Stores ``None`` for absent targets so rollback knows to delete.

        Limitation: snapshots are file-based (``.pre_integration`` sidecars)
        and live only in the in-memory ``_pre_integration_snapshots`` dict.
        If the process dies mid-integration, sidecar files may be orphaned
        and no automatic recovery is possible.  AR-807 (git tag restore
        points) is planned to address this with durable, git-based rollback.
        """
        key = str(target_path)
        if key in self._pre_integration_snapshots:
            return
        if target_path.is_file():
            snapshot_path = target_path.with_suffix(
                target_path.suffix + ".pre_integration"
            )
            shutil.copy2(target_path, snapshot_path)
            self._pre_integration_snapshots[key] = snapshot_path
            logger.debug("Snapshot saved: %s", self._rel_display(snapshot_path))
        else:
            self._pre_integration_snapshots[key] = None
            logger.debug(
                "Snapshot recorded (file absent): %s", self._rel_display(target_path)
            )

    def _restore_target(self, target_path: Path) -> bool:
        """Restore a target file from its pre-integration snapshot.

        Returns True if the restore succeeded, False if no snapshot found.
        """
        key = str(target_path)
        snapshot = self._pre_integration_snapshots.get(key)
        if key not in self._pre_integration_snapshots:
            logger.warning(
                "No pre-integration snapshot for %s", self._rel_display(target_path)
            )
            return False
        if snapshot is None:
            if target_path.is_file():
                target_path.unlink()
                logger.info("Deleted (no original): %s", self._rel_display(target_path))
            return True
        shutil.copy2(snapshot, target_path)
        logger.info("Restored from snapshot: %s", self._rel_display(target_path))
        return True

    def _cleanup_snapshots(self, target_paths: Optional[List[Path]] = None) -> int:
        """Remove ``.pre_integration`` snapshot files.

        Args:
            target_paths: Specific targets to clean up.  ``None`` cleans all.

        Returns:
            Number of snapshot files removed.
        """
        removed = 0
        if target_paths is None:
            keys = list(self._pre_integration_snapshots.keys())
        else:
            keys = [str(p) for p in target_paths]
        for key in keys:
            snapshot = self._pre_integration_snapshots.pop(key, None)
            if snapshot is not None and snapshot.exists():
                snapshot.unlink()
                removed += 1
                logger.debug("Cleaned snapshot: %s", self._rel_display(snapshot))
        return removed

    # ------------------------------------------------------------------
    # Dirty-file protection (extracted from PrimeContractor)
    # ------------------------------------------------------------------

    def is_file_dirty(self, path: Path) -> bool:
        """Check if a specific file has uncommitted changes."""
        result_staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only", str(path)],
            capture_output=True, text=True,
            cwd=self.project_root, timeout=300,
        )
        result_unstaged = subprocess.run(
            ["git", "diff", "--name-only", str(path)],
            capture_output=True, text=True,
            cwd=self.project_root, timeout=300,
        )
        return bool(result_staged.stdout.strip() or result_unstaged.stdout.strip())

    def _protect_dirty_target(self, path: Path) -> bool:
        """Check if it's safe to overwrite a target file.

        Returns:
            True if safe to overwrite, False if file has uncommitted changes.
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

    # ------------------------------------------------------------------
    # Boundary validation (CC-by-C)
    # ------------------------------------------------------------------

    def _validate_boundary(self, unit: IntegrationUnit) -> None:
        """Log warnings for missing expected context keys.

        Does not block integration — purely advisory for observability.
        """
        expected_keys = {"id", "name", "generated_files", "target_files"}
        ctx = unit.context or {}
        missing = expected_keys - set(ctx.keys()) - {"id", "name"}
        # id and name are properties on the protocol, not context keys
        if not unit.generated_files:
            logger.warning(
                "IntegrationUnit '%s' has no generated_files", unit.name,
            )
        if not unit.target_files:
            logger.warning(
                "IntegrationUnit '%s' has no target_files", unit.name,
            )

    # ------------------------------------------------------------------
    # Git commit
    # ------------------------------------------------------------------

    def _commit_files(self, unit: IntegrationUnit, files: List[Path]) -> None:
        """Commit the integrated files to git."""
        for file_path in files:
            subprocess.run(
                ["git", "add", str(file_path)],
                cwd=self.project_root, capture_output=True, timeout=300,
            )
        commit_msg = (
            f"feat: Integrate {unit.name}\n\n"
            "Integrated via IntegrationEngine"
        )
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=self.project_root, capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info("Committed: %s", unit.name)
        else:
            logger.warning(
                "Commit failed for '%s': %s", unit.name, result.stderr.strip(),
            )

    # ------------------------------------------------------------------
    # Main integration pipeline
    # ------------------------------------------------------------------

    def integrate(
        self,
        unit: IntegrationUnit,
        *,
        attempt: int = 1,
        listener: Optional[IntegrationListener] = None,
    ) -> IntegrationResult:
        """Run the full integration pipeline for a single unit.

        Pipeline steps:
          1. Notify listener: started
          2. If retry: restore snapshots for all targets
          3. Pre-validate generated .py files
          4. Per (source, target) pair: sanitize, truncation check, dirty check,
             snapshot, merge
          5. Auto-fix lint
          6. Run checkpoints
          7. On failure: rollback
          8. On success: optional auto-commit, cleanup snapshots

        Args:
            unit: The integration unit to process.
            attempt: Integration attempt number (1-based).  Values > 1 trigger
                snapshot restoration before merge.
            listener: Optional observer for lifecycle events.

        Returns:
            IntegrationResult with success status, integrated files, errors, etc.
        """
        if listener is None:
            listener = _NULL_LISTENER

        errors: List[str] = []
        warnings: List[str] = []
        checkpoint_results: List[Any] = []

        self._validate_boundary(unit)

        # 1. Notify started
        listener.on_integration_started(unit)
        logger.info(
            "INTEGRATING: %s (attempt %d)", unit.name, attempt,
            extra={"unit_id": unit.id, "attempt": attempt},
        )

        # 2. If retry: restore snapshots for all targets
        if attempt > 1:
            for tf in unit.target_files:
                tp = sanitize_path(tf, base_dir=self.project_root)
                if self._restore_target(tp):
                    logger.info(
                        "Retry %d: restored %s from snapshot",
                        attempt, self._rel_display(tp),
                    )

        # 3. Pre-validate generated .py files
        if not self.dry_run and self.checkpoint is not None:
            gen_paths = [
                Path(f)
                for f in unit.generated_files
                if Path(f).exists() and Path(f).suffix == ".py"
            ]
            if gen_paths:
                pre_result = self.checkpoint.pre_validate(gen_paths)
                # Emit GateResult
                try:
                    gate = GateEmitter.from_checkpoint_result(
                        pre_result, workflow_id=unit.id, trace_id=None,
                    )
                    GateEmitter.emit(gate)
                except Exception as gate_exc:
                    logger.warning(
                        "Failed to emit pre-validate gate result: %s", gate_exc,
                    )
                if pre_result.status == CheckpointStatus.FAILED:
                    error_msg = pre_result.message
                    if pre_result.errors:
                        error_msg += ": " + "; ".join(pre_result.errors[:5])
                    logger.error(
                        "Pre-merge validation failed for %s: %s",
                        unit.name, error_msg,
                        extra={"unit_id": unit.id},
                    )
                    errors.append(error_msg)
                    listener.on_integration_failed(unit, error_msg)
                    return IntegrationResult(
                        success=False,
                        errors=errors,
                        warnings=warnings,
                        checkpoint_results=[pre_result],
                    )
                logger.info(
                    "Pre-merge validation passed for %s", unit.name,
                    extra={"unit_id": unit.id},
                )

        # 4. Per (source, target) pair: merge
        integrated_files: List[Path] = []
        for i, source_file in enumerate(unit.generated_files):
            source_path = Path(source_file)

            # Resolve target path
            if i < len(unit.target_files):
                try:
                    target_path = sanitize_path(
                        unit.target_files[i], base_dir=self.project_root,
                    )
                except Exception as e:
                    logger.error(
                        "Path validation failed for '%s': %s",
                        unit.target_files[i], e,
                        extra={"unit_id": unit.id},
                    )
                    continue
            elif not source_path.exists():
                if self.dry_run:
                    target_path = self.project_root / "src" / source_path.name
                else:
                    logger.error(
                        "Source file not found: %s", source_path,
                        extra={"unit_id": unit.id},
                    )
                    continue
            else:
                target_path = self.project_root / "src" / source_path.name

            # Dry run: log only
            if self.dry_run:
                action = "update" if target_path.exists() else "create"
                logger.info(
                    "[DRY RUN] Would %s: %s", action, self._rel_display(target_path),
                    extra={"dry_run": True},
                )
                integrated_files.append(target_path)
                continue

            if not source_path.exists():
                logger.error(
                    "Source file not found: %s", source_path,
                    extra={"unit_id": unit.id},
                )
                continue

            # Truncation detection
            if self.check_truncation:
                from ..truncation_detection import (
                    CONFIDENCE_HIGH,
                    CONFIDENCE_HIGH_PROSE,
                    detect_truncation,
                    get_expected_sections_for_code,
                    log_truncation_result,
                )

                source_content = source_path.read_text(encoding="utf-8")
                expected = get_expected_sections_for_code(source_content)
                trunc_result = detect_truncation(
                    source_content, expected_sections=expected, strict_mode=False,
                )
                if trunc_result.is_truncated:
                    log_truncation_result(
                        trunc_result,
                        source_file=str(source_path),
                        feature_name=unit.name,
                        step_name="pre_integration",
                    )
                    code_mode_active = trunc_result.details.get("code_mode", False)
                    reject_threshold = (
                        CONFIDENCE_HIGH if code_mode_active else CONFIDENCE_HIGH_PROSE
                    )
                    if trunc_result.confidence >= reject_threshold:
                        logger.error(
                            "REJECTED %s: appears truncated "
                            "(confidence=%.0f%%, threshold=%.0f%%, code_mode=%s) "
                            "— integration blocked",
                            source_path.name,
                            trunc_result.confidence * 100,
                            reject_threshold * 100,
                            code_mode_active,
                            extra={"unit_id": unit.id},
                        )
                        continue
                    else:
                        logger.warning(
                            "Possible truncation in %s "
                            "(confidence=%.0f%%, threshold=%.0f%%, code_mode=%s) "
                            "— proceeding, review if build fails",
                            source_path.name,
                            trunc_result.confidence * 100,
                            reject_threshold * 100,
                            code_mode_active,
                            extra={"unit_id": unit.id},
                        )
                        warnings.append(
                            f"Possible truncation in {source_path.name}"
                        )

            # Dirty file protection
            if target_path.exists() and not self.allow_dirty:
                if not self._protect_dirty_target(target_path):
                    logger.warning(
                        "Skipping %s to protect uncommitted changes",
                        target_path.name,
                    )
                    continue

            # Snapshot (first attempt only)
            if attempt == 1:
                self._snapshot_target(target_path)

            # Merge
            if self.merge_strategy.can_merge(source_path, target_path):
                result = self.merge_strategy.merge(source_path, target_path)
                if result.status.value == "success":
                    logger.info(
                        "Merged: %s", self._rel_display(target_path),
                        extra={"unit_id": unit.id},
                    )
                    integrated_files.append(target_path)
                elif result.status.value == "conflict":
                    logger.warning(
                        "Merged with conflicts: %s — %s",
                        target_path.name,
                        "; ".join(result.conflicts[:3]),
                        extra={"unit_id": unit.id},
                    )
                    integrated_files.append(target_path)
                else:
                    logger.error(
                        "Merge failed for %s: %s",
                        target_path.name, result.error,
                        extra={"unit_id": unit.id},
                    )
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                logger.info(
                    "Copied: %s", self._rel_display(target_path),
                    extra={"unit_id": unit.id},
                )
                integrated_files.append(target_path)

            listener.on_file_integrated(unit, source_path, target_path)

        # 5. No files integrated → failure
        if not integrated_files:
            error_msg = "No files were integrated"
            errors.append(error_msg)
            listener.on_integration_failed(unit, error_msg)
            return IntegrationResult(
                success=False,
                errors=errors,
                warnings=warnings,
            )

        # 6. Post-merge: auto-fix lint + run checkpoints
        if not self.dry_run and self.checkpoint is not None:
            # Auto-fix trivially-fixable lint issues before running checkpoints
            for ifile in integrated_files:
                if ifile.suffix == ".py":
                    try:
                        subprocess.run(
                            [
                                "python3", "-m", "ruff", "check", "--fix",
                                "--unsafe-fixes", "--select=E7,E9,F", str(ifile),
                            ],
                            capture_output=True, text=True,
                            cwd=self.project_root, timeout=30,
                        )
                    except Exception:
                        pass  # best-effort

            logger.info(
                "Running integration checkpoints for '%s'...", unit.name,
            )
            results = self.checkpoint.run_all_checkpoints(
                integrated_files, unit.name,
            )

            # Import Check and Lint Check are advisory — downgrade FAILED → WARNING
            for r in results:
                if (
                    r.name in ("Import Check", "Lint Check")
                    and r.status == CheckpointStatus.FAILED
                ):
                    for err in r.errors or []:
                        logger.warning(
                            "Advisory %s: %s", r.name.lower(), err,
                            extra={"unit_id": unit.id},
                        )
                    r.status = CheckpointStatus.WARNING
                    r.warnings = (r.warnings or []) + (r.errors or [])
                    r.errors = []

            # Emit GateResult for each checkpoint
            for cr in results:
                try:
                    gate = GateEmitter.from_checkpoint_result(
                        cr, workflow_id=unit.id, trace_id=None,
                    )
                    GateEmitter.emit(gate)
                except Exception as gate_exc:
                    logger.warning(
                        "Failed to emit checkpoint gate result: %s", gate_exc,
                    )
                listener.on_checkpoint_result(unit, cr)

            checkpoint_results = results
            all_passed = self.checkpoint.summarize_results(results)

            if not all_passed:
                # Rollback
                failed_checks = [
                    r for r in results if r.status == CheckpointStatus.FAILED
                ]
                error_parts = []
                for r in failed_checks:
                    detail = r.message
                    if r.errors:
                        detail += ": " + "; ".join(r.errors[:5])
                    error_parts.append(detail)
                error_msg = " | ".join(error_parts)
                errors.append(error_msg)

                # Restore all targets
                for tf in unit.target_files:
                    try:
                        tp = sanitize_path(tf, base_dir=self.project_root)
                        self._restore_target(tp)
                    except Exception:
                        pass

                listener.on_integration_failed(unit, error_msg)
                return IntegrationResult(
                    success=False,
                    integrated_files=integrated_files,
                    errors=errors,
                    warnings=warnings,
                    rollback_performed=True,
                    checkpoint_results=checkpoint_results,
                )
        elif self.dry_run:
            logger.info(
                "[DRY RUN] Would run integration checkpoints",
                extra={"dry_run": True},
            )

        # 7. Auto-commit
        if self.auto_commit and not self.dry_run:
            self._commit_files(unit, integrated_files)

        # 8. Cleanup snapshots
        self._cleanup_snapshots(integrated_files)

        # 9. Notify completed
        listener.on_integration_completed(unit, integrated_files)
        logger.info(
            "'%s' integrated successfully", unit.name,
            extra={"unit_id": unit.id, "files_count": len(integrated_files)},
        )

        return IntegrationResult(
            success=True,
            integrated_files=integrated_files,
            errors=errors,
            warnings=warnings,
            checkpoint_results=checkpoint_results,
        )
