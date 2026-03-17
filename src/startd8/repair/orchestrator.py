"""Repair pipeline orchestration (REQ-RPL-001, 003, 006, 400, 401, 402, 502).

Phase 0 provides ``run_element_repair()`` for the micro-prime path.
Phase 1 adds ``run_file_repair()`` for the contractor path.

OTel spans and metrics are emitted when OpenTelemetry is installed;
all instrumentation is guarded and degrades to no-ops otherwise.
"""

from __future__ import annotations

import concurrent.futures
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
    StepEffectiveness,
)
from .protocol import AstParseValidator, RepairStep
from .routing import create_steps_from_route, route_failures
from .semantic_bridge import translate_to_diagnostics

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
    _repair_cost_avoided = _meter.create_counter(
        "repair_cost_avoided_usd",
        description="Estimated regeneration cost avoided by repair",
    )
except ImportError:
    _repair_attempts = _repair_success = _repair_steps_applied = _repair_wall_clock = None
    _repair_cost_avoided = None


def record_cost_avoided(amount: float) -> None:
    """Increment the ``repair_cost_avoided_usd`` OTel counter.

    Called by integration_engine when repair succeeds to track ROI.
    No-op when OTel is not configured or amount <= 0.

    Args:
        amount: Estimated USD cost of regeneration that was avoided.
    """
    if _repair_cost_avoided is not None and amount > 0:
        _repair_cost_avoided.add(amount)


# ═══════════════════════════════════════════════════════════════════════════
# Circuit breaker (REQ-RPL-502)
# ═══════════════════════════════════════════════════════════════════════════

# category -> consecutive failure count
_circuit_breaker_state: dict[str, int] = {}


def reset_circuit_breaker() -> None:
    """Reset all circuit breaker state. Primarily for testing."""
    _circuit_breaker_state.clear()


# Step effectiveness tracking (REQ-RPL-503)
_step_effectiveness: dict[str, StepEffectiveness] = {}

_EFFECTIVENESS_WARN_THRESHOLD = 0.05


def get_step_effectiveness() -> dict[str, StepEffectiveness]:
    """Return a copy of the step effectiveness tracker."""
    return dict(_step_effectiveness)


def reset_step_effectiveness() -> None:
    """Reset step effectiveness state. Primarily for testing."""
    _step_effectiveness.clear()


