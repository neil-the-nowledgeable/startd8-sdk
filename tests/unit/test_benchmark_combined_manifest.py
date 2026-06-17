"""M4 — consolidation manifest (CS-11) + the formal §6 acceptance criteria for the combined scoreboard.

The manifest is the integrity twin of the board: input SHA-256s, per-cell supersedence winners, coverage.
The acceptance test asserts the requirements-doc §6 criteria on round3-like + rerun-like + naive inputs.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from startd8.benchmark_matrix import build_combined_manifest, build_combined_scorecard

_NOW = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
_EXPOSE = {"repair_mode": "shadow", "expose_defects": True, "sdk_version": "0.4.0", "scoring_formula": "f"}
_NAIVE = {"repair_mode": "apply", "expose_defects": False, "sdk_version": "0.4.0", "scoring_formula": "f"}


def _cell(service, model, rep, status="ok", *, defect_total=1, quality=0.97):
    return {"cell_id": f"hash:{service}:{model}:r{rep}", "service": service, "model": model,
            "language": "go", "repetition": rep, "status": status, "quality": quality,
            "defect_total": defect_total, "cost_usd": 0.1}


def _run(run_dir: Path, *, spec, cells) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (run_dir / "cells.json").write_text(json.dumps(cells), encoding="utf-8")
    return run_dir


def test_manifest_structure_and_sha256(tmp_path):
    cells = [_cell("svc", "gemini:gemini-2.5-pro", 0)]
    r = _run(tmp_path / "round3", spec=_EXPOSE, cells=cells)
    man = build_combined_manifest([r], now=_NOW)
    assert man["schema_version"] == "1.0"
    assert man["generated_utc"] == "2026-06-16T18:00Z"
    assert man["anchor_method"] == "shadow+expose"
    assert man["coverage"]["canonical_cells"] == 1
    # SHA-256 of the actual cells.json bytes
    expect = hashlib.sha256((r / "cells.json").read_bytes()).hexdigest()
    assert man["inputs"][0]["cells_sha256"] == expect
    # per-cell winner recorded
    assert man["cell_winners"]["svc|gemini:gemini-2.5-pro|r0"]["winner_run"] == "round3"


def test_manifest_deterministic(tmp_path):
    r = _run(tmp_path / "r", spec=_EXPOSE, cells=[_cell("svc", "m", 0)])
    a = json.dumps(build_combined_manifest([r], now=_NOW), sort_keys=True)
    b = json.dumps(build_combined_manifest([r], now=_NOW), sort_keys=True)
    assert a == b


def test_manifest_records_supersedence_and_losers(tmp_path):
    base = _run(tmp_path / "round3", spec=_EXPOSE,
                cells=[_cell("checkout", "openai:gpt-5.5", 0, "infra_fail", defect_total=None)])
    rerun = _run(tmp_path / "rerun", spec=_EXPOSE, cells=[_cell("checkout", "openai:gpt-5.5", 0, "ok")])
    man = build_combined_manifest([base, rerun], now=_NOW)
    w = man["cell_winners"]["checkout|openai:gpt-5.5|r0"]
    assert w["winner_run"] == "rerun" and w["status"] == "ok"
    assert w["losers"] == [{"run": "round3", "cell_id": "hash:checkout:openai:gpt-5.5:r0",
                            "status": "infra_fail"}]


# --------------------------------------------------------------------------- §6 acceptance criteria
def test_acceptance_criteria(tmp_path):
    """Requirements §6: one board; OpenAI from the rerun; naive excluded; provenance complete;
    coverage shown; deterministic."""
    # round3-like (anchor=rerun listed first so its OpenAI slice supersedes)
    rerun = _run(tmp_path / "rerun", spec=_EXPOSE,
                 cells=[_cell("pay", "openai:gpt-5.5", 0, "ok")])
    round3 = _run(tmp_path / "round3", spec=_EXPOSE, cells=[
        _cell("pay", "openai:gpt-5.5", 0, "infra_fail", defect_total=None),  # superseded by rerun
        _cell("cart", "anthropic:claude-opus-4-8", 0, "ok"),                 # round3 sole source
    ])
    naive = _run(tmp_path / "round1", spec=_NAIVE,
                 cells=[_cell("pay", "openai:gpt-5.5", 0, "ok", defect_total=None, quality=1.0)])

    man = build_combined_manifest([rerun, round3, naive], now=_NOW)
    md = build_combined_scorecard([rerun, round3, naive], now=_NOW)

    # (1) one board, (2) OpenAI sourced from the rerun not the infra_fail base
    assert man["cell_winners"]["pay|openai:gpt-5.5|r0"]["winner_run"] == "rerun"
    # (2) the naive cell never won (excluded)
    assert all(w["winner_run"] != "round1" for w in man["cell_winners"].values())
    # (3) every winner traces to a cell_id
    assert all(w["winner_cell_id"] for w in man["cell_winners"].values())
    # (4) coverage shown; round1 excluded
    excluded = [i for i in man["inputs"] if not i["included"]]
    assert any(i["run"] == "round1" for i in excluded)
    assert man["coverage"]["excluded_runs"] == 1 and man["coverage"]["included_runs"] == 2
    # (5) naive board appears in the annex, not the ranking
    assert "`round1` — naive" in md
    # (6) deterministic rebuild
    assert build_combined_scorecard([rerun, round3, naive], now=_NOW) == md
    assert (json.dumps(build_combined_manifest([rerun, round3, naive], now=_NOW), sort_keys=True)
            == json.dumps(man, sort_keys=True))
