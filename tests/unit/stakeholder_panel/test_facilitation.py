# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""GE-M3a behavioral-equivalence + transcript-contract gate for the promoted facilitation.

These tests are the M3a exit criterion (plan R1-S3): they prove the promoted
``stakeholder_panel/facilitation.py`` produces a transcript with the **same structure** the
un-packaged ``scripts/run_kickoff_panel.py`` did — round sequence, per-round entry shape
(role/model/text/grounding), R0 prep block, and synthesis section — and that persistence now
rides the confined safe-write floor (FR-GE-13) with per-round atomic-replace (FR-UX-17).

Everything runs OFFLINE and $0: persona + facilitator agents are ``ScriptedAgent`` doubles,
so no real model is ever called. (H1/H2/H3 hardening + the FR-GE-12 tension-schema test are
GE-M3b, deliberately out of scope here.)
"""
from __future__ import annotations

import asyncio
import json

import pytest

from startd8.stakeholder_panel import facilitation as F
from startd8.stakeholder_panel.models import PersonaBrief, Roster

from .conftest import ScriptedAgent


@pytest.fixture
def small_roster() -> Roster:
    return Roster(
        personas=[
            PersonaBrief(role_id="product-owner", display_name="Product Owner",
                         goals=["ship the MVP"], out_of_scope=["infra"]),
            PersonaBrief(role_id="platform-eng", display_name="Platform Engineer",
                         goals=["keep the funnel reliable"], known_positions=["cache aggressively"]),
        ]
    )


def _persona_factory():
    """A $0 per-persona agent double; reply echoes the role so entries stay distinguishable."""
    def factory(brief: PersonaBrief):
        return ScriptedAgent(
            name=f"persona:{brief.role_id}",
            model="scripted",
            reply=f"[{brief.role_id}] my take.\nGROUNDING: grounded",
        )

    return factory


def _facilitator_factory():
    """A $0 facilitator/synthesizer double keyed by the pass name."""
    def factory(spec: str, name: str, system_prompt: str):
        return ScriptedAgent(name=name, model=spec, reply=f"[{name}] synthetic prep/synthesis text")

    return factory


def _run(config_project, roster, **kw):
    cfg = F.FacilitationConfig(project=config_project, project_name="a test portal")
    fac = F.KickoffFacilitator(
        cfg,
        roster=roster,
        persona_agent_factory=_persona_factory(),
        facilitator_agent_factory=_facilitator_factory(),
        **kw,
    )
    session = asyncio.run(fac.run())
    return fac, session


# ── behavioral-equivalence: round sequence + entry shape ─────────────────────
def test_round_sequence_and_kinds(tmp_path, small_roster):
    _, session = _run(tmp_path, small_roster)
    assert [r["round_id"] for r in session["rounds"]] == ["R1", "R2", "R3", "R4"]
    assert [r["kind"] for r in session["rounds"]] == [
        "individual", "premortem", "cross_pollination", "final_judgment",
    ]


def test_no_final_judgment_drops_r4(tmp_path, small_roster):
    cfg = F.FacilitationConfig(project=tmp_path, final_judgment=False)
    fac = F.KickoffFacilitator(cfg, roster=small_roster,
                               persona_agent_factory=_persona_factory(),
                               facilitator_agent_factory=_facilitator_factory())
    session = asyncio.run(fac.run())
    assert [r["round_id"] for r in session["rounds"]] == ["R1", "R2", "R3"]


def test_per_round_entry_shape(tmp_path, small_roster):
    _, session = _run(tmp_path, small_roster)
    # 2 roster + 2 adversaries (adversary on by default)
    expected_roles = {"product-owner", "platform-eng", "adversary-exploit", "adversary-discredit"}
    for rnd in session["rounds"]:
        assert {e["role_id"] for e in rnd["entries"]} == expected_roles
        for e in rnd["entries"]:
            # exact §6 per-entry schema — the contract the (future) viewer reads
            assert set(e) == {
                "role_id", "display_name", "model", "prompt", "text", "grounding",
                "flags", "input_tokens", "output_tokens", "cost_usd", "created_at",
            }
            assert e["grounding"] == "grounded"
            assert isinstance(e["input_tokens"], int)
            assert isinstance(e["cost_usd"], float)


def test_entry_model_is_assigned_family_spec(tmp_path, small_roster):
    _, session = _run(tmp_path, small_roster)
    briefs = F.build_briefs(F.FacilitationConfig(project=tmp_path), small_roster)
    specs, _ = F.assign_models(briefs)
    # the transcript records the assigned family spec (mixed-model de-correlation), not the
    # agent's own model string
    for e in session["rounds"][0]["entries"]:
        assert e["model"] == specs[e["role_id"]]
        assert e["model"] in F.FAMILIES.values()


def test_prep_block_and_synthesis_present(tmp_path, small_roster):
    _, session = _run(tmp_path, small_roster)
    assert set(session["prep"]) == {"grounded_context", "key_assumptions", "outside_view"}
    # grounding reads no artifact in tmp_path -> grounded_context stays empty, others fill
    assert session["prep"]["key_assumptions"]
    assert session["prep"]["outside_view"]
    assert session["synthesis"]["model"] == F.FACILITATOR_SPEC
    assert session["synthesis"]["text"]


def test_r3_digest_excludes_self(tmp_path, small_roster):
    _, session = _run(tmp_path, small_roster)
    r3 = next(r for r in session["rounds"] if r["round_id"] == "R3")
    po = next(e for e in r3["entries"] if e["role_id"] == "product-owner")
    # the cross-pollination prompt digests OTHERS' R1, never the persona's own line
    assert "Product Owner:" not in po["prompt"]
    assert "Platform Engineer:" in po["prompt"]


def test_session_top_level_schema(tmp_path, small_roster):
    _, session = _run(tmp_path, small_roster)
    assert set(session) == {
        "session_id", "created_at", "project", "objective", "strategy", "prep",
        "model_assignment", "adversaries", "facilitator_model", "rounds", "synthesis",
        "cost_total_usd",
        # GE-M3b hardening: first-class halt state (H2/H3) + budget ceiling surface (H3)
        "status", "halt", "budget_usd",
        # posture (scrutiny|prototype) + tier (premium|cheap) that produced the transcript
        "posture", "tier",
    }
    assert session["posture"] == "scrutiny"  # default posture recorded
    assert session["tier"] == "premium"  # default tier recorded
    assert session["adversaries"] == ["adversary-exploit", "adversary-discredit"]
    assert session["session_id"].startswith("kp-")
    # a clean full run completes and is not halted
    assert session["status"] == "completed"
    assert session["halt"] is None


# ── transcript contract: path + per-round atomic-replace (FR-UX-1 / FR-UX-17) ─
def test_transcript_at_contract_path(tmp_path, small_roster):
    fac, session = _run(tmp_path, small_roster)
    path = fac.transcript_path(session["session_id"])
    assert path == tmp_path / ".startd8" / "kickoff-panel" / f"{session['session_id']}.json"
    on_disk = json.loads(path.read_text())
    assert on_disk == session  # final flush byte-matches the returned session


def test_per_round_incremental_writes(tmp_path, small_roster):
    """FR-UX-17 live-follow: each completed round lands on disk, never a torn file."""
    seen_round_counts = []
    cfg = F.FacilitationConfig(project=tmp_path)
    holder = {}

    def on_round(rnd):
        # read the file the way a live-follow viewer would, mid-run
        path = holder["fac"].transcript_path(holder["sid"])
        doc = json.loads(path.read_text())  # a torn/partial write would raise here
        seen_round_counts.append(len(doc["rounds"]))

    fac = F.KickoffFacilitator(cfg, roster=small_roster,
                               persona_agent_factory=_persona_factory(),
                               facilitator_agent_factory=_facilitator_factory(),
                               on_round=on_round)
    holder["fac"] = fac

    # capture the session_id the moment R1 is persisted by wrapping _persist
    orig_persist = fac._persist

    def spy_persist(sess):
        holder["sid"] = sess["session_id"]
        orig_persist(sess)

    fac._persist = spy_persist
    asyncio.run(fac.run())
    # rounds accumulate 1,2,3,4 on disk as they complete
    assert seen_round_counts == [1, 2, 3, 4]


def test_persistence_routes_through_safe_write(tmp_path, small_roster, monkeypatch):
    """FR-GE-13: the transcript rides concierge/safe_write, not a direct file write."""
    import startd8.concierge.safe_write as sw

    calls = {"n": 0}
    real = sw.apply_write_plan

    def counting(project_root, writes, *, force=False):
        calls["n"] += 1
        for w in writes:
            assert w.path.startswith(".startd8/kickoff-panel/")  # confined, relative
        return real(project_root, writes, force=force)

    monkeypatch.setattr(sw, "apply_write_plan", counting)
    _run(tmp_path, small_roster)
    # 1 initial in_progress write (t=0, so a fire-and-poll caller sees the transcript immediately)
    # + 4 rounds + 1 final synthesis flush = 6 safe-write calls
    assert calls["n"] == 6


# ── equivalence-by-construction: the script delegates to the module ──────────
def test_script_delegates_to_promoted_module():
    """The CLI is a thin wrapper: it re-exports the module's contract helpers, so the
    script and the package cannot diverge in transcript shape."""
    import importlib.util
    from pathlib import Path as _P

    script = _P(__file__).resolve().parents[3] / "scripts" / "run_kickoff_panel.py"
    spec = importlib.util.spec_from_file_location("run_kickoff_panel", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # the script drives KickoffFacilitator + shares the module's plan/entry helpers
    assert mod.F is F
    assert mod.F.KickoffFacilitator is F.KickoffFacilitator
    assert mod.F._entry is F._entry
