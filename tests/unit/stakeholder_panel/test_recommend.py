# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M1 tests — the proactive recommendation pass, Recommendation model, provenance, and staging."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.stakeholder_panel.models import Grounding, PersonaBrief, Recommendation, Roster
from startd8.stakeholder_panel.panel import StakeholderPanel
from startd8.stakeholder_panel.proposals import (
    ProposalStore,
    gc_stale_proposals,
    latest_session,
)
from startd8.stakeholder_panel.recommend import recommend_inputs
from startd8.stakeholder_panel.recommend_provenance import (
    assert_not_authored,
    is_estimate,
    panel_origin,
)

_REPLY = (
    "TARGET: FORTY || VALUE: FORTY || WHY: draft rationale || STATUS: dormant\n"
    "GROUNDING: grounded"
)


class _Usage:
    input = 3
    output = 5
    model_name = "fake"


class FakeAgent:
    def __init__(self, counter, reply=_REPLY, fail=False):
        self.model = "fake"
        self._counter = counter
        self._reply = reply
        self._fail = fail

    async def agenerate(self, prompt, system_prompt=None):
        self._counter["calls"] += 1
        if self._fail:
            raise RuntimeError("provider down")
        return self._reply, 1, _Usage()


def _roster(role_ids):
    return Roster(
        personas=[
            PersonaBrief(role_id=r, display_name=r.title(), goals=["ship the product"])
            for r in role_ids
        ]
    )


def _write_package(root: Path):
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "business-targets.yaml").write_text(
        "domain: business-targets\n"
        "provenance_default: estimate\n"
        "product_funnel:\n"
        "  signup_rate:\n"
        '    target: "<NN%>"\n'
        "    why: <core funnel>\n"
        "  activation_rate:\n"
        '    target: "60%"\n'
        "    why: already filled\n",
        encoding="utf-8",
    )
    (inputs / "conventions.yaml").write_text(
        "domain: conventions\nprovenance_default: estimate\n"
        "language: python\nstack:\n  web: \"<framework>\"\n",
        encoding="utf-8",
    )
    (inputs / "build-preferences.yaml").write_text(
        "domain: build-preferences\nprovenance_default: estimate\n"
        "budgets:\n  llm_monthly_ceiling_usd: \"<N>\"\n",
        encoding="utf-8",
    )


def _panel(root, role_ids, counter, *, fail=False, budget_preflight=None):
    return StakeholderPanel(
        _roster(role_ids),
        project_root=root,
        agent_factory=lambda brief: FakeAgent(counter, fail=fail),
        persist=True,
        budget_preflight=budget_preflight,
    )


# --- the pass -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pass_drafts_unfilled_skips_filled_and_stages(tmp_path):
    _write_package(tmp_path)
    counter = {"calls": 0}
    panel = _panel(tmp_path, ["product-owner", "architect", "pm"], counter)
    try:
        run = await recommend_inputs(tmp_path, panel)
    finally:
        panel.close()

    drafted = {r.value_path for r in run.recommendations}
    # one unfilled field per domain drafted; the human-filled row skipped
    assert drafted == {
        "product_funnel.signup_rate",
        "stack.web",
        "budgets.llm_monthly_ceiling_usd",
    }
    assert run.fields_drafted == 3
    assert run.llm_used is True

    # composite metric row → dict value + two scalar writes (R4-F1)
    sig = next(r for r in run.recommendations if r.value_path == "product_funnel.signup_rate")
    assert sig.is_composite
    assert sig.recommended_value == {"target": "FORTY", "why": "draft rationale"}
    assert sig.scalar_writes() == [
        ("product_funnel.signup_rate.target", "FORTY"),
        ("product_funnel.signup_rate.why", "draft rationale"),
    ]
    assert is_estimate(sig) and sig.origin == panel_origin("product-owner")

    # staged out-of-band and reloadable
    store = ProposalStore(tmp_path, panel.session_id)
    assert {r.value_path for r in store.load()} == drafted


@pytest.mark.asyncio
async def test_no_owner_domain_is_skipped(tmp_path):
    _write_package(tmp_path)
    counter = {"calls": 0}
    # no 'architect' → conventions has no confident owner → skipped
    panel = _panel(tmp_path, ["product-owner", "pm"], counter)
    try:
        run = await recommend_inputs(tmp_path, panel)
    finally:
        panel.close()
    assert {r.value_path for r in run.recommendations} == {
        "product_funnel.signup_rate",
        "budgets.llm_monthly_ceiling_usd",
    }
    assert {"domain": "conventions", "status": "no-owner"} in run.skipped


@pytest.mark.asyncio
async def test_cap_defers_remaining(tmp_path):
    _write_package(tmp_path)
    counter = {"calls": 0}
    panel = _panel(tmp_path, ["product-owner", "architect", "pm"], counter)
    try:
        run = await recommend_inputs(tmp_path, panel, cap=1)
    finally:
        panel.close()
    assert run.fields_drafted == 1
    assert counter["calls"] == 1
    assert sum(1 for s in run.skipped if s["status"] == "deferred-cap") == 2


