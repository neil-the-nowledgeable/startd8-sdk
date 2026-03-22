"""Extract structured sections from plan documents (REQ-SU-500).

Deterministic regex extraction of Risk Register and Verification
sections from plan markdown. No LLM calls.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Section header patterns (case-insensitive, ## or ### level)
_RISK_HEADERS = re.compile(
    r"^#{2,3}\s+(?:Risk(?:s|\s+Register)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_VERIFICATION_HEADERS = re.compile(
    r"^#{2,3}\s+(?:Verification|Test\s+Plan|Acceptance\s+Criteria|Test\s+Strategy)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Next same-or-higher-level header stops the section
_NEXT_HEADER = re.compile(r"^#{2,3}\s+", re.MULTILINE)


def _extract_section(text: str, pattern: re.Pattern) -> Optional[str]:
    """Extract content between a matching header and the next header."""
    match = pattern.search(text)
    if not match:
        return None
    start = match.end()
    # Find next ## or ### header after the matched one
    next_hdr = _NEXT_HEADER.search(text, start)
    end = next_hdr.start() if next_hdr else len(text)
    content = text[start:end].strip()
    return content if content else None


def _parse_risk_entries(text: str) -> List[Dict[str, str]]:
    """Parse risk register content into structured entries.

    Handles both markdown table rows and bullet-point format.
    """
    entries: List[Dict[str, str]] = []

    # Try table format: | Risk | Mitigation | ...
    table_row = re.compile(
        r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|",
        re.MULTILINE,
    )
    for m in table_row.finditer(text):
        risk, mitigation = m.group(1).strip(), m.group(2).strip()
        # Skip separator rows (|---|---|) and header rows
        if risk.startswith("-") or risk.lower() in ("risk", "issue", "concern"):
            continue
        entries.append({"risk": risk, "mitigation": mitigation})

    if entries:
        return entries

    # Fallback: bullet format (- Risk: ... — Mitigation on same line)
    bullet = re.compile(
        r"^[-*]\s+(.+?)(?:[^\S\n]+[-–—][^\S\n]+(.+))?$",
        re.MULTILINE,
    )
    for m in bullet.finditer(text):
        risk = m.group(1).strip()
        mitigation = (m.group(2) or "").strip()
        if risk:
            entries.append({"risk": risk, "mitigation": mitigation})

    return entries


def _parse_verification_entries(text: str) -> List[str]:
    """Parse verification criteria into a list of strings."""
    entries: List[str] = []

    # Bullet points
    for m in re.finditer(r"^[-*]\s+(.+)$", text, re.MULTILINE):
        entry = m.group(1).strip()
        if entry:
            entries.append(entry)

    if entries:
        return entries

    # Numbered list
    for m in re.finditer(r"^\d+[.)]\s+(.+)$", text, re.MULTILINE):
        entry = m.group(1).strip()
        if entry:
            entries.append(entry)

    # Fallback: non-empty lines
    if not entries:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                entries.append(line)

    return entries


def extract_plan_sections(plan_text: str) -> Dict[str, Any]:
    """Extract risk register and verification criteria from plan markdown.

    Args:
        plan_text: Raw markdown text of the plan document.

    Returns:
        Dict with ``plan_risk_register`` (list of dicts or None) and
        ``plan_verification_criteria`` (list of strings or None).
    """
    if not plan_text or not plan_text.strip():
        return {
            "plan_risk_register": None,
            "plan_verification_criteria": None,
        }

    risk_text = _extract_section(plan_text, _RISK_HEADERS)
    verification_text = _extract_section(plan_text, _VERIFICATION_HEADERS)

    risk_entries = _parse_risk_entries(risk_text) if risk_text else []
    verification_entries = (
        _parse_verification_entries(verification_text) if verification_text else []
    )

    return {
        "plan_risk_register": risk_entries or None,
        "plan_verification_criteria": verification_entries or None,
    }
