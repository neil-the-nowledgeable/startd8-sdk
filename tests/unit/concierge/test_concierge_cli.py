"""CLI smoke tests for `startd8 concierge` (FR-C13) — same code path as the MCP tool.

Uses Typer's CliRunner against the `concierge_app` directly (no full `startd8` app needed).
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli_concierge import concierge_app

runner = CliRunner()


def _make_project(tmp_path):
    root = tmp_path / "proj"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    (root / "REQUIREMENTS_app.md").write_text(
        "# Reqs\n## Entities\nAI assists\nOwned fields\nCoverage\n", encoding="utf-8"
    )
    (root / "docs" / "kickoff" / "inputs" / "conventions.yaml").write_text(
        "domain: conventions\nprovenance_default: authored\n", encoding="utf-8"
    )
    return root


def test_survey_exit0_and_renders(tmp_path):
    root = _make_project(tmp_path)
    result = runner.invoke(concierge_app, ["survey", str(root)])
    assert result.exit_code == 0
    assert "Concierge survey" in result.stdout
    assert "extraction-format" in result.stdout  # the matching req doc is tagged


def test_survey_json_is_valid(tmp_path):
    root = _make_project(tmp_path)
    result = runner.invoke(concierge_app, ["survey", str(root), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["action"] == "survey"


def test_assess_exit0_reports_provenance(tmp_path):
    root = _make_project(tmp_path)
    result = runner.invoke(concierge_app, ["assess", str(root)])
    assert result.exit_code == 0
    assert "conventions" in result.stdout
    assert "authored" in result.stdout


def test_bad_input_exits_2(tmp_path):
    result = runner.invoke(concierge_app, ["assess", str(tmp_path / "nope")])
    assert result.exit_code == 2
