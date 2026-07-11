# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""GE-M3b hardening tests for the promoted facilitation orchestrator (FR-GE-10 H1/H2/H3 +
FR-GE-12), parent-owned by PROJECT_START_REQUIREMENTS FR-13c.

Everything runs OFFLINE + $0: persona / facilitator agents are ``ScriptedAgent`` doubles and the
per-answer cost is a ``SpyTracker`` (no real model, no network). Covers:
  * H1  — grounding reuses the kernel ``survey`` inventory; degrade-to-schema-with-warning.
  * H2  — assumptions-check-as-GATE: ``>= threshold`` high-impact/low-confidence ⇒ halted session.
  * H3  — per-round + session-total cost surfaced; a configured budget ceiling hard-halts.
  * FR-GE-12 — structural anti-smoothing: a named raw-round ``tension_id`` must survive as OPEN.
"""
from __future__ import annotations

import asyncio

import pytest

from startd8.stakeholder_panel import facilitation as F
from startd8.stakeholder_panel.models import PersonaBrief, Roster

from .conftest import ScriptedAgent, SpyTracker


@pytest.fixture
def small_roster() -> Roster:
    return Roster(
        personas=[
            PersonaBrief(role_id="product-owner", display_name="Product Owner", goals=["ship"]),
            PersonaBrief(role_id="platform-eng", display_name="Platform Engineer", goals=["reliable"]),
        ]
    )


def _persona_factory(marker_role: str = "", marker: str = ""):
    def factory(brief: PersonaBrief):
        extra = f"\n{marker}" if brief.role_id == marker_role and marker else ""
        return ScriptedAgent(name=f"persona:{brief.role_id}", model="scripted",
                             reply=f"[{brief.role_id}] my take.{extra}\nGROUNDING: grounded")
    return factory


def _facilitator(*, synth_reply="## Tensions\n(none)", assumptions_reply="[assumptions] prep",
                 echo=False):
    """A $0 facilitator/synth double. Keys the synth pass by ``_SYNTH_SYS`` (grounding and synth
    share the name 'facilitator'), the assumptions pass by name."""
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


# ══════════════════════ H1 — artifact-grounding fidelity ═════════════════════
def test_gather_artifact_reuses_kernel_survey(tmp_path):
    """H1: grounding reads the REAL system via ``concierge.build_survey`` (models inventory)."""
    (tmp_path / "models.py").write_text("from pydantic import BaseModel\nclass Widget(BaseModel):\n    x: int\n")
    artifact, warning = F._gather_artifact(tmp_path)
    assert warning == ""
    assert "Live system inventory (kernel survey)" in artifact
    assert "Pydantic model files (1)" in artifact
    assert "models.py" in artifact


def test_gather_artifact_degrades_with_explicit_warning(tmp_path, monkeypatch):
    """H1: if the live inventory can't be read, degrade to schema-only WITH a warning (not silent)."""
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text("model User { id Int @id }\n")

    import startd8.concierge.core as cc

    def boom(_root):
        raise OSError("survey unavailable")

    monkeypatch.setattr(cc, "build_survey", boom)
    artifact, warning = F._gather_artifact(tmp_path)
    assert "DEGRADED" in warning and "schema" in warning.lower()
    assert "Live system inventory" not in artifact  # survey never ran
    assert "schema.prisma" in artifact  # but the static schema still grounds it


def test_grounded_context_carries_survey_inventory(tmp_path, small_roster):
    """H1 integration: the grounded_context reflects the survey inventory, not the schema alone."""
    (tmp_path / "models.py").write_text("from pydantic import BaseModel\nclass Order(BaseModel):\n    id: int\n")
    cfg = F.FacilitationConfig(project=tmp_path, assumptions=False, outside_view=False)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(echo=True))
    assert "Live system inventory (kernel survey)" in session["prep"]["grounded_context"]
    assert "models.py" in session["prep"]["grounded_context"]


def test_grounded_context_starts_with_warning_when_degraded(tmp_path, small_roster, monkeypatch):
    import startd8.concierge.core as cc
    monkeypatch.setattr(cc, "build_survey", lambda _r: (_ for _ in ()).throw(OSError("down")))
    cfg = F.FacilitationConfig(project=tmp_path, assumptions=False, outside_view=False)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(echo=True))
    assert session["prep"]["grounded_context"].startswith("WARNING (H1 artifact-grounding DEGRADED)")


# ══════════════════════ H2 — assumptions-check-as-GATE ═══════════════════════
_TWO_RISKY = (
    "1. Demand exists — CONFIDENCE (low), IMPACT IF WRONG (high).\n"
    "2. Catalog is complete — CONFIDENCE (low), IMPACT IF WRONG (high).\n"
    "3. Payments work — CONFIDENCE (high), IMPACT IF WRONG (low).\n"
)
_ONE_RISKY = (
    "1. Demand exists — CONFIDENCE (low), IMPACT IF WRONG (high).\n"
    "2. Payments work — CONFIDENCE (high), IMPACT IF WRONG (low).\n"
)


def test_parse_assumptions_counts_high_impact_low_confidence():
    risky = F.risky_assumptions(_TWO_RISKY)
    assert len(risky) == 2
    assert all(a["high_impact"] and a["low_confidence"] for a in risky)
    assert len(F.risky_assumptions(_ONE_RISKY)) == 1


