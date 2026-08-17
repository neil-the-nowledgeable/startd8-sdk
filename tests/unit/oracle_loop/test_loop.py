"""FR-4/FR-5 — regen-with-feedback wire, fail-closed termination, cumulative budget, stall."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.oracle_loop import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_SKIP,
    OracleVerdict,
)
from startd8.oracle_loop.grammar import KIND_ASSERTION, KIND_ONESHOT
from startd8.oracle_loop.loop import (
    CAUSE_BUDGET,
    CAUSE_MAX_ITERATIONS,
    CAUSE_NO_FITNESS,
    CAUSE_PASS,
    CAUSE_REGEN_REJECTED,
    CAUSE_STALL,
    GenOutcome,
    _StallDetector,
    exit_code_for_cause,
    run_build_to_spec_loop,
)

pytestmark = pytest.mark.unit

_SPEC = Path(__file__).parent / "fixtures" / "passing_spec.md"


def _v(fr_id, verdict, kind=KIND_ONESHOT, reason=""):
    return OracleVerdict(
        fr_id=fr_id, kind=kind, verdict=verdict, reason=reason, command_or_probe=f"cmd-{fr_id}"
    )


def _passing_verdicts():
    return [
        _v("FR-1", VERDICT_PASS),
        _v("FR-2", VERDICT_PASS, kind="service"),
        _v("FR-3", VERDICT_SKIP, kind=KIND_ASSERTION),
    ]


def _failing_verdicts():
    return [
        _v("FR-1", VERDICT_FAIL, reason="exit 1: assert failed"),
        _v("FR-2", VERDICT_PASS, kind="service"),
        _v("FR-3", VERDICT_SKIP, kind=KIND_ASSERTION),
    ]


def test_passing_first_iteration(tmp_path):
    gen = lambda fb: GenOutcome(app_root=tmp_path, cost_usd=0.5)
    dep = lambda root: _passing_verdicts()
    report = run_build_to_spec_loop(
        _SPEC, generate_fn=gen, deploy_fn=dep, max_iterations=3, enabled=True
    )
    assert report.terminal_cause == CAUSE_PASS
    assert exit_code_for_cause(report.terminal_cause) == 0
    assert report.iterations == 1
    assert report.coverage.coverage == pytest.approx(2 / 3)


def test_convergence_fail_then_fix(tmp_path):
    """FR-4: first gen fails the rung, feedback carries the intent+assertion, second gen passes."""
    seen_feedback = {}
    rounds = {"n": 0}

    def gen(fb):
        rounds["n"] += 1
        seen_feedback["fb"] = fb
        return GenOutcome(app_root=tmp_path, cost_usd=0.3)

    def dep(root):
        return _failing_verdicts() if rounds["n"] == 1 else _passing_verdicts()

    report = run_build_to_spec_loop(
        _SPEC, generate_fn=gen, deploy_fn=dep,
        fr_intent={"FR-1": "the app health function returns ok"},
        max_iterations=5, enabled=True,
    )
    assert report.terminal_cause == CAUSE_PASS
    assert report.iterations == 2
    # The regen feedback named the intent + assertion, not a bare stderr (R1-F7).
    fb = seen_feedback["fb"]
    assert fb and fb[0].fr_id == "FR-1"
    assert "health function returns ok" in fb[0].intent
    rendered = fb[0].render()
    assert "Behavioral goal" in rendered and "Observed" in rendered


def test_regen_rejected_is_fatal_not_a_stall_round(tmp_path):
    """R1-S5: a seam-guard reject → fatal regen_rejected, never burns iterations as stall."""
    def gen(fb):
        return GenOutcome(app_root=tmp_path, regen_rejected=True, reject_reason="seam write-guard")

    report = run_build_to_spec_loop(
        _SPEC, generate_fn=gen, deploy_fn=lambda r: _failing_verdicts(),
        max_iterations=5, enabled=True,
    )
    assert report.terminal_cause == CAUSE_REGEN_REJECTED
    assert report.iterations == 1


def test_cumulative_budget_caps_total_spend(tmp_path):
    """FR-5/R1-S6: budget is cumulative across iterations, not per-invocation."""
    def gen(fb):
        return GenOutcome(app_root=tmp_path, cost_usd=0.6)

    report = run_build_to_spec_loop(
        _SPEC, generate_fn=gen, deploy_fn=lambda r: _failing_verdicts(),
        max_iterations=10, max_cost_usd=1.0, enabled=True,
    )
    assert report.terminal_cause == CAUSE_BUDGET
    # Two iterations (0.6 + 0.6 = 1.2 >= 1.0) — cumulative, not a fresh ceiling each round.
    assert report.iterations == 2
    assert report.cumulative_cost_usd == pytest.approx(1.2)


def test_max_iterations_terminal(tmp_path):
    report = run_build_to_spec_loop(
        _SPEC, generate_fn=lambda fb: GenOutcome(app_root=tmp_path),
        deploy_fn=lambda r: _failing_verdicts(),
        max_iterations=2, stall_patience=99, enabled=True,
    )
    assert report.terminal_cause == CAUSE_MAX_ITERATIONS
    assert report.iterations == 2


def test_rotating_failures_trip_stall(tmp_path):
    """R1-F4: {A},{B},{A},{B}… never reduces the failure count → stall (set-equality would miss)."""
    seq = [
        [_v("FR-1", VERDICT_FAIL, reason="a"), _v("FR-2", VERDICT_PASS, kind="service")],
        [_v("FR-1", VERDICT_PASS), _v("FR-2", VERDICT_FAIL, kind="service", reason="b")],
    ]
    rounds = {"n": 0}

    def dep(root):
        v = seq[rounds["n"] % 2]
        rounds["n"] += 1
        return v

    report = run_build_to_spec_loop(
        _SPEC, generate_fn=lambda fb: GenOutcome(app_root=tmp_path),
        deploy_fn=dep, max_iterations=20, stall_patience=3, enabled=True,
    )
    assert report.terminal_cause == CAUSE_STALL


def test_set_equality_detector_would_not_trip_on_rotation():
    """Characterization: a naive set-equality tracker misses the rotating-failure loop."""
    rounds = [{"FR-1"}, {"FR-2"}, {"FR-1"}, {"FR-2"}]
    tripped = any(rounds[i] == rounds[i - 1] for i in range(1, len(rounds)))
    assert not tripped  # proves the weaker detector is defeated


def test_monotone_stall_detector_reduction_resets():
    d = _StallDetector(patience=2)
    two = [_v("A", VERDICT_FAIL), _v("B", VERDICT_FAIL)]
    one = [_v("A", VERDICT_FAIL)]
    assert d.record(two) is False   # best=2
    assert d.record(two) is False   # no-progress 1
    assert d.record(one) is False   # reduced → best=1, resets
    assert d.record(one) is False   # no-progress 1
    assert d.record(one) is True    # no-progress 2 → stall


def test_disabled_gate_runs_nothing(tmp_path):
    """FR-11: disabled → no generation/deploy, terminal cause disabled."""
    called = {"gen": False, "dep": False}

    def gen(fb):
        called["gen"] = True
        return GenOutcome(app_root=tmp_path)

    def dep(root):
        called["dep"] = True
        return _passing_verdicts()

    report = run_build_to_spec_loop(
        _SPEC, generate_fn=gen, deploy_fn=dep, enabled=False
    )
    assert report.terminal_cause == "disabled"
    assert not called["gen"] and not called["dep"]
    assert exit_code_for_cause(report.terminal_cause) != 0
