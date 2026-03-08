"""SCAFFOLD phase handler."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from startd8.contractors.artisan_contractor import AbstractPhaseHandler, WorkflowPhase
from startd8.contractors.context_schema import ScaffoldPhaseOutput
from startd8.contractors.context_seed.shared import (
    SeedTask,
    _ensure_context_loaded,
    _log_context_completeness,
)
from startd8.logging_config import get_logger

logger = get_logger("startd8.contractors.context_seed_handlers")

# FR-MPA-008: Pre-assembly OTel metrics (optional dependency)
try:
    from opentelemetry import metrics as _otel_metrics
    _mpa_meter = _otel_metrics.get_meter("startd8.mottainai")
    _mpa_skeleton_forwarded = _mpa_meter.create_counter(
        "mottainai.skeleton_sources_forwarded",
        description="Skeletons consumed from seed (vs. recomputed)",
    )
except ImportError:
    _mpa_skeleton_forwarded = None


def _check_stub_drift(
    emit_manifest: list[dict[str, Any]],
    scaffold_metadata: list,
) -> None:
    """Log-only drift detection: compare EMIT-time vs SCAFFOLD-time SHA-256 hashes.

    If the ForwardManifest changed between EMIT and SCAFFOLD (e.g., manual edit
    to the seed), the hashes will differ. This is advisory — no error is raised.
    """
    emit_by_path = {e["file_path"]: e["sha256"] for e in emit_manifest if "sha256" in e}
    for entry in scaffold_metadata:
        path = entry.file_path if hasattr(entry, "file_path") else entry.get("file_path", "")
        sha = entry.sha256 if hasattr(entry, "sha256") else entry.get("sha256", "")
        if path in emit_by_path and sha and emit_by_path[path] != sha:
            logger.warning(
                "SCAFFOLD: stub drift detected for %s — "
                "EMIT sha256=%s, SCAFFOLD sha256=%s",
                path, emit_by_path[path][:12], sha[:12],
            )


class ScaffoldPhaseHandler(AbstractPhaseHandler):
    """SCAFFOLD phase: Verify target directories, check dependencies.

    Creates missing directories and validates the project environment.
    """

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("SCAFFOLD", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        project_root = Path(context.get("project_root", "."))

        logger.info("SCAFFOLD phase: checking %d tasks against %s", len(tasks), project_root)

        dirs_needed: set[str] = set()
        dirs_exist: set[str] = set()
        dirs_created: set[str] = set()
        files_existing: list[str] = []

        skipped_targets: list[str] = []

        for task in tasks:
            for target in task.target_files:
                target_path = project_root / target
                parent = target_path.parent

                # Guard: skip targets whose resolved parent falls outside
                # project_root (e.g. absolute paths in target_files).
                try:
                    parent_rel = str(parent.relative_to(project_root))
                except ValueError:
                    logger.warning(
                        "SCAFFOLD: target %r resolves outside project root, skipping",
                        target,
                    )
                    skipped_targets.append(target)
                    continue

                dirs_needed.add(parent_rel)

                if parent.exists():
                    dirs_exist.add(parent_rel)
                elif not dry_run:
                    try:
                        parent.mkdir(parents=True, exist_ok=True)
                        dirs_created.add(parent_rel)
                        logger.info("Created directory: %s", parent)
                    except OSError as exc:
                        logger.warning(
                            "SCAFFOLD: could not create directory %s: %s",
                            parent, exc,
                        )

                if target_path.exists():
                    files_existing.append(target)

        # Task 8: Staleness classification for existing target files
        staleness: dict[str, str] = {}  # path -> "current" | "stale" | "unknown"
        if files_existing:
            # Use seed mtime as staleness reference
            seed_path = context.get("enriched_seed_path")
            seed_mtime: float | None = None
            if seed_path:
                try:
                    seed_mtime = Path(str(seed_path)).stat().st_mtime
                except OSError as exc:
                    logger.debug("SCAFFOLD: could not stat seed path %s: %s", seed_path, exc)

            for target in files_existing:
                target_path = project_root / target
                try:
                    file_mtime = target_path.stat().st_mtime
                except OSError:
                    staleness[target] = "unknown"
                    continue

                if seed_mtime is not None:
                    if file_mtime >= seed_mtime:
                        staleness[target] = "current"
                    else:
                        staleness[target] = "stale"
                else:
                    staleness[target] = "unknown"

            stale_count = sum(1 for v in staleness.values() if v == "stale")
            if stale_count > 0:
                logger.warning(
                    "SCAFFOLD: %d/%d existing target file(s) are stale (older than seed)",
                    stale_count, len(files_existing),
                )

        dirs_missing = dirs_needed - dirs_exist - dirs_created

        # Fix 5b: soft-validate target file extensions against output_conventions
        output_conventions = context.get("output_conventions", {})
        extension_warnings: list[str] = []
        if output_conventions:
            for task in tasks:
                for atype in task.artifact_types_addressed:
                    expected_ext = output_conventions.get(atype, {}).get("output_ext")
                    if expected_ext:
                        for tf in task.target_files:
                            if not tf.endswith(expected_ext):
                                msg = (
                                    f"task {task.task_id} file {tf} doesn't match "
                                    f"expected extension {expected_ext} for {atype}"
                                )
                                extension_warnings.append(msg)
                                logger.warning("SCAFFOLD: %s", msg)

        # AR-821: Collect importable Python module inventory
        module_inventory = ScaffoldPhaseHandler._collect_module_inventory(project_root)
        if module_inventory:
            logger.info("SCAFFOLD: discovered %d importable packages", len(module_inventory))

        # Mottainai: deterministic file assembly — materialize skeleton stubs
        file_stubs: list = []
        file_stubs_created = file_stubs_skipped = file_stubs_failed = 0
        assembly_degraded = False
        render_specs: dict[str, str] = {}  # populated by DFA or pre-rendered

        try:
            forward_manifest = context.get("forward_manifest")
            if (
                forward_manifest is not None
                and hasattr(forward_manifest, "file_specs")
                and forward_manifest.file_specs
                and not dry_run
            ):
                from startd8.utils.file_assembler import DeterministicFileAssembler

                assembler = DeterministicFileAssembler(
                    module_inventory=module_inventory,
                )

                # FR-MPA-004: Consume pre-rendered skeleton_sources from EMIT
                # instead of re-running render_specs() (Mottainai: don't
                # discard artifacts already produced by earlier phases).
                seed_artifacts = context.get("artifacts") or {}
                pre_rendered = seed_artifacts.get("skeleton_sources")

                if pre_rendered:
                    # Use EMIT-phase skeletons directly
                    render_specs = dict(pre_rendered)
                    logger.info(
                        "SCAFFOLD: reusing %d pre-rendered skeleton(s) from EMIT phase",
                        len(render_specs),
                    )
                    # FR-MPA-008: Emit metric for skeleton reuse
                    if _mpa_skeleton_forwarded is not None:
                        _mpa_skeleton_forwarded.add(
                            len(render_specs), {"phase": "scaffold"},
                        )
                else:
                    # Fallback: re-render if seed lacks skeleton_sources
                    # (backward compat with seeds produced before FR-MPA-001)
                    render_result = assembler.render_specs(forward_manifest)
                    render_specs = dict(render_result.specs) if render_result.specs else {}
                    file_stubs.extend(
                        r.model_dump() for r in render_result.failures
                    )
                    logger.info(
                        "SCAFFOLD: no pre-rendered skeletons in seed — "
                        "fell back to render_specs() (%d files)",
                        len(render_specs),
                    )

                    # Validate against seed manifest for drift detection
                    stub_manifest = seed_artifacts.get("stub_manifest")
                    if stub_manifest and render_result.metadata:
                        _check_stub_drift(stub_manifest, render_result.metadata)

                # Materialize validated specs to disk
                if render_specs:
                    mat_results = assembler.materialize(
                        render_specs, project_root, dry_run=False,
                    )
                    file_stubs.extend(r.model_dump() for r in mat_results)

                # Telemetry counters
                for stub_dict in file_stubs:
                    status = stub_dict.get("status", "")
                    if status == "created":
                        file_stubs_created += 1
                    elif status == "skipped_exists":
                        file_stubs_skipped += 1
                    elif status == "syntax_error":
                        file_stubs_failed += 1

                logger.info(
                    "SCAFFOLD: file assembly complete — created=%d skipped=%d failed=%d",
                    file_stubs_created, file_stubs_skipped, file_stubs_failed,
                )
        except (OSError, ValueError, ImportError) as exc:
            logger.warning(
                "SCAFFOLD: deterministic file assembly failed — degrading gracefully: %s",
                exc,
                exc_info=True,
            )
            assembly_degraded = True

        # FR-MPA-004/007: Bridge skeleton sources into context["skeletons"]
        # so the IMPLEMENT Micro Prime pre-pass can consume them without
        # re-generating from scratch.
        if not assembly_degraded and render_specs:
            existing_skeletons = context.get("skeletons", {})
            existing_skeletons.update(render_specs)
            context["skeletons"] = existing_skeletons
            logger.info(
                "SCAFFOLD: populated context['skeletons'] with %d file(s)",
                len(render_specs),
            )

        output = {
            "directories_needed": sorted(dirs_needed),
            "directories_exist": sorted(dirs_exist),
            "directories_created": sorted(dirs_created),
            "directories_missing": sorted(dirs_missing) if dry_run else [],
            "existing_target_files": files_existing,
            "staleness_classification": staleness,
            "skipped_targets": skipped_targets,
            "project_root": str(project_root),
            "extension_warnings": extension_warnings,
            "module_inventory": module_inventory,
            "file_stubs": file_stubs,
            "file_stubs_created": file_stubs_created,
            "file_stubs_skipped": file_stubs_skipped,
            "file_stubs_failed": file_stubs_failed,
            "assembly_degraded": assembly_degraded,
        }

        # Store scaffold results in context
        context["scaffold"] = output

        # Context contract: validate SCAFFOLD output model
        ScaffoldPhaseOutput(
            scaffold=context["scaffold"],
            module_inventory=module_inventory,
            file_stubs=file_stubs,
            file_stubs_created=file_stubs_created,
            file_stubs_skipped=file_stubs_skipped,
            file_stubs_failed=file_stubs_failed,
            assembly_degraded=assembly_degraded,
        )

        duration = time.monotonic() - start
        logger.info(
            "SCAFFOLD phase complete: %d dirs needed, %d exist, %d created, %d existing files (%.2fs)",
            len(dirs_needed), len(dirs_exist), len(dirs_created), len(files_existing), duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}

    @staticmethod
    def _collect_module_inventory(project_root: Path) -> list[str]:
        """AR-821: Collect importable Python module names under project_root.

        Walks src/ (or project_root if no src/) for directories
        containing __init__.py. Returns dotted module paths.
        """
        src_dir = project_root / "src"
        search_root = src_dir if src_dir.is_dir() else project_root
        modules: list[str] = []
        try:
            for init_file in search_root.rglob("__init__.py"):
                pkg_dir = init_file.parent
                try:
                    rel = pkg_dir.relative_to(search_root)
                    dotted = ".".join(rel.parts)
                    if dotted:
                        modules.append(dotted)
                except ValueError:
                    continue
        except OSError as exc:
            logger.warning("SCAFFOLD: module inventory walk failed: %s", exc)
        return sorted(set(modules))
