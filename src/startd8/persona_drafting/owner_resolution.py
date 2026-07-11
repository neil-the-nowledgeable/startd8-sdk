# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Bounded owner-resolution (FR-PD-4 — shared, generic, NOT value-domain-bound).

The generic form of the algorithm the siblings each re-implement: resolve a routing *symbol* to the
persona that owns it, bounded so a bad fit is never a loose match. Generic over the symbol (keyed on a
string + a domain descriptor of owning-role + aliases) — deliberately **not** coupled to any value
domain (the exact coupling that made ``input_domains.resolve_owner`` non-reusable, R1-F1/R2-S1).
"""

from __future__ import annotations

from typing import Optional, Sequence

from startd8.stakeholder_panel.models import PersonaBrief

__all__ = ["resolve_bounded_owner"]


def _normalize(entry: str) -> str:
    return entry.strip().rstrip("*").rstrip(".").lower()


def resolve_bounded_owner(
    *,
    owning_role: str,
    aliases: Sequence[str],
    symbol: str,
    briefs: Sequence[PersonaBrief],
) -> Optional[str]:
    """Return the ``role_id`` that owns *symbol*, or ``None`` to **skip** (bounded).

    Resolution order (deterministic, roster-order tie-break):
      1. the default ``owning_role`` if present on the roster;
      2. else a persona whose ``answers_for`` **explicitly names** the symbol or an alias (high-confidence);
      3. else ``None`` — skip, never a loose match.
    """
    by_id = {b.role_id: b for b in briefs}
    if owning_role in by_id:
        return owning_role
    wanted = {symbol, *aliases}
    for brief in briefs:  # roster order = deterministic tie-break
        for raw in brief.answers_for:
            if _normalize(raw) in wanted:
                return brief.role_id
    return None
