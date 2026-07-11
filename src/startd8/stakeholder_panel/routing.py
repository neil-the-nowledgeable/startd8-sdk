# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Route an OMIT question to the persona best positioned to answer it (FR-9c / OQ-9).

Matching is an **explicit optional mapping with a heuristic fallback** (OQ-9): a persona's
``answers_for`` prefixes are matched against the question's ``value_path`` symbol. Two hard rules
from FR-9c:

* **No match ⇒ stays OMIT** (return ``None``); the question is never routed to a non-matching
  persona (which would violate FR-7's "no persona speaks for another's domain").
* **Ambiguous match ⇒ deterministic tie-break** — the first matching persona in roster order, never
  an arbitrary pick.
"""

from __future__ import annotations

from typing import List, Optional

from startd8.stakeholder_panel.models import PersonaBrief

__all__ = ["route", "persona_matches"]


def _normalize(entry: str) -> str:
    """A routing prefix: drop a trailing glob/dot, lowercase. ``Order.*`` → ``order``."""
    return entry.strip().rstrip("*").rstrip(".").lower()


def persona_matches(brief: PersonaBrief, value_path: str) -> bool:
    """True iff *value_path* falls under one of the persona's ``answers_for`` prefixes."""
    vp = (value_path or "").strip().lower()
    if not vp:
        return False
    head = vp.split(".", 1)[0]
    for raw in brief.answers_for:
        prefix = _normalize(raw)
        if not prefix:
            continue
        if vp == prefix or head == prefix or vp.startswith(prefix + "."):
            return True
    return False


def route(
    briefs: List[PersonaBrief], value_path: str, claim: str = ""
) -> Optional[str]:
    """Return the ``role_id`` to answer *value_path*, or ``None`` if no persona matches (FR-9c).

    ``claim`` is accepted for future heuristic use; v1 routes on ``value_path`` only. Deterministic:
    the first matching persona in roster order wins an ambiguous match.
    """
    for brief in briefs:  # roster order = deterministic tie-break
        if persona_matches(brief, value_path):
            return brief.role_id
    return None
