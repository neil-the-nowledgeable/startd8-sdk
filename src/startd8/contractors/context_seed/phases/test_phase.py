"""TEST phase handler."""

from __future__ import annotations

import datetime
import json
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)
from startd8.contractors.context_schema import ValidationPhaseOutput
from startd8.contractors.context_seed.shared import (
    SeedTask,
    _ensure_context_loaded,
    _log_context_completeness,
)
from startd8.contractors.protocols import GenerationResult
from startd8.contractors.context_seed.handler_support import (
    HandlerConfig,
    _CACHE_SCHEMA_VERSION,
    _build_provenance_links,
    _capture_task_span_context,
    _compute_design_results_hash,
    _compute_gen_file_hash,
    _log_task_boundary_complete,
    _log_task_boundary_start,
    _log_task_timing,
)
from startd8.contractors.context_seed.tracing import _phase_tracer
from startd8.contractors.artisan_phases.self_consistency import (
    validate_dockerfile_coherence,
    validate_protocol_fidelity,
)
from startd8.logging_config import get_logger
from startd8.utils.file_operations import atomic_write_json

logger = get_logger("startd8.contractors.context_seed_handlers")


class TestPhaseHandler(AbstractPhaseHandler):
    """TEST phase: Run post-generation validators against generated code.

    In dry-run mode: reports the test plan per task (unchanged).
    In real mode: executes validator commands (pytest, mypy, ruff, etc.)
    as subprocesses and collects pass/fail results.

    Helpers:
        * ``_resolve_validator_command`` — maps validator names to CLI commands.
        * ``_run_validator`` — executes a single validator subprocess with
          timeout handling.
        * ``_run_validators_for_task`` — runs all validators for one task,
          skipping tasks whose generation was not successful.
    """

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()

    # ------------------------------------------------------------------
    # Validator command mapping
    # ------------------------------------------------------------------

    def _resolve_validator_command(
        self,
        validator_name: str,
        target_files: list[str],
        project_root: Path,
    ) -> Optional[list[str]]:
        """Resolve a validator name to runnable subprocess args.

        Args:
            validator_name: Name from ``task.post_generation_validators``.
            target_files: List of file paths (relative to project_root).
            project_root: The project root directory.

        Returns:
            List of command arguments, or None if validator is unknown.
        """
        py = sys.executable  # use the running interpreter, not "python"
        file_args = [str(project_root / f) for f in target_files]

        if validator_name == "pytest":
            return [py, "-m", "pytest", *file_args, "--tb=short", "-q"]
        if validator_name == "mypy":
            return [py, "-m", "mypy", *file_args, "--ignore-missing-imports"]
        if validator_name == "ruff":
            return [py, "-m", "ruff", "check", *file_args]
        if validator_name == "ruff_format":
            return [py, "-m", "ruff", "format", "--check", *file_args]
        if validator_name == "black":
            return [py, "-m", "black", "--check", *file_args]
        if validator_name == "pylint":
            return [py, "-m", "pylint", *file_args]
        if validator_name == "syntax_check":
            return [py, "-m", "py_compile", *file_args]
        if validator_name in ("import_check", "imports_resolve"):
            modules = [
                self._file_to_module(f, project_root)
                for f in target_files
            ] if target_files else []
            modules = [m for m in modules if m]
            if modules:
                imports = "; ".join(f"import {m}" for m in modules)
                return [py, "-c", imports]
            return None

        # --- WCP-008: Enrichment-produced domain validators ---
        # These are AST-based validators from domain preflight rules.
        # They run as in-process checks via a wrapper script.
        enrichment_validators = {
            "relative_imports_valid",
            "deps_available",
            "no_circular_imports",
            "no_markdown_fences",
            "merge_damage",
            "no_relative_imports",
            "definition_ordering",
            "test_naming",
            "no_hardcoded_secrets",
            "no_substring_tag_matching",
            "placeholder_detection",
            "import_dependency",
            "intra_project_imports",
            "proto_field_references",
        }
        if validator_name in enrichment_validators:
            # Run the validator via the preflight rules_validators module
            return [
                py, "-c",
                f"from startd8.workflows.builtin.preflight_rules.rules_validators import run_validator; "
                f"run_validator({validator_name!r}, {file_args!r})",
            ]

        logger.warning("TEST: unknown validator %r — skipping", validator_name)
        return None

    @staticmethod
    def _file_to_module(rel_path: str, project_root: Path) -> str:
        """Convert a relative file path to a Python module name.

        Strips common source prefixes (``src/``) and the ``.py`` extension,
        then validates that the resulting dotted path looks importable.

        Returns:
            Dotted module name (e.g. ``"startd8.contractors.foo"``), or
            empty string if the path cannot be converted.
        """
        # Normalize and strip .py
        p = rel_path.replace("\\", "/")
        if not p.endswith(".py"):
            return ""
        p = p[:-3]  # strip .py

        # Strip common source-tree prefixes
        for prefix in ("src/", "lib/"):
            if p.startswith(prefix):
                p = p[len(prefix):]
                break

        # Convert path separators to dots
        module = p.replace("/", ".")

        # Basic sanity: no leading/trailing dots, no double dots
        if module.startswith(".") or module.endswith(".") or ".." in module:
            return ""
        return module

    @staticmethod
    def _truncate_output(text: str, limit: int = 4000) -> str:
        """Truncate output keeping both head and tail for context.

        When *text* exceeds *limit* characters the middle is replaced with
        a marker showing how many characters were elided.  This preserves
        the first lines (often file paths / summary) **and** the last lines
        (often the actual error message) instead of discarding the head.
        """
        if len(text) <= limit:
            return text
        half = limit // 2
        return (
            text[:half]
            + f"\n\n... [{len(text) - limit} chars truncated] ...\n\n"
            + text[-half:]
        )

    def _run_validator(
        self,
        command: list[str],
        project_root: Path,
        timeout: int,
    ) -> dict[str, Any]:
        """Execute a single validator command as a subprocess.

        Args:
            command: The CLI command args to run.
            project_root: Working directory for the subprocess.
            timeout: Timeout in seconds.

        Returns:
            Dict with keys: ``passed``, ``returncode``, ``stdout``,
            ``stderr``, ``timed_out``.
        """
        logger.debug("TEST: running validator: %s (cwd=%s)", command, project_root)
        try:
            proc = subprocess.run(
                command,
                cwd=str(project_root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            passed = proc.returncode == 0
            result = {
                "passed": passed,
                "returncode": proc.returncode,
                "stdout": self._truncate_output(proc.stdout) if proc.stdout else "",
                "stderr": self._truncate_output(proc.stderr) if proc.stderr else "",
                "timed_out": False,
            }
            if not passed:
                logger.info(
                    "TEST: validator failed (rc=%d): %s",
                    proc.returncode,
                    command,
                )
            return result
        except subprocess.TimeoutExpired:
            logger.warning(
                "TEST: validator timed out after %ds: %s", timeout, command
            )
            return {
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Timed out after {timeout}s",
                "timed_out": True,
            }
        except (OSError, UnicodeDecodeError) as exc:
            logger.error("TEST: validator command failed to start: %s", exc)
            return {
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command failed to start: {exc}",
                "timed_out": False,
            }

    def _run_in_process_validators(
        self,
        task: SeedTask,
        project_root: Path,
        generation_result: GenerationResult | None,
        service_metadata: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Run in-process validators (protocol fidelity, Dockerfile coherence).

        These validators need cross-file context (service_metadata) that
        cannot be passed through the subprocess boundary.

        Returns a list of result dicts matching the subprocess shape::

            {"validator": str, "passed": bool, "issues": list, "file": str, "command": "(in-process)"}
        """
        results: list[dict[str, Any]] = []
        if generation_result is None or not generation_result.success:
            return results

        for rel_path in task.target_files:
            full_path = project_root / rel_path
            if not full_path.exists():
                logger.debug("In-process validators: skipping %s (not found)", rel_path)
                continue
            try:
                code = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("In-process validators: skipping %s: %s", rel_path, exc)
                continue

            for validator_fn, validator_name in [
                (validate_protocol_fidelity, "protocol_fidelity"),
                (validate_dockerfile_coherence, "dockerfile_coherence"),
            ]:
                issues = validator_fn(code, rel_path, service_metadata)
                passed = len(issues) == 0
                results.append({
                    "validator": validator_name,
                    "passed": passed,
                    "issues": issues,
                    "file": rel_path,
                    "command": "(in-process)",
                })

        return results

    def _run_validators_for_task(
        self,
        task: SeedTask,
        project_root: Path,
        generation_result: Optional[GenerationResult],
        service_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run all validators for a single task.

        Validators are only executed when *generation_result* indicates
        success.  If the generation failed or was not attempted the task
        is reported as skipped with ``all_passed = False``.

        Args:
            task: The seed task.
            project_root: Project root directory.
            generation_result: The generation result from IMPLEMENT phase
                (if any).
            service_metadata: Service metadata from onboarding for
                protocol fidelity and Dockerfile coherence validators.

        Returns:
            Dict with per-validator results and overall pass/fail.
        """
        # Skip if generation was not successful
        if generation_result is None or not generation_result.success:
            return {
                "task_id": task.task_id,
                "title": task.title,
                "domain": task.domain,
                "validators_run": 0,
                "all_passed": False,
                "results": [],
                "skipped_reason": "generation_not_successful",
            }

        validator_results: list[dict[str, Any]] = []
        all_passed = True

        for validator_name in task.post_generation_validators:
            command = self._resolve_validator_command(
                validator_name, task.target_files, project_root,
            )
            if command is None:
                validator_results.append({
                    "validator": validator_name,
                    "skipped": True,
                    "reason": "unknown_validator",
                    "passed": False,
                })
                all_passed = False
                continue

            result = self._run_validator(
                command, project_root, self.config.test_timeout_seconds,
            )
            result["validator"] = validator_name
            result["command"] = " ".join(shlex.quote(part) for part in command)
            validator_results.append(result)

            if not result.get("passed", False):
                all_passed = False

        # In-process validators (AR-144 protocol fidelity, AR-147 Dockerfile coherence)
        in_process_results = self._run_in_process_validators(
            task, project_root, generation_result, service_metadata,
        )
        for ip_result in in_process_results:
            validator_results.append(ip_result)
            if not ip_result.get("passed", True):
                all_passed = False

        return {
            "task_id": task.task_id,
            "title": task.title,
            "domain": task.domain,
            "validators_run": len(validator_results),
            "all_passed": all_passed,
            "results": validator_results,
        }

    # ------------------------------------------------------------------
    # Resume cache validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_test_cache(
        saved: dict[str, Any],
        tasks: list[Any],
        generation_results: dict[str, Any],
        source_checksum: str | None,
        design_results: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Validate a saved test_results cache through 4 ordered layers.

        Returns the cached output dict if all layers pass, or None if the
        cache should be rejected (caller falls through to fresh TEST).

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Source checksum — _cache_meta.source_checksum matches context
            1.5: Design hash — design_results hash matches context (catches
                 ``--force-design`` invalidation)
            2: Per-task generation file hash — cached results valid only if
               generated code hasn't changed since tests ran.
        """
        # Layer 0: Schema version
        cache_meta = saved.get("_cache_meta")
        if not isinstance(cache_meta, dict):
            logger.warning(
                "TEST: cache missing _cache_meta (v1 or corrupt) — re-running"
            )
            return None
        schema_version = cache_meta.get("schema_version")
        if schema_version != _CACHE_SCHEMA_VERSION:
            logger.warning(
                "TEST: cache schema_version=%s (expected %d) — re-running",
                schema_version, _CACHE_SCHEMA_VERSION,
            )
            return None

        # Layer 1: Source checksum
        cached_checksum = cache_meta.get("source_checksum")
        if (
            cached_checksum is not None
            and source_checksum is not None
            and cached_checksum != source_checksum
        ):
            logger.warning(
                "TEST: source_checksum mismatch "
                "(cached=%s, current=%s) — re-running",
                cached_checksum, source_checksum,
            )
            return None
        elif cached_checksum is not None or source_checksum is not None:
            # One side has a checksum and the other doesn't — we can't
            # confirm integrity but this is common during the first run
            # after cache creation (seed lacks checksum) or after a
            # rebuild (context gains one).  Log for visibility.
            logger.warning(
                "TEST: only one side has source_checksum "
                "(cached=%s, context=%s) — skipping Layer 1 comparison",
                "present" if cached_checksum else "absent",
                "present" if source_checksum else "absent",
            )
        else:
            # Both checksums are None — Layer 1 integrity check is disabled
            logger.warning(
                "Cache validation: neither cached nor current has source_checksum — "
                "Layer 1 integrity check is disabled"
            )

        # Layer 1.5: Design hash — invalidate when design changes
        # (e.g. --force-design re-ran DESIGN but IMPLEMENT cache was
        # also invalidated, producing new code from the new design).
        cached_design_hash = cache_meta.get("design_hash")
        if cached_design_hash is not None and design_results is not None:
            current_design_hash = _compute_design_results_hash(design_results)
            if (
                current_design_hash is not None
                and current_design_hash != cached_design_hash
            ):
                logger.warning(
                    "TEST: design_hash mismatch "
                    "(cached=%s, current=%s) — re-running",
                    cached_design_hash[:12], current_design_hash[:12],
                )
                return None

        # Layer 2: Per-task generation file hash — verify generated code
        # hasn't changed since tests were run.
        cached_gen_hashes = cache_meta.get("generation_file_hashes", {})
        if cached_gen_hashes:
            for tid, cached_hash in cached_gen_hashes.items():
                gen_result = generation_results.get(tid)
                if gen_result is None:
                    continue
                current_files = getattr(gen_result, "generated_files", [])
                if not current_files:
                    continue
                current_hash = _compute_gen_file_hash(current_files)
                if current_hash is not None and current_hash != cached_hash:
                    logger.warning(
                        "TEST: generation file hash mismatch for %s "
                        "(cached=%s, current=%s) — re-running",
                        tid, cached_hash[:12], current_hash[:12],
                    )
                    return None

        cached_output = saved.get("output")
        if not isinstance(cached_output, dict):
            logger.warning("TEST: cache missing 'output' key — re-running")
            return None

        # Verify all current task IDs are covered
        current_ids = {t.task_id for t in tasks}
        cached_per_task = cached_output.get("per_task", {})
        missing = current_ids - set(cached_per_task.keys())
        if missing:
            logger.warning(
                "TEST: cache missing tasks %s — re-running", sorted(missing),
            )
            return None

        logger.info(
            "TEST: cache valid — resuming with %d cached task results",
            len(cached_per_task),
        )
        return cached_output

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("TEST", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        project_root = Path(context.get("project_root", "."))
        generation_results: dict[str, GenerationResult] = context.get("generation_results", {})
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})
        integration_results_ctx: dict[str, Any] = context.get("integration_results", {})

        logger.info("TEST phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        # --- Resume check: load prior test results if available ---
        _has_explicit_project_root = bool(context.get("project_root", "").strip())
        test_cache_path = (
            project_root / ".startd8" / "state" / "test_results.json"
            if _has_explicit_project_root else None
        )
        if (
            test_cache_path
            and test_cache_path.exists()
            and not dry_run
            and not self.config.force_test
        ):
            try:
                with open(test_cache_path, encoding="utf-8") as f:
                    raw_cache = json.load(f)
                cached_output = self._validate_test_cache(
                    raw_cache,
                    tasks,
                    generation_results,
                    context.get("source_checksum"),
                    context.get("design_results"),
                )
                if cached_output is not None:
                    # C-3 fix: assign the validated result back so that any
                    # Pydantic validator transforms (filled defaults, coerced
                    # types) are preserved instead of discarded.
                    validated = ValidationPhaseOutput(test_results=cached_output)
                    cached_output = validated.test_results
                    context["test_results"] = cached_output
                    duration = time.monotonic() - start
                    logger.info(
                        "TEST phase complete (resumed from cache): "
                        "%d passed, %d failed (%.2fs)",
                        cached_output.get("total_passed", 0),
                        cached_output.get("total_failed", 0),
                        duration,
                    )
                    return {"output": cached_output, "cost": 0.0, "metadata": {"duration": duration, "resumed": True}}
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
                logger.warning("TEST: failed to load cache from %s: %s", test_cache_path, exc)

        test_plan: list[dict[str, Any]] = []
        validator_counts: dict[str, int] = defaultdict(int)
        total_passed = 0
        total_failed = 0
        previous_task_started_mono: Optional[float] = None
        _service_metadata = context.get("service_metadata")

        # Note: idx is ordinal position (not completed count) — may skip if tasks are filtered
        for idx, task in enumerate(tasks, start=1):
            _links = _build_provenance_links(task.task_id, context, ["design", "implement"])
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "test",
                },
                links=_links,
            )
            _task_span = _task_span_cm.__enter__()
            previous_task_started_mono = _log_task_timing(
                "TEST",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
            _log_task_boundary_start(task, phase="test")
            task_status = "unknown"
            validators = task.post_generation_validators
            for v in validators:
                validator_counts[v] += 1

            if dry_run:
                # --- Dry-run path (unchanged) ---
                test_entry = {
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "validators": validators,
                    "validator_count": len(validators),
                    "status": "dry_run_planned",
                }
                test_plan.append(test_entry)
                _task_span.set_attribute("task.status", "dry_run_planned")
                _sc = _capture_task_span_context(_task_span)
                if _sc:
                    test_entry["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status="dry_run_planned",
                    phase="test",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # --- Real-mode path ---
            try:
                gen_result = generation_results.get(task.task_id)

                # Skip tasks that were not generated
                if gen_result is None or not gen_result.success:
                    logger.warning(
                        "TEST: skipping task %s (%s) — no successful generation result",
                        task.task_id, task.title,
                    )
                    test_plan.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "validators": validators,
                        "validator_count": len(validators),
                        "status": "skipped_no_generation",
                    })
                    _task_span.set_attribute("task.status", "skipped_no_generation")
                    task_status = "skipped_no_generation"
                    continue

                # Skip tasks that failed INTEGRATE (e.g. truncation-blocked)
                _int_result = integration_results_ctx.get(task.task_id, {})
                if isinstance(_int_result, dict) and _int_result.get("success") is False:
                    _int_status = _int_result.get("status", "unknown")
                    logger.warning(
                        "TEST: skipping task %s (%s) — integration failed (status=%s)",
                        task.task_id, task.title, _int_status,
                    )
                    test_plan.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "validators": validators,
                        "validator_count": len(validators),
                        "status": "skipped_integration_failed",
                        "integration_status": _int_status,
                    })
                    _task_span.set_attribute("task.status", "skipped_integration_failed")
                    _task_span.set_attribute("task.integration_status", _int_status)
                    task_status = "skipped_integration_failed"
                    continue

                # Run validators
                task_test_result = self._run_validators_for_task(
                    task, project_root, gen_result,
                    service_metadata=_service_metadata,
                )

                # Determine status: distinguish zero-validator tasks from
                # genuinely-passing tasks so they don't inflate the pass rate.
                if task_test_result.get("validators_run", 0) == 0:
                    # No validators ran — mark as uncovered, NOT passed
                    task_test_result["status"] = "uncovered"
                    _task_span.set_attribute("task.status", "uncovered")
                    task_status = "uncovered"
                elif task_test_result["all_passed"]:
                    task_test_result["status"] = "passed"
                    total_passed += 1
                    _task_span.set_attribute("task.status", "passed")
                    task_status = "passed"
                else:
                    task_test_result["status"] = "failed"
                    total_failed += 1
                    _task_span.set_attribute("task.status", "failed")
                    task_status = "failed"
                test_plan.append(task_test_result)
            except Exception as exc:
                logger.warning(
                    "TEST: unexpected error for task %s: %s",
                    task.task_id, exc, exc_info=True,
                )
                test_plan.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "validators": validators,
                    "validator_count": len(validators),
                    "validators_run": 0,
                    "all_passed": False,
                    "results": [],
                    "status": "error",
                    "error": str(exc),
                })
                total_failed += 1
                _task_span.set_attribute("task.status", "error")
                task_status = "error"
            finally:
                _sc = _capture_task_span_context(_task_span)
                if _sc and test_plan:
                    test_plan[-1]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status=task_status,
                    phase="test",
                )
                _task_span_cm.__exit__(None, None, None)

        per_task: dict[str, Any] = {}
        for entry in test_plan:
            task_id = entry.get("task_id")
            if not task_id:
                continue
            if entry.get("status") == "passed":
                per_task[task_id] = {
                    "status": "passed",
                    "passed": True,
                    "validators_run": entry.get("validators_run", 0),
                }
            elif entry.get("status") == "uncovered":
                # R2-T1: Zero-validator tasks — not a validated pass
                per_task[task_id] = {
                    "status": "uncovered",
                    "passed": None,
                    "validators_run": 0,
                    "reason": "no_applicable_validators",
                }
            elif entry.get("status") == "failed":
                per_task[task_id] = {
                    "status": "failed",
                    "passed": False,
                    "validators_run": entry.get("validators_run", 0),
                    "failures": [
                        r.get("validator")
                        for r in entry.get("results", [])
                        if not r.get("passed", True)
                    ],
                }
            elif entry.get("status") == "skipped_no_generation":
                per_task[task_id] = {
                    "status": "skipped",
                    "passed": None,
                    "validators_run": 0,
                    "reason": "no_successful_generation",
                }
            elif entry.get("status") == "skipped_integration_failed":
                per_task[task_id] = {
                    "status": "skipped",
                    "passed": None,
                    "validators_run": 0,
                    "reason": "integration_failed",
                    "integration_status": entry.get("integration_status"),
                }
            elif entry.get("status") == "error":
                per_task[task_id] = {
                    "status": "error",
                    "passed": False,
                    "validators_run": 0,
                    "error": entry.get("error", ""),
                }
            else:
                per_task[task_id] = {
                    "status": entry.get("status", "unknown"),
                    "passed": None,
                    "validators_run": entry.get("validators_run", 0),
                }

        # ── Gate 4 propagation: annotate per-task with truncation warnings ──
        # Propagate the minimum fields needed for downstream dashboards
        # and the REVIEW prompt injection.  Full details stay in
        # context["truncation_flags"] for FINALIZE summary.
        if truncation_flags:
            for task_id, tf in truncation_flags.items():
                if task_id in per_task:
                    per_task[task_id]["truncation_warning"] = True
                    per_task[task_id]["truncation_confidence"] = tf.get("max_confidence", 0.0)
                    per_task[task_id]["truncation_source"] = tf.get("source", "unknown")

        total_skipped = sum(
            1 for v in per_task.values()
            if v.get("status") == "skipped"
        )
        # R2-T1: Count tasks with no applicable validators separately
        total_uncovered = sum(
            1 for v in per_task.values()
            if v.get("status") == "uncovered"
        )
        output = {
            "test_plan": test_plan,
            "total_validators": sum(len(t.post_generation_validators) for t in tasks),
            "unique_validators": dict(validator_counts),
            "tasks_with_tests": len([t for t in test_plan if t.get("validator_count", 0) > 0 or t.get("validators_run", 0) > 0]),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "tests_uncovered": total_uncovered,
            "per_task": per_task,
        }

        context["test_results"] = output

        # Context contract: validate TEST output model.
        # R2-T6: Respect gate mode — block raises, warn flags, skip ignores.
        try:
            ValidationPhaseOutput(test_results=context["test_results"])
        except Exception as _val_exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn",
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"TEST output validation failed (block policy): {_val_exc}"
                ) from _val_exc
            logger.warning(
                "TEST output validation failed (continuing per %s policy): %s",
                _gate_mode,
                _val_exc,
            )
            if _gate_mode == "warn":
                # Flag the output so downstream phases know validation failed
                output["_validation_failed"] = True
                output["_validation_error"] = str(_val_exc)

        # --- Cache write: persist test results for resume ---
        if test_cache_path and not dry_run:
            try:
                # Compute per-task generation file hashes for cache invalidation
                gen_file_hashes: dict[str, str] = {}
                for task in tasks:
                    gen_result = generation_results.get(task.task_id)
                    if gen_result is None:
                        continue
                    gen_files = getattr(gen_result, "generated_files", [])
                    if not gen_files:
                        continue
                    file_hash = _compute_gen_file_hash(gen_files)
                    if file_hash is not None:
                        gen_file_hashes[task.task_id] = file_hash

                # Compute design hash for cache invalidation (Layer 1.5)
                _design_hash = _compute_design_results_hash(
                    context.get("design_results", {})
                )

                cache_envelope: dict[str, Any] = {
                    "_cache_meta": {
                        "schema_version": _CACHE_SCHEMA_VERSION,
                        "created_at": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "source_checksum": context.get("source_checksum"),
                        "generation_file_hashes": gen_file_hashes,
                        "design_hash": _design_hash,
                    },
                    "output": output,
                }
                test_cache_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(test_cache_path, cache_envelope, indent=2)
                logger.info(
                    "TEST: saved %d task results (v2) to %s",
                    len(per_task), test_cache_path,
                )
            except Exception as exc:
                logger.warning(
                    "TEST: failed to write cache to %s: %s (non-fatal)",
                    test_cache_path, exc, exc_info=True,
                )

        duration = time.monotonic() - start

        logger.info(
            "TEST phase complete: %d validators across %d tasks, %d passed, %d failed (%.2fs)",
            output["total_validators"], len(test_plan), total_passed, total_failed, duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}
