# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""F1 M2 — the facilitate core: dry-run estimate, single-flight, session_id, terminal states (H-1..H-14)."""
from __future__ import annotations

import json
import os
import time

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


# ── #7 live per-round progress ───────────────────────────────────────────────
def test_round_summaries_shape_and_excerpt():
    long = "x" * 500
    rounds = [{"round_id": "R1", "title": "Individual analysis", "kind": "means-ends",
               "entries": [{"role_id": "po", "display_name": "PO", "text": long, "grounding": "grounded"},
                           {"role_id": "adversary-exploit", "display_name": "Adv", "text": "short"}]}]
    out = FR._round_summaries(rounds)
    assert out[0]["round_id"] == "R1" and out[0]["title"] == "Individual analysis"
    e0 = out[0]["entries"][0]
    assert len(e0["excerpt"]) == FR.EXCERPT_CHARS + 1 and e0["excerpt"].endswith("…")  # truncated + ellipsis
    assert e0["is_challenger"] is False and e0["display_name"] == "PO"
    assert out[0]["entries"][1]["is_challenger"] is True  # adversary flagged
    assert out[0]["entries"][1]["excerpt"] == "short"  # short text not truncated / no ellipsis


def test_round_summaries_partial_and_empty():
    assert FR._round_summaries([]) == []
    assert FR._round_summaries(None) == []
    partial = [{"round_id": "R2", "title": "t", "kind": "k", "entries": []}]  # mid-round: 0 entries
    assert FR._round_summaries(partial)[0]["entries"] == []


def test_round_summaries_accepts_objects():
    class _E:
        def __init__(self, **k):
            self.__dict__.update(k)
    class _R:
        def __init__(self, entries):
            self.round_id, self.title, self.kind, self.entries = "R1", "t", "k", entries
    out = FR._round_summaries([_R([_E(role_id="eu", display_name="EU", text="hi", grounding="g")])])
    assert out[0]["entries"][0]["role_id"] == "eu" and out[0]["entries"][0]["excerpt"] == "hi"


def test_status_carries_rounds(tmp_path, roster):
    res = _start_sync(_cfg(tmp_path), roster)
    rounds = FR.facilitate_status(tmp_path, res["session_id"])["rounds"]
    assert isinstance(rounds, list) and rounds  # a completed run has persona rounds
    r1 = next((r for r in rounds if r["round_id"] == "R1"), None)
    assert r1 is not None and r1["entries"]
    e = r1["entries"][0]
    assert set(e) == {"role_id", "display_name", "excerpt", "grounding", "is_challenger"}


# ── #9 stale-run staleness report (observer) ─────────────────────────────────
def _write_transcript(tmp_path, sid, status):
    d = tmp_path / ".startd8" / "kickoff-panel"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.json"
    p.write_text(json.dumps({"session_id": sid, "status": status, "rounds": []}), encoding="utf-8")
    return p


def test_stale_after_secs_resolver(monkeypatch):
    monkeypatch.delenv(FR._STALE_ENV, raising=False)
    assert FR._stale_after_secs() == float(FR.STALE_AFTER_SECS)  # default
    monkeypatch.setenv(FR._STALE_ENV, "120")
    assert FR._stale_after_secs() == 120.0  # env override
    monkeypatch.setenv(FR._STALE_ENV, "nope")
    assert FR._stale_after_secs() == float(FR.STALE_AFTER_SECS)  # non-numeric → default
    monkeypatch.setenv(FR._STALE_ENV, "0")
    assert FR._stale_after_secs() == float(FR.STALE_AFTER_SECS)  # non-positive → default (never disabled)


def test_nonterminal_old_transcript_is_stalled(tmp_path):
    p = _write_transcript(tmp_path, "s1", "in_progress")
    os.utime(p, (0, time.time() - 700))  # last write 700s ago (> 600 default)
    st = FR.facilitate_status(tmp_path, "s1")
    assert st["status"] == "in_progress" and st["stalled"] is True and st["is_terminal"] is False


