"""EC-2 wiring — the sign-off importer (`startd8 wireframe --signoff <file>`).

Guards the far end of the preview→approve→build loop: the owner's exported verdict is loaded, reported,
and gated (open flags block the handoff). Input shape is exactly what the HTML preview's ``exportSign``
downloads: ``{app, audience:{role,fluency}, reviewed_at, sections:[{key,title,status,note}]}``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from startd8.cli_wireframe import wireframe
from startd8.wireframe.signoff import SignoffError, format_signoff, load_signoff, open_flags

app = typer.Typer()
app.command()(wireframe)
runner = CliRunner()


def _export(sections: list, **over) -> dict:
    """A payload in the exact shape wireframe_view/_template.py::exportSign downloads."""
    return {
        "app": over.get("app", "wfdemo"),
        "audience": over.get("audience", {"role": "end_user", "fluency": "intermediate"}),
        "reviewed_at": over.get("reviewed_at", "2026-07-20T01:19:40.369Z"),
        "sections": sections,
    }


def _write(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "owner-signoff.json"
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def test_load_normalizes_and_tolerates_missing_fields(tmp_path: Path) -> None:
    p = _write(tmp_path, _export([
        {"key": "pages", "title": "Screens & menus", "status": "ok", "note": ""},
        {"key": "forms", "status": "bogus"},                 # unknown status → unreviewed; no title → key
    ]))
    so = load_signoff(p)
    assert so["app"] == "wfdemo" and so["audience"]["role"] == "end_user"
    assert so["sections"][0] == {"key": "pages", "title": "Screens & menus", "status": "ok", "note": ""}
    assert so["sections"][1]["status"] == "unreviewed"       # bogus status degraded, never fabricated
    assert so["sections"][1]["title"] == "forms"             # missing title falls back to the key


def test_open_flags_and_report(tmp_path: Path) -> None:
    p = _write(tmp_path, _export([
        {"key": "pages", "title": "Screens & menus", "status": "ok", "note": ""},
        {"key": "forms", "title": "Forms", "status": "flag", "note": "needs a date field"},
        {"key": "entities", "title": "What it tracks", "status": "unreviewed", "note": ""},
    ]))
    so = load_signoff(p)
    flags = open_flags(so)
    assert [s["key"] for s in flags] == ["forms"]
    report = format_signoff(so)
    assert "approved 1" in report and "flagged 1" in report and "unreviewed 1" in report
    assert "needs a date field" in report                    # the flag note is the actionable to-do
    assert "What it tracks" in report                        # unreviewed section is named


def test_malformed_signoffs_raise(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(SignoffError):
        load_signoff(bad)
    nosec = tmp_path / "nosec.json"
    nosec.write_text('{"app":"x"}', encoding="utf-8")
    with pytest.raises(SignoffError):
        load_signoff(nosec)
    with pytest.raises(SignoffError):
        load_signoff(tmp_path / "does-not-exist.json")


def test_cli_signoff_gates_on_open_flags(tmp_path: Path) -> None:
    flagged = _write(tmp_path, _export([
        {"key": "pages", "title": "Screens", "status": "ok", "note": ""},
        {"key": "forms", "title": "Forms", "status": "flag", "note": "add a date field"},
    ]))
    r = runner.invoke(app, ["--signoff", str(flagged)])
    assert r.exit_code == 1                                   # open flag blocks the handoff
    assert "add a date field" in r.output

    clean = _write(tmp_path, _export([{"key": "pages", "title": "Screens", "status": "ok", "note": ""}]))
    ok = runner.invoke(app, ["--signoff", str(clean)])
    assert ok.exit_code == 0 and "fully signed off" in ok.output

    bad = tmp_path / "bad.json"
    bad.write_text("nope", encoding="utf-8")
    assert runner.invoke(app, ["--signoff", str(bad)]).exit_code == 2   # fatal input, like other flags
