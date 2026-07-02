# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Contradiction check for drafted recommendations (FR-KIR-6, M3).

The reactive :mod:`startd8.stakeholder_panel.grounding_guard` flags *unsupported specifics* — an
answer asserting a number the brief does not contain. That guard is **wrong for a recommendation**:
a proactive starter for a *blank* field is *expected* to introduce a value the brief never stated, so
the reactive guard would flag every honest draft. FR-KIR-6 replaces it with a **contradiction check**:
flag only a recommendation whose value conflicts with a stated brief goal/constraint.

The concrete, deterministic ($0) contradiction this checks is a **stated ceiling violation**: a brief
constraint that names a money/percent limit with a "ceiling" cue (``≤``, ``under``, ``at most``,
``max``, ``no more than`` …) that the recommendation's comparable value *exceeds*. Conservative by
design (money/percent only, ceiling cue required) so it never false-flags an honest estimate — parity
with the reactive guard's conservatism, inverted in intent.
"""

from __future__ import annotations

from typing import List

from startd8.stakeholder_panel.grounding_guard import (
    extract_money as _money,
    extract_percent as _percent,
)
from startd8.stakeholder_panel.models import PersonaBrief

__all__ = ["check_contradiction", "CEILING_CUES"]

# Phrases that mark a brief constraint's number as an upper bound the recommendation must not exceed.
CEILING_CUES = (
    "<=",
    "≤",
    "at most",
    "no more than",
    "not exceed",
    "under ",
    "below ",
    "max",
    "ceiling",
    "cap ",
    "budget",
    "limit",
)


def _value_text(recommended_value) -> str:
    """Flatten a scalar or composite ``{target, why}`` recommendation into one searchable string."""
    if isinstance(recommended_value, dict):
        return " ".join(str(v) for v in recommended_value.values())
    return str(recommended_value)


def check_contradiction(brief: PersonaBrief, recommended_value) -> List[str]:
    """Flag a drafted value that exceeds a stated ceiling in the persona's brief (FR-KIR-6).

    Returns advisory flag strings (empty ⇒ no contradiction). Only money/percent ceilings are
    checked; a constraint without a ceiling cue, or a non-numeric recommendation, never flags.
    """
    text = _value_text(recommended_value)
    rec_money = _money(text)
    rec_pct = _percent(text)
    if not rec_money and not rec_pct:
        return []

    flags: List[str] = []
    for constraint in brief.constraints:
        low = constraint.lower()
        if not any(cue in low for cue in CEILING_CUES):
            continue
        for cv in _money(constraint):
            for rv in rec_money:
                if rv > cv:
                    flags.append(
                        f"contradicts constraint '{constraint}': ${rv:g} exceeds ${cv:g}"
                    )
        for cv in _percent(constraint):
            for rv in rec_pct:
                if rv > cv:
                    flags.append(
                        f"contradicts constraint '{constraint}': {rv:g}% exceeds {cv:g}%"
                    )
    return flags
