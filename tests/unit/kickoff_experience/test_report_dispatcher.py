"""The report dispatcher — one machine-readable surface over every read-only kickoff view."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience import schemas
from startd8.kickoff_experience.report import (
    VIEW_SCHEMAS,
    kickoff_report,
    report_views,
)

pytestmark = pytest.mark.unit
runner = CliRunner()


def test_views_and_schemas_are_aligned():
    # every dispatchable view has a declared schema, and vice versa
    assert set(report_views()) == set(VIEW_SCHEMAS)
    assert VIEW_SCHEMAS["status"] == schemas.STATUS


def test_each_view_returns_its_schema_tagged_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_KICKOFF_EXEMPLARS_DIR", str(tmp_path / "reg"))
    assert kickoff_report(tmp_path, "status")["schema"] == schemas.STATUS
    assert kickoff_report(tmp_path, "activation")["schema"] == schemas.ACTIVATION
    assert kickoff_report(tmp_path, "retrospective")["schema"] == schemas.RETROSPECTIVE
    assert kickoff_report(tmp_path, "exemplars")["schema"] == schemas.EXEMPLAR


def test_unknown_view_lists_valid_views():
    r = kickoff_report(".", "bogus")
    assert "error" in r and set(r["views"]) == set(report_views())


def test_report_matches_the_dedicated_callables(tmp_path):
    # the dispatcher must return the SAME payload as the view's own callable (no drift)
    from startd8.kickoff_experience.agentic_view import kickoff_status

    assert kickoff_report(tmp_path, "status") == kickoff_status(tmp_path)


def test_cli_report_lists_views_then_emits_one(tmp_path):
    lst = runner.invoke(kickoff_kernel_app, ["report"])
    d = json.loads(lst.output)
    assert "status" in d["views"] and d["schemas"]["status"] == schemas.STATUS
    one = runner.invoke(kickoff_kernel_app, ["report", "activation", str(tmp_path)])
    assert json.loads(one.output)["schema"] == schemas.ACTIVATION


def test_cli_report_rejects_unknown_view(tmp_path):
    out = runner.invoke(kickoff_kernel_app, ["report", "nope", str(tmp_path)])
    assert out.exit_code == 2 and "unknown view" in out.output
