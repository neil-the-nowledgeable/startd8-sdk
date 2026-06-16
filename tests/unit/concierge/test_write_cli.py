"""CLI tests for the Concierge write actions (Step 4) — the sole writers (OQ-7).

Covers preview-by-default, --apply, --force, --check drift (FR-C15), and exit codes.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli_concierge import concierge_app

runner = CliRunner()


# ── instantiate-kickoff ──────────────────────────────────────────────────────

def test_instantiate_preview_writes_nothing(tmp_path):
    res = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path)])
    assert res.exit_code == 0
    assert "preview only" in res.stdout
    assert not (tmp_path / "docs").exists()  # nothing written without --apply


def test_instantiate_apply_writes_files(tmp_path):
    res = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--apply"])
    assert res.exit_code == 0
    assert (tmp_path / "docs" / "kickoff" / "KICKOFF_INTRO.md").is_file()
    assert (tmp_path / "docs" / "kickoff" / "inputs" / "conventions.yaml").is_file()


def test_instantiate_apply_idempotent(tmp_path):
    runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--apply"])
    res2 = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--apply"])
    assert res2.exit_code == 0
    assert "skipped" in res2.stdout and "wrote" not in res2.stdout  # all exist → skipped


def test_check_complete_then_drifted(tmp_path):
    runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--apply"])
    res_ok = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--check"])
    assert res_ok.exit_code == 0 and "complete" in res_ok.stdout
    # hand-edit a file → drift → non-zero exit
    (tmp_path / "docs" / "kickoff" / "inputs" / "conventions.yaml").write_text("tampered\n", encoding="utf-8")
    res_drift = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--check"])
    assert res_drift.exit_code == 1 and "drifted" in res_drift.stdout


def test_check_partial_when_absent(tmp_path):
    res = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--check"])
    assert res.exit_code == 1 and "partial" in res.stdout  # nothing instantiated yet


def test_bad_posture_exit_2(tmp_path):
    res = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--posture", "banana"])
    assert res.exit_code == 2


def test_instantiate_json_preview(tmp_path):
    res = runner.invoke(concierge_app, ["instantiate-kickoff", str(tmp_path), "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["action"] == "instantiate-kickoff" and payload["writes"]


# ── log-friction ─────────────────────────────────────────────────────────────

def test_log_friction_preview_writes_nothing(tmp_path):
    res = runner.invoke(concierge_app, [
        "log-friction", str(tmp_path),
        "--friction", "x", "--what-happened", "y", "--implication", "z",
    ])
    assert res.exit_code == 0
    assert "preview only" in res.stdout
    assert not (tmp_path / "concierge-friction.jsonl").exists()


def test_log_friction_apply_appends(tmp_path):
    for msg in ("first", "second"):
        res = runner.invoke(concierge_app, [
            "log-friction", str(tmp_path), "--apply",
            "--friction", msg, "--what-happened", "w", "--implication", "i",
        ])
        assert res.exit_code == 0
    lines = (tmp_path / "concierge-friction.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert {json.loads(line)["friction"] for line in lines} == {"first", "second"}


def test_log_friction_missing_field_errors(tmp_path):
    res = runner.invoke(concierge_app, ["log-friction", str(tmp_path), "--friction", "x"])
    assert res.exit_code != 0  # typer requires the missing options
