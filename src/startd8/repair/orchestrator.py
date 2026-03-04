"""Repair pipeline orchestration (REQ-RPL-001, 003, 006).

Phase 0 provides ``run_element_repair()`` for the micro-prime path.
Phase 1 adds ``run_file_repair()`` for the contractor path.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logging_config import get_logger
from .config import RepairConfig
from .models import (
    Diagnostic,
    ElementContext,
    FileRepairResult,
    RepairContext,
    RepairError,
    RepairOutcome,
    RepairStepResult,
)
from .protocol import AstParseValidator, RepairStep
from .routing import create_steps_from_route, route_failures

logger = get_logger(__name__)

# Stateless singleton — safe for concurrent use (no mutable state).
_validator = AstParseValidator()

# Try to import EventBus for step emissions (R3-S5)
try:
    from ..events import Event, EventBus, EventType

    _HAS_EVENTS = True
except ImportError:
    _HAS_EVENTS = False


def _emit_event(event_type: str, source: str, data: dict) -> None:
    """Emit EventBus event if available."""
    if not _HAS_EVENTS:
        return
    try:
        etype = getattr(EventType, event_type, None)
        if etype:
            EventBus.emit(Event(type=etype, source=source, data=data))
    except Exception:  # noqa: BLE001 — EventBus is advisory; failures must not block repair
        pass


def _delta_fraction(original: str, modified: str) -> float:
    """Fraction of lines changed between original and modified.

    Uses ``difflib.SequenceMatcher`` to compute the ratio of changed
    content. This handles prepend/append operations (e.g., import
    additions) correctly — shifted-but-identical lines are not counted
    as changes.
    """
    import difflib

    orig_lines = original.splitlines()
    mod_lines = modified.splitlines()
    matcher = difflib.SequenceMatcher(None, orig_lines, mod_lines)
    # ratio() returns similarity (0-1); we want change fraction
    return 1.0 - matcher.ratio()


def _run_steps(
    code: str,
    steps: list[RepairStep],
    context: RepairContext,
    file_path: Path,
    element_context: Optional[ElementContext],
    config: RepairConfig,
    is_method: bool = False,
) -> Tuple[str, List[RepairStepResult]]:
    """Run a sequence of repair steps with non-destructive guard.

    Returns (repaired_code, list_of_step_results).
    """
    results: list[RepairStepResult] = []
    current = code
    total_start = time.monotonic()

    for step in steps:
        # Total timeout check
        elapsed = time.monotonic() - total_start
        if elapsed >= config.total_timeout_s:
            logger.debug("Repair total timeout (%.1fs) reached", config.total_timeout_s)
            break

        step_name = getattr(step, "name", step.__class__.__name__)
        _emit_event("PIPELINE_STEP_START", "repair", {"step_name": step_name})

        step_start = time.monotonic()
        was_valid_before = _validator.validate(current, is_method)

        try:
            result = step(current, context, file_path, element_context)
        except RepairError as exc:
            logger.debug("Repair step '%s' raised RepairError: %s", step_name, exc)
            result = RepairStepResult(
                step_name=step_name,
                modified=False,
                code=current,
                metrics={"error": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 — intentional fallback; RepairError caught above
            logger.debug("Repair step '%s' failed: %s", step_name, exc)
            result = RepairStepResult(
                step_name=step_name,
                modified=False,
                code=current,
                metrics={"error": str(exc)},
            )

        step_duration_ms = (time.monotonic() - step_start) * 1000
        reverted = False

        if result.modified:
            # Delta guardrail (REQ-RPL-007/R5-S1) — only when code was
            # already valid. Invalid code may need drastic repair.
            delta = _delta_fraction(current, result.code)
            if was_valid_before and delta > config.delta_threshold:
                logger.debug(
                    "Repair step '%s' changed %.0f%% of lines (threshold %.0f%%) — skipped",
                    step_name, delta * 100, config.delta_threshold * 100,
                )
                result.modified = False
                result.code = current
                result.metrics["skipped_delta"] = delta

            # Non-destructive guard
            elif was_valid_before and not _validator.validate(result.code, is_method):
                logger.debug(
                    "Repair step '%s' broke valid code — reverting", step_name,
                )
                result.modified = False
                result.code = current
                result.metrics["reverted"] = True
                reverted = True
            else:
                current = result.code

        results.append(result)

        _emit_event(
            "PIPELINE_STEP_RETRY" if reverted else "PIPELINE_STEP_COMPLETE",
            "repair",
            {
                "step_name": step_name,
                "reverted": reverted,
                "duration_ms": step_duration_ms,
                "modified": result.modified,
            },
        )

    return current, results


# ═══════════════════════════════════════════════════════════════════════════
# Phase 0: Micro-prime entry point
# ═══════════════════════════════════════════════════════════════════════════


def run_element_repair(
    code: str,
    element_context: ElementContext,
    steps: List[RepairStep],
    config: Optional[RepairConfig] = None,
    file_path: Optional[Path] = None,
) -> Tuple[str, List[RepairStepResult]]:
    """Run repair steps on a single element (micro-prime path).

    Args:
        code: Raw LLM-generated code.
        element_context: Element metadata for level-specific steps.
        steps: Ordered list of repair steps to apply.
        config: Optional repair config (uses defaults if None).
        file_path: Optional file path context.

    Returns:
        Tuple of (repaired code, list of step results).
    """
    if config is None:
        config = RepairConfig()

    ctx = RepairContext(
        config=config,
        element_context=element_context,
    )

    is_method = bool(element_context.parent_class)
    fp = file_path or Path("<element>")

    return _run_steps(code, steps, ctx, fp, element_context, config, is_method)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Contractor entry point
# ═══════════════════════════════════════════════════════════════════════════


def run_file_repair(
    files: Dict[Path, str],
    diagnostics: List[Diagnostic],
    config: RepairConfig,
    project_root: Path,
) -> RepairOutcome:
    """Run repair on multiple files based on diagnostics.

    Returns RepairOutcome (no re-checkpoint — engine drives that).

    Args:
        files: Map of file path → file content.
        diagnostics: Parsed checkpoint diagnostics.
        config: Repair pipeline configuration.
        project_root: Project root for context.

    Returns:
        RepairOutcome with repaired files, attribution, and step results.
    """
    route = route_failures(diagnostics, config)

    if not route.steps:
        return RepairOutcome(
            route=route,
            any_modified=False,
        )

    steps = create_steps_from_route(route)
    repaired_files: dict[Path, str] = {}
    file_results: list[FileRepairResult] = []
    all_step_names: set[str] = set()
    any_modified = False

    for file_path, code in files.items():
        # Build per-file diagnostics
        file_diags = [
            d for d in diagnostics
            if d.file == str(file_path) or d.file == file_path.name
        ]

        ctx = RepairContext(
            diagnostics=file_diags,
            config=config,
            project_root=project_root,
        )

        repaired, step_results = _run_steps(
            code, steps, ctx, file_path, None, config,
        )

        modified = repaired != code
        if modified:
            repaired_files[file_path] = repaired
            any_modified = True

        applied = [r.step_name for r in step_results if r.modified]
        all_step_names.update(applied)

        file_results.append(FileRepairResult(
            file_path=file_path,
            before_valid=_validator.validate(code),
            after_valid=_validator.validate(repaired),
            steps_applied=applied,
            step_results=step_results,
        ))

    return RepairOutcome(
        repaired_files=repaired_files,
        file_results=file_results,
        steps_applied=sorted(all_step_names),
        route=route,
        any_modified=any_modified,
    )