def test_nonterminal_fresh_transcript_not_stalled(tmp_path):
    _write_transcript(tmp_path, "s1", "in_progress")  # just written → fresh
    assert FR.facilitate_status(tmp_path, "s1")["stalled"] is False


def test_terminal_run_never_stalled(tmp_path):
    p = _write_transcript(tmp_path, "s1", "completed")
    os.utime(p, (0, time.time() - 9999))  # ancient, but terminal → never stalled
    st = FR.facilitate_status(tmp_path, "s1")
    assert st["is_terminal"] is True and st["stalled"] is False


def test_stale_threshold_env_override(tmp_path, monkeypatch):
    p = _write_transcript(tmp_path, "s1", "in_progress")
    os.utime(p, (0, time.time() - 30))  # 30s old
    monkeypatch.setenv(FR._STALE_ENV, "10")  # threshold 10s → 30s-old is stalled
    assert FR.facilitate_status(tmp_path, "s1")["stalled"] is True


# ── #6 consensus signal on the poll payload ──────────────────────────────────
def test_status_carries_consensus(tmp_path, roster):
    res = _start_sync(_cfg(tmp_path), roster)
    c = FR.facilitate_status(tmp_path, res["session_id"])["consensus"]
    assert c["basis"] == "lexical-r1"
    assert c["label"] in {"high", "mixed", "low", "n/a"}
    assert c["n"] >= 2 and c["label"] != "n/a"  # 2 non-challenger personas → a real signal
    assert set(c) == {"label", "score", "n", "basis"}


def test_status_consensus_na_for_unknown_session(tmp_path):
    # An unknown session short-circuits before the transcript load → no consensus key (status "unknown").
    assert "consensus" not in FR.facilitate_status(tmp_path, "kp-nope")


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


# ── #4 env-configurable cap ──────────────────────────────────────────────────
def test_max_concurrent_env_override(monkeypatch):
    monkeypatch.delenv(FR._CAP_ENV, raising=False)
    assert FR._max_concurrent_facilitations() == FR.MAX_CONCURRENT_FACILITATIONS  # default
    monkeypatch.setenv(FR._CAP_ENV, "9")
    assert FR._max_concurrent_facilitations() == 9  # env override honored
    monkeypatch.setenv(FR._CAP_ENV, "not-an-int")
    assert FR._max_concurrent_facilitations() == FR.MAX_CONCURRENT_FACILITATIONS  # non-int → default
    monkeypatch.setenv(FR._CAP_ENV, "-3")
    assert FR._max_concurrent_facilitations() == FR.MAX_CONCURRENT_FACILITATIONS  # negative → default


def test_max_concurrent_env_zero_blocks(tmp_path, roster, monkeypatch):
    monkeypatch.setenv(FR._CAP_ENV, "0")  # operator throttles to zero → cap fires
    with pytest.raises(FR.FacilitationCapError):
        _start_sync(_cfg(tmp_path), roster)


# ── #5 outside-view cache (Mottainai) ────────────────────────────────────────
def test_ov_cache_key_and_roundtrip(tmp_path):
    # Key binds (objective, strategy, model) — a model switch mints a DIFFERENT key.
    k1 = F._ov_cache_key("ship X", "lean", "premium-model")
    k2 = F._ov_cache_key("ship X", "lean", "cheap-model")
    assert k1 != k2
    assert F._ov_cache_load(tmp_path, k1) is None  # miss on empty
    F._ov_cache_store(tmp_path, k1, "base rate 40%")
    assert F._ov_cache_load(tmp_path, k1) == "base rate 40%"  # round-trip
    assert F._ov_cache_load(tmp_path, k2) is None  # different key still a miss


def test_ov_cache_corrupt_is_miss(tmp_path):
    p = tmp_path / F.TRANSCRIPT_SUBDIR / F._OV_CACHE_FILE
    p.parent.mkdir(parents=True)
    p.write_text("{ not json", encoding="utf-8")
    assert F._ov_cache_load(tmp_path, "anykey") is None  # corrupt degrades to miss, never raises


