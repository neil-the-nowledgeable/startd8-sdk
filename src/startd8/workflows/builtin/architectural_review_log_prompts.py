"""Prompt builder functions for the architectural review workflow.

Depends on :mod:`architectural_review_log_constants` (leaf) and
:mod:`prompts` (YAML loader).  Three of the five builders delegate
to externalized YAML templates via ``format_prompt()``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from .architectural_review_log_constants import (
    ALLOWED_AREAS,
    ALLOWED_SEVERITIES,
    REQUIRED_COLUMNS,
    REVIEW_PROFILES,
    _normalize_area,
    _now_utc,
    _OPTIONAL_COLUMN_DEFAULT,
)
from .prompts import format_prompt


# ---------------------------------------------------------------------------
# _build_prompt  (review template — YAML-backed)
# ---------------------------------------------------------------------------

def _build_prompt(
    document_without_appendix: str,
    applied_ids: List[str],
    rejected_ids: List[str],
    round_number: int,
    max_suggestions: int,
    reviewer_label: str,
    scope: str,
    template_override: Optional[str] = None,
    context_content: str = "",
    substantially_addressed_areas: Optional[Dict[str, List[str]]] = None,
    area_coverage: Optional[Dict[str, Dict[str, Any]]] = None,
    allowed_areas: Optional[Set[str]] = None,
    persona: Optional[str] = None,
    focus_guidance: Optional[str] = None,
    requirements_content: Optional[str] = None,
    has_feature_requirements: bool = False,
    use_system_prompt: bool = False,
) -> str:
    """
    Build the reviewer prompt. Supports override template that must include:
    - {round_number}, {max_suggestions}, {applied_ids}, {rejected_ids}, {document}, {reviewer_label}, {scope}
    - Optional: {context} (reference material block, empty string when no context provided)

    When *use_system_prompt* is True the document body, context, and
    requirements blocks are omitted (expected in the system prompt via
    ``_build_shared_system_prompt``).

    Note: template_override uses Python ``str.format()``; literal braces in the
    template must be doubled (``{{`` / ``}}``) to avoid ``KeyError``.
    """
    applied_list = ", ".join(applied_ids[:50]) if applied_ids else "(none)"
    rejected_list = ", ".join(rejected_ids[:50]) if rejected_ids else "(none)"
    areas = allowed_areas or ALLOWED_AREAS
    role = persona or "expert enterprise architect"
    default_focus = "architecture clarity, execution safety, risk management, validation completeness, and operational readiness"
    focus = focus_guidance or default_focus

    context_block = ""
    if not use_system_prompt and context_content.strip():
        context_block = (
            "Reference material (institutional knowledge, lessons learned, prior decisions "
            "— use these to ground your review in project-specific patterns and known issues):\n"
            "---\n"
            f"{context_content}\n"
            "---\n\n"
        )

    req_block = ""
    if not use_system_prompt and requirements_content and requirements_content.strip():
        req_block = (
            "Feature Requirements (must be covered):\n"
            "---\n"
            f"{requirements_content}\n"
            "---\n\n"
        )

    if template_override:
        return template_override.format(
            round_number=round_number,
            max_suggestions=max_suggestions,
            applied_ids=applied_list,
            rejected_ids=rejected_list,
            document=document_without_appendix,
            reviewer_label=reviewer_label,
            scope=scope,
            context=context_block,
            requirements=req_block,
        )

    cols = " | ".join(REQUIRED_COLUMNS)
    sep = " | ".join(["----"] * len(REQUIRED_COLUMNS))

    # Adapt iteration context based on whether prior rounds have been triaged
    if applied_list != "(none)" or rejected_list != "(none)":
        iteration_context = f"""Prior review rounds have already been triaged:
- Applied (incorporated into the plan): {applied_list}
- Rejected (with rationale — do NOT re-propose): {rejected_list}

Study the rejected rationale in Appendix B to understand WHY ideas were dismissed.
Your job is to find what prior reviewers MISSED — go deeper, challenge assumptions, identify second-order risks, and surface gaps that only emerge after the obvious issues are resolved.
If you want to revisit a rejected idea, explicitly reference its rejected ID and argue why the original rationale no longer applies."""
    else:
        iteration_context = f"""This is the first review pass. No prior suggestions have been triaged yet.
