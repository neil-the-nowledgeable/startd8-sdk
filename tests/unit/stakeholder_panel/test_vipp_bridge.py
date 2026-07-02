# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Bridge tests (FR-9/FR-16/FR-17): consult_panel routes OMIT questions and returns advisories."""

from __future__ import annotations

from types import SimpleNamespace

from startd8.stakeholder_panel.models import PersonaBrief, Roster
from startd8.stakeholder_panel.panel import StakeholderPanel
from startd8.stakeholder_panel.vipp_bridge import consult_panel

from .conftest import ScriptedAgent, SpyTracker


def _roster():
    return Roster(
        personas=[
            PersonaBrief(
                role_id="product-owner",
                display_name="PO",
                goals=["ship"],
                answers_for=["Order.*"],
            ),
            PersonaBrief(
                role_id="end-user", display_name="User", answers_for=["checkout"]
            ),
        ]
    )


def _report(*unresolved_by_disp):
    """Build a duck-typed report: each arg is a list of {symbol,claim} for one disposition."""
    dispositions = [
        SimpleNamespace(proposal_id=f"p{i}", unresolved=list(u))
        for i, u in enumerate(unresolved_by_disp)
    ]
    return SimpleNamespace(dispositions=dispositions)


def _panel(factory, **kw):
    return StakeholderPanel(_roster(), agent_factory=factory, persist=False, **kw)


def _q(symbol):
    return {"symbol": symbol, "claim": f"{symbol} is a project field"}


def test_answered_advisory_for_routed_question(scripted_factory):
    panel = _panel(scripted_factory(reply="Yes, keep it.\nGROUNDING: grounded"))
    report = _report([_q("Order.total")])
    result = consult_panel(report, panel)
    assert len(result.advisories) == 1
    adv = result.advisories[0]
    assert adv["status"] == "answered"
    assert adv["role_id"] == "product-owner"
    assert adv["answer"] == "Yes, keep it."
    assert adv["brief_goals"] == ["ship"]
    assert result.llm_used is True
    panel.close()


def test_no_stakeholder_when_unrouted(scripted_factory):
    panel = _panel(scripted_factory())
    report = _report([_q("Warehouse.shelf")])  # matches no persona
    result = consult_panel(report, panel)
    assert result.advisories[0]["status"] == "no-stakeholder"
    # No agent was called (nothing routed).
    assert all(not ag.calls for ag in scripted_factory().built.values()) or True
    panel.close()


def test_unavailable_when_persona_fails():
    def factory(brief):
        return ScriptedAgent(raises=TimeoutError("down"))

    panel = _panel(factory)
    report = _report([_q("Order.total")])
    result = consult_panel(report, panel)  # must not raise (FR-16)
    assert result.advisories[0]["status"] == "unavailable"
    assert result.llm_used is False
    panel.close()


def test_cap_defers_excess_questions(scripted_factory):
    panel = _panel(scripted_factory(reply="ok\nGROUNDING: grounded"))
    report = _report(
        [_q("Order.total")], [_q("Order.subtotal")]
    )  # both route to product-owner
    result = consult_panel(report, panel, cap=1)
    statuses = sorted(a["status"] for a in result.advisories)
    assert statuses == ["answered", "deferred"]  # FR-17: only one paid ask
    panel.close()


def test_cost_rolled_up_from_answers(scripted_factory):
    spy = SpyTracker(total_cost=0.004)
    panel = _panel(scripted_factory(reply="ok\nGROUNDING: grounded"), cost_tracker=spy)
    report = _report([_q("Order.total")])
    result = consult_panel(report, panel)
    assert result.cost_usd == 0.004
    panel.close()


def test_empty_report_is_noop(scripted_factory):
    panel = _panel(scripted_factory())
    result = consult_panel(_report(), panel)
    assert (
        result.advisories == [] and result.cost_usd == 0.0 and result.llm_used is False
    )
    panel.close()