def _run_ov(tmp_path, roster, ov_calls, *, cap):
    """Run a full facilitation inline (outside_view ON) counting outside-view agent constructions."""
    def facilitator_factory():
        def factory(spec, name, sys):
            if name == "outside-view":
                ov_calls.append(spec)
            return ScriptedAgent(name=name, model=spec, reply=f"[{name}] base rate 40%")
        return factory

    cfg = F.FacilitationConfig(
        project=tmp_path, ground=False, assumptions=False, outside_view=True,
        objective="ship X", strategy="lean", cap=cap)
    return FR.start_facilitation(
        cfg, roster, thread_starter=lambda target: target(),
        persona_agent_factory=_persona_factory(), facilitator_agent_factory=facilitator_factory())


def test_outside_view_reused_across_runs(tmp_path, roster):
    # Same project + objective/strategy but a different `cap` → a DIFFERENT run_key (no dedup), yet the
    # outside-view inputs are identical → the second run reuses the cache and does NOT re-call the model.
    ov_calls: list = []
    _run_ov(tmp_path, roster, ov_calls, cap=0)
    assert len(ov_calls) == 1  # computed once
    assert (tmp_path / F.TRANSCRIPT_SUBDIR / F._OV_CACHE_FILE).is_file()
    _run_ov(tmp_path, roster, ov_calls, cap=1)  # distinct run_key → really executes
    assert len(ov_calls) == 1  # still 1 — the premium outside-view call was skipped (Mottainai)


def test_outside_view_nocache_env_forces_recompute(tmp_path, roster, monkeypatch):
    ov_calls: list = []
    _run_ov(tmp_path, roster, ov_calls, cap=0)
    monkeypatch.setenv(F._OV_NOCACHE_ENV, "1")  # opt out → recompute even on a hit
    _run_ov(tmp_path, roster, ov_calls, cap=1)
    assert len(ov_calls) == 2  # the escape hatch bypassed the cache


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


# ── #1 the facilitation cost gauge ───────────────────────────────────────────
def test_record_facilitation_cost_labels_project_posture_tier(monkeypatch):
    """The gauge is set AND the cumulative counter (#10) is add()ed, both with {project,posture,tier}."""
    from startd8.kickoff_experience import metrics as M

    captured = {}

    class _FakeGauge:
        def set(self, value, attrs):
            captured["gauge"] = (value, attrs)

    class _FakeCounter:
        def add(self, value, attrs):
            captured["counter"] = (value, attrs)  # #10 cumulative spend

    monkeypatch.setattr(M, "_gauges", lambda: {"facilitation_cost": _FakeGauge(),
                                               "facilitation_cost_total": _FakeCounter()})
    ok = M.record_facilitation_cost(project="household", cost_usd=0.43, posture="prototype", tier="cheap")
    assert ok is True
    labels = {"project": "household", "posture": "prototype", "tier": "cheap"}
    assert captured["gauge"] == (0.43, labels)
    assert captured["counter"] == (0.43, labels)  # #10 — counter got the same spend + labels


def test_record_facilitation_cost_noop_without_collector(monkeypatch):
    """No collector → no gauges → best-effort no-op, never raises, returns False."""
    from startd8.kickoff_experience import metrics as M

    monkeypatch.setattr(M, "_gauges", lambda: None)
    assert M.record_facilitation_cost(project="p", cost_usd=1.0) is False


def test_worker_emits_facilitation_cost_at_completion(tmp_path, roster, monkeypatch):
    """The worker emits the facilitation cost (labeled by posture/tier) once, at terminal state."""
    from startd8.kickoff_experience import metrics as M

    calls = []
    monkeypatch.setattr(M, "record_facilitation_cost", lambda **kw: calls.append(kw) or True)
    _start_sync(_cfg(tmp_path, posture="prototype", tier="cheap"), roster)
    assert len(calls) == 1
    assert calls[0]["posture"] == "prototype" and calls[0]["tier"] == "cheap"
    assert calls[0]["cost_usd"] is not None  # cost read from the persisted transcript
