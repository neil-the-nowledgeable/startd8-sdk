"""Shared prompt utilities used by both artisan and prime contractor routes."""

from __future__ import annotations

import json
from typing import Any

_BINDING_PREFIX = "[BINDING] "
_STRUCTURAL_PREFIX = "[STRUCTURAL] "
_ADVISORY_PREFIX = "[ADVISORY] "

# ---------------------------------------------------------------------------
# Tiered context rendering (TC-100 through TC-203)
# ---------------------------------------------------------------------------

# TC-100: Tier classification registry — single source of truth.
# 0 = Critical, 1 = High, 2 = Medium (default for unknown), 3 = Low/metadata.
CONTEXT_FIELD_TIERS: dict[str, int] = {
    # T0 — Critical: drives design decisions, never compressed
    "critical_parameters_checklist": 0,
    "plan_architecture": 0,
    "api_signatures": 0,
    "api_signature_verification": 0,
    "transport_protocol": 0,
    "contested_files": 0,
    "collision_resolution": 0,
    # T1 — High: frames scope and constraints
    "manifest_context": 1,
    "manifest_edit_context": 1,
    "project_goals": 1,
    "constraints_from_manifest": 1,
    "shared_modules": 1,
    "scope_boundary": 1,
    "refine_suggestions": 1,
    "plan_risks": 1,
    "plan_verification_strategy": 1,
    "complexity_guidance": 1,
    "dependency_designs": 1,
    "artifact_dependencies": 1,
    "staleness_guidance": 1,
    # T2 — Medium: informational, collapsed rendering
    "manifest_dependencies": 2,
    "parameter_sources": 2,
    "derivation_rules": 2,
    "resolved_parameters": 2,
    "output_contracts": 2,
    "lane_peer_designs": 2,
    "domain_concepts": 2,
    "objectives": 2,
    "open_questions": 2,
    "semantic_conventions": 2,
    "prior_designs": 2,
    # T3 — Low: metadata, single line, droppable
    "domain": 3,
    "siblings": 3,
    "feature_id": 3,
    "domain_reasoning": 3,
    "import_conventions": 3,
    "depth_guidance": 3,
    "wave_context": 3,
    "calibration_override_source": 3,
    "plan_delta": 3,
    "design_doc_sections": 3,
}

# TC-200: Soft token budget (tokens ≈ chars // 4).
_ADDITIONAL_CONTEXT_TOKEN_BUDGET = 4000

# Section headers per tier.
_TIER_HEADERS: dict[int, str] = {
    0: "### Critical Context",
    1: "### Design Constraints",
    2: "### Supporting Information",
    3: "### Metadata",
}

# Rendering thresholds.
_T2_STRING_TRUNCATE = 300
_T1_EMERGENCY_TRUNCATE = 500
_T3_VALUE_TRUNCATE = 60
_T2_ONELINE_TRUNCATE = 80


def _render_full(key: str, value: Any) -> str:
    """Render a field with full fidelity (T0/T1 default)."""
    if isinstance(value, str):
        return f"**{key}:** {value}"
    return f"**{key}:**\n{json.dumps(value, indent=2, default=str)}"


def _render_collapsed(key: str, value: Any) -> str:
    """Render a field with collapsed summary (T2 default)."""
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if isinstance(v, dict):
                parts.append(f"{k} {{...{len(v)} items}}")
            elif isinstance(v, list):
                parts.append(f"{k} [{len(v)} items]")
            else:
                parts.append(str(k))
        return f"**{key}:** {', '.join(parts)}"
    if isinstance(value, str):
        if len(value) > _T2_STRING_TRUNCATE:
            return (
                f"**{key}:** {value[:_T2_STRING_TRUNCATE]}"
                f"... [...{len(value) - _T2_STRING_TRUNCATE} more chars]"
            )
        return f"**{key}:** {value}"
    if isinstance(value, list):
        preview = str(value[0])[:80] if value else ""
        return f"**{key}:** {len(value)} items: \"{preview}\" [...]"
    # Fallback for other types
    return _render_full(key, value)


def _render_oneline(key: str, value: Any) -> str:
    """Render a field as a compressed one-liner (T2 under budget pressure)."""
    if isinstance(value, dict):
        return f"**{key}:** {len(value)} entries"
    s = str(value)
    if len(s) > _T2_ONELINE_TRUNCATE:
        return f"**{key}:** {s[:_T2_ONELINE_TRUNCATE]}..."
    return f"**{key}:** {s}"


