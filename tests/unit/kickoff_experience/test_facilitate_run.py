# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""F1 M2 — the facilitate core: dry-run estimate, single-flight, session_id, terminal states (H-1..H-14)."""
from __future__ import annotations

import pytest

from startd8.kickoff_experience import facilitate_run as FR
from startd8.stakeholder_panel import facilitation as F
from startd8.stakeholder_panel.models import PersonaBrief, Roster
from tests.unit.stakeholder_panel.conftest import ScriptedAgent


@pytest.fixture
def roster() -> Roster:
    return Roster(personas=[
        PersonaBrief(role_id="po", display_name="PO", goals=["ship"]),
        PersonaBrief(role_id="eu", display_name="EU", goals=["use"]),
    ])


def _persona_factory():
    return lambda b: ScriptedAgent(name=b.role_id, model="s", reply=f"[{b.role_id}] t.\nGROUNDING: grounded")


def _facilitator_factory():
    return lambda spec, name, sys: ScriptedAgent(name=name, model=spec, reply=f"[{name}] text")


def _cfg(tmp_path, **kw):
    return F.FacilitationConfig(project=tmp_path, ground=False, assumptions=False, outside_view=False, **kw)


def _start_sync(cfg, roster, **kw):
    """Run the worker inline (synchronous thread_starter) with $0 scripted agents."""
    return FR.start_facilitation(
        cfg, roster, thread_starter=lambda target: target(),
        persona_agent_factory=_persona_factory(), facilitator_agent_factory=_facilitator_factory(), **kw)


# ── H-10/H-11 dry-run ────────────────────────────────────────────────────────
def test_dry_run_round_weighted_and_binds_posture_tier(tmp_path, roster):
    premium = FR.facilitate_dry_run(_cfg(tmp_path), roster)
    cheap = FR.facilitate_dry_run(_cfg(tmp_path, tier="cheap"), roster)
    proto = FR.facilitate_dry_run(_cfg(tmp_path, posture="prototype"), roster)
    # H-10: run_key binds posture AND tier — a cheap/prototype preview mints a DIFFERENT key
    assert premium.run_key != cheap.run_key
    assert premium.run_key != proto.run_key
    # H-11: round-weighted — the estimate exceeds a flat per-call × projected_calls (R3/R5 heavier)
    assert premium.estimated_cost > 0
    assert premium.tier == "premium" and cheap.tier == "cheap"
    assert set(cheap.models.values()) <= set(F.CHEAP_FAMILIES.values())


# ── H-2/H-3 kickoff → completed, deterministic session_id ────────────────────
def test_start_completes_with_deterministic_session_id(tmp_path, roster):
    res = _start_sync(_cfg(tmp_path), roster)
    assert res["session_id"] == FR.facilitate_session_id(res["run_key"])  # H-2 deterministic
    assert res["deduped"] is False
    # worker ran inline → transcript is terminal + completed
    status = FR.facilitate_status(tmp_path, res["session_id"])
    assert status["status"] == "completed" and status["is_terminal"] is True
    assert status["synthesis"]  # a completed run has synthesis text


# ── H-1/H-4 single-flight — a duplicate run_key does NOT re-spawn ─────────────
def test_single_flight_dedupes(tmp_path, roster):
    first = _start_sync(_cfg(tmp_path), roster)
    spawns = []
    second = FR.start_facilitation(
        _cfg(tmp_path), roster,
        thread_starter=lambda target: spawns.append(target),  # record, do NOT run
        persona_agent_factory=_persona_factory(), facilitator_agent_factory=_facilitator_factory())
    assert second["session_id"] == first["session_id"]
    assert second["deduped"] is True
    assert spawns == []  # no second worker spawned


# ── H-10 forged/mismatched key → RunKeyMismatchError ─────────────────────────
def test_run_key_mismatch_rejected(tmp_path, roster):
    from startd8.kickoff_experience.stakeholder_run import IdempotencyStore
    # reserve the run_key with DIFFERENT params → a later reserve with our params must reject
    cfg = _cfg(tmp_path)
    rk = FR.facilitate_run_key(posture=cfg.posture, tier=cfg.tier, cap=None, budget_usd=cfg.budget_usd,
                               rv=FR.roster_version(roster))
    IdempotencyStore(tmp_path).reserve(rk, "DIFFERENT-params-hash")
    with pytest.raises(Exception):  # RunKeyMismatchError
        _start_sync(cfg, roster)


