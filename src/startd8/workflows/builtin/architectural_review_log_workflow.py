"""
ArchitecturalReviewLogWorkflow - High-quality sequential architectural review with append-only review rounds.

This workflow is a strategic variation of doc-review-log:
- Defaults to 1+ flagship models (high quality) when agents are not explicitly provided
- Runs models sequentially (one after another)
- Appends suggestions to the SAME document (Appendix C) in an append-only fashion
- Uses Applied/Rejected appendices as memory so later reviewers avoid re-suggesting rejected/applied items
- Enforces a strict suggestion-table schema to keep feedback actionable and triage-ready
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    WorkflowMetadata,
    WorkflowInput,
    WorkflowResult,
    WorkflowMetrics,
    StepResult,
    AgentCount,
    ValidationResult,
)
from ...agents import BaseAgent
from ...exceptions import GeminiSafetyFilterError
from ...logging_config import get_logger
from ...model_catalog import Models, list_models_by_tier
from ...utils.agent_resolution import resolve_agents
from ...utils.file_operations import FileLock, atomic_write, atomic_write_json
from ...utils.token_usage import token_usage_input, token_usage_output, token_usage_cost

_logger = get_logger(__name__)

# Relaxed safety settings for technical document review.
# Architectural plans mention "risks", "vulnerabilities", "attack surfaces", etc.
# which can trip Gemini's DANGEROUS_CONTENT filter on benign content.
RELAXED_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


APPENDIX_HEADING = "## Appendix: Iterative Review Log (Applied / Rejected Suggestions)"

# This matches the appendix scaffold we already introduced in target docs.
APPENDIX_TEMPLATE = """---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
"""


ALLOWED_AREAS = {
    "architecture",
    "interfaces",
    "data",
    "risks",
    "validation",
    "ops",
    "security",
}

REVIEW_PROFILES = {
    "architecture": {
        "areas": ALLOWED_AREAS,
        "persona": "expert enterprise architect",
        "focus": "architecture clarity, execution safety, risk management, validation completeness, and operational readiness",
    },
    "requirements": {
        "areas": {
            "ambiguity", "completeness", "consistency", "testability", "traceability", "feasibility"
        },
        "persona": "expert requirements analyst",
        "focus": "clarity, completeness, testability, consistency, and feasibility",
    },
    "design": {
        "areas": {
            "architecture", "clarity", "completeness", "maintainability", "scalability", "security", "testability"
        },
        "persona": "expert software designer",
        "focus": "clarity, completeness, maintainability, scalability, and testability",
    }
}

ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}

REQUIRED_COLUMNS = [
    "ID",
    "Area",
    "Severity",
    "Suggestion",
    "Rationale",
    "Proposed Placement",
    "Validation Approach",
]

def _is_openai_agent(agent: BaseAgent) -> bool:
    mod = getattr(agent.__class__, "__module__", "") or ""
    return ".agents.openai" in mod or mod.endswith("agents.openai")


def _is_gemini_agent(agent: BaseAgent) -> bool:
    mod = getattr(agent.__class__, "__module__", "") or ""
    return ".agents.gemini" in mod or mod.endswith("agents.gemini")


def _is_anthropic_agent(agent: BaseAgent) -> bool:
    mod = getattr(agent.__class__, "__module__", "") or ""
    return ".agents.claude" in mod or mod.endswith("agents.claude")


def _looks_like_model_not_found_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("model" in msg and ("not found" in msg or "not available" in msg or "does not exist" in msg))


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _strip_code_fences(text: str) -> str:
    """Strip markdown code-block fences (```markdown ... ```) from LLM output."""
    stripped = text.strip()
    # Match ```markdown, ```md, or bare ``` at start
    if re.match(r"^```(?:markdown|md)?\s*\n", stripped, re.IGNORECASE):
        stripped = re.sub(r"^```(?:markdown|md)?\s*\n", "", stripped, count=1, flags=re.IGNORECASE)
        # Remove trailing ``` (possibly with trailing whitespace)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    return stripped


def _strip_json_fences(text: str) -> str:
    """Strip ```json ``` fences from LLM output."""
    stripped = text.strip()
    if re.match(r"^```(?:json)?\s*\n", stripped, re.IGNORECASE):
        stripped = re.sub(r"^```(?:json)?\s*\n", "", stripped, count=1, flags=re.IGNORECASE)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    return stripped


def _split_cells(row: str) -> List[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _normalize_header(cell: str) -> str:
    """Strip markdown bold/italic markers (e.g. **Area**, _Area_) for header comparison."""
    return re.sub(r'^[*_]+|[*_]+$', '', cell.strip()).strip()


def _ensure_appendix_exists(doc: str) -> str:
    if APPENDIX_HEADING in doc:
        return doc
    return doc.rstrip() + "\n\n" + APPENDIX_TEMPLATE


def _strip_appendix_for_prompt(doc: str) -> str:
    idx = doc.find(APPENDIX_HEADING)
    if idx == -1:
        return doc
    return doc[:idx].rstrip() + "\n"


def _max_review_round(doc: str) -> int:
    rounds = [int(x) for x in re.findall(r"^####\s+Review Round R(\d+)\s*$", doc, re.MULTILINE)]
    return max(rounds) if rounds else 0


def _extract_table_ids(doc: str, section_heading: str) -> List[str]:
    m = re.search(rf"^{re.escape(section_heading)}\s*$", doc, re.MULTILINE)
    if not m:
        return []
    tail = doc[m.end() :]
    lines = tail.splitlines()

    table_lines: List[str] = []
    in_table = False
    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_lines.append(line)
            continue
        if in_table:
            break

    if len(table_lines) < 3:
        return []

    ids: List[str] = []
    for row in table_lines[2:]:
        cells = _split_cells(row)
        if not cells:
            continue
        first = cells[0]
        if not first or first.startswith("("):
            continue
        ids.append(first)
    return ids


def _extract_untriaged_suggestions(
    doc: str,
    applied_ids: List[str],
    rejected_ids: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Extract untriaged suggestions from Appendix C review round blocks.

    Returns:
        (suggestions, endorsement_counts) where suggestions is a list of dicts
        with keys: id, area, severity, suggestion, rationale, placement, validation, round.
        endorsement_counts maps suggestion ID -> number of endorsements.
    """
    triaged = set(applied_ids) | set(rejected_ids)
    suggestions: List[Dict[str, Any]] = []
    endorsement_counts: Dict[str, int] = {}

    # Find Appendix C section
    appendix_c_match = re.search(
        r"^### Appendix C: Incoming Suggestions.*$",
        doc,
        re.MULTILINE,
    )
    if not appendix_c_match:
        return suggestions, endorsement_counts

    appendix_c_text = doc[appendix_c_match.end():]

    # Split into review round blocks
    round_blocks = re.split(r"(?=^#### Review Round R\d+)", appendix_c_text, flags=re.MULTILINE)

    for block in round_blocks:
        round_match = re.match(r"^#### Review Round R(\d+)", block)
        if not round_match:
            continue
        round_num = int(round_match.group(1))

        # Extract table rows
        lines = block.splitlines()
        in_table = False
        for line in lines:
            stripped = line.strip()
            if not in_table and stripped.startswith("| ID"):
                in_table = True
                continue
            
            if in_table:
                if stripped.startswith("|") and stripped.startswith("| -"):
                    # Separator row
                    continue
                
                if stripped.startswith("|"):
                    cells = _split_cells(stripped)
                    if len(cells) >= 7:
                        sid = cells[0]
                        if sid in triaged or sid.startswith("("):
                            continue
                        suggestions.append({
                            "id": sid,
                            "area": cells[1],
                            "severity": cells[2],
                            "suggestion": cells[3],
                            "rationale": cells[4],
                            "placement": cells[5],
                            "validation": cells[6],
                            "round": round_num,
                        })
                else:
                    in_table = False

        # Parse endorsements
        endorsement_match = re.search(
            r"\*\*Endorsements\*\*.*?(?=\n####|\n###|\Z)",
            block,
            re.DOTALL,
        )
        if endorsement_match:
            endorsement_text = endorsement_match.group(0)
            for eid in re.findall(r"(R\d+-[SF]\d+)", endorsement_text):
                endorsement_counts[eid] = endorsement_counts.get(eid, 0) + 1

    return suggestions, endorsement_counts


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

    return f"""You are an {role} performing triage on architectural review suggestions.

Your task: Evaluate every untriaged suggestion below and decide whether to ACCEPT or REJECT it.

Context:
- Previously applied suggestions: {applied_list}
- Previously rejected suggestions: {rejected_list}

{endorsement_info}Untriaged suggestions to evaluate:
{untriaged_block}

{doc_section}{id_instruction}
You MUST output a JSON array. Each element must have these fields:
- "id": the suggestion ID (e.g. "R1-S1")
- "decision": exactly "ACCEPT" or "REJECT"
- "summary": a one-sentence summary of the suggestion
- "rationale": why you are accepting or rejecting it
- "area": one of: {', '.join(sorted(areas))}

Output ONLY the JSON array, no other text. Example:
[
  {{"id": "R1-S1", "decision": "ACCEPT", "summary": "Add circuit breakers", "rationale": "Critical for resilience", "area": "architecture"}},
  {{"id": "R1-S2", "decision": "REJECT", "summary": "Use GraphQL", "rationale": "Not aligned with REST strategy", "area": "interfaces"}}
]
"""


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


