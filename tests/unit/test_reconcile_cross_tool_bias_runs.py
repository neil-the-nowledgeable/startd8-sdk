from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "reconcile_cross_tool_bias_runs.py"

spec = importlib.util.spec_from_file_location("reconcile_cross_tool_bias_runs", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_reconcile_blocks_without_traceback_when_schedule_missing(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    schedule = tmp_path / "authoring-schedule.json"

    report = mod.reconcile(raw_root, schedule)

    assert report["status"] == "blocked"
    assert report["expected_runs"] == 0
    assert report["observed_runs"] == 0
    assert report["runs"] == []
    assert report["preflight_errors"] == [f"missing_schedule:{schedule}"]


def test_reconcile_blocks_without_traceback_when_raw_root_missing(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    schedule = tmp_path / "authoring-schedule.json"
    schedule.write_text(json.dumps([]), encoding="utf-8")

    report = mod.reconcile(raw_root, schedule)

    assert report["status"] == "blocked"
    assert report["preflight_errors"] == [f"missing_raw_root:{raw_root}"]


def test_reconcile_main_writes_blocked_report_for_missing_schedule(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()

    rc = mod.main(["--raw-root", str(raw_root)])

    report_path = tmp_path / "reconciliation-report.json"
    assert rc == 2
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    assert report["preflight_errors"] == [f"missing_schedule:{tmp_path / 'authoring-schedule.json'}"]
