"""M3 increment-2 — run_ob_benchmark.py CLI.

The dry-run path is always tested (no spend). A real 1-cell run is gated behind
STARTD8_BENCH_SMOKE=1 so it never spends money / calls LLMs in CI or by default.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "scripts" / "run_ob_benchmark.py"


def test_dry_run_sizes_without_spending():
    r = subprocess.run(
        [sys.executable, str(CLI), "--flagships-only", "--reps", "2", "--dry-run"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    assert "9 services x 4 models x 2 reps = 72 cells" in r.stdout
    assert "no cells executed" in r.stdout


def test_run_without_budget_is_blocked_fail_closed():
    # No --budget and not --dry-run -> fail-closed preflight blocks before any spend.
    r = subprocess.run(
        [sys.executable, str(CLI), "--flagships-only", "--reps", "1",
         "--services", "emailservice"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 2
    assert "preflight BLOCKED" in r.stderr
    assert "fail-closed" in r.stderr


@pytest.mark.skipif(
    os.getenv("STARTD8_BENCH_SMOKE") != "1",
    reason="real LLM smoke — set STARTD8_BENCH_SMOKE=1 to run (spends money, needs API keys)",
)
def test_real_single_cell_smoke(tmp_path):
    # One cheapest-model cell against one service; tiny budget. Opt-in only.
    r = subprocess.run(
        [sys.executable, str(CLI),
         "--models", "gemini:gemini-2.5-flash-lite",
         "--services", "emailservice", "--reps", "1",
         "--budget", "1.0", "--timeout", "600",
         "--out-dir", str(tmp_path / "run")],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode in (0, 1), r.stderr  # 1 = integrity fail surfaced; both write artifacts
    cells = json.loads((tmp_path / "run" / "cells.json").read_text())
    assert len(cells) == 1
    assert cells[0]["service"] == "emailservice"
    assert (tmp_path / "run" / "leaderboard.md").exists()