def _validate_triage_output(
    raw_text: str,
    untriaged_ids: List[str],
    allowed_areas: Optional[Set[str]] = None,
) -> Tuple[bool, str, List[Dict[str, Any]], List[str]]:
    """
    Parse and validate triage JSON output.
    
    Returns:
        (ok, message, parsed_decisions, missing_ids)
        Partial results are accepted — missing IDs stay untriaged.
        Now more lenient: warns instead of failing for minor issues.
    """
    cleaned = _strip_json_fences(raw_text.strip())
    areas = allowed_areas or ALLOWED_AREAS

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}", [], list(untriaged_ids)

    if not isinstance(data, list):
        return False, "Expected a JSON array", [], list(untriaged_ids)

    untriaged_set = set(untriaged_ids)
    seen_ids: set = set()
    decisions: List[Dict[str, Any]] = []
    errors: List[str] = []

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            errors.append(f"Entry {i}: not an object")
            continue

        # Required fields
        for field in ("id", "decision", "summary", "rationale", "area"):
            if field not in entry:
                errors.append(f"Entry {i}: missing field '{field}'")
                break
        else:
            sid = entry["id"]
            raw_decision = entry["decision"]
            if not isinstance(raw_decision, str):
                errors.append(f"Entry {i}: 'decision' must be a string, got {type(raw_decision).__name__}")
                continue
            decision = raw_decision.upper()  # Leniency: case-insensitive decision
            area = entry["area"].strip().lower()

            if sid not in untriaged_set:
                errors.append(f"Entry {i}: unknown ID '{sid}'")
                continue
            
            if decision not in ("ACCEPT", "REJECT"):
                # Leniency check for common typos
                if "ACCEPT" in decision:
                    decision = "ACCEPT"
                elif "REJECT" in decision:
                    decision = "REJECT"
                else:
                    errors.append(f"Entry {i}: invalid decision '{decision}' (must be ACCEPT or REJECT)")
                    continue
            
            if area not in areas:
                errors.append(f"Entry {i}: invalid area '{area}' (allowed: {sorted(areas)})")
                continue

            seen_ids.add(sid)
            decisions.append({
                "id": sid,
                "decision": decision,
                "summary": entry["summary"],
                "rationale": entry["rationale"],
                "area": area,
            })

    missing_ids = [sid for sid in untriaged_ids if sid not in seen_ids]

    if not decisions and errors:
        return False, "; ".join(errors), [], missing_ids

    # Partial success: we have some valid decisions even if some entries had errors
    msg = "ok" if not errors else f"Partial: {'; '.join(errors)}"
    return True, msg, decisions, missing_ids


def _apply_triage_decisions(
    doc: str,
    decisions: List[Dict[str, Any]],
    reviewer_sources: Dict[str, str],
) -> str:
    """
    Apply triage decisions by inserting rows into Appendix A (ACCEPT) and Appendix B (REJECT).

    reviewer_sources maps suggestion ID -> reviewer label string.
    """
    date_str = _now_utc()

    accepted = [d for d in decisions if d["decision"] == "ACCEPT"]
    rejected = [d for d in decisions if d["decision"] == "REJECT"]

    if accepted:
        doc = _insert_appendix_rows(
            doc,
            "### Appendix A: Applied Suggestions",
            [(d["id"], d["summary"], reviewer_sources.get(d["id"], ""), d["rationale"], date_str) for d in accepted],
        )

    if rejected:
        doc = _insert_appendix_rows(
            doc,
            "### Appendix B: Rejected Suggestions (with Rationale)",
            [(d["id"], d["summary"], reviewer_sources.get(d["id"], ""), d["rationale"], date_str) for d in rejected],
        )

    return doc


def _insert_appendix_rows(
    doc: str,
    section_heading: str,
    rows: List[Tuple[str, str, str, str, str]],
) -> str:
    """
    Insert rows into an appendix table. Each row is (id, summary, source, notes, date).
    Removes the '(none yet)' placeholder if present.
    """
    m = re.search(rf"^{re.escape(section_heading)}\s*$", doc, re.MULTILINE)
    if not m:
        return doc

    tail = doc[m.end():]
    lines = tail.splitlines(keepends=True)

    # Find the table end (last | line before a non-| line)
    table_end_idx = -1
    in_table = False
    for i, line in enumerate(lines):
        if line.strip().startswith("|"):
            in_table = True
            table_end_idx = i
        elif in_table:
            break

    if table_end_idx == -1:
        return doc

    # Check for (none yet) placeholder in the last table line
    last_table_line = lines[table_end_idx]
    if "(none yet)" in last_table_line:
        # Replace the placeholder line with actual rows
        new_rows = "".join(
            f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |\n"
            for r in rows
        )
        lines[table_end_idx] = new_rows
    else:
        # Append after last table line
        new_rows = "".join(
            f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |\n"
            for r in rows
        )
        lines.insert(table_end_idx + 1, new_rows)

    return doc[: m.end()] + "".join(lines)


def _compute_substantially_addressed(
    applied_with_area: List[Tuple[str, str]],
    threshold: int,
) -> Dict[str, List[str]]:
    """
    Group accepted IDs by area and return areas with >= threshold accepted suggestions.

    applied_with_area: list of (suggestion_id, area) tuples.
    Returns: {area: [id1, id2, ...]} for areas meeting the threshold.
    """
    area_ids: Dict[str, List[str]] = {}
    for sid, area in applied_with_area:
        area_key = area.strip().lower()
        area_ids.setdefault(area_key, []).append(sid)

    return {area: ids for area, ids in area_ids.items() if len(ids) >= threshold}


def _compute_substantially_addressed_from_doc(
    doc: str,
    threshold: int,
) -> Dict[str, List[str]]:
    """
    Extract applied suggestions from Appendix A and compute substantially addressed areas.
    Parses the Area from Appendix C for each applied ID.
    """
    applied_ids = _extract_table_ids(doc, "### Appendix A: Applied Suggestions")
    if not applied_ids:
        return {}

    # Build ID → area mapping from Appendix C
    id_to_area: Dict[str, str] = {}
    appendix_c_match = re.search(
        r"^### Appendix C: Incoming Suggestions.*$",
        doc,
        re.MULTILINE,
    )
    if appendix_c_match:
        appendix_c_text = doc[appendix_c_match.end():]
        for line in appendix_c_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and not stripped.startswith("| -") and "ID" not in stripped:
                cells = _split_cells(stripped)
                if len(cells) >= 2 and re.match(r"R\d+-S\d+", cells[0]):
                    id_to_area[cells[0]] = cells[1].strip().lower()

    applied_with_area = [(sid, id_to_area.get(sid, "unknown")) for sid in applied_ids]
    return _compute_substantially_addressed(applied_with_area, threshold)