@pytest.mark.asyncio
async def test_budget_denial_defers_all_spends_nothing(tmp_path):
    _write_package(tmp_path)
    counter = {"calls": 0}

    def deny(_n):
        raise RuntimeError("budget exceeded")

    panel = _panel(
        tmp_path, ["product-owner", "architect", "pm"], counter, budget_preflight=deny
    )
    try:
        run = await recommend_inputs(tmp_path, panel)
    finally:
        panel.close()
    assert run.fields_drafted == 0
    assert counter["calls"] == 0  # nothing asked → $0
    assert all(s["status"] == "deferred-budget" for s in run.skipped if "value_path" in s)
    # nothing staged
    assert ProposalStore(tmp_path, panel.session_id).load() == []


@pytest.mark.asyncio
async def test_unavailable_persona_leaves_field_unchanged(tmp_path):
    _write_package(tmp_path)
    counter = {"calls": 0}
    panel = _panel(tmp_path, ["product-owner", "architect", "pm"], counter, fail=True)
    try:
        run = await recommend_inputs(tmp_path, panel)
    finally:
        panel.close()
    assert run.fields_drafted == 0
    assert all(s["status"] == "unavailable" for s in run.skipped if "value_path" in s)


@pytest.mark.asyncio
async def test_rerun_skips_already_drafted_no_respend(tmp_path):
    _write_package(tmp_path)
    counter = {"calls": 0}
    panel = _panel(tmp_path, ["product-owner", "architect", "pm"], counter)
    try:
        await recommend_inputs(tmp_path, panel)
        first = counter["calls"]
        run2 = await recommend_inputs(tmp_path, panel)
    finally:
        panel.close()
    assert run2.fields_drafted == 0
    assert counter["calls"] == first  # Mottainai: no re-spend (R2-S2)
    assert all(s["status"] == "already-drafted" for s in run2.skipped)


@pytest.mark.asyncio
async def test_redraft_forces_respend(tmp_path):
    _write_package(tmp_path)
    counter = {"calls": 0}
    panel = _panel(tmp_path, ["product-owner", "architect", "pm"], counter)
    try:
        await recommend_inputs(tmp_path, panel)
        first = counter["calls"]
        run2 = await recommend_inputs(tmp_path, panel, redraft=True)
    finally:
        panel.close()
    assert run2.fields_drafted == 3
    assert counter["calls"] == first + 3


# --- model / provenance / staging ----------------------------------------------------


def test_recommendation_roundtrip_preserves_estimate():
    rec = Recommendation(
        domain="business-targets",
        value_path="traction.mau",
        recommended_value={"target": "1000", "why": "x"},
        role_id="product-owner",
        grounding=Grounding.GROUNDED,
        origin="panel:product-owner",
        composite_keys=("target", "why"),
    )
    back = Recommendation.from_dict(rec.to_dict())
    assert back == rec
    assert back.provenance == "estimate"
    # a reloaded draft with a missing provenance key never silently upgrades
    d = rec.to_dict()
    del d["provenance"]
    assert Recommendation.from_dict(d).provenance == "estimate"


def test_assert_not_authored_guard():
    ok = Recommendation(domain="d", value_path="v", recommended_value="x")
    assert_not_authored(ok)  # no raise
    bad = Recommendation(domain="d", value_path="v", recommended_value="x", provenance="authored")
    with pytest.raises(ValueError):
        assert_not_authored(bad)


def test_proposal_store_disposition_and_session_helpers(tmp_path):
    store = ProposalStore(tmp_path, "sess-a")
    rec = Recommendation(domain="conventions", value_path="stack.web", recommended_value="fastapi")
    store.save([rec])
    assert store.get("conventions", "stack.web").disposition == "draft"
    assert store.update_disposition("conventions", "stack.web", "approved") is True
    assert store.get("conventions", "stack.web").disposition == "approved"
    assert store.update_disposition("conventions", "missing", "approved") is False

    # sorted + indent=2 (diffable audit trail, R2-S4)
    text = store.path.read_text(encoding="utf-8")
    assert text.startswith("[\n  {")
    assert '"domain": "conventions"' in text

    assert latest_session(tmp_path) == "sess-a"


def test_gc_stale_proposals_keeps_recent(tmp_path):
    import os
    import time

    for i in range(3):
        s = ProposalStore(tmp_path, f"sess-{i}")
        s.save([Recommendation(domain="d", value_path=f"v{i}", recommended_value="x")])
        os.utime(s.path, (time.time() + i, time.time() + i))  # deterministic mtime order
    deleted = gc_stale_proposals(tmp_path, keep=2)
    assert len(deleted) == 1
    assert deleted[0].name == "proposals-sess-0.json"  # oldest removed
