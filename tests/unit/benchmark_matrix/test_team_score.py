"""Unit tests for dual-track team score + suggest advancement (M1/M5.1/M6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from startd8.benchmark_matrix.entrant_roster import EntrantMeta, load_entrant_roster
from startd8.benchmark_matrix.round_roster import RoundRoster, resolve_enrollment
from startd8.benchmark_matrix.suggest_advancement import (
    adopt_suggestion,
    build_suggestion,
    dump_suggestion,
)
from startd8.benchmark_matrix.team_score import team_rows

PROJECT = Path(__file__).resolve().parents[4]  # may not exist; use fixture roster


@pytest.fixture
def roster():
    return {
        "anthropic:opus": EntrantMeta("anthropic:opus", "anthropic", "flagship"),
        "anthropic:sonnet": EntrantMeta("anthropic:sonnet", "anthropic", "mid"),
        "anthropic:haiku": EntrantMeta("anthropic:haiku", "anthropic", "fast"),
        "openai:pro": EntrantMeta("openai:pro", "openai", "flagship"),
        "openai:mini": EntrantMeta("openai:mini", "openai", "mid"),
        "openai:nano": EntrantMeta("openai:nano", "openai", "fast"),
        "deepseek:pro": EntrantMeta("deepseek:pro", "deepseek", "flagship"),
        "deepseek:mid": EntrantMeta("deepseek:mid", "deepseek", "mid"),
        "deepseek:fast": EntrantMeta("deepseek:fast", "deepseek", "fast"),
        "solo:only": EntrantMeta("solo:only", "solo-lab", "solo"),
    }


def _agg(qualities: dict, cost: float = 0.1):
    by_model = {
        m: {"quality_median": q, "cost_mean_usd": cost, "cost_total_usd": cost}
        for m, q in qualities.items()
    }
    return {"by_model": by_model}


def test_a1_full_squad_invite_excluded_from_team(roster):
    rr = RoundRoster(
        lane="main",
        team_lane_labs=["anthropic", "openai"],
        individual_invite=["deepseek:pro", "deepseek:mid", "deepseek:fast"],
        parent_run="results/heats",
    )
    enr = resolve_enrollment(rr, roster)
    assert enr.classification["deepseek:pro"] == "invite"
    assert "deepseek:pro" in enr.models
    agg = _agg({
        "anthropic:opus": 0.9, "anthropic:sonnet": 0.6, "anthropic:haiku": 0.3,
        "openai:pro": 0.8, "openai:mini": 0.7, "openai:nano": 0.5,
        "deepseek:pro": 0.99, "deepseek:mid": 0.95, "deepseek:fast": 0.9,
    })
    rows = team_rows(agg, roster, team_lane=list(enr.team_lane_labs))
    assert {r.lab for r in rows} == {"anthropic", "openai"}


def test_team_rows_mean_tier_quality(roster):
    agg = _agg({
        "anthropic:opus": 0.9, "anthropic:sonnet": 0.6, "anthropic:haiku": 0.3,
        "openai:pro": 0.8, "openai:mini": 0.7, "openai:nano": 0.5,
    })
    rows = team_rows(agg, roster)
    assert rows[0].lab == "openai"
    assert abs(rows[0].quality - (0.8 + 0.7 + 0.5) / 3) < 1e-9


def test_suggest_expands_tie_at_cut(roster, tmp_path):
    # Five equal-quality labs would need more models; use 3 labs with tie at cut N=2
    for lab, models in [
        ("anthropic", ["anthropic:opus", "anthropic:sonnet", "anthropic:haiku"]),
        ("openai", ["openai:pro", "openai:mini", "openai:nano"]),
        ("deepseek", ["deepseek:pro", "deepseek:mid", "deepseek:fast"]),
    ]:
        pass
    # Tie anthropic/openai at 0.7; deepseek lower — cut N=1 expands? N=1 clean.
    # Tie at N=2: anthropic=openai=0.8, deepseek=0.5 → main_n=1 is clean;
    # main_n=2 with anthropic==openai quality expands if a 3rd shares — use anthropic==openai.
    agg = _agg({
        "anthropic:opus": 0.9, "anthropic:sonnet": 0.6, "anthropic:haiku": 0.3,  # mean 0.6
        "openai:pro": 0.9, "openai:mini": 0.6, "openai:nano": 0.3,              # mean 0.6 tied
        "deepseek:pro": 0.5, "deepseek:mid": 0.4, "deepseek:fast": 0.3,         # mean 0.4
    })
    (tmp_path / "aggregate.json").write_text(json.dumps(agg), encoding="utf-8")
    sug = build_suggestion(tmp_path, roster, main_n=1)
    # cut N=1 falls inside tie of anthropic+openai → expand both, needs_operator_choice
    assert set(sug.main_suggested) == {"anthropic", "openai"}
    assert sug.tied is True
    assert sug.needs_operator_choice is True


def test_suggest_adopt_roundtrip(roster, tmp_path):
    agg = _agg({
        "anthropic:opus": 0.9, "anthropic:sonnet": 0.6, "anthropic:haiku": 0.3,
        "openai:pro": 0.8, "openai:mini": 0.7, "openai:nano": 0.5,
    })
    (tmp_path / "aggregate.json").write_text(json.dumps(agg), encoding="utf-8")
    sug = build_suggestion(tmp_path, roster, main_n=2, suggest_invites="cut-mid-fast")
    sp = tmp_path / "advancement.suggested.yaml"
    dump_suggestion(sug, sp)
    dest = tmp_path / "advancement.yaml"
    out = adopt_suggestion(sp, dest)
    assert out["main"] == sug.main_suggested
    assert out["consolation"] == sug.consolation_suggested
    assert out["individual_invite"]  # deepseek mid+fast selectors
    raw = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert "main_suggested" not in raw
    with pytest.raises(FileExistsError):
        adopt_suggestion(sp, dest)  # refuse silent overwrite
    adopt_suggestion(sp, dest, force=True)  # explicit force OK


def test_project_entrant_roster_loads():
    path = Path.home() / "Documents/dev/benchmarking/Summer2026/config/entrant_roster.yaml"
    if not path.is_file():
        pytest.skip("Summer2026 roster not present")
    r = load_entrant_roster(path)
    assert "openrouter:deepseek/deepseek-v4-pro" in r
    assert r["openrouter:qwen/qwen3-max"].lab == "qwen"
    assert r["openrouter:deepseek/deepseek-chat"].tier == "mid"


def test_team_board_falls_back_to_tournament_json(roster, tmp_path):
    """EC-DT-8: SCORECARD Team loads lane/classification from tournament.json."""
    from startd8.benchmark_matrix.scorecard import _team_board

    entrants = [
        {"model": m, "lab": meta.lab, "tier": meta.tier}
        for m, meta in roster.items()
    ]
    (tmp_path / "entrant_roster.yaml").write_text(
        yaml.safe_dump({"entrants": entrants}), encoding="utf-8"
    )
    agg = _agg({
        "anthropic:opus": 0.9, "anthropic:sonnet": 0.6, "anthropic:haiku": 0.3,
        "openai:pro": 0.8, "openai:mini": 0.7, "openai:nano": 0.5,
        "deepseek:pro": 0.99, "deepseek:mid": 0.95, "deepseek:fast": 0.9,
    })
    (tmp_path / "tournament.json").write_text(
        json.dumps({
            "lane": "heats",
            "team_lane_labs": ["anthropic", "openai"],
            "individual_invite_only": ["deepseek:pro", "deepseek:mid", "deepseek:fast"],
            "classification": {
                "anthropic:opus": "team_lane",
                "openai:pro": "team_lane",
                "deepseek:pro": "invite",
            },
            "round_roster_hash": "sha256:test",
        }),
        encoding="utf-8",
    )
    board = _team_board(agg, run_dir=tmp_path)
    assert board.degrade is None
    assert {r.lab for r in board.rows} == {"anthropic", "openai"}
    assert board.classification["deepseek:pro"] == "invite"
    assert "tournament.json" in board.footnote


def test_qtable_includes_lane_column():
    """EC-DT-2: Individual table tags invite/team_lane/both."""
    from startd8.benchmark_matrix.scorecard import _qtable

    agg = {
        "by_model": {
            "m:a": {
                "quality_median": 0.9,
                "quality_iqr": 0.0,
                "pass_rate": 1.0,
                "catastrophic_count": 0,
                "n": 1,
                "cost_total_usd": 0.1,
                "model_tokens_per_sec_median": 10.0,
            }
        }
    }
    md = _qtable(agg, ["m:a"], classification={"m:a": "invite"})
    assert "| lane |" in md
    assert "`invite`" in md
