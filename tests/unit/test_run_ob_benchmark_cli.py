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


# --- K3 S7: role-pairs CLI + cell guard --------------------------------------

def test_role_grid_dry_run_shows_role_factor():
    r = subprocess.run(
        [sys.executable, str(CLI), "--flagships-only", "--reps", "1", "--role-pairs", "grid", "--dry-run"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    assert "16 role-pairs" in r.stdout                 # 4 flagships → 4² (NOT implied by --models)
    assert "144 cells" in r.stdout


def test_default_models_never_imply_grid():
    # Listing N models stays diagonal-only — the N²-fan footgun (R6-S3) must not trigger.
    r = subprocess.run(
        [sys.executable, str(CLI), "--models", "a:1", "b:2", "c:3", "--reps", "1", "--dry-run"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    assert "3 models" in r.stdout and "role-pairs" not in r.stdout   # diagonal, not 3²


def test_cell_guard_refuses_large_grid_before_spend():
    # grid × 2 reps = 288 cells > 200; no --allow-large, real run -> refuse (return 2), before preflight.
    r = subprocess.run(
        [sys.executable, str(CLI), "--flagships-only", "--reps", "2", "--role-pairs", "grid"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 2
    assert "refusing 288 cells" in r.stderr and "200-cell guard" in r.stderr


def test_allow_large_bypasses_guard_then_preflight_blocks():
    # --allow-large clears the guard; the run then still fail-closes on the missing budget.
    r = subprocess.run(
        [sys.executable, str(CLI), "--flagships-only", "--reps", "2", "--role-pairs", "grid",
         "--allow-large"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 2
    assert "200-cell guard" not in r.stderr            # guard cleared (its signature absent)
    assert "preflight BLOCKED" in r.stderr             # blocked later, by budget (no spend)


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
