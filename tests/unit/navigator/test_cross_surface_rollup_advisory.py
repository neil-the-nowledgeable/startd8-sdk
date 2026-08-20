"""EC-CS-7 / EC-CS-10 — navig8r→cockpit rollup + validate advisories."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.cli import app
from startd8.navigator.view_definition import (
    BASE_NAVIG8R_DEFINITION,
    activation_severity_from_cockpit_attention,
    attention_counts_from_navig8r_statuses,
    cross_surface_consumption_advisories,
    rollup_cockpit_attentions,
    rollup_navig8r_statuses_to_attention,
)

pytestmark = pytest.mark.unit

RUNNER = CliRunner()
_NS = BASE_NAVIG8R_DEFINITION.node_state


def test_ec_cs_7_attention_counts_and_worst_case_rollup():
    counts = attention_counts_from_navig8r_statuses(
        ["grounded", "spec", "awaiting", "excluded", "unknown"], _NS
    )
    assert counts == {"ok": 1, "review": 2, "backlog": 1, "blocked": 1}
    assert rollup_cockpit_attentions(["ok", "review", "backlog"]) == "review"
    assert rollup_cockpit_attentions(["ok", "blocked"]) == "blocked"
    assert rollup_navig8r_statuses_to_attention(["grounded"], _NS) == "ok"
    assert rollup_navig8r_statuses_to_attention(["grounded", "unknown"], _NS) == "blocked"
    assert rollup_navig8r_statuses_to_attention([], _NS) == "ok"
    assert attention_counts_from_navig8r_statuses(["nope"], _NS)["blocked"] == 1
    assert activation_severity_from_cockpit_attention("blocked") == "blocked"
    assert activation_severity_from_cockpit_attention("review") == "attention"
    assert activation_severity_from_cockpit_attention("ok") == "ok"


def test_ec_cs_10_validate_prints_advisories_and_exits_zero():
    notes = cross_surface_consumption_advisories()
    assert any("H1" in n for n in notes)
    assert any("EC-CS-8" in n for n in notes)
    res = RUNNER.invoke(app, ["navigator", "view-definition", "--validate"])
    assert res.exit_code == 0, res.output
    assert "definitions valid" in res.output
    assert "advisory:" in res.output
    assert "surface_links" in res.output
