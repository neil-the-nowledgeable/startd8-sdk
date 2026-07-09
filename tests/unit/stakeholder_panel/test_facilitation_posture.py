# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Posture: scrutiny (default, strategic red-team) vs prototype (constructive early-stage UX).

Proves the ``prototype`` posture (1) replaces the two attack adversaries with ONE constructive
skeptic, (2) turns the assumptions gate into a NON-BLOCKING readiness note (no premise-halt),
(3) reframes every round + the synthesis around UX improvement, and that the ``scrutiny`` default is
byte-unchanged (still halts). Also covers the derived (no-longer-hardcoded) outside-view reference
class. Everything runs OFFLINE and $0 via ScriptedAgent doubles.
"""
from __future__ import annotations

import asyncio

import pytest

from startd8.stakeholder_panel import facilitation as F
from startd8.stakeholder_panel.models import PersonaBrief, Roster

from .conftest import ScriptedAgent


@pytest.fixture
def small_roster() -> Roster:
    return Roster(
        personas=[
            PersonaBrief(role_id="product-owner", display_name="Product Owner", goals=["ship the MVP"]),
            PersonaBrief(role_id="end-user", display_name="End User", goals=["log a thing fast"]),
        ]
    )


def _persona_factory():
    def factory(brief: PersonaBrief):
        return ScriptedAgent(name=f"persona:{brief.role_id}", model="scripted",
                             reply=f"[{brief.role_id}] my take.\nGROUNDING: grounded")
    return factory


_TWO_RISKY = (
    "1. Demand exists — CONFIDENCE (low), IMPACT IF WRONG (high).\n"
    "2. The proactive path works — CONFIDENCE (low), IMPACT IF WRONG (high).\n"
    "3. Payments work — CONFIDENCE (high), IMPACT IF WRONG (low).\n"
)


def _facilitator(*, synth_reply="## Tensions\n(none)", assumptions_reply="[assumptions] prep", echo=False):
    def factory(spec, name, system_prompt):
        if echo:
            return ScriptedAgent(name=name, model=spec, reply=lambda p: p)
        if system_prompt == F._SYNTH_SYS:
            reply = synth_reply
        elif name == "assumptions":
            reply = assumptions_reply
        else:
            reply = f"[{name}] prep"
        return ScriptedAgent(name=name, model=spec, reply=reply)
    return factory


def _run(roster, cfg, **kw):
    fac = F.KickoffFacilitator(cfg, roster=roster, **kw)
    return fac, asyncio.run(fac.run())


# ── config surface ───────────────────────────────────────────────────────────
def test_default_posture_is_scrutiny(tmp_path):
    assert F.FacilitationConfig(project=tmp_path).posture == F.POSTURE_SCRUTINY


def test_invalid_posture_rejected(tmp_path):
    with pytest.raises(ValueError):
        F.FacilitationConfig(project=tmp_path, posture="bogus")


# ── challenger selection ─────────────────────────────────────────────────────
def test_prototype_uses_one_skeptic_not_adversaries(tmp_path, small_roster):
    briefs = F.build_briefs(F.FacilitationConfig(project=tmp_path, posture="prototype"), small_roster)
    ids = [b.role_id for b in briefs]
    assert "skeptical-new-user" in ids
    assert not (set(ids) & F.ADVERSARY_IDS)


def test_scrutiny_uses_two_adversaries(tmp_path, small_roster):
    briefs = F.build_briefs(F.FacilitationConfig(project=tmp_path), small_roster)
    assert F.ADVERSARY_IDS <= {b.role_id for b in briefs}
    assert "skeptical-new-user" not in {b.role_id for b in briefs}


# ── the gate: prototype does NOT halt, scrutiny still does ────────────────────
def test_prototype_posture_does_not_halt_on_risky_assumptions(tmp_path, small_roster):
    """The miscalibration this posture fixes: an early prototype has unproven assumptions by
    definition, so the premise-halt must NOT fire — it degrades to a readiness note and runs."""
    cfg = F.FacilitationConfig(project=tmp_path, posture="prototype", ground=False, outside_view=False)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(assumptions_reply=_TWO_RISKY))
    assert session["status"] == "completed"
    assert session["halt"] is None
    assert session["rounds"], "prototype must spend the rounds, not halt"
    assert session["synthesis"] is not None
    # the readiness note is still recorded for the human
    assert session["prep"]["key_assumptions"] == _TWO_RISKY


def test_scrutiny_posture_still_halts_on_risky_assumptions(tmp_path, small_roster):
    """Regression: the default posture is unchanged — >= threshold risky assumptions still HALT."""
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(assumptions_reply=_TWO_RISKY))
    assert session["status"] == "halted"
    assert session["halt"]["reason"] == "assumptions_gate"


# ── framing: rounds + synthesis are constructive/UX in prototype ─────────────
def test_prototype_round_and_synth_framing_is_constructive():
    assert "UX IMPROVEMENTS" in F._r1_for("c", "proj", "prototype", is_challenger=False)
    assert "SKEPTICAL NEW USER" in F._r1_for("c", "proj", "prototype", is_challenger=True)
    assert "FIRST-WEEK CHECK" in F._premortem_for("proj", "prototype", is_challenger=False)
    assert "BUILD ON" in F._r3_for("digest", "prototype")
    assert "UX improvement" in F._r4_for("prototype")
    synth = F._synth_for("prototype", "transcript", {}, {})
    assert "## Prioritized UX Improvements" in synth and "## Quick Wins" in synth
    assert "## Adversary Findings" not in synth  # not the scrutiny structure


def test_scrutiny_framing_unchanged():
    assert "biggest RISK" in F._r1_for("c", "proj", "scrutiny", is_challenger=False)
    assert "ADVERSARY" in F._r1_for("c", "proj", "scrutiny", is_challenger=True)
    assert "PRE-MORTEM" in F._premortem_for("proj", "scrutiny", is_challenger=False)
    synth = F._synth_for("scrutiny", "transcript", {}, {})
    assert "## Risk Register" in synth and "## Adversary Findings" in synth


# ── outside-view reference class is DERIVED, not hardcoded to Online Boutique ─
def test_outside_view_prompt_is_derived_from_objective(tmp_path, small_roster):
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, assumptions=False,
                               objective="track household chores and alert before deadlines slip")
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(echo=True))
    ov = session["prep"]["outside_view"]
    assert "NAME the general reference class" in ov
    assert "track household chores" in ov          # derived from THIS objective
    assert "online retailer" not in ov.lower()      # the old hardcoded class is gone
