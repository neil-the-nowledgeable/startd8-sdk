# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Stakeholder Panel (codename *Kaigi*) — synthetic stakeholder agents kept available to answer
questions VIPP raises during kickoff preparation.

**M0 (this increment) ships the authoring surface only** — the roster contract (:mod:`models`) and
its loader/validator (:mod:`roster`), plus the ``stakeholders.yaml`` kickoff input domain projected
by Concierge ``instantiate-kickoff`` and reported by ``assess``. It is deterministic and ``$0`` (no
LLM). The **live panel** that queries these personas ships in a later increment; until then
:data:`PANEL_CONSUMABLE` is ``False`` and ``assess`` reports a roster as *authored* but not yet
*consumable* (requirements R2-S5 / FR-4).

See ``docs/design/stakeholder-panel/`` for the full requirements (v0.3) and plan (v1.1).
"""

from __future__ import annotations

from startd8.stakeholder_panel.models import (
    PROTOCOL_VERSION,
    PersonaBrief,
    Roster,
)
from startd8.stakeholder_panel.roster import (
    RosterError,
    assess_roster,
    load_roster,
    validate_roster,
)

# Flipped to True in the increment that ships the live panel (M1). ``assess`` reads this to
# distinguish "roster authored" from "roster consumable" so early adopters are not misled into
# expecting live-panel behavior that is not yet built (R2-S5).
PANEL_CONSUMABLE = False

__all__ = [
    "PROTOCOL_VERSION",
    "PANEL_CONSUMABLE",
    "PersonaBrief",
    "Roster",
    "RosterError",
    "assess_roster",
    "load_roster",
    "validate_roster",
]
