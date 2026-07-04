"""IMPLEMENT phase handler."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import subprocess
import threading
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)
from startd8.contractors.context_schema import ImplementPhaseOutput
from startd8.contractors.context_seed.shared import (
    SeedTask,
    _ensure_context_loaded,
    _log_context_completeness,
    _track_onboarding_consumption,
)
from startd8.contractors.protocols import CodeGenerator, GenerationResult
from startd8.contractors.context_seed.handler_support import (
    EditModeClassification,
    HandlerConfig,
    PerFileMode,
    _CACHE_SCHEMA_VERSION,
    _MAX_GEN_FILE_HASH_BYTES,
    _SIZE_REGRESSION_MIN_LINES,
    _SIZE_REGRESSION_THRESHOLD,
    _coerce_optional_float,
    _compute_design_results_hash,
    _dict_to_gen_result,
    _log_task_boundary_complete,
    _log_task_boundary_start,
)
from startd8.contractors.context_seed.design_support import (
    _classify_complexity_tier,
    _compute_manifest_file_checksums,
    _extract_complexity_signals,
    _set_default_complexity_metadata,
)
from startd8.contractors.gate_contracts import GateEmitter
from startd8.exceptions import Startd8Error
from startd8.otel import attach_context, capture_context, detach_context
from startd8.logging_config import get_logger
from startd8.utils.file_operations import atomic_write_json

logger = get_logger("startd8.contractors.context_seed_handlers")


class ImplementPhaseHandler(AbstractPhaseHandler):
    """IMPLEMENT phase: Generate code per task via DevelopmentPhase engine.

    In dry-run mode: reports what would be implemented per task (unchanged).
    In real mode: delegates to :class:`DevelopmentPhase` with a
    :class:`PrimaryContractorChunkExecutor`, gaining parallelism, state
    persistence, crash recovery, and retry with error-informed feedback.

    Bridges the sync ``handler.execute()`` call from
    :class:`ArtisanContractorWorkflow` to the async ``DevelopmentPhase.run()``
    via ``asyncio.run()``.

    Data flow:
        1. ``SeedTask`` list → ``DevelopmentChunk`` list (``_tasks_to_chunks``)
        2. Build ``DevelopmentPlan`` → ``DevelopmentPhase.run()``
        3. ``DevelopmentResult`` → output dict + ``context["generation_results"]``
           (``_map_development_result``)
    """

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        code_generator: Optional[CodeGenerator] = None,  # deprecated, ignored
        enriched_seed_path: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        if code_generator is not None:
            warnings.warn(
                "ImplementPhaseHandler: 'code_generator' parameter is deprecated "
                "and ignored. The artisan pipeline now uses DevelopmentPhase with "
                "'drafter_spec' from HandlerConfig instead. This parameter will "
                "be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.config = handler_config or HandlerConfig()
        self._enriched_seed_path = enriched_seed_path
        self._project_root = project_root

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_environment(task: SeedTask) -> list[dict[str, Any]]:
        """Check environment readiness for a task.

        Returns list of environment issues (fail/warn checks).
        """
        return [
            c for c in task.environment_checks
            if c.get("status") in ("fail", "warn")
        ]

    @staticmethod
    def _validate_multi_file_tasks(tasks: list[SeedTask]) -> None:
        """Pre-IMPLEMENT validation: warn about risky multi-file tasks.

        Logs structured warnings for tasks that are likely to encounter
        multi-file split failures so operators can monitor and intervene
        early. This is a defense-in-depth layer — it doesn't block
        execution but makes risk visible.

        Checks:
        1. Multi-file tasks (>1 target) — higher split failure risk.
        2. Multi-file tasks with ``__init__.py`` — often confuses LLMs.
        3. Tasks whose prompt_constraints mention "shared module" — known
           shared files that the LLM may skip.
        4. Cross-task file overlap — files targeted by multiple tasks.
        """
        multi_file_tasks = [t for t in tasks if len(t.target_files) > 1]
        if not multi_file_tasks:
            return

        # Only build the file→tasks index when there are multi-file tasks
        # to check (avoids iterating all tasks when none are multi-file).
        file_to_tasks: dict[str, list[str]] = {}
        for task in tasks:
            for tf in task.target_files:
                file_to_tasks.setdefault(tf, []).append(task.task_id)

        logger.info(
            "IMPLEMENT pre-validation: %d of %d tasks are multi-file",
            len(multi_file_tasks),
            len(tasks),
        )

        for task in multi_file_tasks:
            risk_flags: list[str] = []

            # __init__.py is often omitted by LLMs
            init_files = [f for f in task.target_files if f.endswith("__init__.py")]
            if init_files:
                risk_flags.append(f"includes __init__.py ({', '.join(init_files)})")

            # Shared module hint present
            shared_hints = [
                c for c in task.prompt_constraints
                if "shared module" in c.lower() or "shared file" in c.lower()
            ]
            if shared_hints:
                risk_flags.append("contains shared-module constraint")

            # Files targeted by other tasks too
            overlapping = [
                f for f in task.target_files
                if len(file_to_tasks.get(f, [])) > 1
            ]
            if overlapping:
                risk_flags.append(
                    f"overlapping files: {', '.join(overlapping)}"
                )

            # File scope from seed — contract-level classification
            if task.file_scope:
                non_primary = {
                    f: s for f, s in task.file_scope.items()
                    if s != "primary"
                }
                if non_primary:
                    risk_flags.append(
                        f"file_scope: {non_primary} (Gate 2c will pre-stub)"
                    )

            if risk_flags:
                logger.warning(
                    "IMPLEMENT pre-validation: task %s (%d files) has elevated "
                    "multi-file split risk — %s. Stub generation will activate "
                    "if LLM omits files.",
                    task.task_id,
                    len(task.target_files),
                    "; ".join(risk_flags),
                )
            else:
                logger.info(
                    "IMPLEMENT pre-validation: task %s has %d target files",
                    task.task_id,
                    len(task.target_files),
                )

    def _run_micro_prime_prepass(
        self, context: dict[str, Any], project_root: Path,
    ) -> None:
        """Run Micro Prime pre-pass to fill TRIVIAL/SIMPLE element bodies.

        Reads the forward manifest and skeleton files from context, runs the
        Micro Prime engine, and stores results in context for downstream use.
        """
        try:
            from startd8.micro_prime.artisan_adapter import MicroPrimePrePass
            from startd8.micro_prime.models import MicroPrimeConfig
        except ImportError:
            logger.warning(
                "IMPLEMENT: micro_prime package not available, skipping pre-pass",
            )
            return

        manifest_path = context.get("manifest_path")
        if not manifest_path:
            logger.info("IMPLEMENT: no manifest_path in context, skipping Micro Prime pre-pass")
            return

        manifest = context.get("manifest")
        skeletons = context.get("skeletons", {})

        if not manifest or not skeletons:
            logger.info("IMPLEMENT: no manifest/skeletons in context, skipping Micro Prime pre-pass")
            return

        config = MicroPrimeConfig()
        override = context.get("micro_prime_config")
        if override:
            try:
                if isinstance(override, MicroPrimeConfig):
                    config = override
                elif isinstance(override, dict):
                    config = MicroPrimeConfig(**override)
            except Exception as exc:
                logger.warning(
                    "IMPLEMENT: invalid micro_prime_config override: %s", exc,
                )
        pre_pass = MicroPrimePrePass(
            config=config,
            manifest=manifest,
            skeletons=skeletons,
            project_root=project_root,
        )
        result = pre_pass.run()

        # Store results in context for downstream phases
        context["micro_prime_result"] = {
            "filled_skeletons": result.filled_skeletons,
            "escalated_elements": result.escalated_elements,
            "metrics": result.metrics,
            "element_metrics": result.element_metrics,
            "elements_filled": result.elements_filled,
        }
        # Update skeletons with filled versions
        if result.filled_skeletons:
            context["skeletons"] = result.filled_skeletons

        # Emit micro-prime quality gate result (REQ-MP-600 observability)
        try:
            gate_result = GateEmitter.from_micro_prime_result(
                context["micro_prime_result"],
                workflow_id=context.get("workflow_id", "unknown"),
                trace_id=context.get("trace_id"),
            )
            GateEmitter.emit(gate_result)
        except Exception as exc:
            logger.warning("IMPLEMENT: failed to emit Micro Prime gate result: %s", exc)

        logger.info(
            "IMPLEMENT: Micro Prime pre-pass completed — %d local, %d escalated",
            result.local_success_count,
            result.escalated_count,
        )

    @staticmethod
    def _validate_generation_completeness(
        tasks: list[SeedTask],
        generation_results: dict[str, "GenerationResult"],
        project_root: Path,
        downstream_map: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Gate 3: post-IMPLEMENT validation of multi-file split completeness.

        Per the Export Pipeline Analysis Guide's defense-in-depth Principle 1
        (validate at every boundary): verifies that multi-file tasks actually
        produced all their target files on disk.

        Returns a list of validation findings (one per multi-file task that
        has issues).  Empty list means all multi-file tasks are complete.

        This is the last gate before output is accepted — it catches cases
        where Gate 2 warnings were present but the drafter still omitted
        files despite all mitigation layers.

        Enhancement (defense-in-depth): ``downstream_map`` from Gate 2c
        allows distinguishing **downstream stubs** (expected, pre-created)
        from **generation failure stubs** (unexpected, needs attention).
        """
        findings: list[dict[str, Any]] = []
        downstream_map = downstream_map or {}

        for task in tasks:
            if len(task.target_files) <= 1:
                continue

            gr = generation_results.get(task.task_id)
            if gr is None:
                continue  # Task wasn't processed (dep-blocked, skipped, etc.)

            task_downstream = set(downstream_map.get(task.task_id, []))

            # Check which target files actually exist on disk
            generated_paths = {str(p) for p in (gr.generated_files or [])}
            missing_on_disk: list[str] = []
            stubbed: list[str] = []
            downstream_stubbed: list[str] = []

            for tf in task.target_files:
                full_path = project_root / tf
                if not full_path.exists():
                    if tf in task_downstream:
                        # Downstream file not on disk — unexpected since
                        # Gate 2c should have pre-created it.
                        missing_on_disk.append(tf)
                    else:
                        missing_on_disk.append(tf)
                elif full_path.exists():
                    # Check for stub sentinel (auto-generated placeholder)
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        is_stub = (
                            "STUB_PLACEHOLDER" in content
                            or "# AUTO-STUB" in content
                            or "# STARTD8_AUTO_STUB" in content
                            or "downstream — will be implemented by later tasks" in content
                        )
                        if is_stub:
                            if tf in task_downstream:
                                downstream_stubbed.append(tf)
                            else:
                                stubbed.append(tf)
                    except Exception:
                        logger.debug(
                            "IMPLEMENT Gate 3: stub sentinel check failed for %s in task %s",
                            tf, task.task_id, exc_info=True,
                        )

            # Only report as issues if there are true failures (not downstream)
            has_real_issues = bool(missing_on_disk or stubbed)

            if has_real_issues or downstream_stubbed:
                finding: dict[str, Any] = {
                    "task_id": task.task_id,
                    "target_file_count": len(task.target_files),
                    "target_files": task.target_files,
                    "missing_on_disk": missing_on_disk,
                    "stubbed_files": stubbed,
                    "downstream_stubbed": downstream_stubbed,
                    "generation_success": gr.success,
                    "has_real_issues": has_real_issues,
                }
                findings.append(finding)

                if has_real_issues:
                    level = "ERROR" if missing_on_disk else "WARN"
                    logger.warning(
                        "Gate 3 [%s]: task %s multi-file split incomplete — "
                        "%d/%d files verified. Missing: %s. Stubbed: %s",
                        level,
                        task.task_id,
                        len(task.target_files) - len(missing_on_disk) - len(stubbed),
                        len(task.target_files),
                        missing_on_disk or "(none)",
                        stubbed or "(none)",
                    )
                if downstream_stubbed:
                    logger.info(
                        "Gate 3 [OK/downstream]: task %s — %d file(s) are "
                        "expected downstream stubs (pre-created by Gate 2c): %s",
                        task.task_id,
                        len(downstream_stubbed),
                        downstream_stubbed,
                    )
            else:
                logger.info(
                    "Gate 3 [OK]: task %s — all %d target files verified on disk",
                    task.task_id,
                    len(task.target_files),
                )

        return findings

    @staticmethod
    def _validate_generation_content(
        tasks: list[SeedTask],
        generation_results: dict[str, "GenerationResult"],
        project_root: Path,
        service_metadata: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Gate 3b: post-IMPLEMENT semantic content validation.

        Runs all 5 self-consistency validators (AR-143 through AR-147)
        against generated files to catch production-blocking defects
        before TEST/REVIEW/FINALIZE.

        Returns:
            Dict mapping task_id to a list of issue dicts.
            Empty dict means all tasks are clean.
        """
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_placeholder_detection,
            validate_import_dependency,
            validate_intra_project_imports,
            validate_proto_field_references,
            validate_protocol_fidelity,
            validate_dockerfile_coherence,
            validate_function_call_completeness,
            validate_dockerfile_runtime_deps,
        )
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            _StubEnrichment,
        )

        enrichment = _StubEnrichment(cwd=str(project_root))
        all_findings: dict[str, list[dict[str, Any]]] = {}

        for task in tasks:
            gr = generation_results.get(task.task_id)
            if gr is None or not gr.success:
                continue

            task_issues: list[dict[str, Any]] = []
            for rel_path in task.target_files:
                full_path = project_root / rel_path
                if not full_path.exists():
                    continue
                try:
                    code = full_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                # AR-146: Placeholder detection (all files)
                task_issues.extend(validate_placeholder_detection(code, enrichment))

                # AR-143, AR-145, AR-150: Python-specific validators
                if rel_path.endswith(".py"):
                    task_issues.extend(validate_import_dependency(code, enrichment))
                    task_issues.extend(validate_intra_project_imports(code, enrichment))
                    task_issues.extend(validate_proto_field_references(code, enrichment))

                # AR-144: Protocol fidelity (with service_metadata)
                task_issues.extend(
                    validate_protocol_fidelity(code, rel_path, service_metadata)
                )

                # AR-147: Dockerfile coherence
                task_issues.extend(
                    validate_dockerfile_coherence(code, rel_path, service_metadata)
                )

                # AR-148: Function call completeness
                task_issues.extend(
                    validate_function_call_completeness(code, rel_path, service_metadata)
                )

                # AR-149: Dockerfile runtime dependencies
                task_issues.extend(
                    validate_dockerfile_runtime_deps(code, rel_path, service_metadata)
                )

            if task_issues:
                all_findings[task.task_id] = task_issues

        return all_findings

    @staticmethod
    def _validate_truncation(
        tasks: list[SeedTask],
        generation_results: dict[str, "GenerationResult"],
        project_root: Path,
        existing_file_sizes: dict[str, dict[str, int]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Gate 4: post-IMPLEMENT truncation detection on generated files.

        For each successfully generated task, reads every generated file from
        disk and runs four checks:

        1. ``detect_truncation()`` with ``code_mode=None`` (auto-detect).
        2. ``compile()`` syntax validation for Python files.
        3. Line-count ratio against ``task.estimated_loc`` (flag if < 30%).
        4. Size regression vs existing file (PCA-603): flag when generated
           file is < ``_SIZE_REGRESSION_THRESHOLD`` (default 70%) of existing
           file, for files > ``_SIZE_REGRESSION_MIN_LINES`` lines.

        Args:
            existing_file_sizes: Optional mapping of task_id → {path: line_count}
                for existing files on disk. Used for Check 4 size regression.

        Returns:
            Dict mapping task_id to a flag dict with keys:
            ``detected`` (bool), ``max_confidence`` (float),
            ``source`` (str: syntax|heuristic_high|ratio|size_regression|heuristic),
            ``indicators`` (list[str]), ``file_results`` (list[dict]),
            ``syntax_errors`` (list[str]), ``total_lines`` (int),
            ``estimated_loc`` (int|None), and optionally ``ratio`` (float)
            or ``size_regression_ratio`` (float).
            Only tasks with at least one positive signal are included;
            clean tasks are omitted (empty dict for a fully clean run).
        """
        from startd8.truncation_detection import (
            CONFIDENCE_HIGH,
            detect_truncation,
            log_truncation_result,
        )

        # OTel span for event emission.  When OTel is installed but no
        # tracer is configured, get_current_span() returns a
        # NonRecordingSpan whose add_event() is a safe no-op.
        _span = None
        try:
            from opentelemetry import trace as _trace
            _span = _trace.get_current_span()
        except ImportError:
            logger.debug("Optional import not available", exc_info=True)

        flags: dict[str, dict[str, Any]] = {}

        for task in tasks:
            gr = generation_results.get(task.task_id)
            if gr is None or not gr.success:
                continue  # skip failed / unprocessed tasks

            file_results: list[dict[str, Any]] = []
            syntax_errors: list[str] = []
            max_confidence = 0.0
            any_detected = False
            total_lines = 0

            for fpath in (gr.generated_files or []):
                fp = Path(fpath)
                if not fp.exists():
                    continue
                # Respect existing 50 MB ceiling
                try:
                    fsize = fp.stat().st_size
                except OSError as exc:
                    logger.debug("Gate 4: skipping %s — stat failed: %s", fp, exc)
                    continue
                if fsize > _MAX_GEN_FILE_HASH_BYTES:
                    continue

                try:
                    content = fp.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    logger.debug("Gate 4: skipping unreadable file %s: %s", fp, exc)
                    continue

                line_count = len(content.splitlines())
                total_lines += line_count

                # --- Check 1: heuristic truncation detection ---
                tr = detect_truncation(content, code_mode=None)
                fr: dict[str, Any] = {
                    "file": str(fp),
                    "lines": line_count,
                    "truncation_detected": tr.is_truncated,
                    "truncation_confidence": tr.confidence,
                    "truncation_indicators": tr.indicators,
                }
                if tr.is_truncated:
                    any_detected = True
                    max_confidence = max(max_confidence, tr.confidence)
                    log_truncation_result(
                        tr,
                        source_file=str(fp),
                        feature_name=task.task_id,
                        step_name="IMPLEMENT.gate4",
                    )

                # --- Check 2: syntax validation (Python only) ---
                if fp.suffix == ".py":
                    try:
                        compile(content, str(fp), "exec")
                        fr["syntax_valid"] = True
                    except (SyntaxError, ValueError) as se:
                        fr["syntax_valid"] = False
                        msg = getattr(se, "msg", str(se))
                        lineno = getattr(se, "lineno", None)
                        fr["syntax_error"] = (
                            f"{msg} (line {lineno})" if lineno else msg
                        )
                        syntax_errors.append(str(fp))
                        any_detected = True
                        if _span:
                            _span.add_event(
                                "syntax.validation_failed",
                                attributes={
                                    "task_id": task.task_id,
                                    "file": str(fp),
                                    "error": fr["syntax_error"],
                                },
                            )

                file_results.append(fr)

            # --- Check 3: line-count ratio ---
            ratio_flag = False
            if task.estimated_loc and task.estimated_loc > 0 and total_lines > 0:
                ratio = total_lines / task.estimated_loc
                if ratio < 0.3:
                    ratio_flag = True
                    any_detected = True

            # --- Check 4: Size regression vs existing file (PCA-603) ---
            size_regression_flag = False
            size_regression_details: list[dict[str, Any]] = []
            if existing_file_sizes:
                task_sizes = existing_file_sizes.get(task.task_id, {})
                # Build a map of generated file paths → line counts from file_results
                gen_line_counts: dict[str, int] = {}
                for fr_item in file_results:
                    gen_line_counts[fr_item["file"]] = fr_item.get("lines", 0)

                for existing_path, existing_lines in task_sizes.items():
                    if existing_lines <= _SIZE_REGRESSION_MIN_LINES:
                        continue
                    # Find matching generated file — match by relative path suffix
                    gen_lines = 0
                    for gen_path, gen_lc in gen_line_counts.items():
                        if gen_path.endswith(existing_path) or str(Path(gen_path)) == str(Path(existing_path)):
                            gen_lines = gen_lc
                            break
                    if gen_lines <= 0:
                        continue  # File not generated — skip (handled by Gate 3)
                    if existing_lines > 0 and gen_lines / existing_lines < _SIZE_REGRESSION_THRESHOLD:
                        size_regression_flag = True
                        any_detected = True
                        size_regression_details.append({
                            "file": existing_path,
                            "existing_lines": existing_lines,
                            "generated_lines": gen_lines,
                            "ratio": gen_lines / existing_lines,
                        })
                        logger.warning(
                            "Gate 4 [size_regression]: task %s file %s — "
                            "%d generated / %d existing (%.0f%% < %.0f%% threshold)",
                            task.task_id, existing_path,
                            gen_lines, existing_lines,
                            (gen_lines / existing_lines) * 100,
                            _SIZE_REGRESSION_THRESHOLD * 100,
                        )

            if not any_detected:
                continue

            # Determine primary source for the flag
            if syntax_errors:
                source = "syntax"
            elif max_confidence >= CONFIDENCE_HIGH:
                source = "heuristic_high"
            elif size_regression_flag:
                source = "size_regression"
            elif ratio_flag:
                source = "ratio"
            else:
                source = "heuristic"

            task_flag: dict[str, Any] = {
                "detected": True,
                "max_confidence": max_confidence,
                "source": source,
                "indicators": [],
                "file_results": file_results,
                "syntax_errors": syntax_errors,
                "total_lines": total_lines,
                "estimated_loc": task.estimated_loc,
            }
            if ratio_flag:
                task_flag["ratio"] = (
                    total_lines / task.estimated_loc
                    if task.estimated_loc and task.estimated_loc > 0
                    else None
                )
            if size_regression_flag:
                task_flag["size_regression"] = size_regression_details
            # AR-816: Mark tasks that should be blocked at INTEGRATE
            from startd8.truncation_detection import (
                CONFIDENCE_TRUNCATION_BLOCKED,
                MIN_LINES_TRUNCATION_BLOCKING,
            )
            # Compute blocking confidence from files large enough to be meaningful.
            # Tiny files (e.g., 1-line __init__.py) produce false-positive prose
            # heuristics that shouldn't prevent integration.
            _blocking_confidence = max(
                (
                    fr["truncation_confidence"]
                    for fr in file_results
                    if fr["lines"] >= MIN_LINES_TRUNCATION_BLOCKING
                    and fr.get("truncation_detected", False)
                ),
                default=0.0,
            )
            task_flag["truncation_blocked"] = (
                task_flag["detected"]
                and _blocking_confidence >= CONFIDENCE_TRUNCATION_BLOCKED
            )
            # Aggregate unique indicators
            for fr in file_results:
                task_flag["indicators"].extend(fr.get("truncation_indicators", []))
            task_flag["indicators"] = sorted(set(task_flag["indicators"]))

            flags[task.task_id] = task_flag

            if _span:
                _span.add_event(
                    "truncation.detected",
                    attributes={
                        "task_id": task.task_id,
                        "source": source,
                        "max_confidence": max_confidence,
                        "syntax_errors": len(syntax_errors),
                        "total_lines": total_lines,
                        "estimated_loc": task.estimated_loc or 0,
                    },
                )

        return flags

    @staticmethod
    def _ensure_test_scaffolding_for_artifact_tasks(
        tasks: list[SeedTask],
        project_root: Path,
    ) -> None:
        """Ensure test scaffolding exists for artifact generator tasks (Item 12).

        For tasks with artifact_types_addressed, derive the expected test path
        from the first target file and create minimal scaffolding if missing.
        Uses convention: target path/to/foo.py or path/to/foo.yaml → tests/test_foo.py.
        """
        for task in tasks:
            if not task.artifact_types_addressed or not task.target_files:
                continue

            tests_dir = project_root / "tests"
            target = Path(task.target_files[0])
            stem = target.stem.replace("-", "_")
            if not stem:
                continue
            test_path = tests_dir / f"test_{stem}.py"

            if test_path.exists():
                continue

            tests_dir.mkdir(parents=True, exist_ok=True)

            # Minimal scaffolding: test class skeleton
            artifact_label = "_".join(
                t.replace("-", "_") for t in task.artifact_types_addressed[:2]
            )
            class_name = "".join(
                p.capitalize() for p in stem.split("_") if p
            ) or "Artifact"
            content = f'''"""Tests for {artifact_label} — scaffold-first (Item 12)."""

import pytest


class Test{class_name}:
    """Test scaffold for {artifact_label} — implement before generation."""
    pass
'''
            test_path.write_text(content, encoding="utf-8")
            logger.info(
                "IMPLEMENT: scaffolded test file for artifact task %s: %s",
                task.task_id,
                test_path.relative_to(project_root),
            )

    @staticmethod
    def _reconcile_design_downstream(
        tasks: list[SeedTask],
        design_results: dict[str, Any],
        project_root: Path,
    ) -> dict[str, list[str]]:
        """Gate 2c: Reconcile design doc downstream designations with target_files.

        Uses a two-layer detection strategy (defense-in-depth Principle 1):

        **Layer 1 — Contract-level (seed ``_file_scope``):**
        Plan ingestion already classified files as "primary", "shared", or
        "stub" using ContextCore export's ``file_ownership`` and cross-feature
        analysis.  When ``_file_scope`` is present, we trust it as the
        authoritative source — it represents the contract answer to
        "Is the contract complete?" (Principle 6, Question 1).

        **Layer 2 — Runtime fallback (design doc parsing):**
        When ``_file_scope`` is absent (older seeds, manual seeds), falls
        back to scanning the design doc for downstream signals (e.g.
        "F-002+", "implemented by later tasks").

        For downstream/stub files:
        1. **Pre-creates a stub** on disk so downstream tasks have a valid
           import target immediately.
        2. **Returns a mapping** task_id → [downstream_files] so callers can
           shrink the drafter's target list and annotate metadata.

        Args:
            tasks: Parsed seed tasks from the PLAN phase.
            design_results: Per-task design results from the DESIGN phase.
            project_root: Root of the project for writing pre-stubs.

        Returns:
            Dict mapping task_id → list of downstream file paths that were
            pre-stubbed. Empty dict if no downstream files found.
        """
        from startd8.contractors.generators.primary_contractor import (
            _detect_downstream_files,
        )
        from startd8.utils.code_extraction import STUB_SENTINEL

        downstream_map: dict[str, list[str]] = {}

        for task in tasks:
            if len(task.target_files) < 2:
                continue

            downstream: list[str] = []

            # ── Layer 1: contract-level file scope from seed ──────────
            # This is the authoritative source when available.
            if task.file_scope:
                downstream = [
                    f for f in task.target_files
                    if task.file_scope.get(f) in ("stub", "shared")
                ]
                if downstream:
                    logger.info(
                        "Gate 2c [contract]: task %s has %d non-primary files "
                        "from seed _file_scope: %s",
                        task.task_id, len(downstream),
                        {f: task.file_scope[f] for f in downstream},
                    )

            # ── Layer 2: runtime fallback — parse design doc ──────────
            # Only fall through when file_scope is absent (older/manual seeds).
            # If file_scope exists, it's authoritative even if all files are
            # "primary" — that means the contract says to implement everything.
            if not downstream and not task.file_scope:
                task_design = design_results.get(task.task_id, {})
                if task_design.get("status") in ("designed", "adopted", "refined"):
                    design_doc = task_design.get("design_document", "")
                    if design_doc:
                        downstream = _detect_downstream_files(
                            task.target_files, design_doc,
                        )
                        if downstream:
                            logger.info(
                                "Gate 2c [runtime]: task %s has %d downstream "
                                "files from design doc parsing: %s",
                                task.task_id, len(downstream), downstream,
                            )

            if not downstream:
                continue

            # Safety: never remove ALL files — at least one must remain for
            # the drafter to implement.
            if len(downstream) >= len(task.target_files):
                logger.warning(
                    "Gate 2c: all %d target files for %s flagged as downstream "
                    "— keeping all to avoid empty task. Files: %s",
                    len(task.target_files), task.task_id, downstream,
                )
                continue

            # Pre-create stubs on disk for downstream files
            for fpath in downstream:
                abs_path = project_root / fpath
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                if not abs_path.exists():
                    # Generate a meaningful stub based on file type
                    module_name = abs_path.stem
                    if module_name == "__init__":
                        stub_content = (
                            f'"""{abs_path.parent.name} package."""\n'
                            f"{STUB_SENTINEL}  # downstream — will be implemented by later tasks\n"
                        )
                    else:
                        stub_content = (
                            f'"""{module_name} module — stub for downstream implementation."""\n'
                            f"{STUB_SENTINEL}  # downstream — will be implemented by later tasks\n"
                        )
                    abs_path.write_text(stub_content, encoding="utf-8")
                    logger.info(
                        "Gate 2c: pre-stubbed downstream file %s for task %s",
                        fpath, task.task_id,
                    )

            downstream_map[task.task_id] = downstream
            logger.info(
                "Gate 2c: task %s has %d downstream files (pre-stubbed): %s. "
                "These will be excluded from drafter targets.",
                task.task_id, len(downstream), downstream,
            )

        return downstream_map

    @staticmethod
    def _classify_edit_mode(
        task: SeedTask,
        scaffold: dict[str, Any],
        design_mode_summary: dict[str, str],
        design_mode_evidence: dict[str, dict[str, Any]] | None = None,
        manifest_registry: Any = None,
    ) -> EditModeClassification:
        """Classify each target file as 'create' or 'edit' using upstream signals.

        Consumes 6+ signals computed but previously unconsumed by IMPLEMENT:
          - scaffold["existing_target_files"] (Tier 1, weight 2)
          - task.existing_content_hash (Tier 1, weight 2)
          - manifest_registry.public_element_count (Tier 1, weight 2) [REQ-EMM-001]
          - manifest_registry.fqn_exists for api_signatures (Tier 1, weight 2) [REQ-EMM-002]
          - design_mode_summary[task_id] (Tier 2, weight 1; elevated to
            weight 2 when design_mode_evidence has >=2 corroborating signals)
          - scaffold["staleness_classification"] (Tier 2, weight 1)
          - task.file_scope (Tier 2, weight 1)

        When manifest_registry is None, produces identical results to the
        original 5-signal system (REQ-EMM-003).

        Args:
            design_mode_evidence: Gap 4 enrichment — when provided with >=2
                evidence signals, the design_mode_summary weight is elevated
                from Tier 2 (1) to Tier 1 (2), reflecting higher confidence.
            manifest_registry: Optional ManifestRegistry instance providing
                AST-based code intelligence (fqn_exists, public_element_count).

        Returns EditModeClassification with typed fields for mode, per_file,
        confidence, and signal_conflicts.
        """
        existing_targets = set(scaffold.get("existing_target_files", []))
        staleness_map = scaffold.get("staleness_classification", {})
        design_mode = design_mode_summary.get(task.task_id, "")

        # Gap 4: Determine design mode weight based on evidence strength
        _evidence = (design_mode_evidence or {}).get(task.task_id, {})
        _evidence_signals = _evidence.get("evidence", [])
        # Elevate from Tier 2 (weight 1) to Tier 1 (weight 2) when DESIGN
        # has >=2 corroborating signals (e.g. scaffold + doc annotation)
        _design_mode_weight = 2 if len(_evidence_signals) >= 2 else 1

        per_file: dict[str, PerFileMode] = {}
        signal_conflicts: list[str] = []

        for fpath in task.target_files:
            # Collect per-file signals with tier weights
            edit_weight = 0
            create_weight = 0
            file_signals_edit: list[str] = []
            file_signals_create: list[str] = []

            # Tier 1 (weight 2): existing_content_hash — non-None means file
            # physically existed at preflight time
            has_hash = task.existing_content_hash is not None

            # Tier 1 (weight 2): scaffold.existing_target_files
            in_existing = fpath in existing_targets

            # I-2: Only apply hash signal to files confirmed on disk
            if has_hash and in_existing:
                edit_weight += 2
                file_signals_edit.append("existing_content_hash")
            if in_existing:
                edit_weight += 2
                file_signals_edit.append("scaffold.existing_target_files")

            # Tier 2 (weight 1, elevated to 2 with evidence): design_mode_summary
            if design_mode == "update":
                edit_weight += _design_mode_weight
                file_signals_edit.append(
                    f"design_mode_summary=update(w={_design_mode_weight})"
                )
            elif design_mode == "create":
                create_weight += _design_mode_weight
                file_signals_create.append(
                    f"design_mode_summary=create(w={_design_mode_weight})"
                )

            # Tier 2 (weight 1): staleness_classification
            staleness = staleness_map.get(fpath, "")
            if staleness in ("fresh", "stale"):
                edit_weight += 1
                file_signals_edit.append(f"staleness={staleness}")

            # Tier 2 (weight 1): file_scope
            scope = (task.file_scope or {}).get(fpath, "")
            if scope == "primary":
                edit_weight += 1
                file_signals_edit.append("file_scope=primary")

            # Tier 1 (weight 2): manifest.public_element_count (REQ-EMM-001)
            _manifest_elem_count = 0
            if manifest_registry is not None:
                try:
                    _manifest_elem_count = manifest_registry.public_element_count(fpath)
                    if _manifest_elem_count > 0:
                        edit_weight += 2
                        file_signals_edit.append(
                            f"manifest.public_element_count={_manifest_elem_count}"
                        )
                        logger.info(
                            "Edit-mode manifest signal: %s has %d public elements",
                            fpath, _manifest_elem_count,
                        )
                except (AttributeError, TypeError, OSError):
                    logger.debug("Graceful degradation: file summary extraction failed", exc_info=True)

            # Tier 1 (weight 2): manifest.fqn_exists for api_signatures (REQ-EMM-002, PI-3)
            if manifest_registry is not None and task.api_signatures:
                try:
                    _matched_fqns = [
                        s for s in task.api_signatures
                        if manifest_registry.fqn_exists(s)
                    ]
                    if _matched_fqns:
                        edit_weight += 2
                        file_signals_edit.append(
                            f"manifest.fqn_exists={len(_matched_fqns)}/{len(task.api_signatures)}"
                        )
                        logger.info(
                            "Edit-mode manifest signal: %d/%d FQNs confirmed for task %s: %s",
                            len(_matched_fqns), len(task.api_signatures),
                            task.task_id, _matched_fqns[:3],
                        )
                except (AttributeError, TypeError):
                    logger.debug("Graceful degradation: manifest query failed", exc_info=True)

            # Classify this file
            if edit_weight >= 1:
                file_mode = "edit"
            else:
                file_mode = "create"

            # Detect Tier 1 vs Tier 2 conflicts
            tier1_edit = has_hash or in_existing or _manifest_elem_count > 0
            tier2_create = design_mode == "create"
            if tier1_edit and tier2_create:
                conflict = (
                    f"Signal conflict for file {fpath}: Tier 1 signals "
                    f"{file_signals_edit} indicate 'edit' but Tier 2 signals "
                    f"{file_signals_create} indicate 'create'. "
                    f"Tier 1 precedence applied."
                )
                signal_conflicts.append(conflict)
                logger.warning(conflict)

            per_file[fpath] = PerFileMode(
                mode=file_mode,
                staleness=staleness,
                has_hash=has_hash,
                edit_weight=edit_weight,
                manifest_element_count=_manifest_elem_count,
            )

        # Task-level aggregation: "edit" if ANY per_file is "edit"
        any_edit = any(pf.mode == "edit" for pf in per_file.values())
        task_mode = "edit" if any_edit else "create"

        # Confidence from max edit weight across files
        max_weight = max(
            (pf.edit_weight for pf in per_file.values()), default=0,
        )
        if max_weight >= 3:
            confidence = "high"
        elif max_weight >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        return EditModeClassification(
            mode=task_mode,
            per_file=per_file,
            confidence=confidence,
            signal_conflicts=signal_conflicts,
        )

    @staticmethod
    def _tasks_to_chunks(
        tasks: list[SeedTask],
        max_retries: int = 2,
        design_results: dict[str, Any] | None = None,
        calibration_map: dict[str, dict[str, Any]] | None = None,
        downstream_map: dict[str, list[str]] | None = None,
        staleness_classification: dict[str, str] | None = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
        # PCA-300/301/400: project-level context for IMPLEMENT prompts
        architectural_context: dict[str, Any] | None = None,
        plan_goals: list[str] | None = None,
        plan_context: str | None = None,
        service_metadata: dict[str, Any] | None = None,
        # PCA-401/403/404: additional IMPLEMENT enrichment
        calibration_hints: dict[str, Any] | None = None,
        prior_impl_summaries: list[dict[str, Any]] | None = None,
        # PCA-501: project identity for edit-first behavior
        project_name: str | None = None,
        project_root_path: str | None = None,
        preflight_safe_loc_limit: int = 800,
        preflight_safe_token_limit: int = 64000,
        # PCA-600: edit mode classification from upstream signals
        edit_mode_map: dict[str, EditModeClassification] | None = None,
        # AR-822: module inventory from SCAFFOLD for import grounding
        module_inventory: list[str] | None = None,
        # Scaffold output for skeleton file detection
        scaffold_output: dict[str, Any] | None = None,
        # Micro Prime pre-pass results for local-first skip / partial injection
        micro_prime_result: dict[str, Any] | None = None,
        # FR-MPA-005: Pre-classified element tiers from ingestion for prompt narrowing
        element_tiers: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,  # Allow forward_manifest via kwargs to avoid massive signature change
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Convert SeedTasks to DevelopmentChunks, pre-filtering env-blocked.

        Args:
            tasks: Parsed seed tasks from the PLAN phase.
            max_retries: Max retry count for each chunk.
            design_results: Per-task design results from the DESIGN phase.
                Maps task_id → dict with 'design_document' key containing the
                raw design document text to inject into implementation prompts.
            calibration_map: Per-task calibration (design_calibration) with
                optional implement_max_output_tokens for per-task token caps.
            downstream_map: Gate 2c output — maps task_id → list of files
                that were pre-stubbed as downstream.  These are excluded
                from the drafter's ``file_targets`` and annotated in
                chunk metadata so retry/review layers can distinguish
                expected stubs from generation failures.

        Returns:
            Tuple of (chunks, skipped_reports). ``skipped_reports`` contains
            task report dicts for env-blocked tasks.
        """
        from startd8.contractors.artisan_phases.development import DevelopmentChunk

        chunks: list[DevelopmentChunk] = []
        skipped: list[dict[str, Any]] = []
        design_results = design_results or {}
        downstream_map = downstream_map or {}
        staleness_classification = staleness_classification or {}
        active_task_ids = {t.task_id for t in tasks}

        env_blocked_ids: set[str] = set()
        for task in tasks:
            _log_task_boundary_start(task, phase="implement")
            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            if env_fails:
                env_blocked_ids.add(task.task_id)
                logger.warning(
                    "IMPLEMENT: skipping task %s (%s) — env_blocked (%d failing check(s))",
                    task.task_id,
                    task.title,
                    len(env_fails),
                )
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "env_blocked",
                    "complexity_tier": "tier_2",
                    "environment_issues": [
                        c for c in task.environment_checks
                        if c.get("status") in ("fail", "warn")
                    ],
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="env_blocked",
                    phase="implement",
                )

        for task in tasks:
            if task.task_id in env_blocked_ids:
                continue

            blocked_deps = [d for d in task.depends_on if d in env_blocked_ids]
            if blocked_deps:
                logger.warning(
                    "IMPLEMENT: skipping task %s (%s) — dep_blocked_env (blocked by: %s)",
                    task.task_id,
                    task.title,
                    ", ".join(blocked_deps),
                )
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "dep_blocked_env",
                    "complexity_tier": "tier_2",
                    "blocked_dependencies": blocked_deps,
                    "depends_on": task.depends_on,
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="dep_blocked_env",
                    phase="implement",
                )
                continue

            task_design = design_results.get(task.task_id, {})
            if task_design.get("status") == "design_failed":
                fail_reason = (
                    task_design.get("quality_failure_reason")
                    or task_design.get("error")
                    or "design_failed"
                )
                logger.warning(
                    "IMPLEMENT: skipping task %s (%s) — design_blocked (%s)",
                    task.task_id,
                    task.title,
                    fail_reason,
                )
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "design_blocked",
                    "complexity_tier": "tier_2",
                    "reason": str(fail_reason),
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="design_blocked",
                    phase="implement",
                )
                continue

            # Extract design document from DESIGN phase results (if available).
            # "adopted" status indicates reuse from a prior run (dress-rehearsal).
            design_doc_text = None
            if task_design.get("status") in ("designed", "adopted", "refined"):
                design_doc_text = task_design.get("design_document")

            # ── Layer 1: DESIGN→IMPLEMENT boundary validation (DP-2) ────
            # Defense-in-depth: per-task line-count pre-check before the
            # phase-level contract exit validator (BP-3).  Metric aligned
            # with artisan-pipeline.contract.yaml: line_count >= 50.
            # Pre-compute design doc metrics once (used for DP-2 boundary
            # check, scope logging, B-5 framing, and post-gen validation).
            _design_lines = 0
            _design_sections = 0
            if task_design.get("status") in ("designed", "adopted", "refined"):
                if design_doc_text:
                    for _dl in design_doc_text.strip().splitlines():
                        _design_lines += 1
                        if _dl.strip().startswith("##"):
                            _design_sections += 1
                if not design_doc_text or _design_lines < 10:
                    logger.warning(
                        "DESIGN→IMPLEMENT boundary: task %s has status '%s' but "
                        "design_document is empty/trivial (%d lines) — falling back "
                        "to task description only (DP-2: no silent defaults)",
                        task.task_id,
                        task_design.get("status"),
                        _design_lines,
                    )
                    design_doc_text = None
                    _design_lines = 0
                    _design_sections = 0
                else:
                    logger.info(
                        "DESIGN→IMPLEMENT boundary: task %s design document "
                        "propagated (%d chars, %d lines, %d sections)",
                        task.task_id,
                        len(design_doc_text),
                        _design_lines,
                        _design_sections,
                    )

            # Per-task implement token cap from design_calibration
            task_cal = (calibration_map or {}).get(task.task_id, {})
            max_output_tokens = task_cal.get("implement_max_output_tokens")

            # Initialize env_checks early so LOC mismatch and multi-file
            # checks can both append to it.
            env_checks = list(task.environment_checks)

            # ── Fix 3: LOC estimation mismatch detection ─────────────────
            # If the design doc exists, estimate its implied LOC from code
            # blocks and compare against the seed's estimated_loc.  A large
            # mismatch (>3x) means the depth tier was likely too low, which
            # causes truncation, incomplete output, and wasted retries.
            if design_doc_text and task.estimated_loc:
                _code_line_count = sum(
                    1 for line in design_doc_text.split("\n")
                    if line.strip()
                    and not line.strip().startswith("#")
                    and not line.strip().startswith("```")
                )
                # Rough heuristic: design doc code blocks ≈ 60% of total
                # lines are actual code.  Compare against seed estimate.
                _implied_loc = int(_code_line_count * 0.6)
                if _implied_loc > task.estimated_loc * 3:
                    env_checks.append({
                        "check_name": "loc_estimation_mismatch",
                        "status": "warn",
                        "message": (
                            f"Design doc implies ~{_implied_loc} LOC but seed "
                            f"estimates {task.estimated_loc} LOC (>{3}x mismatch)"
                        ),
                        "detail": (
                            f"The design document for {task.task_id} contains "
                            f"~{_code_line_count} non-empty lines, implying "
                            f"~{_implied_loc} LOC of implementation. The seed "
                            f"estimated {task.estimated_loc} LOC, which placed "
                            f"this task in the '{task_cal.get('depth_tier', 'standard')}' "
                            f"depth tier. Token budget will be auto-recalibrated "
                            f"based on design-implied LOC."
                        ),
                    })
                    logger.warning(
                        "LOC mismatch for task %s: design implies ~%d LOC, "
                        "seed estimates %d LOC (depth_tier=%s). "
                        "Token budget will be auto-recalibrated.",
                        task.task_id,
                        _implied_loc,
                        task.estimated_loc,
                        task_cal.get("depth_tier", "standard"),
                    )

                    # ── Defense-in-depth: auto-recalibrate token budget ────
                    # The design phase expanded scope beyond the seed
                    # estimate.  Bump implement tokens to prevent
                    # truncation rather than just warning about it.
                    # Tiers: <=150 LOC → 32768, <=400 LOC → 49152, >400 → 64000
                    # Cap at 64000: lowest common max across lead (opus)
                    # and drafter (haiku) models in the pipeline.
                    if _implied_loc <= 150:
                        _recal_tokens = 32768
                    elif _implied_loc <= 400:
                        _recal_tokens = 49152
                    else:
                        _recal_tokens = 64000
                    if max_output_tokens is None or _recal_tokens > max_output_tokens:
                        logger.info(
                            "Auto-recalibrating implement tokens for %s: "
                            "%s → %d (design implies ~%d LOC)",
                            task.task_id,
                            max_output_tokens,
                            _recal_tokens,
                            _implied_loc,
                        )
                        max_output_tokens = _recal_tokens

            # ── Multi-file preflight checks ──────────────────────────────
            # Surface risk signals as environment checks so they appear in
            # preflight reports.  These are task-level (not per-file) checks
            # derived from real-world failure patterns (PI-001 post-mortem).
            if len(task.target_files) > 1:
                env_checks.append({
                    "check_name": "multi_file_split_risk",
                    "status": "warn",
                    "message": (
                        f"Task targets {len(task.target_files)} files — "
                        f"LLM may omit some code blocks"
                    ),
                    "detail": (
                        f"Target files: {', '.join(task.target_files)}. "
                        f"Multi-file tasks have higher risk of incomplete output. "
                        f"Defense layers: prompt checklist, __init__.py constraint, "
                        f"content-heuristic extraction, retry with role hints, "
                        f"stub fallback."
                    ),
                })
                init_files = [
                    f for f in task.target_files if f.endswith("__init__.py")
                ]
                if init_files:
                    env_checks.append({
                        "check_name": "init_py_in_multi_file",
                        "status": "warn",
                        "message": (
                            f"__init__.py among {len(task.target_files)} targets — "
                            f"commonly skipped by LLM drafters"
                        ),
                        "detail": (
                            f"Files: {', '.join(init_files)}. "
                            f"Models treat __init__.py as optional because it's "
                            f"'just imports'. Dedicated constraints and extraction "
                            f"heuristics are active."
                        ),
                    })
                # High-LOC multi-file: truncation risk compounds with split risk
                if task.estimated_loc and task.estimated_loc > 200:
                    env_checks.append({
                        "check_name": "multi_file_high_loc",
                        "status": "warn",
                        "message": (
                            f"Multi-file task with {task.estimated_loc} estimated LOC — "
                            f"truncation may compound split failure"
                        ),
                        "detail": (
                            "Consider splitting into single-file tasks, or increase "
                            "implement_max_output_tokens in design_calibration."
                        ),
                    })

            # Multi-file format constraint: ensure LLM produces distinct blocks per file
            prompt_constraints = list(task.prompt_constraints)

            # Domain-aware output format constraint: prevent test code generation
            # for non-code artifacts (config YAML, JSON dashboards, runbooks, etc.).
            # The design doc may contain test examples that confuse the LLM into
            # generating test code instead of the target artifact.
            _target_ext = (
                Path(task.target_files[0]).suffix.lower()
                if task.target_files else ""
            )
            if _target_ext in (".yaml", ".yml") and task.domain in (
                "config-yaml", "unknown",
            ):
                prompt_constraints.append(
                    f"TARGET FILE FORMAT — you MUST generate ONLY a valid YAML "
                    f"configuration file for: {task.target_files[0]}. "
                    f"The output MUST be parseable by yaml.safe_load(). "
                    f"Do NOT generate Python test code, validation scripts, or "
                    f"documentation — even if the design document contains test "
                    f"examples. Those are for reference only, not implementation."
                )
            elif _target_ext == ".json":
                prompt_constraints.append(
                    f"TARGET FILE FORMAT — you MUST generate ONLY valid JSON "
                    f"for: {task.target_files[0]}. "
                    f"The output MUST be parseable by json.loads(). "
                    f"Do NOT generate Python test code or scripts."
                )
            elif _target_ext == ".md":
                prompt_constraints.append(
                    f"TARGET FILE FORMAT — you MUST generate a Markdown document "
                    f"for: {task.target_files[0]}. "
                    f"Do NOT generate Python code or test scripts."
                )

            if len(task.target_files) > 1:
                _task_mode = "create"
                if edit_mode_map and task.task_id in edit_mode_map:
                    _task_mode = edit_mode_map[task.task_id].mode

                if _task_mode != "edit":
                    file_list = ", ".join(task.target_files)
                    prompt_constraints.append(
                        f"MULTI-FILE OUTPUT REQUIRED — you MUST produce a SEPARATE fenced "
                        f"code block for EACH of these {len(task.target_files)} target files: "
                        f"{file_list}. "
                        f"First line of each block MUST be a comment with the full path "
                        f"(e.g. # src/package/__init__.py). "
                        f"If a file is a shared module implemented by downstream tasks, "
                        f"produce a minimal stub (imports, docstring, empty registrations). "
                        f"Every target file MUST have its own code block — omitting any "
                        f"file will cause the build to fail."
                    )
                    # Layer 3 (defense-in-depth): dedicated __init__.py constraint.
                    # Models commonly skip __init__.py because it's "just imports".
                    # This makes the requirement explicit and impossible to miss.
                    init_files = [f for f in task.target_files if f.endswith("__init__.py")]
                    if init_files:
                        init_list = ", ".join(init_files)
                        prompt_constraints.append(
                            f"PACKAGE __init__.py REQUIRED — {init_list} MUST have "
                            f"its own separate code block. Even a minimal file with "
                            f"imports and __all__ is required. The build will FAIL "
                            f"if any __init__.py is missing its own block."
                        )

                    # ── Downstream file detection ──────────────────────────────
                    # Reuse the already-computed downstream_map from Gate 2c
                    # (via _reconcile_design_downstream) instead of re-calling
                    # _detect_downstream_files() on the same design doc text.
                    _task_downstream_prompt = downstream_map.get(task.task_id, [])
                    if _task_downstream_prompt:
                        ds_list = ", ".join(_task_downstream_prompt)
                        prompt_constraints.append(
                            f"DOWNSTREAM FILE STUBS — the following files are marked "
                            f"as shared/downstream in the design doc: {ds_list}. "
                            f"You MUST still produce a code block for each one, but "
                            f"it can be a MINIMAL stub: module docstring, imports, "
                            f"empty __all__, and placeholder functions/classes. "
                            f"A 5-line stub is acceptable — omitting the file is NOT."
                        )
                        logger.info(
                            "IMPLEMENT: detected %d downstream files for task %s: %s",
                            len(_task_downstream_prompt), task.task_id, _task_downstream_prompt,
                        )

            # ── Gate 2c: shrink file_targets for downstream files ────────
            # If Gate 2c pre-stubbed some files, remove them from the
            # drafter's target list so it only implements files it's supposed
            # to.  Downstream files are already on disk as stubs.
            task_downstream = downstream_map.get(task.task_id, [])
            effective_targets = [
                f for f in task.target_files
                if f not in task_downstream
            ] if task_downstream else task.target_files

            # ── PCA-605c: merge design-discovered files into targets ──────
            # The DESIGN phase may split code into new files not in the
            # original target_files.  Merge them so IMPLEMENT generates
            # code for the right set of files.
            _discovered_targets = (
                design_results.get(task.task_id, {}).get("discovered_target_files")
            )
            if _discovered_targets:
                _before = list(effective_targets)
                effective_targets = list(
                    dict.fromkeys(effective_targets + _discovered_targets)
                )
                if effective_targets != _before:
                    logger.info(
                        "PCA-605c: task %s effective_targets expanded %s → %s",
                        task.task_id,
                        _before,
                        effective_targets,
                    )

            # ── AR-138: preflight output-size guard + split guidance ─────
            _effective_loc = task.estimated_loc
            if _design_lines:
                _effective_loc = max(_effective_loc, int(_design_lines * 0.6))
            _estimated_tokens = int((_effective_loc * 24) + (len(effective_targets) * 512))
            if isinstance(max_output_tokens, int) and max_output_tokens > 0:
                _estimated_tokens = max(_estimated_tokens, max_output_tokens)
            preflight_estimate = {
                "estimated_loc": _effective_loc,
                "estimated_tokens": _estimated_tokens,
                "safe_loc_limit": preflight_safe_loc_limit,
                "safe_token_limit": preflight_safe_token_limit,
                "target_file_count": len(effective_targets),
            }
            if (
                _effective_loc > preflight_safe_loc_limit
                or _estimated_tokens > preflight_safe_token_limit
            ):
                split_guidance = (
                    f"Task {task.task_id} exceeds IMPLEMENT preflight safe limits "
                    f"(loc={_effective_loc}, tokens={_estimated_tokens}). "
                    "Split into smaller execution units before regeneration."
                )
                logger.warning("IMPLEMENT: %s", split_guidance)
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "preflight_blocked_size",
                    "complexity_tier": "tier_2",
                    "reason": "preflight_size_limit_exceeded",
                    "split_guidance": split_guidance,
                    "preflight_estimate": preflight_estimate,
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="preflight_blocked_size",
                    phase="implement",
                )
                continue

            # ── AR-138: staleness/provenance classification metadata ─────
            provenance_files: list[dict[str, Any]] = []
            current_count = 0
            stale_count = 0
            missing_count = 0
            for _target in effective_targets:
                _state_hint = staleness_classification.get(_target)
                _exists = False
                if project_root_path:
                    try:
                        _exists = (Path(project_root_path) / _target).exists()
                    except (OSError, ValueError):
                        _exists = False
                if _exists:
                    if _state_hint == "stale":
                        _status = "stale"
                        stale_count += 1
                    else:
                        _status = "current"
                        current_count += 1
                else:
                    _status = "missing"
                    missing_count += 1
                provenance_files.append({
                    "path": _target,
                    "status": _status,
                    "staleness_hint": _state_hint,
                })
            artifact_provenance = {
                "files": provenance_files,
                "summary": {
                    "current": current_count,
                    "stale": stale_count,
                    "missing": missing_count,
                },
            }
            reuse_decision = (
                "reuse_candidate"
                if stale_count == 0 and missing_count == 0 and current_count > 0
                else "regenerate_required"
            )

            # Strip dependencies on tasks not in this run (already completed
            # or filtered out by --task-filter).  The plan validator rejects
            # references to non-existent chunks.
            in_scope_deps = [d for d in task.depends_on if d in active_task_ids]

            # ── IMP-7: DESIGN→IMPLEMENT parameter completeness validation ──
            # Check that resolved_parameters from the seed are present in the
            # design document. Missing parameters indicate information loss at
            # the DESIGN bottleneck.
            design_completeness_warning = ""
            _param_completeness = task_design.get("parameter_completeness")
            if (
                isinstance(_param_completeness, dict)
                and _param_completeness.get("missing_count", 0)
            ):
                _missing = _param_completeness.get("missing", []) or []
                _missing_preview = ", ".join(
                    f"{m.get('key')}={m.get('value')}"
                    for m in _missing[:5]
                    if isinstance(m, dict)
                )
                design_completeness_warning = (
                    f"WARNING: {_param_completeness.get('missing_count', 0)} "
                    f"resolved parameter(s) missing from DESIGN specification: "
                    f"{_missing_preview}. Include them verbatim in implementation."
                )
            elif design_doc_text:
                _task_seed = design_results.get(task.task_id, {})
                _seed_config = _task_seed.get("_seed_config", {})
                _resolved = _seed_config.get("resolved_parameters", {})
                if not _resolved:
                    # Also check additional_context from the task
                    _resolved = {}
                    for atype in task.artifact_types_addressed:
                        for k, v in (parameter_sources or {}).get(atype, {}).items():
                            if isinstance(v, str):
                                _resolved[k] = v
                missing_params: list[str] = []
                for param_key, param_val in _resolved.items():
                    val_str = str(param_val)
                    if val_str and val_str not in design_doc_text:
                        missing_params.append(f"{param_key}={val_str}")
                if missing_params:
                    design_completeness_warning = (
                        f"WARNING: {len(missing_params)} resolved parameter(s) "
                        f"not found in design document: {', '.join(missing_params[:5])}. "
                        f"These may have been lost at the DESIGN bottleneck. "
                        f"Include them verbatim in your implementation."
                    )
                    logger.warning(
                        "IMP-7 DESIGN→IMPLEMENT gate: task %s missing %d parameter(s) "
                        "in design doc: %s",
                        task.task_id,
                        len(missing_params),
                        ", ".join(missing_params[:5]),
                    )

            # ── Phase 5: Forward Manifest Interface Contracts ──────
            _forward_contracts = None
            forward_manifest = kwargs.get("forward_manifest")
            if forward_manifest is not None:
                # Lazy import inside the loop to avoid circular import overhead
                from startd8.contractors.artisan_phases.design_prompts.seed_mapping import map_forward_contracts_for_task
                from startd8.contractors.artisan_phases.design_prompts.modules import ContractModule
                _contract_data = map_forward_contracts_for_task(task, forward_manifest=forward_manifest)
                if _contract_data:
                    _fragment = ContractModule().render(_contract_data)
                    if _fragment and _fragment.text:
                        _forward_contracts = _fragment.text
                        logger.info(
                            "IMPLEMENT: injected forward contracts for task %s",
                            task.task_id,
                        )

            # ── Phase 6: Skeleton file detection for body-only prompting ──
            _skeleton_file_list: str | None = None
            _skeleton_files_present = False
            _scaffold_data = scaffold_output or {}
            _file_stubs = _scaffold_data.get("file_stubs", [])
            _asm_degraded = _scaffold_data.get("assembly_degraded", False)
            if _file_stubs and not _asm_degraded:
                _task_skeleton_lines: list[str] = []
                for stub in _file_stubs:
                    stub_status = stub.get("status", "") if isinstance(stub, dict) else getattr(stub, "status", "")
                    stub_path = stub.get("file_path", "") if isinstance(stub, dict) else getattr(stub, "file_path", "")
                    if stub_status == "created" and stub_path in set(effective_targets):
                        _task_skeleton_lines.append(f"- `{stub_path}`")
                if _task_skeleton_lines:
                    _skeleton_files_present = True
                    _skeleton_file_list = "\n".join(_task_skeleton_lines)
                    logger.info(
                        "IMPLEMENT: %d skeleton file(s) detected for task %s",
                        len(_task_skeleton_lines), task.task_id,
                    )

            # FR-MPA-005: Compute per-task pre-filled vs. unfilled element lists
            # from ingestion-time element_tiers, for prompt narrowing.
            _pre_filled_elements: list[str] | None = None
            _unfilled_elements: list[str] | None = None
            if element_tiers:
                _pf: list[str] = []
                _uf: list[str] = []
                for fp in effective_targets:
                    file_tiers = element_tiers.get(fp, {})
                    for qname, tier_info in file_tiers.items():
                        if not isinstance(tier_info, dict):
                            continue
                        if tier_info.get("pre_filled"):
                            src = tier_info.get("fill_source", "template")
                            _pf.append(f"{qname} ({src})")
                        else:
                            _uf.append(qname)
                if _pf or _uf:
                    _pre_filled_elements = _pf or None
                    _unfilled_elements = _uf or None
                    logger.info(
                        "IMPLEMENT: task %s — %d pre-filled, %d unfilled elements",
                        task.task_id, len(_pf), len(_uf),
                    )

            # Micro Prime pre-pass: determine if this chunk was fully filled locally
            _mp_complete = False
            _mp_skeletons: dict[str, str] | None = None
            _mp_escalated: list[dict[str, Any]] | None = None
            if micro_prime_result:
                _mp_filled = micro_prime_result.get("filled_skeletons") or {}
                _mp_esc_all = micro_prime_result.get("escalated_elements") or []
                _target_set = set(effective_targets)
                _mp_skeletons = {t: _mp_filled[t] for t in effective_targets if t in _mp_filled}
                _mp_escalated = [e for e in _mp_esc_all if e.get("file_path") in _target_set]
                _mp_complete = (
                    len(_mp_skeletons) == len(effective_targets)
                    and len(effective_targets) > 0
                    and len(_mp_escalated) == 0
                )

            chunks.append(DevelopmentChunk(
                chunk_id=task.task_id,
                description=task.description,
                dependencies=in_scope_deps,
                file_targets=effective_targets,
                implementation_prompt=task.description,
                test_commands=[],  # Post-gen validation via DomainChecklist
                max_retries=max_retries,
                metadata={
                    "feature_id": task.feature_id,
                    "domain": task.domain,
                    "estimated_loc": task.estimated_loc,
                    "prompt_constraints": prompt_constraints,
                    "environment_checks": env_checks,
                    "post_generation_validators": task.post_generation_validators,
                    "title": task.title,
                    "design_document": design_doc_text,
                    "design_document_missing": design_doc_text is None,
                    "_design_lines": _design_lines,
                    "_design_sections": _design_sections,
                    "max_output_tokens": max_output_tokens,
                    "preflight_estimate": preflight_estimate,
                    "artifact_provenance": artifact_provenance,
                    "reuse_decision": reuse_decision,
                    "artifact_types_addressed": task.artifact_types_addressed,
                    "downstream_files": task_downstream,
                    "original_target_files": task.target_files if task_downstream else None,
                    # IMP-7: DESIGN→IMPLEMENT parameter completeness warning
                    "design_completeness_warning": design_completeness_warning,
                    # PCA-300: project architecture for code generation
                    "architectural_context": architectural_context or {},
                    "plan_goals": (plan_goals or [])[:5],
                    "plan_context": (plan_context or "")[:4000] or None,
                    # PCA-301/400: service metadata for protocol compliance
                    "service_metadata": service_metadata if service_metadata else None,
                    # PCA-403: cross-feature context accumulation
                    "prior_implementations": (prior_impl_summaries or [])[-3:] if prior_impl_summaries else None,
                    # PCA-404: requirements text for IMPLEMENT prompt
                    "requirements_text": task.requirements_text[:3000] if task.requirements_text else None,
                    # PCA-501: project identity for edit-first behavior
                    "project_name": project_name,
                    "project_root_path": project_root_path,
                    # PCA-600: edit mode classification from upstream signals
                    "_edit_mode": (edit_mode_map or {}).get(task.task_id, EditModeClassification(
                        mode="create", per_file={}, confidence="low",
                    )).to_dict() if edit_mode_map else None,
                    # AR-822: module inventory from SCAFFOLD for import grounding
                    "module_inventory": module_inventory or [],
                    # Mottainai Rule 5: parameter provenance for IMPLEMENT prompt
                    "parameter_sources": parameter_sources or {},
                    "semantic_conventions": semantic_conventions or {},
                    # Phase 5: Forward interface contracts
                    "forward_contracts": _forward_contracts,
                    # Phase 6: Skeleton file detection for body-only prompting
                    "skeleton_file_list": _skeleton_file_list,
                    "skeleton_files_present": _skeleton_files_present,
                    # REQ-CMR-042: per-task override from seed JSON
                    "complexity_tier_override": task.complexity_tier_override,
                    # FR-MPA-005: Pre-assembly prompt narrowing data
                    "_pre_filled_elements": _pre_filled_elements,
                    "_unfilled_elements": _unfilled_elements,
                    # Micro Prime pre-pass: per-chunk fill status
                    "_micro_prime_complete": _mp_complete,
                    "_micro_prime_filled_skeletons": _mp_skeletons if _mp_skeletons else None,
                    "_micro_prime_escalated": _mp_escalated if _mp_escalated else None,
                },
            ))

        # ── Layer 1: aggregate handoff log ────────────────────────────
        tasks_with_design = sum(
            1 for c in chunks if c.metadata.get("design_document")
        )
        logger.info(
            "DESIGN→IMPLEMENT handoff: %d/%d tasks have design documents",
            tasks_with_design,
            len(chunks),
        )

        return chunks, skipped

    def _map_development_result(
        self,
        dev_result: Any,  # DevelopmentResult
        chunks: list[Any],  # list[DevelopmentChunk]
        tasks: list[SeedTask],
        skipped_reports: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, GenerationResult], float]:
        """Map DevelopmentResult back to the output format downstream expects.

        Reconstructs ``generation_results`` (dict[str, GenerationResult])
        from chunk metadata where ``PrimaryContractorChunkExecutor`` stored them.

        Args:
            dev_result: The DevelopmentResult from DevelopmentPhase.run().
            chunks: The DevelopmentChunk list (with metadata populated).
            tasks: Original SeedTask list for domain grouping.
            skipped_reports: Pre-filtered env-blocked task reports.

        Returns:
            Tuple of (output_dict, generation_results, total_cost).
        """
        from startd8.contractors.artisan_phases.development import ChunkStatus

        chunk_map = {c.chunk_id: c for c in chunks}
        generation_results: dict[str, GenerationResult] = {}
        task_reports: list[dict[str, Any]] = list(skipped_reports)
        total_cost = 0.0

        for chunk_id, state in dev_result.chunk_states.items():
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue

            meta = chunk.metadata
            gen_result = meta.get("_generation_result")

            task_report: dict[str, Any] = {
                "task_id": chunk_id,
                "feature_id": meta.get("feature_id", ""),
                "title": meta.get("title", ""),
                "domain": meta.get("domain", "unknown"),
                "complexity_tier": meta.get("_complexity_tier", "tier_2"),
                "target_files": chunk.file_targets,
                "estimated_loc": meta.get("estimated_loc", 0),
                "depends_on": chunk.dependencies,
                "prompt_constraints_count": len(meta.get("prompt_constraints", [])),
                "validators": meta.get("post_generation_validators", []),
                # PCA-505: track whether existing files were present for review
                "had_existing_files": bool(meta.get("_existing_file_contents")),
                # AR-138: IMPLEMENT preflight + provenance audit fields
                "preflight_estimate": meta.get("preflight_estimate"),
                "artifact_provenance": meta.get("artifact_provenance"),
                "reuse_decision": meta.get("reuse_decision"),
            }

            # Surface missing target files (Fix 3: missing file detection)
            missing_targets = meta.get("_missing_targets")
            if missing_targets:
                task_report["missing_targets"] = missing_targets

            # Surface design document absence for downstream phases (Issue 4)
            if meta.get("design_document_missing"):
                task_report["design_document_missing"] = True

            if state.status == ChunkStatus.PASSED and gen_result is not None:
                task_report["status"] = "generated"
                task_report["cost"] = gen_result.cost_usd
                task_report["tokens"] = {
                    "input": gen_result.input_tokens,
                    "output": gen_result.output_tokens,
                }
                task_report["iterations"] = gen_result.iterations
                generation_results[chunk_id] = gen_result
                total_cost += gen_result.cost_usd
            elif state.status == ChunkStatus.FAILED:
                task_report["status"] = "generation_failed"
                task_report["error"] = state.last_error or "Unknown failure"
                if gen_result is not None:
                    task_report["cost"] = gen_result.cost_usd
                    task_report["tokens"] = {
                        "input": gen_result.input_tokens,
                        "output": gen_result.output_tokens,
                    }
                    task_report["iterations"] = gen_result.iterations
                    generation_results[chunk_id] = gen_result
                    total_cost += gen_result.cost_usd
            elif state.status == ChunkStatus.SKIPPED:
                task_report["status"] = "dep_blocked"
                task_report["error"] = state.last_error or "Dependency not satisfied"
            else:
                task_report["status"] = "unknown"

            _log_task_boundary_complete(
                chunk_id,
                status=str(task_report.get("status", "unknown")),
                phase="implement",
                cost_usd=_coerce_optional_float(task_report.get("cost")),
            )
            task_reports.append(task_report)

        # Domain breakdown
        domain_tasks: dict[str, list[str]] = defaultdict(list)
        for task in tasks:
            domain_tasks[task.domain].append(task.task_id)

        output: dict[str, Any] = {
            "task_reports": task_reports,
            "tasks_processed": len(task_reports),
            "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
            "total_estimated_loc": sum(t.estimated_loc for t in tasks),
            "total_cost": total_cost,
            "generation_results": {
                tid: {"success": r.success, "error": r.error, "cost": r.cost_usd}
                for tid, r in generation_results.items()
            },
            "development_result_summary": dev_result.summary,
            "execution_order": dev_result.execution_order,
        }

        return output, generation_results, total_cost

    @staticmethod
    def _run_development_phase(
        dev_phase: Any,
        plan: Any,
        timeout: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Any:
        """Run DevelopmentPhase in a dedicated thread-owned event loop.

        Using a dedicated thread avoids nested event-loop errors when the
        caller is already inside an async runtime (e.g. notebooks, test
        harnesses, or async servers).

        Args:
            dev_phase: The DevelopmentPhase instance.
            plan: The DevelopmentPlan to execute.
            timeout: Maximum seconds to wait for the thread. ``None``
                means wait indefinitely (the orchestrator's own timeout
                still applies at the outer level).
            cancel_event: Optional :class:`threading.Event` for cooperative
                cancellation. When set after a timeout, signals the background
                thread to stop initiating new LLM calls.
        """
        result_box: dict[str, Any] = {}
        error_box: dict[str, Exception] = {}
        parent_ctx = capture_context()
        # OT-710: Capture boundary result for thread propagation
        from startd8.contractors.forensic_log import (
            get_boundary_result,
            set_boundary_result,
            reset_boundary_result,
        )
        parent_boundary_result = get_boundary_result()

        def _runner() -> None:
            token = attach_context(parent_ctx)
            br_token = set_boundary_result(parent_boundary_result)
            try:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result_box["result"] = loop.run_until_complete(
                        dev_phase.run(plan)
                    )
                except Exception as exc:  # pragma: no cover - propagated
                    error_box["error"] = exc
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            finally:
                reset_boundary_result(br_token)
                detach_context(token)

        # daemon=True is intentional: if the main process exits (e.g.
        # KeyboardInterrupt or SIGTERM), we don't want this thread to keep
        # the process alive indefinitely.  For *cooperative* shutdown the
        # cancel_event is preferred — setting it tells the DevelopmentPhase
        # to stop initiating new LLM calls.  daemon=True is the fallback
        # for uncooperative exits where cancel_event alone isn't enough.
        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # M-12: Race guard — the thread may have completed between
            # join() returning and the is_alive() check.  If result_box
            # was populated the work *did* finish; treat it as success
            # rather than raising a false TimeoutError.
            if "result" in result_box or "error" in error_box:
                logger.debug(
                    "DevelopmentPhase thread reported alive after join() "
                    "but result_box is populated — treating as completed",
                )
            else:
                if cancel_event:
                    cancel_event.set()
                    logger.warning(
                        "Cancel event set — signalling background DevelopmentPhase "
                        "thread to stop initiating new LLM calls",
                    )
                logger.error(
                    "DevelopmentPhase did not complete within %.0fs — "
                    "abandoning background thread (daemon=True)",
                    timeout,
                )
                raise TimeoutError(
                    f"DevelopmentPhase.run() did not complete within {timeout}s"
                )

        if "error" in error_box:
            raise error_box["error"]
        return result_box["result"]

    # ------------------------------------------------------------------
    # Resume cache validation (v2 format)
    # ------------------------------------------------------------------

    def _validate_resume_cache(
        self,
        saved: dict[str, Any],
        tasks: list[SeedTask],
        project_root: Path,
        source_checksum: str | None,
        design_results: dict[str, Any] | None = None,
    ) -> dict[str, GenerationResult] | None:
        """Validate a saved generation_results cache through 8 ordered layers.

        Returns a dict of task_id → GenerationResult if all layers pass,
        or None if the cache should be rejected (caller falls through to
        fresh IMPLEMENT).

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Filter success:false entries (info log)
            2: Coverage — all current task IDs present in successful entries
            3: Source checksum — _cache_meta.source_checksum matches context
            3b: Design hash — design_results hash matches context (catches
                ``--force-design`` invalidation; mirrors TEST/REVIEW Layer 1.5)
            4: Path validation — cached generated_files match task.target_files
            5: File existence — every cached file exists on disk
            6: Content hash — sha256(file_bytes) matches cached content_hashes
        """
        # Layer 0: Schema version
        cache_meta = saved.get("_cache_meta")
        if not isinstance(cache_meta, dict):
            logger.warning(
                "IMPLEMENT --resume: cache missing _cache_meta (v1 or corrupt) — re-running"
            )
            return None
        schema_version = cache_meta.get("schema_version")
        if schema_version != _CACHE_SCHEMA_VERSION:
            logger.warning(
                "IMPLEMENT --resume: cache schema_version=%s (expected %d) — re-running",
                schema_version, _CACHE_SCHEMA_VERSION,
            )
            return None

        tasks_data = saved.get("tasks", {})

        # Layer 1: Filter out failed entries
        successful: dict[str, dict[str, Any]] = {}
        filtered_count = 0
        for tid, data in tasks_data.items():
            if data.get("success"):
                successful[tid] = data
            else:
                filtered_count += 1
        if filtered_count:
            logger.info(
                "IMPLEMENT --resume: filtered %d failed entries from cache",
                filtered_count,
            )

        # Layer 2: Coverage — all current task IDs in successful cache entries
        current_ids = {t.task_id for t in tasks}
        missing = current_ids - set(successful)
        if missing:
            logger.warning(
                "IMPLEMENT --resume: cache missing tasks %s — re-running",
                sorted(missing),
            )
            return None

        # Layer 3: Source checksum
        cached_checksum = cache_meta.get("source_checksum")
        if (
            cached_checksum is not None
            and source_checksum is not None
            and cached_checksum != source_checksum
        ):
            logger.warning(
                "IMPLEMENT --resume: source_checksum mismatch "
                "(cached=%s, current=%s) — re-running",
                cached_checksum, source_checksum,
            )
            return None
        elif cached_checksum is not None or source_checksum is not None:
            logger.warning(
                "IMPLEMENT --resume: Layer 3 (source checksum): partial checksum — "
                "cache has %s, current has %s — cannot verify integrity",
                "checksum" if cached_checksum else "None",
                "checksum" if source_checksum else "None",
            )

        # Layer 3b: Design hash — invalidate when design changes
        # (mirrors TEST/REVIEW Layer 1.5; catches --force-design)
        cached_design_hash = cache_meta.get("design_hash")
        if cached_design_hash is not None and design_results is not None:
            current_design_hash = _compute_design_results_hash(design_results)
            if (
                current_design_hash is not None
                and current_design_hash != cached_design_hash
            ):
                logger.warning(
                    "IMPLEMENT --resume: design_hash mismatch "
                    "(cached=%s, current=%s) — design changed since last "
                    "IMPLEMENT; re-running to regenerate from new design",
                    cached_design_hash[:16], current_design_hash[:16],
                )
                return None
            logger.debug(
                "IMPLEMENT --resume: Layer 3b (design hash): match",
            )
        elif cached_design_hash is not None:
            logger.info(
                "IMPLEMENT --resume: Layer 3b: cache has design_hash but "
                "current context has no design_results — cannot verify; "
                "proceeding (design may not have changed)",
            )

        # Parse GenerationResult objects from successful entries
        generation_results: dict[str, GenerationResult] = {}
        task_map = {t.task_id: t for t in tasks}
        for tid in current_ids:
            data = successful[tid]
            generation_results[tid] = GenerationResult(
                success=data["success"],
                generated_files=[Path(p) for p in data.get("generated_files", [])],
                error=data.get("error"),
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
                cost_usd=data.get("cost_usd", 0.0),
                iterations=data.get("iterations", 0),
                model=data.get("model", "unknown"),
                metadata=data.get("metadata", {}),
            )

        # Layer 4: Path validation — cached generated_files match task.target_files
        for tid, gr in generation_results.items():
            task = task_map.get(tid)
            if task is None or not gr.generated_files:
                continue
            expected = {
                str((project_root / tf).resolve())
                for tf in task.target_files
            }
            actual = {str(Path(p).resolve()) for p in gr.generated_files}
            if actual != expected:
                logger.warning(
                    "IMPLEMENT --resume: path mismatch for %s "
                    "(expected %s, got %s) — re-running",
                    tid, sorted(expected), sorted(actual),
                )
                return None

        # Layer 5: File existence — every cached file exists on disk
        for tid, gr in generation_results.items():
            for p in gr.generated_files:
                if not Path(p).exists():
                    logger.warning(
                        "IMPLEMENT --resume: cached file missing from disk: %s "
                        "(task %s) — re-running",
                        p, tid,
                    )
                    return None

        # Layer 6: Content hash — sha256(file_bytes) matches cached content_hashes
        for tid in current_ids:
            data = successful[tid]
            content_hashes = data.get("content_hashes", {})
            for fpath, expected_hash in content_hashes.items():
                fp = Path(fpath)
                if not fp.exists():
                    # Already caught by Layer 5, but guard anyway
                    logger.warning(
                        "IMPLEMENT --resume: hash check file missing: %s — re-running",
                        fpath,
                    )
                    return None
                actual_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    logger.warning(
                        "IMPLEMENT --resume: content hash mismatch for %s "
                        "(task %s, expected %s, got %s) — re-running",
                        fpath, tid, expected_hash[:12], actual_hash[:12],
                    )
                    return None

        logger.info(
            "IMPLEMENT --resume: all %d layers passed for %d tasks",
            8, len(generation_results),
        )
        return generation_results

    @staticmethod
    def _build_implementation_metadata(context: dict[str, Any]) -> dict[str, Any]:
        """Build the metadata sub-dict mirroring propagation chain fields."""
        tier_distribution = context.get("_tier_distribution")
        if not isinstance(tier_distribution, dict):
            tier_distribution = {"tier_1": 0, "tier_2": 0, "tier_3": 0}
            for report in context.get("implementation", {}).get("task_reports", []):
                tier = report.get("complexity_tier", "tier_2")
                if tier in tier_distribution:
                    tier_distribution[tier] += 1
        return {
            "design_mode_summary": context.get("design_mode_summary", {}),
            "service_metadata": context.get("service_metadata"),
            "_tier_distribution": tier_distribution,
        }

    # ------------------------------------------------------------------
    # REQ-IME-300: Inner loop implementation engine path
    # ------------------------------------------------------------------

    def _execute_with_inner_loop(
        self,
        tasks: list[SeedTask],
        context: dict[str, Any],
        project_root: Path,
        start_time: float,
    ) -> dict[str, Any]:
        """Execute IMPLEMENT phase using the implementation engine's
        iterative spec-draft-review loop.

        This replaces the single-shot DevelopmentPhase with a per-task
        engine pipeline that produces a spec, then iterates draft-review
        cycles until the review passes or max iterations are reached.

        Falls back to logging errors on per-task failures
        (REQ-IME-502: Mottainai Rule 3).

        Returns the same output structure as the standard execute() path
        so downstream phases (INTEGRATE, TEST, REVIEW, FINALIZE) require
        zero code changes (REQ-IME-303).
        """
        from startd8.implementation_engine import (
            DefaultImplementationEngine,
        )

        config = self.config
        staging_dir = Path(config.staging_dir) if config.staging_dir else (
            project_root / ".startd8" / "staging"
        )
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Resolve agent specs
        drafter_spec = config.inner_loop_drafter or config.drafter_agent
        reviewer_spec = config.inner_loop_reviewer or config.lead_agent

        # REQ-IME-502: Validate reviewer is configured (don't mutate shared config)
        if not reviewer_spec:
            logger.warning(
                "IMPLEMENT inner loop: no reviewer agent configured — "
                "falling back to single-shot DevelopmentPhase for all tasks"
            )
            return {
                "output": {"error": "inner_loop_reviewer not configured"},
                "cost": 0.0,
                "metadata": {"duration": time.monotonic() - start_time},
            }

        engine = DefaultImplementationEngine()
        generation_results: dict[str, GenerationResult] = {}
        task_reports: list[dict[str, Any]] = []
        total_cost = 0.0
        truncation_flags: dict[str, dict[str, Any]] = {}

        # --- Pre-IMPLEMENT setup (mirrors standard path) ---

        # Pre-IMPLEMENT: warn about risky multi-file tasks (Gap 4)
        self._validate_multi_file_tasks(tasks)

        # Item 12 (Gap 5): scaffold test files for artifact generator tasks
        if config.scaffold_test_first:
            self._ensure_test_scaffolding_for_artifact_tasks(
                tasks, project_root,
            )

        # Gate 2c (Gap 2): pre-stub downstream files and build downstream_map
        design_results = context.get("design_results", {})
        pre_computed_dm = context.get("_downstream_map")
        if pre_computed_dm is not None:
            downstream_map: dict[str, list[str]] = pre_computed_dm
            logger.debug(
                "IMPLEMENT inner loop: using pre-computed "
                "_downstream_map (%d entries)",
                len(downstream_map),
            )
        else:
            downstream_map = self._reconcile_design_downstream(
                tasks, design_results, project_root,
            )

        # PCA-600: Build per-task edit mode classification
        # (mirrors standard path edit_mode_map computation)
        scaffold = context.get("scaffold", {})
        design_mode_summary = context.get("design_mode_summary", {})
        _mode_evidence = context.get("design_mode_evidence", {})
        _manifest_registry_for_edit = None
        if config.manifest_consumption_enabled:
            _manifest_registry_for_edit = (
                config.manifest_registry or context.get("project_manifests")
            )
        edit_mode_map: dict[str, EditModeClassification] = {}
        for task in tasks:
            edit_mode_map[task.task_id] = self._classify_edit_mode(
                task, scaffold, design_mode_summary,
                design_mode_evidence=_mode_evidence,
                manifest_registry=_manifest_registry_for_edit,
            )
        context["edit_mode_classifications"] = {
            tid: cls.to_dict() for tid, cls in edit_mode_map.items()
        }
        edit_tasks = sum(1 for v in edit_mode_map.values() if v.mode == "edit")
        logger.info(
            "IMPLEMENT inner loop: edit mode classification: %d edit, %d create",
            edit_tasks, len(tasks) - edit_tasks,
        )

        # --- Gap 6: Manifest staleness check (advisory) ---
        _design_checksums = context.get("manifest_file_checksums", {})
        if _design_checksums and project_root:
            _current_checksums = _compute_manifest_file_checksums(
                list(_design_checksums.keys()), str(project_root),
            )
            _stale_files = [
                fpath for fpath, expected in _design_checksums.items()
                if fpath in _current_checksums
                and _current_checksums[fpath] != expected
            ]
            if _stale_files:
                logger.warning(
                    "IMPLEMENT inner loop Gap 6: %d target file(s) "
                    "changed since DESIGN: %s",
                    len(_stale_files),
                    ", ".join(_stale_files[:5]),
                )
                context["_manifest_stale_files"] = _stale_files

        # --- Gap 6: Phantom element warnings (advisory) ---
        _phantom_warnings: dict[str, list[str]] = {}
        _design_refs = context.get("design_referenced_elements", {})
        if _design_refs and _manifest_registry_for_edit is not None:
            for tid, file_refs in _design_refs.items():
                for fpath, elements in file_refs.items():
                    try:
                        _current_summary = (
                            _manifest_registry_for_edit.file_element_summary(
                                fpath, 5000,
                            )
                        )
                    except (AttributeError, TypeError, OSError):
                        _current_summary = None
                    if not _current_summary:
                        continue
                    for elem in elements:
                        if elem not in _current_summary:
                            _phantom_warnings.setdefault(tid, []).append(
                                f"{fpath}:{elem}",
                            )
            if _phantom_warnings:
                context["_phantom_element_warnings"] = _phantom_warnings
                logger.warning(
                    "IMPLEMENT inner loop Gap 6: %d task(s) have "
                    "phantom element references",
                    len(_phantom_warnings),
                )

        # CMR: Complexity-Driven Model Router (mirrors standard path 8563-8630)
        from startd8.contractors.artisan_phases.development import (
            TaskComplexityTier,
        )
        import types as _types

        task_tiers: dict[str, TaskComplexityTier] = {}
        _tier_distribution: dict[str, int] = {"tier_1": 0, "tier_2": 0, "tier_3": 0}

        if config.complexity_routing_enabled:
            _cmr_manifest = None
            if config.manifest_consumption_enabled:
                _cmr_manifest = (
                    config.manifest_registry or context.get("project_manifests")
                )

            for task in tasks:
                try:
                    _cmr_meta: dict[str, Any] = {}
                    # Inject call graph callers from manifest registry
                    if _cmr_manifest and task.target_files:
                        _cg_callers_cmr: list[dict[str, Any]] = []
                        for tf in task.target_files:
                            try:
                                callers_map = _cmr_manifest.callers_of_file(tf)
                                for fqn, callers in callers_map.items():
                                    br = _cmr_manifest.blast_radius(
                                        fqn,
                                        max_depth=config.blast_radius_max_depth,
                                    )
                                    _cg_callers_cmr.append({
                                        "fqn": fqn,
                                        "direct_callers": sorted(callers),
                                        "blast_radius": len(br),
                                    })
                            except Exception:
                                logger.debug(
                                    "IMPLEMENT CMR: call graph callers enrichment "
                                    "failed for %s in task %s",
                                    tf, task.task_id, exc_info=True,
                                )
                        if _cg_callers_cmr:
                            _cmr_meta["_call_graph_callers"] = _cg_callers_cmr

                    # Edit mode from classification
                    _edit_cls = edit_mode_map.get(task.task_id)
                    if _edit_cls:
                        _cmr_meta["_edit_mode"] = _edit_cls.to_dict()

                    # Estimated LOC from task
                    if hasattr(task, "estimated_loc") and task.estimated_loc:
                        _cmr_meta["estimated_loc"] = task.estimated_loc

                    # Build chunk-like object for CMR functions
                    _chunk_like = _types.SimpleNamespace(
                        metadata=_cmr_meta,
                        file_targets=task.target_files or [],
                        chunk_id=task.task_id,
                    )

                    signals = _extract_complexity_signals(_chunk_like, _cmr_manifest)
                    tier = _classify_complexity_tier(signals, config)
                    task_tiers[task.task_id] = tier
                    _tier_distribution[tier.value] += 1

                    logger.info(
                        "CMR inner loop: task=%s tier=%s blast=%d callers=%d "
                        "edit=%s loc=%d",
                        task.task_id, tier.value,
                        signals.blast_radius, signals.caller_count,
                        signals.edit_mode, signals.estimated_loc,
                    )
                except Exception:
                    task_tiers[task.task_id] = TaskComplexityTier.TIER_2
                    _tier_distribution["tier_2"] += 1
                    logger.warning(
                        "CMR inner loop: classification failed for %s, "
                        "defaulting to tier_2",
                        task.task_id, exc_info=True,
                    )
        else:
            for task in tasks:
                task_tiers[task.task_id] = TaskComplexityTier.TIER_2
                _tier_distribution["tier_2"] += 1

        context["_tier_distribution"] = _tier_distribution

        # Resume check: load prior generation results if available
        results_path = project_root / ".startd8" / "state" / "generation_results.json"
        resumed = False
        resumed_cost = 0.0

        _is_retry_inner = bool(context.get("_retry_attempt", 0))
        if not config.force_implement and not _is_retry_inner and results_path.exists():
            try:
                saved = json.loads(results_path.read_text(encoding="utf-8"))
                cached_results = self._validate_resume_cache(
                    saved, tasks, project_root,
                    source_checksum=context.get("source_checksum"),
                    design_results=context.get("design_results"),
                )
                if cached_results is not None:
                    generation_results = cached_results
                    resumed = True
                    resumed_cost = sum(
                        gr.cost_usd for gr in cached_results.values()
                    )
                    # Report zero cost for resumed phase — no LLM calls were
                    # made.  Historical cost tracked in metadata["resumed_cost"].
                    total_cost = 0.0
                    truncation_flags = saved.get("truncation_flags", {})
                    # Restore downstream_map from cache (mirrors legacy path Fix 1)
                    _cached_dm = saved.get("downstream_map", {})
                    if isinstance(_cached_dm, dict) and _cached_dm:
                        downstream_map = _cached_dm
                    logger.info(
                        "IMPLEMENT inner loop: resumed %d tasks from cache ($%.4f)",
                        len(cached_results), resumed_cost,
                    )
            except (
                json.JSONDecodeError, KeyError, TypeError,
                OSError, ValueError, UnicodeDecodeError,
            ) as exc:
                logger.warning(
                    "IMPLEMENT inner loop: cache load failed: "
                    "%s — running fresh",
                    exc, exc_info=True,
                )

        # --- Env-block pre-filter (mirrors _tasks_to_chunks env check) ---
        env_blocked_ids: set[str] = set()
        skipped_reports: list[dict[str, Any]] = []
        eligible_tasks: list[SeedTask] = []
        for task in tasks:
            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            if env_fails:
                env_blocked_ids.add(task.task_id)
                logger.warning(
                    "IMPLEMENT inner loop: skipping task %s (%s) — "
                    "env_blocked (%d failing check(s))",
                    task.task_id, task.title, len(env_fails),
                )
                skipped_reports.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "env_blocked",
                    "complexity_tier": "tier_2",
                    "environment_issues": [
                        c for c in task.environment_checks
                        if c.get("status") in ("fail", "warn")
                    ],
                })
                _log_task_boundary_complete(
                    task.task_id, status="env_blocked",
                    phase="implement",
                )
            else:
                # Also check for dep-blocked (dependency on an env-blocked task)
                blocked_deps = [
                    d for d in task.depends_on if d in env_blocked_ids
                ]
                if blocked_deps:
                    logger.warning(
                        "IMPLEMENT inner loop: skipping task %s (%s) — "
                        "dep_blocked_env (blocked by: %s)",
                        task.task_id, task.title,
                        ", ".join(blocked_deps),
                    )
                    skipped_reports.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "status": "dep_blocked_env",
                        "complexity_tier": "tier_2",
                        "blocked_dependencies": blocked_deps,
                    })
                    _log_task_boundary_complete(
                        task.task_id, status="dep_blocked_env",
                        phase="implement",
                    )
                else:
                    eligible_tasks.append(task)

        if env_blocked_ids:
            logger.info(
                "IMPLEMENT inner loop: %d/%d tasks env-blocked, "
                "%d eligible for generation",
                len(env_blocked_ids), len(tasks), len(eligible_tasks),
            )

        if not resumed:
            self._execute_inner_loop_tasks(
                eligible_tasks, engine, config, context,
                design_results, staging_dir, project_root,
                drafter_spec, reviewer_spec,
                edit_mode_map, task_tiers,
                generation_results, task_reports,
                truncation_flags,
                downstream_map=downstream_map,
            )
            total_cost = sum(
                gr.cost_usd for gr in generation_results.values()
            )

        # --- Post-generation gates (mirrors standard path) ---

        # Gate 3: multi-file completeness
        gate3 = self._validate_generation_completeness(
            tasks, generation_results, project_root,
            downstream_map=downstream_map,
        )

        # Gate 3b: semantic content validation
        _svc_meta = context.get("service_metadata")
        gate3b = self._validate_generation_content(
            tasks, generation_results, project_root,
            service_metadata=_svc_meta,
        )

        # Gate 4: truncation detection
        existing_file_sizes: dict[str, dict[str, int]] = {}
        for task in tasks:
            task_sizes: dict[str, int] = {}
            task_edit_cls = edit_mode_map.get(task.task_id)
            if task_edit_cls and task_edit_cls.mode == "edit":
                for fpath in (task.target_files or []):
                    fp = project_root / fpath
                    if fp.is_file():
                        try:
                            task_sizes[fpath] = len(
                                fp.read_text(encoding="utf-8").splitlines()
                            )
                        except (OSError, UnicodeDecodeError):
                            logger.debug("Could not read file for size check: %s", fp, exc_info=True)
            if task_sizes:
                existing_file_sizes[task.task_id] = task_sizes

        truncation_flags_gate4 = self._validate_truncation(
            tasks, generation_results, project_root,
            existing_file_sizes=existing_file_sizes,
        )
        truncation_flags.update(truncation_flags_gate4)

        # ── Gate 5: Edit-First Enforcement (REQ-EFE-020) ──
        from startd8.contractors.edit_first_gate import (
            validate_task_size_regression,
            resolve_threshold,
            emit_rejection_telemetry,
        )
        from startd8.utils.code_extraction import extract_code_from_response
        import types as _types_g5

        gate5_results: dict[str, Any] = {}
        _output_contracts = context.get("onboarding_output_contracts")
        _schema_features = context.get("onboarding_schema_features")

        # Resolve a retry agent lazily (only if needed)
        _retry_agent = None
        _retry_executor = None

        for task in tasks:
            gr = generation_results.get(task.task_id)
            if gr is None or not gr.success:
                continue

            task_edit_cls = edit_mode_map.get(task.task_id)
            if not task_edit_cls or task_edit_cls.mode != "edit":
                continue  # New-file task — no size regression possible

            # Read existing file contents for comparison
            chunk_efc: dict[str, str] = {}
            for fpath in (task.target_files or []):
                fp = project_root / fpath
                if fp.is_file():
                    try:
                        chunk_efc[fpath] = fp.read_text(
                            encoding="utf-8", errors="replace",
                        )
                    except OSError:
                        logger.debug("Could not read existing file: %s", fp, exc_info=True)
            if not chunk_efc:
                continue

            # Read generated file content from staging
            gen_file_contents: dict[str, str] = {}
            for gen_path in gr.generated_files:
                fp = Path(gen_path)
                if fp.exists():
                    try:
                        rel_key = str(fp.relative_to(staging_dir))
                    except ValueError:
                        # Fallback: use full path string to avoid
                        # name-only collisions across directories.
                        rel_key = str(fp)
                    try:
                        gen_file_contents[rel_key] = fp.read_text(
                            encoding="utf-8",
                        )
                    except (OSError, UnicodeDecodeError):
                        logger.debug("Could not read generated file: %s", fp, exc_info=True)
            if not gen_file_contents:
                continue

            # Resolve threshold
            artifact_types = [
                task.artifact_type,
            ] if hasattr(task, "artifact_type") and task.artifact_type else [
                "source_code",
            ]
            threshold = resolve_threshold(
                artifact_types=artifact_types,
                output_contracts=_output_contracts,
                schema_features=_schema_features,
            )

            gate_result = validate_task_size_regression(
                task_id=task.task_id,
                generated_files=gen_file_contents,
                existing_contents=chunk_efc,
                threshold=threshold,
                artifact_type=(
                    artifact_types[0] if artifact_types else "unknown"
                ),
                force_rewrite=config.force_rewrite,
            )

            if gate_result.any_rejected:
                # Emit rejection telemetry
                try:
                    from opentelemetry import trace as _g5_trace
                    _g5_span = _g5_trace.get_current_span()
                    emit_rejection_telemetry(gate_result, _g5_span)
                except (
                    ImportError, TypeError, AttributeError,
                    RuntimeError, NameError,
                ):
                    logger.debug("Auto-lint import failed", exc_info=True)

                # Lazy-resolve retry agent (once per run)
                if _retry_agent is None:
                    try:
                        from startd8.utils.agent_resolution import (
                            resolve_agent_spec,
                        )
                        _retry_agent = resolve_agent_spec(drafter_spec)
                        _retry_executor = _types_g5.SimpleNamespace(
                            agent=_retry_agent,
                        )
                    except Exception as agent_exc:
                        logger.warning(
                            "Gate 5: cannot resolve retry agent %s: %s",
                            drafter_spec, agent_exc,
                        )

                if _retry_executor is not None:
                    retry_succeeded = self._attempt_edit_first_retry(
                        task, gate_result, chunk_efc, context,
                        gr, _retry_executor, staging_dir, threshold,
                        extract_code_from_response,
                    )

                    # Re-evaluate after retry
                    still_rejected = any(
                        f.action == "rejected"
                        for f in gate_result.file_results
                    )
                    gate_result.any_rejected = still_rejected
                    gate_result.retry_succeeded = (
                        retry_succeeded and not still_rejected
                    )

            gate5_results[task.task_id] = {
                "any_rejected": gate_result.any_rejected,
                "retry_needed": gate_result.retry_needed,
                "retry_succeeded": gate_result.retry_succeeded,
                "file_results": [
                    {
                        "file_path": fr.file_path,
                        "input_chars": fr.input_chars,
                        "output_chars": fr.output_chars,
                        "ratio": round(fr.ratio, 2),
                        "threshold": fr.threshold,
                        "artifact_type": fr.artifact_type,
                        "passed": fr.passed,
                        "action": fr.action,
                    }
                    for fr in gate_result.file_results
                ],
            }

        if gate5_results:
            rejected_count = sum(
                1 for r in gate5_results.values() if r["any_rejected"]
            )
            if rejected_count:
                logger.warning(
                    "Gate 5: %d task(s) with edit-first size regression",
                    rejected_count,
                )
            else:
                logger.info(
                    "Gate 5: edit-first gate passed for %d task(s)",
                    len(gate5_results),
                )
        context["edit_first_gate_results"] = gate5_results

        # Persist generation_results to disk for crash recovery (v2 envelope)
        try:
            save_path = project_root / ".startd8" / "state" / "generation_results.json"
            serializable_tasks: dict[str, dict[str, Any]] = {}
            for tid, gr in generation_results.items():
                content_hashes: dict[str, str] = {}
                for p in gr.generated_files:
                    fp = Path(p)
                    if fp.exists():
                        content_hashes[str(p)] = hashlib.sha256(
                            fp.read_bytes()
                        ).hexdigest()
                serializable_tasks[tid] = {
                    "success": gr.success,
                    "generated_files": [str(p) for p in gr.generated_files],
                    "content_hashes": content_hashes,
                    "error": gr.error,
                    "input_tokens": gr.input_tokens,
                    "output_tokens": gr.output_tokens,
                    "cost_usd": gr.cost_usd,
                    "iterations": gr.iterations,
                    "model": gr.model,
                }
            cache_envelope: dict[str, Any] = {
                "_cache_meta": {
                    "schema_version": _CACHE_SCHEMA_VERSION,
                    "created_at": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "source_checksum": context.get("source_checksum"),
                    "design_hash": _compute_design_results_hash(
                        context.get("design_results", {})
                    ),
                },
                "truncation_flags": truncation_flags,
                "downstream_map": downstream_map,
                "edit_first_gate_results": gate5_results,
                "tasks": serializable_tasks,
            }
            save_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(save_path, cache_envelope, indent=2)
            logger.info(
                "IMPLEMENT inner loop: saved %d generation results to %s",
                len(generation_results), save_path,
            )
        except Exception as exc:
            logger.warning(
                "IMPLEMENT inner loop: failed to write cache: %s (non-fatal)",
                exc, exc_info=True,
            )

        # --- Assemble output (same structure as DevelopmentPhase path) ---
        # Merge env-blocked skipped reports into task_reports
        task_reports.extend(skipped_reports)

        if not task_reports:
            # Build task reports for resumed path
            for task in tasks:
                gr = generation_results.get(task.task_id)
                report: dict[str, Any] = {
                    "task_id": task.task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "status": "resumed",
                    "complexity_tier": task_tiers.get(
                        task.task_id, TaskComplexityTier.TIER_2,
                    ).value,
                }
                if gr is not None:
                    report["cost_usd"] = gr.cost_usd
                    report["iterations"] = gr.iterations
                    report["files_generated"] = len(gr.generated_files)
                task_reports.append(report)

        output: dict[str, Any] = {
            "task_reports": task_reports,
            "tasks_processed": len(task_reports),
            "total_cost": total_cost,
            "generation_results": generation_results,
        }

        if gate3:
            output["_gate3_validation"] = gate3
        if gate3b:
            output["_gate3b_content_validation"] = gate3b
        if truncation_flags_gate4:
            output["_gate4_truncation"] = truncation_flags_gate4
        # Gate 5 results (only include if any rejections)
        if gate5_results:
            rejected_count = sum(
                1 for r in gate5_results.values() if r["any_rejected"]
            )
            if rejected_count:
                output["_gate5_edit_first"] = gate5_results

        context["implementation"] = output
        # C-2 fix: normalize any dict entries to GenerationResult so downstream
        # phases can safely access .cost_usd / .success without AttributeError.
        generation_results = {
            tid: _dict_to_gen_result(v) if isinstance(v, dict) else v
            for tid, v in generation_results.items()
        }
        context["generation_results"] = generation_results
        context["truncation_flags"] = truncation_flags
        output["metadata"] = self._build_implementation_metadata(context)

        # Gap 3: Context propagation for downstream phases (REVIEW, TEST)
        # PCA-403: accumulate prior implementation summaries
        prior_summaries = context.get("_prior_impl_summaries", [])
        for task_id_ps, gr_ps in generation_results.items():
            if gr_ps.success:
                prior_summaries.append({
                    "task_id": task_id_ps,
                    "files": [str(p) for p in gr_ps.generated_files[:5]],
                })
        context["_prior_impl_summaries"] = prior_summaries[-3:]

        # Propagate downstream_map to REVIEW phase
        if downstream_map:
            context["_downstream_map"] = downstream_map

        # Context contract validation
        ImplementPhaseOutput(
            implementation=context["implementation"],
            generation_results=context["generation_results"],
            truncation_flags=context["truncation_flags"],
        )

        duration = time.monotonic() - start_time
        logger.info(
            "IMPLEMENT phase complete (inner loop): %d tasks, $%.4f (%.2fs)",
            len(task_reports), total_cost, duration,
        )
        return {
            "output": output,
            "cost": total_cost,
            "metadata": {
                "duration": duration,
                "resumed": resumed,
                "engine": "implementation_engine",
                **({"resumed_cost": resumed_cost} if resumed else {}),
            },
        }

    def _execute_inner_loop_tasks(
        self,
        tasks: list[SeedTask],
        engine: Any,
        config: "HandlerConfig",
        context: dict[str, Any],
        design_results: dict[str, Any],
        staging_dir: Path,
        project_root: Path,
        drafter_spec: str,
        reviewer_spec: str,
        edit_mode_map: dict[str, EditModeClassification],
        task_tiers: dict[str, Any],
        generation_results: dict[str, GenerationResult],
        task_reports: list[dict[str, Any]],
        truncation_flags: dict[str, dict[str, Any]],
        *,
        downstream_map: dict[str, list[str]] | None = None,
    ) -> None:
        """Run the inner loop engine for each task, populating results in-place."""
        from startd8.implementation_engine import EngineRequest
        from startd8.contractors.artisan_phases.development import (
            TaskComplexityTier,
        )

        for task in tasks:
            task_id = task.task_id
            _log_task_boundary_start(task, phase="implement")

            try:
                # --- Build EngineRequest ---
                engine_context: dict[str, Any] = {}

                # REQ-IME-301: Design document forwarding
                task_design = design_results.get(task_id, {})
                design_doc = task_design.get("design_document")
                _design_doc_missing = False

                # Gate: skip tasks whose DESIGN phase explicitly failed.
                _design_status = task_design.get("status", "")
                if _design_status == "design_failed":
                    _gate_mode = context.get("quality_gate_summary", {}).get(
                        "policy_mode", "warn"
                    )
                    if _gate_mode == "block":
                        logger.warning(
                            "Inner loop task %s: DESIGN failed — skipping "
                            "IMPLEMENT per block policy",
                            task_id,
                        )
                        generation_results[task_id] = GenerationResult(
                            text="", time_ms=0,
                            token_usage={"input": 0, "output": 0},
                            success=False,
                            error="design_failed: skipped by quality gate (block)",
                            metadata={"design_gated": True},
                        )
                        task_reports.append({
                            "task_id": task_id, "status": "design_gated",
                            "error": "DESIGN failed — skipped per block policy",
                        })
                        _log_task_boundary_complete(
                            task_id, status="design_gated",
                            phase="implement",
                        )
                        continue
                    else:
                        logger.warning(
                            "Inner loop task %s: DESIGN failed — skipping "
                            "per %s policy (no design document)",
                            task_id, _gate_mode,
                        )
                        generation_results[task_id] = GenerationResult(
                            text="", time_ms=0,
                            token_usage={"input": 0, "output": 0},
                            success=False,
                            error=f"design_failed: skipped by quality gate ({_gate_mode})",
                            metadata={"design_gated": True},
                        )
                        task_reports.append({
                            "task_id": task_id, "status": "design_gated",
                            "error": f"DESIGN failed — skipped per {_gate_mode} policy",
                        })
                        _log_task_boundary_complete(
                            task_id, status="design_gated",
                            phase="implement",
                        )
                        continue

                if design_doc:
                    engine_context["design_document"] = design_doc
                else:
                    _design_doc_missing = True
                    logger.warning(
                        "Inner loop task %s: no design document available — "
                        "falling back to spec template (Prime route). "
                        "Downstream phases will see design_document_missing flag.",
                        task_id,
                    )

                # REQ-IME-305: Existing file content injection
                existing_files: dict[str, str] = {}
                task_edit_cls = edit_mode_map.get(task_id)
                task_edit_mode = task_edit_cls.to_dict() if task_edit_cls else None
                for target_file in (task.target_files or []):
                    fpath = project_root / target_file
                    if fpath.is_file():
                        try:
                            existing_files[target_file] = fpath.read_text(
                                encoding="utf-8", errors="replace"
                            )
                        except OSError as err:
                            logger.warning(
                                "Inner loop: cannot read %s: %s",
                                target_file, err,
                            )

                # Forward pipeline context
                for key in (
                    "plan_context", "architectural_context",
                    "project_objectives", "semantic_conventions",
                    "domain_constraints", "requirements_text",
                    # Keys already handled by spec_builder but not previously forwarded
                    "forward_contracts", "critical_parameters",
                    "parameter_sources", "requirements_context",
                    "protocol_guidance", "scope_boundary",
                    # FLCM: full manifest object for task-specific constraints
                    "forward_manifest",
                ):
                    val = context.get(key)
                    if val:
                        engine_context[key] = val

                # Phase 4/5/6: Manifest + call graph enrichment
                # (mirrors ImplementPhaseHandler lines 8375-8428)
                _manifest_registry = None
                if config.manifest_consumption_enabled:
                    _manifest_registry = (
                        config.manifest_registry
                        or context.get("project_manifests")
                    )
                if _manifest_registry is not None and task.target_files:
                    _enable_introspect = getattr(
                        config, "enable_introspect", False,
                    )
                    _manifest_budget = config.manifest_context_budget

                    # Phase 4 (IM-1–IM-4) + Phase 5 (IM-1): element summaries
                    _mc_parts: list[str] = []
                    for tf in task.target_files:
                        summary = _manifest_registry.file_element_summary(
                            tf, _manifest_budget,
                            include_resolved_types=_enable_introspect,
                        )
                        if summary:
                            _mc_parts.append(f"### {tf}\n{summary}")
                    if _mc_parts:
                        engine_context["manifest_context"] = "\n\n".join(
                            _mc_parts,
                        )

                    # Phase 6 (CG-IM-1,2,4): call graph summary + callers
                    _cg_budget = config.call_graph_context_budget
                    _cg_parts: list[str] = []
                    _cg_callers: list[dict[str, Any]] = []
                    for tf in task.target_files:
                        try:
                            cg_summary = _manifest_registry.call_graph_summary(
                                tf, _cg_budget,
                            )
                            if cg_summary:
                                _cg_parts.append(f"### {tf}\n{cg_summary}")
                            callers_map = _manifest_registry.callers_of_file(tf)
                            for fqn, callers in callers_map.items():
                                br = _manifest_registry.blast_radius(
                                    fqn,
                                    max_depth=config.blast_radius_max_depth,
                                )
                                _cg_callers.append({
                                    "fqn": fqn,
                                    "direct_callers": sorted(callers),
                                    "blast_radius": len(br),
                                })
                        except Exception:
                            logger.debug(
                                "Inner loop: call graph enrichment failed "
                                "for %s", tf, exc_info=True,
                            )
                    if _cg_parts:
                        engine_context["call_graph_context"] = "\n\n".join(
                            _cg_parts,
                        )
                    if _cg_callers:
                        engine_context["call_graph_callers"] = _cg_callers

                    # Phase 5 (DS-2, DS-4): MRO + runtime attributes
                    if _enable_introspect:
                        _introspect_parts: list[str] = []
                        for tf in task.target_files:
                            try:
                                mro_map = _manifest_registry.file_mro_summary(
                                    tf,
                                )
                                if mro_map:
                                    for cls, chain in mro_map.items():
                                        if len(chain) > 2:
                                            _introspect_parts.append(
                                                f"- {cls} MRO: "
                                                f"{' → '.join(chain)}"
                                            )
                                ra_map = (
                                    _manifest_registry.file_runtime_attributes(
                                        tf,
                                    )
                                )
                                if ra_map:
                                    for elem, attrs in ra_map.items():
                                        _introspect_parts.append(
                                            f"- {elem} runtime attrs: "
                                            f"{', '.join(attrs)}"
                                        )
                            except Exception:
                                logger.debug(
                                    "Inner loop: introspect enrichment "
                                    "failed for %s", tf, exc_info=True,
                                )
                        if _introspect_parts:
                            engine_context[
                                "manifest_introspect_context"
                            ] = "\n".join(_introspect_parts)

                # CMR: select per-task drafter based on complexity tier
                _task_tier = task_tiers.get(
                    task_id, TaskComplexityTier.TIER_2,
                )
                if (
                    _task_tier == TaskComplexityTier.TIER_3
                    and config.tier3_agent
                ):
                    _task_drafter = config.tier3_agent
                else:
                    _task_drafter = drafter_spec

                request = EngineRequest(
                    task_description=task.description or task.title,
                    context=engine_context,
                    drafter_agent_spec=_task_drafter,
                    reviewer_agent_spec=reviewer_spec,
                    max_iterations=config.inner_loop_max_iterations,
                    pass_threshold=config.inner_loop_pass_threshold,
                    existing_files=existing_files or None,
                    edit_mode=task_edit_mode,
                    target_files=task.target_files,
                    check_truncation=config.check_truncation,
                    strict_truncation=config.strict_truncation,
                    fail_on_api_truncation=config.fail_on_truncation,
                    fail_on_heuristic_truncation=False,
                )

                # --- Execute engine ---
                result = engine.build_and_execute(request)

                # --- Map to GenerationResult format (REQ-IME-303) ---
                generated_files: dict[str, str] = {}
                if result.final_code and task.target_files:
                    if len(task.target_files) == 1:
                        generated_files[task.target_files[0]] = result.final_code
                    else:
                        from startd8.utils.code_extraction import (
                            extract_multi_file_code,
                        )
                        raw = result.last_raw_response or result.final_code
                        generated_files = extract_multi_file_code(
                            raw, task.target_files,
                        )

                # Write to staging
                for rel_path, code in generated_files.items():
                    out_path = staging_dir / rel_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(code, encoding="utf-8")

                _gen_file_paths: list[Path] = [
                    staging_dir / rel_path for rel_path in generated_files
                ]
                gen_result = GenerationResult(
                    success=bool(result.final_code),
                    generated_files=_gen_file_paths,
                    error=result.error,
                    input_tokens=result.total_input_tokens,
                    output_tokens=result.total_output_tokens,
                    cost_usd=result.total_cost,
                    iterations=result.iterations_used,
                    model=_task_drafter,
                    metadata={
                        "engine_result": result.to_serializable_summary(),
                        "_edit_mode": (
                            task_edit_cls.to_dict()
                            if task_edit_cls
                            else None
                        ),
                        "_complexity_tier": _task_tier.value,
                        **({"design_document_missing": True} if _design_doc_missing else {}),
                    },
                )

                generation_results[task_id] = gen_result

                if result.truncation_events:
                    truncation_flags[task_id] = {
                        "events": result.truncation_events,
                    }

                _task_report: dict[str, Any] = {
                    "task_id": task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "status": (
                        "engine_passed" if result.passed else "engine_completed"
                    ),
                    "iterations": result.iterations_used,
                    "review_passed": result.passed,
                    "cost_usd": result.total_cost,
                    "files_generated": len(gen_result.generated_files),
                    "complexity_tier": _task_tier.value,
                }
                if _design_doc_missing:
                    _task_report["design_document_missing"] = True
                task_reports.append(_task_report)

                _log_task_boundary_complete(
                    task_id,
                    status="passed" if result.passed else "completed",
                    phase="implement",
                )

            except Exception as exc:
                # REQ-IME-304: Per-task error guard
                logger.warning(
                    "IMPLEMENT inner loop: task %s failed — %s. "
                    "Marking as failed (graceful degradation).",
                    task_id, exc, exc_info=True,
                )
                _err_tier = task_tiers.get(
                    task_id, TaskComplexityTier.TIER_2,
                )
                generation_results[task_id] = GenerationResult(
                    success=False,
                    generated_files=[],
                    error=str(exc),
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    iterations=0,
                    model=drafter_spec,
                    metadata={"_complexity_tier": _err_tier.value},
                )
                task_reports.append({
                    "task_id": task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "status": "engine_error",
                    "error": str(exc),
                    "iterations": 0,
                    "review_passed": False,
                    "cost_usd": 0.0,
                    "files_generated": 0,
                    "complexity_tier": _err_tier.value,
                })
                _log_task_boundary_complete(
                    task_id, status="error", phase="implement",
                )

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    @staticmethod
    def _bridge_retry_feedback(context: dict[str, Any]) -> bool:
        """Bridge AR-153 orchestrator retry feedback into DevelopmentPhase keys.

        The orchestrator (_execute_feature) sets ``prior_error_feedback`` and
        ``retry_feedback`` when rewinding to IMPLEMENT after an
        INTEGRATE/TEST/REVIEW failure.  DevelopmentPhase reads
        ``last_error`` and ``test_output``.  This method bridges the two
        so the LLM receives error-informed retry context.

        Returns True if retry feedback was bridged (i.e. this is a retry).
        """
        retry_attempt = context.get("_retry_attempt", 0)
        if not retry_attempt:
            return False

        # Bridge primary error feedback
        prior_feedback = context.get("prior_error_feedback")
        if prior_feedback and not context.get("last_error"):
            context["last_error"] = prior_feedback

        # Extract structured test/review failure details for the LLM
        retry_fb = context.get("retry_feedback")
        if isinstance(retry_fb, dict) and not context.get("test_output"):
            details = retry_fb.get("details", {})
            source_phase = retry_fb.get("source_phase", "")
            detail_parts: list[str] = []

            test_failures = details.get("test_failures")
            if isinstance(test_failures, dict):
                for tid, info in test_failures.items():
                    if isinstance(info, dict):
                        failures = info.get("failures", [])
                        detail_parts.append(
                            f"Task {tid}: {len(failures)} validator(s) failed — "
                            + ", ".join(str(f) for f in failures[:5])
                        )

            review_failures = details.get("review_failures")
            if isinstance(review_failures, dict):
                for tid, info in review_failures.items():
                    score = info.get("score", "?") if isinstance(info, dict) else info
                    detail_parts.append(f"Task {tid}: review score {score}")

            integration_failures = details.get("integration_failures")
            if isinstance(integration_failures, dict):
                for tid, info in integration_failures.items():
                    reason = (
                        info.get("error", "unknown")
                        if isinstance(info, dict) else str(info)
                    )
                    detail_parts.append(f"Task {tid}: integration failed — {reason}")

            if detail_parts:
                context["test_output"] = (
                    f"[{source_phase.upper()} phase failures]\n"
                    + "\n".join(detail_parts)
                )

        logger.info(
            "IMPLEMENT: AR-153 retry %d — bridged prior_error_feedback → last_error",
            retry_attempt,
        )
        return True

    def _build_existing_file_sizes(
        self,
        chunks: list,
        project_root: Path,
    ) -> dict[str, dict[str, int]]:
        """PCA-603: line counts of edit-mode files per chunk, for Gate 4 size regression.

        Uses ``_existing_file_contents`` populated by PCA-502 disk reads; for edit-mode
        files missing from cache (PCA-603 AC 6), attempts a fresh disk read as fallback.
        """
        existing_file_sizes: dict[str, dict[str, int]] = {}
        for chunk in chunks:
            _efc = chunk.metadata.get("_existing_file_contents", {})
            _edit_mode_dict = chunk.metadata.get("_edit_mode")
            task_sizes: dict[str, int] = {}

            if _efc:
                for epath, econtent in _efc.items():
                    task_sizes[epath] = len(econtent.splitlines())

            # Fallback: check for edit-mode files missing from cache
            if _edit_mode_dict and _edit_mode_dict.get("mode") == "edit":
                per_file_modes = _edit_mode_dict.get("per_file", {})
                for fpath, finfo in per_file_modes.items():
                    if finfo.get("mode") == "edit" and fpath not in task_sizes:
                        logger.warning(
                            "Edit-mode file %s has no cached content for "
                            "size regression check — attempting fresh disk "
                            "read as fallback.",
                            fpath,
                        )
                        try:
                            fallback_path = project_root / fpath
                            fallback_content = fallback_path.read_text(
                                encoding="utf-8",
                            )
                            task_sizes[fpath] = len(
                                fallback_content.splitlines(),
                            )
                        except (OSError, UnicodeDecodeError) as exc:
                            logger.warning(
                                "Edit-mode file %s: fallback disk read "
                                "failed (%s) — size regression guard "
                                "bypassed for this file.",
                                fpath, exc,
                            )

            if task_sizes:
                existing_file_sizes[chunk.chunk_id] = task_sizes
        return existing_file_sizes

    def _execute_dry_run(
        self,
        tasks: list[SeedTask],
        context: dict[str, Any],
        start: float,
    ) -> dict[str, Any]:
        """Dry-run path of ``execute``: report per-task plans without generating."""
        task_reports: list[dict[str, Any]] = []
        for task in tasks:
            _log_task_boundary_start(task, phase="implement")
            env_checks = self._check_environment(task)
            task_report: dict[str, Any] = {
                "task_id": task.task_id,
                "feature_id": task.feature_id,
                "title": task.title,
                "domain": task.domain,
                "complexity_tier": "tier_2",
                "target_files": task.target_files,
                "estimated_loc": task.estimated_loc,
                "depends_on": task.depends_on,
                "prompt_constraints_count": len(task.prompt_constraints),
                "validators": task.post_generation_validators,
                "status": "dry_run_skipped",
            }
            if env_checks:
                task_report["environment_issues"] = env_checks
            task_reports.append(task_report)
            _log_task_boundary_complete(
                task.task_id,
                status=str(task_report["status"]),
                phase="implement",
            )

        domain_tasks: dict[str, list[str]] = defaultdict(list)
        for task in tasks:
            domain_tasks[task.domain].append(task.task_id)

        output = {
            "task_reports": task_reports,
            "tasks_processed": len(task_reports),
            "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
            "total_estimated_loc": sum(t.estimated_loc for t in tasks),
            "total_cost": 0.0,
            "generation_results": {},
        }
        context["implementation"] = output
        output["metadata"] = self._build_implementation_metadata(context)
        context["generation_results"] = {}
        context["truncation_flags"] = {}

        # Context contract: validate IMPLEMENT output model (dry-run path)
        ImplementPhaseOutput(
            implementation=context["implementation"],
            generation_results=context["generation_results"],
            truncation_flags=context["truncation_flags"],
        )

        duration = time.monotonic() - start
        logger.info(
            "IMPLEMENT phase complete (dry-run): %d tasks (%.2fs)",
            len(task_reports), duration,
        )
        return {"output": output, "cost": 0.0, "metadata": {"duration": duration, "resumed": False}}

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("IMPLEMENT", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        _project_root_str = context.get("project_root")
        project_root = Path(_project_root_str) if _project_root_str and _project_root_str.strip() else Path(".")
        _has_explicit_project_root = bool(_project_root_str and _project_root_str.strip())

        # AR-153: Bridge orchestrator retry feedback into DevelopmentPhase keys.
        # Must run before cache check so _is_retry can gate cache loading.
        _is_retry = self._bridge_retry_feedback(context)

        logger.info(
            "IMPLEMENT phase: processing %d tasks (dry_run=%s, retry=%s)",
            len(tasks), dry_run, _is_retry,
        )

        # --- Pre-IMPLEMENT validation: warn about risky multi-file tasks ---
        self._validate_multi_file_tasks(tasks)

        # --- Dry-run path (unchanged) ---
        if dry_run:
            return self._execute_dry_run(tasks, context, start)

        # --- REQ-MP-503: Micro Prime pre-pass (opt-in) ---
        if self.config.micro_prime_enabled:
            self._run_micro_prime_prepass(context, project_root)

        # --- REQ-IME-300: Inner loop path (opt-in) ---
        if self.config.enable_inner_loop:
            return self._execute_with_inner_loop(
                tasks, context, project_root, start,
            )

        # --- Real-mode path: delegate to DevelopmentPhase ---
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
            DevelopmentPhase,
            DevelopmentPlan,
            DefaultTestRunner,
            JsonFileStateStore,
        )

        # --- Resume check: load prior generation results if available ---
        # Skip resume when force_implement is set (ignore cache, always run fresh).
        # Skip when no explicit project_root (matches REVIEW's pattern).
        results_path = project_root / ".startd8" / "state" / "generation_results.json"
        # Backward compat: check legacy location
        if not results_path.exists():
            _legacy = project_root / ".startd8_state" / "generation_results.json"
            if _legacy.exists():
                results_path = _legacy
        resumed = False
        downstream_map: dict[str, list[str]] = {}
        truncation_flags: dict[str, dict[str, Any]] = {}
        if not _has_explicit_project_root:
            logger.info("IMPLEMENT: no explicit project_root — skipping cache load")
        # AR-153: On retry, determine which tasks need regeneration.
        # Only failed tasks are regenerated; passing tasks reuse cache.
        _retry_failed_tasks: set[str] = set()
        if _is_retry:
            _rfb = context.get("retry_feedback")
            if isinstance(_rfb, dict):
                _rft = _rfb.get("failed_tasks", [])
                if isinstance(_rft, list):
                    _retry_failed_tasks = set(_rft)
            # If no specific failed tasks identified, fall back to
            # regenerating all tasks (original behavior).
            if not _retry_failed_tasks:
                logger.info(
                    "IMPLEMENT: AR-153 retry with no specific failed_tasks — "
                    "regenerating all tasks",
                )

        if (
            _has_explicit_project_root
            and results_path.exists()
            and not dry_run
            and not self.config.force_implement
            and not (_is_retry and not _retry_failed_tasks)  # AR-153: skip cache only when no specific failed tasks
        ):
            try:
                with open(results_path) as f:
                    saved = json.load(f)
                validated = self._validate_resume_cache(
                    saved, tasks, project_root,
                    source_checksum=context.get("source_checksum"),
                    design_results=context.get("design_results"),
                )
                if validated is not None:
                    generation_results = validated
                    current_task_ids = {t.task_id for t in tasks}

                    # AR-153 scoped retry: evict failed tasks from cache
                    # so they get regenerated while passing tasks are reused.
                    if _retry_failed_tasks:
                        _evicted = {
                            tid for tid in _retry_failed_tasks
                            if tid in generation_results
                        }
                        for tid in _evicted:
                            del generation_results[tid]
                        if _evicted:
                            logger.info(
                                "IMPLEMENT: AR-153 scoped retry — evicted %d/%d "
                                "failed task(s) from cache, reusing %d passing: %s",
                                len(_evicted),
                                len(_retry_failed_tasks),
                                len(generation_results),
                                sorted(_evicted),
                            )
                        else:
                            logger.info(
                                "IMPLEMENT: AR-153 scoped retry — none of %d "
                                "failed task(s) found in cache; full regeneration "
                                "will run: %s",
                                len(_retry_failed_tasks),
                                sorted(_retry_failed_tasks),
                            )
                        # Don't mark as fully resumed — the evicted tasks
                        # will fall through to the fresh generation path.
                        # Store partial cache for merging after regeneration.
                        context["_retry_cached_results"] = dict(generation_results)
                    else:
                        # Fix 1: Restore downstream_map from cache
                        downstream_map = saved.get("downstream_map", {})
                        if not isinstance(downstream_map, dict):
                            logger.warning(
                                "IMPLEMENT resume: downstream_map is not a dict, resetting"
                            )
                            downstream_map = {}

                        # Restore truncation_flags from cache (v3+; graceful for v2)
                        truncation_flags = saved.get("truncation_flags", {})
                        if not isinstance(truncation_flags, dict):
                            logger.warning(
                                "IMPLEMENT resume: truncation_flags is not a dict, resetting"
                            )
                            truncation_flags = {}

                        # Fix 2: Report zero cost for resumed phase (no LLM
                        # calls were made).  Track historical cost separately.
                        total_cost = 0.0
                        resumed_cost = sum(
                            r.cost_usd for tid, r in generation_results.items()
                            if tid in current_task_ids
                        )
                        if resumed_cost == 0.0:
                            logger.info(
                                "IMPLEMENT --resume: historical cost is $0.00 "
                                "(%d cached results, %d current tasks)",
                                len(generation_results),
                                len(current_task_ids),
                            )

                        domain_tasks: dict[str, list[str]] = defaultdict(list)
                        for task in tasks:
                            domain_tasks[task.domain].append(task.task_id)

                        task_reports: list[dict[str, Any]] = []
                        for task in tasks:
                            _log_task_boundary_start(task, phase="implement")
                            gr = generation_results.get(task.task_id)
                            report: dict[str, Any] = {
                                "task_id": task.task_id,
                                "feature_id": task.feature_id,
                                "title": task.title,
                                "domain": task.domain,
                                "complexity_tier": "tier_2",
                                "target_files": task.target_files,
                                "estimated_loc": task.estimated_loc,
                                "depends_on": task.depends_on,
                                "prompt_constraints_count": len(task.prompt_constraints),
                                "validators": task.post_generation_validators,
                            }
                            if gr is not None:
                                report["status"] = "generated" if gr.success else "generation_failed"
                                report["cost"] = gr.cost_usd
                                report["tokens"] = {
                                    "input": gr.input_tokens,
                                    "output": gr.output_tokens,
                                }
                                report["iterations"] = gr.iterations
                                if gr.error:
                                    report["error"] = gr.error
                            else:
                                report["status"] = "not_in_saved_results"
                            task_reports.append(report)
                            _log_task_boundary_complete(
                                task.task_id,
                                status=str(report["status"]),
                                phase="implement",
                                cost_usd=_coerce_optional_float(report.get("cost")),
                            )

                        output: dict[str, Any] = {
                            "task_reports": task_reports,
                            "tasks_processed": len(task_reports),
                            "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
                            "total_estimated_loc": sum(t.estimated_loc for t in tasks),
                            "total_cost": total_cost,
                            "generation_results": {
                                tid: {"success": r.success, "error": r.error, "cost": r.cost_usd}
                                for tid, r in generation_results.items()
                                if tid in current_task_ids
                            },
                            # Structural parity with fresh-run output
                            "development_result_summary": "resumed from cache",
                            "execution_order": [list(current_task_ids)],
                        }
                        resumed = True
            except (json.JSONDecodeError, KeyError, TypeError, OSError, ValueError, UnicodeDecodeError) as exc:
                logger.warning(
                    "IMPLEMENT --resume: could not load cache: %s — re-running",
                    exc,
                )

        _retry_cached: dict[str, Any] | None = None
        _generation_tasks = tasks
        if not resumed:
            # AR-153 scoped retry: filter tasks to only regenerate failed ones
            # when partial cache was loaded above.
            _retry_cached = context.pop("_retry_cached_results", None)
            if _retry_cached and _retry_failed_tasks:
                _generation_tasks = [
                    t for t in tasks if t.task_id in _retry_failed_tasks
                ]
                logger.info(
                    "IMPLEMENT: AR-153 scoped retry — regenerating %d/%d tasks: %s",
                    len(_generation_tasks),
                    len(tasks),
                    [t.task_id for t in _generation_tasks],
                )

            # Item 12: scaffold test files for artifact generator tasks first
            if self.config.scaffold_test_first:
                self._ensure_test_scaffolding_for_artifact_tasks(
                    _generation_tasks, project_root
                )

            # Convert SeedTasks → DevelopmentChunks (with env pre-filter)
            # Inject design documents from the DESIGN phase into chunk metadata
            design_results = context.get("design_results", {})
            calibration_map = context.get("design_calibration", {})

            # Gate 2c: Reconcile design doc downstream designations.
            # Pre-stubs downstream files on disk and returns a mapping so
            # _tasks_to_chunks can exclude them from drafter targets.
            #
            # In wave mode, pre-stubbing runs on the main thread BEFORE
            # lane dispatch (R8-S6) to prevent filesystem write races.
            # The pre-computed result is stored in context["_downstream_map"].
            # If present, reuse it; otherwise compute here (non-wave modes).
            pre_computed_dm = context.get("_downstream_map")
            if pre_computed_dm is not None:
                downstream_map = pre_computed_dm
                logger.debug(
                    "IMPLEMENT: using pre-computed _downstream_map (%d entries)",
                    len(downstream_map),
                )
            else:
                downstream_map = self._reconcile_design_downstream(
                    tasks, design_results, project_root,
                )

            # PCA-501: derive project name from plan_title with fallback
            _project_name = context.get("plan_title") or project_root.name

            # REQ-EMM-007: Resolve manifest registry BEFORE classification
            # so it is available as the 6th signal in _classify_edit_mode().
            _impl_manifest_registry = None
            if self.config.manifest_consumption_enabled:
                _impl_manifest_registry = (
                    self.config.manifest_registry
                    or context.get("project_manifests")
                )

            # PCA-600: Build per-task edit mode classification from upstream signals
            scaffold = context.get("scaffold", {})
            design_mode_summary = context.get("design_mode_summary", {})
            _mode_evidence = context.get("design_mode_evidence", {})
            edit_mode_map: dict[str, EditModeClassification] = {}
            for task in tasks:
                edit_mode_map[task.task_id] = self._classify_edit_mode(
                    task, scaffold, design_mode_summary,
                    design_mode_evidence=_mode_evidence,
                    manifest_registry=_impl_manifest_registry,
                )
            edit_tasks = sum(1 for v in edit_mode_map.values() if v.mode == "edit")
            conflict_tasks = sum(1 for v in edit_mode_map.values() if v.signal_conflicts)
            _signal_count = 6 if _impl_manifest_registry is not None else 5
            logger.info(
                "IMPLEMENT: edit mode classification: %d edit, %d create "
                "(%d with signal conflicts) (from %d upstream signals, 2-tier weighted consensus)",
                edit_tasks, len(tasks) - edit_tasks, conflict_tasks, _signal_count,
            )
            # PCA-600 AC 9: Persist structured classifications for post-hoc debugging
            context["edit_mode_classifications"] = {
                task_id: classification.to_dict()
                for task_id, classification in edit_mode_map.items()
            }

            # Gap 2: Manifest staleness check — compare design-time checksums
            # against current file state to detect drift between split runs.
            _design_checksums = context.get("manifest_file_checksums", {})
            if _design_checksums and project_root:
                _current_checksums = _compute_manifest_file_checksums(
                    list(_design_checksums.keys()), str(project_root),
                )
                _stale_files = [
                    fpath for fpath, expected in _design_checksums.items()
                    if fpath in _current_checksums
                    and _current_checksums[fpath] != expected
                ]
                if _stale_files:
                    logger.warning(
                        "IMPLEMENT Gap 2: %d target file(s) changed since DESIGN — "
                        "design docs may reference stale structure: %s",
                        len(_stale_files),
                        ", ".join(_stale_files[:5]),
                    )
                    context["_manifest_stale_files"] = _stale_files

            # Gap 1: Phantom element warnings — elements referenced in design
            # but not found in manifest at IMPLEMENT time.
            # NOTE: _impl_manifest_registry was resolved above (REQ-EMM-007).
            _phantom_warnings: dict[str, list[str]] = {}
            _design_refs = context.get("design_referenced_elements", {})
            if _design_refs and _impl_manifest_registry is not None:
                for tid, file_refs in _design_refs.items():
                    for fpath, elements in file_refs.items():
                        try:
                            _current_summary = _impl_manifest_registry.file_element_summary(
                                fpath, 5000,
                            )
                        except (AttributeError, TypeError, OSError):
                            _current_summary = None
                        if not _current_summary:
                            continue
                        for elem in elements:
                            if elem not in _current_summary:
                                _phantom_warnings.setdefault(tid, []).append(
                                    f"{fpath}:{elem}"
                                )
                if _phantom_warnings:
                    logger.warning(
                        "IMPLEMENT Gap 1: phantom element references in %d task(s): %s",
                        len(_phantom_warnings),
                        {tid: refs[:3] for tid, refs in _phantom_warnings.items()},
                    )
                    context["_phantom_element_warnings"] = _phantom_warnings

            chunks, skipped_reports = self._tasks_to_chunks(
                _generation_tasks,
                max_retries=2,
                design_results=design_results,
                calibration_map=calibration_map,
                downstream_map=downstream_map,
                staleness_classification=context.get("scaffold", {}).get(
                    "staleness_classification", {},
                ),
                parameter_sources=context.get("parameter_sources", {}),
                semantic_conventions=context.get("semantic_conventions", {}),
                # PCA-300/301/400: project-level context
                architectural_context=context.get("architectural_context"),
                plan_goals=context.get("plan_goals"),
                plan_context=(context.get("plan_document_text") or "")[:4000] or None,
                service_metadata=context.get("service_metadata"),
                # PCA-401/403/404
                calibration_hints=context.get("onboarding_calibration_hints"),
                prior_impl_summaries=context.get("_prior_impl_summaries"),
                # PCA-501: project identity
                project_name=_project_name,
                project_root_path=str(project_root),
                # PCA-600: edit mode classification
                edit_mode_map=edit_mode_map,
                # AR-822: module inventory from SCAFFOLD
                module_inventory=context.get("scaffold", {}).get("module_inventory"),
                # Scaffold output for skeleton file detection
                scaffold_output=context.get("scaffold", {}),
                # Phase 5: Forward interface contracts
                forward_manifest=context.get("forward_manifest"),
                # Micro Prime pre-pass results
                micro_prime_result=context.get("micro_prime_result"),
                # FR-MPA-005: Pre-classified element tiers for prompt narrowing
                element_tiers=(
                    context.get("element_tiers")
                    or context.get("artifacts", {}).get("element_tiers")
                ),
            )

            # Phase 4: Enrich chunks with manifest context (IM-1 through IM-4)
            _manifest_registry = None
            if self.config.manifest_consumption_enabled:
                _manifest_registry = self.config.manifest_registry or context.get("project_manifests")
            if _manifest_registry is not None:
                _manifest_budget = self.config.manifest_context_budget
                _enable_introspect = getattr(self.config, "enable_introspect", False)
                for chunk in chunks:
                    _mc_parts = []
                    for tf in getattr(chunk, "target_files", []):
                        summary = _manifest_registry.file_element_summary(
                            tf, _manifest_budget,
                            include_resolved_types=_enable_introspect,  # IM-1: Phase 5
                        )
                        if summary:
                            _mc_parts.append(f"### {tf}\n{summary}")
                    if _mc_parts:
                        chunk.metadata["_manifest_context"] = "\n\n".join(_mc_parts)
                logger.debug(
                    "IMPLEMENT: manifest context injected into %d chunks",
                    sum(1 for c in chunks if c.metadata.get("_manifest_context")),
                )

                # Phase 6: Enrich chunks with call graph context (CG-IM-1,2,3,4)
                _cg_budget = self.config.call_graph_context_budget
                for chunk in chunks:
                    try:
                        _cg_parts: list[str] = []
                        _cg_callers: list[dict[str, Any]] = []
                        for tf in getattr(chunk, "target_files", []):
                            cg_summary = _manifest_registry.call_graph_summary(tf, _cg_budget)
                            if cg_summary:
                                _cg_parts.append(f"### {tf}\n{cg_summary}")
                            callers_map = _manifest_registry.callers_of_file(tf)
                            for fqn, callers in callers_map.items():
                                br = _manifest_registry.blast_radius(fqn, max_depth=self.config.blast_radius_max_depth)
                                _cg_callers.append({
                                    "fqn": fqn,
                                    "direct_callers": sorted(callers),
                                    "blast_radius": len(br),
                                })
                        if _cg_parts:
                            chunk.metadata["_call_graph_context"] = "\n\n".join(_cg_parts)
                        if _cg_callers:
                            chunk.metadata["_call_graph_callers"] = _cg_callers
                    except (AttributeError, TypeError, OSError, KeyError, ValueError):
                        logger.debug(
                            "IMPLEMENT: call graph enrichment failed for chunk %s",
                            getattr(chunk, "chunk_id", "?"), exc_info=True,
                        )
                logger.debug(
                    "IMPLEMENT: call graph context injected into %d chunks",
                    sum(1 for c in chunks if c.metadata.get("_call_graph_context")),
                )
            else:
                logger.info(
                    "manifest.fallback",
                    extra={"surface": "implement_enrichment", "reason": "registry_unavailable" if not self.config.manifest_consumption_enabled else "no_registry"},
                )

            # Gaps 3/4/5: Enrich chunks with handoff improvement data
            _structural_delta = context.get("design_structural_delta", {})
            _mode_evidence = context.get("design_mode_evidence", {})
            _trunc_tier = context.get("manifest_truncation_tier", {})
            _phantom_warns = context.get("_phantom_element_warnings", {})
            for chunk in chunks:
                tid = chunk.chunk_id
                # Gap 3: structural delta for element-level guidance
                if tid in _structural_delta:
                    chunk.metadata["_design_structural_delta"] = _structural_delta[tid]
                # Gap 4: design mode evidence
                if tid in _mode_evidence:
                    chunk.metadata["_design_mode_evidence"] = _mode_evidence[tid]
                # Gap 5: truncation tier per target file
                _chunk_trunc = {}
                for tf in getattr(chunk, "target_files", []):
                    if tf in _trunc_tier:
                        _chunk_trunc[tf] = _trunc_tier[tf]
                if _chunk_trunc:
                    chunk.metadata["_manifest_truncation_tier"] = _chunk_trunc
                # Gap 1: phantom element warnings
                if tid in _phantom_warns:
                    chunk.metadata["_phantom_element_warnings"] = _phantom_warns[tid]

            # CMR: Complexity-Driven Model Router (REQ-CMR-012)
            # Classification runs after Phase 6 call graph enrichment, before
            # executor construction.
            _tier_distribution = {"tier_1": 0, "tier_2": 0, "tier_3": 0}
            if chunks:
                from startd8.contractors.artisan_phases.development import (
                    TaskComplexitySignals,
                    TaskComplexityTier,
                )

                for chunk in chunks:
                    try:
                        if not self.config.complexity_routing_enabled:
                            _set_default_complexity_metadata(chunk, force=True)
                            _tier_distribution["tier_2"] += 1
                            continue

                        signals = _extract_complexity_signals(
                            chunk, _manifest_registry,
                        )
                        override_raw = chunk.metadata.get("complexity_tier_override")
                        if isinstance(override_raw, str):
                            override_norm = override_raw.strip().lower()
                            try:
                                tier = TaskComplexityTier(override_norm)
                                logger.info(
                                    "CMR: chunk=%s using complexity_tier_override=%s",
                                    getattr(chunk, "chunk_id", "?"),
                                    tier.value,
                                )
                            except ValueError:
                                logger.warning(
                                    "CMR: invalid complexity_tier_override=%r for chunk %s; using classifier",
                                    override_raw,
                                    getattr(chunk, "chunk_id", "?"),
                                )
                                tier = _classify_complexity_tier(signals, self.config)
                        else:
                            tier = _classify_complexity_tier(signals, self.config)
                        chunk.metadata["_complexity_tier"] = tier.value
                        chunk.metadata["_complexity_signals"] = signals.to_dict()
                        _tier_distribution[tier.value] += 1
                        logger.info(
                            "CMR: chunk=%s tier=%s blast=%d callers=%d edit=%s loc=%d",
                            getattr(chunk, "chunk_id", "?"),
                            tier.value,
                            signals.blast_radius,
                            signals.caller_count,
                            signals.edit_mode,
                            signals.estimated_loc,
                        )
                    except Exception:
                        # Graceful degradation — default to Tier 2
                        _set_default_complexity_metadata(chunk, force=False)
                        _tier_distribution["tier_2"] += 1
                        logger.warning(
                            "CMR: classification failed for chunk %s, defaulting to tier_2",
                            getattr(chunk, "chunk_id", "?"),
                            exc_info=True,
                        )
                logger.info(
                    "CMR: T1=%d, T2=%d, T3=%d across %d chunks",
                    _tier_distribution["tier_1"],
                    _tier_distribution["tier_2"],
                    _tier_distribution["tier_3"],
                    len(chunks),
                )
            context["_tier_distribution"] = _tier_distribution

            # PCA-402: track onboarding field consumption
            if context.get("service_metadata") is not None:
                _track_onboarding_consumption(context, "service_metadata", "IMPLEMENT")
            if context.get("onboarding_calibration_hints") is not None:
                _track_onboarding_consumption(context, "onboarding_calibration_hints", "IMPLEMENT")
            if context.get("architectural_context"):
                _track_onboarding_consumption(context, "architectural_context", "IMPLEMENT")

            if not chunks:
                logger.warning("IMPLEMENT: no eligible tasks after env pre-filter")
                output = {
                    "task_reports": skipped_reports,
                    "tasks_processed": len(skipped_reports),
                    "domain_breakdown": {},
                    "total_estimated_loc": 0,
                    "total_cost": 0.0,
                    "generation_results": {},
                }
                context["implementation"] = output
                output["metadata"] = self._build_implementation_metadata(context)
                context["generation_results"] = {}
                context["truncation_flags"] = {}

                # Context contract: validate IMPLEMENT output model (no-chunks path)
                ImplementPhaseOutput(
                    implementation=context["implementation"],
                    generation_results=context["generation_results"],
                    truncation_flags=context["truncation_flags"],
                )

                duration = time.monotonic() - start
                return {"output": output, "cost": 0.0, "metadata": {"duration": duration, "resumed": False}}

            # Build executor (inject pre-configured generator if provided)
            # Write to staging_dir so INTEGRATE merges into project_root
            staging_dir = project_root / (self.config.staging_dir or ".startd8/staging")
            staging_dir.mkdir(parents=True, exist_ok=True)
            context["_staging_dir"] = str(staging_dir)

            executor = ArtisanChunkExecutor(
                drafter_spec=self.config.drafter_agent,
                refiner_spec=(
                    self.config.tier2_agent
                    if not self.config.skip_refinement
                    else None
                ),
                tier3_drafter_spec=(
                    self.config.tier3_agent
                    if self.config.complexity_routing_enabled
                    else None
                ),
                tier2_gate_escalation=self.config.complexity_tier2_gate_escalation,
                output_dir=staging_dir,
                max_tokens=self.config.max_tokens,
                project_root=project_root,
            )

            # Cooperative cancellation token — set on timeout to signal
            # the background thread to stop initiating new LLM calls.
            cancel_event = threading.Event()

            # Build plan
            plan = DevelopmentPlan(
                plan_id=f"artisan-implement-{int(time.time())}",
                chunks=chunks,
                config={
                    "dry_run": False,
                    "walkthrough": self.config.walkthrough,
                    "state_dir": str(project_root / ".startd8" / "state"),
                    "cancel_event": cancel_event,
                    "example_artifacts": context.get("example_artifacts", {}),
                },
            )

            # Build phase with test runner (no shell test commands — tests are
            # handled by DomainChecklist and the TEST phase handler)
            state_store = JsonFileStateStore(
                directory=str(project_root / ".startd8" / "state"),
            )
            # --- WCP-006: Wire DomainChecklist to DevelopmentPhase ---
            domain_checklist = None
            enriched_seed_path = (
                self._enriched_seed_path
                or context.get("enriched_seed_path")
            )
            if enriched_seed_path:
                try:
                    from startd8.contractors.artisan_phases.domain_checklist import DomainChecklist
                    domain_checklist = DomainChecklist(
                        project_root=project_root,
                        enriched_seed_path=Path(enriched_seed_path),
                    )
                    logger.info(
                        "IMPLEMENT: DomainChecklist configured (seed=%s)",
                        enriched_seed_path,
                    )
                except Exception as e:
                    logger.warning(
                        "IMPLEMENT: DomainChecklist init failed (non-fatal): %s", e,
                    )

            dev_phase = DevelopmentPhase(
                executor=executor,
                test_runner=DefaultTestRunner(),
                state_store=state_store,
                max_parallel=4,
                domain_checklist=domain_checklist,
            )

            # Bridge sync → async
            logger.info(
                "IMPLEMENT: delegating %d chunks to DevelopmentPhase (plan=%s)",
                len(chunks), plan.plan_id,
            )
            dev_result = self._run_development_phase(
                dev_phase, plan,
                timeout=self.config.development_timeout_seconds,
                cancel_event=cancel_event,
            )

            if dev_result is None or not hasattr(dev_result, "chunk_states"):
                raise RuntimeError(
                    "DevelopmentPhase returned an invalid result "
                    f"(type={type(dev_result).__name__}). "
                    "Expected DevelopmentResult with chunk_states attribute."
                )

            mp_result = context.get("micro_prime_result")
            if mp_result:
                logger.info(
                    "IMPLEMENT: Micro Prime savings — %d local ($0), %d escalated to cloud",
                    (mp_result.get("metrics") or {}).get("local_success_count", 0),
                    len(mp_result.get("escalated_elements") or []),
                )

            # Map results back to downstream contract
            output, generation_results, total_cost = self._map_development_result(
                dev_result, chunks, tasks, skipped_reports,
            )

            # ── All-tasks-failed guard ────────────────────────────────
            # When chunks were dispatched but zero generation results came
            # back, every task failed (e.g. API overloaded, auth error).
            # Raise so the orchestrator marks the phase FAILED instead of
            # silently passing empty results to INTEGRATE/TEST/REVIEW.
            if chunks and not generation_results and not self.config.walkthrough:
                failed_reports = [
                    r for r in output.get("task_reports", [])
                    if r.get("status") == "generation_failed"
                ]
                error_details = "; ".join(
                    f"{r['task_id']}: {r.get('error', 'unknown')}"
                    for r in failed_reports[:3]
                )
                raise RuntimeError(
                    f"IMPLEMENT: all {len(chunks)} task(s) failed generation. "
                    f"No code was produced. Details: {error_details or 'no error details'}"
                )

            # ── Gate 3: post-IMPLEMENT multi-file split validation ────
            # Per defense-in-depth Principle 1 (validate at every
            # boundary): verify that every multi-file task actually
            # produced all its target files.  This is the last gate
            # before output is accepted.
            gate3 = self._validate_generation_completeness(
                tasks, generation_results, project_root,
                downstream_map=downstream_map,
            )
            if gate3:
                output["_gate3_validation"] = gate3

            # ── Gate 3b: post-IMPLEMENT semantic content validation ──
            # Runs 5 self-consistency validators (AR-143–AR-147) to
            # catch placeholder literals, undeclared imports, proto
            # field mismatches, protocol fidelity issues, and
            # Dockerfile coherence problems.  Advisory in v1.
            _svc_meta = context.get("service_metadata")
            gate3b = self._validate_generation_content(
                tasks, generation_results, project_root,
                service_metadata=_svc_meta,
            )
            if gate3b:
                output["_gate3b_content_validation"] = gate3b
                flagged_ids = sorted(gate3b.keys())
                total_issues = sum(len(v) for v in gate3b.values())
                logger.warning(
                    "Gate 3b: %d task(s) with %d content issue(s): %s",
                    len(flagged_ids), total_issues, flagged_ids,
                )
            else:
                logger.info(
                    "Gate 3b: no content issues across %d task(s)",
                    len(generation_results),
                )

            # ── PCA-603: Build existing file sizes for Gate 4 size regression ──
            existing_file_sizes = self._build_existing_file_sizes(chunks, project_root)

            # ── Gate 4: post-IMPLEMENT truncation detection ─────────
            # Per Context Correctness by Construction: detect truncated
            # or syntactically broken generated files BEFORE they
            # propagate to TEST/REVIEW/FINALIZE.
            truncation_flags = self._validate_truncation(
                tasks, generation_results, project_root,
                existing_file_sizes=existing_file_sizes,
            )
            if truncation_flags:
                output["_gate4_truncation"] = truncation_flags
                flagged_ids = sorted(truncation_flags.keys())
                logger.warning(
                    "Gate 4: %d task(s) flagged for truncation: %s",
                    len(flagged_ids), flagged_ids,
                )
            else:
                logger.info(
                    "Gate 4: no truncation detected across %d task(s)",
                    len(generation_results),
                )

            # ── Gate 5: Edit-First Enforcement (REQ-EFE-020) ─────────
            from startd8.contractors.edit_first_gate import (
                validate_task_size_regression,
                resolve_threshold,
                emit_rejection_telemetry,
                build_edit_retry_prompt,
            )
            from startd8.utils.code_extraction import extract_code_from_response

            gate5_results: dict[str, Any] = {}
            _output_contracts = context.get("onboarding_output_contracts")
            _schema_features = context.get("onboarding_schema_features")

            for task in tasks:
                gr = generation_results.get(task.task_id)
                if gr is None or not gr.success:
                    continue

                # Get existing content from chunk metadata
                chunk_efc: dict[str, str] = {}
                for chunk in chunks:
                    if chunk.chunk_id == task.task_id:
                        chunk_efc = chunk.metadata.get(
                            "_existing_file_contents", {},
                        )
                        break

                if not chunk_efc:
                    continue  # New-file task — no size regression possible

                # Read generated file content from staging
                gen_file_contents: dict[str, str] = {}
                for gen_path in gr.generated_files:
                    fp = Path(gen_path)
                    if fp.exists():
                        try:
                            rel_key = str(fp.relative_to(staging_dir))
                        except ValueError:
                            # Fallback: use full path string to avoid
                            # name-only collisions across directories.
                            rel_key = str(fp)
                        try:
                            gen_file_contents[rel_key] = fp.read_text(
                                encoding="utf-8",
                            )
                        except (OSError, UnicodeDecodeError) as read_exc:
                            logger.debug(
                                "Gate 5: skipping unreadable generated file %s: %s",
                                fp, read_exc,
                            )

                if not gen_file_contents:
                    continue

                # Resolve threshold for this task's artifact types
                artifact_types = [
                    task.artifact_type
                ] if hasattr(task, "artifact_type") and task.artifact_type else ["source_code"]
                threshold = resolve_threshold(
                    artifact_types=artifact_types,
                    output_contracts=_output_contracts,
                    schema_features=_schema_features,
                )

                gate_result = validate_task_size_regression(
                    task_id=task.task_id,
                    generated_files=gen_file_contents,
                    existing_contents=chunk_efc,
                    threshold=threshold,
                    artifact_type=artifact_types[0] if artifact_types else "unknown",
                    force_rewrite=self.config.force_rewrite,
                )

                if gate_result.any_rejected:
                    # Emit telemetry for initial rejection
                    try:
                        from opentelemetry import trace as _g5_trace
                        _g5_span = _g5_trace.get_current_span()
                        emit_rejection_telemetry(gate_result, _g5_span)
                    except (ImportError, TypeError, AttributeError, RuntimeError, NameError):
                        logger.debug("Auto-lint import failed", exc_info=True)

                    # REQ-EFE-023: single retry with edit-focused prompt
                    retry_succeeded = self._attempt_edit_first_retry(
                        task, gate_result, chunk_efc, context,
                        gr, executor, staging_dir, threshold,
                        extract_code_from_response,
                    )

                    # Re-evaluate after retry
                    still_rejected = any(
                        f.action == "rejected" for f in gate_result.file_results
                    )
                    gate_result.any_rejected = still_rejected
                    gate_result.retry_succeeded = retry_succeeded and not still_rejected
                    if still_rejected:
                        # Emit telemetry for post-retry rejection
                        try:
                            from opentelemetry import trace as _g5_trace2
                            _g5_span2 = _g5_trace2.get_current_span()
                            emit_rejection_telemetry(gate_result, _g5_span2)
                        except (ImportError, TypeError, AttributeError, RuntimeError, NameError):
                            logger.debug("Auto-lint import failed", exc_info=True)

                gate5_results[task.task_id] = {
                    "any_rejected": gate_result.any_rejected,
                    "retry_needed": gate_result.retry_needed,
                    "retry_succeeded": gate_result.retry_succeeded,
                    "file_results": [
                        {
                            "file_path": fr.file_path,
                            "input_chars": fr.input_chars,
                            "output_chars": fr.output_chars,
                            "ratio": round(fr.ratio, 2),
                            "threshold": fr.threshold,
                            "artifact_type": fr.artifact_type,
                            "passed": fr.passed,
                            "action": fr.action,
                        }
                        for fr in gate_result.file_results
                    ],
                }

            if gate5_results:
                rejected_count = sum(
                    1 for r in gate5_results.values() if r["any_rejected"]
                )
                if rejected_count:
                    output["_gate5_edit_first"] = gate5_results
                    logger.warning(
                        "Gate 5: %d task(s) with edit-first size regression: %s",
                        rejected_count,
                        sorted(
                            tid for tid, r in gate5_results.items()
                            if r["any_rejected"]
                        ),
                    )
                else:
                    logger.info(
                        "Gate 5: edit-first gate passed for %d task(s)",
                        len(gate5_results),
                    )
            else:
                logger.info(
                    "Gate 5: no existing-file tasks to check (all new files)"
                )

            context["edit_first_gate_results"] = gate5_results

            # Persist generation_results to disk for crash recovery (v2 envelope)
            # Always write to the canonical .startd8/state/ location.
            # Skip when no explicit project_root (matches REVIEW's pattern).
            if not _has_explicit_project_root:
                logger.info("IMPLEMENT: no explicit project_root — skipping cache save")
            else:
                try:
                    save_path = project_root / ".startd8" / "state" / "generation_results.json"
                    serializable_tasks = {}
                    for tid, gr in generation_results.items():
                        content_hashes: dict[str, str] = {}
                        for p in gr.generated_files:
                            fp = Path(p)
                            if fp.exists():
                                content_hashes[str(p)] = hashlib.sha256(
                                    fp.read_bytes()
                                ).hexdigest()
                        serializable_tasks[tid] = {
                            "success": gr.success,
                            "generated_files": [str(p) for p in gr.generated_files],
                            "content_hashes": content_hashes,
                            "error": gr.error,
                            "input_tokens": gr.input_tokens,
                            "output_tokens": gr.output_tokens,
                            "cost_usd": gr.cost_usd,
                            "iterations": gr.iterations,
                            "model": gr.model,
                        }
                    # Persist downstream_map so REVIEW can restore it on resume
                    cache_envelope: dict[str, Any] = {
                        "_cache_meta": {
                            "schema_version": _CACHE_SCHEMA_VERSION,
                            "created_at": datetime.datetime.now(
                                datetime.timezone.utc
                            ).isoformat(),
                            "source_checksum": context.get("source_checksum"),
                            "design_hash": _compute_design_results_hash(
                                context.get("design_results", {})
                            ),
                        },
                        "downstream_map": downstream_map,
                        "truncation_flags": truncation_flags,
                        "edit_first_gate_results": gate5_results,
                        "tasks": serializable_tasks,
                    }
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_json(save_path, cache_envelope, indent=2)
                    logger.info(
                        "IMPLEMENT: saved %d generation results (v2) to %s",
                        len(generation_results), save_path,
                    )
                except Exception as exc:
                    logger.warning(
                        "IMPLEMENT: failed to write cache: %s (non-fatal)",
                        exc, exc_info=True,
                    )

        # NOTE: Auto-commit moved to INTEGRATE phase.
        # The IMPLEMENT phase now writes to staging_dir; INTEGRATE merges
        # into project_root and commits if auto_commit is enabled.

        # AR-153 scoped retry: merge cached passing-task results back in
        # so INTEGRATE/TEST/REVIEW see the full set of generation results.
        if _retry_cached:
            _merged_count = 0
            for _cached_tid, _cached_gr in _retry_cached.items():
                if _cached_tid not in generation_results:
                    generation_results[_cached_tid] = _cached_gr
                    _merged_count += 1
            if _merged_count:
                logger.info(
                    "IMPLEMENT: AR-153 merged %d cached passing-task "
                    "result(s) into generation_results",
                    _merged_count,
                )

        context["implementation"] = output
        output["metadata"] = self._build_implementation_metadata(context)
        # C-2 fix: normalize any dict entries to GenerationResult so downstream
        # phases can safely access .cost_usd / .success without AttributeError.
        generation_results = {
            tid: _dict_to_gen_result(v) if isinstance(v, dict) else v
            for tid, v in generation_results.items()
        }
        context["generation_results"] = generation_results
        context["truncation_flags"] = truncation_flags

        # PCA-403: accumulate prior implementation summaries for cross-feature context
        prior_summaries = context.get("_prior_impl_summaries", [])
        for task_id, gen_result in generation_results.items():
            if hasattr(gen_result, "success") and gen_result.success:
                files = [str(p) for p in (gen_result.generated_files or [])[:5]] if hasattr(gen_result, "generated_files") and gen_result.generated_files else []
                prior_summaries.append({"task_id": task_id, "files": files})
        context["_prior_impl_summaries"] = prior_summaries[-3:]
        # Propagate downstream_map to REVIEW phase so it can distinguish
        # expected downstream stubs from generation failures.
        if downstream_map:
            context["_downstream_map"] = downstream_map

        # Context contract: validate IMPLEMENT output model (normal path)
        ImplementPhaseOutput(
            implementation=context["implementation"],
            generation_results=context["generation_results"],
            truncation_flags=context["truncation_flags"],
        )

        duration = time.monotonic() - start

        logger.info(
            "IMPLEMENT phase complete: %d tasks, %d passed, $%.4f cost (%.2fs)",
            len(tasks),
            sum(1 for r in generation_results.values() if r.success),
            total_cost,
            duration,
        )

        # Fix 5: Include resumed flag in metadata so orchestrator can
        # distinguish cached from fresh phases.
        metadata: dict[str, Any] = {"duration": duration, "resumed": resumed}
        if resumed:
            metadata["resumed_cost"] = resumed_cost  # type: ignore[possibly-undefined]

        return {"output": output, "cost": total_cost, "metadata": metadata}

    def _attempt_edit_first_retry(
        self,
        task: SeedTask,
        gate_result: Any,
        chunk_efc: dict[str, str],
        context: dict[str, Any],
        gr: GenerationResult,
        executor: Any,
        staging_dir: Path,
        threshold: float,
        extract_code_fn: Any,
    ) -> bool:
        """Attempt a single edit-focused retry for each rejected file (REQ-EFE-023).

        Returns True if at least one file was successfully retried.
        """
        from startd8.contractors.edit_first_gate import build_edit_retry_prompt

        # Guard: executor must expose a usable drafter agent
        if not (
            hasattr(executor, "agent")
            and executor.agent is not None
            and hasattr(executor.agent, "generate")
        ):
            logger.debug(
                "Gate 5: executor has no usable agent for retry — skipping "
                "edit-first retry for %s", task.task_id,
            )
            return False

        retry_succeeded = False
        for fr in gate_result.file_results:
            if fr.action != "rejected":
                continue

            existing_content = chunk_efc.get(fr.file_path, "")
            design_doc = (
                context.get("design_results", {})
                .get(task.task_id, {})
                .get("design_document", "")
            )
            retry_prompt = build_edit_retry_prompt(
                original_content=existing_content,
                design_doc=design_doc,
                task_description=getattr(task, "description", str(task.task_id)),
                ratio=fr.ratio,
                threshold=fr.threshold,
            )
            logger.info(
                "Gate 5: retrying %s file %s with edit-focused prompt "
                "(ratio=%.1f%% < threshold=%.1f%%)",
                task.task_id, fr.file_path, fr.ratio, fr.threshold,
            )

            try:
                retry_response = executor.agent.generate(retry_prompt)
                retry_text = (
                    retry_response.text
                    if hasattr(retry_response, "text")
                    else str(retry_response)
                )
                retry_code = extract_code_fn(retry_text)

                min_chars = len(existing_content) * (threshold / 100.0)
                if not retry_code or len(retry_code) < min_chars:
                    logger.warning(
                        "Gate 5: retry for %s file %s still below threshold",
                        task.task_id, fr.file_path,
                    )
                    continue

                # Write retry result to staging
                for gen_path in gr.generated_files:
                    gfp = Path(gen_path)
                    try:
                        rel = str(gfp.relative_to(staging_dir))
                    except ValueError:
                        # Fallback: use full path string to avoid
                        # name-only collisions across directories.
                        rel = str(gfp)
                    if rel == fr.file_path and gfp.exists():
                        gfp.write_text(retry_code, encoding="utf-8")
                        fr.output_chars = len(retry_code)
                        new_ratio = (
                            (len(retry_code) / fr.input_chars) * 100.0
                            if fr.input_chars > 0
                            else 100.0
                        )
                        fr.ratio = new_ratio
                        fr.passed = True
                        fr.action = "passed"
                        retry_succeeded = True
                        logger.info(
                            "Gate 5: retry succeeded for %s file %s "
                            "(new ratio=%.1f%%)",
                            task.task_id, fr.file_path, fr.ratio,
                        )
                        break
            except (OSError, RuntimeError, ValueError, Startd8Error) as retry_exc:
                logger.warning(
                    "Gate 5: retry failed for %s file %s: %s",
                    task.task_id, fr.file_path, retry_exc,
                    exc_info=True,
                )

        return retry_succeeded

    def _commit_features(
        self,
        generation_results: dict[str, GenerationResult],
        tasks: list[SeedTask],
        project_root: Path,
    ) -> None:
        """Commit each successful feature's generated files to git individually.

        Produces one commit per task, mirroring the PrimeContractor pattern.
        Failures are logged as warnings but do not abort the workflow.
        """
        task_map = {t.task_id: t for t in tasks}
        for task_id, gr in generation_results.items():
            if not gr.success or not gr.generated_files:
                continue
            task = task_map.get(task_id)
            title = task.title if task else task_id
            staged_files: list[str] = []
            for fpath in gr.generated_files:
                add_result = subprocess.run(
                    ["git", "add", str(fpath)],
                    cwd=project_root,
                    capture_output=True,
                    timeout=30,
                )
                if add_result.returncode != 0:
                    stderr = getattr(add_result, "stderr", b"")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", errors="replace")
                    logger.warning(
                        "git add failed for %s (task %s): %s",
                        fpath,
                        task_id,
                        stderr.strip(),
                    )
                else:
                    staged_files.append(str(fpath))
            if not staged_files:
                logger.warning(
                    "Skipping commit for %s: all git-add calls failed",
                    task_id,
                )
                continue
            msg = (
                f"feat({task_id}): {title}\n\n"
                "Generated by Artisan IMPLEMENT phase"
            )
            # Commit only the specific generated files to avoid capturing
            # unrelated staged changes from the user's working tree.
            files_to_commit = staged_files
            result = subprocess.run(
                ["git", "commit", "-m", msg, "--"] + files_to_commit,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Committed %s: %s", task_id, title)
            else:
                logger.warning(
                    "Commit failed for %s: %s",
                    task_id,
                    result.stderr.strip(),
                )