- Applied IDs: {applied_list}
- Rejected IDs: {rejected_list}"""

    # Substantially addressed areas — two-tier priority guidance
    focus_line = f"- Focus on: {focus}."
    if substantially_addressed_areas:
        covered = set(substantially_addressed_areas.keys())
        uncovered = sorted(areas - covered)
        addressed_lines = []
        for area in sorted(covered):
            ids = substantially_addressed_areas[area]
            addressed_lines.append(f"  - **{area}**: {len(ids)} suggestions applied ({', '.join(ids)})")
        total_applied = sum(len(v) for v in substantially_addressed_areas.values())

        if uncovered:
            # Tier 1
            iteration_context += (
                f"\n\n**Priority areas NOT yet substantially addressed — start your analysis here:**\n"
            )
            if area_coverage:
                for area in uncovered:
                    info = area_coverage.get(area, {})
                    count = info.get("accepted_count", 0)
                    gap = info.get("gap", 0)
                    ids = info.get("accepted_ids", [])
                    if count > 0:
                        ids_str = ", ".join(ids)
                        iteration_context += (
                            f"  - **{area}**: {count} accepted ({ids_str}) — "
                            f"needs {gap} more to reach threshold\n"
                        )
                    else:
                        iteration_context += (
                            f"  - **{area}**: no accepted suggestions yet — "
                            f"needs {gap} to reach threshold\n"
                        )
            else:
                iteration_context += f"  {', '.join(f'**{a}**' for a in uncovered)}\n"
            iteration_context += (
                f"Exhaust these areas first. Allocate at least {max(1, max_suggestions - 1)} of your "
                f"{max_suggestions} suggestion slots to these priority areas before considering addressed areas."
            )
            # Tier 2
            iteration_context += (
                f"\n\nAreas already substantially addressed — only propose if you find a genuine gap "
                f"the {total_applied} accepted suggestions missed:\n"
            )
            iteration_context += "\n".join(addressed_lines)
            focus_line = (
                f"- Prioritize: {', '.join(uncovered)}. "
                f"Only revisit {', '.join(sorted(covered))} if you find a gap the "
                f"{total_applied} accepted suggestions missed."
            )
        else:
            # All areas covered
            iteration_context += (
                f"\n\nAll {len(areas)} review areas are substantially addressed "
                f"({total_applied} suggestions accepted). Your job is to find genuine gaps "
                f"the prior reviewers missed — second-order risks, unstated assumptions, "
                f"or interactions between accepted suggestions that create new issues.\n"
            )
            iteration_context += "\n".join(addressed_lines)
            iteration_context += (
                f"\n\nDo NOT rehash areas already well-covered. Instead, look for:\n"
                f"  1. Gaps *between* areas (e.g., an ops process that contradicts an architecture decision)\n"
                f"  2. Assumptions that were never validated\n"
                f"  3. Second-order effects of accepted suggestions\n"
                f"  4. Edge cases or failure modes not yet addressed"
            )
            focus_line = (
                f"- All areas have substantial coverage. Focus exclusively on genuine gaps, "
                f"cross-cutting concerns, and second-order risks the prior {total_applied} "
                f"accepted suggestions may have introduced or missed."
            )

    # Context-aware instructions
    context_instruction = ""
    if context_block:
        context_instruction = (
            "- If reference material is provided, ground your suggestions in project-specific patterns "
            "and cite relevant lessons by name when applicable.\n"
        )

    dual_doc_instruction = ""
    req_instruction = ""
    if req_block:
        req_instruction = "- Ensure the plan adequately addresses each requirement provided above. Identify any missing requirements or under-addressed constraints.\n"

    if has_feature_requirements:
        dual_doc_instruction = f"""
You MUST include a Requirements Coverage section that explicitly maps plan steps to the provided feature requirements.
Also, if you find issues with the REQUIREMENTS themselves (ambiguity, conflict, missing details), you must report them in a separate table.

Dual-Document Output Format:
1. Normal plan suggestions in the main table (as below).
2. A second table headed "#### Feature Requirements Suggestions" for issues with the requirements doc.
   Use IDs R{round_number}-F1..R{round_number}-F{max_suggestions} for these.
