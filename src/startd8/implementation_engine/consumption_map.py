"""Static seed field consumption map (REQ-SU-201).

Replaces dynamic field-access tracing (KSU-100) with a static constant
that documents which seed fields are read by which consumer, enabling
"unused" and "missing" field reports at seed load time with zero runtime
overhead.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set


# Each entry: consumer module, impact level, and notes.
# Impact levels:
#   critical — queue deadlock or no output without this field
#   high     — significantly affects generation quality
#   medium   — improves output but has graceful fallback
#   low      — informational / telemetry only
SEED_FIELD_CONSUMPTION_MAP: Dict[str, Dict[str, str]] = {
    # --- Task-level fields (inside tasks[].config.context) ---
    "task_description": {
        "consumer": "spec_builder.build_spec_prompt",
        "impact": "critical",
        "notes": "Primary LLM instruction. Thin descriptions (<100 chars) produce poor code.",
    },
    "target_files": {
        "consumer": "spec_builder, drafter, queue",
        "impact": "critical",
        "notes": "Output file paths, multi-file format selection, skeleton matching.",
    },
    "depends_on": {
        "consumer": "queue.get_next_feature",
        "impact": "critical",
        "notes": "Task ordering. Circular deps deadlock the queue.",
    },
    "element_tiers": {
        "consumer": "spec_builder (pre-assembly), drafter (skeleton_fill)",
        "impact": "high",
        "notes": "Drives draft mode selection and scope narrowing. Absence = full-file generation.",
    },
    "skeleton_sources": {
        "consumer": "drafter._detect_skeleton_fill",
        "impact": "high",
        "notes": "Pre-assembled code skeleton for fill-in. Requires element_tiers too.",
    },
    "existing_files": {
        "consumer": "drafter._resolve_draft_mode",
        "impact": "high",
        "notes": "Switches between create/edit/search_replace modes.",
    },
    "kaizen_hints": {
        "consumer": "spec_builder, drafter",
        "impact": "high",
        "notes": "Quality guidance from prior runs. Split on security/quality.",
    },
    "quality_hints": {
        "consumer": "spec_builder, drafter",
        "impact": "medium",
        "notes": "Per-task quality guidance from review feedback loop (REQ-RFL-300).",
    },
    "runtime_dependencies": {
        "consumer": "spec_builder.build_spec_available_imports",
        "impact": "medium",
        "notes": "Available imports section. Empty = LLM guesses.",
    },
    "negative_scope": {
        "consumer": "embedded in task_description",
        "impact": "medium",
        "notes": "Exclusions to reduce hallucination. Consumed as prose, not structured.",
    },
    "api_signatures": {
        "consumer": "embedded in task_description",
        "impact": "medium",
        "notes": "Interface contracts. Consumed as prose, not structured.",
    },
    "design_document": {
        "consumer": "spec_builder",
        "impact": "high",
        "notes": "Design doc forwarded via Mottainai Rule 2.",
    },
    "design_doc_sections": {
        "consumer": "spec_builder",
        "impact": "medium",
        "notes": "Key implementation constraints from design phase.",
    },
    "forward_contracts": {
        "consumer": "spec_builder, drafter",
        "impact": "medium",
        "notes": "Interface contract bindings from forward manifest.",
    },
    "forward_element_specs": {
        "consumer": "spec_builder",
        "impact": "medium",
        "notes": "Expected code elements from forward manifest.",
    },
    "domain_constraints": {
        "consumer": "spec_builder",
        "impact": "medium",
        "notes": "Domain-specific constraints from preflight.",
    },
    "requirements_text": {
        "consumer": "spec_builder",
        "impact": "medium",
        "notes": "Requirements passthrough for traceability.",
    },
    "critical_parameters": {
        "consumer": "spec_builder, drafter",
        "impact": "medium",
        "notes": "Critical parameter injection.",
    },
    "reference_implementation": {
        "consumer": "spec_builder",
        "impact": "low",
        "notes": "Copy-and-modify reference. P3 priority (dropped first under budget).",
    },
    # --- Seed-level fields ---
    "architectural_context": {
        "consumer": "spec_builder (P2 section)",
        "impact": "medium",
        "notes": "Shared module analysis, integration points.",
    },
    "design_calibration": {
        "consumer": "prime_contractor (token budget)",
        "impact": "medium",
        "notes": "Per-task depth tiers for generation verbosity.",
    },
    "onboarding": {
        "consumer": "prime_contractor (mode detection)",
        "impact": "medium",
        "notes": "Semantic conventions, project objectives.",
    },
    "service_metadata": {
        "consumer": "prime_contractor (protocol-aware gen)",
        "impact": "medium",
        "notes": "Protocol classification for Dockerfiles and services.",
    },
    "output_format": {
        "consumer": "spec_builder.build_spec_context_section",
        "impact": "low",
        "notes": "Output formatting hints. Rarely populated.",
    },
    "language_profile": {
        "consumer": "spec_builder, drafter",
        "impact": "medium",
        "notes": "Language-specific extension filtering, stub markers, anti-patterns.",
    },
    "security_contract": {
        "consumer": "drafter",
        "impact": "medium",
        "notes": "Security validation rules.",
    },
    "plan_risk_register": {
        "consumer": "spec_builder (P3 section)",
        "impact": "low",
        "notes": "Risk register extracted from plan document (REQ-SU-500).",
    },
    "plan_verification_criteria": {
        "consumer": "spec_builder (P3 section)",
        "impact": "low",
        "notes": "Verification criteria extracted from plan document (REQ-SU-500).",
    },
}

# Fields classified as critical or high impact.
_HIGH_IMPACT_FIELDS = frozenset(
    name for name, meta in SEED_FIELD_CONSUMPTION_MAP.items()
    if meta["impact"] in ("critical", "high")
)


def compute_seed_consumption_report(
    seed_fields: Set[str],
) -> Dict[str, Any]:
    """Diff actual seed fields against the consumption map.

    Args:
        seed_fields: Set of field names present in the seed (both
            top-level and per-task ``config.context`` keys).

    Returns:
        Dict with ``unused_fields``, ``missing_high_impact_fields``,
        and ``coverage_pct``.
    """
    known = set(SEED_FIELD_CONSUMPTION_MAP)
    present_known = seed_fields & known
    unused = sorted(seed_fields - known)
    missing_high = sorted(_HIGH_IMPACT_FIELDS - seed_fields)

    coverage = (len(present_known) / len(known) * 100) if known else 0.0

    return {
        "unused_fields": unused,
        "missing_high_impact_fields": missing_high,
        "coverage_pct": round(coverage, 1),
        "present_count": len(present_known),
        "total_known": len(known),
    }