def _update_step_effectiveness(
    step_results: List[RepairStepResult],
    repair_succeeded: bool,
) -> None:
    """Update per-step effectiveness counters."""
    for r in step_results:
        se = _step_effectiveness.get(r.step_name)
        if se is None:
            se = StepEffectiveness(step_name=r.step_name)
            _step_effectiveness[r.step_name] = se
        se.attempts += 1
        if r.modified:
            if r.metrics.get("reverted"):
                se.reverts += 1
            else:
                se.modifications += 1
        if repair_succeeded and r.modified and not r.metrics.get("reverted"):
            se.contributed_to_success += 1
        # Warn if effectiveness drops below threshold
        if se.attempts >= 20 and se.effectiveness_rate < _EFFECTIVENESS_WARN_THRESHOLD:
            logger.warning(
                "Repair step '%s' effectiveness %.1f%% below threshold %.1f%% "
                "(%d attempts, %d contributed to success)",
                r.step_name, se.effectiveness_rate * 100,
                _EFFECTIVENESS_WARN_THRESHOLD * 100,
                se.attempts, se.contributed_to_success,
            )


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
) -> Tuple[str, List[RepairStepResult], bool, bool]:
    """Run a sequence of repair steps with non-destructive guard.

    Returns (repaired_code, list_of_step_results, before_valid, after_valid).
    The validity flags are tracked during step execution to avoid redundant
    ast.parse() calls downstream (Validation Layer Accretion fix).
    """
    results: list[RepairStepResult] = []
    current = code
    total_start = time.monotonic()
    # Track validity across the step loop to avoid redundant re-parsing.
    _initial_valid: Optional[bool] = None  # set on first step
    _current_valid: Optional[bool] = None  # tracks latest validity

    # Single executor for all steps — avoids per-step thread pool overhead.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        for step in steps:
            # Total timeout check
            elapsed = time.monotonic() - total_start
            if elapsed >= config.total_timeout_s:
                logger.debug("Repair total timeout (%.1fs) reached", config.total_timeout_s)
                break

            step_name = getattr(step, "name", step.__class__.__name__)
            _emit_event("PIPELINE_STEP_START", "repair", {"step_name": step_name})

            step_start = time.monotonic()
            # Reuse cached validity from prior step when available.
            if _current_valid is not None:
                was_valid_before = _current_valid
            else:
                was_valid_before = _validator.validate(current, is_method)
                _initial_valid = was_valid_before

            try:
                # Per-step timeout enforcement (REQ-RPL-007 / acceptance 9.2.3)
                future = pool.submit(step, current, context, file_path, element_context)
                result = future.result(timeout=config.per_step_timeout_s)
            except concurrent.futures.TimeoutError:
                future.cancel()
                logger.warning(
                    "Repair step '%s' timed out after %.1fs — orphaned thread may still be running",
                    step_name, config.per_step_timeout_s,
                )
                result = RepairStepResult(
                    step_name=step_name,
                    modified=False,
                    code=current,
                    metrics={"skipped_reason": "timeout"},
                )
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
                    # Validity unchanged (reverted to prior valid code)
                    _current_valid = was_valid_before
                else:
                    current = result.code
                    # Step succeeded: code is valid (passed the guard above
                    # or was_valid_before was False meaning we accept any result)
                    _current_valid = True if was_valid_before else None

            # Determine step outcome for OTel
            skipped_reason = result.metrics.get("skipped_reason")
            if skipped_reason:
                step_outcome = "skipped"
            elif reverted:
                step_outcome = "reverted"
            elif result.modified:
                step_outcome = "applied"
            else:
                step_outcome = "no_change"

            # Emit per-step OTel span event (REQ-RPL-400)
            if _HAS_OTEL and _tracer is not None:
                span = trace.get_current_span()
                if span.is_recording():
                    span.add_event(
                        f"repair.step.{step_name}",
                        attributes={
                            "modified": result.modified,
                            "reverted": reverted,
                            "duration_ms": step_duration_ms,
                            **({"skipped_reason": skipped_reason} if skipped_reason else {}),
                        },
                    )

            # Emit per-step metric (REQ-RPL-401)
            if _repair_steps_applied is not None:
                _repair_steps_applied.add(1, {"step_name": step_name, "outcome": step_outcome})

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

    # Resolve final validity: use tracked state, fall back to validator
    before_valid = _initial_valid if _initial_valid is not None else _validator.validate(code, is_method)
    after_valid = _current_valid if _current_valid is not None else _validator.validate(current, is_method)
    return current, results, before_valid, after_valid


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

    repaired, results, _bv, _av = _run_steps(code, steps, ctx, fp, element_context, config, is_method)
    return repaired, results


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


def strip_repair_markers(code: str) -> str:
    """Remove STARTD8 repair traceability comments from final output.

    Called before writing files to the project directory.  The markers
    remain in ``.artifacts/`` pipeline copies for debugging.
    """
    if _TRACEABILITY_PREFIX.rstrip() not in code:
        return code
    lines = code.splitlines(keepends=True)
    cleaned = [
        line for line in lines
        if not line.strip().startswith(_TRACEABILITY_PREFIX.rstrip())
    ]
    # Strip leading blank line if marker removal left one
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    return "".join(cleaned)


# ═══════════════════════════════════════════════════════════════════════════
# Repair attempt artifact persistence (REQ-RPL-404)
# ═══════════════════════════════════════════════════════════════════════════


