"""Unit tests for benchmark_matrix.tracking (T4 / Section B / FR-7/8/9/10 / OQ-2)."""

import json
from pathlib import Path

from startd8.benchmark_matrix.tracking import (
    CELL_STATUS_MAP,
    map_cell_status,
    reconstruct_run_tracking,
)


def _write_run(tmp_path: Path, cells, name="r1"):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run-spec.json").write_text(json.dumps({
        "name": name, "spec_hash": "49252392edaa02539f80d22b4d7e59c1", "services": [], "models": [],
    }))
    (run / "cells.json").write_text(json.dumps(cells))
    return run


def _cells():
    return [
        {"cell_id": "h:cart:opus:r0", "service": "cart", "model": "opus", "language": "go",
         "repetition": 0, "status": "ok", "cost_usd": 0.10},
        {"cell_id": "h:cart:gpt:r0", "service": "cart", "model": "gpt", "language": "go",
         "repetition": 0, "status": "infra_fail", "cost_usd": 0.0, "error": "429"},
        {"cell_id": "h:email:opus:r0", "service": "email", "model": "opus", "language": "py",
         "repetition": 0, "status": "failed", "cost_usd": 0.05, "error": "boom"},
        {"cell_id": "h:email:gem:r0", "service": "email", "model": "gem", "language": "py",
         "repetition": 0, "status": "integrity_fail", "cost_usd": 0.0},
    ]


def test_status_mapping_table():
    assert map_cell_status("ok") == ("done", None)
    assert map_cell_status("failed") == ("cancelled", None)
    assert map_cell_status("timeout") == ("cancelled", None)
    assert map_cell_status("integrity_fail") == ("cancelled", "integrity")
    assert map_cell_status("infra_fail") == ("blocked", "infra")
    assert map_cell_status("budget_skip") == ("blocked", None)
    # all 6 native statuses covered
    assert set(CELL_STATUS_MAP) == {"ok", "failed", "timeout", "integrity_fail", "infra_fail", "budget_skip"}


def _load(out_dir: Path, task_id: str) -> dict:
    return json.loads((out_dir / "contextcore-tasks" / f"{task_id}.json").read_text())


def test_cell_mode_hierarchy_and_status(tmp_path):
    run = _write_run(tmp_path, _cells())
    s = reconstruct_run_tracking(run, mode="cell")
    assert s["granularity"] == "cell"
    assert s["run_id"] == "49252392edaa"
    assert s["project_id"] == "startd8-benchmark-run-49252392edaa"
    assert s["counts"] == {"services": 2, "cells": 4, "cell_tasks": 4}
    out = run / "contextcore-tracking"
    # ok → done
    ok_cell = _load(out, "h:cart:opus:r0")
    assert ok_cell["attributes"]["task.status"] == "done"
    assert ok_cell["status"] == "OK"
    # infra_fail → blocked + exclusion_reason label
    infra = _load(out, "h:cart:gpt:r0")
    assert infra["attributes"]["task.status"] == "blocked"
    assert "exclusion_reason:infra" in infra["attributes"]["task.labels"]
    assert "run:49252392edaa" in infra["attributes"]["task.labels"]
    # failed → cancelled
    assert _load(out, "h:email:opus:r0")["attributes"]["task.status"] == "cancelled"
    # integrity_fail → cancelled + exclusion label (NOT a model failure)
    integ = _load(out, "h:email:gem:r0")
    assert integ["attributes"]["task.status"] == "cancelled"
    assert "exclusion_reason:integrity" in integ["attributes"]["task.labels"]


def test_cost_rollup_in_summary(tmp_path):
    run = _write_run(tmp_path, _cells())
    s = reconstruct_run_tracking(run, mode="cell")
    assert s["cost_total_usd"] == 0.15  # 0.10 + 0.05 (+0 infra/integrity)
    assert s["cost_by_model"]["opus"] == 0.15


def test_count_mode_no_per_cell_tasks(tmp_path):
    run = _write_run(tmp_path, _cells())
    s = reconstruct_run_tracking(run, mode="count")
    assert s["granularity"] == "count"
    assert s["counts"]["cell_tasks"] == 0  # services as stories, no per-cell tasks
    # service story carries cell counts in labels
    story = _load(run / "contextcore-tracking", "cart-story")
    assert "cells:2" in story["attributes"]["task.labels"]
    assert "ok:1" in story["attributes"]["task.labels"]


def test_auto_mode_picks_cell_for_small_run(tmp_path):
    run = _write_run(tmp_path, _cells())
    assert reconstruct_run_tracking(run, mode="auto")["granularity"] == "cell"


def test_notable_insights_via_bridge(tmp_path):
    run = _write_run(tmp_path, _cells())

    class _Bridge:
        def __init__(self):
            self.calls = []

        def emit_blocker(self, summary, confidence=1.0, **kw):
            self.calls.append(("blocker", summary))
            return True

        def emit_risk(self, summary, confidence=0.8, **kw):
            self.calls.append(("risk", summary))
            return True

    bridge = _Bridge()
    s = reconstruct_run_tracking(run, mode="cell", insight_bridge=bridge)
    # only the 'failed' cell is a notable model failure (infra_fail/integrity_fail excluded)
    assert s["notable_insights"] == 1
    assert bridge.calls[0][0] == "blocker"


def test_real_run_reconstructs(tmp_path):
    """The shipped real Round-1 run reconstructs cleanly if present (skip otherwise)."""
    import pytest

    real = Path.home() / "Documents/dev/benchmarking/Summer2026/results/run-20260614T0505"
    if not (real / "cells.json").exists():
        pytest.skip("real run dir not present")
    s = reconstruct_run_tracking(real, mode="cell", output_dir=tmp_path / "out")
    assert s["counts"]["cells"] == 81
    assert round(s["cost_total_usd"], 2) == 5.82
