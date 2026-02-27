"""Forensic LLM Call Logging (OT-712).

Provides ``emit_forensic_log()`` — the single chokepoint for structured
forensic log entries emitted at every LLM call site in the Artisan
pipeline.  Each log entry captures full context metadata: contract state,
propagation diagnostics, provenance, and OTel exemplars for trace-log
correlation.

Design principles:
- "Prescriptive Over Descriptive" (DP-1)
- "Observable Contracts Over Invisible Guarantees" (DP-6)
- "Trace Context Propagation" (DP-3)

Public API (``__all__``):
- ``emit_forensic_log`` — centralized log builder
- ``emit_quality_gate_log`` — centralized quality-gate decision log builder
- ``CallMetadata``, ``TaskMetadata``, ``ContextPropagationMetadata``,
  ``ProvenanceMetadata`` — dict type aliases (documented field contracts)
- ``set_boundary_result``, ``get_boundary_result``,
  ``reset_boundary_result`` — ContextVar accessors
- ``is_degraded`` — degradation evaluator
- ``ModelSpecProvider`` — protocol for model spec access
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any, Protocol, runtime_checkable

from startd8.logging_config import get_logger
from startd8.otel_conventions import (
    FORENSIC_LOG_SCHEMA_VERSION,
    VALID_CALL_TYPES,
    DegradationReasons,
    EventNames,
)

# ---------------------------------------------------------------------------
# OTel guard pattern (module-level, per R3-S5)
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace as _trace

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

# ---------------------------------------------------------------------------
# Typed metadata classes (OT-712 AC-10, R4-S1)
# ---------------------------------------------------------------------------

# Using plain dicts with documentation rather than TypedDict to avoid
# Python 3.9 compatibility issues with TypedDict(total=False) + union types.
# The interface contract is enforced by documentation and tests.

# CallMetadata fields:
#   prompt_length: int | None
#   max_tokens: int | None
#   model_spec: str | None
#   response_time_ms: int | None
#   tokens_input: int | None
#   tokens_output: int | None
#   cost_usd: float | None
#   attempt: int | None
#   max_attempts: int | None

# TaskMetadata fields:
#   task_id: str | None
#   title: str | None
#   domain: str | None
#   feature_id: str | None
#   phase: str | None
#   target_files: list[str] | None

# ContextPropagationMetadata fields:
#   domain_source: str | None
#   domain_defaulted: bool | None
#   prompt_constraints_count: int | None
#   environment_checks_count: int | None
#   design_calibration_present: bool | None
#   depth_tier: str | None
#   design_doc_present: bool | None
#   design_doc_line_count: int | None
#   parameter_sources_present: bool | None
#   existing_file_inventory_present: bool | None

# ProvenanceMetadata fields:
#   workflow_id: str | None
#   iteration: int | None
#   prior_design_available: bool | None
#   reviewer_verdict: str | None
#   arbiter_verdict: str | None

# Type aliases for documentation clarity
CallMetadata = dict[str, Any]
TaskMetadata = dict[str, Any]
ContextPropagationMetadata = dict[str, Any]
ProvenanceMetadata = dict[str, Any]


__all__ = [
    "emit_forensic_log",
    "emit_quality_gate_log",
    "CallMetadata",
    "TaskMetadata",
    "ContextPropagationMetadata",
    "ProvenanceMetadata",
    "set_boundary_result",
    "get_boundary_result",
    "reset_boundary_result",
    "is_degraded",
    "ModelSpecProvider",
]


# ---------------------------------------------------------------------------
# ModelSpecProvider Protocol (OT-714 AC-6)
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelSpecProvider(Protocol):
    """Protocol for objects that can provide their model spec string."""

    def get_model_spec(self) -> str | None: ...


# ---------------------------------------------------------------------------
# ContextVar for boundary result propagation (OT-710 AC-9)
# ---------------------------------------------------------------------------

_boundary_result_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "boundary_result", default=None
)


def set_boundary_result(result: Any) -> contextvars.Token:
    """Store a BoundaryResult in the current context.

    Called by ``_execute_phase()`` after entry gate validation.
    The token must be used to reset via ``reset_boundary_result()``
    in a ``finally`` block.

    Args:
        result: A BoundaryResult object (or None).

    Returns:
        A contextvars.Token for resetting.
    """
    return _boundary_result_var.set(result)


def get_boundary_result() -> Any:
    """Retrieve the current BoundaryResult from the ContextVar.

    Returns:
        The BoundaryResult set by the enclosing phase, or None.
    """
    return _boundary_result_var.get()


def reset_boundary_result(token: contextvars.Token) -> None:
    """Reset the boundary result ContextVar to its previous value.

    Encapsulates the private ``_boundary_result_var.reset()`` so callers
    don't need to import the private ContextVar directly.

    Args:
        token: The token returned by ``set_boundary_result()``.
    """
    _boundary_result_var.reset(token)


# ---------------------------------------------------------------------------
# List truncation limits (OT-716)
# ---------------------------------------------------------------------------

_MAX_TARGET_FILES = 20
_MAX_QUALITY_VIOLATIONS = 20
_MAX_DEGRADATION_REASONS = 50

# ---------------------------------------------------------------------------
# Sentinel for boundary_result_override
# ---------------------------------------------------------------------------

_SENTINEL = object()

# ---------------------------------------------------------------------------
# Log level map (module-level constant, avoids per-call dict creation — C4)
# ---------------------------------------------------------------------------

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
}


# ---------------------------------------------------------------------------
# is_degraded() — OT-711
# ---------------------------------------------------------------------------


def is_degraded(
    call_type: str,
    context_propagation: dict[str, Any],
    boundary_result: Any,
) -> tuple[bool, list[str]]:
    """Evaluate whether the context for this LLM call is degraded.

    Checks 12 conditions and returns a boolean plus the list of reason
    codes that triggered.  Used for WARNING-level filtering.

    Args:
        call_type: The forensic log call type (e.g. "design.generate").
        context_propagation: The context propagation metadata dict.
        boundary_result: The BoundaryResult from the ContextVar (may be None).

    Returns:
        ``(is_degraded, reason_codes)`` — True if any condition fires.
    """
    # Guard: None/empty call_type cannot be split (P2)
    if not call_type:
        return (False, [])

    reasons: list[str] = []
    phase = call_type.split(".")[0]

    # 1. domain_defaulted is true
    if context_propagation.get("domain_defaulted") is True:
        reasons.append(DegradationReasons.DOMAIN_DEFAULTED)

    # 2. design_doc_present is false (at IMPLEMENT/TEST/REVIEW)
    if phase in ("implement", "test", "review"):
        if context_propagation.get("design_doc_present") is False:
            reasons.append(DegradationReasons.DESIGN_DOC_MISSING)

    # 3. design_calibration_present is false (at DESIGN)
    if phase == "design":
        if context_propagation.get("design_calibration_present") is False:
            reasons.append(DegradationReasons.DESIGN_CALIBRATION_MISSING)

    # 4. prompt_constraints_count is 0 (at IMPLEMENT)
    if phase == "implement":
        if context_propagation.get("prompt_constraints_count") == 0:
            reasons.append(DegradationReasons.PROMPT_CONSTRAINTS_EMPTY)

    # 5. parameter_sources_present is false (at REVIEW)
    if phase == "review":
        if context_propagation.get("parameter_sources_present") is False:
            reasons.append(DegradationReasons.PARAMETER_SOURCES_MISSING)

    # 6. existing_file_inventory_present is false (at TEST)
    if phase == "test":
        if context_propagation.get("existing_file_inventory_present") is False:
            reasons.append(DegradationReasons.FILE_INVENTORY_MISSING)

    # 7. depth_tier is null
    if context_propagation.get("depth_tier") is None:
        reasons.append(DegradationReasons.DEPTH_TIER_NULL)

    # 8. design_doc_line_count is 0 when design_doc_present is true
    if (
        context_propagation.get("design_doc_present") is True
        and context_propagation.get("design_doc_line_count") == 0
    ):
        reasons.append(DegradationReasons.DESIGN_DOC_EMPTY)

    # 8b. manifest coverage absent for complexity routing signals (REQ-CMR-034)
    if phase == "implement":
        if context_propagation.get("complexity_manifest_coverage") == "none":
            reasons.append(DegradationReasons.COMPLEXITY_MANIFEST_MISSING)

    # 9-12: Contract state conditions (from boundary result)
    if boundary_result is not None:
        # 9. entry_gate_passed is false
        if getattr(boundary_result, "passed", None) is False:
            reasons.append(DegradationReasons.ENTRY_GATE_FAILED)

        # 10. boundary_severity_max is WARNING or BLOCKING
        sev = _resolve_enum_str(
            boundary_result, "boundary_severity_max", "severity"
        )
        if sev and sev.upper() in ("WARNING", "BLOCKING"):
            reasons.append(DegradationReasons.BOUNDARY_SEVERITY_HIGH)

        # 11. Any chain_statuses value is DEGRADED or BROKEN
        chain_statuses = getattr(boundary_result, "chain_statuses", None)
        if chain_statuses and isinstance(chain_statuses, dict):
            for chain_name, status in chain_statuses.items():
                status_str = getattr(status, "value", str(status)).upper()
                if status_str in ("DEGRADED", "BROKEN"):
                    reasons.append(
                        f"{DegradationReasons.CHAIN_DEGRADED}:{chain_name}"
                    )

        # 12. quality_violations is non-empty (R5: truthiness implies len>0)
        qv = getattr(boundary_result, "quality_violations", None)
        if qv is None:
            qv = getattr(boundary_result, "blocking_failures", None)
        if qv:
            reasons.append(DegradationReasons.QUALITY_VIOLATIONS_PRESENT)

    return (len(reasons) > 0, reasons)


# ---------------------------------------------------------------------------
# emit_forensic_log() — the centralized log builder (OT-712)
# ---------------------------------------------------------------------------


def emit_forensic_log(
    *,
    call_type: str,
    call: dict[str, Any],
    task: dict[str, Any],
    context_propagation: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    boundary_result_override: Any = _SENTINEL,
    forensic_log_level: str = "INFO",
) -> None:
    """Emit a structured forensic log entry for an LLM call.

    This is the single chokepoint for all 7 call sites in the Artisan
    pipeline.  It assembles the full OT-700 schema, evaluates degradation,
    extracts OTel exemplars, and emits via ``get_logger()``.

    Never raises exceptions — internal errors are recorded as OTel span
    events (OT-712 AC-8).

    Args:
        call_type: One of 7 valid call types (e.g. "design.generate").
        call: CallMetadata dict with LLM call details.
        task: TaskMetadata dict with task context.
        context_propagation: ContextPropagationMetadata dict.
        provenance: Optional ProvenanceMetadata dict.
        boundary_result_override: For testing — override the ContextVar
            lookup.  Use ``_SENTINEL`` (default) for normal operation.
        forensic_log_level: "DEBUG", "INFO", or "WARNING".
    """
    try:
        # --- Input validation (OT-712 AC-11) ---
        _validate_inputs(call_type, call, task)

        # --- Boundary result (OT-710) ---
        if boundary_result_override is not _SENTINEL:
            br = boundary_result_override
        else:
            br = get_boundary_result()

        # --- Degradation evaluation (OT-711) ---
        degraded, degradation_reasons = is_degraded(
            call_type, context_propagation, br
        )

        # --- WARNING-level filtering ---
        if forensic_log_level == "WARNING" and not degraded:
            return

        # --- OTel exemplars (OT-708) ---
        trace_id, span_id = _extract_exemplars()

        # --- Contract state construction (OT-710) ---
        contract_state = _build_contract_state(br)

        # --- List truncation (OT-716) ---
        target_files = task.get("target_files")
        target_files_truncated = False
        if target_files and len(target_files) > _MAX_TARGET_FILES:
            target_files = target_files[:_MAX_TARGET_FILES]
            target_files_truncated = True

        qv = contract_state.get("quality_violations", [])
        qv_truncated = False
        if qv and len(qv) > _MAX_QUALITY_VIOLATIONS:
            qv = qv[:_MAX_QUALITY_VIOLATIONS]
            qv_truncated = True
            contract_state["quality_violations"] = qv

        dr_truncated = False
        if len(degradation_reasons) > _MAX_DEGRADATION_REASONS:
            degradation_reasons = degradation_reasons[:_MAX_DEGRADATION_REASONS]
            dr_truncated = True

        # --- Assemble the log entry (OT-700 schema) ---
        entry = {
            "event": EventNames.LLM_CALL,
            "schema_version": FORENSIC_LOG_SCHEMA_VERSION,
            "call_type": call_type,
            "call": {
                "prompt_length": call.get("prompt_length"),
                "max_tokens": call.get("max_tokens"),
                "model_spec": call.get("model_spec"),
                "response_time_ms": call.get("response_time_ms"),
                "tokens_input": call.get("tokens_input"),
                "tokens_output": call.get("tokens_output"),
                "cost_usd": call.get("cost_usd"),
                "attempt": call.get("attempt"),
                "max_attempts": call.get("max_attempts"),
            },
            "task": {
                "task_id": task.get("task_id"),
                "title": task.get("title"),
                "domain": task.get("domain"),
                "feature_id": task.get("feature_id"),
                "phase": task.get("phase"),
                "target_files": target_files,
                "target_files_truncated": target_files_truncated,
            },
            "context_propagation": {
                "domain_source": context_propagation.get("domain_source"),
                "domain_defaulted": context_propagation.get("domain_defaulted"),
                "prompt_constraints_count": context_propagation.get(
                    "prompt_constraints_count"
                ),
                "environment_checks_count": context_propagation.get(
                    "environment_checks_count"
                ),
                "design_calibration_present": context_propagation.get(
                    "design_calibration_present"
                ),
                "depth_tier": context_propagation.get("depth_tier"),
                "design_doc_present": context_propagation.get("design_doc_present"),
                "design_doc_line_count": context_propagation.get(
                    "design_doc_line_count"
                ),
                "parameter_sources_present": context_propagation.get(
                    "parameter_sources_present"
                ),
                "existing_file_inventory_present": context_propagation.get(
                    "existing_file_inventory_present"
                ),
            },
            "contract_state": contract_state,
            "provenance": {
                "workflow_id": (provenance or {}).get("workflow_id"),
                "iteration": (provenance or {}).get("iteration"),
                "prior_design_available": (provenance or {}).get(
                    "prior_design_available"
                ),
                "reviewer_verdict": (provenance or {}).get("reviewer_verdict"),
                "arbiter_verdict": (provenance or {}).get("arbiter_verdict"),
            },
            "exemplars": {
                "trace_id": trace_id,
                "span_id": span_id,
            },
            "degraded": degraded,
            "degradation_reasons": degradation_reasons,
            "degradation_reasons_truncated": dr_truncated,
            "quality_violations_truncated": qv_truncated,
        }

        # --- Emit via get_logger() (OT-700 AC-5, OT-715) ---
        flogger = get_logger(__name__)

        level = _resolve_log_level(forensic_log_level)
        # "forensic" is safe as an extra key — not in Python's LogRecord
        # reserved attributes (SDK Leg 9 #1).
        flogger.log(level, "llm.call", extra={"forensic": entry})

    except Exception as exc:
        # OT-712 AC-8: Record error on current OTel span, never raise
        _record_internal_error(call_type, exc)


def emit_quality_gate_log(
    *,
    gate_id: str,
    phase: str,
    policy_mode: str,
    threshold: dict[str, Any] | None,
    observed_value: Any,
    decision: str,
    violated: bool,
    contract_signal_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Emit a structured forensic log entry for a quality gate decision.

    The payload mirrors the runtime gate object so downstream artifacts can
    trace each decision (phase, mode, threshold, observed value, decision).
    Never raises.
    """
    try:
        trace_id, span_id = _extract_exemplars()
        entry = {
            "event": "quality.gate",
            "schema_version": FORENSIC_LOG_SCHEMA_VERSION,
            "gate_id": gate_id,
            "contract_signal_id": contract_signal_id,
            "phase": phase,
            "policy_mode": policy_mode,
            "threshold": threshold or {},
            "observed_value": observed_value,
            "decision": decision,
            "violated": violated,
            "details": details or {},
            "exemplars": {
                "trace_id": trace_id,
                "span_id": span_id,
            },
        }
        get_logger(__name__).info("quality.gate", extra={"forensic": entry})
    except Exception as exc:
        _record_internal_error("quality.gate", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_enum_str(
    obj: Any, attr: str, fallback_attr: str | None = None,
) -> str | None:
    """Safely extract a string from an attribute that may be an enum.

    Handles the common OTel/contract pattern where a value may be a raw
    string, an enum with a ``.value`` attribute, or absent entirely.

    Args:
        obj: The object to read from.
        attr: Primary attribute name.
        fallback_attr: Optional fallback attribute name if primary is None.

    Returns:
        The string value, or None if not found.
    """
    val = getattr(obj, attr, None)
    if val is None and fallback_attr is not None:
        val = getattr(obj, fallback_attr, None)
    if val is None:
        return None
    return getattr(val, "value", str(val))


def _validate_inputs(
    call_type: str,
    call: dict[str, Any],
    task: dict[str, Any],
) -> None:
    """Validate inputs per OT-712 AC-11.

    Raises ValueError on invalid inputs (caught by the outer try/except).
    """
    if call_type not in VALID_CALL_TYPES:
        raise ValueError(
            f"Invalid call_type '{call_type}'; "
            f"must be one of {sorted(VALID_CALL_TYPES)}"
        )

    # Numeric fields must be non-negative when non-None
    for key in ("prompt_length", "max_tokens", "response_time_ms",
                "tokens_input", "tokens_output", "attempt", "max_attempts"):
        val = call.get(key)
        if val is not None and isinstance(val, (int, float)) and val < 0:
            raise ValueError(
                f"call.{key} must be non-negative, got {val}"
            )

    cost = call.get("cost_usd")
    if cost is not None and isinstance(cost, (int, float)) and cost < 0:
        raise ValueError(f"call.cost_usd must be non-negative, got {cost}")

    # String fields must be non-empty when non-None
    for key in ("task_id", "title", "domain"):
        val = task.get(key)
        if val is not None and isinstance(val, str) and not val:
            raise ValueError(
                f"task.{key} must be non-empty when provided"
            )


def _extract_exemplars() -> tuple[str | None, str | None]:
    """Extract trace_id and span_id from the current OTel span (OT-708).

    Returns (None, None) when OTel is unavailable or span is not recording.
    """
    if not _HAS_OTEL:
        return None, None

    try:
        # get_current_span() never returns None — it returns INVALID_SPAN
        # when no span is active.  Check the span context directly (R2).
        span = _trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid:
            return None, None
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")
        return trace_id, span_id
    except Exception:
        get_logger(__name__).debug(
            "OTel exemplar extraction failed", exc_info=True,
        )
        return None, None


def _build_contract_state(boundary_result: Any) -> dict[str, Any]:
    """Construct the contract_state section from a BoundaryResult.

    Args:
        boundary_result: The BoundaryResult object (may be None).

    Returns:
        Dict with entry_gate_passed, propagation_status, chain_statuses,
        boundary_severity_max, quality_violations.
    """
    if boundary_result is None:
        return {
            "entry_gate_passed": None,
            "propagation_status": None,
            "chain_statuses": None,
            "boundary_severity_max": None,
            "quality_violations": [],
        }

    passed = getattr(boundary_result, "passed", None)
    prop_status = _resolve_enum_str(boundary_result, "propagation_status")

    chain_statuses_raw = getattr(boundary_result, "chain_statuses", None)
    chain_statuses = None
    if chain_statuses_raw and isinstance(chain_statuses_raw, dict):
        chain_statuses = {
            k: getattr(v, "value", str(v))
            for k, v in chain_statuses_raw.items()
        }

    sev = _resolve_enum_str(boundary_result, "boundary_severity_max")

    qv = getattr(boundary_result, "quality_violations", None)
    if qv is None:
        qv = getattr(boundary_result, "blocking_failures", None)
    if qv is None:
        qv = []
    else:
        qv = list(qv)

    return {
        "entry_gate_passed": passed,
        "propagation_status": prop_status,
        "chain_statuses": chain_statuses,
        "boundary_severity_max": sev,
        "quality_violations": qv,
    }


def _resolve_log_level(forensic_log_level: str) -> int:
    """Map the forensic_log_level string to a logging level int."""
    return _LEVEL_MAP.get(forensic_log_level.upper(), logging.INFO)


def _record_internal_error(call_type: str, exc: Exception) -> None:
    """Record an internal forensic logging error on the current OTel span.

    Uses ``get_logger()`` for OTel bridge forwarding.
    Never raises.
    """
    try:
        _fallback_logger = get_logger(__name__)

        _fallback_logger.warning(
            "Forensic log emission failed for call_type=%s: %s",
            call_type, exc,
        )

        # OTel span event (OT-712 AC-8)
        if _HAS_OTEL:
            span = _trace.get_current_span()
            if span is not None and hasattr(span, "add_event"):
                span.add_event(
                    EventNames.FORENSIC_LOG_ERROR,
                    attributes={
                        "error.type": type(exc).__name__,
                        "error.message": str(exc),
                        "error.call_type": call_type or "",
                    },
                )
    except Exception:
        # Absolute last resort — emit a debug trace so failures are
        # discoverable when explicitly sought, then suppress (E1).
        get_logger(__name__).debug(
            "_record_internal_error itself failed", exc_info=True,
        )
