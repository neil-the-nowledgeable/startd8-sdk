"""CLI orchestrator tests for `startd8 generate handoff` (the operator surface).

Mirrors the plan projector's CLI tests (a lesson the standard carries: exercise the operator surface,
not only the core) — write / stdout / solo-skip / --check drift / --sarif / --base.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

REQ = """# Widget — Requirements

**Format:** det-req/0.1
**Pairs with:** *(plan deferred)*

> **Semantic name:** *SDK builds a widget.*
> **Canonical ref:** `cc:intent:demo:requirement:req-42`

## Objectives

- **O-1:** the widget builds — target: it builds.

- **FR-1 — Build the widget.** Name: The SDK builds a widget. Touches: `src/startd8/widget.py`. Verify: `startd8 widget build` exits 0. Serves: O-1
"""

LEDGER_DELIVERED = "| **REQ-42 Widget** | FR-1 | built, tests green (abc1234) |\n"


def _w(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_generate_handoff_writes(tmp_path):
    req = _w(tmp_path, "REQ-42.md", REQ)
    out = tmp_path / "HANDOFF-42.md"
    r = runner.invoke(
        generate_app,
        ["handoff", "-r", str(req), "--base", "abc1234", "--out", str(out)],
    )
    assert r.exit_code == 0, r.output
    body = out.read_text(encoding="utf-8")
    assert "formatVersion:** det-handoff/0.1" in body
    assert "base:** main @ abc1234" in body
    assert "FR-1" in body


def test_generate_handoff_solo_skips_exit_0(tmp_path):
    req = _w(tmp_path, "REQ-42.md", REQ)
    ledger = _w(tmp_path, "LEDGER.md", LEDGER_DELIVERED)
    r = runner.invoke(
        generate_app, ["handoff", "-r", str(req), "--ledger", str(ledger)]
    )
    assert r.exit_code == 0
    assert "skipped" in r.output.lower()


def test_generate_handoff_check_in_sync_and_drift(tmp_path):
    req = _w(tmp_path, "REQ-42.md", REQ)
    out = tmp_path / "HANDOFF-42.md"
    assert (
        runner.invoke(
            generate_app,
            ["handoff", "-r", str(req), "--base", "abc1234", "--out", str(out)],
        ).exit_code
        == 0
    )
    ok = runner.invoke(
        generate_app,
        ["handoff", "-r", str(req), "--base", "abc1234", "--out", str(out), "--check"],
    )
    assert ok.exit_code == 0, ok.output
    assert "in_sync" in ok.output
    out.write_text(out.read_text() + "\nEDIT\n", encoding="utf-8")
    drift = runner.invoke(
        generate_app,
        ["handoff", "-r", str(req), "--base", "abc1234", "--out", str(out), "--check"],
    )
    assert drift.exit_code == 1


def test_generate_handoff_sarif(tmp_path):
    req = _w(tmp_path, "REQ-42.md", REQ)
    out = tmp_path / "HANDOFF-42.md"
    sarif = tmp_path / "h.sarif.json"
    r = runner.invoke(
        generate_app,
        [
            "handoff",
            "-r",
            str(req),
            "--base",
            "abc1234",
            "--out",
            str(out),
            "--sarif",
            str(sarif),
        ],
    )
    assert r.exit_code == 0, r.output
    doc = json.loads(sarif.read_text(encoding="utf-8"))
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "startd8-handoff-projector"
