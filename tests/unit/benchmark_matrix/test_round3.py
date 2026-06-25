"""Unit tests for R3-M6 roster + orchestration (fleet.roster, fleet.round3) — NO docker, mock score_fn.

Pins roster loading/validation, the default namespace mapping, and the run_round3 orchestration (each
finalist scored via an injected score_fn; infra-degraded finalists carried into the report; artifacts
written).
"""
from __future__ import annotations

import json

import pytest

from startd8.benchmark_matrix.fleet import roster as RO
from startd8.benchmark_matrix.fleet import round3 as R3
from startd8.benchmark_matrix.fleet.score import Scorecard

pytestmark = pytest.mark.unit


# --- roster ---------------------------------------------------------------------------------------

def test_finalist_default_namespace():
    assert RO.FinalistSpec.of("reference").image_namespace == "r3"
    assert RO.FinalistSpec.of("claude-x").image_namespace == "r3/claude-x"
    assert RO.FinalistSpec.of("m", "custom/ns").image_namespace == "custom/ns"


def test_load_roster(tmp_path):
    p = tmp_path / "roster.yaml"
    p.write_text("finalists:\n  - model: claude-x\n  - model: reference\n    image_namespace: r3\n")
    specs = RO.load_roster(p)
    assert [s.model for s in specs] == ["claude-x", "reference"]
    assert specs[0].image_namespace == "r3/claude-x" and specs[1].image_namespace == "r3"


def test_load_roster_rejects_malformed(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("finalists: []\n")
    with pytest.raises(ValueError, match="non-empty"):
        RO.load_roster(p)
    p.write_text("finalists:\n  - model: a\n  - model: a\n")
    with pytest.raises(ValueError, match="duplicate"):
        RO.load_roster(p)


# --- orchestration --------------------------------------------------------------------------------

def _sc(weighted: float, completed: bool = True) -> Scorecard:
    return Scorecard(weighted, weighted, journey_completed=completed, confidence="high", faults=[])


def test_run_round3_ranks_and_writes(tmp_path):
    roster = [RO.FinalistSpec.of("strong"), RO.FinalistSpec.of("weak")]
    scores = {"strong": R3.ScoreOutcome(_sc(1.0), cost_usd=0.4, wall_seconds=120.0),
              "weak": R3.ScoreOutcome(_sc(0.5, completed=False), cost_usd=0.1, wall_seconds=90.0)}
    report, md = R3.run_round3(roster, score_fn=lambda s: scores[s.model],
                               attribution_trustworthy=True, out_dir=tmp_path)
    assert [r["model"] for r in report["finalists"]] == ["strong", "weak"]  # ranked desc
    assert report["decision_gate"]["verdict"] == "GO"  # discriminates + trustworthy
    # artifacts written + re-loadable
    written = json.loads((tmp_path / "round3-system-report.json").read_text())
    assert written["finalists"][0]["model"] == "strong"
    assert (tmp_path / "round3-system-report.md").read_text() == md


def test_live_score_fn_wraps_scorecard_in_outcome(monkeypatch):
    """Regression: live_score_fn must return a ScoreOutcome (run_round3 reads .scorecard), not the raw
    Scorecard that score_namespace_fleet returns — a type mismatch the mock-based orchestration tests
    can't catch (it surfaced only in the live CLI smoke)."""
    import startd8.benchmark_matrix.fleet.validate_m6 as v6
    monkeypatch.setattr(v6, "score_namespace_fleet", lambda ns: _sc(1.0))
    out = R3.live_score_fn(RO.FinalistSpec.of("reference"))  # "r3" namespace skips the image check
    assert isinstance(out, R3.ScoreOutcome)
    assert out.scorecard.weighted_coverage == 1.0


def test_infra_degraded_finalist_is_not_a_model_zero():
    """A finalist whose fleet couldn't be scored degrades infra-honestly (zero coverage, low
    confidence, NO service charged model-fault) and carries an 'infra:' note."""
    out = R3._infra_degraded("fleet images missing under r3/ghost")
    assert out.scorecard.weighted_coverage == 0.0
    assert out.scorecard.confidence == "low"
    assert out.scorecard.model_faulted_services == set()  # not blamed on any service
    assert out.note.startswith("infra:")

    roster = [RO.FinalistSpec.of("real"), RO.FinalistSpec.of("ghost")]
    scores = {"real": R3.ScoreOutcome(_sc(1.0)), "ghost": out}
    report, _ = R3.run_round3(roster, score_fn=lambda s: scores[s.model], attribution_trustworthy=True)
    ghost_row = next(r for r in report["finalists"] if r["model"] == "ghost")
    assert ghost_row["note"].startswith("infra:") and ghost_row["model_faults"] == []
