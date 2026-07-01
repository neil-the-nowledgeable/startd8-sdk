from __future__ import annotations

import importlib.util
import json
import sqlite3
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


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_suite_run(raw_root: Path, run_dir: str, *, run_id: str, ordinal: int = 1) -> None:
    directory = raw_root / run_dir
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_id,
        "ordinal": ordinal,
        "experiment": "suite_author",
        "tool_id": "gemini-cli",
        "author_vendor": "google",
        "sample_index": 2,
        "status": "success",
        "exit_code": 0,
        "missing_files": [],
    }
    _write_json(directory / "metadata.json", metadata)
    _write_json(directory / "authoring_manifest.json", {"run_id": run_id})
    _write_json(directory / "self-manifest.schema.json", {})
    _write_json(directory / "suite_manifest.json", {})
    (directory / "suite.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (directory / "rendered_prompt.md").write_text("prompt\n", encoding="utf-8")
    (directory / "stdout.log").write_text("", encoding="utf-8")
    (directory / "stderr.log").write_text("", encoding="utf-8")


def _write_schedule(path: Path) -> None:
    _write_json(path, [{
        "ordinal": 1,
        "experiment": "suite_author",
        "tool_id": "gemini-cli",
        "author_vendor": "google",
        "sample_index": 2,
    }])


def test_reconcile_blocks_duplicate_ordinal_without_disposition(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    schedule = tmp_path / "authoring-schedule.json"
    _write_schedule(schedule)
    _write_suite_run(raw_root, "run_01_suite_author_gemini-cli_sample_2", run_id="run-01")
    _write_suite_run(
        raw_root,
        "run_01_suite_author_gemini-cli_sample_2_replacement_1",
        run_id="run-01-replacement-1",
    )

    report = mod.reconcile(raw_root, schedule)

    assert report["status"] == "blocked"
    assert report["observed_runs"] == 2
    assert report["effective_observed_runs"] == 1
    assert report["duplicate_ordinals"] == {1: ["run-01", "run-01-replacement-1"]}
    assert report["dispositions"]["errors"] == [
        "duplicate_ordinal_without_disposition:1:run-01,run-01-replacement-1"
    ]


def test_reconcile_quarantines_non_evidence_smoke_run(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    schedule = tmp_path / "authoring-schedule.json"
    _write_schedule(schedule)
    _write_suite_run(raw_root, "run_01_suite_author_gemini-cli_sample_2", run_id="smoke-run-01")
    metadata_path = raw_root / "run_01_suite_author_gemini-cli_sample_2" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update({
        "mode": "non_evidence_smoke",
        "evidence_role": "non_evidence_smoke",
        "promote_to_evidence": False,
    })
    _write_json(metadata_path, metadata)

    report = mod.reconcile(raw_root, schedule)

    assert report["status"] == "blocked"
    assert report["runs"][0]["status"] == "quarantined"
    assert "non_evidence_smoke" in report["runs"][0]["errors"]


def test_reconcile_accepts_dispositioned_replacement_duplicate(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    schedule = tmp_path / "authoring-schedule.json"
    _write_schedule(schedule)
    _write_suite_run(raw_root, "run_01_suite_author_gemini-cli_sample_2", run_id="run-01")
    _write_suite_run(
        raw_root,
        "run_01_suite_author_gemini-cli_sample_2_replacement_1",
        run_id="run-01-replacement-1",
    )
    _write_json(tmp_path / "dispositions.json", [{
        "rejected_run_id": "run-01",
        "replacement_run_id": "run-01-replacement-1",
        "reason_code": "forbidden_import",
        "reviewer": "codex",
        "timestamp": "2026-06-29T00:00:00+00:00",
    }])

    report = mod.reconcile(raw_root, schedule)

    assert report["status"] == "accepted"
    assert report["raw_observed_runs"] == 2
    assert report["effective_observed_runs"] == 1
    assert report["dispositions"]["errors"] == []
    assert report["dispositions"]["replacement_pairs"] == [{
        "ordinal": 1,
        "rejected_run_id": "run-01",
        "replacement_run_id": "run-01-replacement-1",
        "reason_code": "forbidden_import",
        "reviewer": "codex",
        "timestamp": "2026-06-29T00:00:00+00:00",
    }]
    by_id = {run["metadata"]["run_id"]: run for run in report["runs"]}
    assert by_id["run-01"]["disposition"]["status"] == "replaced"
    assert by_id["run-01-replacement-1"]["disposition"]["status"] == "replacement"


def test_reconcile_blocks_disposition_missing_replacement_run(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    schedule = tmp_path / "authoring-schedule.json"
    _write_schedule(schedule)
    _write_suite_run(raw_root, "run_01_suite_author_gemini-cli_sample_2", run_id="run-01")
    _write_json(tmp_path / "dispositions.json", [{
        "rejected_run_id": "run-01",
        "replacement_run_id": "run-01-replacement-1",
        "reason_code": "forbidden_import",
        "reviewer": "codex",
        "timestamp": "2026-06-29T00:00:00+00:00",
    }])

    report = mod.reconcile(raw_root, schedule)

    assert report["status"] == "blocked"
    assert report["dispositions"]["errors"] == [
        "disposition_missing_replacement_run:run-01-replacement-1"
    ]


def test_promote_persists_dispositioned_duplicate_ordinals(tmp_path: Path) -> None:
    raw_root = tmp_path / "batch/raw"
    schedule = tmp_path / "batch/authoring-schedule.json"
    _write_schedule(schedule)
    _write_suite_run(raw_root, "run_01_suite_author_gemini-cli_sample_2", run_id="run-01")
    _write_suite_run(
        raw_root,
        "run_01_suite_author_gemini-cli_sample_2_replacement_1",
        run_id="run-01-replacement-1",
    )
    _write_json(tmp_path / "batch/dispositions.json", [{
        "rejected_run_id": "run-01",
        "replacement_run_id": "run-01-replacement-1",
        "reason_code": "forbidden_import",
        "reviewer": "codex",
        "timestamp": "2026-06-29T00:00:00+00:00",
    }])
    report = mod.reconcile(raw_root, schedule)

    promoted = mod.promote(report, raw_root, tmp_path / "store", "batch")

    assert (promoted / "dispositions.json").is_file()
    with sqlite3.connect(promoted / "audit.sqlite") as connection:
        rows = connection.execute(
            "SELECT run_id, ordinal, disposition_json FROM authoring_runs ORDER BY run_id"
        ).fetchall()
        artifact_rows = connection.execute(
            "SELECT run_id, ordinal, path FROM artifacts WHERE path = 'suite.py' ORDER BY run_id"
        ).fetchall()
    assert [row[0] for row in rows] == ["run-01", "run-01-replacement-1"]
    assert [row[1] for row in rows] == [1, 1]
    assert json.loads(rows[0][2])["status"] == "replaced"
    assert json.loads(rows[1][2])["status"] == "replacement"
    assert [row[0] for row in artifact_rows] == ["run-01", "run-01-replacement-1"]
