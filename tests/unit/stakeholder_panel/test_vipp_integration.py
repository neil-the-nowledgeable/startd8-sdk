# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""VIPP integration (M2): FR-9b routing context, FR-9 opt-in pass, FR-18 verdict/store isolation."""

from __future__ import annotations

import json

from startd8.sapper.ground_truth import GroundTruthAnswer, GroundTruthVerdict
from startd8.vipp import evaluate
from startd8.vipp.assistant import run_vipp_negotiate
from startd8.vipp.models import Decision, EnvelopedProposal, ProposalEnvelope

from .conftest import ScriptedAgent


class _OmitOracle:
    def answer(self, question):
        return GroundTruthAnswer.omit("unscripted")


class _ValidateOracle:
    def answer(self, question):
        return GroundTruthAnswer(
            verdict=GroundTruthVerdict.VALIDATED,
            evidence="found",
            source="sapper:project_knowledge",
        )


def _capture_env(seq=1):
    return ProposalEnvelope(
        project_id="proj-1",
        envelope_seq=seq,
        generated_at="2026-06-30T00:00:00Z",
        proposals=[
            EnvelopedProposal(
                kind="capture",
                params={"value_path": "Order.total", "value": "x"},
                id="p_cap",
            )
        ],
        content_checksum="sha256:fixed",
    )


# ── FR-9b: routing context threaded onto OMIT dispositions (additive, R2-S1) ─────


def test_omit_disposition_carries_routing_context():
    [disp] = evaluate.evaluate_envelope(_capture_env(), _OmitOracle())
    assert disp.decision is Decision.ACCEPT  # OMIT-default ACCEPT (unchanged verdict)
    assert disp.unresolved == [
        {"symbol": "Order.total", "claim": "Order.total is a project field"}
    ]
    assert disp.to_dict()["unresolved"][0]["symbol"] == "Order.total"


def test_validated_disposition_has_no_unresolved_key_backcompat():
    # R2-S1: a non-OMIT disposition serializes byte-identically to before (no new key).
    [disp] = evaluate.evaluate_envelope(_capture_env(), _ValidateOracle())
    assert disp.unresolved == []
    assert "unresolved" not in disp.to_dict()


# ── FR-9 / FR-18 / FR-19: the opt-in panel pass around run_vipp_negotiate ─────────


def _panel_for(tmp_path, reply="Yes, that's the order total.\nGROUNDING: grounded"):
    from startd8.stakeholder_panel.models import PersonaBrief, Roster
    from startd8.stakeholder_panel.panel import StakeholderPanel

    roster = Roster(
        personas=[
            PersonaBrief(
                role_id="product-owner",
                display_name="Product Owner",
                goals=["ship the MVP"],
                answers_for=["Order.*"],
            )
        ]
    )
    return StakeholderPanel(
        roster,
        agent_factory=lambda brief: ScriptedAgent(reply=reply),
        project_root=tmp_path,
        persist=False,
    )


def _write_inbox(tmp_path):
    inbox = tmp_path / "inbox.json"
    inbox.write_text(json.dumps(_capture_env().to_dict()), encoding="utf-8")
    return inbox


def test_negotiate_without_panel_is_zero_cost_and_no_advisories(tmp_path):
    out = run_vipp_negotiate(_write_inbox(tmp_path), project_root=tmp_path, emit=False)
    assert out.report.cost_usd == 0.0 and out.report.llm_used is False
    assert out.report.panel_advisories == []
    assert (
        "panel_advisories" not in out.report.to_dict()
    )  # additive: omitted when empty


def test_negotiate_with_panel_attaches_synthetic_advisory(tmp_path):
    panel = _panel_for(tmp_path)
    out = run_vipp_negotiate(
        _write_inbox(tmp_path), project_root=tmp_path, emit=False, panel=panel
    )
    panel.close()

    advisories = out.report.panel_advisories
    assert len(advisories) == 1 and advisories[0]["status"] == "answered"
    assert advisories[0]["role_id"] == "product-owner"

    # FR-9: the verdict is UNCHANGED (still the OMIT-default ACCEPT)...
    disp = out.report.dispositions[0]
    assert disp.decision is Decision.ACCEPT
    # FR-18: ...and no synthetic claim leaked into the ratified disposition claims.
    assert all("panel:" not in c.source for c in disp.claims)

    # FR-19: the rendered report carries the synthetic/unratified banner + the answer.
    md = (tmp_path / ".startd8/vipp/dispositions.md").read_text(encoding="utf-8")
    assert "SYNTHETIC, UNRATIFIED" in md
    assert "that's the order total" in md
    assert "panel_advisories" in out.report.to_dict()


def test_negotiate_advisory_surfaces_grounding_flag(tmp_path):
    # FR-7 (M3): a persona fabricating an unsupported figure is flagged in the advisory section.
    panel = _panel_for(tmp_path, reply="It should be $99,000.\nGROUNDING: grounded")
    out = run_vipp_negotiate(
        _write_inbox(tmp_path), project_root=tmp_path, emit=False, panel=panel
    )
    panel.close()
    adv = out.report.panel_advisories[0]
    assert (
        adv["grounding"] == "uncertain"
    )  # downgraded from the self-reported "grounded"
    assert any("$99000" in f for f in adv["flags"])
    md = (tmp_path / ".startd8/vipp/dispositions.md").read_text(encoding="utf-8")
    assert "grounding check" in md


def test_negotiate_with_panel_no_match_stays_omit(tmp_path):
    # Persona answers_for does not cover Order.* → the question stays OMIT (FR-9c).
    from startd8.stakeholder_panel.models import PersonaBrief, Roster
    from startd8.stakeholder_panel.panel import StakeholderPanel

    roster = Roster(
        personas=[
            PersonaBrief(
                role_id="ops",
                display_name="Ops",
                goals=["uptime"],
                answers_for=["infra"],
            )
        ]
    )
    panel = StakeholderPanel(
        roster,
        agent_factory=lambda b: ScriptedAgent(),
        project_root=tmp_path,
        persist=False,
    )
    out = run_vipp_negotiate(
        _write_inbox(tmp_path), project_root=tmp_path, emit=False, panel=panel
    )
    panel.close()
    assert out.report.panel_advisories[0]["status"] == "no-stakeholder"
    assert out.report.cost_usd == 0.0  # nothing was asked
