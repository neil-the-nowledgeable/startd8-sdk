# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""FR-10 (folds Q4) — the cheap model tier for facilitation: de-correlated cheap models, everywhere."""
from __future__ import annotations

import asyncio

import pytest

from startd8.stakeholder_panel import facilitation as F
from startd8.stakeholder_panel.models import PersonaBrief, Roster

from .conftest import ScriptedAgent


@pytest.fixture
def small_roster() -> Roster:
    return Roster(personas=[
        PersonaBrief(role_id="product-owner", display_name="PO", goals=["ship"]),
        PersonaBrief(role_id="end-user", display_name="EU", goals=["use it"]),
    ])


def _persona_factory():
    def factory(b):
        return ScriptedAgent(name=f"persona:{b.role_id}", model="scripted",
                             reply=f"[{b.role_id}] take.\nGROUNDING: grounded")
    return factory


def _facilitator_factory():
    def factory(spec, name, system_prompt):
        return ScriptedAgent(name=name, model=spec, reply=f"[{name}] text")
    return factory


# ── config ───────────────────────────────────────────────────────────────────
def test_default_tier_is_premium(tmp_path):
    assert F.FacilitationConfig(project=tmp_path).tier == "premium"


def test_invalid_tier_rejected(tmp_path):
    with pytest.raises(ValueError):
        F.FacilitationConfig(project=tmp_path, tier="platinum")


# ── the cheap family set is de-correlated + catalog-canonical ────────────────
def test_cheap_families_are_catalog_canonicals():
    assert F.CHEAP_FAMILIES == {
        "claude": "anthropic:claude-haiku-4-5-20251001",
        "gpt": "openai:gpt-5.4-mini",
        "gemini": "gemini:gemini-2.5-flash",
    }
    # distinct providers → de-correlation preserved
    assert len({s.split(":")[0] for s in F.CHEAP_FAMILIES.values()}) == 3


def test_families_for_and_specs():
    assert F.families_for("cheap") is F.CHEAP_FAMILIES
    assert F.families_for("premium") is F.FAMILIES
    assert F.families_for("bogus") is F.FAMILIES  # unknown → premium
    assert F.facilitator_spec_for("cheap") == F.CHEAP_FAMILIES["claude"]
    assert F.outside_view_spec_for("cheap") == F.CHEAP_FAMILIES["gpt"]


def test_assign_models_tier_aware(small_roster):
    briefs = list(small_roster.personas)
    cheap_specs, cheap_fams = F.assign_models(briefs, tier="cheap")
    prem_specs, prem_fams = F.assign_models(briefs)  # default premium
    assert set(cheap_specs.values()) <= set(F.CHEAP_FAMILIES.values())
    assert set(prem_specs.values()) <= set(F.FAMILIES.values())
    assert cheap_fams == prem_fams  # same family ROTATION, different model set


# ── a full offline run in the cheap tier uses cheap models everywhere ────────
def test_cheap_run_records_tier_and_uses_cheap_specs(tmp_path, small_roster):
    cfg = F.FacilitationConfig(project=tmp_path, tier="cheap",
                               ground=False, assumptions=False, outside_view=False)
    fac = F.KickoffFacilitator(cfg, roster=small_roster,
                               persona_agent_factory=_persona_factory(),
                               facilitator_agent_factory=_facilitator_factory())
    session = asyncio.run(fac.run())
    assert session["tier"] == "cheap"
    # facilitator/synth model + persona models are all cheap
    assert session["facilitator_model"] == F.CHEAP_FAMILIES["claude"]
    assert set(session["model_assignment"].values()) <= set(F.CHEAP_FAMILIES.values())
    assert session["synthesis"]["model"] == F.CHEAP_FAMILIES["claude"]


def test_premium_run_unchanged(tmp_path, small_roster):
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, assumptions=False, outside_view=False)
    fac = F.KickoffFacilitator(cfg, roster=small_roster,
                               persona_agent_factory=_persona_factory(),
                               facilitator_agent_factory=_facilitator_factory())
    session = asyncio.run(fac.run())
    assert session["tier"] == "premium"
    assert session["facilitator_model"] == F.FAMILIES["claude"]
    assert set(session["model_assignment"].values()) <= set(F.FAMILIES.values())
