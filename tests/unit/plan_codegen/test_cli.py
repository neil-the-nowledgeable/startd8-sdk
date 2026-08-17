"""CLI orchestrator tests for `startd8 generate plan` (REQ-29 FR-6 operator surface).

HTH value-path audit (Phase 1) found the core projector well-tested but the *operator surface* — the
`generate plan` command's exit-code contract, solo→skip, drift-check, and SARIF emit — unexercised.
These tests drive the typer command end to end via CliRunner.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

REQ_OWED = """# Widget — Requirements

**Pairs with:** *(plan deferred — spec-only)*

> **Semantic name:** *SDK builds a widget and verifies it.*
> **Canonical ref:** `cc:intent:demo:requirement:req-demo`

- **FR-1 — Build the widget.** Name: The SDK builds a widget. Touches: `src/startd8/widget.py`. Verify: `startd8 widget build` exits 0. Serves: O-1
- **FR-2 — Verify the widget.** Name: The SDK verifies a widget. Touches: `src/startd8/verify.py`. Verify: the widget passes its self-check. Serves: O-2
"""

REQ_SOLO = """# Solo — Requirements

**Pairs with:** the design brief `docs/BRIEF.md`

> **Semantic name:** *A solo requirement.*
> **Canonical ref:** `cc:intent:demo:requirement:req-solo`

- **FR-1 — Do a thing.** Name: Do a thing. Touches: `src/startd8/thing.py`. Verify: it works. Serves: O-1
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_generate_plan_writes_a_conformant_plan(tmp_path):
    req = _write(tmp_path, "REQ-demo.md", REQ_OWED)
    out = tmp_path / "PLAN-demo.md"
    result = runner.invoke(
        generate_app, ["plan", "--requirements", str(req), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "formatVersion:** det-plan/0.1" in body
    assert "maturity:** 0.1" in body


def test_generate_plan_stdout_when_no_out(tmp_path):
    req = _write(tmp_path, "REQ-demo.md", REQ_OWED)
    result = runner.invoke(generate_app, ["plan", "--requirements", str(req)])
    assert result.exit_code == 0
    assert "det-plan/0.1" in result.output


def test_generate_plan_solo_req_skips_exit_0(tmp_path):
    req = _write(tmp_path, "REQ-solo.md", REQ_SOLO)
    result = runner.invoke(generate_app, ["plan", "--requirements", str(req)])
    assert result.exit_code == 0  # correct-absence, not an error
    assert "skipped" in result.output.lower()


def test_generate_plan_check_in_sync_and_drift(tmp_path):
    req = _write(tmp_path, "REQ-demo.md", REQ_OWED)
    out = tmp_path / "PLAN-demo.md"
    assert (
        runner.invoke(
            generate_app, ["plan", "--requirements", str(req), "--out", str(out)]
        ).exit_code
        == 0
    )
    # in-sync → 0
    ok = runner.invoke(
        generate_app, ["plan", "--requirements", str(req), "--out", str(out), "--check"]
    )
    assert ok.exit_code == 0, ok.output
    assert "in_sync" in ok.output
    # tamper → drift → 1
    out.write_text(out.read_text() + "\nHAND EDIT\n", encoding="utf-8")
    drift = runner.invoke(
        generate_app, ["plan", "--requirements", str(req), "--out", str(out), "--check"]
    )
    assert drift.exit_code == 1
    assert "drift" in drift.output


def test_generate_plan_emits_sarif(tmp_path):
    req = _write(tmp_path, "REQ-demo.md", REQ_OWED)
    out = tmp_path / "PLAN-demo.md"
    sarif = tmp_path / "plan.sarif.json"
    result = runner.invoke(
        generate_app,
        ["plan", "--requirements", str(req), "--out", str(out), "--sarif", str(sarif)],
    )
    assert result.exit_code == 0, result.output
    doc = json.loads(sarif.read_text(encoding="utf-8"))
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "startd8-plan-projector"


def test_generate_plan_unknown_strategy_errors(tmp_path):
    req = _write(tmp_path, "REQ-demo.md", REQ_OWED)
    result = runner.invoke(
        generate_app, ["plan", "--requirements", str(req), "--strategy", "bogus"]
    )
    assert result.exit_code == 2  # _EXIT_ERROR
