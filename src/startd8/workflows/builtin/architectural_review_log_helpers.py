"""Validation, table parsing, document mutation, and feature-doc helpers for the architectural review workflow.

Depends on :mod:`architectural_review_log_constants` and
:mod:`architectural_review_log_prompts`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ...agents import BaseAgent
from ...logging_config import get_logger
from .architectural_review_log_constants import (
    ALLOWED_AREAS,
    ALLOWED_SEVERITIES,
    APPENDIX_HEADING,
    CORE_COLUMNS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    _COLUMN_ALIAS_MAP,
    _OPTIONAL_COLUMN_DEFAULT,
    _extract_token_metrics,
    _is_separator_row,
    _normalize_area,
    _normalize_header,
    _now_utc,
    _split_cells,
    _strip_appendix_for_prompt,
    _strip_code_fences,
    _strip_json_fences,
)
from .architectural_review_log_prompts import _build_apply_prompt

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------

def _max_review_round(doc: str) -> int:
    """Return the highest review round number found in the document, or 0."""
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
        ``placement`` and ``validation`` default to :data:`_OPTIONAL_COLUMN_DEFAULT`
        when the corresponding optional columns are absent from the source table.
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

        # Extract table rows using header-aware column index map so
        # reordered columns are handled correctly (mirrors _validate_snippet).
        lines = block.splitlines()
        in_table = False
        col_idx: Dict[str, int] = {}
        for line in lines:
            stripped = line.strip()
            if not in_table and stripped.startswith("| ID"):
                header_cells = [_normalize_header(h).casefold() for h in _split_cells(stripped)]
                col_idx = {name: idx for idx, name in enumerate(header_cells)}
                in_table = True
                continue

            if in_table:
                if _is_separator_row(stripped):
                    continue

                if stripped.startswith("|"):
                    cells = _split_cells(stripped)
                    if len(cells) >= len(CORE_COLUMNS):
                        try:
                            sid = cells[col_idx["id"]]
                        except (KeyError, IndexError):
                            continue
                        if sid in triaged or sid.startswith("("):
                            continue
                        suggestions.append({
                            "id": sid,
                            "area": _normalize_area(cells[col_idx.get("area", 1)]),
                            "severity": cells[col_idx.get("severity", 2)],
                            "suggestion": cells[col_idx.get("suggestion", 3)],
                            "rationale": cells[col_idx.get("rationale", 4)],
                            "placement": (
                                cells[col_idx["proposed placement"]]
                                if "proposed placement" in col_idx
                                   and col_idx["proposed placement"] < len(cells)
                                else _OPTIONAL_COLUMN_DEFAULT
                            ),
                            "validation": (
                                cells[col_idx["validation approach"]]
                                if "validation approach" in col_idx
                                   and col_idx["validation approach"] < len(cells)
                                else _OPTIONAL_COLUMN_DEFAULT
                            ),
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


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

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
        if ln.strip().startswith("|") and re.search(r'\bID\b|^\|\s*#\s*\|', ln, re.IGNORECASE):
            # Possible table header
            if i + 1 >= len(lines):
                break
            sep = lines[i+1]
            if not sep.strip().startswith("|") or "-" not in sep:
                i += 1
                continue

            # Found table
            tables_found += 1
            raw_header = _split_cells(ln)
            # Normalize header cells: strip markdown bold/italic and casefold
            # so **Area**, "area", "AREA" all match the required column name.
            header = [_normalize_header(h) for h in raw_header]
            header_cf = [h.casefold() for h in header]
            # Resolve LLM synonyms to canonical column names via alias map.
            # e.g. "recommendation" → "suggestion", "reasoning" → "rationale"
            header_cf = [_COLUMN_ALIAS_MAP.get(h, h) for h in header_cf]
            # Leniency: Accept header if it has the required columns, even if extra or slightly different order
            header_cf_set = set(header_cf)
            # Only enforce CORE_COLUMNS; OPTIONAL_COLUMNS get defaults when missing
            missing_core = [col for col in CORE_COLUMNS if col.casefold() not in header_cf_set]
            if missing_core:
                return False, f"Table header mismatch. Missing columns: {missing_core}", []

            missing_optional = [col for col in OPTIONAL_COLUMNS if col.casefold() not in header_cf_set]
            if missing_optional:
                _logger.info(
                    "Table missing optional columns %s — will default to '%s'",
                    missing_optional,
                    _OPTIONAL_COLUMN_DEFAULT,
                )

            # Build case-insensitive column index map for row extraction
            col_idx = {name.casefold(): idx for idx, name in enumerate(header_cf)}

            i += 2 # Skip header and sep

            # Parse rows
            while i < len(lines):
                row = lines[i]
                if not row.strip().startswith("|"):
                    break # End of table

                cells = _split_cells(row)
                # Leniency: Require at least CORE_COLUMNS cells; allow fewer than full REQUIRED_COLUMNS
                if len(cells) < len(CORE_COLUMNS):
                    _logger.debug("Skipping row with insufficient columns: %s", row)
                    i += 1
                    continue

                # Extract values by mapping column names to indices (case-insensitive)
                try:
                    sid = cells[col_idx["id"]]
                    area = cells[col_idx["area"]].strip().lower()
                    severity = cells[col_idx["severity"]].strip().lower()
                except (ValueError, KeyError, IndexError):
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

    unique_ids = sorted(set(ids), key=sort_key)

    if not unique_ids:
        # Leniency: It's technically okay to have no suggestions if the review found nothing
        return True, "No suggestions found (which is valid)", []

    # Check max suggestions for PLAN suggestions (S-prefix)
    s_ids = [x for x in unique_ids if "-S" in x]
    if len(s_ids) > max_suggestions:
        return False, f"Too many plan suggestions: {len(s_ids)} > {max_suggestions}", unique_ids

    return True, "ok", unique_ids


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
            area = _normalize_area(entry["area"], areas)

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
                errors.append(f"Entry {i}: area '{entry['area']}' not recognized (allowed: {sorted(areas)})")
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


# ---------------------------------------------------------------------------
# Document mutation
# ---------------------------------------------------------------------------

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

    new_rows = "".join(
        f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |\n"
        for r in rows
    )

    # Check for (none yet) placeholder in the last table line
    last_table_line = lines[table_end_idx]
    if "(none yet)" in last_table_line:
        lines[table_end_idx] = new_rows
    else:
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


def _build_id_to_area_map(
    doc: str,
    allowed_areas: Optional[Set[str]] = None,
) -> Dict[str, str]:
    """Parse Appendix C to build a mapping of suggestion ID -> normalized area name."""
    id_to_area: Dict[str, str] = {}
    appendix_c_match = re.search(
        r"^### Appendix C: Incoming Suggestions.*$",
        doc,
        re.MULTILINE,
    )
    if appendix_c_match:
        appendix_c_text = doc[appendix_c_match.end():]
        in_table = False
        for line in appendix_c_text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                in_table = False
                continue
            # Skip header rows (contain "ID" in first cell) and separator rows
            if _is_separator_row(stripped):
                continue
            first_cell = _split_cells(stripped)[0] if _split_cells(stripped) else ""
            if _normalize_header(first_cell).casefold() == "id":
                in_table = True
                continue
            if in_table:
                cells = _split_cells(stripped)
                if len(cells) >= 2 and re.match(r"R\d+-S\d+", cells[0]):
                    id_to_area[cells[0]] = _normalize_area(cells[1], allowed_areas)
    return id_to_area


def _compute_substantially_addressed_from_doc(
    doc: str,
    threshold: int,
    allowed_areas: Optional[Set[str]] = None,
) -> Dict[str, List[str]]:
    """
    Extract applied suggestions from Appendix A and compute substantially addressed areas.
    Parses the Area from Appendix C for each applied ID.
    """
    applied_ids = _extract_table_ids(doc, "### Appendix A: Applied Suggestions")
    if not applied_ids:
        return {}

    id_to_area = _build_id_to_area_map(doc, allowed_areas)
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

    id_to_area = _build_id_to_area_map(doc, areas)

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


# ---------------------------------------------------------------------------
# Apply / extract helpers
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

    Raises:
        Exception: Propagates any exception from ``agent.generate()``
            (e.g., API errors, safety filter errors).
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
    input_tokens, output_tokens, cost = _extract_token_metrics(token_usage)

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
# Feature doc helpers
# ---------------------------------------------------------------------------

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

    parts = response_text.split(marker, maxsplit=1)
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