3. A "#### Requirements Coverage" section with a table mapping Feature Doc Section -> Plan Step(s) | Coverage (Full/Partial/None) | Gaps.
"""

    document_section = ""
    if not use_system_prompt:
        document_section = (
            f"\nDocument (excluding the review appendix):\n"
            f"---\n"
            f"{document_without_appendix}\n"
            f"---"
        )

    return format_prompt(
        "architectural_review",
        "review",
        role=role,
        round_number=round_number,
        iteration_context=iteration_context,
        req_block=req_block,
        context_block=context_block,
        max_suggestions=max_suggestions,
        req_instruction=req_instruction,
        focus_line=focus_line,
        context_instruction=context_instruction,
        dual_doc_instruction=dual_doc_instruction,
        reviewer_label=reviewer_label,
        now_utc=_now_utc(),
        scope=scope,
        cols=cols,
        sep=sep,
        areas_list=", ".join(sorted(areas)),
        document_section=document_section,
    )


# ---------------------------------------------------------------------------
# _build_triage_prompt  (triage template — YAML-backed)
# ---------------------------------------------------------------------------

def _build_triage_prompt(
    document_without_appendix: str,
    applied_ids: List[str],
    rejected_ids: List[str],
    untriaged_block: str,
    endorsement_counts: Dict[str, int],
    allowed_areas: Optional[Set[str]] = None,
    persona: Optional[str] = None,
    has_feature_suggestions: bool = False,
    use_system_prompt: bool = False,
) -> str:
    """Build the triage prompt asking agent to classify each untriaged suggestion.

    When *use_system_prompt* is True the document body is omitted (it is
    expected to be in the system prompt via ``_build_shared_system_prompt``).
    """
    applied_list = ", ".join(applied_ids[:50]) if applied_ids else "(none)"
    rejected_list = ", ".join(rejected_ids[:50]) if rejected_ids else "(none)"
    areas = allowed_areas or ALLOWED_AREAS
    role = persona or "expert enterprise architect"

    endorsement_info = ""
    if endorsement_counts:
        parts = [f"  - {sid}: {count} endorsement(s)" for sid, count in sorted(endorsement_counts.items())]
        endorsement_info = "Endorsement counts (suggestions endorsed by multiple reviewers should be weighted higher):\n" + "\n".join(parts) + "\n\n"

    id_instruction = ""
    if has_feature_suggestions:
        id_instruction = (
            "Note: R*-S* IDs are plan suggestions; R*-F* IDs are feature suggestions (issues with the requirements doc). "
            "You must triage both types.\n"
        )

    doc_section = ""
    if not use_system_prompt:
        doc_section = (
            f"Document being reviewed (for context):\n"
            f"---\n"
            f"{document_without_appendix}\n"
            f"---\n\n"
        )

    return format_prompt(
        "architectural_review",
        "triage",
        role=role,
        applied_list=applied_list,
        rejected_list=rejected_list,
        endorsement_info=endorsement_info,
        untriaged_block=untriaged_block,
        doc_section=doc_section,
        id_instruction=id_instruction,
        areas_list=", ".join(sorted(areas)),
    )


# ---------------------------------------------------------------------------
# _build_shared_system_prompt  (Python-only — conditional assembly)
# ---------------------------------------------------------------------------

def _build_shared_system_prompt(
    document_without_appendix: str,
    context_content: str = "",
    requirements_content: str = "",
) -> str:
    """Build a shared system prompt containing the document and reference material.

    Used with Anthropic prompt caching: the system prompt is cached across
    sequential LLM calls (review rounds, triage, apply) for ~90% input cost
    reduction on the document body.
    """
    parts = [
        "Document under review (excluding the review appendix):",
        "---",
        document_without_appendix,
        "---",
    ]

    if requirements_content and requirements_content.strip():
        parts.append("")
        parts.append("Feature Requirements (must be covered):")
        parts.append("---")
        parts.append(requirements_content)
        parts.append("---")

    if context_content and context_content.strip():
        parts.append("")
        parts.append(
            "Reference material (institutional knowledge, lessons learned, prior decisions "
            "— use these to ground your review in project-specific patterns and known issues):"
        )
        parts.append("---")
        parts.append(context_content)
        parts.append("---")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# _build_apply_prompt  (apply template — YAML-backed)
# ---------------------------------------------------------------------------

def _build_apply_prompt(
    accepted_suggestions: List[Dict[str, Any]],
    persona: Optional[str] = None,
    use_system_prompt: bool = False,
    document_without_appendix: str = "",
) -> str:
    """Build the prompt for the apply-suggestions LLM call.

    When *use_system_prompt* is True the document body is omitted from
    the prompt (it is already in the system prompt).
    """
    role = persona or "expert enterprise architect"

    # Build suggestion table
    rows = [
        "| ID | Suggestion | Proposed Placement | Rationale |",
        "| ---- | ---- | ---- | ---- |",
    ]
    for s in accepted_suggestions:
        rows.append(
            f"| {s.get('id', '?')} | {s.get('suggestion', '')} "
            f"| {s.get('placement', '')} | {s.get('triage_rationale', s.get('rationale', ''))} |"
        )
    suggestion_table = "\n".join(rows)

    doc_section = ""
    if not use_system_prompt:
        doc_section = (
            f"Document body:\n"
            f"---\n"
            f"{document_without_appendix}\n"
            f"---\n\n"
        )

    return format_prompt(
        "architectural_review",
        "apply",
        role=role,
        doc_section=doc_section,
        suggestion_table=suggestion_table,
    )


# ---------------------------------------------------------------------------
# _build_untriaged_block  (Python-only — table formatting)
# ---------------------------------------------------------------------------

def _build_untriaged_block(suggestions: List[Dict[str, Any]]) -> str:
    """Format untriaged suggestions as a readable block for the triage prompt."""
    if not suggestions:
        return "(none)"

    lines = ["| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |",
             "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |"]
    for s in suggestions:
        lines.append(
            f"| {s['id']} | {s['area']} | {s['severity']} | {s['suggestion']} "
            f"| {s['rationale']} | {s['placement']} | {s['validation']} |"
        )
    return "\n".join(lines)
