"""Unit tests for R3-M6 system report + ranking + decision gate (fleet.report) — synthetic finalists.

Pins the finalist ranking (system score desc, tie-break on model-faults then cost), the advisory
decision gate (discriminate + attribution-trustworthy → GO/NO-GO), and the markdown leaderboard.
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.fleet import report as R
from startd8.benchmark_matrix.fleet.score import Scorecard, ServiceFault, MODEL_FAULT

pytestmark = pytest.mark.unit


def _sc(weighted: float, unweighted: float = 1.0, completed: bool = True,
        confidence: str = "high", model_faults: list[str] | None = None) -> Scorecard:
    faults = [ServiceFault(s, MODEL_FAULT, "checkout") for s in (model_faults or [])]
    return Scorecard(unweighted_coverage=unweighted, weighted_coverage=weighted,
                     journey_completed=completed, confidence=confidence, faults=faults)


def test_rank_by_system_score_desc():
    fs = [
        R.FinalistScore("model-a", _sc(0.80)),
        R.FinalistScore("model-b", _sc(1.00)),
        R.FinalistScore("model-c", _sc(0.50)),
    ]
    ranked = R.rank_finalists(fs)
    assert [f.model for f in ranked] == ["model-b", "model-a", "model-c"]


def test_tie_breaks_on_model_faults_then_cost():
    fs = [
        R.FinalistScore("clean-but-pricey", _sc(0.90), cost_usd=5.0),
        R.FinalistScore("faulted", _sc(0.90, model_faults=["paymentservice"]), cost_usd=0.1),
        R.FinalistScore("clean-cheap", _sc(0.90), cost_usd=0.5),
    ]
    ranked = R.rank_finalists(fs)
    # equal system score -> fewer model-faults first, then lower cost; faulted ranks last.
    assert [f.model for f in ranked] == ["clean-cheap", "clean-but-pricey", "faulted"]


def test_gate_go_when_discriminates_and_attribution_trustworthy():
    fs = [R.FinalistScore("a", _sc(1.00)), R.FinalistScore("b", _sc(0.60))]
    g = R.decide(fs, attribution_trustworthy=True)
    assert g.discriminates is True and g.verdict == "GO"
    assert abs(g.spread - 0.40) < 1e-9


def test_gate_no_go_when_finalists_tie():
    fs = [R.FinalistScore("a", _sc(0.90)), R.FinalistScore("b", _sc(0.90))]
    g = R.decide(fs, attribution_trustworthy=True)
    assert g.discriminates is False and g.verdict == "NO-GO"
    assert "tie" in g.note


def test_gate_no_go_when_attribution_untrustworthy():
    fs = [R.FinalistScore("a", _sc(1.00)), R.FinalistScore("b", _sc(0.50))]
    g = R.decide(fs, attribution_trustworthy=False)
    assert g.discriminates is True and g.verdict == "NO-GO"
    assert "attribution is NOT trustworthy" in g.note


def test_single_finalist_cannot_assess_discrimination():
    g = R.decide([R.FinalistScore("solo", _sc(1.00))], attribution_trustworthy=True)
    assert g.discriminates is False and g.verdict == "NO-GO"
    assert "one finalist" in g.note


def test_frontend_bonus_never_rank_flips_a_better_backend():
    """OQ-J3: a brilliant-frontend/weak-backend finalist must NEVER outrank a strong-backend one."""
    fs = [
        R.FinalistScore("weak-backend-great-frontend", _sc(0.80),
                        frontend_mounted="generated", frontend_bonus=0.10),
        R.FinalistScore("strong-backend-no-frontend", _sc(0.95),
                        frontend_mounted="canonical-substituted", frontend_bonus=0.0),
    ]
    ranked = R.rank_finalists(fs)
    assert ranked[0].model == "strong-backend-no-frontend"  # backend wins despite 0 bonus


def test_frontend_bonus_breaks_ties_among_equal_backends():
    """Among EQUAL backend scores (+ equal faults), the higher frontend bonus ranks first."""
    fs = [
        R.FinalistScore("equal-no-bonus", _sc(0.90), frontend_bonus=0.0),
        R.FinalistScore("equal-with-bonus", _sc(0.90), frontend_mounted="generated", frontend_bonus=0.08),
    ]
    ranked = R.rank_finalists(fs)
    assert ranked[0].model == "equal-with-bonus"


def test_substituted_run_shows_zero_bonus():
    fs = [R.FinalistScore("sub", _sc(1.0), frontend_mounted="canonical-substituted", frontend_bonus=0.0)]
    report, md = R.build_system_report(fs, attribution_trustworthy=True)
    row = report["finalists"][0]
    assert row["frontend_mounted"] == "canonical-substituted" and row["frontend_bonus"] == 0.0
    assert "+0.000" in md and "canonical" in md


def test_build_report_json_and_markdown():
    fs = [
        R.FinalistScore("winner", _sc(1.00), cost_usd=0.40, wall_seconds=120.0),
        R.FinalistScore("loser", _sc(0.40, completed=False, model_faults=["paymentservice"]),
                        cost_usd=0.10, wall_seconds=90.0),
    ]
    report, md = R.build_system_report(fs, attribution_trustworthy=True)
    assert report["advisory"] is True
    assert report["decision_gate"]["verdict"] == "GO"
    assert [r["model"] for r in report["finalists"]] == ["winner", "loser"]  # ranked
    assert report["finalists"][1]["model_faults"] == ["paymentservice"]
    # markdown carries the gate verdict + a ranked leaderboard row per finalist
    assert "Decision gate: GO" in md
    assert "`winner`" in md and "`loser`" in md
    assert "| 1 | `winner`" in md and "| 2 | `loser`" in md  # ranked rows