def test_assumptions_gate_halts_and_skips_rounds(tmp_path, small_roster):
    """H2: >= threshold (default 2) risky assumptions ⇒ HALT before spending R1–R5."""
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False)
    fac, session = _run(small_roster, cfg,
                        persona_agent_factory=_persona_factory(),
                        facilitator_agent_factory=_facilitator(assumptions_reply=_TWO_RISKY))
    assert session["status"] == "halted"
    assert session["halt"]["reason"] == "assumptions_gate"
    assert session["halt"]["threshold"] == 2
    assert session["halt"]["risky_count"] == 2
    assert session["rounds"] == []  # rounds were NOT spent
    assert session["synthesis"] is None
    # first-class transcript state: the halted session is persisted for the viewer to render
    import json
    on_disk = json.loads(fac.transcript_path(session["session_id"]).read_text())
    assert on_disk["status"] == "halted"


def test_assumptions_threshold_is_tunable(tmp_path, small_roster):
    """The default is 2; raising it lets a 2-risky check through (R2-F4 configurable field)."""
    assert F.FacilitationConfig(project=tmp_path).assumptions_halt_threshold == 2
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False,
                               assumptions_halt_threshold=5)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(assumptions_reply=_TWO_RISKY))
    assert session["status"] == "completed"
    assert [r["round_id"] for r in session["rounds"]] == ["R1", "R2", "R3", "R4"]


def test_assumptions_below_threshold_does_not_halt(tmp_path, small_roster):
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(assumptions_reply=_ONE_RISKY))
    assert session["status"] == "completed"


# ══════════════════════ H3 — cost tracking + budget halt ═════════════════════
def test_per_round_and_session_cost_surfaced(tmp_path, small_roster):
    """H3: per-round cost_usd aggregates the panel's per-answer attribution; session total sums them."""
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator(),
                      cost_tracker=SpyTracker(total_cost=0.01))
    # 4 participants (2 roster + 2 adversaries) * $0.01 = $0.04 per round
    for rnd in session["rounds"]:
        assert rnd["cost_usd"] == pytest.approx(0.04)
    assert session["cost_total_usd"] == pytest.approx(0.16)  # 4 rounds


def test_zero_cost_without_tracker(tmp_path, small_roster):
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False)
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory(),
                      facilitator_agent_factory=_facilitator())
    assert session["cost_total_usd"] == 0.0
    assert all(r["cost_usd"] == 0.0 for r in session["rounds"])


def test_budget_cap_hard_halts_before_next_round(tmp_path, small_roster):
    """H3: a configured budget ceiling is a cumulative-abort — refused before the round whose
    start would exceed the cap; the remaining rounds are NOT spent."""
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False, budget_usd=0.05)
    fac, session = _run(small_roster, cfg,
                        persona_agent_factory=_persona_factory(),
                        facilitator_agent_factory=_facilitator(),
                        cost_tracker=SpyTracker(total_cost=0.01))
    # R1 -> $0.04 (<0.05, proceed); R2 -> $0.08 (>=0.05); halt fires before R3
    assert [r["round_id"] for r in session["rounds"]] == ["R1", "R2"]
    assert session["status"] == "halted"
    assert session["halt"]["reason"] == "budget_cap"
    assert session["halt"]["budget_usd"] == 0.05
    assert session["halt"]["spent_usd"] == pytest.approx(0.08)
    assert session["synthesis"] is None
    import json
    assert json.loads(fac.transcript_path(session["session_id"]).read_text())["status"] == "halted"


# ══════════════════════ FR-GE-12 — anti-smoothing (structural) ═══════════════
def test_tension_extraction_and_open_detection():
    rounds = [{"entries": [{"text": "worry [[tension:T1|pricing vs speed]] here"},
                           {"text": "also [[tension:T2|scope]]"}]}]
    assert F.extract_raw_tensions(rounds) == {"T1": "pricing vs speed", "T2": "scope"}
    assert F.synthesis_open_tensions("- T1 pricing vs speed — OPEN\n- T2 resolved") == {"T1"}
    assert F.check_anti_smoothing(rounds, "T1 — OPEN") == ["T2"]  # T2 smoothed away


def test_named_tension_survives_synthesis_as_open(tmp_path, small_roster):
    """FR-GE-12: a raw-round tension_id preserved as OPEN in synthesis ⇒ no smoothing flagged."""
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False)
    synth = "## Tensions\n- T1 pricing vs speed — OPEN (needs human adjudication)\n"
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory("product-owner", "[[tension:T1|pricing vs speed]]"),
                      facilitator_agent_factory=_facilitator(synth_reply=synth))
    assert session["synthesis"]["raw_tension_ids"] == ["T1"]
    assert session["synthesis"]["open_tension_ids"] == ["T1"]
    assert session["synthesis"]["smoothed_tension_ids"] == []


def test_smoothed_tension_is_flagged_structurally(tmp_path, small_roster):
    """FR-GE-12: if the synthesis drops a named raw tension, the smoothing is caught (not prose-match)."""
    cfg = F.FacilitationConfig(project=tmp_path, ground=False, outside_view=False)
    synth = "## Tensions\nAll concerns were reconciled; the team is aligned.\n"  # T1 smoothed away
    _, session = _run(small_roster, cfg,
                      persona_agent_factory=_persona_factory("product-owner", "[[tension:T1|pricing vs speed]]"),
                      facilitator_agent_factory=_facilitator(synth_reply=synth))
    assert session["synthesis"]["raw_tension_ids"] == ["T1"]
    assert session["synthesis"]["smoothed_tension_ids"] == ["T1"]  # the failure is machine-checkable
