# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Heuristic ($0) extraction of discrete items from a synthesis markdown (FR-1/FR-2/FR-3).

Two passes over the same text:

* **structured** — items under a *recognized* ``##`` section (Recommendations, Open Questions, Risk
  Register, Tensions, and the prototype sections UX Improvements / Quick Wins / Bigger Bets), captured
  as numbered/bullet/bold-lead lines (FR-1/FR-2). Records the *line index* it claimed.
* **residual** (FR-3, the centerpiece) — a sweep over the **raw line stream** (NOT gated behind a
  recognized section, H-1) that emits an ``UNSTRUCTURED`` :class:`Candidate` for every non-boilerplate
  line the structured pass did **not** claim — so content under *unknown* headings, and recognized-
  section lines that matched no item pattern, are preserved verbatim rather than silently dropped.

The two passes are disjoint by construction (residual skips ``claimed`` indices — H-3). No LLM.
"""

from __future__ import annotations

import re
from typing import List, Set, Tuple

from .models import Candidate, Lane

MIN_ITEM_CHARS = 8  # the noise floor; boilerplate + fragments shorter than this are excluded (H-2)

# Section header -> the label we tag candidates with. Matched case-insensitively; a heading merely has
# to *start with* (or contain) one of these. FR-1 adds the three prototype-posture sections.
_SECTION_PREFIXES = {
    "recommendation": "Recommendations",
    "open question": "Open Questions",
    "risk register": "Risk Register",
    "tension": "Tensions",
    "prioritized ux": "UX Improvements",
    "ux improvement": "UX Improvements",
    "quick win": "Quick Wins",
    "bigger bet": "Bigger Bets",
}

_KNOWN_SECTION_LABELS = frozenset(_SECTION_PREFIXES.values())

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_BOLD_LEAD_RE = re.compile(r"^\s*\*\*(.+?)\*\*")  # a line that leads with a **bold** span (FR-2)


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
    """A short label. For a **bold-lead** item the title is the bold span (NOT split on ``—``/``.`` —
    H-6: the ``**Label — …**`` format collides with a delimiter split and would truncate the title)."""
    t = text.strip()
    bm = _BOLD_LEAD_RE.match(t)
    if bm:
        head = _clean(bm.group(1))
        return head[:90].rstrip() if 3 <= len(head) else _clean(t)[:80].rstrip()
    head = _clean(re.split(r"[:—.]", t, maxsplit=1)[0])
    if 3 <= len(head) <= 90:
        return head
    return _clean(t)[:80].rstrip()


def _table_cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_boilerplate(line: str) -> bool:
    """Structural noise excluded from the residual sweep + the FR-5 coverage invariant (H-2).

    boilerplate = blank / heading / any table-scaffolding row (``|`` — risk *data* rows are claimed by
    the structured pass, so an unclaimed ``|`` line is a header or separator) / the SYNTHETIC-UNRATIFIED
    banner + disclaimer / fragments shorter than ``MIN_ITEM_CHARS``.
    """
    s = line.strip()
    if not s:
        return True
    if _HEADING_RE.match(line):
        return True
    if s.startswith("|"):
        return True
    up = s.upper()
    if ("SYNTHETIC" in up and "UNRATIFIED" in up) or "UNRATIFIED PANEL" in up:
        return True
    return len(_clean(s)) < MIN_ITEM_CHARS


def extract_structured(synthesis_text: str) -> Tuple[List[Candidate], Set[int]]:
    """The recognized-section items + the set of line indices they claimed (FR-1/FR-2, H-4)."""
    out: List[Candidate] = []
    claimed: Set[int] = set()
    section = ""  # current known section label ("" = not in a recognized section)
    in_table = False
    table_seen_header = False

    for i, raw in enumerate(synthesis_text.splitlines()):
        line = raw.rstrip()
        hm = _HEADING_RE.match(line)
        if hm:
            section = _section_for(hm.group(1))
            in_table = False
            table_seen_header = False
            continue
        if not section:
            continue

        # Risk Register is a markdown table: header row, separator, then risk data rows.
        if section == "Risk Register" and line.lstrip().startswith("|"):
            cells = _table_cells(line)
            if set("".join(cells)) <= set("-: "):  # separator row (boilerplate, unclaimed)
                in_table = True
                continue
            if not table_seen_header:
                table_seen_header = True  # header row (boilerplate, unclaimed)
                continue
            if in_table and cells and _clean(cells[0]):
                risk = _clean(cells[0])
                out.append(Candidate(title=_title_of(risk), source_section="Risk Register",
                                     raw_text=_clean(" — ".join(cells))))
                claimed.add(i)  # H-4: claim the risk DATA row
            continue

        m = _NUMBERED_RE.match(line) or _BULLET_RE.match(line)
        if m:
            item = _clean(m.group(1))
            if len(item) < MIN_ITEM_CHARS:
                continue
            out.append(Candidate(title=_title_of(m.group(1)), source_section=section, raw_text=item))
            claimed.add(i)
            continue

        if _BOLD_LEAD_RE.match(line):  # FR-2: a bold-lead item (e.g. Tensions "**T1 — … OPEN**")
            item = _clean(line)
            if len(item) < MIN_ITEM_CHARS:
                continue
            out.append(Candidate(title=_title_of(line), source_section=section, raw_text=item))
            claimed.add(i)

    return out, claimed


def extract_residual(synthesis_text: str, claimed: Set[int]) -> List[Candidate]:
    """FR-3 — preserve every non-boilerplate line the structured pass didn't claim, as UNSTRUCTURED.

    Iterates the raw line stream INDEPENDENTLY of the structured section gate (H-1), so lines under
    *unrecognized* headings are captured (tagged with the literal heading, else ``(unsectioned)``).
    """
    out: List[Candidate] = []
    section_label = "(unsectioned)"
    for i, raw in enumerate(synthesis_text.splitlines()):
        line = raw.rstrip()
        hm = _HEADING_RE.match(line)
        if hm:
            heading = hm.group(1).strip()
            section_label = _section_for(heading) or heading or "(unsectioned)"
            continue
        if i in claimed:
            continue
        # A table row under an UNRECOGNIZED heading carries real content the structured pass never
        # sees (that pass only tables under "Risk Register") — preserve its data rows rather than drop
        # them. Under a KNOWN section, tables are scaffolding the structured pass owns → skip.
        if line.lstrip().startswith("|"):
            cells = _table_cells(line)
            is_separator = set("".join(cells)) <= set("-: ")
            if is_separator or section_label in _KNOWN_SECTION_LABELS:
                continue
            item = _clean(" — ".join(c for c in cells if c))
            if len(item) < MIN_ITEM_CHARS:
                continue
            out.append(Candidate(title=_title_of(item), source_section=section_label,
                                 raw_text=item, lane=Lane.UNSTRUCTURED))
            continue
        if _is_boilerplate(line):
            continue
        item = _clean(line)
        out.append(Candidate(title=_title_of(line), source_section=section_label,
                             raw_text=item, lane=Lane.UNSTRUCTURED))
    return out


def extract_candidates(synthesis_text: str) -> List[Candidate]:
    """Parse a synthesis markdown into candidate items (deterministic, ``$0``).

    Structured items first (recognized sections), then residual UNSTRUCTURED items for everything else —
    disjoint by construction (residual skips the structured pass's claimed indices).
    """
    if not synthesis_text:
        return []
    structured, claimed = extract_structured(synthesis_text)
    residual = extract_residual(synthesis_text, claimed)
    return structured + residual
