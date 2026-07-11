# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""StakeholderPanel tests (FR-8/FR-13/FR-16/FR-17/FR-20/R2-S3)."""

from __future__ import annotations

import asyncio

import pytest

from startd8.stakeholder_panel.models import Grounding
from startd8.stakeholder_panel.panel import (
    PanelClosedError,
    StakeholderPanel,
    UnknownPersonaError,
)

from .conftest import SpyTracker


def _panel(roster, factory, **kw):
    return StakeholderPanel(roster, agent_factory=factory, persist=False, **kw)


def test_panel_builds_one_persona_per_roster_entry(
    two_persona_roster, scripted_factory
):
    panel = _panel(two_persona_roster, scripted_factory())
    assert panel.role_ids == ["product-owner", "end-user"]
    assert panel.roster_version.startswith("sha256:")
    panel.close()


def test_ask_returns_answer_stamped_with_session_and_roster(
    two_persona_roster, scripted_factory
):
    panel = _panel(two_persona_roster, scripted_factory())
    ans = asyncio.run(panel.ask("product-owner", "when do we ship?"))
    assert ans.role_id == "product-owner"
    assert ans.session_id == panel.session_id
    assert ans.roster_version == panel.roster_version
    assert ans.grounding is Grounding.GROUNDED
    panel.close()


def test_unknown_role_raises_never_misroutes(two_persona_roster, scripted_factory):
    panel = _panel(two_persona_roster, scripted_factory())
    with pytest.raises(UnknownPersonaError):
        asyncio.run(panel.ask("cfo", "budget?"))
    panel.close()


def test_cost_recorded_with_role_and_session_attribution(
    two_persona_roster, scripted_factory
):
    spy = SpyTracker(total_cost=0.002)
    panel = _panel(two_persona_roster, scripted_factory(), cost_tracker=spy)
    ans = asyncio.run(panel.ask("end-user", "what matters?"))
    assert ans.cost_usd == 0.002
    rec = spy.records[-1]
    # FR-13: the record must carry role_id + session_id as explicit dimensions.
    assert rec["metadata"]["role_id"] == "end-user"
    assert rec["metadata"]["session_id"] == panel.session_id
    assert "role:end-user" in rec["tags"]
    assert f"session:{panel.session_id}" in rec["tags"]
    panel.close()


def test_record_cost_splits_provider_prefix_for_pricing(two_persona_roster):
    """The pricing table is keyed by the BARE model id; passing 'provider:model' misses it and
    falls back to a generic estimate (the costUsd-mismapping). _record_cost must split the spec."""
    from .conftest import ScriptedAgent

    spy = SpyTracker(total_cost=0.01)

    def factory(brief):
        return ScriptedAgent(
            name=f"persona:{brief.role_id}",
            model="anthropic:claude-opus-4-8",
            reply="ok\nGROUNDING: grounded",
        )

    panel = _panel(two_persona_roster, factory, cost_tracker=spy)
    asyncio.run(panel.ask("end-user", "q?"))
    rec = spy.records[-1]
    assert rec["model"] == "claude-opus-4-8"  # bare id -> matches the pricing table
    assert rec["provider"] == "anthropic"
    panel.close()


def test_ask_all_answers_every_persona(two_persona_roster, scripted_factory):
    panel = _panel(two_persona_roster, scripted_factory())
    answers = asyncio.run(panel.ask_all("what's your top concern?"))
    assert {a.role_id for a in answers} == {"product-owner", "end-user"}
    panel.close()


def test_ask_all_cap_bounds_paid_calls_and_defers_rest(
    two_persona_roster, scripted_factory
):
    factory = scripted_factory()
    panel = _panel(two_persona_roster, factory)
    answers = asyncio.run(panel.ask_all("q", cap=1))
    answered = [a for a in answers if a.grounding is not Grounding.DEFERRED]
    deferred = [a for a in answers if a.grounding is Grounding.DEFERRED]
    assert len(answered) == 1 and len(deferred) == 1
    # Only the answered persona's agent was actually called (no spend on the deferred one).
    called = [rid for rid, ag in factory.built.items() if ag.calls]
    assert len(called) == 1
    panel.close()


def test_preflight_budget_delegates_and_is_noop_without_a_gate(
    two_persona_roster, scripted_factory
):
    seen = []
    panel = _panel(
        two_persona_roster,
        scripted_factory(),
        budget_preflight=lambda n: seen.append(n),
    )
    panel.preflight_budget(3)
    assert seen == [3]
    panel.close()
    # No gate configured → no-op, no raise.
    p2 = _panel(two_persona_roster, scripted_factory())
    p2.preflight_budget(99)
    p2.close()


def test_ask_all_budget_preflight_aborts_before_spend(
    two_persona_roster, scripted_factory
):
    factory = scripted_factory()

    def preflight(n):
        raise RuntimeError(f"budget would be exceeded for {n} calls")

    panel = _panel(two_persona_roster, factory, budget_preflight=preflight)
    with pytest.raises(RuntimeError):
        asyncio.run(panel.ask_all("q"))
    # No agent was called — the preflight fired before fan-out (FR-17).
    assert all(not ag.calls for ag in factory.built.values())
    panel.close()


def test_ask_all_one_failure_does_not_abort_siblings(two_persona_roster):
    # FR-16: a persona failure leaves that answer unavailable; the others still answer.
    def factory(brief):
        from .conftest import ScriptedAgent

        if brief.role_id == "product-owner":
            return ScriptedAgent(raises=TimeoutError("down"))
        return ScriptedAgent(reply="fine\nGROUNDING: grounded")

    panel = _panel(two_persona_roster, factory)
    answers = asyncio.run(panel.ask_all("q"))
    by_id = {a.role_id: a for a in answers}
    assert by_id["product-owner"].grounding is Grounding.UNAVAILABLE
    assert by_id["end-user"].grounding is Grounding.GROUNDED
    panel.close()


def test_close_makes_further_queries_raise(two_persona_roster, scripted_factory):
    panel = _panel(two_persona_roster, scripted_factory())
    panel.close()
    with pytest.raises(PanelClosedError):
        asyncio.run(panel.ask("product-owner", "q"))


def test_context_manager_closes(two_persona_roster, scripted_factory):
    with _panel(two_persona_roster, scripted_factory()) as panel:
        asyncio.run(panel.ask("product-owner", "q"))
    with pytest.raises(PanelClosedError):
        asyncio.run(panel.ask("product-owner", "q"))


def test_transcript_persists_available_answers_only(
    tmp_path, two_persona_roster, scripted_factory
):
    def factory(brief):
        from .conftest import ScriptedAgent

        if brief.role_id == "end-user":
            return ScriptedAgent(raises=TimeoutError("down"))
        return ScriptedAgent(reply="ship\nGROUNDING: grounded")

    panel = StakeholderPanel(
        two_persona_roster, agent_factory=factory, project_root=tmp_path, persist=True
    )
    asyncio.run(panel.ask("product-owner", "q"))
    asyncio.run(panel.ask("end-user", "q"))  # fails → unavailable → not persisted
    from startd8.stakeholder_panel.transcript import TranscriptStore

    entries = TranscriptStore(tmp_path, panel.session_id).load()
    assert [e.role_id for e in entries] == ["product-owner"]
    assert entries[0].brief_hash.startswith("sha256:")
    assert entries[0].roster_version == panel.roster_version
    panel.close()
