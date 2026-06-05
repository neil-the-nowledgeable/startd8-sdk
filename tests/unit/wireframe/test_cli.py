"""CLI tests (FR-W9, FR-W10): stdout JSON contract, exit semantics, advisory default."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from startd8.cli_wireframe import wireframe

# Single-command Typer app: invoked WITHOUT the command name (Typer collapses it).
app = typer.Typer()
app.command()(wireframe)

runner = CliRunner()


def test_json_stdout_is_parseable_json_only(golden_root: Path) -> None:
    """R4-F1: with --json, stdout is machine output — no Rich tree bytes."""
    result = runner.invoke(app, ["--project", str(golden_root), "--json", "--no-write"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["schema_version"] == 1
    assert "Wireframe —" not in result.stdout  # tree suppressed without --verbose


def test_tree_renders_by_default_and_exit_zero_on_issues(tmp_path: Path) -> None:
    """Advisory contract: an empty project (everything not_defined) still exits 0."""
    result = runner.invoke(app, ["--project", str(tmp_path), "--no-write"])
    assert result.exit_code == 0, result.output
    assert "Wireframe —" in result.output
    assert "not defined" in result.output


def test_bad_inputs_file_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "inputs.yaml"
    bad.write_text("inputs:\n  bogus: {path: x}\n", encoding="utf-8")
    result = runner.invoke(
        app, ["--project", str(tmp_path), "--inputs", str(bad), "--no-write"]
    )
    assert result.exit_code == 2


def test_persists_plan_unless_no_write(mini_root: Path) -> None:
    result = runner.invoke(app, ["--project", str(mini_root)])
    assert result.exit_code == 0, result.output
    persisted = mini_root / ".startd8" / "wireframe" / "wireframe-plan.json"
    assert persisted.is_file()
    assert json.loads(persisted.read_text(encoding="utf-8"))["_meta"]["emit_context"] == "cli"


def test_only_issues_hides_planned_sections(golden_root: Path) -> None:
    result = runner.invoke(
        app, ["--project", str(golden_root), "--only-issues", "--no-write"]
    )
    assert result.exit_code == 0, result.output
    assert "Entities & CRUD" not in result.output  # planned on the golden fixture
    assert "Content Inputs" in result.output       # not_defined (home.md missing)
