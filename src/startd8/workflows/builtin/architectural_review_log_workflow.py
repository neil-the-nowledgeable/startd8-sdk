"""
ArchitecturalReviewLogWorkflow — Convergent Review Protocol (CRP) implementation.

Implements the Convergent Review Protocol: a structured, iterative, domain-aware
review process that converges toward full coverage across defined review areas.

CRP characteristics:
- Structured 7-column suggestion schema (ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach)
- Three-appendix triage structure: Applied (A), Rejected with rationale (B), Incoming (C)
- Round-based iteration with sequential reviewers, each building on triaged prior rounds
- Domain coverage tracking with per-area "substantially addressed" thresholds
- Two-tier priority steering: uncovered areas get Tier 1 priority; covered areas deprioritized
- Convergence: process narrows as areas cross threshold; enters gap-hunting mode when all covered
- Endorsement system for building consensus on untriaged suggestions
- Dual-document mode for simultaneous plan + feature requirements review

Defaults to flagship models. Enforces a strict suggestion-table schema.
See docs/ARCHITECTURAL_REVIEW_REQUIREMENTS.md for full functional requirements (RV-xxx).
See docs/capability-index/startd8.architectural-review.functional-requirements.yaml for canonical YAML.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
from ...model_catalog import Models, list_models_by_tier
from ...agents.pool import TimeoutConfig
from ...utils.agent_resolution import resolve_agents
from ...utils.file_operations import FileLock, atomic_write, atomic_write_json
from ...utils.retry import RetryConfig
from ...utils.token_usage import token_usage_input, token_usage_output, token_usage_cost

_logger = logging.getLogger(__name__)

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
# The appendix structure implements the Convergent Review Protocol (CRP) —
# see docs/ARCHITECTURAL_REVIEW_REQUIREMENTS.md for formal definition.
APPENDIX_TEMPLATE = """---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix implements the **Convergent Review Protocol (CRP)** — an iterative, domain-aware review process that converges toward full coverage. It is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

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
    """Split a markdown table row into cells, handling escaped pipes.

    Escaped pipes (\\|) within cell content are preserved and unescaped.
    Unescaped pipes are treated as cell delimiters.
    """
    # Replace escaped pipes with a placeholder that won't appear in real content
    placeholder = "\x00PIPE\x00"
    escaped = row.strip().strip("|").replace("\\|", placeholder)
    # Split on unescaped pipes
    cells = [c.strip().replace(placeholder, "|") for c in escaped.split("|")]
    return cells


def _ensure_appendix_exists(doc: str) -> str:
    if APPENDIX_HEADING in doc:
        return doc
    return doc.rstrip() + "\n\n" + APPENDIX_TEMPLATE


def _get_feature_doc_path(feature_requirements: list) -> Optional[Path]:
    """Return the first .md file from feature_requirements paths, or None."""
    for item in feature_requirements:
        p = Path(str(item)).expanduser().resolve()
        if p.is_file() and p.suffix == ".md":
            return p
        elif p.is_dir():
            for md_file in sorted(p.glob("*.md")):
                return md_file
    return None


def _extract_feature_snippet(
    full_snippet: str,
    round_number: int,
    reviewer_label: str,
    scope: str,
) -> str:
    """Extract feature suggestions from reviewer output, formatted as a feature doc Appendix C entry."""
    match = re.search(
        r"(####?\s*Feature Requirements Suggestions\s*\n.*?)(?=\n####?\s+(?!Feature)|$)",
        full_snippet,
        re.DOTALL,
    )
    if not match:
        return ""
    feature_table = match.group(1).strip()
    # Wrap in round heading for the feature doc's Appendix C
    return (
        f"#### Review Round R{round_number}\n\n"
        f"- **Reviewer**: {reviewer_label}\n"
        f"- **Date**: {_now_utc()}\n"
        f"- **Scope**: {scope}\n\n"
        f"{feature_table}\n"
    )


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

        # Extract table rows (may have multiple tables: plan + feature)
        lines = block.splitlines()
        in_table = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and "ID" in stripped:
                in_table = True
                continue
            if in_table and stripped.startswith("|") and stripped.startswith("| -"):
                # Separator row
                continue
            if in_table and stripped.startswith("|"):
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
            elif in_table and not stripped.startswith("|"):
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
    has_feature_suggestions: bool = False,
) -> str:
    """Build the triage prompt asking agent to classify each untriaged suggestion."""
    applied_list = ", ".join(applied_ids[:50]) if applied_ids else "(none)"
    rejected_list = ", ".join(rejected_ids[:50]) if rejected_ids else "(none)"

    endorsement_info = ""
    if endorsement_counts:
        parts = [f"  - {sid}: {count} endorsement(s)" for sid, count in sorted(endorsement_counts.items())]
        endorsement_info = "Endorsement counts (suggestions endorsed by multiple reviewers should be weighted higher):\n" + "\n".join(parts) + "\n\n"

    suggestion_type_note = ""
    if has_feature_suggestions:
        suggestion_type_note = (
            "\n**Note on suggestion types:**\n"
            "- R*-S* IDs are plan suggestions (improvements to the implementation plan)\n"
            "- R*-F* IDs are feature suggestions (improvements to the feature requirements document)\n"
            "Evaluate both types using the same ACCEPT/REJECT criteria.\n\n"
        )

    return f"""You are an expert enterprise architect performing triage on architectural review suggestions.

Your task: Evaluate every untriaged suggestion below and decide whether to ACCEPT or REJECT it.

Context:
- Previously applied suggestions: {applied_list}
- Previously rejected suggestions: {rejected_list}

{endorsement_info}{suggestion_type_note}Untriaged suggestions to evaluate:
{untriaged_block}

Document being reviewed (for context):
---
{document_without_appendix}
---

You MUST output a JSON array. Each element must have these fields:
- "id": the suggestion ID (e.g. "R1-S1")
- "decision": exactly "ACCEPT" or "REJECT"
- "summary": a one-sentence summary of the suggestion
- "rationale": why you are accepting or rejecting it
- "area": one of: {', '.join(sorted(ALLOWED_AREAS))}

Output ONLY the JSON array, no other text. Example:
[
  {{"id": "R1-S1", "decision": "ACCEPT", "summary": "Add circuit breakers", "rationale": "Critical for resilience", "area": "architecture"}},
  {{"id": "R1-S2", "decision": "REJECT", "summary": "Use GraphQL", "rationale": "Not aligned with REST strategy", "area": "interfaces"}}
]
"""


