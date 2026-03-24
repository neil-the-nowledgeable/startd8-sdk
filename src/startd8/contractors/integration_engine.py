"""
IntegrationEngine — standalone integration pipeline extracted from PrimeContractor.

Handles the full merge lifecycle:
  snapshot → validate → merge → checkpoint → commit/rollback

Designed to be used by both PrimeContractorWorkflow (via FeatureSpecUnit adapter)
and the Artisan INTEGRATE phase (via SeedTaskUnit adapter).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from ..security import sanitize_path
from .checkpoint import CheckpointStatus, IntegrationCheckpoint
from .gate_contracts import GateEmitter
from .protocols import (
    IntegrationListener,
    IntegrationResult,
    IntegrationStatus,
    IntegrationUnit,
    MergeStrategy,
)

# Repair pipeline imports — optional, guarded (R2-S5)
try:
    from ..repair.diagnostics import classify_checkpoint_category, parse_checkpoint_diagnostics
    from ..repair.orchestrator import run_file_repair
    from ..repair.staging import create_staging

    _HAS_REPAIR = True
except ImportError:
    _HAS_REPAIR = False

# Backward-compat defaults — canonical source is PrimeContractorConfig.integration
_INTEGRATION_SIZE_REGRESSION_THRESHOLD = 0.60
_INTEGRATION_MIN_LINES = 50

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# REQ-MLT-102: Python-stub cross-language guard
# ---------------------------------------------------------------------------

_PYTHON_FUTURE_IMPORT_RE = "from __future__ import"


def _detect_python_stub_in_non_python(
    content: str, target_path: str,
) -> Optional[str]:
    """Return an error string if *content* looks like a Python stub but
    *target_path* is a non-Python file.  Returns ``None`` when the file is
    safe to write.

    This is a lightweight safety-net — it catches the obvious case where
    the template/skeleton system emits Python boilerplate into Go, HTML,
    Java, etc. files.
    """
    if target_path.endswith(".py"):
        return None

    # Fast-exit: no Python fingerprint at all.
    if _PYTHON_FUTURE_IMPORT_RE not in content:
        return None

    # Strip blank lines / whitespace for "only substantive lines" checks.
    substantive = [
        line for line in content.splitlines() if line.strip()
    ]

    # Case 1: content is *only* ``from __future__ import annotations``
    if len(substantive) == 1 and substantive[0].strip().startswith(
        "from __future__ import"
    ):
        return (
            "content consists solely of a Python __future__ import "
            f"('{substantive[0].strip()}')"
        )

    # Case 2: __future__ import + raise NotImplementedError skeleton
    non_future = [
        line for line in substantive
        if not line.strip().startswith("from __future__ import")
    ]
    if all(
        line.strip() == "raise NotImplementedError"
        for line in non_future
    ) and len(non_future) >= 1:
        return (
            "content is a Python skeleton stub "
            "(from __future__ import + raise NotImplementedError)"
        )

    # Case 3: generic — __future__ import present in a non-Python file
    from pathlib import PurePosixPath
    _ext = PurePosixPath(target_path).suffix
    _label = _ext.lstrip(".") if _ext else PurePosixPath(target_path).name
    return (
        f"Python 'from __future__ import' detected in non-Python target "
        f"({_label} file)"
    )


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
        repair_config: Optional[Any] = None,
        element_registry: Optional[Any] = None,
        size_regression_threshold: float = _INTEGRATION_SIZE_REGRESSION_THRESHOLD,
        min_lines: int = _INTEGRATION_MIN_LINES,
        element_retention_threshold: float = 0.80,
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
        # Phase 4: Manifest-based pre-merge diff
        self.manifest_registry: Any = None
        self.element_retention_threshold: float = element_retention_threshold
        # Size regression thresholds (from config or module defaults)
        self._size_regression_threshold: float = size_regression_threshold
        self._min_lines: int = min_lines
        # Repair pipeline (REQ-RPL-200)
        self._repair_config = repair_config
        # Element registry (ER-008)
        self._element_registry = element_registry
        # Forward manifest for contract violation repair
        self._forward_manifest: Any = None
        # Language profile for language-aware repair gating
        self._language_profile: Any = None
        # REQ-QPA-500: Cross-feature Anzen gate accumulator.
        # Entries are appended per-feature and finalized once at workflow end.
        self._anzen_gate_entries: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Phase 4: Manifest diff (IN-1 through IN-3)
    # ------------------------------------------------------------------

    def _manifest_pre_merge_diff(
        self, rel_path: str, staged_path: Path
    ) -> None:
        """Run manifest diff between existing and staged file (IN-1 through IN-3).

        Logs diff at INFO (IN-1). Emits WARNING on breaking changes (IN-2)
        and element regression below retention threshold (IN-3).

        Graceful: never blocks integration. All errors caught and logged.
        """
        if self.manifest_registry is None:
            return

        existing = self.manifest_registry.get(rel_path)
        if existing is None:
            return

        # Check staleness — skip diff for files modified after cache load
        try:
            if self.manifest_registry.is_stale(rel_path):
                logger.debug(
                    "manifest.diff: skipping stale file %s", rel_path,
                )
                return
        except Exception as exc:
            logger.debug("manifest.diff: staleness check failed for %s: %s", rel_path, exc)

        try:
            from startd8.utils.code_manifest import generate_file_manifest
            staged = generate_file_manifest(staged_path, self.project_root)
        except Exception as exc:
            logger.debug(
                "manifest.diff: failed to parse staged file %s: %s",
                rel_path, exc,
            )
            return

        try:
            from startd8.utils.manifest_registry import ManifestDiff
            diff = ManifestDiff.diff(existing, staged)

            logger.info(
                "manifest.diff",
                extra={
                    "path": rel_path,
                    "removed": len(diff.removed_public),
                    "added": len(diff.added_public),
                    "changed_sigs": len(diff.changed_signatures),
                    "delta": diff.element_count_delta,
                },
            )

            # IN-2: Breaking changes warning
            if diff.has_breaking_changes:
                logger.warning(
                    "manifest.diff: breaking changes detected in %s — "
                    "%d removed, %d changed signatures "
                    "(note: renames appear as removal+addition)",
                    rel_path,
                    len(diff.removed_public),
                    len(diff.changed_signatures),
                )
                try:
                    gate = GateEmitter.quality_gate_result(
                        gate_name="manifest_breaking_change",
                        passed=False,
                        details={
                            "path": rel_path,
                            "removed_fqns": diff.removed_public[:10],
                            "changed_sigs": [
                                {"fqn": fqn, "old": old, "new": new}
                                for fqn, old, new in diff.changed_signatures[:10]
                            ],
                        },
                    )
                    GateEmitter.emit(gate)
                except Exception as exc:
                    logger.debug(
                        "manifest.diff: GateEmitter failed: %s", exc,
                    )

            # IN-3: Element retention check
            from startd8.utils.manifest_registry import _count_all_elements
            old_count = _count_all_elements(existing.elements)
            if old_count > 0:
                new_count = old_count + diff.element_count_delta
                ratio = new_count / old_count
                if ratio < self.element_retention_threshold:
                    logger.warning(
                        "manifest.diff: element regression in %s — "
                        "ratio %.2f < threshold %.2f "
                        "(note: file splits/refactors may produce per-file false positives)",
                        rel_path, ratio, self.element_retention_threshold,
                    )

            # CG-IN-1: Escalate breaking changes based on caller count
            try:
                for fqn in diff.removed_public:
                    callers = self.manifest_registry.callers_of(fqn)
                    if callers:
                        logger.error(
                            "manifest.diff: removed public element %s has %d callers — "
                            "downstream breakage likely",
                            fqn, len(callers),
                        )
                    else:
                        logger.info(
                            "manifest.diff: removed public element %s has no callers",
                            fqn,
                        )
                for fqn, old_sig, new_sig in diff.changed_signatures:
                    callers = self.manifest_registry.callers_of(fqn)
                    if callers:
                        logger.error(
                            "manifest.diff: changed signature of %s has %d callers — "
                            "downstream breakage likely (old=%s, new=%s)",
                            fqn, len(callers), old_sig, new_sig,
                        )
                    else:
                        logger.info(
                            "manifest.diff: changed signature of %s has no callers",
                            fqn,
                        )
            except Exception as exc:
                logger.debug("manifest.diff: CG-IN-1 caller check failed: %s", exc)

            # CG-IN-2: Call edge diff
            try:
                removed_edges, added_edges = ManifestDiff.call_edge_diff(existing, staged)
                if removed_edges or added_edges:
                    logger.debug(
                        "manifest.diff: call edge changes in %s — "
                        "%d removed, %d added",
                        rel_path, len(removed_edges), len(added_edges),
                    )
            except Exception as exc:
                logger.debug("manifest.diff: CG-IN-2 edge diff failed: %s", exc)

            # CG-IN-3: Cross-file caller impact
            try:
                callers_map = self.manifest_registry.callers_of_file(rel_path)
                if callers_map:
                    affected_files: set[str] = set()
                    for _fqn, callers in callers_map.items():
                        for caller_fqn in callers:
                            resolved = self.manifest_registry.resolve_fqn(caller_fqn)
                            if resolved:
                                affected_files.add(resolved[0])
                    if affected_files:
                        logger.info(
                            "manifest.diff: modified file %s has callers in %d files — "
                            "consider re-testing: %s",
                            rel_path, len(affected_files),
                            ", ".join(sorted(affected_files)[:5]),
                        )
            except Exception as exc:
                logger.debug("manifest.diff: CG-IN-3 caller impact failed: %s", exc)

            # Phase 5 IN-1: Resolved type changes — catch type-level breaking changes
            # invisible to AST diff (e.g. resolved int vs str when AST signature is same)
            try:
                for fqn, old_rs, new_rs in diff.changed_resolved_signatures:
                    callers = self.manifest_registry.callers_of(fqn)
                    if callers:
                        logger.error(
                            "INTEGRATE IN-1: Resolved type change for %s: %r → %r "
                            "(%d callers — type change may break callers)",
                            fqn, old_rs, new_rs, len(callers),
                        )
                    else:
                        logger.warning(
                            "INTEGRATE IN-1: Resolved type change for %s: %r → %r "
                            "(no known callers)",
                            fqn, old_rs, new_rs,
                        )
            except Exception as exc:
                logger.debug("manifest.diff: IN-1 resolved type check failed: %s", exc)

            # Phase 5 IN-2: MRO changes — inheritance restructuring detection
            try:
                for fqn, old_mro, new_mro in diff.mro_changes:
                    added_bases = set(new_mro) - set(old_mro)
                    removed_bases = set(old_mro) - set(new_mro)
                    logger.warning(
                        "INTEGRATE IN-2: MRO changed for %s — added: %s, removed: %s",
                        fqn,
                        sorted(added_bases) or "none",
                        sorted(removed_bases) or "none",
                    )
                    try:
                        gate = GateEmitter.quality_gate_result(
                            gate_name="manifest_mro_change",
                            passed=False,
                            details={
                                "path": rel_path,
                                "fqn": fqn,
                                "old_mro": old_mro,
                                "new_mro": new_mro,
                            },
                        )
                        GateEmitter.emit(gate)
                    except Exception as exc:  # E2: GateEmitter is advisory, never block
                        logger.debug("manifest.diff: IN-2 GateEmitter failed for %s: %s", fqn, exc)
            except Exception as exc:
                logger.debug("manifest.diff: IN-2 MRO change check failed: %s", exc)

            # Phase 5 IN-3: __all__ diff — exported surface change logging
            try:
                if diff.module_all_diff is not None:
                    added_exports, removed_exports = diff.module_all_diff
                    if added_exports:
                        logger.info(
                            "INTEGRATE IN-3: New exports in __all__ for %s: %s",
                            rel_path, added_exports,
                        )
                    if removed_exports:
                        logger.info(
                            "INTEGRATE IN-3: Removed exports from __all__ for %s: %s "
                            "(may break 'from %s import *' consumers)",
                            rel_path, removed_exports,
                            rel_path.replace("/", ".").removesuffix(".py"),
                        )
            except Exception as exc:
                logger.debug("manifest.diff: IN-3 __all__ diff failed: %s", exc)

        except Exception as exc:
            logger.debug(
                "manifest.diff: diff failed for %s: %s", rel_path, exc,
            )

    def _manifest_post_merge_refresh(
        self, merged_files: List[str], context: Dict[str, Any]
    ) -> None:
        """Refresh manifest registry after successful merges (IN-4).

        Creates a NEW ManifestRegistry instance (immutable-per-phase, req R1-S1).
        Per-file parse failures are tolerated (excluded from update).
        """
        if self.manifest_registry is None:
            return

        try:
            from startd8.utils.code_manifest import generate_file_manifest
            from startd8.utils.manifest_registry import ManifestRegistry

            staged_updates = {}
            for rel_path in merged_files:
                try:
                    full_path = self.project_root / rel_path
                    if full_path.exists():
                        fresh = generate_file_manifest(full_path, self.project_root)
                        staged_updates[rel_path] = fresh
                except Exception as exc:
                    logger.warning(
                        "manifest.refresh_file_failed",
                        extra={"path": rel_path, "error": str(exc)},
                    )

            if staged_updates:
                new_registry = self.manifest_registry.with_updated_files(staged_updates)
                context["project_manifests"] = new_registry
                self.manifest_registry = new_registry
                logger.debug(
                    "manifest.refresh",
                    extra={
                        "files_refreshed": len(staged_updates),
                        "files_failed": len(merged_files) - len(staged_updates),
                    },
                )
        except Exception as exc:
            logger.warning("manifest.refresh: failed: %s", exc)

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
    # Path derivation (PCA-607)
    # ------------------------------------------------------------------

    def _derive_target_from_source(self, source_path: Path, unit: IntegrationUnit) -> Path:
        """Derive a project-relative target path from a staging source path.

        Strips known staging directory prefixes (e.g. ``.startd8/staging/``,
        ``.startd8/state/``) to recover the original relative path.  Falls
        back to ``project_root / source_path.name`` when no staging marker
        is found (preserves previous behavior minus the hardcoded ``src/``).
        """
        source_resolved = source_path.resolve()
        source_str = str(source_resolved)
        staging_markers = [".startd8/staging", ".startd8/state"]
        for marker in staging_markers:
            marker_str = f"/{marker}/"
            if marker_str in source_str:
                relative = source_str.split(marker_str, 1)[1]
                if not relative:
                    break  # degenerate path — fall through to filename fallback
                try:
                    return sanitize_path(relative, base_dir=self.project_root)
                except (ValueError, OSError) as exc:
                    logger.warning(
                        "sanitize_path rejected derived relative path '%s' "
                        "from %s: %s — falling back to filename",
                        relative, source_path, exc,
                        extra={"unit_id": unit.id},
                    )
                    return self.project_root / source_path.name
        # Fallback: try to match the source filename against known target
        # files in the unit.  If a target file shares the same basename,
        # reuse its directory structure instead of writing to project root.
        src_name = source_path.name
        for tf in unit.target_files:
            if Path(tf).name == src_name:
                try:
                    matched = sanitize_path(tf, base_dir=self.project_root)
                    logger.info(
                        "Derived target for %s from matching target_file entry: %s",
                        source_path, matched,
                        extra={"unit_id": unit.id},
                    )
                    return matched
                except (ValueError, OSError):
                    pass
        logger.warning(
            "Could not derive relative path for %s — using filename only",
            source_path,
            extra={"unit_id": unit.id},
        )
        return self.project_root / source_path.name

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
    # Element registry provenance (ER-008)
    # ------------------------------------------------------------------

    def _record_element_merge_outcomes(
        self,
        unit: IntegrationUnit,
        integrated_files: List[Path],
        skipped_files: List[Dict[str, Any]],
    ) -> None:
        """Record per-element merge outcomes in the element registry.

        For each integrated file, look up known elements and mark them as
        ``integrated``.  For skipped files, mark elements as ``blocked``.
        """
        registry = self._element_registry
        if registry is None:
            return

        integrated_set = {str(f) for f in integrated_files}
        skipped_set = {
            entry.get("path", "") for entry in skipped_files
        }

        for tf in unit.target_files:
            try:
                entries = registry.elements_for_file(tf)
            except Exception:
                continue
            for entry in entries:
                try:
                    if tf in integrated_set or any(
                        tf in str(p) for p in integrated_files
                    ):
                        registry.set_phase_status(
                            entry.element_id,
                            "integrate",
                            "merged",
                            metadata={"unit_id": unit.id},
                        )
                    elif tf in skipped_set:
                        registry.set_phase_status(
                            entry.element_id,
                            "integrate",
                            "blocked",
                            metadata={"unit_id": unit.id},
                        )
                except Exception as exc:
                    logger.debug(
                        "Element provenance recording failed for %s: %s",
                        entry.element_id, exc,
                    )

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
    # AR-823: Import validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_imports(
        source_path: Path,
        module_inventory: List[str],
    ) -> List[str]:
        """AR-823: Validate first-party imports against known project modules.

        Parses the source file's AST, extracts all import statements, and
        checks that any import whose top-level name matches a project
        package actually resolves to a known module in the inventory.

        Returns list of unresolved first-party import dotted names.
        """
        import ast
        import sys

        if source_path.suffix != ".py" or not module_inventory:
            return []

        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
        except SyntaxError:
            return []  # Syntax errors caught elsewhere

        # Collect full dotted import names
        imported_modules: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

        # Build lookup sets
        stdlib = set(getattr(sys, "stdlib_module_names", set()))
        project_top_level = {m.split(".")[0] for m in module_inventory}
        inventory_set = set(module_inventory)

        unresolved = []
        for full_mod in sorted(imported_modules):
            top = full_mod.split(".")[0]
            # Skip stdlib
            if top in stdlib:
                continue
            # Not a project module at all → third-party, skip
            if top not in project_top_level:
                continue
            # It's a project import — verify the module path resolves:
            # 1. Exact match: full_mod is in inventory
            if full_mod in inventory_set:
                continue
            # 2. Parent exists: full_mod is a .py module inside a known
            #    package (e.g. "startd8.agents.base" where "startd8.agents"
            #    is in inventory — base.py is a module, not a sub-package)
            parts = full_mod.split(".")
            parent = ".".join(parts[:-1])
            if parent and parent in inventory_set:
                continue
            # 3. Descendant exists: full_mod is a package prefix of a known
            #    deeper package (e.g. importing "startd8" when "startd8.agents"
            #    is in inventory)
            if any(inv.startswith(full_mod + ".") for inv in inventory_set):
                continue
            unresolved.append(full_mod)

        return unresolved

    # ------------------------------------------------------------------
    # Repair pipeline (REQ-RPL-200)
    # ------------------------------------------------------------------

    def _attempt_pre_merge_repair(
        self,
        gen_paths: List[Path],
        unit: IntegrationUnit,
    ) -> Optional[Any]:
        """Attempt repair on generated files BEFORE merge.

        Runs syntax and lint checks individually (not aggregated via
        ``pre_validate``) so that ``classify_checkpoint_category`` can
        route diagnostics correctly.  Import repair is excluded because
        generated files are not yet under ``src_dirs``.

        REQ-RPL-302 execution order note: This method runs in step 3
        (pre-validate), BEFORE the merge loop (step 4). The post-merge
        repair path (``_attempt_repair``) runs in step 6, AFTER the
        merge AND AFTER the ruff auto-fix. Both paths are guarded by
        ``repair_config.repair_enabled`` and additionally
        ``pre_checkpoint_repair`` controls this pre-merge path.

        Returns a replacement ``CheckpointResult`` from re-running
        ``pre_validate`` after successful repair, or ``None`` if repair
        was not attempted or failed.
        """
        if not (
            _HAS_REPAIR
            and self._repair_config is not None
            and getattr(self._repair_config, "repair_enabled", False)
        ):
            logger.debug(
                "Pre-merge repair skipped: _HAS_REPAIR=%s, "
                "repair_config=%s, repair_enabled=%s",
                _HAS_REPAIR,
                self._repair_config is not None,
                getattr(self._repair_config, "repair_enabled", "N/A"),
            )
            return None

        # P0: Skip repair for languages that disable it (e.g. Go — compiler validates)
        if (
            self._language_profile is not None
            and not self._language_profile.repair_enabled
        ):
            logger.info(
                "Pre-merge repair skipped: language=%s has repair_enabled=False",
                self._language_profile.language_id,
            )
            return None

        try:
            # Run checks individually for proper diagnostic routing
            syntax_result = self.checkpoint.check_syntax(gen_paths)
            lint_result = self.checkpoint.check_lint(
                gen_paths, ignore_codes=["F401"],
            )

            failed_results = [
                r for r in (syntax_result, lint_result)
                if r.status == CheckpointStatus.FAILED
            ]
            if not failed_results:
                return None

            categories = {
                classify_checkpoint_category(r) for r in failed_results
            }
            repairable = categories & set(
                self._repair_config.repairable_categories
            )
            if not repairable:
                return None

            logger.info(
                "Pre-merge repair: attempting %s for %s",
                sorted(repairable), unit.name,
                extra={"unit_id": unit.id},
            )

            diagnostics = parse_checkpoint_diagnostics(failed_results)
            files_to_repair: Dict[Path, str] = {}
            for gp in gen_paths:
                if gp.suffix in (".py", ".java", ".go", ".cs", ".js") and gp.exists():
                    files_to_repair[gp] = gp.read_text(encoding="utf-8")

            if not files_to_repair:
                return None

            outcome = run_file_repair(
                files_to_repair,
                diagnostics,
                self._repair_config,
                self.project_root,
            )

            if outcome.any_modified:
                # Write repaired content back in-place (no staging needed)
                for fpath, content in outcome.repaired_files.items():
                    fpath.write_text(content, encoding="utf-8")

                # Gap-A: Update element registry for repaired files
                if self._element_registry is not None:
                    for fpath in outcome.repaired_files:
                        rel = str(fpath.relative_to(self.project_root)) if fpath.is_absolute() else str(fpath)
                        for entry in self._element_registry.elements_for_file(rel):
                            self._element_registry.set_phase_status(
                                entry.element_id, "integrate", "repaired",
                                metadata={"repair_stage": "pre_merge"},
                            )

                # Re-run pre_validate to verify
                new_result = self.checkpoint.pre_validate(gen_paths)
                logger.info(
                    "Pre-merge repair result for %s: %s",
                    unit.name, new_result.status.value,
                    extra={"unit_id": unit.id},
                )
                return new_result

        except Exception as exc:
            logger.warning(
                "Pre-merge repair failed for %s: %s",
                unit.name, exc,
                extra={"unit_id": unit.id},
            )

        return None

    def _attempt_repair(
        self,
        results: List[Any],
        integrated_files: List[Path],
        unit: IntegrationUnit,
        attempt: int,
        result_obj_metadata: Dict[str, Any],
    ) -> tuple[list[Any], bool]:
        """Attempt deterministic repair on failed checkpoint results.

        Args:
            results: Checkpoint results (may contain FAILED entries).
            integrated_files: Files that were merged into the project.
            unit: Integration unit being processed.
            attempt: Current integration attempt number.
            result_obj_metadata: Mutable metadata dict — repair keys are
                added in-place.

        Returns:
            Tuple of (possibly-updated results, repair_success bool).
        """
        repair_success = False
        repair_attempted = False

        if not (
            _HAS_REPAIR
            and self._repair_config is not None
            and getattr(self._repair_config, "repair_enabled", False)
        ):
            return results, False

        # P0: Skip repair for languages that disable it
        if (
            self._language_profile is not None
            and not self._language_profile.repair_enabled
        ):
            logger.info(
                "Post-merge repair skipped: language=%s has repair_enabled=False",
                self._language_profile.language_id,
            )
            return results, False

        failed_checks = [
            r for r in results
            if r.status == CheckpointStatus.FAILED
        ]
        categories = {
            classify_checkpoint_category(r) for r in failed_checks
        }
        repairable = categories & set(
            self._repair_config.repairable_categories
        )

        if not (repairable and failed_checks):
            return results, False

        repair_start = time.monotonic()
        try:
            diagnostics = parse_checkpoint_diagnostics(failed_checks)
            files_to_repair: Dict[Path, str] = {}
            for ifile in integrated_files:
                if ifile.suffix in (".py", ".java", ".go", ".cs", ".js") and ifile.exists():
                    files_to_repair[ifile] = ifile.read_text(
                        encoding="utf-8",
                    )

            # R3-S1: Truncation pre-filter
            truncation_skipped: List[str] = []
            try:
                from ..truncation_detection import (
                    CONFIDENCE_TRUNCATION_BLOCKED,
                    detect_truncation,
                )
                for fpath in list(files_to_repair):
                    tr = detect_truncation(files_to_repair[fpath])
                    if tr.confidence >= CONFIDENCE_TRUNCATION_BLOCKED:
                        del files_to_repair[fpath]
                        truncation_skipped.append(str(fpath))
            except (ImportError, OSError, ValueError):
                pass  # truncation detection is advisory

            if files_to_repair:
                staging_root = (
                    self._repair_config.staging_root
                    or self.project_root / ".startd8" / "repair"
                )
                with create_staging(
                    files_to_repair,
                    staging_root,
                    unit.name,
                    attempt,
                    project_root=self.project_root,
                ) as staged:
                    outcome = run_file_repair(
                        staged.files,
                        diagnostics,
                        self._repair_config,
                        self.project_root,
                    )
                    repair_attempted = True

                    if outcome.any_modified:
                        staged.write_repaired(outcome.repaired_files)
                        # R2-S2: Engine drives re-checkpoint
                        recheckpoint_results = (
                            self.checkpoint.run_all_checkpoints(
                                staged.paths, unit.name,
                            )
                        )
                        if self.checkpoint.summarize_results(
                            recheckpoint_results,
                        ):
                            # R1-S4: Atomic swap
                            staged.apply_atomic()
                            results = recheckpoint_results
                            repair_success = True

                            # Gap-A: Update element registry for post-merge repaired files
                            if self._element_registry is not None:
                                for fpath in outcome.repaired_files:
                                    rel = str(fpath.relative_to(self.project_root)) if fpath.is_absolute() else str(fpath)
                                    for entry in self._element_registry.elements_for_file(rel):
                                        self._element_registry.set_phase_status(
                                            entry.element_id, "integrate", "repaired",
                                            metadata={"repair_stage": "post_merge"},
                                        )

                # R3-S2: Cost measurement
                repair_duration_ms = (
                    (time.monotonic() - repair_start) * 1000
                )
                result_obj_metadata.update({
                    "repair_attempted": True,
                    "repair_success": repair_success,
                    "repair_duration_ms": repair_duration_ms,
                    "repair_steps": outcome.steps_applied,
                    "repair_files_modified": [
                        str(p) for p in outcome.repaired_files
                    ],
                })
                # REQ-RFL-105: Condensed repair summary for review adapter
                result_obj_metadata.setdefault(
                    "repair_summaries", [],
                ).append({
                    "phase": "post_merge",
                    "total_repairs": len(outcome.repaired_files) if outcome.repaired_files else 0,
                    "steps_applied": list(outcome.steps_applied) if outcome.steps_applied else [],
                    "any_modified": bool(outcome.any_modified),
                })
                if truncation_skipped:
                    result_obj_metadata["truncation_skipped"] = (
                        truncation_skipped
                    )

                # REQ-RPL-501: Cost avoidance tracking
                if repair_success:
                    estimated_regen_cost = getattr(
                        self._repair_config,
                        "estimated_regen_cost_usd",
                        0.75,  # static estimate; midpoint of $0.50-$1.00 regen range
                    )
                    result_obj_metadata[
                        "repair_cost_avoided_usd"
                    ] = estimated_regen_cost

                    # REQ-RPL-401/501: OTel cost avoidance counter
                    try:
                        from ..repair import record_cost_avoided
                        record_cost_avoided(estimated_regen_cost)
                    except ImportError:
                        logger.debug("repair.record_cost_avoided not available — skipping OTel cost counter")

                    # REQ-RPL-303: Handoff attribution (P2)
                    result_obj_metadata["repairs"] = [
                        {
                            "file": str(fpath),
                            "steps": [
                                r.step_name
                                for r in (
                                    fr.step_results
                                    if hasattr(fr, "step_results")
                                    else []
                                )
                                if r.modified
                            ],
                            "lines_modified": len(
                                content.splitlines()
                            ) - len(
                                files_to_repair.get(fpath, "").splitlines()
                            ),
                        }
                        for fpath, content in outcome.repaired_files.items()
                        for fr in outcome.file_results
                        if fr.file_path == fpath
                    ]

                # R3-S5: EventBus emission
                try:
                    from ..events import Event, EventBus, EventType
                    EventBus.emit(Event(
                        type=EventType.PIPELINE_STEP_COMPLETE,
                        source="repair",
                        data={
                            "success": repair_success,
                            "duration_ms": repair_duration_ms,
                            "files_repaired": len(outcome.repaired_files),
                            "steps": outcome.steps_applied,
                        },
                    ))
                except (ImportError, AttributeError, TypeError) as ebus_exc:
                    logger.debug(
                        "EventBus repair emission skipped: %s", ebus_exc,
                    )

                # REQ-RPL-501: Cost avoidance event emission
                if repair_success:
                    try:
                        from ..events import Event, EventBus, EventType
                        EventBus.emit(Event(
                            type=EventType.PIPELINE_STEP_COMPLETE,
                            source="repair.cost_avoided",
                            data={
                                "cost_avoided_usd": estimated_regen_cost,
                                "feature_name": unit.name,
                            },
                        ))
                    except (ImportError, AttributeError, TypeError):
                        pass  # advisory

        except Exception as exc:
            # R2-S5 + R3-S7: Defensive guard
            logger.error(
                "Repair pipeline failed: %s", exc,
                exc_info=True,
                extra={"unit_id": unit.id},
            )
            result_obj_metadata["repair_attempted"] = repair_attempted
            result_obj_metadata["repair_success"] = False
            result_obj_metadata["repair_error"] = str(exc)

            # R3-S6: Persist to TaskErrorStore
            try:
                from ..storage.error_store import TaskErrorStore
                TaskErrorStore(
                    project_root=self.project_root,
                ).record_error(
                    workflow_id=unit.id,
                    source="repair",
                    error_message=str(exc),
                    context={"categories": sorted(repairable)},
                )
            except (ImportError, OSError, ValueError) as store_exc:
                logger.debug(
                    "TaskErrorStore repair persistence skipped: %s",
                    store_exc,
                )

        return results, repair_success

    # ------------------------------------------------------------------
    # Anzen gate: security verification (SP-GT-001–004)
    # ------------------------------------------------------------------

    def _run_anzen_gate(
        self,
        integrated_files: List[Path],
        unit: IntegrationUnit,
        result_metadata: Dict[str, Any],
    ) -> None:
        """Run security verification on integrated files via query_prime.

        Uses ``query_prime.security.verify_file()`` for two-pass injection
        detection, credential leakage, and resource lifecycle checks.
        Injection and credential findings are hard failures (not advisory).

        Runs AFTER semantic repair so it evaluates repaired code.
        Runs BEFORE advisory downgrade so findings are never demoted.
        """
        try:
            from startd8.query_prime.security import verify_file
            from startd8.query_prime.decomposer import detect_database_type
            from startd8.query_prime.models import SecurityCheckType, SecurityVerdict
        except ImportError:
            logger.warning(
                "Anzen security gate SKIPPED — query_prime module not available. "
                "Install startd8[security] to enable SQL injection, credential "
                "leakage, and resource lifecycle checks.",
            )
            result_metadata["anzen_gate"] = [{"status": "skipped", "reason": "query_prime not available"}]
            # Write gate-skipped sentinel so consumers distinguish
            # "all clean" from "never ran" (REQ-KSP-499 gap analysis)
            try:
                from startd8.security_prime.gate_metrics import write_gate_metrics_report
                import datetime as _dt
                skipped_report = {
                    "schema_version": "1.0.0",
                    "status": "skipped",
                    "run_id": result_metadata.get(
                        "run_id",
                        f"skipped-{_dt.datetime.now().strftime('%H%M%S')}",
                    ),
                    "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                    "reason": "query_prime not available",
                    "files_checked": 0,
                    "files_skipped": 0,
                    "files_total": 0,
                    "security_posture": "SKIPPED",
                }
                out_dir = str(self.project_root) if self.project_root else "."
                write_gate_metrics_report(skipped_report, out_dir)
            except (ImportError, OSError):
                pass
            return

        # Load allowlist for false-positive suppression
        allowlist = []
        try:
            from startd8.security_prime.allowlist import load_allowlist, is_allowlisted
            project_root = str(self.project_root) if self.project_root else "."
            allowlist = load_allowlist(project_root)
        except ImportError:
            is_allowlisted = None  # type: ignore[assignment]

        import fnmatch as _fnmatch
        import time as _time
        from dataclasses import replace as _dc_replace

        gate_results = []
        enriched_entries: List[Dict[str, Any]] = []
        allowlist_hit_tracker: Dict[str, List[str]] = {}
        checks_that_ran: set = set()
        findings_by_check_type: Dict[str, int] = {}
        files_skipped = 0

        for fpath in integrated_files:
            if not fpath.is_file():
                continue
            try:
                source = fpath.read_text(errors="replace")
            except OSError:
                continue

            # Auto-detect database type from source content
            db_type = detect_database_type(source)
            if db_type is None:
                # REQ-QPA-201/202: check seed metadata for security_sensitive
                # features — gate all files from security-sensitive tasks
                # even when source doesn't contain direct DB keywords.
                unit_ctx = getattr(unit, "context", {}) or {}
                if unit_ctx.get("security_sensitive"):
                    db_str = unit_ctx.get("detected_database", "")
                    if db_str:
                        try:
                            from startd8.query_prime.models import DatabaseType as _DBT
                            db_type = _DBT(db_str)
                        except (ValueError, KeyError):
                            # Intentional: "unknown" is a valid str fallback;
                            # verify_file accepts DatabaseType | str.
                            db_type = "unknown"
                    else:
                        db_type = "unknown"  # security_sensitive but no specific DB
                else:
                    files_skipped += 1
                    continue  # No database surface — skip

            # Resolve language from file extension
            _ext_to_lang = {
                ".cs": "csharp", ".py": "python", ".go": "go",
                ".java": "java", ".js": "nodejs", ".ts": "nodejs",
            }
            language = _ext_to_lang.get(fpath.suffix, "")
            if not language:
                files_skipped += 1
                continue

            t0 = _time.monotonic()
            sv_result = verify_file(
                source, str(fpath), db_type, language,
            )
            verify_time_ms = (_time.monotonic() - t0) * 1000.0

            # REQ-KQP-102: Per-step timing threshold alert
            step_timing = sv_result.verification_timing_ms or {}
            det_total = sum(step_timing.values())
            if det_total > 500.0:
                logger.warning(
                    "Anzen verification slow: %s took %.0fms (injection=%.0f, "
                    "credential=%.0f, lifecycle=%.0f) — pattern module may need optimization",
                    fpath.name, det_total,
                    step_timing.get("injection_ms", 0),
                    step_timing.get("credential_ms", 0),
                    step_timing.get("lifecycle_ms", 0),
                )

            # Track checks that ran
            for finding_item in sv_result.findings:
                checks_that_ran.add(finding_item.check_type.value)
                ct_val = finding_item.check_type.value
                findings_by_check_type[ct_val] = findings_by_check_type.get(ct_val, 0) + 1

            # Allowlist suppression: filter out operator-declared false positives
            was_allowlisted = False
            if allowlist and is_allowlisted is not None and sv_result.findings:
                unsuppressed = []
                for finding in sv_result.findings:
                    justification = is_allowlisted(
                        str(fpath), finding.check_type.value, allowlist,
                    )
                    if justification:
                        logger.info(
                            "Anzen allowlist: suppressed %s in %s (%s)",
                            finding.check_type.value, fpath.name, justification,
                        )
                        was_allowlisted = True
                        # Track allowlist hit for audit
                        for al_entry in allowlist:
                            if (al_entry["check_id"] == finding.check_type.value
                                    and _fnmatch.fnmatch(str(fpath), al_entry["file_pattern"])):
                                allowlist_hit_tracker.setdefault(
                                    al_entry["file_pattern"], [],
                                ).append(str(fpath))
                                break
                    else:
                        unsuppressed.append(finding)
                # Recompute verdict with unsuppressed findings only
                if len(unsuppressed) < len(sv_result.findings):
                    has_hard = any(
                        f.check_type in (SecurityCheckType.INJECTION, SecurityCheckType.CREDENTIAL_LEAKAGE)
                        and f.severity == "error"
                        for f in unsuppressed
                    )
                    if has_hard:
                        new_verdict = SecurityVerdict.FAIL
                    elif unsuppressed:
                        new_verdict = SecurityVerdict.WARN
                    else:
                        new_verdict = SecurityVerdict.PASS
                    # Replace result with filtered version
                    sv_result = _dc_replace(
                        sv_result, findings=unsuppressed, verdict=new_verdict,
                    )

            gate_results.append(sv_result)

            # Compute per-file score
            try:
                from startd8.security_prime.scorer import compute_security_score
                score = compute_security_score(
                    sv_result.verdict.value,
                    [f.severity for f in sv_result.findings] if sv_result.findings else None,
                )
            except ImportError:
                score = {"pass": 1.0, "warn": 0.7, "fail": 0.0}.get(
                    sv_result.verdict.value, 0.5,
                )

            # Build enriched entry for gate report
            finding_types: Dict[str, int] = {}
            finding_severities: List[str] = []
            structured_findings: List[Dict[str, Any]] = []
            for f in sv_result.findings:
                _fct = f.check_type.value
                finding_types[_fct] = finding_types.get(_fct, 0) + 1
                finding_severities.append(f.severity)
                structured_findings.append({
                    "check_type": _fct,
                    "severity": f.severity,
                    "message": f.message,
                    "line": f.line,
                    "pattern_hash": getattr(f, "pattern_hash", ""),
                })

            db_str = db_type.value if hasattr(db_type, "value") else str(db_type)
            enriched_entries.append({
                "file_path": str(fpath),
                "verdict": sv_result.verdict.value,
                "score": score,
                "findings_count": len(sv_result.findings),
                "finding_types": finding_types,
                "finding_severities": finding_severities,
                "findings": structured_findings,
                "database": db_str,
                "language": language,
                "timing_ms": verify_time_ms,
                "step_timing_ms": sv_result.verification_timing_ms or {},
                "allowlisted": was_allowlisted,
                "prompt_security_features": result_metadata.get("prompt_security_features"),
            })

            # OTel recording
            try:
                from startd8.security_prime.otel import record_gate_result
                record_gate_result(
                    str(fpath), sv_result.verdict.value, score,
                    db_str, language, len(sv_result.findings),
                )
            except ImportError:
                pass

            if sv_result.verdict == SecurityVerdict.FAIL:
                logger.error(
                    "Anzen gate FAIL: %s — %s",
                    fpath.name,
                    sv_result.findings[0].message if sv_result.findings else "security violation",
                    extra={"unit_id": unit.id},
                )
            elif sv_result.verdict == SecurityVerdict.WARN:
                logger.warning(
                    "Anzen gate WARN: %s — lifecycle issue",
                    fpath.name,
                    extra={"unit_id": unit.id},
                )

        if gate_results:
            result_metadata["anzen_gate"] = enriched_entries
            # Track files processed by Query Prime so _run_semantic_checks
            # can suppress duplicate sql_injection_risk findings.
            # Query Prime's two-pass detection is authoritative for injection.
            self._anzen_gated_files: set = getattr(self, "_anzen_gated_files", set())
            self._anzen_gated_files.update(r.file_path for r in gate_results)
            # REQ-QPA-500: Accumulate for cross-feature finalization
            self._anzen_gate_entries.extend(enriched_entries)

            # Bridge Anzen findings into semantic_issues for postmortem/Kaizen
            # visibility (CRITICAL: without this, security findings are orphaned
            # from the Kaizen feedback loop — see Issues #1-4 in security audit).
            try:
                from startd8.forward_manifest_validator import validate_disk_compliance
                for entry in enriched_entries:
                    if not entry.get("findings"):
                        continue
                    fpath_str = entry["file_path"]
                    for finding in entry["findings"]:
                        # Convert to semantic issue format (category prefix
                        # "query_security_" enables _SEMANTIC_CATEGORY_TO_SUGGESTION
                        # mapping in prime_postmortem.py).
                        check_type = finding.get("check_type", "unknown")
                        category = f"query_security_{check_type}"
                        issue_dict = {
                            "category": category,
                            "severity": finding.get("severity", "error"),
                            "message": finding.get("message", ""),
                            "line": finding.get("line"),
                        }
                        # Append to the unit's accumulated semantic issues
                        # (populated by _run_semantic_checks which ran first).
                        if not hasattr(unit, "_anzen_semantic_issues"):
                            unit._anzen_semantic_issues = []
                        unit._anzen_semantic_issues.append(
                            (fpath_str, issue_dict),
                        )
            except Exception:
                logger.debug("Anzen→semantic bridge failed (non-fatal)", exc_info=True)

            # Wire update_security_metrics() (Phase 0: remaining work #5)
            try:
                from startd8.security_prime.kaizen import update_security_metrics
                from startd8.security_prime.scorer import compute_aggregate_score

                per_file_scores = [e["score"] for e in enriched_entries]
                agg_score = compute_aggregate_score(per_file_scores)
                injection_count = sum(
                    e.get("finding_types", {}).get("injection", 0)
                    for e in enriched_entries
                )
                credential_count = sum(
                    e.get("finding_types", {}).get("credential_leakage", 0)
                    for e in enriched_entries
                )
                violation_files = [
                    e["file_path"] for e in enriched_entries
                    if e["verdict"] == "fail"
                ]
                output_dir = str(self.project_root) if self.project_root else "."
                update_security_metrics(
                    output_dir,
                    injection_blocked=injection_count,
                    credential_blocked=credential_count,
                    aggregate_score=agg_score,
                    files_checked=len(enriched_entries),
                    files_skipped=files_skipped,
                    violation_files=violation_files,
                )
            except (ImportError, OSError) as exc:
                logger.debug("Security metrics update skipped: %s", exc)

            # Build and write gate verdict report (Phase 1)
            try:
                from startd8.security_prime.gate_metrics import (
                    build_gate_verdict_report,
                    build_owasp_section,
                    compute_component_contributions,
                    compute_score_distribution,
                    compute_threshold_sensitivity,
                    write_gate_metrics_report,
                )
                from startd8.security_prime.allowlist import build_allowlist_metrics

                owasp_section = build_owasp_section(
                    checks_that_ran, findings_by_check_type,
                )
                score_dist = compute_score_distribution(
                    [e["score"] for e in enriched_entries],
                )
                thresh_sens = compute_threshold_sensitivity(enriched_entries)
                comp_contribs = compute_component_contributions(enriched_entries)
                al_metrics = build_allowlist_metrics(
                    allowlist, allowlist_hit_tracker,
                )

                # Aggregate prompt security features for report
                psf = result_metadata.get("prompt_security_features")
                if psf:
                    from startd8.security_prime.gate_metrics import compute_prompt_effectiveness
                    security_sensitive_count = sum(
                        1 for e in enriched_entries
                        if (e.get("prompt_security_features") or {}).get("security_sensitive")
                    )
                    prompt_eff = compute_prompt_effectiveness(
                        enriched_entries,
                        security_sensitive_tasks=security_sensitive_count,
                        p0_injected=psf.get("p0_injected", False),
                        p1_databases=psf.get("p1_databases"),
                    )
                else:
                    prompt_eff = None

                import uuid as _uuid
                run_id = result_metadata.get("run_id", str(_uuid.uuid4())[:8])
                gate_report = build_gate_verdict_report(
                    enriched_entries,
                    run_id,
                    allowlist_metrics=al_metrics,
                    owasp_data=owasp_section,
                    score_distribution=score_dist,
                    threshold_sensitivity=thresh_sens,
                    component_contributions=comp_contribs,
                    prompt_effectiveness=prompt_eff,
                )
                out_dir = str(self.project_root) if self.project_root else "."
                write_gate_metrics_report(gate_report, out_dir)
            except (ImportError, OSError) as exc:
                logger.debug("Gate metrics report skipped: %s", exc)

            # REQ-QPA-500: Per-unit metrics writes removed — accumulated
            # entries are finalized by finalize_anzen_metrics() at workflow end.
            # Per-unit report is still stashed in result_metadata for the
            # postmortem to thread into integration_history per-feature.
            result_metadata["_query_security_entries"] = enriched_entries

    # ------------------------------------------------------------------
    # REQ-QPA-500: Cross-feature Anzen gate finalization
    # ------------------------------------------------------------------

    def finalize_anzen_metrics(
        self, output_dir: str, run_id: str,
    ) -> Dict[str, Any]:
        """Aggregate accumulated Anzen gate entries and write final metrics.

        Called once at workflow end (after all features integrated).
        Returns the aggregated report dict for threading into result_dict.
        """
        entries = self._anzen_gate_entries
        if not entries:
            empty_report: Dict[str, Any] = {
                "status": "no_queries_detected",
                "mean_score": 0.0,
                "pass_rate": 0.0,
                "total_work_items": 0,
                "total_cost_usd": 0.0,
                "injection_total": 0,
                "credential_total": 0,
                "lifecycle_total": 0,
                "parameterization_rate": 0.0,
                "false_positives_suppressed": 0,
                "by_database": {},
                "by_tier": {},
            }
            self._write_query_security_files(output_dir, run_id, empty_report)
            return empty_report

        # Aggregate by database
        qp_by_db: Dict[str, Any] = {}
        for entry in entries:
            db = entry.get("database", "unknown")
            bucket = qp_by_db.setdefault(
                db, {"count": 0, "mean_score": 0.0, "scores": []},
            )
            bucket["count"] += 1
            bucket["scores"].append(entry.get("score", 0.0))

        for db_data in qp_by_db.values():
            scores = db_data.pop("scores")
            db_data["mean_score"] = (
                round(sum(scores) / len(scores), 4) if scores else 0.0
            )

        injection_total = sum(
            e.get("finding_types", {}).get("injection", 0) for e in entries
        )
        credential_total = sum(
            e.get("finding_types", {}).get("credential_leakage", 0)
            for e in entries
        )
        lifecycle_total = sum(
            e.get("finding_types", {}).get("lifecycle", 0) for e in entries
        )
        all_scores = [e.get("score", 0.0) for e in entries]
        mean_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
        pass_count = sum(1 for s in all_scores if s >= 0.8)

        report: Dict[str, Any] = {
            "status": "pass" if injection_total == 0 else "fail",
            "mean_score": round(mean_score, 4),
            "pass_rate": (
                round(pass_count / len(all_scores), 4) if all_scores else 0.0
            ),
            "total_work_items": len(entries),
            "total_cost_usd": 0.0,
            "injection_total": injection_total,
            "credential_total": credential_total,
            "lifecycle_total": lifecycle_total,
            "parameterization_rate": (
                round(max(0.0, 1.0 - injection_total / len(entries)), 4)
                if entries else 0.0
            ),
            "false_positives_suppressed": 0,
            "by_database": qp_by_db,
            "by_tier": {},
        }

        self._write_query_security_files(output_dir, run_id, report)
        logger.info(
            "Anzen gate finalized: %d files, %d injections, %d credentials, "
            "score=%.2f (%d databases)",
            len(entries), injection_total, credential_total,
            mean_score, len(qp_by_db),
        )
        return report

    def _write_query_security_files(
        self, output_dir: str, run_id: str, report: Dict[str, Any],
    ) -> None:
        """Write query-security-metrics.json + update kaizen-metrics.json."""
        import datetime
        import json

        try:
            from startd8.security_prime.kaizen import update_query_security_metrics
            update_query_security_metrics(output_dir, report)
        except (ImportError, OSError) as exc:
            logger.debug("Query security metrics update skipped: %s", exc)

        qp_standalone = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "timestamp": datetime.datetime.now(
                datetime.timezone.utc,
            ).isoformat(),
            **report,
        }
        qp_path = Path(output_dir) / "query-security-metrics.json"
        try:
            qp_path.write_text(
                json.dumps(qp_standalone, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            logger.info("Wrote query-security-metrics.json to %s", qp_path)
        except OSError as exc:
            logger.debug(
                "Advisory: query-security-metrics.json write failed: %s", exc,
            )

    # ------------------------------------------------------------------
    # Phase D: Semantic validation (Kaizen Quality)
    # ------------------------------------------------------------------

    def _run_semantic_checks(
        self,
        integrated_files: List[Path],
        unit: IntegrationUnit,
    ) -> Dict[str, Any]:
        """Run semantic validation on integrated files via disk compliance.

        Uses ``validate_disk_compliance()`` (the full L1–L10 semantic check
        suite) rather than the limited ``semantic_checks.py`` module.  Issues
        are logged as warnings (non-blocking).  This runs after syntax repair
        but before final commit.

        Returns:
            Dict of per-file compliance data for files with issues
            (REQ-RFL-100).  Keys are paths relative to project_root.
        """
        compliance_results: Dict[str, Any] = {}
        try:
            from startd8.forward_manifest_validator import validate_disk_compliance
        except ImportError:
            return compliance_results

        project_root = str(self.project_root) if self.project_root else "."

        for fpath in integrated_files:
            if not fpath.is_file():
                continue
            if fpath.suffix == ".py":
                try:
                    compliance = validate_disk_compliance(str(fpath), project_root)
                    for issue in compliance.semantic_issues or []:
                        if not isinstance(issue, dict):
                            continue
                        logger.warning(
                            "Semantic issue: %s",
                            issue.get("message", str(issue)),
                            extra={"unit_id": unit.id},
                        )
                    # REQ-RFL-100: Persist compliance data for files with issues
                    if (not compliance.ast_valid
                            or compliance.stubs_remaining > 0
                            or compliance.duplicate_definitions > 0
                            or compliance.import_completeness < 1.0
                            or compliance.contract_compliance < 1.0
                            or compliance.semantic_issues):
                        try:
                            rel = str(fpath.relative_to(self.project_root))
                        except ValueError:
                            rel = str(fpath)
                        compliance_results[rel] = {
                            "ast_valid": compliance.ast_valid,
                            "stubs_remaining": compliance.stubs_remaining,
                            "duplicate_definitions": compliance.duplicate_definitions,
                            "import_completeness": compliance.import_completeness,
                            "contract_compliance": compliance.contract_compliance,
                            "semantic_issues": [
                                {"category": si.get("category", "unknown"),
                                 "severity": si.get("severity", "warning"),
                                 "message": str(si.get("message", ""))[:200]}
                                for si in (compliance.semantic_issues or [])
                                if isinstance(si, dict)
                            ],
                        }
                except Exception as exc:
                    logger.debug(
                        "Semantic check failed for %s: %s", fpath, exc,
                    )
            elif fpath.suffix in (".cs", ".csproj"):
                try:
                    from startd8.validators.csharp_semantic_checks import (
                        run_csharp_semantic_checks,
                    )
                    source = fpath.read_text(encoding="utf-8")
                    issues = run_csharp_semantic_checks(source, file_path=str(fpath))
                    # Deduplicate: suppress sql_injection_risk findings for files
                    # already processed by the Anzen gate (Query Prime is authoritative
                    # for injection detection — its two-pass approach handles
                    # parameterization suppression that csharp_semantic_checks misses).
                    anzen_files = getattr(self, "_anzen_gated_files", set())
                    if anzen_files and str(fpath) in anzen_files:
                        issues = [i for i in issues if i.check != "sql_injection_risk"]
                    for issue in issues:
                        logger.warning(
                            "C# semantic: %s",
                            issue.message,
                            extra={"unit_id": unit.id},
                        )
                    # REQ-KZ-CS-402c: Store C# results in compliance_results
                    # so _attempt_semantic_repair() can consume them.
                    if issues:
                        try:
                            rel = str(fpath.relative_to(self.project_root))
                        except ValueError:
                            rel = str(fpath)
                        compliance_results[rel] = {
                            "ast_valid": True,  # passed tree-sitter
                            "stubs_remaining": 0,
                            "duplicate_definitions": 0,
                            "import_completeness": 1.0,
                            "contract_compliance": 1.0,
                            "semantic_issues": [
                                {"category": si.check,
                                 "severity": si.severity,
                                 "message": str(si.message)[:200],
                                 "line": getattr(si, "line", 0)}
                                for si in issues
                            ],
                        }
                    # REQ-KZ-CS-502: Using directive coverage check
                    if fpath.suffix == ".cs":
                        try:
                            from startd8.languages.csharp_splicer import (
                                check_using_coverage,
                            )
                            # Find the nearest .csproj for this .cs file
                            _csproj = None
                            for _p in fpath.parent.iterdir():
                                if _p.suffix == ".csproj":
                                    _csproj = _p
                                    break
                            if _csproj is None:
                                for _p in fpath.parent.parent.iterdir():
                                    if _p.suffix == ".csproj":
                                        _csproj = _p
                                        break
                            if _csproj is not None:
                                _cov = check_using_coverage(
                                    source, _csproj.read_text(encoding="utf-8"),
                                )
                                for _ci in _cov:
                                    logger.warning(
                                        "C# using coverage: %s",
                                        _ci.get("message", str(_ci)),
                                        extra={"unit_id": unit.id},
                                    )
                        except Exception:
                            pass  # advisory — never block on using coverage
                except Exception as exc:
                    logger.debug(
                        "C# semantic check failed for %s: %s", fpath, exc,
                    )
            elif fpath.suffix == ".java":
                from startd8.validators.java_semantic_checks import (
                    run_java_semantic_checks,
                )
                self._collect_language_semantic_checks(
                    fpath, unit, compliance_results,
                    run_java_semantic_checks, "Java",
                )
            elif fpath.suffix == ".go":
                from startd8.validators.go_semantic_checks import (
                    run_go_semantic_checks,
                )
                self._collect_language_semantic_checks(
                    fpath, unit, compliance_results,
                    run_go_semantic_checks, "Go",
                )
            elif fpath.suffix in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"):
                from startd8.validators.nodejs_semantic_checks import (
                    run_nodejs_semantic_checks,
                )
                self._collect_language_semantic_checks(
                    fpath, unit, compliance_results,
                    run_nodejs_semantic_checks, "Node.js",
                )

        return compliance_results

    def _collect_language_semantic_checks(
        self,
        fpath: Path,
        unit: "IntegrationUnit",
        compliance_results: Dict[str, Any],
        check_fn: Any,
        language_label: str,
    ) -> None:
        """Run language-specific semantic checks and collect into compliance_results.

        Shared helper that eliminates per-language boilerplate (REQ-KZ-001).
        Each language branch imports its check function, then delegates here.
        """
        try:
            source = fpath.read_text(encoding="utf-8")
            issues = check_fn(source, file_path=str(fpath))
            for issue in issues:
                logger.warning(
                    "%s semantic: %s",
                    language_label,
                    issue.message,
                    extra={"unit_id": unit.id},
                )
            if issues:
                try:
                    rel = str(fpath.relative_to(self.project_root))
                except ValueError:
                    rel = str(fpath)
                compliance_results[rel] = {
                    "ast_valid": True,
                    "stubs_remaining": 0,
                    "duplicate_definitions": 0,
                    "import_completeness": 1.0,
                    "contract_compliance": 1.0,
                    "semantic_issues": [
                        {"category": si.check, "severity": si.severity,
                         "message": str(si.message)[:200],
                         "line": getattr(si, "line", 0)}
                        for si in issues
                    ],
                }
        except Exception as exc:
            logger.debug(
                "%s semantic check failed for %s: %s",
                language_label, fpath, exc,
            )

    def _attempt_semantic_repair(
        self,
        integrated_files: List[Path],
        unit: IntegrationUnit,
    ) -> Optional[Dict[str, Any]]:
        """Run semantic repair on integrated files (REQ-SR-100–400, REQ-KZ-CS-402).

        Delegates to ``run_semantic_repair()`` in the repair orchestrator.
        Active when ``semantic_repair_categories`` is non-empty OR when C#
        files are present (auto-enables sql_injection_risk repair).

        Returns:
            Semantic repair result dict (for postmortem dual scoring), or None.
        """
        if self._repair_config is None or not getattr(
            self._repair_config, "repair_enabled", False,
        ):
            return None

        repair_config = self._repair_config

        # Auto-enable language-specific semantic repair categories.
        # RepairConfig._DEFAULT_SEMANTIC_CATEGORIES_BY_LANGUAGE defines
        # which categories each language supports (e.g., Go: unchecked_error,
        # C#: sql_injection_risk).  Merge these into the config so the
        # orchestrator doesn't skip repair for languages with defaults.
        existing_categories = getattr(repair_config, "semantic_repair_categories", frozenset()) or frozenset()
        auto_categories = set(existing_categories)
        for f in integrated_files:
            ext = f.suffix.lower()
            try:
                from startd8.languages.registry import LanguageRegistry
                profile = LanguageRegistry.get_by_extension(ext)
                if profile is not None:
                    lang_defaults = repair_config.get_semantic_categories(profile.language_id)
                    auto_categories.update(lang_defaults)
            except (ImportError, AttributeError):
                pass
        if auto_categories != existing_categories:
            from startd8.repair.config import RepairConfig
            repair_config = RepairConfig(
                repair_enabled=repair_config.repair_enabled,
                repairable_categories=repair_config.repairable_categories,
                semantic_repair_categories=frozenset(auto_categories),
                max_semantic_repairs_per_file=repair_config.max_semantic_repairs_per_file,
                semantic_repair_circuit_breaker_threshold=repair_config.semantic_repair_circuit_breaker_threshold,
                per_step_timeout_s=repair_config.per_step_timeout_s,
                total_timeout_s=repair_config.total_timeout_s,
            )

        if not getattr(repair_config, "semantic_repair_categories", None):
            return None

        try:
            from startd8.repair.orchestrator import run_semantic_repair
        except ImportError:
            return None

        project_root = self.project_root or Path(".")
        result = run_semantic_repair(
            integrated_files, repair_config, project_root,
        )
        if result.get("issues_repaired", 0) > 0:
            logger.info(
                "Semantic repair complete: %d/%d issues repaired across %d files",
                result["issues_repaired"],
                result["issues_found"],
                len(result.get("per_file", {})),
            )
            # Post-repair semantic re-check moved to caller (REQ-RFL-100)
            # so compliance results can be captured in result metadata.

        return result

    # ------------------------------------------------------------------
    # Fix-2 / Gap-C: Post-integrate contract violation repair
    # ------------------------------------------------------------------

    def _attempt_contract_violation_repair(
        self,
        integrated_files: List[Path],
        unit: IntegrationUnit,
        result_obj_metadata: Dict[str, Any],
    ) -> bool:
        """Validate integrated files against forward manifest and repair violations.

        Builds a ManifestRegistry from the integrated Python files, runs
        ``validate_forward_manifest()`` against the stored forward manifest,
        and routes any ERROR-severity violations through the repair pipeline.

        Returns:
            True if any files were repaired, False otherwise.
        """
        if not _HAS_REPAIR or self._forward_manifest is None:
            return False

        try:
            from ..forward_manifest_validator import validate_forward_manifest
            from ..repair.models import ContractViolationDiagnostic, RepairContext
            from ..utils.code_manifest import generate_file_manifest

            # Build ManifestRegistry from integrated Python files
            manifest_registry: dict = {}
            for fpath in integrated_files:
                if not fpath.suffix == ".py" or not fpath.exists():
                    continue
                try:
                    fm = generate_file_manifest(fpath, self.project_root)
                    rel = str(fpath.relative_to(self.project_root)) if fpath.is_absolute() else str(fpath)
                    manifest_registry[rel] = fm
                except Exception:
                    continue

            if not manifest_registry:
                return False

            # Validate against forward manifest
            violations = validate_forward_manifest(
                self._forward_manifest, manifest_registry,
            )

            # Filter to ERROR severity only
            error_violations = [
                v for v in violations
                if getattr(v, "severity", "error") == "error"
            ]
            if not error_violations:
                return False

            logger.info(
                "Found %d contract violation(s) for %s, attempting repair",
                len(error_violations), unit.name,
                extra={"unit_id": unit.id},
            )

            # REQ-MSR-220: Persist contract violation diagnostics
            result_obj_metadata["contract_violation_details"] = [
                {
                    "expected": str(getattr(v, "expected", ""))[:200],
                    "actual": str(getattr(v, "actual", ""))[:200],
                    "severity": getattr(v, "severity", "error"),
                    "violation_type": str(getattr(v, "violation_type", ""))[:100],
                    "repaired": False,  # Updated after repair
                }
                for v in error_violations[:20]
            ]

            # Convert ContractViolation → ContractViolationDiagnostic
            diagnostics: list = []
            for v in error_violations:
                # Extract element name from contract_id pattern "file_element:path:name"
                element_name = ""
                if hasattr(v, "contract_id") and v.contract_id:
                    parts = v.contract_id.split(":")
                    if len(parts) >= 3:
                        element_name = parts[-1]

                diagnostics.append(ContractViolationDiagnostic(
                    category="contract_violation",
                    file=v.file_path if hasattr(v, "file_path") else "",
                    message=f"{v.violation_type}: expected {v.expected}, got {v.actual}",
                    violation_type=v.violation_type,
                    expected=str(v.expected),
                    actual=str(v.actual),
                    element_name=element_name,
                ))

            # Collect file contents for repair
            files_to_repair: dict = {}
            for diag in diagnostics:
                ifile = Path(diag.file)
                if not ifile.is_absolute():
                    ifile = self.project_root / ifile
                if ifile.exists() and ifile not in files_to_repair:
                    files_to_repair[ifile] = ifile.read_text(encoding="utf-8")

            if not files_to_repair:
                return False

            outcome = run_file_repair(
                files_to_repair,
                diagnostics,
                self._repair_config,
                self.project_root,
                forward_manifest=self._forward_manifest,
            )

            if outcome.any_modified:
                for fpath, content in outcome.repaired_files.items():
                    fpath.write_text(content, encoding="utf-8")

                # Gap-C: Update element registry for contract-violation-repaired files
                if self._element_registry is not None:
                    for fpath in outcome.repaired_files:
                        rel = str(fpath.relative_to(self.project_root)) if fpath.is_absolute() else str(fpath)
                        for entry in self._element_registry.elements_for_file(rel):
                            self._element_registry.set_phase_status(
                                entry.element_id, "integrate", "repaired",
                                metadata={"repair_stage": "contract_violation"},
                            )

                result_obj_metadata["contract_repair_applied"] = True
                result_obj_metadata["contract_violations_found"] = len(error_violations)
                result_obj_metadata["contract_files_repaired"] = [
                    str(p) for p in outcome.repaired_files
                ]
                # REQ-MSR-220: Mark violations as repaired
                for entry in result_obj_metadata.get("contract_violation_details", []):
                    entry["repaired"] = True
                logger.info(
                    "Contract violation repair applied to %d file(s) for %s",
                    len(outcome.repaired_files), unit.name,
                    extra={"unit_id": unit.id},
                )
                return True

        except Exception as exc:
            logger.warning(
                "Post-integrate contract validation failed for %s: %s",
                unit.name, exc,
                extra={"unit_id": unit.id},
            )

        return False

    # ------------------------------------------------------------------
    # REQ-RPL-301: Size Regression Merge Repair
    # ------------------------------------------------------------------

    def _merge_subset_into_target(
        self,
        generated: str,
        target: str,
    ) -> Optional[str]:
        """Attempt to merge generated content into target when generated is a subset.

        Uses ``difflib.SequenceMatcher`` to determine whether the generated
        file is a *subset* of the target (missing sections but not wrong
        sections).  When the generated content only adds new lines that
        don't contradict existing target lines, those additions are spliced
        into the target at the appropriate positions.

        Returns:
            Merged content string on success, or ``None`` if a
            contradiction is detected (generated deletes/replaces target
            lines), or if either input is empty.
        """
        if not target:
            return None

        import difflib

        gen_lines = generated.splitlines(keepends=True)
        tgt_lines = target.splitlines(keepends=True)

        sm = difflib.SequenceMatcher(None, tgt_lines, gen_lines, autojunk=False)

        merged: list[str] = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace":
                return None
            elif tag in ("equal", "delete"):
                merged.extend(tgt_lines[i1:i2])
            elif tag == "insert":
                merged.extend(gen_lines[j1:j2])

        return "".join(merged)

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
        skipped_files: List[Dict[str, Any]] = []
        result_obj_metadata: Dict[str, Any] = {}

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

        # 2.5. Post-generation cleanup (P2: goimports for Go, etc.)
        if not self.dry_run and self._language_profile is not None:
            all_gen_paths = []
            for f in unit.generated_files:
                p = Path(f)
                if not p.is_absolute():
                    p = p.resolve()
                if p.exists():
                    all_gen_paths.append(p)
            if all_gen_paths:
                try:
                    cleanup_warnings = self._language_profile.post_generation_cleanup(
                        all_gen_paths, self.project_root,
                    )
                    for w in cleanup_warnings:
                        logger.warning("Post-gen cleanup: %s", w)
                        warnings.append(w)
                    # REQ-MSR-330: Persist language-specific warnings
                    if cleanup_warnings:
                        _lang_id = getattr(self._language_profile, "language_id", "unknown")
                        result_obj_metadata.setdefault(
                            "language_warnings", [],
                        ).extend([
                            {"language": _lang_id, "category": "post_gen_cleanup",
                             "message": str(w)[:200]}
                            for w in cleanup_warnings[:20]
                        ])
                except Exception as exc:
                    logger.warning("Post-gen cleanup failed: %s", exc)

        # 3. Pre-validate generated source files
        if not self.dry_run and self.checkpoint is not None:
            gen_paths = []
            source_exts = {".py"}
            if self._language_profile is not None:
                source_exts = set(self._language_profile.source_extensions)
            for f in unit.generated_files:
                p = Path(f)
                if not p.is_absolute():
                    p = p.resolve()
                if p.exists() and p.suffix in source_exts:
                    gen_paths.append(p)
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
                    # Attempt pre-merge repair before giving up
                    repaired_result = self._attempt_pre_merge_repair(
                        gen_paths, unit,
                    )
                    if repaired_result is not None:
                        pre_result = repaired_result
                        # REQ-RFL-105: Record pre-merge repair in metadata
                        result_obj_metadata.setdefault(
                            "repair_summaries", [],
                        ).append({
                            "phase": "pre_merge",
                            "any_modified": True,
                            "repair_succeeded": (
                                pre_result.status != CheckpointStatus.FAILED
                            ),
                        })

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
            if not source_path.is_absolute():
                source_path = source_path.resolve()

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
                    target_path = self._derive_target_from_source(source_path, unit)
                else:
                    logger.error(
                        "Source file not found: %s", source_path,
                        extra={"unit_id": unit.id},
                    )
                    continue
            else:
                target_path = self._derive_target_from_source(source_path, unit)

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

            # REQ-MLT-102: Python-stub cross-language guard
            try:
                _source_text = source_path.read_text(encoding="utf-8")
                _stub_error = _detect_python_stub_in_non_python(
                    _source_text, str(target_path),
                )
                if _stub_error is not None:
                    logger.warning(
                        "Python stub detected in non-Python target %s: %s",
                        target_path, _stub_error,
                        extra={"unit_id": unit.id},
                    )
                    skipped_files.append({
                        "path": str(source_path),
                        "reason": "python_stub_in_non_python",
                        "detail": _stub_error,
                    })
                    continue
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning(
                    "Cross-language guard read failed for %s: %s — proceeding",
                    source_path.name, exc,
                    extra={"unit_id": unit.id},
                )

            # Truncation detection
            if self.check_truncation:
                from ..truncation_detection import (
                    CONFIDENCE_HIGH,
                    CONFIDENCE_HIGH_PROSE,
                    CONFIDENCE_IS_TRUNCATED,
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
                    target_exists = target_path.is_file()
                    if target_exists:
                        # AR-819: stricter threshold when overwriting existing code
                        reject_threshold = CONFIDENCE_IS_TRUNCATED  # 0.5
                    else:
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

            # PCA-604: Path traversal protection — ensure target is within project root
            try:
                canonical_target = target_path.resolve()
                canonical_root = self.project_root.resolve()
                if (
                    canonical_target != canonical_root
                    and not str(canonical_target).startswith(str(canonical_root) + os.sep)
                ):
                    msg = (
                        f"Path traversal blocked: {target_path} resolves to "
                        f"{canonical_target} outside project root {canonical_root}"
                    )
                    logger.error(msg, extra={"unit_id": unit.id})
                    warnings.append(msg)
                    continue
                if target_path.is_symlink():
                    link_target = target_path.resolve()
                    if not str(link_target).startswith(str(canonical_root) + os.sep):
                        msg = (
                            f"Symlink traversal blocked: {target_path} -> "
                            f"{link_target} outside project root"
                        )
                        logger.error(msg, extra={"unit_id": unit.id})
                        warnings.append(msg)
                        continue
            except (OSError, ValueError) as exc:
                logger.warning(
                    "Path resolution failed for %s: %s", target_path, exc,
                    extra={"unit_id": unit.id},
                )

            # AR-823: Import validation against module inventory
            _unit_ctx = unit.context if hasattr(unit, "context") else {}
            _module_inventory = (
                _unit_ctx.get("module_inventory", []) if isinstance(_unit_ctx, dict) else []
            )
            if source_path.suffix == ".py" and _module_inventory:
                unresolved = self._validate_imports(source_path, _module_inventory)
                if unresolved:
                    msg = (
                        f"Import validation failed for {source_path.name}: "
                        f"unresolved first-party imports: {', '.join(unresolved)}"
                    )
                    logger.error(msg, extra={"unit_id": unit.id})
                    warnings.append(msg)
                    skipped_files.append({
                        "path": str(source_path),
                        "reason": "unresolved_imports",
                        "unresolved": unresolved,
                    })
                    continue

            # PCA-604: Size regression guard — block overwrites that would lose significant code.
            # Pipeline-poisoning guard: skip when the target file is manifest-covered —
            # the existing content is from a prior run (possibly a different generation
            # strategy), not a meaningful regression baseline for skeleton-based generation.
            _manifest_covers_target = False
            if self._forward_manifest is not None:
                try:
                    _fm_specs = self._forward_manifest.file_specs or {}
                    # Use relative path for manifest lookup — target_path is
                    # absolute but manifest keys are relative (e.g. "src/foo.py").
                    _rel = str(target_path.relative_to(self.project_root))
                    _manifest_covers_target = _rel in _fm_specs
                except (AttributeError, TypeError):
                    pass
            if target_path.is_file() and source_path.exists() and not _manifest_covers_target:
                try:
                    target_content = target_path.read_text(encoding="utf-8")
                    target_lines = len(target_content.splitlines())
                    source_content_text = source_path.read_text(encoding="utf-8")
                    source_lines = len(source_content_text.splitlines())

                    ctx = unit.context or {}
                    allow_override = ctx.get("allow_size_regression", False)
                    file_manifest = ctx.get("file_manifest", {})
                    file_override = file_manifest.get(
                        str(source_path), {},
                    ).get("size_regression_override", False)
                    if not allow_override and file_override:
                        allow_override = True
                    override_source = (
                        "cli_flag" if ctx.get("allow_size_regression")
                        else "plan_annotation" if file_override
                        else None
                    )

                    # AR-818: Stricter threshold when truncation is also detected
                    _task_trunc_conf = 0.0
                    _tf = ctx.get("_truncation_flags", {})
                    if isinstance(_tf, dict):
                        _task_trunc_conf = _tf.get("max_confidence", 0.0)

                    from ..truncation_detection import CONFIDENCE_IS_TRUNCATED as _CIT
                    effective_threshold = self._size_regression_threshold  # 0.60
                    if _task_trunc_conf >= _CIT:  # 0.5
                        effective_threshold = 0.70  # AR-818: stricter when truncation detected

                    if (
                        target_lines > self._min_lines
                        and source_lines / target_lines < effective_threshold
                    ):
                        ratio = source_lines / target_lines
                        if allow_override:
                            logger.warning(
                                "Size regression override: %s (%d/%d lines, %.0f%% of original)"
                                " — override source: %s",
                                source_path.name, source_lines, target_lines,
                                ratio * 100, override_source,
                                extra={"unit_id": unit.id},
                            )
                            result_obj_metadata.setdefault(
                                "size_regression_overrides", [],
                            ).append({
                                "path": str(source_path),
                                "source_lines": source_lines,
                                "target_lines": target_lines,
                                "ratio": ratio,
                                "override_source": override_source,
                            })
                        else:
                            # REQ-RPL-301: Attempt merge-based repair for
                            # size regressions when repair is enabled.
                            _merge_repaired = False
                            if (
                                self._repair_config is not None
                                and getattr(
                                    self._repair_config,
                                    "repair_enabled",
                                    False,
                                )
                            ):
                                try:
                                    merged = self._merge_subset_into_target(
                                        source_content_text, target_content,
                                    )
                                    if merged is not None:
                                        target_path.write_text(
                                            merged, encoding="utf-8",
                                        )
                                        result_obj_metadata.setdefault(
                                            "merge_repair_advisory", [],
                                        ).append({
                                            "file": str(target_path),
                                            "action": "merged_subset",
                                            "confidence": "LOW",
                                            "requires_review": True,
                                            "source_lines": source_lines,
                                            "target_lines": target_lines,
                                            "ratio": ratio,
                                        })
                                        logger.info(
                                            "Size regression merge repair: "
                                            "%s (%d/%d lines merged into "
                                            "target)",
                                            source_path.name,
                                            source_lines, target_lines,
                                            extra={"unit_id": unit.id},
                                        )
                                        _merge_repaired = True
                                except (OSError, UnicodeDecodeError, TypeError) as _merge_exc:
                                    logger.warning(
                                        "Size regression merge repair "
                                        "failed for %s: %s — falling "
                                        "back to block",
                                        source_path.name, _merge_exc,
                                        extra={"unit_id": unit.id},
                                    )

                            if _merge_repaired:
                                integrated_files.append(target_path)
                                listener.on_file_integrated(
                                    unit, source_path, target_path,
                                )
                            else:
                                msg = (
                                    f"Size regression blocked: {source_path.name} has "
                                    f"{source_lines} lines but target has {target_lines} "
                                    f"lines ({ratio:.0%} < "
                                    f"{effective_threshold:.0%} threshold). "
                                    f"Use --force-rewrite to override."
                                )
                                logger.error(msg, extra={"unit_id": unit.id})
                                warnings.append(msg)
                                skipped_files.append({
                                    "path": str(source_path),
                                    "reason": "size_regression",
                                    "source_lines": source_lines,
                                    "target_lines": target_lines,
                                    "ratio": ratio,
                                })
                            continue
                except (OSError, UnicodeDecodeError) as exc:
                    logger.warning(
                        "Size regression check failed for %s: %s — proceeding",
                        source_path.name, exc,
                        extra={"unit_id": unit.id},
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

            # Merge — skip merge strategy for edit-mode tasks where the
            # staging file IS the complete file (search/replace applied).
            # The merge strategy's duplicate-class deduplication destroys
            # content when source and target share the same classes.
            _unit_ctx = unit.context if hasattr(unit, "context") else {}
            _edit_mode = _unit_ctx.get("_edit_mode")
            _skip_merge = (
                isinstance(_edit_mode, dict)
                and _edit_mode.get("mode") == "edit"
            )
            if _skip_merge:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                logger.info(
                    "Copied (edit mode — merge skipped): %s",
                    self._rel_display(target_path),
                    extra={"unit_id": unit.id},
                )
                integrated_files.append(target_path)
            elif self.merge_strategy.can_merge(source_path, target_path):
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
                    # REQ-MSR-100: Persist merge conflict details
                    result_obj_metadata.setdefault(
                        "merge_conflicts", [],
                    ).append({
                        "file": self._rel_display(target_path),
                        "conflicts": result.conflicts[:5],
                    })
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
            status = (
                IntegrationStatus.BLOCKED if skipped_files
                else IntegrationStatus.FAILED
            )
            return IntegrationResult(
                success=False,
                errors=errors,
                warnings=warnings,
                skipped_files=skipped_files,
                metadata=result_obj_metadata,
                status=status,
            )

        # 6. Post-merge: language-aware cleanup + auto-fix lint + run checkpoints
        if not self.dry_run and self.checkpoint is not None:
            # P2: Run language-specific post-merge cleanup (goimports, etc.)
            if self._language_profile is not None:
                try:
                    post_merge_warnings = self._language_profile.post_generation_cleanup(
                        integrated_files, self.project_root,
                    )
                    for w in post_merge_warnings:
                        warnings.append(w)
                except Exception as exc:
                    logger.warning("Post-merge cleanup failed: %s", exc)

            # Auto-fix trivially-fixable lint issues before running checkpoints
            # (Python-specific: ruff auto-fix)
            _is_python = (
                self._language_profile is None
                or self._language_profile.language_id == "python"
            )
            if _is_python:
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

            # ── Repair pipeline hook (REQ-RPL-200, R6-S1, R6-S2) ──
            results, repair_success = self._attempt_repair(
                results, integrated_files, unit, attempt, result_obj_metadata,
            )

            # ── Contract violation repair (Fix-2) ──
            self._attempt_contract_violation_repair(
                integrated_files, unit, result_obj_metadata,
            )

            # ── Semantic checks (Phase D — Kaizen Quality) ──
            compliance_results = self._run_semantic_checks(integrated_files, unit)

            # ── Semantic repair (Phase D+ — REQ-SR-100–400) ──
            sem_repair = self._attempt_semantic_repair(integrated_files, unit)
            if sem_repair is not None:
                result_obj_metadata["semantic_repair"] = sem_repair
                # Re-capture compliance after repair to reflect final state
                if sem_repair.get("issues_repaired", 0) > 0:
                    compliance_results = self._run_semantic_checks(
                        integrated_files, unit,
                    )

            # REQ-RFL-100: Persist disk compliance for downstream consumers
            if compliance_results:
                result_obj_metadata["disk_compliance"] = compliance_results

                # REQ-RFL-115: Compute disk quality score (min = weakest link)
                try:
                    from types import SimpleNamespace
                    from startd8.forward_manifest_validator import (
                        compute_disk_quality_score,
                    )
                    scores = [
                        compute_disk_quality_score(SimpleNamespace(**d))
                        for d in compliance_results.values()
                    ]
                    if scores:
                        result_obj_metadata["disk_quality_score"] = min(scores)
                except Exception:
                    logger.debug(
                        "Disk quality score computation failed",
                        exc_info=True,
                    )

            # ── Anzen gate (SP-GT-001–004) — security verification ──
            # Runs AFTER semantic repair (evaluates repaired code) and
            # BEFORE advisory downgrade (security findings are never advisory).
            self._run_anzen_gate(integrated_files, unit, result_obj_metadata)

            # Advisory downgrade (only if repair not attempted or failed)
            # R6-S1: When repair succeeds, skip downgrade — results are
            # already replaced with passing re-checkpoint results
            if not repair_success:
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

            # R2-S8: GateEmitter AFTER repair decision — emits final results
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
            # REQ-MSR-120: Persist checkpoint details for postmortem analysis
            _cp_details = []
            for _cr in results:
                _cp_entry = {
                    "check_name": getattr(_cr, "name", "unknown"),
                    "passed": getattr(_cr, "status", None) != CheckpointStatus.FAILED,
                }
                _msg = getattr(_cr, "message", None)
                if _msg:
                    _cp_entry["message"] = str(_msg)[:500]
                _errs = getattr(_cr, "errors", None)
                if _errs:
                    _cp_entry["diagnostics"] = [str(e)[:200] for e in _errs[:5]]
                _cp_details.append(_cp_entry)
            if _cp_details:
                result_obj_metadata["checkpoint_details"] = _cp_details

            all_passed = (
                True if repair_success
                else self.checkpoint.summarize_results(results)
            )

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
                    skipped_files=skipped_files,
                    metadata=result_obj_metadata,
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

        # PCA-604: Partial integration warning — when some files were
        # blocked by size regression but others succeeded.
        if skipped_files and integrated_files:
            partial_msg = (
                f"Partial integration for unit {unit.name}: "
                f"{len(integrated_files)} files integrated, "
                f"{len(skipped_files)} files blocked by size regression guard. "
                f"Project may be in an inconsistent state."
            )
            logger.warning(partial_msg, extra={"unit_id": unit.id})
            warnings.append(partial_msg)

        # Determine final status
        if skipped_files:
            final_status = (
                IntegrationStatus.PARTIAL if integrated_files
                else IntegrationStatus.BLOCKED
            )
        else:
            final_status = IntegrationStatus.SUCCESS

        # 8b. Element registry provenance (ER-008) — record merge outcomes
        if self._element_registry is not None:
            self._record_element_merge_outcomes(
                unit, integrated_files, skipped_files,
            )

        # REQ-MSR-310: Export element registry repair summary
        if self._element_registry is not None:
            try:
                all_elements = list(self._element_registry._elements.values()) if hasattr(self._element_registry, "_elements") else []
                repaired = [e for e in all_elements if isinstance(e, dict) and e.get("phase_status", {}).get("integrate") == "repaired"]
                if repaired:
                    repair_by_type: Dict[str, int] = {}
                    for e in repaired:
                        t = e.get("element_type", "unknown")
                        repair_by_type[t] = repair_by_type.get(t, 0) + 1
                    result_obj_metadata["element_repair_summary"] = {
                        "total_elements": len(all_elements),
                        "repaired": len(repaired),
                        "repair_by_type": repair_by_type,
                    }
            except Exception:
                pass  # advisory — never block integration

        # REQ-MSR-300: Persist skipped files in metadata for postmortem
        if skipped_files:
            result_obj_metadata["skipped_files"] = skipped_files

        # 9. Notify completed
        listener.on_integration_completed(unit, integrated_files)
        logger.info(
            "'%s' integrated successfully", unit.name,
            extra={"unit_id": unit.id, "files_count": len(integrated_files)},
        )

        return IntegrationResult(
            success=not skipped_files,
            integrated_files=integrated_files,
            errors=errors,
            warnings=warnings,
            checkpoint_results=checkpoint_results,
            skipped_files=skipped_files,
            metadata=result_obj_metadata,
            status=final_status,
        )