def _render_metadata_line(fields: dict[str, Any]) -> str:
    """Render all T3 fields as a single pipe-delimited line."""
    parts: list[str] = []
    for k, v in fields.items():
        if isinstance(v, str):
            # Collapse multi-line to first line
            first_line = v.split("\n", 1)[0]
            if len(first_line) > _T3_VALUE_TRUNCATE:
                first_line = first_line[:_T3_VALUE_TRUNCATE] + "..."
            parts.append(f"{k}: {first_line}")
        else:
            s = str(v)
            if len(s) > _T3_VALUE_TRUNCATE:
                s = s[:_T3_VALUE_TRUNCATE] + "..."
            parts.append(f"{k}: {s}")
    return " | ".join(parts)


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length (chars // 4)."""
    return len(text) // 4


def format_tiered_context(
    additional_context: dict[str, Any] | None,
    *,
    token_budget: int = _ADDITIONAL_CONTEXT_TOKEN_BUDGET,
) -> str:
    """Render additional_context with tier-based progressive disclosure.

    Fields are grouped by tier (T0 critical → T3 metadata) with per-tier
    rendering fidelity.  When the rendered output exceeds *token_budget*,
    a progressive compression cascade drops T3, collapses T2 to one-liners,
    and finally truncates T1 strings.

    Args:
        additional_context: The ``FeatureContext.additional_context`` dict.
        token_budget: Soft token budget (default 4000).  Tokens estimated
            as ``len(chars) // 4``.

    Returns:
        Structured markdown string, or ``"None"`` for empty/None input.
    """
    if not additional_context:
        return "None"

    # Group fields by tier.
    tier_groups: dict[int, dict[str, Any]] = {0: {}, 1: {}, 2: {}, 3: {}}
    for key, value in additional_context.items():
        tier = CONTEXT_FIELD_TIERS.get(key, 2)  # TC-405: unknown → T2
        tier_groups[tier][key] = value

    # --- Initial render (full fidelity per tier) ---
    def _render_all(
        t0: dict[str, Any],
        t1: dict[str, Any],
        t2: dict[str, Any],
        t3: dict[str, Any],
        *,
        t2_renderer: Any = _render_collapsed,
        t1_truncate: int | None = None,
    ) -> str:
        sections: list[str] = []

        for tier, fields, renderer in [
            (0, t0, _render_full),
            (1, t1, _render_full),
            (2, t2, t2_renderer),
        ]:
            if not fields:
                continue
            lines: list[str] = [_TIER_HEADERS[tier]]
            for k, v in fields.items():
                if tier == 1 and t1_truncate is not None and isinstance(v, str):
                    if len(v) > t1_truncate:
                        v = v[:t1_truncate] + f"\n... [truncated to {t1_truncate} chars]"
                lines.append(renderer(k, v))
            sections.append("\n".join(lines))

        if t3:
            sections.append(
                _TIER_HEADERS[3] + "\n" + _render_metadata_line(t3)
            )

        return "\n\n".join(sections)

    output = _render_all(
        tier_groups[0], tier_groups[1], tier_groups[2], tier_groups[3],
    )

    # --- Progressive compression cascade (TC-201..TC-203) ---
    if _estimate_tokens(output) <= token_budget:
        return output

    # Step 1: Drop T3 (TC-201)
    output = _render_all(
        tier_groups[0], tier_groups[1], tier_groups[2], {},
    )
    if _estimate_tokens(output) <= token_budget:
        return output

    # Step 2: Collapse T2 to one-liners (TC-202)
    output = _render_all(
        tier_groups[0], tier_groups[1], tier_groups[2], {},
        t2_renderer=_render_oneline,
    )
    if _estimate_tokens(output) <= token_budget:
        return output

    # Step 3: Truncate T1 strings to 500 chars (TC-203)
    output = _render_all(
        tier_groups[0], tier_groups[1], tier_groups[2], {},
        t2_renderer=_render_oneline,
        t1_truncate=_T1_EMERGENCY_TRUNCATE,
    )
    return output


def format_constraints(constraints: list[str]) -> str:
    """Group constraints by ``[BINDING]``/``[STRUCTURAL]``/``[ADVISORY]`` prefix.

    Tagged constraints are stripped of their prefix and grouped under markdown
    ``###`` headers.  Untagged constraints are rendered as a flat bullet list
    after the tagged groups.

    Args:
        constraints: Constraint strings, optionally prefixed with a priority
            tag (e.g. ``"[BINDING] Must use X"``).

    Returns:
        Markdown string with grouped sections, or ``""`` if *constraints*
        is empty.  Example output::

            ### Binding (must not violate)
            - Must use X
            ### Advisory (prefer but not blocking)
            - Prefer stdlib
    """
    if not constraints:
        return ""

    groups: dict[str, list[str]] = {
        "binding": [],
        "structural": [],
        "advisory": [],
        "other": [],
    }
    for c in constraints:
        if c.startswith(_BINDING_PREFIX):
            groups["binding"].append(c.removeprefix(_BINDING_PREFIX))
        elif c.startswith(_STRUCTURAL_PREFIX):
            groups["structural"].append(c.removeprefix(_STRUCTURAL_PREFIX))
        elif c.startswith(_ADVISORY_PREFIX):
            groups["advisory"].append(c.removeprefix(_ADVISORY_PREFIX))
        else:
            groups["other"].append(c)

    parts: list[str] = []
    if groups["binding"]:
        parts.append("### Binding (must not violate)")
        parts.extend(f"- {c}" for c in groups["binding"])
    if groups["structural"]:
        parts.append("### Structural (code organization)")
        parts.extend(f"- {c}" for c in groups["structural"])
    if groups["advisory"]:
        parts.append("### Advisory (prefer but not blocking)")
        parts.extend(f"- {c}" for c in groups["advisory"])
    if groups["other"]:
        parts.extend(f"- {c}" for c in groups["other"])
    return "\n".join(parts)


def find_missing_parameters(
    text: str,
    resolved_parameters: list[dict],
) -> list[dict]:
    """Return resolved parameters whose ``key_value`` is not found in *text*.

    Args:
        text: The document text to search (e.g. a design document).
        resolved_parameters: List of parameter dicts, each expected to
            contain a ``"key_value"`` key.

    Returns:
        Subset of *resolved_parameters* whose ``key_value`` does not appear
        as a substring of *text*.  Empty list if all are present.
    """
    missing = []
    for param in resolved_parameters:
        key_value = param.get("key_value", "")
        if key_value and key_value not in text:
            missing.append(param)
    return missing
