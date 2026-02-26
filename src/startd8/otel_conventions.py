"""Centralized OTel semantic conventions for the StartD8 SDK.

Defines span names, attribute keys, event names, and degradation reason
codes used across the Artisan pipeline instrumentation (OT-503).

No runtime OTel dependency — pure constants, importable without OTel
installed.
"""

from __future__ import annotations


class SpanNames:
    """Canonical span names for the Artisan pipeline."""

    # Phase-level
    PHASE_PREFIX = "phase."

    # Gate spans
    GATE_ENTRY = "gate.entry"
    GATE_EXIT = "gate.exit"

    # Design phase
    DESIGN_GENERATE = "design.generate"
    DESIGN_REVIEW = "design.review"
    DESIGN_REVISION = "design.revision"

    # Implement phase
    IMPLEMENT_CHUNK = "implement.chunk"

    # Test phase
    TEST_GENERATE = "test.generate"
    TEST_RETRY = "test.retry"

    # Review phase
    REVIEW_EVALUATE = "review.evaluate"


class AttributeKeys:
    """Canonical attribute key names."""

    # Phase
    PHASE_NAME = "phase.name"
    PHASE_ATTEMPT = "phase.attempt"
    PHASE_STATUS = "phase.status"
    PHASE_COST = "phase.cost"
    PHASE_DURATION = "phase.duration_seconds"

    # Gate
    GATE_PHASE = "gate.phase"
    GATE_PASSED = "gate.passed"
    GATE_PROPAGATION_STATUS = "gate.propagation_status"

    # Task
    TASK_ID = "task.id"
    TASK_TITLE = "task.title"
    TASK_DOMAIN = "task.domain"
    TASK_PHASE = "task.phase"
    TASK_TARGET_FILES = "task.target_files"
    TASK_STATUS = "task.status"
    TASK_COST = "task.cost"
    TASK_ATTEMPTS = "task.attempts"

    # Complexity-Driven Model Router (CMR) — REQ-CMR-031
    TASK_COMPLEXITY_TIER = "task.complexity_tier"
    TASK_BLAST_RADIUS = "task.blast_radius"
    TASK_CALLER_COUNT = "task.caller_count"
    TASK_HAS_DYNAMIC_DISPATCH = "task.has_dynamic_dispatch"

    # LLM call
    LLM_PROMPT_LENGTH = "llm.prompt_length"
    LLM_MAX_TOKENS = "llm.max_tokens"
    LLM_RESPONSE_TIME_MS = "llm.response_time_ms"
    LLM_TOKENS_INPUT = "llm.tokens_input"
    LLM_TOKENS_OUTPUT = "llm.tokens_output"
    LLM_COST_USD = "llm.cost_usd"


class EventNames:
    """Canonical event names."""

    LLM_CALL = "llm.call"
    LLM_CALL_START = "llm.call.start"
    LLM_CALL_COMPLETE = "llm.call.complete"
    FORENSIC_LOG_ERROR = "forensic_log.error"
    CONTEXT_DEFAULTED = "context.defaulted"
    CONTEXT_PROPAGATED = "context.propagated"
    PHASE_TIMEOUT = "phase.timeout"
    PHASE_RETRY = "phase.retry"
    EDIT_FIRST_SIZE_REGRESSION = "edit_first.size_regression"


class DegradationReasons:
    """Reason codes for the ``degradation_reasons`` field in forensic logs.

    Each constant maps to one of the 13 conditions evaluated by
    ``is_degraded()`` in ``forensic_log.py`` (OT-711).
    """

    DOMAIN_DEFAULTED = "DOMAIN_DEFAULTED"
    DESIGN_DOC_MISSING = "DESIGN_DOC_MISSING"
    DESIGN_CALIBRATION_MISSING = "DESIGN_CALIBRATION_MISSING"
    PROMPT_CONSTRAINTS_EMPTY = "PROMPT_CONSTRAINTS_EMPTY"
    PARAMETER_SOURCES_MISSING = "PARAMETER_SOURCES_MISSING"
    FILE_INVENTORY_MISSING = "FILE_INVENTORY_MISSING"
    DEPTH_TIER_NULL = "DEPTH_TIER_NULL"
    DESIGN_DOC_EMPTY = "DESIGN_DOC_EMPTY"
    ENTRY_GATE_FAILED = "ENTRY_GATE_FAILED"
    BOUNDARY_SEVERITY_HIGH = "BOUNDARY_SEVERITY_HIGH"
    CHAIN_DEGRADED = "CHAIN_DEGRADED"
    QUALITY_VIOLATIONS_PRESENT = "QUALITY_VIOLATIONS_PRESENT"
    COMPLEXITY_MANIFEST_MISSING = "COMPLEXITY_MANIFEST_MISSING"


# Valid call_type values for emit_forensic_log().
# NOTE: These are semantic call types (e.g. "design.revise"), distinct from
# SpanNames (e.g. DESIGN_REVISION = "design.revision"). SpanNames follow OTel
# noun-form conventions; call_types use verb-form to describe the action taken.
VALID_CALL_TYPES = frozenset({
    "design.generate",
    "design.review",
    "design.revise",
    "implement.chunk",
    "implement.chunk.refine",
    "test.generate",
    "test.retry",
    "review.evaluate",
})


# Schema version for forensic log entries
FORENSIC_LOG_SCHEMA_VERSION = "1.0.0"