def _persist_repair_artifact(
    outcome: "RepairOutcome",
    diagnostics: List[Diagnostic],
    route: "RepairRoute",
    project_root: Path,
    feature_name: str = "",
) -> Optional[Path]:
    """Persist repair_attempt.json for offline debugging.

    Returns the artifact path, or None if persistence fails.
    """
    import json

    artifact_dir = project_root / ".startd8" / "repair" / "artifacts"
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    timestamp = int(time.time() * 1000)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in feature_name) or "unnamed"
    artifact_path = artifact_dir / f"repair_attempt_{safe_name}_{timestamp}.json"

    payload = {
        "feature_name": feature_name,
        "timestamp_ms": timestamp,
        "route": {
            "matched_patterns": route.matched_patterns,
            "steps": route.steps,
            "confidence": route.confidence,
        },
        "diagnostics": [
            {"category": d.category, "file": d.file, "message": d.message[:500]}
            for d in diagnostics
        ],
        "files_repaired": [str(p) for p in outcome.repaired_files],
        "steps_applied": outcome.steps_applied,
        "any_modified": outcome.any_modified,
        "file_results": [
            {
                "file": str(fr.file_path),
                "success": fr.success,
                "before_valid": fr.before_valid,
                "after_valid": fr.after_valid,
                "steps_applied": fr.steps_applied,
            }
            for fr in outcome.file_results
        ],
    }

    try:
        artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return artifact_path
    except OSError:
        logger.debug("Failed to persist repair artifact to %s", artifact_path)
        return None


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

    # CR-H4: Determine per-category circuit breaker keys.
    # Track each error category individually so that recurring failures in
    # one category aren't masked by varying companion categories.
    error_categories = sorted({d.category for d in diagnostics}) or ["unknown"]

    # Circuit breaker check (REQ-RPL-502) — trip if ANY individual category
    # has exceeded the threshold.
    tripped_categories = [
        cat for cat in error_categories
        if _circuit_breaker_state.get(cat, 0) >= config.circuit_breaker_threshold
    ]
    if tripped_categories:
        tripped_detail = ", ".join(
            f"{cat}({_circuit_breaker_state.get(cat, 0)})"
            for cat in tripped_categories
        )
        logger.info(
            "Circuit breaker open for categories [%s] (threshold %d) — skipping repair",
            tripped_detail, config.circuit_breaker_threshold,
        )
        duration_ms = (time.monotonic() - repair_start) * 1000
        # Emit skipped metrics — use first category for OTel label
        cb_label = tripped_categories[0] if tripped_categories else "unknown"
        if _repair_attempts is not None:
            _repair_attempts.add(1, {"outcome": "skipped", "error_category": cb_label})
        if _repair_wall_clock is not None:
            _repair_wall_clock.record(duration_ms)
        return RepairOutcome(
            route=route,
            any_modified=False,
        )

    # OTel label for metrics — use first category for consistency
    cb_label = error_categories[0] if error_categories else "unknown"

    if not route.steps:
        duration_ms = (time.monotonic() - repair_start) * 1000
        if _repair_attempts is not None:
            _repair_attempts.add(1, {"outcome": "skipped", "error_category": cb_label})
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

            repaired, step_results, before_valid, after_valid = _run_steps(
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

            # before_valid and after_valid carried from _run_steps —
            # no redundant ast.parse() (Validation Layer Accretion fix).
            file_results.append(FileRepairResult(
                file_path=file_path,
                success=modified and after_valid,
                original_code=code,
                repaired_code=repaired if modified else "",
                before_valid=before_valid,
                after_valid=after_valid,
                steps_applied=applied,
                step_results=step_results,
            ))

        # CR-H4: Update circuit breaker state per individual category
        for cat in error_categories:
            if any_modified:
                # Success — reset counter for this category
                _circuit_breaker_state[cat] = 0
            else:
                # Failure — increment
                _circuit_breaker_state[cat] = _circuit_breaker_state.get(cat, 0) + 1

        duration_ms = (time.monotonic() - repair_start) * 1000
        outcome_label = "success" if any_modified else "failure"

        # Emit OTel metrics (REQ-RPL-401)
        if _repair_attempts is not None:
            _repair_attempts.add(1, {"outcome": outcome_label, "error_category": cb_label})
        if any_modified and _repair_success is not None:
            _repair_success.add(1, {"error_category": cb_label})
        if _repair_wall_clock is not None:
            _repair_wall_clock.record(duration_ms)

        # Set span attributes for success
        if _HAS_OTEL and _tracer is not None:
            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("repair.success", any_modified)
                span.set_attribute("repair.feature_name", "")

        # Update step effectiveness tracking (REQ-RPL-503)
        all_step_results = [
            sr for fr in file_results for sr in fr.step_results
        ]
        _update_step_effectiveness(all_step_results, any_modified)

        outcome = RepairOutcome(
            repaired_files=repaired_files,
            file_results=file_results,
            steps_applied=sorted(all_step_names),
            route=route,
            any_modified=any_modified,
        )

        # Persist repair artifact (REQ-RPL-404) — advisory, never blocks
        try:
            _persist_repair_artifact(
                outcome, diagnostics, route, project_root,
            )
        except Exception:  # noqa: BLE001
            pass

        # Per-file repair frequency (REQ-RPL-402) — advisory
        if any_modified:
            try:
                _update_repair_frequency(repaired_files, project_root)
            except Exception:  # noqa: BLE001
                pass

        return outcome
    finally:
        if span_ctx is not None:
            span_ctx.__exit__(None, None, None)


# ═══════════════════════════════════════════════════════════════════════════
# Per-file repair frequency tracking (REQ-RPL-402)
# ═══════════════════════════════════════════════════════════════════════════

_REPAIR_FREQUENCY_FILE = "repair_frequency.json"


def _update_repair_frequency(
    repaired_files: Dict[Path, str],
    project_root: Path,
) -> None:
    """Increment per-file repair counts and timestamps.

    Persists ``repair_frequency.json`` to ``.startd8/repair/`` for offline
    analysis.  Files with high repair frequency are candidates for manual
    refactoring (the LLM consistently produces repairable-but-not-clean
    output for these paths).
    """
    import json

    freq_dir = project_root / ".startd8" / "repair"
    freq_path = freq_dir / _REPAIR_FREQUENCY_FILE

    # Load existing frequency data
    freq: dict[str, dict] = {}
    try:
        if freq_path.exists():
            freq = json.loads(freq_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        freq = {}

    now = int(time.time())
    for file_path in repaired_files:
        key = str(file_path)
        entry = freq.get(key, {"repair_count": 0, "first_repair_epoch": now})
        entry["repair_count"] = entry.get("repair_count", 0) + 1
        entry["last_repair_epoch"] = now
        if "first_repair_epoch" not in entry:
            entry["first_repair_epoch"] = now
        freq[key] = entry

    try:
        freq_dir.mkdir(parents=True, exist_ok=True)
        freq_path.write_text(
            json.dumps(freq, indent=2, sort_keys=True), encoding="utf-8",
        )
    except OSError:
        logger.debug("Failed to persist repair frequency to %s", freq_path)


def get_repair_frequency(project_root: Path) -> Dict[str, dict]:
    """Load the per-file repair frequency data.

    Returns:
        Dict mapping file path strings to dicts with ``repair_count``,
        ``first_repair_epoch``, and ``last_repair_epoch`` keys.
        Empty dict if no frequency data exists.
    """
    import json

    freq_path = project_root / ".startd8" / "repair" / _REPAIR_FREQUENCY_FILE
    try:
        if freq_path.exists():
            return json.loads(freq_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Manifest attribution (REQ-RPL-402)
# ═══════════════════════════════════════════════════════════════════════════

_OTEL_DESCRIPTORS: dict = {
    "metrics": [
        {
            "name": "repair_attempts_total",
            "instrument": "counter",
            "unit": "attempts",
            "description": "Total repair attempts",
            "meter": "startd8.repair",
            "labels": ["outcome", "error_category"],
        },
        {
            "name": "repair_success_total",
            "instrument": "counter",
            "unit": "repairs",
            "description": "Successful repairs",
            "meter": "startd8.repair",
            "labels": ["error_category"],
        },
        {
            "name": "repair_steps_applied",
            "instrument": "counter",
            "unit": "steps",
            "description": "Per-step application count",
            "meter": "startd8.repair",
            "labels": ["step_name", "outcome"],
        },
        {
            "name": "repair_wall_clock_ms",
            "instrument": "histogram",
            "unit": "ms",
            "description": "Wall-clock time per repair attempt",
            "meter": "startd8.repair",
            "labels": [],
        },
        {
            "name": "repair_cost_avoided_usd",
            "instrument": "counter",
            "unit": "USD",
            "description": "Estimated regeneration cost avoided by repair",
            "meter": "startd8.repair",
            "labels": [],
        },
    ],
    "spans": [
        {
            "name_pattern": "repair.attempt",
            "kind": "INTERNAL",
            "attributes": [
                "repair.feature_name",
                "repair.file_count",
                "repair.route_confidence",
                "repair.success",
            ],
            "events": [
                "repair.step.{step_name}",
            ],
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Semantic repair orchestration (REQ-SR-100–400)
# ═══════════════════════════════════════════════════════════════════════════


def _repair_single_file(
    fpath: Path,
    config: RepairConfig,
    project_root: Path,
    validate_disk_compliance,  # noqa: ANN001 — lazy import, type known at call site
    compute_disk_quality_score,  # noqa: ANN001
) -> Optional[Dict[str, object]]:
    """Detect, repair, and verify semantic issues in a single Python file.

    Returns:
        Dict with ``found``, ``repaired``, ``pre_score``, ``categories``
        on success.  None if no repairable issues found or repair failed.
        Raises on step exception (caller handles circuit breaker).
    """
    try:
        source = fpath.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Cannot read %s for semantic repair: %s", fpath, exc)
        return None

    # 1. Detect
    try:
        compliance = validate_disk_compliance(str(fpath), str(project_root))
    except Exception as exc:
        logger.debug("Disk compliance failed for %s: %s", fpath, exc)
        return None

    repairable = [
        issue for issue in (compliance.semantic_issues or [])
        if isinstance(issue, dict)
        and issue.get("category", "") in config.semantic_repair_categories
    ]
    if not repairable:
        return None

    pre_score = compute_disk_quality_score(compliance)
    found_count = min(len(repairable), config.max_semantic_repairs_per_file)

    # 2. Translate → Route → Repair
    diagnostics = translate_to_diagnostics(
        repairable[:config.max_semantic_repairs_per_file], str(fpath),
    )
    route = route_failures(diagnostics, config)
    if not route.steps:
        return {"found": found_count, "repaired": 0, "pre_score": pre_score, "categories": []}

    steps = create_steps_from_route(route)
    if not steps:
        return {"found": found_count, "repaired": 0, "pre_score": pre_score, "categories": []}

    context = RepairContext(
        diagnostics=diagnostics,
        config=config,
        project_root=project_root,
    )

    # Apply steps — exceptions propagate to caller for circuit breaker
    repaired_code = source
    for step in steps:
        result = step(repaired_code, context, fpath)
        if result.modified:
            repaired_code = result.code

    if repaired_code == source:
        return {"found": found_count, "repaired": 0, "pre_score": pre_score, "categories": []}

    # 3. Verify — re-run compliance on repaired code
    try:
        fpath.write_text(repaired_code, encoding="utf-8")
        post_compliance = validate_disk_compliance(str(fpath), str(project_root))
    except Exception as exc:
        fpath.write_text(source, encoding="utf-8")
        logger.warning("Semantic repair verification failed for %s: %s", fpath, exc)
        raise

    post_repairable = [
        issue for issue in (post_compliance.semantic_issues or [])
        if isinstance(issue, dict)
        and issue.get("category", "") in config.semantic_repair_categories
    ]

    repaired_count = found_count - len(post_repairable)
    if repaired_count > 0:
        logger.info(
            "Semantic repair: %s — %d/%d issues repaired",
            fpath.name, repaired_count, found_count,
        )
        return {
            "found": found_count,
            "repaired": repaired_count,
            "remaining": len(post_repairable),
            "pre_score": pre_score,
            "categories": list({d.semantic_category for d in diagnostics}),
        }

    # Rollback — repair didn't reduce issues
    fpath.write_text(source, encoding="utf-8")
    logger.debug("Semantic repair rollback: %s — no issues resolved", fpath.name)
    return {"found": found_count, "repaired": 0, "pre_score": pre_score, "categories": []}


def run_semantic_repair(
    files: List[Path],
    config: RepairConfig,
    project_root: Path,
) -> Dict[str, object]:
    """Detect semantic issues, apply deterministic repairs, and verify.

    Runs the full detect → translate → route → repair → verify cycle
    on each Python file.  Non-Python files are skipped.

    Args:
        files: Integrated file paths to check.
        config: Repair config (must have ``semantic_repair_categories`` set).
        project_root: Project root for ``validate_disk_compliance()``.

    Returns:
        Dict with keys ``issues_found``, ``issues_repaired``,
        ``issues_unfixable``, ``per_file``, ``pre_repair_scores``.
    """
    _empty = {"issues_found": 0, "issues_repaired": 0, "issues_unfixable": 0, "per_file": {}, "pre_repair_scores": {}}

    try:
        from startd8.contractors.prime_postmortem import compute_disk_quality_score
        from startd8.forward_manifest_validator import validate_disk_compliance
    except ImportError:
        logger.debug("forward_manifest_validator not available; skipping semantic repair")
        return _empty

    if not config.semantic_repair_categories:
        return _empty

    total_found = 0
    total_repaired = 0
    total_unfixable = 0
    per_file: dict[str, dict[str, object]] = {}
    pre_repair_scores: dict[str, float] = {}
    breaker_failures = 0

    for fpath in files:
        if fpath.suffix != ".py" or not fpath.is_file():
            continue

        if breaker_failures >= config.semantic_repair_circuit_breaker_threshold:
            logger.warning(
                "Semantic repair circuit breaker tripped (%d consecutive failures); "
                "skipping remaining files",
                breaker_failures,
            )
            break

        try:
            file_result = _repair_single_file(
                fpath, config, project_root,
                validate_disk_compliance, compute_disk_quality_score,
            )
        except Exception as exc:  # noqa: BLE001 — broad catch for circuit breaker
            logger.warning("Semantic repair step failed for %s: %s", fpath, exc)
            breaker_failures += 1
            continue

        if file_result is None:
            continue

        found = file_result["found"]
        repaired = file_result["repaired"]
        total_found += found

        if file_result.get("pre_score") is not None:
            pre_repair_scores[str(fpath)] = file_result["pre_score"]

        if repaired > 0:
            total_repaired += repaired
            total_unfixable += file_result.get("remaining", 0)
            breaker_failures = 0
            per_file[str(fpath)] = {
                "repaired": repaired,
                "remaining": file_result.get("remaining", 0),
                "categories": file_result.get("categories", []),
            }
        else:
            total_unfixable += found

    return {
        "issues_found": total_found,
        "issues_repaired": total_repaired,
        "issues_unfixable": total_unfixable,
        "per_file": per_file,
        "pre_repair_scores": pre_repair_scores,
    }