def _compute_area_coverage(
    doc: str,
    threshold: int,
    allowed_areas: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Compute coverage status for every area in allowed_areas.

    Returns: {area: {"accepted_count": N, "accepted_ids": [...], "addressed": bool, "gap": M}}
    where gap = max(0, threshold - accepted_count).
    """
    applied_ids = _extract_table_ids(doc, "### Appendix A: Applied Suggestions")
    areas = allowed_areas or ALLOWED_AREAS

    # Build ID → area mapping from Appendix C
    id_to_area: Dict[str, str] = {}
    appendix_c_match = re.search(
        r"^### Appendix C: Incoming Suggestions.*$",
        doc,
        re.MULTILINE,
    )
    if appendix_c_match:
        appendix_c_text = doc[appendix_c_match.end():]
        for line in appendix_c_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and not stripped.startswith("| -") and "ID" not in stripped:
                cells = _split_cells(stripped)
                if len(cells) >= 2 and re.match(r"R\d+-S\d+", cells[0]):
                    id_to_area[cells[0]] = cells[1].strip().lower()

    # Group applied IDs by area
    area_ids: Dict[str, List[str]] = {area: [] for area in areas}
    for sid in applied_ids:
        area = id_to_area.get(sid, "unknown")
        if area in area_ids:
            area_ids[area].append(sid)

    return {
        area: {
            "accepted_count": len(ids),
            "accepted_ids": ids,
            "addressed": len(ids) >= threshold,
            "gap": max(0, threshold - len(ids)),
        }
        for area, ids in area_ids.items()
    }


def _insert_areas_needing_review_section(
    doc: str,
    area_coverage: Dict[str, Dict[str, Any]],
    threshold: int,
) -> str:
    """
    Insert or update '### Areas Needing Further Review' section
    after 'Areas Substantially Addressed' and before Appendix A.
    """
    section_heading = "### Areas Needing Further Review"

    underserved = {
        area: info for area, info in area_coverage.items()
        if not info["addressed"]
    }

    # Build section content
    lines_out = [f"{section_heading}\n\n"]
    if underserved:
        for area in sorted(underserved.keys()):
            info = underserved[area]
            count = info["accepted_count"]
            gap = info["gap"]
            if count > 0:
                ids_str = ", ".join(info["accepted_ids"])
                lines_out.append(
                    f"- **{area}**: {count} accepted ({ids_str}) — "
                    f"needs {gap} more to reach threshold of {threshold}\n"
                )
            else:
                lines_out.append(
                    f"- **{area}**: no accepted suggestions yet — "
                    f"needs {threshold} to reach threshold\n"
                )
    else:
        lines_out.append("All areas have reached the substantially addressed threshold.\n")
    lines_out.append("\n")
    section_text = "".join(lines_out)

    # Check if section already exists
    existing_match = re.search(
        rf"^{re.escape(section_heading)}\s*\n",
        doc,
        re.MULTILINE,
    )
    if existing_match:
        rest = doc[existing_match.start():]
        next_heading = re.search(r"^### (?!Areas Needing Further Review)", rest, re.MULTILINE)
        if next_heading:
            end_pos = existing_match.start() + next_heading.start()
        else:
            end_pos = len(doc)
        return doc[: existing_match.start()] + section_text + doc[end_pos:]

    # Insert after "Areas Substantially Addressed" if it exists, else before Appendix A
    sa_match = re.search(r"^### Areas Substantially Addressed\s*\n", doc, re.MULTILINE)
    if sa_match:
        # Find the end of the SA section (next ### heading)
        rest = doc[sa_match.start():]
        next_heading = re.search(r"^### (?!Areas Substantially Addressed)", rest, re.MULTILINE)
        if next_heading:
            insert_pos = sa_match.start() + next_heading.start()
            return doc[:insert_pos] + section_text + doc[insert_pos:]

    appendix_a_match = re.search(r"^### Appendix A:", doc, re.MULTILINE)
    if appendix_a_match:
        return doc[: appendix_a_match.start()] + section_text + doc[appendix_a_match.start():]

    return doc


def _insert_substantially_addressed_section(
    doc: str,
    addressed_areas: Dict[str, List[str]],
) -> str:
    """
    Insert or update '### Areas Substantially Addressed' section
    between Reviewer Instructions and Appendix A.
    """
    section_heading = "### Areas Substantially Addressed"

    # Build section content
    lines_out = [f"{section_heading}\n\n"]
    for area in sorted(addressed_areas.keys()):
        ids = addressed_areas[area]
        lines_out.append(f"- **{area}**: {len(ids)} suggestions applied ({', '.join(ids)})\n")
    lines_out.append("\n")
    section_text = "".join(lines_out)

    # Check if section already exists
    existing_match = re.search(
        rf"^{re.escape(section_heading)}\s*\n",
        doc,
        re.MULTILINE,
    )
    if existing_match:
        # Find extent: from heading to next ### heading
        rest = doc[existing_match.start():]
        next_heading = re.search(r"^### (?!Areas Substantially Addressed)", rest, re.MULTILINE)
        if next_heading:
            end_pos = existing_match.start() + next_heading.start()
        else:
            end_pos = len(doc)
        return doc[: existing_match.start()] + section_text + doc[end_pos:]

    # Insert before Appendix A
    appendix_a_match = re.search(r"^### Appendix A:", doc, re.MULTILINE)
    if appendix_a_match:
        return doc[: appendix_a_match.start()] + section_text + doc[appendix_a_match.start():]

    return doc


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


def _extract_reviewer_sources(doc: str) -> Dict[str, str]:
    """
    Extract a mapping of suggestion ID -> reviewer label from Appendix C round blocks.
    """
    sources: Dict[str, str] = {}
    appendix_c_match = re.search(
        r"^### Appendix C: Incoming Suggestions.*$",
        doc,
        re.MULTILINE,
    )
    if not appendix_c_match:
        return sources

    appendix_c_text = doc[appendix_c_match.end():]
    round_blocks = re.split(r"(?=^#### Review Round R\d+)", appendix_c_text, flags=re.MULTILINE)

    for block in round_blocks:
        round_match = re.match(r"^#### Review Round R(\d+)", block)
        if not round_match:
            continue

        # Extract reviewer label
        reviewer_match = re.search(r"\*\*Reviewer\*\*:\s*(.+)", block)
        reviewer_label = reviewer_match.group(1).strip() if reviewer_match else "Unknown"

        # Extract suggestion IDs
        for sid in re.findall(r"(R\d+-S\d+)", block):
            # Only set if we haven't seen it (first occurrence = definition)
            if sid not in sources:
                sources[sid] = reviewer_label

    return sources


# ---------------------------------------------------------------------------
# Apply-suggestions helpers
# ---------------------------------------------------------------------------

def _extract_accepted_suggestions_for_apply(
    triage_decisions: List[Dict[str, Any]],
    untriaged_suggestions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge ACCEPT triage decisions with full suggestion data from Appendix C.

    Returns enriched dicts containing all Appendix C fields (placement,
    validation, etc.) plus the triage ``rationale``.
    """
    accepted_ids = {
        d["id"] for d in triage_decisions if d.get("decision") == "ACCEPT"
    }
    if not accepted_ids:
        return []

    suggestion_map = {s["id"]: s for s in untriaged_suggestions}
    result: List[Dict[str, Any]] = []
    for decision in triage_decisions:
        sid = decision["id"]
        if sid not in accepted_ids:
            continue
        base = dict(suggestion_map.get(sid, {"id": sid}))
        base["triage_rationale"] = decision.get("rationale", "")
        result.append(base)
    return result


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

    return f"""You are an {role}. Your task is to integrate the following accepted review suggestions into the document body.

{doc_section}Accepted suggestions to integrate:
{suggestion_table}

Instructions:
1. Produce the COMPLETE updated document body with the suggestions integrated at or near their Proposed Placement locations.
2. Maintain all existing headings, numbering, and structure.
3. Do NOT include any appendix sections (Appendix A, B, or C). Output only the document body.
4. Do NOT add commentary or meta-text — output only the updated document.
5. Integrate each suggestion naturally into the relevant section rather than appending it.
6. If a suggestion's Proposed Placement is ambiguous, use your best judgment for the most logical location.

Output the complete updated document body now:
"""


def _validate_apply_output(
    output: str,
    original_body: str,
    accepted_suggestions: List[Dict[str, Any]],
) -> Tuple[bool, str, List[str]]:
    """Validate the LLM's apply output.

    Returns ``(ok, message, warning_ids)`` where *warning_ids* lists suggestion
    IDs whose key terms could not be found in the output (non-blocking).
    """
    if not output or not output.strip():
        return False, "Empty output", []

    # Length check — reject if < 50% of original (accidental truncation)
    if len(output.strip()) < len(original_body.strip()) * 0.5:
        return (
            False,
            f"Output too short ({len(output.strip())} chars vs original {len(original_body.strip())} chars)",
            [],
        )

    # Heading preservation — all ##/### headings from original must be present
    # Normalize for comparison: strip trailing whitespace and casefold so LLMs
    # that change "## Architecture Overview" to "## Architecture overview" pass.
    original_headings = re.findall(r"^(#{2,3}\s+.+)$", original_body, re.MULTILINE)
    output_headings_normalized = {
        h.strip().casefold() for h in re.findall(r"^(#{2,3}\s+.+)$", output, re.MULTILINE)
    }
    missing_headings = [
        h for h in original_headings if h.strip().casefold() not in output_headings_normalized
    ]
    if missing_headings:
        return (
            False,
            f"Missing {len(missing_headings)} heading(s): {missing_headings[:3]}",
            [],
        )

    # No appendix leakage
    for appendix_heading in ("### Appendix A", "### Appendix B", "### Appendix C"):
        if appendix_heading in output:
            return False, f"Output contains {appendix_heading} (appendix leakage)", []

    # Integration warnings (non-blocking) — check if key terms appear
    warning_ids: List[str] = []
    for s in accepted_suggestions:
        suggestion_text = s.get("suggestion", "")
        # Extract first significant word (>4 chars) as a key term
        words = [w for w in suggestion_text.split() if len(w) > 4]
        if words and not any(w.lower() in output.lower() for w in words[:3]):
            warning_ids.append(s.get("id", "?"))

    return True, "ok", warning_ids


def _apply_suggestions_to_doc(
    doc_text: str,
    accepted_suggestions: List[Dict[str, Any]],
    agent: BaseAgent,
    persona: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Tuple[str, bool, str, List[str], int, int, int, float]:
    """Orchestrate the apply-suggestions step.

    Returns ``(updated_doc, ok, message, warning_ids, time_ms,
    input_tokens, output_tokens, cost)``.
    """
    original_body = _strip_appendix_for_prompt(doc_text)
    appendix_idx = doc_text.find(APPENDIX_HEADING)
    appendix_portion = doc_text[appendix_idx:] if appendix_idx != -1 else ""

    use_sp = system_prompt is not None
    prompt = _build_apply_prompt(
        accepted_suggestions=accepted_suggestions,
        persona=persona,
        use_system_prompt=use_sp,
        document_without_appendix=original_body,
    )

    generate_kwargs: Dict[str, Any] = {}
    if system_prompt is not None:
        generate_kwargs["system_prompt"] = system_prompt

    response_text, time_ms, token_usage = agent.generate(prompt, **generate_kwargs)
    input_tokens = token_usage_input(token_usage) if token_usage else 0
    output_tokens = token_usage_output(token_usage) if token_usage else 0
    cost = token_usage_cost(token_usage) if token_usage else 0.0

    # Strip code fences
    response_text = _strip_code_fences(response_text)

    ok, message, warning_ids = _validate_apply_output(
        response_text, original_body, accepted_suggestions,
    )

    if ok:
        updated_doc = response_text.rstrip() + "\n\n" + appendix_portion
        return updated_doc, True, message, warning_ids, time_ms, input_tokens, output_tokens, cost
    else:
        return doc_text, False, message, warning_ids, time_ms, input_tokens, output_tokens, cost


def _select_default_agents(
    quality_tier: str,
    reviewer_count: int,
    providers: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Select default models by tier from the model catalog.

    Returns a list of agent specs in provider:model format.
    """
    tier = (quality_tier or "flagship").strip().lower()

    # For strategic architectural review, default to Opus + Gemini Pro.
    # OpenAI o3 removed from defaults due to org TPM limits vs large prompts.
    # Users can add other models (e.g. mistral:mistral-large-latest) via
    # the "agents" config or the "providers" allowlist.
    _KNOWN_TIERS = {"flagship", "balanced", "fast", "mini"}
    if tier not in _KNOWN_TIERS:
        _logger.warning(
            "Unknown quality_tier '%s' (expected one of %s); "
            "falling back to tier-registry lookup",
            tier, sorted(_KNOWN_TIERS),
        )

    preferred: List[str] = []
    if tier == "flagship":
        preferred = [
            Models.CLAUDE_OPUS_LATEST,
            Models.GEMINI_PRO_LATEST,
        ]

    # Apply provider allowlist to preferred first (preserving order)
    allowed: Optional[set[str]] = None
    if providers:
        allowed = {p.strip().lower() for p in providers if p and p.strip()}
        preferred = [m for m in preferred if m.split(":", 1)[0].lower() in allowed]

    if len(preferred) >= reviewer_count:
        return preferred[:reviewer_count]

    # Fill remaining slots from tier registry (stable, provider-prioritized)
    remainder = [m for m in list_models_by_tier(tier) if m not in preferred]
    if allowed is not None:
        remainder = [m for m in remainder if m.split(":", 1)[0].lower() in allowed]

    priority = {"anthropic": 0, "gemini": 1, "mistral": 2, "openai": 3}
    remainder.sort(key=lambda full: (priority.get(full.split(":", 1)[0].lower(), 99), full))

    return (preferred + remainder)[:reviewer_count]


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
        # ... (same as before)
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

    return f"""You are an {role} performing Review Round R{round_number} of an iterative architectural review.

This document undergoes multiple review passes. Each pass should be sharper than the last.

{iteration_context}

{req_block}{context_block}Your task:
- Propose up to {max_suggestions} high-leverage improvements not yet captured.
{req_instruction}{focus_line}
{context_instruction}- Do NOT rewrite the document. Do NOT modify Appendix A or Appendix B.
- You MUST output ONLY an appendable markdown snippet for Appendix C.
{dual_doc_instruction}
Required output format (append-only snippet):
- Start with:
  #### Review Round R{round_number}
- Then include:
  - **Reviewer**: {reviewer_label}
  - **Date**: {_now_utc()}
  - **Scope**: {scope}
- Then output a markdown table with these EXACT column headers (plain text, no bold/italic formatting in headers):
  | {cols} |
  | {sep} |
  Copy the header row above verbatim. Do NOT wrap column names in ** or _.
  Rows must use IDs R{round_number}-S1..R{round_number}-S{max_suggestions} (you may output fewer rows).
  Area must be one of: {', '.join(sorted(areas))}.
  Severity must be one of: critical, high, medium, low.
- After the table, if you agree with any untriaged suggestions from prior rounds (in Appendix C but NOT in Appendix A or B), add:
  **Endorsements** (prior untriaged suggestions this reviewer agrees with):
  - <ID>: <one-sentence reason you agree>
  This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage. Only endorse suggestions you genuinely believe should be implemented. Do NOT endorse your own suggestions.
{"" if use_system_prompt else f"""
Document (excluding the review appendix):
---
{document_without_appendix}
---"""}
"""


def _validate_snippet(
    snippet: str,
    round_number: int,
    max_suggestions: int,
    allowed_areas: Optional[Set[str]] = None,
) -> Tuple[bool, str, List[str]]:
    """
    Validate agent output is a safe, append-only review-round block with required table schema.
    Now more lenient: warns instead of failing for minor issues.
    """
    areas = allowed_areas or ALLOWED_AREAS

    if not snippet or not snippet.strip():
        return False, "Empty snippet", []

    if f"#### Review Round R{round_number}" not in snippet:
        return False, f"Missing required heading: '#### Review Round R{round_number}'", []

    # Disallow attempts to edit other appendices
    for forbidden in ("### Appendix A", "### Appendix B"):
        if forbidden in snippet:
            return False, f"Snippet appears to modify {forbidden}; only Appendix C additions are allowed", []

    lines = [ln.rstrip() for ln in snippet.strip().splitlines() if ln.strip()]
    ids: List[str] = []
    
    # Iterate looking for markdown tables
    # A table starts with a | line containing ID, followed by a | line starting with |-
    i = 0
    tables_found = 0
    
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("|") and "ID" in ln:
            # Possible table header
            if i + 1 >= len(lines):
                break
            sep = lines[i+1]
            if not sep.strip().startswith("|") or not "-" in sep:
                i += 1
                continue
            
            # Found table
            tables_found += 1
            raw_header = _split_cells(ln)
            # Normalize header cells: strip markdown bold/italic so **Area** matches Area
            header = [_normalize_header(h) for h in raw_header]
            # Leniency: Accept header if it has the required columns, even if extra or slightly different order
            missing_cols = [col for col in REQUIRED_COLUMNS if col not in header]
            if missing_cols:
                return False, f"Table header mismatch. Missing columns: {missing_cols}", []

            i += 2 # Skip header and sep

            # Parse rows
            while i < len(lines):
                row = lines[i]
                if not row.strip().startswith("|"):
                    break # End of table

                cells = _split_cells(row)
                # Leniency: Allow extra cells, just truncate to match header length
                if len(cells) < len(REQUIRED_COLUMNS):
                    _logger.debug("Skipping row with insufficient columns: %s", row)
                    i += 1
                    continue

                # Extract values by mapping column names to indices
                try:
                    sid = cells[header.index("ID")]
                    area = cells[header.index("Area")].strip().lower()
                    severity = cells[header.index("Severity")].strip().lower()
                except ValueError:
                    i += 1
                    continue

                ids.append(sid)
                
                # Validate ID: R{round}-[SF]{num}
                if not re.fullmatch(rf"R{round_number}-[SF]\d+", sid):
                    _logger.debug(
                        "Suggestion ID '%s' will be renumbered to R%d prefix.",
                        sid, round_number,
                    )
                    # IDs are auto-corrected by _fix_snippet_ids() before appending

                # Leniency: Check area/severity but don't fail, just log
                if area not in areas:
                    _logger.debug(
                        "Non-standard Area '%s' (expected: %s); accepted.",
                        area, sorted(areas),
                    )
                if severity not in ALLOWED_SEVERITIES:
                    _logger.warning(
                        "Invalid Severity '%s' (allowed: %s); proceeding with warning.",
                        severity, sorted(ALLOWED_SEVERITIES),
                    )
                
                i += 1
            continue
        i += 1

    if tables_found == 0:
        return False, "Missing required markdown table", []

    def sort_key(sid):
        m = re.match(r"R\d+-([SF])(\d+)$", sid)
        if m:
            return (m.group(1), int(m.group(2)))
        return (sid, 0)

    unique_ids = sorted(list(set(ids)), key=sort_key)

    if not unique_ids:
        # Leniency: It's technically okay to have no suggestions if the review found nothing
        return True, "No suggestions found (which is valid)", []
        
    # Check max suggestions for PLAN suggestions (S-prefix)
    s_ids = [x for x in unique_ids if "-S" in x]
    if len(s_ids) > max_suggestions:
         return False, f"Too many plan suggestions: {len(s_ids)} > {max_suggestions}", unique_ids

    return True, "ok", unique_ids


def _fix_snippet_ids(snippet: str, round_number: int) -> str:
    """Rewrite mis-numbered R{X}-S/F IDs to use the correct round_number.

    LLMs sometimes use a different round prefix (e.g. R3-S1 when asked for
    R1-S1) because they see prior rounds in the document. Only rewrites IDs
    in table rows (lines starting with ``|``) to avoid corrupting endorsement
    references like "I agree with R2-S3".
    """
    def _replace(m: re.Match) -> str:
        return f"R{round_number}-{m.group(1)}{m.group(2)}"

    out_lines: list[str] = []
    for line in snippet.splitlines(keepends=True):
        if line.lstrip().startswith("|"):
            out_lines.append(re.sub(r"R\d+-([SF])(\d+)", _replace, line))
        else:
            out_lines.append(line)
    return "".join(out_lines)


def _get_feature_doc_path(feature_requirements: Optional[List[str]]) -> Optional[Path]:
    if not feature_requirements:
        return None
    for path_str in feature_requirements:
        p = Path(path_str).expanduser()
        if p.exists() and p.is_file() and p.suffix.lower() == ".md":
            return p
        if p.exists() and p.is_dir():
            # Find first md file
            try:
                return sorted(p.glob("*.md"))[0]
            except IndexError:
                continue
    return None


def _extract_feature_snippet(
    response_text: str,
    round_number: int,
    reviewer_label: str,
    scope: str,
) -> str:
    """Extract the Feature Requirements Suggestions section if present."""
    marker = "#### Feature Requirements Suggestions"
    if marker not in response_text:
        return ""
    
    parts = response_text.split(marker)
    if len(parts) < 2:
        return ""
        
    content = parts[1].strip()
    # If there's another header, stop there
    next_header = re.search(r"^#+\s+", content, re.MULTILINE)
    if next_header:
        content = content[:next_header.start()].strip()
        
    if not content:
        return ""
        
    # Reconstruct a valid snippet
    return f"""#### Review Round R{round_number}

- **Reviewer**: {reviewer_label}
- **Date**: {_now_utc()}
- **Scope**: {scope} (Feature Requirements)

{marker}
{content}
"""


def _agent_label(agent: BaseAgent) -> str:
    """Format a consistent agent name label for StepResult and logging."""
    return f"{agent.name}:{getattr(agent, 'model', '')}"


def _make_error_step(
    step_name: str,
    agent: BaseAgent,
    error: str,
    *,
    output: str = "",
    time_ms: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: float = 0.0,
) -> StepResult:
    """Create a StepResult representing a failed step."""
    return StepResult(
        step_name=step_name,
        agent_name=_agent_label(agent),
        output=output,
        time_ms=time_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        error=error,
    )


@dataclass
class _MetricsAccumulator:
    """Running totals for token usage, cost, and wall-clock time across rounds.

    Used sequentially under ``FileLock`` — not thread-safe.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0

    def add(self, input_tokens: int, output_tokens: int, cost: float, time_ms: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost += cost
        self.time_ms += time_ms


@dataclass
class _RoundRecord:
    """Record of a single completed review round for state persistence."""

    round_number: int
    agent: str
    model: str
    ids: List[str]
    appended_at_utc: str
    cost: float


class ArchitecturalReviewLogWorkflow(WorkflowBase):
    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="architectural-review-log",
            name="Architectural Review Log Workflow",
            description=(
                "High-quality sequential architectural review. Uses flagship models by default "
                "and appends structured suggestions to the document's review appendix."
            ),
            version="1.0.0",
            capabilities=["document-review", "architecture", "multi-agent", "append-only"],
            tags=["architecture", "review", "appendix", "premium"],
            requires_agents=False,  # can select default agents from model catalog
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="document_path",
                    type="string",
                    required=True,
                    description="Path to the markdown document to append architectural review rounds to",
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=False,
                    description="Optional explicit agents (provider:model) to run sequentially; overrides default selection",
                ),
                WorkflowInput(
                    name="quality_tier",
                    type="string",
                    required=False,
                    default="flagship",
                    description="Default model tier when agents not specified: flagship|balanced|fast|mini",
                ),
                WorkflowInput(
                    name="providers",
                    type="string_list",
                    required=False,
                    description="Optional provider allowlist for default selection (e.g., ['anthropic','gemini'])",
                ),
                WorkflowInput(
                    name="reviewer_count",
                    type="number",
                    required=False,
                    default=2,
                    description="Number of default high-quality reviewers to run when agents not specified",
                ),
                WorkflowInput(
                    name="max_suggestions",
                    type="number",
                    required=False,
                    default=10,
                    description="Maximum number of suggestions per review round",
                ),
                WorkflowInput(
                    name="scope",
                    type="string",
                    required=False,
                    default="Improve plan clarity, auditability, and execution safety (architecture-focused).",
                    description="One-sentence scope statement inserted into the review round metadata",
                ),
                WorkflowInput(
                    name="init_if_missing",
                    type="boolean",
                    required=False,
                    default=True,
                    description="If true, initializes the Applied/Rejected/Incoming appendix structure when missing",
                ),
                WorkflowInput(
                    name="state_path",
                    type="string",
                    required=False,
                    description="Optional path for workflow state JSON (defaults to <doc_dir>/.startd8/architectural_review_state.json)",
                ),
                WorkflowInput(
                    name="warn_cost_usd",
                    type="number",
                    required=False,
                    description="Warn if cumulative cost exceeds this amount (USD)",
                ),
                WorkflowInput(
                    name="max_cost_usd",
                    type="number",
                    required=False,
                    description="Fail-fast if cumulative cost exceeds this amount (USD)",
                ),
                WorkflowInput(
                    name="review_template",
                    type="text",
                    required=False,
                    description="Optional prompt template override (must include required placeholders)",
                ),
                WorkflowInput(
                    name="context_files",
                    type="array",
                    required=False,
                    description=(
                        "List of file or directory paths to include as reference material in the reviewer prompt. "
                        "Directories are scanned recursively for .md files. "
                        "Use for lessons learned, design docs, or prior decisions."
                    ),
                ),
                WorkflowInput(
                    name="max_context_chars",
                    type="number",
                    required=False,
                    default=200_000,
                    description="Maximum total characters of context file content to include (default 200000)",
                ),
                WorkflowInput(
                    name="fallback_openai_model",
                    type="string",
                    required=False,
                    default="openai:gpt-4.1",
                    description=(
                        "If the configured OpenAI model is not available (e.g., access denied / model not found), "
                        "retry the round once with this fallback model."
                    ),
                ),
                WorkflowInput(
                    name="fallback_on_model_not_found",
                    type="boolean",
                    required=False,
                    default=True,
                    description="If true, retries OpenAI rounds with fallback_openai_model on model-not-found errors.",
                ),
                WorkflowInput(
                    name="gemini_safety_settings",
                    type="array",
                    required=False,
                    description=(
                        "Custom Gemini safety_settings applied to all Gemini reviewers. "
                        "Each entry: {category: 'HARM_CATEGORY_*', threshold: 'BLOCK_NONE'|'BLOCK_ONLY_HIGH'|...}. "
                        "When not set, Gemini uses its default filters (with automatic relaxation on SAFETY retry)."
                    ),
                ),
                WorkflowInput(
                    name="enable_triage",
                    type="boolean",
                    required=False,
                    default=True,
                    description="Enable automated triage step after all reviewers to classify suggestions as ACCEPT/REJECT",
                ),
                WorkflowInput(
                    name="enable_apply",
                    type="boolean",
                    required=False,
                    default=True,
                    description=(
                        "Enable apply-suggestions step after triage to integrate accepted suggestions "
                        "into the document body. Requires enable_triage=True."
                    ),
                ),
                WorkflowInput(
                    name="enable_prompt_caching",
                    type="boolean",
                    required=False,
                    default=True,
                    description=(
                        "Enable prompt caching for Anthropic agents. Moves the document body "
                        "into a system prompt for ~90%% input cost reduction on cache hits."
                    ),
                ),
                WorkflowInput(
                    name="substantially_addressed_threshold",
                    type="number",
                    required=False,
                    default=3,
                    description="Minimum accepted suggestions per area to mark it as 'substantially addressed'",
                ),
                WorkflowInput(
                    name="review_profile",
                    type="string",
                    required=False,
                    default="architecture",
                    description="Review profile to use (architecture|requirements|design)",
                ),
                WorkflowInput(
                    name="custom_review_profile",
                    type="object",
                    required=False,
                    description="Custom review profile object with keys: areas (list), persona (str), focus (str)",
                ),
                WorkflowInput(
                    name="feature_requirements",
                    type="array",
                    required=False,
                    description="List of paths to feature requirement documents (markdown). Enables dual-doc review mode.",
                ),
            ],
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        errors: List[str] = []
        doc_path = config.get("document_path")
        if not doc_path:
            errors.append("document_path is required")
        else:
            p = Path(str(doc_path)).expanduser()
            if not p.exists() or not p.is_file():
                errors.append(f"document_path does not exist or is not a file: {p}")

        reviewer_count = config.get("reviewer_count", 2)
        if reviewer_count is not None and (not isinstance(reviewer_count, int) or reviewer_count < 1 or reviewer_count > 5):
            errors.append("reviewer_count must be an int between 1 and 5")

        max_suggestions = config.get("max_suggestions", 10)
        if not isinstance(max_suggestions, int) or max_suggestions < 1 or max_suggestions > 25:
            errors.append("max_suggestions must be an int between 1 and 25")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Run the architectural review workflow.

        Sequentially executes review rounds (one per agent), validates and
        appends each reviewer's suggestions to the document's Appendix C,
        then optionally runs automated triage to classify suggestions into
        Appendix A (applied) or Appendix B (rejected).

        All document mutations are protected by a file lock to prevent
        concurrent writes.
        """
        started_at = datetime.now(timezone.utc)

        doc_path = Path(str(config["document_path"])).expanduser().resolve()
        init_if_missing = bool(config.get("init_if_missing", True))
        max_suggestions = int(config.get("max_suggestions", 10))
        scope = str(config.get("scope") or "").strip() or "Architecture-focused review"

        warn_cost_usd = config.get("warn_cost_usd")
        max_cost_usd = config.get("max_cost_usd")
        fallback_openai_model = str(config.get("fallback_openai_model") or "openai:gpt-4.1").strip()
        fallback_on_model_not_found = bool(config.get("fallback_on_model_not_found", True))

        default_state_path = doc_path.parent / ".startd8" / "architectural_review_state.json"
        state_path = Path(config.get("state_path") or default_state_path).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = doc_path.parent / ".startd8" / "architectural_review.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Resolve review profile
        profile_name = config.get("review_profile", "architecture")
        custom_profile = config.get("custom_review_profile")
        
        # Default to architecture if unknown profile name
        base_profile = REVIEW_PROFILES.get(profile_name, REVIEW_PROFILES["architecture"])
        
        # Allow custom override
        if custom_profile and isinstance(custom_profile, dict):
            allowed_areas = set(custom_profile.get("areas", base_profile["areas"]))
            persona = custom_profile.get("persona", base_profile["persona"])
            focus = custom_profile.get("focus", base_profile["focus"])
        else:
            allowed_areas = base_profile["areas"]
            persona = base_profile["persona"]
            focus = base_profile["focus"]

        # Resolve agents: explicit list in config OR provided agents param OR default selection
        resolved_agents: List[BaseAgent] = []
        explicit_specs = config.get("agents") or []
        if agents:
            resolved_agents = agents
        elif explicit_specs:
            resolved_agents = resolve_agents(explicit_specs)
        else:
            quality_tier = str(config.get("quality_tier") or "flagship")
            providers = config.get("providers")
            reviewer_count = int(config.get("reviewer_count", 2))  # matches default in metadata
            default_specs = _select_default_agents(quality_tier, reviewer_count, providers)
            resolved_agents = resolve_agents(default_specs)

        if not resolved_agents:
            return WorkflowResult.from_error(self.metadata.workflow_id, "No agents available for architectural review")

        # Apply caller-provided Gemini safety_settings to all Gemini agents
        gemini_safety = config.get("gemini_safety_settings")
        if gemini_safety:
            for ag in resolved_agents:
                if _is_gemini_agent(ag) and hasattr(ag, "safety_settings"):
                    ag.safety_settings = gemini_safety

        # Enable Anthropic prompt caching for input cost reduction
        enable_caching = bool(config.get("enable_prompt_caching", True))
        if enable_caching:
            for ag in resolved_agents:
                if _is_anthropic_agent(ag) and hasattr(ag, "enable_prompt_caching"):
                    ag.enable_prompt_caching = True

        step_results: List[StepResult] = []
        round_records: List[_RoundRecord] = []
        totals = _MetricsAccumulator()

        with FileLock(lock_path):
            # Load Feature Requirements (Dual-Document Mode)
            feature_reqs = config.get("feature_requirements")
            feature_doc_path = _get_feature_doc_path(feature_reqs)
            requirements_content = ""
            if feature_doc_path:
                try:
                    requirements_content = feature_doc_path.read_text(encoding="utf-8")
                except Exception as e:
                    _logger.warning("Failed to read feature requirements doc: %s", e, exc_info=True)

            doc_text = doc_path.read_text(encoding="utf-8")
            if init_if_missing:
                doc_text = _ensure_appendix_exists(doc_text)
                
                # Also initialize feature doc if present
                if feature_doc_path:
                    try:
                        fd_text = feature_doc_path.read_text(encoding="utf-8")
                        fd_text = _ensure_appendix_exists(fd_text)
                        atomic_write(feature_doc_path, fd_text, mode="w", backup=True)
                    except Exception as e:
                        _logger.warning("Failed to initialize feature doc appendix: %s", e)

            applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
            rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")
            next_round = _max_review_round(doc_text) + 1

            total_rounds = len(resolved_agents)
            self._emit_progress(on_progress, 0, total_rounds, f"Starting {total_rounds} architectural review round(s)")

            template_override = config.get("review_template")

            # Load context files (lessons learned, design docs, prior decisions)
            context_files = config.get("context_files") or []
            context_content = ""
            if context_files:
                max_context_chars = int(config.get("max_context_chars", 200_000))
                parts: List[str] = []
                for cf in context_files:
                    p = Path(str(cf)).expanduser().resolve()
                    if p.is_file():
                        try:
                            parts.append(f"### {p.name}\n\n{p.read_text(encoding='utf-8')}")
                        except Exception as e:
                            _logger.debug("Failed to read context file %s: %s", p, e)
                    elif p.is_dir():
                        for md_file in sorted(p.glob("**/*.md")):
                            try:
                                parts.append(
                                    f"### {md_file.relative_to(p)}\n\n"
                                    f"{md_file.read_text(encoding='utf-8')}"
                                )
                            except Exception as e:
                                _logger.debug("Failed to read context file %s: %s", md_file, e)
                context_content = "\n\n".join(parts)
                if len(context_content) > max_context_chars:
                    context_content = context_content[:max_context_chars] + "\n\n[... truncated ...]"

            # Compute substantially addressed areas and per-area coverage from existing Appendix A
            sa_threshold = int(config.get("substantially_addressed_threshold", 3))
            substantially_addressed = _compute_substantially_addressed_from_doc(doc_text, sa_threshold)
            coverage = _compute_area_coverage(doc_text, sa_threshold, allowed_areas=allowed_areas)

            # Build shared system prompt for prompt caching (document + context + requirements)
            shared_system_prompt: Optional[str] = None
            use_sp = enable_caching and not template_override  # skip caching with custom templates
            if use_sp:
                shared_system_prompt = _build_shared_system_prompt(
                    document_without_appendix=_strip_appendix_for_prompt(doc_text),
                    context_content=context_content,
                    requirements_content=requirements_content or "",
                )

            for i, agent in enumerate(resolved_agents):
                round_number = next_round + i
                step_name = f"architectural_review_R{round_number}"

                reviewer_label = f"{agent.name} ({getattr(agent, 'model', '')})"
                self._emit_progress(on_progress, i, total_rounds, f"Running Round R{round_number} with {reviewer_label}")

                prompt = _build_prompt(
                    document_without_appendix=_strip_appendix_for_prompt(doc_text),
                    applied_ids=applied_ids,
                    rejected_ids=rejected_ids,
                    round_number=round_number,
                    max_suggestions=max_suggestions,
                    reviewer_label=reviewer_label,
                    scope=scope,
                    template_override=template_override,
                    context_content=context_content,
                    substantially_addressed_areas=substantially_addressed,
                    area_coverage=coverage,
                    allowed_areas=allowed_areas,
                    persona=persona,
                    focus_guidance=focus,
                    requirements_content=requirements_content,
                    has_feature_requirements=bool(feature_doc_path),
                    use_system_prompt=use_sp,
                )

                # Build generate kwargs (system_prompt for caching)
                gen_kwargs: Dict[str, Any] = {}
                if shared_system_prompt is not None:
                    gen_kwargs["system_prompt"] = shared_system_prompt

                # Execute generation with graceful error handling, Gemini SAFETY
                # retry, and OpenAI model fallback.
                try:
                    response_text, time_ms, token_usage = agent.generate(prompt, **gen_kwargs)

                except GeminiSafetyFilterError as safety_err:
                    # ── Gemini SAFETY retry (Fix 3) ──────────────────────────
                    # Attempt 1: retry with reduced prompt (no context files)
                    # Attempt 2: retry with relaxed safety_settings + reduced prompt
                    # Both failures → skip this reviewer, continue to next round
                    _logger.warning(
                        "Gemini SAFETY filter hit for R%d (%s); "
                        "prompt_tokens=%s, safety_ratings=%s; "
                        "attempting reduced-context retry",
                        round_number,
                        reviewer_label,
                        safety_err.prompt_tokens,
                        safety_err.safety_ratings,
                    )
                    self._emit_progress(
                        on_progress, i, total_rounds,
                        f"Gemini SAFETY filter on R{round_number}; retrying with reduced context",
                    )

                    reduced_prompt = _build_prompt(
                        document_without_appendix=_strip_appendix_for_prompt(doc_text),
                        applied_ids=applied_ids,
                        rejected_ids=rejected_ids,
                        round_number=round_number,
                        max_suggestions=max_suggestions,
                        reviewer_label=reviewer_label,
                        scope=scope,
                        template_override=template_override,
                        context_content="",  # drop context files
                        allowed_areas=allowed_areas,
                        persona=persona,
                        focus_guidance=focus,
                    )

                    try:
                        response_text, time_ms, token_usage = agent.generate(reduced_prompt)
                    except GeminiSafetyFilterError:
                        # Attempt 2: temporarily apply relaxed safety_settings
                        _logger.warning(
                            "Reduced-context retry still blocked; retrying with relaxed safety_settings",
                        )
                        self._emit_progress(
                            on_progress, i, total_rounds,
                            f"R{round_number}: retrying with relaxed safety settings",
                        )
                        original_safety = getattr(agent, "safety_settings", None)
                        try:
                            if _is_gemini_agent(agent):
                                agent.safety_settings = RELAXED_SAFETY_SETTINGS
                            response_text, time_ms, token_usage = agent.generate(reduced_prompt)
                        except Exception as e3:
                            # Give up on this reviewer, continue to next
                            _logger.warning(
                                "Gemini SAFETY retry exhausted for R%d; skipping reviewer",
                                round_number,
                            )
                            self._emit_progress(
                                on_progress, i, total_rounds,
                                f"R{round_number}: skipping {reviewer_label} after repeated SAFETY blocks",
                            )
                            step_results.append(_make_error_step(
                                step_name, agent,
                                f"Gemini SAFETY filter (skipped): {e3}",
                            ))
                            continue  # ← skip, don't break — let remaining reviewers run
                        finally:
                            # Restore original settings so they don't leak to later operations
                            if _is_gemini_agent(agent):
                                agent.safety_settings = original_safety

                except Exception as e:
                    # If OpenAI model is unavailable, retry once with a fallback model
                    if (
                        fallback_on_model_not_found
                        and fallback_openai_model
                        and _is_openai_agent(agent)
                        and _looks_like_model_not_found_error(e)
                    ):
                        self._emit_progress(
                            on_progress,
                            i,
                            total_rounds,
                            f"OpenAI model unavailable ({getattr(agent, 'model', '')}); retrying with {fallback_openai_model}",
                        )
                        try:
                            fallback_agent = resolve_agents([fallback_openai_model])[0]
                            response_text, time_ms, token_usage = fallback_agent.generate(prompt, **gen_kwargs)
                            agent = fallback_agent  # record agent/model that actually ran
                        except Exception as e2:
                            step_results.append(_make_error_step(step_name, agent, str(e2)))
                            break
                    else:
                        step_results.append(_make_error_step(step_name, agent, str(e)))
                        break

                input_tokens = token_usage_input(token_usage) if token_usage else 0
                output_tokens = token_usage_output(token_usage) if token_usage else 0
                cost = token_usage_cost(token_usage) if token_usage else 0.0
                totals.add(input_tokens, output_tokens, cost, time_ms)

                if warn_cost_usd is not None and totals.cost >= float(warn_cost_usd):
                    self._emit_progress(
                        on_progress,
                        i,
                        total_rounds,
                        f"Cost warning: cumulative ${totals.cost:.2f} >= warn_cost_usd=${float(warn_cost_usd):.2f}",
                    )

                if max_cost_usd is not None and totals.cost >= float(max_cost_usd):
                    step_results.append(_make_error_step(
                        step_name, agent,
                        f"Max cost exceeded: ${totals.cost:.2f} >= max_cost_usd=${float(max_cost_usd):.2f}",
                        time_ms=time_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                    ))
                    break

                # Strip code-block fences (Gemini sometimes wraps output)
                response_text = _strip_code_fences(response_text)

                # Dual-Document: Extract feature suggestions if present
                if feature_doc_path:
                    feature_snippet = _extract_feature_snippet(
                        response_text,
                        round_number,
                        reviewer_label,
                        scope,
                    )
                    if feature_snippet:
                        try:
                            # Atomic append to feature doc
                            curr_feat = feature_doc_path.read_text(encoding="utf-8")
                            updated_feat = curr_feat.rstrip() + "\n\n" + feature_snippet + "\n"
                            atomic_write(feature_doc_path, updated_feat, mode="w", backup=True)
                        except Exception as e:
                            _logger.warning("Failed to append feature suggestions: %s", e, exc_info=True)

                ok, message, ids = _validate_snippet(response_text, round_number, max_suggestions, allowed_areas=allowed_areas)
                if not ok:
                    _logger.warning(
                        "Validation failed for R%d (%s): %s",
                        round_number,
                        reviewer_label,
                        message,
                    )

                    # ── Validation retry (1 attempt with targeted re-prompt) ──
                    retry_prompt = (
                        f"Your previous response failed validation: {message}\n\n"
                        f"Please regenerate the review snippet for Round R{round_number}. "
                        f"Requirements:\n"
                        f"- Start with: #### Review Round R{round_number}\n"
                        f"- Table header row EXACTLY (plain text, no bold): | {' | '.join(REQUIRED_COLUMNS)} |\n"
                        f"- IDs: R{round_number}-S1, R{round_number}-S2, etc.\n"
                        f"- Area must be one of: {', '.join(sorted(ALLOWED_AREAS))}\n"
                        f"- Severity must be one of: {', '.join(sorted(ALLOWED_SEVERITIES))}\n"
                        f"- Do NOT wrap output in code blocks (no ```)\n\n"
                        f"Original prompt:\n{prompt}"
                    )
                    self._emit_progress(
                        on_progress, i, total_rounds,
                        f"R{round_number}: validation failed ({message}); retrying",
                    )
                    try:
                        retry_text, retry_time_ms, retry_token_usage = agent.generate(retry_prompt, **gen_kwargs)
                        retry_text = _strip_code_fences(retry_text)
                        retry_input = token_usage_input(retry_token_usage) if retry_token_usage else 0
                        retry_output = token_usage_output(retry_token_usage) if retry_token_usage else 0
                        retry_cost = token_usage_cost(retry_token_usage) if retry_token_usage else 0.0
                        totals.add(retry_input, retry_output, retry_cost, retry_time_ms)

                        ok2, message2, ids = _validate_snippet(retry_text, round_number, max_suggestions, allowed_areas=allowed_areas)
                        if ok2:
                            _logger.info(
                                "Validation retry succeeded for R%d (%s)",
                                round_number,
                                reviewer_label,
                            )
                            response_text = retry_text
                            time_ms += retry_time_ms
                            input_tokens += retry_input
                            output_tokens += retry_output
                            cost += retry_cost
                        else:
                            _logger.warning(
                                "Validation retry also failed for R%d (%s): %s; skipping reviewer",
                                round_number,
                                reviewer_label,
                                message2,
                            )
                            step_results.append(_make_error_step(
                                step_name, agent,
                                f"Invalid snippet after retry: {message2}",
                                output=retry_text[:500] + "..." if len(retry_text) > 500 else retry_text,
                                time_ms=time_ms + retry_time_ms,
                                input_tokens=input_tokens + retry_input,
                                output_tokens=output_tokens + retry_output,
                                cost=cost + retry_cost,
                            ))
                            continue  # skip reviewer, let remaining reviewers run
                    except Exception as retry_err:
                        _logger.warning(
                            "Validation retry call failed for R%d (%s): %s; skipping reviewer",
                            round_number,
                            reviewer_label,
                            retry_err,
                        )
                        step_results.append(_make_error_step(
                            step_name, agent,
                            f"Validation retry failed: {retry_err}",
                            output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                            time_ms=time_ms,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=cost,
                        ))
                        continue  # skip reviewer, let remaining reviewers run

                # Fix mis-numbered IDs before appending (LLMs sometimes use wrong round prefix)
                response_text = _fix_snippet_ids(response_text, round_number)
                ids = [re.sub(r"R\d+-([SF]\d+)", rf"R{round_number}-\1", sid) for sid in ids]

                # Append snippet and persist
                doc_text = doc_text.rstrip() + "\n\n" + response_text.strip() + "\n"
                atomic_write(doc_path, doc_text, mode="w", backup=True)

                # Update memory from current doc for next round
                applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
                rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")

                record = _RoundRecord(
                    round_number=round_number,
                    agent=agent.name,
                    model=getattr(agent, "model", ""),
                    ids=ids,
                    appended_at_utc=_now_utc(),
                    cost=cost,
                )
                round_records.append(record)

                step_results.append(StepResult(
                    step_name=step_name,
                    agent_name=_agent_label(agent),
                    output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                    time_ms=time_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    error=None,
                ))

                # State file (best-effort)
                try:
                    state = {
                        "document_path": str(doc_path),
                        "updated_at_utc": _now_utc(),
                        "applied_ids": applied_ids,
                        "rejected_ids": rejected_ids,
                        "rounds": [
                            {
                                "round": r.round_number,
                                "agent": r.agent,
                                "model": r.model,
                                "ids": r.ids,
                                "appended_at_utc": r.appended_at_utc,
                                "cost": r.cost,
                            }
                            for r in round_records
                        ],
                        "cumulative_cost_usd": totals.cost,
                    }
                    atomic_write_json(state_path, state, indent=2, sort_keys=False)
                except Exception as e:
                    _logger.warning("Failed to write state file %s: %s", state_path, e)

                self._emit_progress(on_progress, i + 1, total_rounds, f"Appended Round R{round_number}")

            # ── Automated Triage Step ──────────────────────────────────────
            enable_triage = bool(config.get("enable_triage", True))
            triage_decisions: List[Dict[str, Any]] = []
            untriaged: List[Dict[str, Any]] = []
            triage_info: Dict[str, Any] = {
                "enabled": enable_triage,
                "accepted": 0,
                "rejected": 0,
                "feature_accepted": 0,
                "feature_rejected": 0,
                "untriaged_remaining": [],
                "substantially_addressed_areas": [],
                "areas_needing_review": [],
            }

            if enable_triage and round_records and resolved_agents:
                triage_agent = resolved_agents[0]

                # Re-extract applied/rejected (may have changed during rounds)
                applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
                rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")

                untriaged, endorsements = _extract_untriaged_suggestions(doc_text, applied_ids, rejected_ids)

                if untriaged:
                    self._emit_progress(on_progress, total_rounds, total_rounds, "Running automated triage")
                    untriaged_ids = [s["id"] for s in untriaged]
                    untriaged_block = _build_untriaged_block(untriaged)
                    reviewer_sources = _extract_reviewer_sources(doc_text)

                    triage_prompt = _build_triage_prompt(
                        document_without_appendix=_strip_appendix_for_prompt(doc_text),
                        applied_ids=applied_ids,
                        rejected_ids=rejected_ids,
                        untriaged_block=untriaged_block,
                        endorsement_counts=endorsements,
                        allowed_areas=allowed_areas,
                        persona=persona,
                        has_feature_suggestions=bool(feature_doc_path),
                        use_system_prompt=use_sp,
                    )

                    # Build triage generate kwargs (same system_prompt for caching)
                    triage_gen_kwargs: Dict[str, Any] = {}
                    if shared_system_prompt is not None:
                        triage_gen_kwargs["system_prompt"] = shared_system_prompt

                    # Execute triage with same error handling pattern
                    triage_ok = False
                    triage_decisions: List[Dict[str, Any]] = []
                    triage_missing: List[str] = []

                    try:
                        triage_text, triage_time_ms, triage_token_usage = triage_agent.generate(triage_prompt, **triage_gen_kwargs)
                    except GeminiSafetyFilterError:
                        _logger.warning("Triage blocked by Gemini SAFETY filter; retrying with relaxed settings")
                        original_safety = getattr(triage_agent, "safety_settings", None)
                        try:
                            if _is_gemini_agent(triage_agent):
                                triage_agent.safety_settings = RELAXED_SAFETY_SETTINGS
                            triage_text, triage_time_ms, triage_token_usage = triage_agent.generate(triage_prompt, **triage_gen_kwargs)
                        except Exception as triage_err:
                            _logger.warning("Triage failed after retry: %s", triage_err)
                            step_results.append(_make_error_step(
                                "triage", triage_agent, f"Triage failed: {triage_err}",
                            ))
                            triage_text = None
                            triage_time_ms = 0
                            triage_token_usage = None
                        finally:
                            if _is_gemini_agent(triage_agent):
                                triage_agent.safety_settings = original_safety
                    except Exception as triage_err:
                        _logger.warning("Triage failed: %s", triage_err)
                        step_results.append(_make_error_step(
                            "triage", triage_agent, f"Triage failed: {triage_err}",
                        ))
                        triage_text = None
                        triage_time_ms = 0
                        triage_token_usage = None

                    if triage_text is not None:
                        triage_input_tokens = token_usage_input(triage_token_usage) if triage_token_usage else 0
                        triage_output_tokens = token_usage_output(triage_token_usage) if triage_token_usage else 0
                        triage_cost = token_usage_cost(triage_token_usage) if triage_token_usage else 0.0
                        totals.add(triage_input_tokens, triage_output_tokens, triage_cost, triage_time_ms)

                        triage_ok, triage_msg, triage_decisions, triage_missing = _validate_triage_output(
                            triage_text, untriaged_ids, allowed_areas=allowed_areas
                        )

                        if not triage_ok:
                            _logger.warning("Triage validation failed: %s", triage_msg)
                            # Try one retry with targeted re-prompt
                            retry_prompt = (
                                f"Your previous triage response failed validation: {triage_msg}\n\n"
                                f"Please output ONLY a JSON array with entries for each suggestion. "
                                f"Required fields: id, decision (ACCEPT or REJECT), summary, rationale, "
                                f"area (one of: {', '.join(sorted(allowed_areas))}).\n\n"
                                f"Suggestions to triage:\n{untriaged_block}"
                            )
                            try:
                                retry_text, retry_time_ms, retry_token_usage = triage_agent.generate(retry_prompt, **triage_gen_kwargs)
                                retry_input = token_usage_input(retry_token_usage) if retry_token_usage else 0
                                retry_output = token_usage_output(retry_token_usage) if retry_token_usage else 0
                                retry_cost = token_usage_cost(retry_token_usage) if retry_token_usage else 0.0
                                totals.add(retry_input, retry_output, retry_cost, retry_time_ms)
                                triage_input_tokens += retry_input
                                triage_output_tokens += retry_output
                                triage_cost += retry_cost
                                triage_time_ms += retry_time_ms

                                triage_ok, triage_msg, triage_decisions, triage_missing = _validate_triage_output(
                                    retry_text, untriaged_ids, allowed_areas=allowed_areas
                                )
                                if not triage_ok:
                                    _logger.warning("Triage retry also failed: %s", triage_msg)
                            except Exception as retry_err:
                                _logger.warning("Triage retry call failed: %s", retry_err)

                        if triage_decisions:
                            # Split plan vs feature suggestions
                            plan_decisions = [d for d in triage_decisions if "F" not in d["id"]]
                            feature_decisions = [d for d in triage_decisions if "F" in d["id"]]

                            # Apply plan decisions to main doc
                            if plan_decisions:
                                doc_text = _apply_triage_decisions(doc_text, plan_decisions, reviewer_sources)

                                # Compute substantially addressed areas
                                applied_with_area = [(d["id"], d["area"]) for d in plan_decisions if d["decision"] == "ACCEPT"]
                                # Also include previously applied suggestions
                                prev_addressed = _compute_substantially_addressed_from_doc(doc_text, sa_threshold)
                                # Merge with new accepts
                                for area, ids in prev_addressed.items():
                                    for sid in ids:
                                        if (sid, area) not in applied_with_area:
                                            applied_with_area.append((sid, area))
                                addressed = _compute_substantially_addressed(applied_with_area, sa_threshold)

                                if addressed:
                                    doc_text = _insert_substantially_addressed_section(doc_text, addressed)
                                    triage_info["substantially_addressed_areas"] = list(addressed.keys())

                                # Compute and insert areas needing further review
                                post_triage_coverage = _compute_area_coverage(doc_text, sa_threshold, allowed_areas=allowed_areas)
                                doc_text = _insert_areas_needing_review_section(doc_text, post_triage_coverage, sa_threshold)
                                areas_needing = [
                                    area for area, info in post_triage_coverage.items()
                                    if not info["addressed"]
                                ]
                                triage_info["areas_needing_review"] = sorted(areas_needing)

                                # Persist document
                                atomic_write(doc_path, doc_text, mode="w", backup=True)

                            # Apply feature decisions to feature doc
                            if feature_decisions and feature_doc_path:
                                try:
                                    fd_text = feature_doc_path.read_text(encoding="utf-8")
                                    # Ensure appendix exists if not already
                                    fd_text = _ensure_appendix_exists(fd_text)
                                    fd_text = _apply_triage_decisions(fd_text, feature_decisions, reviewer_sources)
                                    atomic_write(feature_doc_path, fd_text, mode="w", backup=True)

                                    triage_info["feature_accepted"] = sum(1 for d in feature_decisions if d["decision"] == "ACCEPT")
                                    triage_info["feature_rejected"] = sum(1 for d in feature_decisions if d["decision"] == "REJECT")
                                except Exception as e:
                                    _logger.warning("Failed to apply feature triage: %s", e)

                            accepted_count = sum(1 for d in triage_decisions if d["decision"] == "ACCEPT")
                            rejected_count = sum(1 for d in triage_decisions if d["decision"] == "REJECT")
                            triage_info["accepted"] = accepted_count
                            triage_info["rejected"] = rejected_count
                            triage_info["untriaged_remaining"] = triage_missing

                        step_results.append(StepResult(
                            step_name="triage",
                            agent_name=_agent_label(triage_agent),
                            output=f"Accepted: {triage_info['accepted']}, Rejected: {triage_info['rejected']}, Remaining: {len(triage_missing)}",
                            time_ms=triage_time_ms,
                            input_tokens=triage_input_tokens,
                            output_tokens=triage_output_tokens,
                            cost=triage_cost,
                            error=None if triage_decisions else f"Triage validation failed: {triage_msg}",
                            metadata={
                                "accepted": triage_info["accepted"],
                                "rejected": triage_info["rejected"],
                                "untriaged_remaining": triage_missing,
                            },
                        ))

            # ── Apply Suggestions Step ────────────────────────────────────
            enable_apply = bool(config.get("enable_apply", True))
            apply_info: Dict[str, Any] = {
                "enabled": enable_apply and enable_triage,
                "applied_count": 0,
                "applied_ids": [],
                "warning_ids": [],
                "feature_applied_count": 0,
                "error": None,
            }

            if enable_apply and enable_triage and triage_info["accepted"] > 0 and resolved_agents:
                apply_agent = resolved_agents[0]
                self._emit_progress(on_progress, total_rounds, total_rounds, "Applying accepted suggestions to document")

                # Extract accepted suggestions enriched with Appendix C data
                plan_accepted = _extract_accepted_suggestions_for_apply(
                    [d for d in triage_decisions if "-S" in d.get("id", "")] if triage_decisions else [],
                    untriaged,
                )

                if plan_accepted:
                    try:
                        (
                            updated_doc, apply_ok, apply_msg, apply_warnings,
                            apply_time_ms, apply_input, apply_output, apply_cost,
                        ) = _apply_suggestions_to_doc(
                            doc_text, plan_accepted, apply_agent,
                            persona=persona,
                            system_prompt=shared_system_prompt,
                        )
                        totals.add(apply_input, apply_output, apply_cost, apply_time_ms)

                        if apply_ok:
                            doc_text = updated_doc
                            atomic_write(doc_path, doc_text, mode="w", backup=True)
                            apply_info["applied_count"] = len(plan_accepted)
                            apply_info["applied_ids"] = [s["id"] for s in plan_accepted]
                            apply_info["warning_ids"] = apply_warnings
                        else:
                            # Retry once — call _apply_suggestions_to_doc() again
                            # so the retry gets the full suggestion table and context
                            _logger.warning("Apply validation failed: %s; retrying", apply_msg)
                            try:
                                (
                                    updated_doc, apply_ok, apply_msg, apply_warnings,
                                    r_time, r_in, r_out, r_cost,
                                ) = _apply_suggestions_to_doc(
                                    doc_text, plan_accepted, apply_agent,
                                    persona=persona,
                                    system_prompt=shared_system_prompt,
                                )
                                totals.add(r_in, r_out, r_cost, r_time)
                                apply_time_ms += r_time
                                apply_input += r_in
                                apply_output += r_out
                                apply_cost += r_cost

                                if apply_ok:
                                    doc_text = updated_doc
                                    atomic_write(doc_path, doc_text, mode="w", backup=True)
                                    apply_info["applied_count"] = len(plan_accepted)
                                    apply_info["applied_ids"] = [s["id"] for s in plan_accepted]
                                    apply_info["warning_ids"] = apply_warnings
                                else:
                                    apply_info["error"] = f"Retry also failed: {apply_msg}"
                            except Exception as retry_err:
                                _logger.warning("Apply retry failed: %s", retry_err, exc_info=True)
                                apply_info["error"] = f"Apply retry failed: {retry_err}"

                        step_results.append(StepResult(
                            step_name="apply_suggestions",
                            agent_name=_agent_label(apply_agent),
                            output=f"Applied: {apply_info['applied_count']}, Warnings: {len(apply_info['warning_ids'])}",
                            time_ms=apply_time_ms,
                            input_tokens=apply_input,
                            output_tokens=apply_output,
                            cost=apply_cost,
                            error=apply_info["error"],
                            metadata={
                                "applied_count": apply_info["applied_count"],
                                "applied_ids": apply_info["applied_ids"],
                                "warning_ids": apply_info["warning_ids"],
                            },
                        ))

                    except GeminiSafetyFilterError:
                        _logger.warning("Apply step blocked by Gemini SAFETY filter; retrying with relaxed settings")
                        original_safety = getattr(apply_agent, "safety_settings", None)
                        try:
                            if _is_gemini_agent(apply_agent):
                                apply_agent.safety_settings = RELAXED_SAFETY_SETTINGS
                            (
                                updated_doc, apply_ok, apply_msg, apply_warnings,
                                apply_time_ms, apply_input, apply_output, apply_cost,
                            ) = _apply_suggestions_to_doc(
                                doc_text, plan_accepted, apply_agent,
                                persona=persona,
                                system_prompt=shared_system_prompt,
                            )
                            totals.add(apply_input, apply_output, apply_cost, apply_time_ms)
                            if apply_ok:
                                doc_text = updated_doc
                                atomic_write(doc_path, doc_text, mode="w", backup=True)
                                apply_info["applied_count"] = len(plan_accepted)
                                apply_info["applied_ids"] = [s["id"] for s in plan_accepted]
                                apply_info["warning_ids"] = apply_warnings
                        except Exception as e2:
                            _logger.warning("Apply SAFETY retry failed: %s", e2, exc_info=True)
                            apply_info["error"] = f"Apply SAFETY retry failed: {e2}"
                        finally:
                            if _is_gemini_agent(apply_agent):
                                apply_agent.safety_settings = original_safety
                        # Record success or error step based on outcome
                        if apply_info.get("error"):
                            step_results.append(_make_error_step(
                                "apply_suggestions", apply_agent,
                                apply_info["error"],
                            ))
                        else:
                            step_results.append(StepResult(
                                step_name="apply_suggestions",
                                agent_name=_agent_label(apply_agent),
                                output=f"Applied: {apply_info['applied_count']} (SAFETY retry), Warnings: {len(apply_info['warning_ids'])}",
                                time_ms=apply_time_ms,
                                input_tokens=apply_input,
                                output_tokens=apply_output,
                                cost=apply_cost,
                                error=None,
                                metadata={
                                    "applied_count": apply_info["applied_count"],
                                    "applied_ids": apply_info["applied_ids"],
                                    "warning_ids": apply_info["warning_ids"],
                                    "safety_retry": True,
                                },
                            ))
                    except Exception as apply_err:
                        _logger.warning("Apply step failed: %s", apply_err, exc_info=True)
                        apply_info["error"] = str(apply_err)
                        step_results.append(_make_error_step(
                            "apply_suggestions", apply_agent, str(apply_err),
                        ))

                # Apply to feature doc (dual-document mode)
                if feature_doc_path and triage_info.get("feature_accepted", 0) > 0:
                    feature_accepted = _extract_accepted_suggestions_for_apply(
                        [d for d in triage_decisions if "-F" in d.get("id", "")] if triage_decisions else [],
                        untriaged,
                    )
                    if feature_accepted:
                        try:
                            fd_text = feature_doc_path.read_text(encoding="utf-8")
                            (
                                updated_fd, fd_ok, fd_msg, fd_warns,
                                fd_time, fd_in, fd_out, fd_cost,
                            ) = _apply_suggestions_to_doc(
                                fd_text, feature_accepted, apply_agent,
                                persona=persona,
                                system_prompt=None,  # feature doc has different content
                            )
                            totals.add(fd_in, fd_out, fd_cost, fd_time)
                            if fd_ok:
                                atomic_write(feature_doc_path, updated_fd, mode="w", backup=True)
                                apply_info["feature_applied_count"] = len(feature_accepted)
                        except Exception as e:
                            _logger.warning("Failed to apply suggestions to feature doc: %s", e, exc_info=True)

            # Update state file with triage + apply info
            try:
                applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
                rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")
                state = {
                    "document_path": str(doc_path),
                    "updated_at_utc": _now_utc(),
                    "applied_ids": applied_ids,
                    "rejected_ids": rejected_ids,
                    "rounds": [
                        {
                            "round": r.round_number,
                            "agent": r.agent,
                            "model": r.model,
                            "ids": r.ids,
                            "appended_at_utc": r.appended_at_utc,
                            "cost": r.cost,
                        }
                        for r in round_records
                    ],
                    "cumulative_cost_usd": totals.cost,
                    "triage": triage_info,
                    "apply": apply_info,
                }
                atomic_write_json(state_path, state, indent=2, sort_keys=False)
            except Exception as e:
                _logger.warning("Failed to write state file %s: %s", state_path, e)

        completed_at = datetime.now(timezone.utc)
        success = bool(round_records) and all(
            s.error is None for s in step_results
            if s.step_name not in ("triage", "apply_suggestions")
        )

        metrics = WorkflowMetrics(
            total_time_ms=totals.time_ms,
            input_tokens=totals.input_tokens,
            output_tokens=totals.output_tokens,
            total_cost=totals.cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=success,
            output={
                "document_path": str(doc_path),
                "feature_document_path": str(feature_doc_path) if feature_doc_path else None,
                "rounds_appended": len(round_records),
                "round_numbers": [r.round_number for r in round_records],
                "state_path": str(state_path),
                "cumulative_cost_usd": totals.cost,
                "triage": triage_info,
                "apply": apply_info,
            },
            metrics=metrics,
            steps=step_results,
            error=None if success else "Architectural review did not complete successfully; see steps for details",
            started_at=started_at,
            completed_at=completed_at,
        )

