# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Independent grounding guard against in-scope fabrication (FR-7 / OQ-10, M3).

The persona's ``GROUNDING:`` line is **self-reported** — a confident in-scope fabrication would claim
``grounded`` while inventing a fact. This module is a deterministic ($0) second opinion: it extracts
the high-signal *commitment specifics* an answer asserts — **money, percentages, and dates/quarters**
— and flags any that are not traceable to the persona's brief. Two effects (advisory, never a hard
block per plan §4):

* a self-reported ``grounded`` carrying unsupported specifics is **downgraded to ``uncertain``**
  (we never let an unverified "grounded" stand);
* the unsupported specifics are attached to the answer as ``flags`` so the ratification view (FR-19)
  and the CLI can show "check this".

Deliberately conservative: only ``$``/``%``/temporal tokens are checked (bare integers like "3 goals"
are ignored) to keep false positives low. Money is value-normalized so ``$5k`` ≡ ``$5,000``.
"""

from __future__ import annotations

import re
from typing import List, Set, Tuple

from startd8.stakeholder_panel.models import Grounding, PersonaBrief

__all__ = ["check_grounding", "unsupported_specifics"]

_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?([kKmM])?")
_PERCENT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?%")
_QUARTER = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_MONTHS = (
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec"
).split()


def _num(raw: str, suffix: str = "") -> float:
    value = float(raw.replace(",", ""))
    if suffix.lower() == "k":
        value *= 1_000
    elif suffix.lower() == "m":
        value *= 1_000_000
    return value


def _money(text: str) -> Set[float]:
    return {_num(m.group(1), m.group(2) or "") for m in _MONEY.finditer(text)}


def _percent(text: str) -> Set[float]:
    return {_num(m.group(1)) for m in _PERCENT.finditer(text)}


def _temporal(text: str) -> Set[str]:
    low = text.lower()
    out: Set[str] = set()
    out |= {f"q{m.group(1)}" for m in _QUARTER.finditer(text)}
    out |= {m.group(0) for m in _YEAR.finditer(text)}
    out |= {word for word in _MONTHS if re.search(rf"\b{word}\b", low)}
    return out


def _brief_corpus(brief: PersonaBrief) -> str:
    return " ".join(
        [*brief.goals, *brief.constraints, *brief.known_positions, brief.display_name]
    )


def unsupported_specifics(brief: PersonaBrief, answer_text: str) -> List[str]:
    """Return the answer's money/percent/date specifics that the brief does not support."""
    corpus = _brief_corpus(brief)
    brief_money, brief_pct, brief_time = (
        _money(corpus),
        _percent(corpus),
        _temporal(corpus),
    )
    out: List[str] = []
    for value in sorted(_money(answer_text)):
        if value not in brief_money:
            out.append(f"${value:g}")
    for value in sorted(_percent(answer_text)):
        if value not in brief_pct:
            out.append(f"{value:g}%")
    for token in sorted(_temporal(answer_text)):
        if token not in brief_time:
            out.append(token)
    return out


def check_grounding(
    brief: PersonaBrief, answer_text: str, reported: Grounding
) -> Tuple[Grounding, List[str]]:
    """Second-opinion grounding check (FR-7). Returns (possibly-downgraded grounding, advisory flags).

    Deferred/unavailable answers assert nothing, so they are passed through unchecked.
    """
    if reported in (Grounding.DEFERRED, Grounding.UNAVAILABLE):
        return reported, []
    unsupported = unsupported_specifics(brief, answer_text)
    if not unsupported:
        return reported, []
    flag = "unsupported-specifics: " + ", ".join(unsupported)
    # Never let a self-reported "grounded" with unbacked specifics stand; hedge it to "uncertain".
    adjusted = Grounding.UNCERTAIN if reported is Grounding.GROUNDED else reported
    return adjusted, [flag]
