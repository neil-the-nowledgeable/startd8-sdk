"""Repair pipeline orchestration (REQ-RPL-001, 003, 006, 400, 401, 502).

Phase 0 provides ``run_element_repair()`` for the micro-prime path.
Phase 1 adds ``run_file_repair()`` for the contractor path.

OTel spans and metrics are emitted when OpenTelemetry is installed;
all instrumentation is guarded and degrades to no-ops otherwise.
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

# ═══════════════════════════════════════════════════════════════════════════
# OTel instrumentation (REQ-RPL-400, REQ-RPL-401)
# ═══════════════════════════════════════════════════════════════════════════

try:
    from opentelemetry import trace
    _tracer = trace.get_tracer(__name__)
    _HAS_OTEL = True
except ImportError:
    _tracer = None
    _HAS_OTEL = False

try:
    from opentelemetry import metrics
    _meter = metrics.get_meter(__name__)
    _repair_attempts = _meter.create_counter(
        "repair_attempts_total", description="Total repair attempts",
    )
    _repair_success = _meter.create_counter(
        "repair_success_total", description="Successful repairs",
    )
    _repair_steps_applied = _meter.create_counter(
        "repair_steps_applied", description="Per-step application count",
    )
    _repair_wall_clock = _meter.create_histogram(
        "repair_wall_clock_ms", description="Wall-clock time per repair",
    )
except ImportError:
    _repair_attempts = _repair_success = _repair_steps_applied = _repair_wall_clock = None

# ═══════════════════════════════════════════════════════════════════════════
# Circuit breaker (REQ-RPL-502)
# ═══════════════════════════════════════════════════════════════════════════

# category -> consecutive failure count
_circuit_breaker_state: dict[str, int] = {}


def reset_circuit_breaker() -> None:
    """Reset all circuit breaker state. Primarily for testing."""
    _circuit_breaker_state.clear()


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

        # Emit per-step OTel span event (REQ-RPL-400)
        if _HAS_OTEL and _tracer is not None:
            span = trace.get_current_span()
            if span.is_recording():
                outcome = "reverted" if reverted else ("applied" if result.modified else "no_change")
                span.add_event(
                    f"repair.step.{step_name}",
                    attributes={
                        "modified": result.modified,
                        "reverted": reverted,
                        "duration_ms": step_duration_ms,
                    },
                )

        # Emit per-step metric (REQ-RPL-401)
        if _repair_steps_applied is not None:
            outcome = "reverted" if reverted else ("applied" if result.modified else "no_change")
            _repair_steps_applied.add(1, {"step_name": step_name, "outcome": outcome})

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
# Traceability comment injection (REQ-RPL-009)
# ═══════════════════════════════════════════════════════════════════════════

_TRACEABILITY_PREFIX = "# [REPAIRED BY STARTD8: "


def _inject_traceability_comment(code: str, step_names: List[str]) -> str:
    """Inject a traceability header comment listing applied steps."""
    if not step_names:
        return code
    comment = f"{_TRACEABILITY_PREFIX}{', '.join(step_names)}]"
    return f"{comment}\n{code}"


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

    Includes circuit breaker (REQ-RPL-502), traceability comments
    (REQ-RPL-009), OTel spans (REQ-RPL-400), and metrics (REQ-RPL-401).

    Args:
        files: Map of file path -> file content.
        diagnostics: Parsed checkpoint diagnostics.
        config: Repair pipeline configuration.
        project_root: Project root for context.

    Returns:
        RepairOutcome with repaired files, attribution, and step results.
    """
    repair_start = time.monotonic()

    route = route_failures(diagnostics, config)

    # Determine the error category for circuit breaker tracking
    error_categories = sorted({d.category for d in diagnostics})
    cb_key = "|".join(error_categories) if error_categories else "unknown"

    # Circuit breaker check (REQ-RPL-502)
    cb_count = _circuit_breaker_state.get(cb_key, 0)
    if cb_count >= config.circuit_breaker_threshold:
        logger.info(
            "Circuit breaker open for category '%s' (%d consecutive failures, threshold %d) — skipping repair",
            cb_key, cb_count, config.circuit_breaker_threshold,
        )
        duration_ms = (time.monotonic() - repair_start) * 1000
        # Emit skipped metrics
        if _repair_attempts is not None:
            _repair_attempts.add(1, {"outcome": "skipped", "error_category": cb_key})
        if _repair_wall_clock is not None:
            _repair_wall_clock.record(duration_ms)
        return RepairOutcome(
            route=route,
            any_modified=False,
        )

    if not route.steps:
        duration_ms = (time.monotonic() - repair_start) * 1000
        if _repair_attempts is not None:
            _repair_attempts.add(1, {"outcome": "skipped", "error_category": cb_key})
        if _repair_wall_clock is not None:
            _repair_wall_clock.record(duration_ms)
        return RepairOutcome(
            route=route,
            any_modified=False,
        )

    # Start OTel span (REQ-RPL-400)
    span_ctx = None
    if _HAS_OTEL and _tracer is not None:
        span_ctx = _tracer.start_as_current_span(
            "repair.attempt",
            attributes={
                "repair.file_count": len(files),
                "repair.route_confidence": route.confidence,
            },
        )
        span_ctx.__enter__()

    try:
        steps = create_steps_from_route(route)
        repaired_files: dict[Path, str] = {}
        file_results: list[FileRepairResult] = []
        all_step_names: set[str] = set()
        any_modified = False

        for file_path, code in files.items():
            # Build per-file diagnostics
            file_diags = [
                d for d in diagnostics
                if d.file == str(file_path)
                or d.file == file_path.name
                or Path(d.file).name == file_path.name
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
            applied = [r.step_name for r in step_results if r.modified]

            if modified:
                # Inject traceability comment (REQ-RPL-009)
                repaired = _inject_traceability_comment(repaired, applied)
                repaired_files[file_path] = repaired
                any_modified = True

            all_step_names.update(applied)

            file_results.append(FileRepairResult(
                file_path=file_path,
                before_valid=_validator.validate(code),
                after_valid=_validator.validate(repaired),
                steps_applied=applied,
                step_results=step_results,
            ))

        # Update circuit breaker state
        if any_modified:
            # Success — reset counter for this category
            _circuit_breaker_state[cb_key] = 0
        else:
            # Failure — increment
            _circuit_breaker_state[cb_key] = cb_count + 1

        duration_ms = (time.monotonic() - repair_start) * 1000
        outcome_label = "success" if any_modified else "failure"

        # Emit OTel metrics (REQ-RPL-401)
        if _repair_attempts is not None:
            _repair_attempts.add(1, {"outcome": outcome_label, "error_category": cb_key})
        if any_modified and _repair_success is not None:
            _repair_success.add(1, {"error_category": cb_key})
        if _repair_wall_clock is not None:
            _repair_wall_clock.record(duration_ms)

        # Set span attributes for success
        if _HAS_OTEL and _tracer is not None:
            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("repair.success", any_modified)
                span.set_attribute("repair.feature_name", "")

        return RepairOutcome(
            repaired_files=repaired_files,
            file_results=file_results,
            steps_applied=sorted(all_step_names),
            route=route,
            any_modified=any_modified,
        )
    finally:
        if span_ctx is not None:
            span_ctx.__exit__(None, None, None)