# ── H-5 concurrency cap ──────────────────────────────────────────────────────
def test_concurrency_cap(tmp_path, roster, monkeypatch):
    monkeypatch.setattr(FR, "MAX_CONCURRENT_FACILITATIONS", 0)
    with pytest.raises(FR.FacilitationCapError):
        _start_sync(_cfg(tmp_path), roster)


# ── H-15 status of an unknown session ────────────────────────────────────────
def test_status_unknown_session(tmp_path):
    assert FR.facilitate_status(tmp_path, "kp-nope")["status"] == "unknown"


# ── /code-review CRITICAL: a cap-raise must ROLL BACK the reservation (no lost run) ──
def test_cap_raise_releases_reservation_so_retry_respawns(tmp_path, roster, monkeypatch):
    monkeypatch.setattr(FR, "MAX_CONCURRENT_FACILITATIONS", 0)
    with pytest.raises(FR.FacilitationCapError):
        _start_sync(_cfg(tmp_path), roster)
    # the reservation was rolled back → a retry (cap freed) spawns for REAL, not deduped-to-nothing
    monkeypatch.setattr(FR, "MAX_CONCURRENT_FACILITATIONS", 4)
    res = _start_sync(_cfg(tmp_path), roster)
    assert res["deduped"] is False
    assert FR.facilitate_status(tmp_path, res["session_id"])["status"] == "completed"


# ── /code-review MEDIUM: dedup during worker-startup reports in_progress, not `unknown` ──
def test_dedup_before_transcript_reports_in_progress(tmp_path, roster):
    from startd8.kickoff_experience.stakeholder_run import IdempotencyStore
    cfg = _cfg(tmp_path)
    rv = FR.roster_version(roster)
    rk = FR.facilitate_run_key(posture=cfg.posture, tier=cfg.tier, cap=None, budget_usd=cfg.budget_usd, rv=rv)
    ph = FR._params_hash(posture=cfg.posture, tier=cfg.tier, cap=None, budget_usd=cfg.budget_usd, rv=rv)
    IdempotencyStore(tmp_path).reserve(rk, ph, session_id=FR.facilitate_session_id(rk))  # reserved, no run
    res = FR.start_facilitation(  # dedups; transcript absent → must fall back to in_progress
        cfg, roster, thread_starter=lambda target: None,
        persona_agent_factory=_persona_factory(), facilitator_agent_factory=_facilitator_factory())
    assert res["deduped"] is True and res["status"] == "in_progress"


# ── /code-review MEDIUM: a corrupt transcript degrades the poll to `error`, not a 500 ──
def test_status_corrupt_transcript_degrades(tmp_path):
    d = tmp_path / ".startd8" / "kickoff-panel"
    d.mkdir(parents=True)
    (d / "kp-bad.json").write_text("{ not json", encoding="utf-8")
    assert FR.facilitate_status(tmp_path, "kp-bad")["status"] == "error"


# ── FR-8 e2e: facilitate → completed → the transcript feeds the synthesis-bridge triage ──
def test_completed_facilitation_feeds_triage(tmp_path, roster):
    res = _start_sync(_cfg(tmp_path), roster)
    status = FR.facilitate_status(tmp_path, res["session_id"])
    assert status["status"] == "completed"
    from startd8.kickoff_view import KickoffViewService
    from startd8.stakeholder_panel.synthesis_bridge import build_triage
    transcript = KickoffViewService(str(tmp_path)).load(res["session_id"])
    report = build_triage(transcript)  # the session id round-trips into the bridge (no error)
    assert report.session_id == res["session_id"]


# ── H-7 a crashing facilitator → terminal `error`, not stuck in_progress ─────
def test_error_terminal_state(tmp_path, roster):
    def boom_persona():
        def factory(b):
            raise RuntimeError("agent build failed")
        return factory
    res = FR.start_facilitation(
        _cfg(tmp_path), roster, thread_starter=lambda target: target(),
        persona_agent_factory=boom_persona(), facilitator_agent_factory=_facilitator_factory())
    status = FR.facilitate_status(tmp_path, res["session_id"])
    assert status["status"] == "error" and status["is_terminal"] is True
