# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Regression tests for the facilitation cost-attribution bug (the ``Session cost: $0.0000`` report).

Root cause: the runner never wired a ``cost_tracker`` into ``KickoffFacilitator``, so every answer's
``cost_usd`` short-circuited to 0 and the session total was always $0 — which ALSO silently defeated
the ``--budget-usd`` cap (it reads the same total). These tests pin: a wired tracker produces non-zero
cost, no tracker yields $0 (documenting why the runner must wire one), and the budget cap actually
trips once cost is real.
"""

from __future__ import annotations

import asyncio

from startd8.costs import CostTracker, PricingService
from startd8.costs.store import CostStore
from startd8.stakeholder_panel import facilitation as F
from startd8.stakeholder_panel.models import PersonaBrief, Roster

from .conftest import ScriptedAgent


def _roster() -> Roster:
    return Roster(
        personas=[
            PersonaBrief(role_id="product-owner", display_name="Product Owner", goals=["ship the MVP"]),
            PersonaBrief(role_id="platform-eng", display_name="Platform Engineer", goals=["reliability"]),
        ]
    )


def _persona_factory():
    # model is the provider-prefixed spec, exactly as a real agent reports it (see the mismapping fix).
    def factory(brief: PersonaBrief):
        return ScriptedAgent(
            name=f"persona:{brief.role_id}",
            model="anthropic:claude-opus-4-8",
            reply=f"[{brief.role_id}] my take.\nGROUNDING: grounded",
        )

    return factory


def _facilitator_factory():
    def factory(spec: str, name: str, system_prompt: str):
        return ScriptedAgent(name=name, model=spec, reply=f"[{name}] synthetic text")

    return factory


def _tracker(tmp_path):
    return CostTracker(CostStore(tmp_path / "costs.db"), PricingService())


def _facilitator(tmp_path, **kw):
    cfg = F.FacilitationConfig(project=tmp_path, project_name="a test portal", **kw.pop("cfg_kw", {}))
    return F.KickoffFacilitator(
        cfg,
        roster=_roster(),
        persona_agent_factory=_persona_factory(),
        facilitator_agent_factory=_facilitator_factory(),
        **kw,
    )


def test_cost_total_is_nonzero_when_tracker_wired(tmp_path):
    fac = _facilitator(tmp_path, cost_tracker=_tracker(tmp_path))
    session = asyncio.run(fac.run())
    assert session["cost_total_usd"] > 0.0
    assert any(e["cost_usd"] > 0.0 for r in session["rounds"] for e in r["entries"])


def test_cost_total_is_zero_without_a_tracker(tmp_path):
    # Documents the pre-fix behavior — this is exactly why the runner MUST wire a tracker.
    fac = _facilitator(tmp_path)  # no cost_tracker
    session = asyncio.run(fac.run())
    assert session["cost_total_usd"] == 0.0


def test_budget_cap_trips_once_cost_is_real(tmp_path):
    # A tiny budget must halt the run. This is impossible when cost is always $0 (the guardrail bug):
    # the cap reads session["cost_total_usd"], so a broken tracker leaves --budget-usd inert.
    fac = _facilitator(tmp_path, cost_tracker=_tracker(tmp_path), cfg_kw={"budget_usd": 0.0001})
    session = asyncio.run(fac.run())
    assert session.get("status") == "halted"
    assert session["halt"]["reason"] == "budget_cap"
