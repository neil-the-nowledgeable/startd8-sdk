"""INTEGRATE phase handler."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)
from startd8.contractors.context_seed.shared import (
    _ensure_context_loaded,
    _log_context_completeness,
)
from startd8.contractors.protocols import GenerationResult
from startd8.contractors.context_seed.handler_support import (
    ArtisanIntegrationListener,
    HandlerConfig,
    OTelIntegrationListener,
    SeedTaskUnit,
    _build_provenance_links,
    _capture_task_span_context,
    _log_task_boundary_complete,
    _log_task_boundary_start,
)
from startd8.contractors.context_seed.tracing import _phase_tracer
from startd8.logging_config import get_logger

logger = get_logger("startd8.contractors.context_seed_handlers")


class IntegratePhaseHandler(AbstractPhaseHandler):
    """INTEGRATE phase: merge staged files into project_root with validation.

    Reads ``generation_results`` from context (populated by IMPLEMENT),
    runs each task through IntegrationEngine, and writes
    ``integration_results`` back to context.

    Files are merged from ``_staging_dir`` (or ``.startd8/staging/``)
    into the project root.  Auto-commit (if enabled) happens here,
    not in IMPLEMENT.
    """

    def __init__(self, config: Optional[HandlerConfig] = None) -> None:
        self.config = config or HandlerConfig()

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        import shutil as _shutil
        from startd8.contractors.checkpoint import IntegrationCheckpoint
        from startd8.contractors.integration_engine import IntegrationEngine
        from startd8.contractors.registry import get_registry

        start = time.monotonic()
        _log_context_completeness("INTEGRATE", context)
        project_root = Path(context.get("project_root", ".")).resolve()
        staging_dir = Path(
            context.get("_staging_dir", str(project_root / ".startd8/staging"))
        )
        tasks = _ensure_context_loaded(context)
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {},
        )
        task_map = {t.task_id: t for t in tasks}
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})

        # Build engine
        registry = get_registry()
        registry.discover()
        # R-PY-006: Language-aware merge strategy selection
        _language_id = context.get("language_profile")
        if _language_id and hasattr(_language_id, "language_id"):
            _language_id = _language_id.language_id
        merge_strategy = registry.get_default_merge_strategy(
            for_python=True, language_id=_language_id if isinstance(_language_id, str) else None,
        )()

        # P0: Thread language profile to checkpoint and engine
        _lang_profile = context.get("language_profile")
        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=merge_strategy,
            checkpoint=IntegrationCheckpoint(
                project_root=project_root, run_tests=False,
                language_profile=_lang_profile,
            ),
            dry_run=dry_run,
            auto_commit=False,  # Workflow commits once at FINALIZE
            allow_dirty=False,
            check_truncation=self.config.check_truncation,
        )
        engine._language_profile = _lang_profile
        # R2-O6: Thread manifest_registry from orchestrator context so
        # INTEGRATE can use manifest data for validation/conflict detection.
        engine.manifest_registry = context.get("project_manifests")

        # Capture original generated file paths before integration overwrites them
        _original_gen_files: dict[str, list[str]] = {}
        for task_id, gr in generation_results.items():
            if gr.success:
                _original_gen_files[task_id] = [str(f) for f in gr.generated_files]

        # Integrate each task
        integration_results: dict[str, dict[str, Any]] = {}
        for task_id, gr in generation_results.items():
            if not gr.success:
                continue
            task = task_map.get(task_id)
            if not task:
                logger.warning(
                    "INTEGRATE: task %s has generation_results but is not in task_map "
                    "— skipping integration (task may have been removed from seed)",
                    task_id,
                )
                continue
            _log_task_boundary_start(task, phase="integrate")

            _links = _build_provenance_links(task_id, context, ["design", "implement"])
            with _phase_tracer.start_as_current_span(
                f"task.{task_id}",
                attributes={
                    "task.id": task_id,
                    "task.phase": "integrate",
                },
                links=_links,
            ) as _int_span:
                # AR-816: Skip integration for truncation-blocked tasks
                _task_trunc = truncation_flags.get(task_id, {})
                if _task_trunc.get("truncation_blocked"):
                    integration_results[task_id] = {
                        "success": False,
                        "integrated_files": [],
                        "errors": [
                            f"Truncation blocked (confidence="
                            f"{_task_trunc.get('max_confidence', 0):.2f})"
                        ],
                        "warnings": [],
                        "rollback_performed": False,
                        "skipped_files": [
                            {"path": str(f), "reason": "truncation_blocked"}
                            for f in gr.generated_files
                        ],
                        "status": "BLOCKED",
                    }
                    _int_span.set_attribute("task.truncation_blocked", True)
                    _int_span.set_attribute(
                        "truncation.confidence",
                        _task_trunc.get("max_confidence", 0),
                    )
                    _int_span.add_event(
                        "truncation.rejection",
                        attributes={
                            "truncation.confidence": _task_trunc.get("max_confidence", 0),
                            "truncation.action": "rejected",
                            "truncation.source": _task_trunc.get("source", "unknown"),
                        },
                    )
                    _log_task_boundary_complete(
                        task_id,
                        status="BLOCKED",
                        phase="integrate",
                    )
                    continue

                # Pass edit mode classification so the integration engine
                # can skip merge strategy for edit-mode tasks (the staging
                # file IS the complete file after search/replace).
                _edit_classifications = context.get(
                    "edit_mode_classifications", {},
                )
                _task_edit_mode = _edit_classifications.get(task_id)
                # AR-818/AR-823: Thread truncation and module inventory into unit context
                _unit_extra: dict[str, Any] = {}
                if _task_trunc:
                    _unit_extra["_truncation_flags"] = _task_trunc
                _scaffold = context.get("scaffold", {})
                _module_inv = _scaffold.get("module_inventory", [])
                if _module_inv:
                    _unit_extra["module_inventory"] = _module_inv
                unit = SeedTaskUnit(
                    task, gr, edit_mode=_task_edit_mode,
                    extra_context=_unit_extra if _unit_extra else None,
                )
                listener = OTelIntegrationListener(
                    task_id=task_id,
                    task_span=_int_span,
                    wrapped=ArtisanIntegrationListener(task_id),
                )
                result = engine.integrate(unit, listener=listener)
                integration_results[task_id] = {
                    "success": result.success,
                    "integrated_files": [str(f) for f in result.integrated_files],
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "rollback_performed": result.rollback_performed,
                    "skipped_files": result.skipped_files,
                    "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                }
                _int_span.set_attribute("task.success", result.success)
                _int_span.set_attribute(
                    "integration.status",
                    result.status.value if hasattr(result.status, "value") else str(result.status),
                )
                _int_span.set_attribute("integration.files_merged", len(result.integrated_files))
                _int_span.set_attribute("integration.error_count", len(result.errors))
                _int_span.set_attribute("integration.warning_count", len(result.warnings))
                _int_span.set_attribute("integration.rollback", result.rollback_performed)
                _int_span.set_attribute("integration.skipped_count", len(result.skipped_files))

                # AR-825: Import validation OTel span attributes
                _import_skipped = [
                    s for s in result.skipped_files
                    if isinstance(s, dict) and s.get("reason") == "unresolved_imports"
                ]
                _unresolved_modules: list[str] = []
                for s in _import_skipped:
                    _unresolved_modules.extend(s.get("unresolved", []))
                _int_span.set_attribute(
                    "task.import_validation.unresolved_count", len(_unresolved_modules),
                )
                _int_span.set_attribute(
                    "task.import_validation.unresolved_modules",
                    ", ".join(_unresolved_modules) if _unresolved_modules else "",
                )

                _sc = _capture_task_span_context(_int_span)
                if _sc:
                    integration_results[task_id]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task_id,
                    status=str(integration_results[task_id].get("status", "unknown")),
                    phase="integrate",
                )

                # Update generation_results paths: staging → project_root
                if result.success:
                    gr.generated_files = [Path(f) for f in result.integrated_files]

        # ── Reconcile expected vs merged files ─────────────────────
        # Detect files that IMPLEMENT generated but INTEGRATE didn't
        # merge (silent file loss). This catches the gap where a
        # multi-file generation produces N files but only N-1 appear
        # in the merged output.
        _total_missing = 0
        for task_id, gr in generation_results.items():
            if not gr.success:
                continue
            ir = integration_results.get(task_id, {})
            if ir.get("status") == "BLOCKED":
                continue

            integrated = {str(Path(f)) for f in ir.get("integrated_files", [])}
            expected = set(_original_gen_files.get(task_id, []))

            # Also count skipped files as "accounted for"
            skipped_paths = ir.get("skipped_files", [])
            for sf in skipped_paths:
                if isinstance(sf, dict):
                    sp = sf.get("path", "")
                    if sp:
                        integrated.add(str(Path(sp)))
                elif isinstance(sf, str):
                    integrated.add(str(Path(sf)))

            missing = expected - integrated
            if missing:
                _total_missing += len(missing)
                ir["_missing_files"] = sorted(missing)
                logger.warning(
                    "INTEGRATE: task %s — %d file(s) generated but not merged: %s",
                    task_id,
                    len(missing),
                    sorted(missing),
                )

        if _total_missing:
            logger.error(
                "INTEGRATE: %d file(s) lost during merge across all tasks "
                "— check integration warnings above",
                _total_missing,
            )

        # R2-O1: Before cleaning staging, update generated_files for tasks
        # whose integration failed or was blocked — their staging paths are
        # about to be deleted, so downstream phases must not reference them.
        for task_id, gr in generation_results.items():
            if not gr.success:
                continue
            ir = integration_results.get(task_id, {})
            if not ir:
                # Task had no integration attempt — clear staging paths
                gr.generated_files = []
            elif not ir.get("success", False):
                # Integration failed or blocked — staging paths are stale
                gr.generated_files = []

        # Clean staging dir
        if staging_dir.exists() and not dry_run:
            _shutil.rmtree(staging_dir, ignore_errors=True)

        # C-4: Guard against silent empty integration_results when
        # generation_results has successful entries.  This catches the
        # scenario where a cache load failure causes generation_results
        # to be empty (or mismatched) — FINALIZE would otherwise see
        # every task as "failed integration" without any warning.
        _successful_gen = sum(
            1 for gr in generation_results.values() if gr.success
        )
        if _successful_gen > 0 and not integration_results:
            logger.warning(
                "INTEGRATE: generation_results has %d successful "
                "entry(ies) but integration_results is empty — "
                "a fresh integration pass will be performed on retry. "
                "Cached integration results could not be loaded.",
                _successful_gen,
            )
        elif not generation_results and not integration_results:
            logger.warning(
                "INTEGRATE: generation_results is empty — "
                "cached generation results could not be loaded; "
                "a fresh integration pass will be required after "
                "re-running IMPLEMENT.",
            )

        # Log skipped files summary for visibility
        skipped_total = sum(
            len(r.get("skipped_files", [])) for r in integration_results.values()
        )
        if skipped_total:
            skipped_tasks = sum(
                1 for r in integration_results.values() if r.get("skipped_files")
            )
            logger.error(
                "INTEGRATE: %d file(s) skipped due to size regression "
                "across %d task(s)",
                skipped_total,
                skipped_tasks,
            )

        # Validate output structure before writing to context.
        # In "block" quality gate mode, validation failure is fatal.
        from startd8.contractors.context_schema import IntegratePhaseOutput
        _validation_failed = False
        try:
            IntegratePhaseOutput.model_validate(
                {"integration_results": integration_results}
            )
        except Exception as exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn"
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"INTEGRATE output validation failed (block policy): {exc}"
                ) from exc
            _validation_failed = True
            logger.warning(
                "INTEGRATE output validation failed (continuing per %s "
                "policy): %s", _gate_mode, exc,
            )
        if _validation_failed:
            for ir_val in integration_results.values():
                if isinstance(ir_val, dict):
                    ir_val["_validation_failed"] = True

        # Write to context
        context["integration_results"] = integration_results
        # generation_results already mutated with project_root paths

        duration = time.monotonic() - start
        passed = sum(1 for r in integration_results.values() if r["success"])
        # R2-O2: Include design-failed and other non-generated tasks in the
        # denominator so they don't inflate the pass rate.  Tasks whose
        # generation failed (including design_gated) are counted but not passed.
        _design_failed_count = sum(
            1 for gr in generation_results.values()
            if not gr.success and getattr(gr, "metadata", None)
            and isinstance(gr.metadata, dict)
            and gr.metadata.get("design_gated")
        )
        _gen_failed_count = sum(
            1 for gr in generation_results.values()
            if not gr.success
        )
        # Total = tasks that went through integration + tasks that were
        # skipped due to generation failure (design_gated, impl errors, etc.)
        total = len(integration_results) + _gen_failed_count

        logger.info(
            "INTEGRATE phase complete: %d/%d tasks merged "
            "(%d design-failed, %d gen-failed) (%.2fs)",
            passed, total, _design_failed_count,
            _gen_failed_count - _design_failed_count, duration,
        )

        return {
            "output": integration_results,
            "cost": 0.0,  # no LLM cost — only subprocess validation
            "metadata": {
                "duration": duration,
                "passed": passed,
                "total": total,
                "design_failed": _design_failed_count,
                "gen_failed": _gen_failed_count,
            },
        }
