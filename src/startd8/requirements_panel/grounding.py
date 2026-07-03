# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Project-grounding guard (FR-RP-4 — owned, brief + schema, two severities).

Grounds a candidate against **the project brief corpus + the parsed schema** (NOT the persona's own
brief — ``stakeholder_panel.grounding_guard`` is persona-brief-scoped). CRP corrections baked in:

* **Owned ``extract_temporal`` (R2-F1/R2-S2).** The panel guard's conservative temporal handling
  (``_MONTH_DATE`` bare-month exclusion + day-adjacency) is **private** and not reused, so it is
  **ported** here — a bare month verb ("may improve latency") must produce no temporal flag while
  "March 2027" does. Only ``extract_money``/``extract_percent`` are reused (they are public).
* **Two severities (R2-F2 / P3).** A **schema entity/field absence** is a deterministic **high** flag;
  an unsupported **money/percent/explicit-date** specific is **advisory**; a bare **year** (``_YEAR``
  matches every ``19xx``/``20xx`` → floods requirement prose) is **advisory-low**.
* **"Soften" = flags-only (R1-F2).** This module returns flags; it **never** mutates candidate text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence, Set

# Reuse ONLY the public extractors (money/percent are value-normalized: $5k ≡ $5,000).
from startd8.stakeholder_panel.grounding_guard import extract_money, extract_percent

__all__ = [
    "SEV_HIGH",
    "SEV_ADVISORY",
    "SEV_ADVISORY_LOW",
    "GroundingFlag",
    "extract_temporal",
    "extract_years",
    "ground_requirement",
]

SEV_HIGH = "high"
SEV_ADVISORY = "advisory"
SEV_ADVISORY_LOW = "advisory-low"

# Ported from stakeholder_panel.grounding_guard (its equivalents are private). Bare month words are
# deliberately NOT matched — "may"/"march" are common English verbs and would chronically false-flag
# qualitative requirement prose. A month is a date only when adjacent to a day/year number.
_QUARTER = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_MONTH = "january|february|march|april|may|june|july|august|september|october|november|december"
_MONTH_DATE = re.compile(
    rf"\b(?:{_MONTH})\b\.?,?\s+\d{{1,4}}|\b\d{{1,2}}\s+(?:{_MONTH})\b", re.IGNORECASE
)


@dataclass(frozen=True)
class GroundingFlag:
    """One grounding concern. ``severity`` gates behavior; the flag never mutates candidate text."""

    severity: str
    kind: str  # "schema-absence" | "money" | "percent" | "date" | "year"
    detail: str

    def render(self) -> str:
        return f"{self.severity}: {self.kind}: {self.detail}"


def extract_years(text: str) -> Set[str]:
    """Bare 4-digit years — the advisory-low class (``_YEAR`` floods prose, R2-F2)."""
    return {m.group(0) for m in _YEAR.finditer(text or "")}


def extract_temporal(text: str) -> Set[str]:
    """Explicit dates — quarters and day/year-adjacent months (the *advisory* class).

    Ports the panel guard's bare-month exclusion + day-adjacency (R2-S2): quarters (``Q3``) and
    month-with-day/year (``March 2027``, ``3 April``) are dates; a bare ``"may"`` is not.
    """
    out: Set[str] = set()
    out |= {f"q{m.group(1)}" for m in _QUARTER.finditer(text or "")}
    out |= {
        " ".join(m.group(0).lower().split()) for m in _MONTH_DATE.finditer(text or "")
    }
    return out


def _corpus_of(brief: str, schema_entities: Sequence[str]) -> str:
    return " ".join([brief or "", *schema_entities])


def ground_requirement(
    *,
    text: str,
    entities_referenced: Sequence[str],
    brief: str,
    schema_entities: Sequence[str],
) -> List[GroundingFlag]:
    """Flag a candidate against the project brief + schema. Returns flags; mutates nothing (R1-F2).

    - a referenced entity absent from ``schema_entities`` → **high** (deterministic);
    - a money/percent/explicit-date specific not in the corpus → **advisory**;
    - a bare year not in the corpus → **advisory-low**.
    """
    flags: List[GroundingFlag] = []
    known = {e.lower() for e in schema_entities}
    for ent in entities_referenced:
        if ent and ent.lower() not in known:
            flags.append(
                GroundingFlag(
                    SEV_HIGH, "schema-absence", f"entity {ent!r} not in schema"
                )
            )

    corpus = _corpus_of(brief, schema_entities)
    c_money, c_pct = extract_money(corpus), extract_percent(corpus)
    c_dates, c_years = extract_temporal(corpus), extract_years(corpus)

    for value in sorted(extract_money(text) - c_money):
        flags.append(GroundingFlag(SEV_ADVISORY, "money", f"${value:g}"))
    for value in sorted(extract_percent(text) - c_pct):
        flags.append(GroundingFlag(SEV_ADVISORY, "percent", f"{value:g}%"))
    for token in sorted(extract_temporal(text) - c_dates):
        flags.append(GroundingFlag(SEV_ADVISORY, "date", token))
    for token in sorted(extract_years(text) - c_years):
        flags.append(GroundingFlag(SEV_ADVISORY_LOW, "year", token))
    return flags
