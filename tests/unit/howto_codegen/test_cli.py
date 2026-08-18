"""CliRunner tests for `startd8 generate howto` (STANDARD Part 5 exit-code contract)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

_REQ_WITH_COMMANDS = """# Widget Exporter — Requirements

**Version:** 0.2.0
**Format:** det-req/0.1

> **Semantic name:** *Widget exporter emits a CSV of widgets.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-99`

## Functional requirements

- **FR-1 — Export command.** Add `startd8 widget export --out <p>`. Touches: src/startd8/widget/export.py. Verify: ok. Serves: O-1

## Contract projection

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| widget-export | command | structure | new: `startd8 widget export --out <p>` |
| out-flag | option | structure | `--out <p>` target path |
"""

_REQ_SOLO = """# Internal Refactor — Requirements

**Version:** 0.1.0
**Format:** det-req/0.1

> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-98`

## Functional requirements

- **FR-1 — Consolidate.** Merge helpers. Touches: src/startd8/x/helper.py. Verify: ok. Serves: O-1

## Contract projection

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| WidgetModel | entity | structure | a data model, not a command |
"""


def _write_req(tmp_path: Path, text: str) -> Path:
    (tmp_path / "src" / "startd8").mkdir(parents=True, exist_ok=True)
    req = tmp_path / "REQ.md"
    req.write_text(text, encoding="utf-8")
    return req


def test_write_to_stdout(tmp_path):
    req = _write_req(tmp_path, _REQ_WITH_COMMANDS)
    result = runner.invoke(generate_app, ["howto", "-r", str(req)])
    assert result.exit_code == 0, result.output
    assert "det-howto/0.1" in result.output
    assert "widget-export" in result.output


def test_write_to_out_file(tmp_path):
    req = _write_req(tmp_path, _REQ_WITH_COMMANDS)
    out = tmp_path / "HOWTO_widget.md"
    result = runner.invoke(generate_app, ["howto", "-r", str(req), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "GENERATED det-howto/0.1" in out.read_text()


def test_solo_req_skips_exit_0(tmp_path):
    """STANDARD 6a — a solo REQ (no command surface) prints skipped, exit 0."""
    req = _write_req(tmp_path, _REQ_SOLO)
    result = runner.invoke(generate_app, ["howto", "-r", str(req)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output.lower()


def test_check_in_sync(tmp_path):
    """--check on a freshly-written doc → in_sync, exit 0."""
    req = _write_req(tmp_path, _REQ_WITH_COMMANDS)
    out = tmp_path / "HOWTO_widget.md"
    assert (
        runner.invoke(
            generate_app, ["howto", "-r", str(req), "--out", str(out)]
        ).exit_code
        == 0
    )
    result = runner.invoke(
        generate_app, ["howto", "-r", str(req), "--out", str(out), "--check"]
    )
    assert result.exit_code == 0, result.output
    assert "in_sync" in result.output


def test_check_drift(tmp_path):
    """--check on a tampered doc → drift, exit 1."""
    req = _write_req(tmp_path, _REQ_WITH_COMMANDS)
    out = tmp_path / "HOWTO_widget.md"
    runner.invoke(generate_app, ["howto", "-r", str(req), "--out", str(out)])
    out.write_text(out.read_text() + "\nhand-edited drift\n", encoding="utf-8")
    result = runner.invoke(
        generate_app, ["howto", "-r", str(req), "--out", str(out), "--check"]
    )
    assert result.exit_code == 1, result.output
    assert "drift" in result.output


def test_sarif_written(tmp_path):
    req = _write_req(tmp_path, _REQ_WITH_COMMANDS)
    sarif = tmp_path / "howto.sarif.json"
    result = runner.invoke(
        generate_app, ["howto", "-r", str(req), "--sarif", str(sarif)]
    )
    assert result.exit_code == 0, result.output
    assert sarif.exists()
    doc = json.loads(sarif.read_text())
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "det-howto-projector"


def test_missing_requirements_errors(tmp_path):
    result = runner.invoke(generate_app, ["howto", "-r", str(tmp_path / "nope.md")])
    assert result.exit_code == 2, result.output
