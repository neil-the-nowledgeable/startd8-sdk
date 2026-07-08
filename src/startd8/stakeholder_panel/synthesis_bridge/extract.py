# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Heuristic ($0) extraction of discrete items from a synthesis markdown (FR-2, increment 1).

The facilitation synthesis is well-structured markdown with `## ` sections. This parses the sections
that carry *decidable-ish* items — Recommendations, Open Questions, Risk Register, Tensions — into
:class:`Candidate` rows. No LLM: deterministic and re-runnable.

An LLM extractor (OQ-9) that maps prose to concrete ``entity.field`` value_paths is a later,
*paid* enhancement (increment 2) — this heuristic core always fires and costs nothing. Sections not
listed here (Adversary Findings, Assumptions At Risk) are intentionally skipped as background, not
actionable items; add them to ``_SECTION_OWNERS`` if that changes.
"""

from __future__ import annotations

import re
from typing import List

from .models import Candidate

# Section header -> the label we tag candidates with. Matched case-insensitively on a `## ` heading;
# a heading merely has to *start with* one of these (e.g. "Open Questions for the Human").
_SECTION_PREFIXES = {
    "recommendation": "Recommendations",
    "open question": "Open Questions",
    "risk register": "Risk Register",
    "tension": "Tensions",
}

_HEADING_RE = re.compile(r"^#{1,4}\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")


def _section_for(heading: str) -> str:
    h = heading.strip().lower()
    for prefix, label in _SECTION_PREFIXES.items():
        if h.startswith(prefix) or prefix in h:
            return label
    return ""


def _clean(text: str) -> str:
    """Strip markdown emphasis/backticks and collapse whitespace to a single bounded line."""
    text = re.sub(r"[*_`>]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_of(text: str) -> str:
    """A short label: the leading bold/colon-delimited head, else the first ~80 chars."""
    # "**Domain scope:** rest" or "Build the immutable X — ..." → the head clause.
    head = re.split(r"[:—.]", text, maxsplit=1)[0]
    head = _clean(head)
    if 3 <= len(head) <= 90:
        return head
    return _clean(text)[:80].rstrip()


def _table_cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def extract_candidates(synthesis_text: str) -> List[Candidate]:
    """Parse a synthesis markdown into candidate items (deterministic, ``$0``)."""
    if not synthesis_text:
        return []
    out: List[Candidate] = []
    section = ""  # current known section label ("" = ignore lines)
    in_table = False
    table_seen_header = False

    for raw in synthesis_text.splitlines():
        line = raw.rstrip()
        hm = _HEADING_RE.match(line)
        if hm:
            section = _section_for(hm.group(1))
            in_table = False
            table_seen_header = False
            continue
        if not section:
            continue

        # Risk Register is a markdown table: first row = header, second = |---|, rest = risks.
        if section == "Risk Register" and line.lstrip().startswith("|"):
            cells = _table_cells(line)
            if set("".join(cells)) <= set("-: "):  # separator row
                in_table = True
                continue
            if not table_seen_header:
                table_seen_header = True  # header row
                continue
            if in_table and cells and _clean(cells[0]):
                risk = _clean(cells[0])
                out.append(Candidate(title=_title_of(risk), source_section="Risk Register",
                                     raw_text=_clean(" — ".join(cells))))
            continue

        m = _NUMBERED_RE.match(line) or _BULLET_RE.match(line)
        if m:
            item = _clean(m.group(1))
            if len(item) < 8:  # skip trivial fragments / sub-bullets that are noise
                continue
            out.append(Candidate(title=_title_of(item), source_section=section, raw_text=item))

    return out
