# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M3 tests — contradiction-only grounding (FR-KIR-6), estimate signal, deferral skip, telemetry."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.stakeholder_panel.contradiction_guard import check_contradiction
from startd8.stakeholder_panel.models import Grounding, PersonaBrief, Roster
from startd8.stakeholder_panel.panel import StakeholderPanel
from startd8.stakeholder_panel.recommend import recommend_inputs
from startd8.stakeholder_panel.telemetry import EV_APPROVED, decision_event

from .conftest import ScriptedAgent


# --- contradiction guard (unit) -------------------------------------------------------


def test_check_contradiction_money_ceiling():
    b = PersonaBrief(
        role_id="pm",
        display_name="PM",
        constraints=["Keep the LLM budget under $5000 per month"],
    )
    assert check_contradiction(b, "$10000")  # exceeds → flagged
    assert "exceeds" in check_contradiction(b, "$10000")[0]
    assert check_contradiction(b, "$3000") == []  # within ceiling
    assert check_contradiction(b, "fastapi") == []  # non-numeric → no flag


def test_check_contradiction_needs_ceiling_cue_and_percent():
    # a plain historical number is NOT a ceiling → no false flag
    b = PersonaBrief(role_id="pm", display_name="PM", constraints=["We spent $5000 last year"])
    assert check_contradiction(b, "$10000") == []
    # percent ceiling
    b2 = PersonaBrief(role_id="po", display_name="PO", goals=["g"], constraints=["conversion at most 5%"])
    assert check_contradiction(b2, {"target": "12%", "why": "x"})


# --- pass wiring ----------------------------------------------------------------------


def _bp_package(root: Path):
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(
        "domain: build-preferences\nprovenance_default: estimate\n"
        'budgets:\n  llm_monthly_ceiling_usd: "<N>"\n',
        encoding="utf-8",
    )


def _panel(root, roster, reply):
    return StakeholderPanel(
        roster,
        project_root=root,
        agent_factory=lambda brief: ScriptedAgent(reply=reply),
        persist=True,
    )


@pytest.mark.asyncio
async def test_draft_is_estimate_with_contradiction_flag_not_unsupported_specifics(tmp_path):
    _bp_package(tmp_path)
    roster = Roster(
        personas=[
            PersonaBrief(
                role_id="pm",
                display_name="PM",
                goals=["ship on budget"],
                constraints=["Keep the LLM budget under $5000 per month"],
            )
        ]
    )
    # persona over-recommends $10000 — a real contradiction with its own stated ceiling
    panel = _panel(tmp_path, roster, "VALUE: $10000 || WHY: aggressive\nGROUNDING: grounded")
    try:
        run = await recommend_inputs(tmp_path, panel)
    finally:
        panel.close()

    rec = run.recommendations[0]
    # FR-KIR-6: the draft is an ESTIMATE (not 'grounded'/'uncertain' from the reactive guard)
    assert rec.grounding is Grounding.ESTIMATE
    # the contradiction fires ...
    assert any("exceeds" in f for f in rec.flags)
    # ... and the reactive "unsupported-specifics" flag is NOT carried onto a recommendation
    assert not any("unsupported-specifics" in f for f in rec.flags)


@pytest.mark.asyncio
async def test_persona_deferral_leaves_field_unchanged(tmp_path):
    _bp_package(tmp_path)
    roster = Roster(personas=[PersonaBrief(role_id="pm", display_name="PM", goals=["ship"])])
    panel = _panel(tmp_path, roster, "That's outside my remit.\nGROUNDING: deferred")
    try:
        run = await recommend_inputs(tmp_path, panel)
    finally:
        panel.close()
    assert run.fields_drafted == 0
    assert any(s["status"] == "deferred-persona" for s in run.skipped)


def test_decision_event_never_throws():
    # telemetry must never break a CLI action, with or without an OTel backend
    decision_event(EV_APPROVED, domain="business-targets", role_id="product-owner", value_path="x")
