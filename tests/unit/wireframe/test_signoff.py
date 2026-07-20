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
from startd8.wireframe.signoff import (
    SignoffError,
    format_approval_check,
    format_signoff,
    load_signoff,
    open_flags,
    stale_approvals,
)

app = typer.Typer()
app.command()(wireframe)
runner = CliRunner()


def _export(sections: list, **over) -> dict:
    """A payload in the exact shape wireframe_view/_template.py::exportSign downloads."""
    out = {
        "app": over.get("app", "wfdemo"),
        "audience": over.get("audience", {"role": "end_user", "fluency": "intermediate"}),
        "reviewed_at": over.get("reviewed_at", "2026-07-20T01:19:40.369Z"),
        "sections": sections,
    }
    if "inputs_fingerprint" in over:  # SO-1: stamp the plan identity (omit to model a pre-provenance export)
        out["inputs_fingerprint"] = over["inputs_fingerprint"]
    return out


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


def _signoff(sections: list) -> dict:
    """A loaded/normalized sign-off (as load_signoff returns), for the pure approve↔diff functions."""
    return {"app": "x", "audience": {"role": "end_user"}, "reviewed_at": "", "sections": sections}


def _diff(*changed_keys: str) -> dict:
    """A diff_plans-shaped result whose only changed sections are *changed_keys*."""
    return {"unchanged": not changed_keys, "fingerprint_changed": True, "shape": {}, "content": None,
            "sections": [{"key": k, "title": k.title(), "added": ["/x"], "removed": [],
                          "status_changed": {}, "sec_status": None} for k in changed_keys]}


def test_stale_approvals_flags_approved_sections_that_changed() -> None:
    so = _signoff([
        {"key": "pages", "title": "Screens", "status": "ok", "note": ""},
        {"key": "forms", "title": "Forms", "status": "flag", "note": "add a date field"},
        {"key": "entities", "title": "Things", "status": "ok", "note": ""},
    ])
    # 'pages' was approved AND changed → stale; 'entities' approved but unchanged → not stale.
    stale = stale_approvals(_diff("pages"), so)
    assert [s["key"] for s in stale] == ["pages"]
    assert stale_approvals(_diff("entities"), so)[0]["key"] == "entities"
    assert stale_approvals(_diff("forms"), so) == []          # 'forms' was flagged, not approved

    report = format_approval_check(_diff("pages"), so)
    assert "you approved changed since" in report and "Pages" in report     # stale headline (diff's title)
    assert "still flagged" in report and "Forms" in report                  # the open flag persists

    # a diff that changes only a NON-approved section (forms was flagged) → the approval still holds
    holds = format_approval_check(_diff("forms"), so)
    assert "none of the sections you approved have changed" in holds

    # SO-3: the sign-off's age is surfaced in the header (shown, not auto-gated — SO-1 owns identity)
    dated = dict(so, reviewed_at="2026-07-20T04:00:00Z")
    assert "2026-07-20T04:00:00Z" in format_approval_check(_diff("pages"), dated)


def test_cli_approve_diff_gates_on_stale_approval(golden_copy: Path, tmp_path: Path) -> None:
    """Full approve↔diff: save a baseline, sign off approving a section, change that section's manifest,
    then --diff --signoff flags the approval as stale and exits non-zero."""
    runner.invoke(app, ["--project", str(golden_copy)])       # persist the baseline (the approved snapshot)

    so = _write(tmp_path, _export([
        {"key": "pages", "title": "Screens & menus", "status": "ok", "note": ""},   # owner approves pages…
        {"key": "entities", "title": "What it tracks", "status": "ok", "note": ""},
    ]))
    pages_yaml = golden_copy / "prisma" / "pages.yaml"        # …then a page is added (pages changes)
    pages_yaml.write_text(
        pages_yaml.read_text(encoding="utf-8")
        + "  - slug: /contact\n    title: Contact\n    content: pages/contact.md\n    nav_label: Contact\n",
        encoding="utf-8",
    )
    r = runner.invoke(app, ["--project", str(golden_copy), "--diff", "--signoff", str(so), "--no-write"])
    assert r.exit_code == 1                                   # stale approval blocks the handoff
    assert "you approved changed since" in r.output
    assert "Since the last saved preview" in r.output         # the full structural diff is shown too


def _baseline_fingerprint(project: Path) -> str:
    """The inputs_fingerprint of the persisted baseline plan (what a real sign-off would carry)."""
    body = json.loads((project / ".startd8" / "wireframe" / "wireframe-plan.json").read_text(encoding="utf-8"))
    return body["inputs_fingerprint"]


def test_cli_approve_diff_rejects_a_foreign_signoff(golden_copy: Path, tmp_path: Path) -> None:
    """SO-1 — a sign-off whose stamped plan identity doesn't match this project is REFUSED (exit 2), instead
    of silently cross-referencing by generic section keys and reporting a confident-but-wrong approval check."""
    runner.invoke(app, ["--project", str(golden_copy)])           # persist the baseline
    foreign = _write(tmp_path, _export(
        [{"key": "pages", "title": "Screens", "status": "ok", "note": ""}],
        inputs_fingerprint="deadbeef" * 8,                        # a different plan's fingerprint
    ))
    r = runner.invoke(app, ["--project", str(golden_copy), "--diff", "--signoff", str(foreign), "--no-write"])
    assert r.exit_code == 2 and "DIFFERENT plan" in r.output


def test_cli_approve_diff_accepts_a_matching_signoff(golden_copy: Path, tmp_path: Path) -> None:
    """SO-1 — a sign-off stamped with THIS plan's fingerprint passes the provenance gate (no warning) and the
    approval check runs normally (a changed approved section → stale → exit 1)."""
    runner.invoke(app, ["--project", str(golden_copy)])           # persist the baseline
    so = _write(tmp_path, _export(
        [{"key": "pages", "title": "Screens & menus", "status": "ok", "note": ""}],
        inputs_fingerprint=_baseline_fingerprint(golden_copy),    # the RIGHT identity
    ))
    pages = golden_copy / "prisma" / "pages.yaml"                 # change the approved section
    pages.write_text(
        pages.read_text(encoding="utf-8")
        + "  - slug: /c\n    title: C\n    content: pages/c.md\n    nav_label: C\n",
        encoding="utf-8",
    )
    r = runner.invoke(app, ["--project", str(golden_copy), "--diff", "--signoff", str(so), "--no-write"])
    assert r.exit_code == 1                                        # stale approval gate, not a provenance error
    assert "DIFFERENT plan" not in r.output and "predates provenance" not in r.output
    assert "you approved changed since" in r.output


def test_cli_approve_diff_tolerates_pre_provenance_signoff(golden_copy: Path, tmp_path: Path) -> None:
    """SO-1 backward-compat — an old export with no fingerprint proceeds best-effort with a warning."""
    runner.invoke(app, ["--project", str(golden_copy)])
    old = _write(tmp_path, _export([{"key": "entities", "title": "Things", "status": "ok", "note": ""}]))
    r = runner.invoke(app, ["--project", str(golden_copy), "--diff", "--signoff", str(old), "--no-write"])
    assert r.exit_code == 0 and "predates provenance" in r.output  # unverifiable but not blocked


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