def _validate_triage_output(
    raw_text: str,
    untriaged_ids: List[str],
) -> Tuple[bool, str, List[Dict[str, Any]], List[str]]:
    """
    Parse and validate triage JSON output.

    Returns:
        (ok, message, parsed_decisions, missing_ids)
        Partial results are accepted — missing IDs stay untriaged.
    """
    cleaned = _strip_json_fences(raw_text.strip())

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
            decision = entry["decision"]
            area = entry["area"].strip().lower()

            if sid not in untriaged_set:
                errors.append(f"Entry {i}: unknown ID '{sid}'")
                continue
            if decision not in ("ACCEPT", "REJECT"):
                errors.append(f"Entry {i}: invalid decision '{decision}' (must be ACCEPT or REJECT)")
                continue
            if area not in ALLOWED_AREAS:
                errors.append(f"Entry {i}: invalid area '{area}' (allowed: {sorted(ALLOWED_AREAS)})")
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
) -> Dict[str, Dict[str, Any]]:
    """
    Compute coverage status for every area in ALLOWED_AREAS.

    Returns: {area: {"accepted_count": N, "accepted_ids": [...], "addressed": bool, "gap": M}}
    where gap = max(0, threshold - accepted_count).
    """
    applied_ids = _extract_table_ids(doc, "### Appendix A: Applied Suggestions")

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
    area_ids: Dict[str, List[str]] = {area: [] for area in ALLOWED_AREAS}
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

        # Extract suggestion IDs (S-prefix plan, F-prefix feature)
        for sid in re.findall(r"(R\d+-[SF]\d+)", block):
            # Only set if we haven't seen it (first occurrence = definition)
            if sid not in sources:
                sources[sid] = reviewer_label

    return sources


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
    requirements_content: str = "",
    substantially_addressed_areas: Optional[Dict[str, List[str]]] = None,
    area_coverage: Optional[Dict[str, Dict[str, Any]]] = None,
    has_feature_requirements: bool = False,
) -> str:
    """
    Build the reviewer prompt. Supports override template that must include:
    - {round_number}, {max_suggestions}, {applied_ids}, {rejected_ids}, {document}, {reviewer_label}, {scope}
    - Optional: {context} (reference material block, empty string when no context provided)
    - Optional: {requirements} (feature requirements block, empty string when none provided)
    - Optional: {has_feature_requirements} (bool, enables dual-document output sections)
    """
    applied_list = ", ".join(applied_ids[:50]) if applied_ids else "(none)"
    rejected_list = ", ".join(rejected_ids[:50]) if rejected_ids else "(none)"

    context_block = ""
    if context_content.strip():
        context_block = (
            "Reference material (institutional knowledge, lessons learned, prior decisions "
            "— use these to ground your review in project-specific patterns and known issues):\n"
            "---\n"
            f"{context_content}\n"
            "---\n\n"
        )

    requirements_block = ""
    if requirements_content.strip():
        requirements_block = (
            "Feature Requirements (the plan under review is designed to implement these — "
            "evaluate whether the plan adequately addresses each requirement, flag gaps "
            "in traceability, and identify requirements that lack clear implementation steps):\n"
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
            requirements=requirements_block,
            has_feature_requirements=has_feature_requirements,
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
    focus_line = "- Focus on: architecture clarity, execution safety, risk management, validation completeness, and operational readiness."
    if substantially_addressed_areas:
        covered = set(substantially_addressed_areas.keys())
        uncovered = sorted(ALLOWED_AREAS - covered)
        addressed_lines = []
        for area in sorted(covered):
            ids = substantially_addressed_areas[area]
            addressed_lines.append(f"  - **{area}**: {len(ids)} suggestions applied ({', '.join(ids)})")
        total_applied = sum(len(v) for v in substantially_addressed_areas.values())

        if uncovered:
            # Tier 1: uncovered areas as explicit priorities with gap details
            iteration_context += (
                f"\n\n**Priority areas NOT yet substantially addressed — start your analysis here:**\n"
            )
            if area_coverage:
                # Show per-area gap details: count, existing IDs, how many more needed
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
            # Tier 2: covered areas (secondary)
            iteration_context += (
                f"\n\nAreas already substantially addressed — only propose if you find a genuine gap "
                f"the {total_applied} accepted suggestions missed:\n"
            )
            iteration_context += "\n".join(addressed_lines)
            # Dynamic focus line
            focus_line = (
                f"- Prioritize: {', '.join(uncovered)}. "
                f"Only revisit {', '.join(sorted(covered))} if you find a gap the "
                f"{total_applied} accepted suggestions missed."
            )
        else:
            # All areas substantially addressed — gap-hunting mode
            iteration_context += (
                f"\n\nAll {len(ALLOWED_AREAS)} review areas are substantially addressed "
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

    requirements_instruction = ""
    if requirements_block:
        if has_feature_requirements:
            requirements_instruction = (
                "- You MUST include a Requirements Coverage section mapping each feature "
                "requirement to plan steps. Flag any requirements that are under-addressed, "
                "missing implementation steps, or have unclear traceability.\n"
            )
        else:
            requirements_instruction = (
                "- Evaluate whether the plan adequately covers the feature requirements. "
                "Flag any requirements that are under-addressed, missing implementation steps, "
                "or have unclear traceability from requirement to implementation.\n"
            )

    dual_doc_format = ""
    if has_feature_requirements:
        dual_doc_format = (
            f"\n**Dual-Document Output — REQUIRED when feature requirements are provided:**\n\n"
            f"After your plan suggestion table, you MUST include TWO additional sections:\n\n"
            f"1. **Requirements Coverage** (MANDATORY):\n"
            f"   #### Requirements Coverage\n"
            f"   | Feature Doc Section | Plan Step(s) | Coverage | Gaps |\n"
            f"   | ---- | ---- | ---- | ---- |\n"
            f"   For each major requirement/section in the feature requirements document, map it to "
            f"the plan step(s) that implement it, assess coverage (Full / Partial / Missing), and "
            f"describe any gaps. This is your primary analytical tool — be thorough and specific.\n\n"
            f"2. **Feature Requirements Suggestions** (include if you find improvements needed):\n"
            f"   #### Feature Requirements Suggestions\n"
            f"   Same 7-column table schema as plan suggestions, but with IDs "
            f"R{round_number}-F1..R{round_number}-F{max_suggestions}.\n"
            f"   These target the feature requirements document itself — missing requirements, "
            f"ambiguous specs, under-specified acceptance criteria, or gaps discovered during "
            f"coverage analysis.\n\n"
        )

    return f"""You are an expert enterprise architect performing Review Round R{round_number} of an iterative architectural review.

This document undergoes multiple review passes. Each pass should be sharper than the last.

{iteration_context}

{requirements_block}{context_block}Your task:
- Propose up to {max_suggestions} high-leverage improvements not yet captured.
{focus_line}
{requirements_instruction}{context_instruction}- Do NOT rewrite the document. Do NOT modify Appendix A or Appendix B.
- You MUST output ONLY an appendable markdown snippet for Appendix C.

Required output format (append-only snippet):
- Start with:
  #### Review Round R{round_number}
- Then include:
  - **Reviewer**: {reviewer_label}
  - **Date**: {_now_utc()}
  - **Scope**: {scope}
- Then output a markdown table EXACTLY with these columns:
  | {cols} |
  | {sep} |
  Rows must use IDs R{round_number}-S1..R{round_number}-S{max_suggestions} (you may output fewer rows).
  Area must be one of: Architecture, Interfaces, Data, Risks, Validation, Ops, Security.
  Severity must be one of: critical, high, medium, low.
  IMPORTANT: If any cell content contains a pipe character (|), escape it as \\| to avoid breaking the table structure.
- After the table, if you agree with any untriaged suggestions from prior rounds (in Appendix C but NOT in Appendix A or B), add:
  **Endorsements** (prior untriaged suggestions this reviewer agrees with):
  - <ID>: <one-sentence reason you agree>
  This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage. Only endorse suggestions you genuinely believe should be implemented. Do NOT endorse your own suggestions.
{dual_doc_format}
Document (excluding the review appendix):
---
{document_without_appendix}
---
"""


def _validate_snippet(snippet: str, round_number: int, max_suggestions: int) -> Tuple[bool, str, List[str]]:
    """
    Validate agent output is a safe, append-only review-round block with required table schema.
    """
    if not snippet or not snippet.strip():
        return False, "Empty snippet", []

    if f"#### Review Round R{round_number}" not in snippet:
        return False, f"Missing required heading: '#### Review Round R{round_number}'", []

    # Disallow attempts to edit other appendices
    for forbidden in ("### Appendix A", "### Appendix B"):
        if forbidden in snippet:
            return False, f"Snippet appears to modify {forbidden}; only Appendix C additions are allowed", []

    # Find the first markdown table and validate header
    lines = [ln.rstrip() for ln in snippet.strip().splitlines() if ln.strip()]
    table_start = None
    for idx, ln in enumerate(lines):
        if ln.strip().startswith("|") and "ID" in ln:
            table_start = idx
            break
    if table_start is None or table_start + 1 >= len(lines):
        return False, "Missing required markdown table", []

    header = _split_cells(lines[table_start])
    if header != REQUIRED_COLUMNS:
        return False, f"Table header mismatch. Expected columns: {REQUIRED_COLUMNS}", []

    # Require separator row after header
    sep = lines[table_start + 1]
    if not sep.strip().startswith("|"):
        return False, "Missing table separator row", []

    # Extract IDs and validate enums from rows
    ids: List[str] = []
    for ln in lines[table_start + 2 :]:
        if not ln.strip().startswith("|"):
            break
        cells = _split_cells(ln)
        if len(cells) != len(REQUIRED_COLUMNS):
            return False, "Table row has wrong column count", ids

        suggestion_id = cells[0]
        ids.append(suggestion_id)

        # Validate ID pattern (S-prefix for plan suggestions)
        if not re.fullmatch(rf"R{round_number}-S\d+", suggestion_id):
            return False, f"Invalid suggestion ID '{suggestion_id}' for round R{round_number}", ids

        # Validate area and severity values
        area = cells[1].strip().lower()
        severity = cells[2].strip().lower()
        if area not in ALLOWED_AREAS:
            return False, f"Invalid Area '{cells[1]}' (allowed: {sorted(ALLOWED_AREAS)})", ids
        if severity not in ALLOWED_SEVERITIES:
            return False, f"Invalid Severity '{cells[2]}' (allowed: {sorted(ALLOWED_SEVERITIES)})", ids

    unique_ids = sorted(set(ids), key=lambda x: int(m.group(1)) if (m := re.search(r"-S(\d+)$", x)) else 9999)
    if not unique_ids:
        return False, "No suggestion rows found in table", []
    if len(unique_ids) > max_suggestions:
        return False, f"Too many suggestions: {len(unique_ids)} > {max_suggestions}", unique_ids

    # Validate feature suggestions table (F-prefix IDs) if present
    feature_ids: List[str] = []
    feat_idx = None
    for idx, ln in enumerate(lines):
        if "Feature Requirements Suggestions" in ln:
            feat_idx = idx
            break
    if feat_idx is not None:
        for ln in lines[feat_idx + 1:]:
            if not ln.strip().startswith("|"):
                if feature_ids:  # past the table
                    break
                continue
            cells = _split_cells(ln)
            if len(cells) < 7 or cells[0] == "ID" or cells[0].startswith("-"):
                continue
            fid = cells[0]
            if re.fullmatch(rf"R{round_number}-F\d+", fid):
                feature_ids.append(fid)

    all_ids = unique_ids + feature_ids
    return True, "ok", all_ids


@dataclass
class _RoundRecord:
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
                    name="feature_requirements",
                    type="array",
                    required=False,
                    description=(
                        "List of file or directory paths containing feature requirements "
                        "that the plan under review is designed to implement. "
                        "Reviewers will evaluate plan-to-requirements traceability and coverage gaps. "
                        "Directories are scanned recursively for .md files."
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
                    name="substantially_addressed_threshold",
                    type="number",
                    required=False,
                    default=3,
                    description="Minimum accepted suggestions per area to mark it as 'substantially addressed'",
                ),
                WorkflowInput(
                    name="llm_read_timeout_seconds",
                    type="number",
                    required=False,
                    default=90,
                    description="Fast-fail read timeout for reviewer LLM calls",
                ),
                WorkflowInput(
                    name="llm_max_attempts",
                    type="number",
                    required=False,
                    default=1,
                    description="Retry attempts for reviewer LLM calls (1 = fail fast)",
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

        llm_read_timeout_seconds = config.get("llm_read_timeout_seconds", 90)
        try:
            timeout_val = float(llm_read_timeout_seconds)
            if timeout_val <= 0:
                errors.append("llm_read_timeout_seconds must be > 0")
        except (TypeError, ValueError):
            errors.append("llm_read_timeout_seconds must be a positive number")

        llm_max_attempts = config.get("llm_max_attempts", 1)
        try:
            attempts_val = int(llm_max_attempts)
            if attempts_val < 1:
                errors.append("llm_max_attempts must be >= 1")
        except (TypeError, ValueError):
            errors.append("llm_max_attempts must be an integer >= 1")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        started_at = datetime.now(timezone.utc)

        doc_path = Path(str(config["document_path"])).expanduser().resolve()
        init_if_missing = bool(config.get("init_if_missing", True))
        max_suggestions = int(config.get("max_suggestions", 10))
        scope = str(config.get("scope") or "").strip() or "Architecture-focused review"

        warn_cost_usd = config.get("warn_cost_usd")
        max_cost_usd = config.get("max_cost_usd")
        fallback_openai_model = str(config.get("fallback_openai_model") or "openai:gpt-4.1").strip()
        fallback_on_model_not_found = bool(config.get("fallback_on_model_not_found", True))
        llm_read_timeout_seconds = float(config.get("llm_read_timeout_seconds", 90))
        llm_max_attempts = int(config.get("llm_max_attempts", 1))
        llm_timeout_config = TimeoutConfig(read=llm_read_timeout_seconds)
        llm_retry_config = RetryConfig(max_attempts=llm_max_attempts)

        default_state_path = doc_path.parent / ".startd8" / "architectural_review_state.json"
        state_path = Path(config.get("state_path") or default_state_path).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = doc_path.parent / ".startd8" / "architectural_review.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Resolve agents: explicit list in config OR provided agents param OR default selection
        resolved_agents: List[BaseAgent] = []
        explicit_specs = config.get("agents") or []
        if agents:
            resolved_agents = agents
        elif explicit_specs:
            resolved_agents = resolve_agents(
                explicit_specs,
                timeout_config=llm_timeout_config,
                retry_config=llm_retry_config,
            )
        else:
            quality_tier = str(config.get("quality_tier") or "flagship")
            providers = config.get("providers")
            reviewer_count = int(config.get("reviewer_count", 2))  # matches default in metadata
            default_specs = _select_default_agents(quality_tier, reviewer_count, providers)
            resolved_agents = resolve_agents(
                default_specs,
                timeout_config=llm_timeout_config,
                retry_config=llm_retry_config,
            )

        if not resolved_agents:
            return WorkflowResult.from_error(self.metadata.workflow_id, "No agents available for architectural review")

        # Apply caller-provided Gemini safety_settings to all Gemini agents
        gemini_safety = config.get("gemini_safety_settings")
        if gemini_safety:
            for ag in resolved_agents:
                if _is_gemini_agent(ag) and hasattr(ag, "safety_settings"):
                    ag.safety_settings = gemini_safety

        step_results: List[StepResult] = []
        round_records: List[_RoundRecord] = []

        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        total_time_ms = 0

        with FileLock(lock_path):
            doc_text = doc_path.read_text(encoding="utf-8")
            if init_if_missing:
                doc_text = _ensure_appendix_exists(doc_text)

            # Resolve feature doc path for dual-document mode
            feature_doc_path: Optional[Path] = None
            feature_doc_text: Optional[str] = None
            has_feature_doc = False
            feature_requirements_list = config.get("feature_requirements") or []
            if feature_requirements_list:
                feature_doc_path = _get_feature_doc_path(feature_requirements_list)
                if feature_doc_path and feature_doc_path.exists():
                    feature_doc_text = feature_doc_path.read_text(encoding="utf-8")
                    if init_if_missing:
                        feature_doc_text = _ensure_appendix_exists(feature_doc_text)
                        atomic_write(feature_doc_path, feature_doc_text, mode="w", backup=True)
                    has_feature_doc = True

            applied_ids = _extract_table_ids(doc_text, "### Appendix A: Applied Suggestions")
            rejected_ids = _extract_table_ids(doc_text, "### Appendix B: Rejected Suggestions (with Rationale)")
            next_round = _max_review_round(doc_text) + 1

            total_rounds = len(resolved_agents)
            self._emit_progress(on_progress, 0, total_rounds, f"Starting {total_rounds} architectural review round(s)")

            template_override = config.get("review_template")

            max_context_chars = int(config.get("max_context_chars", 200_000))

            # Load context files (lessons learned, design docs, prior decisions)
            context_files = config.get("context_files") or []
            context_content = ""
            if context_files:
                parts: List[str] = []
                for cf in context_files:
                    p = Path(str(cf)).expanduser().resolve()
                    if p.is_file():
                        try:
                            parts.append(f"### {p.name}\n\n{p.read_text(encoding='utf-8')}")
                        except Exception:
                            pass
                    elif p.is_dir():
                        for md_file in sorted(p.glob("**/*.md")):
                            try:
                                parts.append(
                                    f"### {md_file.relative_to(p)}\n\n"
                                    f"{md_file.read_text(encoding='utf-8')}"
                                )
                            except Exception:
                                pass
                context_content = "\n\n".join(parts)
                if len(context_content) > max_context_chars:
                    context_content = context_content[:max_context_chars] + "\n\n[... truncated ...]"

            # Load feature requirements (documents the plan is designed to implement)
            feature_requirements = config.get("feature_requirements") or []
            requirements_content = ""
            if feature_requirements:
                req_parts: List[str] = []
                for cf in feature_requirements:
                    p = Path(str(cf)).expanduser().resolve()
                    if p.is_file():
                        try:
                            req_parts.append(f"### {p.name}\n\n{p.read_text(encoding='utf-8')}")
                        except Exception:
                            pass
                    elif p.is_dir():
                        for md_file in sorted(p.glob("**/*.md")):
                            try:
                                req_parts.append(
                                    f"### {md_file.relative_to(p)}\n\n"
                                    f"{md_file.read_text(encoding='utf-8')}"
                                )
                            except Exception:
                                pass
                requirements_content = "\n\n".join(req_parts)
                if len(requirements_content) > max_context_chars:
                    requirements_content = requirements_content[:max_context_chars] + "\n\n[... truncated ...]"

            # Compute substantially addressed areas and per-area coverage from existing Appendix A
            sa_threshold = int(config.get("substantially_addressed_threshold", 3))
            substantially_addressed = _compute_substantially_addressed_from_doc(doc_text, sa_threshold)
            coverage = _compute_area_coverage(doc_text, sa_threshold)

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
                    requirements_content=requirements_content,
                    substantially_addressed_areas=substantially_addressed,
                    area_coverage=coverage,
                    has_feature_requirements=has_feature_doc,
                )

                # Execute generation with graceful error handling, Gemini SAFETY
                # retry, and OpenAI model fallback.
                try:
                    response_text, time_ms, token_usage = agent.generate(prompt)

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
                        requirements_content="",  # drop on safety retry
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
                            step_results.append(
                                StepResult(
                                    step_name=step_name,
                                    agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                                    output="",
                                    time_ms=0,
                                    input_tokens=0,
                                    output_tokens=0,
                                    cost=0.0,
                                    error=f"Gemini SAFETY filter (skipped): {e3}",
                                )
                            )
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
                            fallback_agent = resolve_agents(
                                [fallback_openai_model],
                                timeout_config=llm_timeout_config,
                                retry_config=llm_retry_config,
                            )[0]
                            response_text, time_ms, token_usage = fallback_agent.generate(prompt)
                            agent = fallback_agent  # record agent/model that actually ran
                        except Exception as e2:
                            step_results.append(
                                StepResult(
                                    step_name=step_name,
                                    agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                                    output="",
                                    time_ms=0,
                                    input_tokens=0,
                                    output_tokens=0,
                                    cost=0.0,
                                    error=str(e2),
                                )
                            )
                            break
                    else:
                        step_results.append(
                            StepResult(
                                step_name=step_name,
                                agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                                output="",
                                time_ms=0,
                                input_tokens=0,
                                output_tokens=0,
                                cost=0.0,
                                error=str(e),
                            )
                        )
                        break

                input_tokens = token_usage_input(token_usage) if token_usage else 0
                output_tokens = token_usage_output(token_usage) if token_usage else 0
                cost = token_usage_cost(token_usage) if token_usage else 0.0

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_cost += cost
                total_time_ms += time_ms

                if warn_cost_usd is not None and total_cost >= float(warn_cost_usd):
                    self._emit_progress(
                        on_progress,
                        i,
                        total_rounds,
                        f"Cost warning: cumulative ${total_cost:.2f} >= warn_cost_usd=${float(warn_cost_usd):.2f}",
                    )

                if max_cost_usd is not None and total_cost >= float(max_cost_usd):
                    step_results.append(
                        StepResult(
                            step_name=step_name,
                            agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                            output="",
                            time_ms=time_ms,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=cost,
                            error=f"Max cost exceeded: ${total_cost:.2f} >= max_cost_usd=${float(max_cost_usd):.2f}",
                        )
                    )
                    break

                # Strip code-block fences (Gemini sometimes wraps output)
                response_text = _strip_code_fences(response_text)

                ok, message, ids = _validate_snippet(response_text, round_number, max_suggestions)
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
                        f"- Table columns EXACTLY: {' | '.join(REQUIRED_COLUMNS)}\n"
                        f"- IDs: R{round_number}-S1, R{round_number}-S2, etc.\n"
                        f"- Area must be one of: {', '.join(sorted(ALLOWED_AREAS))}\n"
                        f"- Severity must be one of: {', '.join(sorted(ALLOWED_SEVERITIES))}\n"
                        f"- If cell content contains a pipe character (|), escape it as \\| to avoid breaking the table\n"
                        f"- Do NOT wrap output in code blocks (no ```)\n\n"
                        f"Original prompt:\n{prompt}"
                    )
                    self._emit_progress(
                        on_progress, i, total_rounds,
                        f"R{round_number}: validation failed ({message}); retrying",
                    )
                    try:
                        retry_text, retry_time_ms, retry_token_usage = agent.generate(retry_prompt)
                        retry_text = _strip_code_fences(retry_text)
                        retry_input = token_usage_input(retry_token_usage) if retry_token_usage else 0
                        retry_output = token_usage_output(retry_token_usage) if retry_token_usage else 0
                        retry_cost = token_usage_cost(retry_token_usage) if retry_token_usage else 0.0
                        total_input_tokens += retry_input
                        total_output_tokens += retry_output
                        total_cost += retry_cost
                        total_time_ms += retry_time_ms

                        ok2, message2, ids = _validate_snippet(retry_text, round_number, max_suggestions)
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
                            step_results.append(
                                StepResult(
                                    step_name=step_name,
                                    agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                                    output=retry_text[:500] + "..." if len(retry_text) > 500 else retry_text,
                                    time_ms=time_ms + retry_time_ms,
                                    input_tokens=input_tokens + retry_input,
                                    output_tokens=output_tokens + retry_output,
                                    cost=cost + retry_cost,
                                    error=f"Invalid snippet after retry: {message2}",
                                )
                            )
                            continue  # skip reviewer, let remaining reviewers run
                    except Exception as retry_err:
                        _logger.warning(
                            "Validation retry call failed for R%d (%s): %s; skipping reviewer",
                            round_number,
                            reviewer_label,
                            retry_err,
                        )
                        step_results.append(
                            StepResult(
                                step_name=step_name,
                                agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                                output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                                time_ms=time_ms,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                cost=cost,
                                error=f"Validation retry failed: {retry_err}",
                            )
                        )
                        continue  # skip reviewer, let remaining reviewers run

                # Append snippet and persist
                doc_text = doc_text.rstrip() + "\n\n" + response_text.strip() + "\n"
                atomic_write(doc_path, doc_text, mode="w", backup=True)

                # Dual-document: extract feature suggestions and append to feature doc
                if has_feature_doc and feature_doc_text is not None:
                    feature_snippet = _extract_feature_snippet(
                        response_text, round_number, reviewer_label, scope,
                    )
                    if feature_snippet:
                        feature_doc_text = feature_doc_text.rstrip() + "\n\n" + feature_snippet + "\n"
                        atomic_write(feature_doc_path, feature_doc_text, mode="w", backup=True)

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

                step_results.append(
                    StepResult(
                        step_name=step_name,
                        agent_name=f"{agent.name}:{getattr(agent, 'model', '')}",
                        output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                        time_ms=time_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                        error=None,
                    )
                )

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
                        "cumulative_cost_usd": total_cost,
                    }
                    atomic_write_json(state_path, state, indent=2, sort_keys=False)
                except Exception:
                    pass

                self._emit_progress(on_progress, i + 1, total_rounds, f"Appended Round R{round_number}")

            # ── Automated Triage Step ──────────────────────────────────────
            enable_triage = bool(config.get("enable_triage", True))
            triage_info: Dict[str, Any] = {
                "enabled": enable_triage,
                "accepted": 0,
                "rejected": 0,
                "untriaged_remaining": [],
                "substantially_addressed_areas": [],
                "areas_needing_review": [],
                "feature_accepted": 0,
                "feature_rejected": 0,
                "feature_document_path": str(feature_doc_path) if feature_doc_path else None,
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

                    has_feature_suggestions = any("-F" in s["id"] for s in untriaged)
                    triage_prompt = _build_triage_prompt(
                        document_without_appendix=_strip_appendix_for_prompt(doc_text),
                        applied_ids=applied_ids,
                        rejected_ids=rejected_ids,
                        untriaged_block=untriaged_block,
                        endorsement_counts=endorsements,
                        has_feature_suggestions=has_feature_suggestions,
                    )

                    # Execute triage with same error handling pattern
                    triage_ok = False
                    triage_decisions: List[Dict[str, Any]] = []
                    triage_missing: List[str] = []

                    try:
                        triage_text, triage_time_ms, triage_token_usage = triage_agent.generate(triage_prompt)
                    except GeminiSafetyFilterError:
                        _logger.warning("Triage blocked by Gemini SAFETY filter; retrying with relaxed settings")
                        original_safety = getattr(triage_agent, "safety_settings", None)
                        try:
                            if _is_gemini_agent(triage_agent):
                                triage_agent.safety_settings = RELAXED_SAFETY_SETTINGS
                            triage_text, triage_time_ms, triage_token_usage = triage_agent.generate(triage_prompt)
                        except Exception as triage_err:
                            _logger.warning("Triage failed after retry: %s", triage_err)
                            step_results.append(StepResult(
                                step_name="triage",
                                agent_name=f"{triage_agent.name}:{getattr(triage_agent, 'model', '')}",
                                output="",
                                time_ms=0,
                                input_tokens=0,
                                output_tokens=0,
                                cost=0.0,
                                error=f"Triage failed: {triage_err}",
                            ))
                            triage_text = None
                            triage_time_ms = 0
                            triage_token_usage = None
                        finally:
                            if _is_gemini_agent(triage_agent):
                                triage_agent.safety_settings = original_safety
                    except Exception as triage_err:
                        _logger.warning("Triage failed: %s", triage_err)
                        step_results.append(StepResult(
                            step_name="triage",
                            agent_name=f"{triage_agent.name}:{getattr(triage_agent, 'model', '')}",
                            output="",
                            time_ms=0,
                            input_tokens=0,
                            output_tokens=0,
                            cost=0.0,
                            error=f"Triage failed: {triage_err}",
                        ))
                        triage_text = None
                        triage_time_ms = 0
                        triage_token_usage = None

                    if triage_text is not None:
                        triage_input_tokens = token_usage_input(triage_token_usage) if triage_token_usage else 0
                        triage_output_tokens = token_usage_output(triage_token_usage) if triage_token_usage else 0
                        triage_cost = token_usage_cost(triage_token_usage) if triage_token_usage else 0.0

                        total_input_tokens += triage_input_tokens
                        total_output_tokens += triage_output_tokens
                        total_cost += triage_cost
                        total_time_ms += triage_time_ms

                        triage_ok, triage_msg, triage_decisions, triage_missing = _validate_triage_output(
                            triage_text, untriaged_ids
                        )

                        if not triage_ok:
                            _logger.warning("Triage validation failed: %s", triage_msg)
                            # Try one retry with targeted re-prompt
                            retry_prompt = (
                                f"Your previous triage response failed validation: {triage_msg}\n\n"
                                f"Please output ONLY a JSON array with entries for each suggestion. "
                                f"Required fields: id, decision (ACCEPT or REJECT), summary, rationale, "
                                f"area (one of: {', '.join(sorted(ALLOWED_AREAS))}).\n\n"
                                f"Suggestions to triage:\n{untriaged_block}"
                            )
                            try:
                                retry_text, retry_time_ms, retry_token_usage = triage_agent.generate(retry_prompt)
                                retry_input = token_usage_input(retry_token_usage) if retry_token_usage else 0
                                retry_output = token_usage_output(retry_token_usage) if retry_token_usage else 0
                                retry_cost = token_usage_cost(retry_token_usage) if retry_token_usage else 0.0
                                total_input_tokens += retry_input
                                total_output_tokens += retry_output
                                total_cost += retry_cost
                                total_time_ms += retry_time_ms
                                triage_input_tokens += retry_input
                                triage_output_tokens += retry_output
                                triage_cost += retry_cost
                                triage_time_ms += retry_time_ms

                                triage_ok, triage_msg, triage_decisions, triage_missing = _validate_triage_output(
                                    retry_text, untriaged_ids
                                )
                                if not triage_ok:
                                    _logger.warning("Triage retry also failed: %s", triage_msg)
                            except Exception as retry_err:
                                _logger.warning("Triage retry call failed: %s", retry_err)

                        if triage_decisions:
                            # Split decisions by target document
                            plan_decisions = [d for d in triage_decisions if "-S" in d["id"]]
                            feature_decisions = [d for d in triage_decisions if "-F" in d["id"]]

                            # Apply plan decisions to plan doc
                            if plan_decisions:
                                doc_text = _apply_triage_decisions(doc_text, plan_decisions, reviewer_sources)

                            # Apply feature decisions to feature doc
                            if feature_decisions and has_feature_doc and feature_doc_text is not None:
                                feature_doc_text = _apply_triage_decisions(
                                    feature_doc_text, feature_decisions, reviewer_sources,
                                )
                                atomic_write(feature_doc_path, feature_doc_text, mode="w", backup=True)

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
                            post_triage_coverage = _compute_area_coverage(doc_text, sa_threshold)
                            doc_text = _insert_areas_needing_review_section(doc_text, post_triage_coverage, sa_threshold)
                            areas_needing = [
                                area for area, info in post_triage_coverage.items()
                                if not info["addressed"]
                            ]
                            triage_info["areas_needing_review"] = sorted(areas_needing)

                            # Persist document
                            atomic_write(doc_path, doc_text, mode="w", backup=True)

                            accepted_count = sum(1 for d in triage_decisions if d["decision"] == "ACCEPT")
                            rejected_count = sum(1 for d in triage_decisions if d["decision"] == "REJECT")
                            triage_info["accepted"] = accepted_count
                            triage_info["rejected"] = rejected_count
                            triage_info["untriaged_remaining"] = triage_missing

                            # Update feature doc triage info
                            if feature_decisions:
                                feat_accepted = sum(1 for d in feature_decisions if d["decision"] == "ACCEPT")
                                feat_rejected = sum(1 for d in feature_decisions if d["decision"] == "REJECT")
                                triage_info["feature_accepted"] = feat_accepted
                                triage_info["feature_rejected"] = feat_rejected

                        step_results.append(StepResult(
                            step_name="triage",
                            agent_name=f"{triage_agent.name}:{getattr(triage_agent, 'model', '')}",
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

                    # Update state file with triage info
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
                            "cumulative_cost_usd": total_cost,
                            "triage": triage_info,
                        }
                        atomic_write_json(state_path, state, indent=2, sort_keys=False)
                    except Exception:
                        pass

        completed_at = datetime.now(timezone.utc)
        success = bool(round_records) and all(s.error is None for s in step_results if s.step_name != "triage")

        metrics = WorkflowMetrics(
            total_time_ms=total_time_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_cost=total_cost,
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
                "cumulative_cost_usd": total_cost,
                "triage": triage_info,
            },
            metrics=metrics,
            steps=step_results,
            error=None if success else "Architectural review did not complete successfully; see steps for details",
            started_at=started_at,
            completed_at=completed_at,
        )

