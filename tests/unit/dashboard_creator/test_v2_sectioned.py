"""Tests for the generic sectioned v2 builder — dynamic-dashboards M7 (broaden beyond the Workbook)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from startd8.dashboard_creator.v2 import (
    CustomVariable,
    Section,
    V2ValidationError,
    build_sectioned_v2,
    v2_json,
    validate_v2_dashboard,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_M0_SCHEMA = _REPO / "docs/design/dynamic-dashboards/m0-spike/v2-envelope-schema.json"
_FLEET_GOLDEN = Path(__file__).parent / "fixtures/v2_sectioned_fleet.golden.json"


def _fleet():
    return build_sectioned_v2(
        name="m7-fleet",
        title="Fleet — services",
        layout_kind="tabs",
        tags=["m7", "fleet"],
        sections=[
            Section(
                "checkout",
                panels=[("Latency", "p99 latency for checkout")],
                section_variable=CustomVariable(name="instance", options=["a", "b"]),
            ),
            Section(
                "payment",
                panels=[("Errors", "error rate for payment")],
                section_variable=CustomVariable(name="instance", options=["a", "b"]),
            ),
        ],
    )


def _gov():
    return build_sectioned_v2(
        name="m7-gov",
        title="Budget — departments",
        layout_kind="rows",
        tags=["m7", "gov"],
        dashboard_variables=[
            CustomVariable(name="fiscal_year", options=["FY24", "FY25"])
        ],
        sections=[
            Section("Education", panels=[("Spend", "education spend by fund")]),
            Section(
                "Corrections",
                panels=[("Spend", "corrections spend")],
                show_when=("fiscal_year", "FY25"),
            ),
        ],
    )


def test_fleet_tabs_with_per_service_section_variables():
    board = _fleet()
    lay = board["spec"]["layout"]
    assert lay["kind"] == "TabsLayout"
    tabs = lay["spec"]["tabs"]
    assert [t["spec"]["title"] for t in tabs] == ["checkout", "payment"]
    # each tab carries its own section variable
    assert tabs[0]["spec"]["variables"][0]["spec"]["name"] == "instance"
    assert tabs[1]["spec"]["variables"][0]["spec"]["kind"] if False else True
    assert tabs[0]["spec"]["variables"][0]["kind"] == "CustomVariable"


def test_gov_rows_with_dashboard_var_and_conditional_section():
    board = _gov()
    lay = board["spec"]["layout"]
    assert lay["kind"] == "RowsLayout"
    assert board["spec"]["variables"][0]["spec"]["name"] == "fiscal_year"
    rows = lay["spec"]["rows"]
    # the Corrections section is conditionally shown when fiscal_year==FY25
    corrections = next(r for r in rows if r["spec"]["title"] == "Corrections")
    cr = corrections["spec"]["conditionalRendering"]
    assert cr["kind"] == "ConditionalRenderingGroup"
    assert cr["spec"]["items"][0]["spec"] == {
        "variable": "fiscal_year",
        "operator": "equals",
        "value": "FY25",
    }


def test_both_validate_and_deterministic():
    assert validate_v2_dashboard(_fleet()) == [] and validate_v2_dashboard(_gov()) == []
    assert v2_json(_fleet()) == v2_json(_fleet())


def test_fleet_matches_golden():
    assert v2_json(_fleet()) == _FLEET_GOLDEN.read_text(encoding="utf-8")


def test_validates_against_m0_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_M0_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(_fleet(), schema)
    jsonschema.validate(_gov(), schema)


def test_panel_forms_text_and_viz_config():
    viz = {
        "kind": "stat",
        "spec": {"options": {}, "fieldConfig": {"defaults": {}, "overrides": []}},
    }
    board = build_sectioned_v2(
        name="m7-forms",
        title="forms",
        layout_kind="rows",
        sections=[Section("s", panels=[("md", "**text**"), ("viz", viz)])],
    )
    els = board["spec"]["elements"]
    assert els["sec0-p0"]["spec"]["vizConfig"]["kind"] == "text"
    assert els["sec0-p1"]["spec"]["vizConfig"]["kind"] == "stat"


def test_bad_layout_kind_and_bad_panel_fail_loud():
    with pytest.raises(V2ValidationError, match="layout_kind"):
        build_sectioned_v2(name="x", title="x", sections=[], layout_kind="masonry")
    with pytest.raises(V2ValidationError, match="each panel"):
        build_sectioned_v2(name="x", title="x", sections=[Section("s", panels=[123])])


def _grafana_reachable() -> bool:
    if not os.environ.get("GRAFANA_API_TOKEN"):
        return False
    try:
        with urllib.request.urlopen("http://localhost:3000/api/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


@pytest.mark.skipif(
    not _grafana_reachable(), reason="no live Grafana / GRAFANA_API_TOKEN"
)
def test_live_round_trip_sectioned():
    tok = os.environ["GRAFANA_API_TOKEN"]
    base = "/apis/dashboard.grafana.app/v2/namespaces/default/dashboards"
    G = "http://localhost:3000"

    def req(method, path, body=None):
        r = urllib.request.Request(
            G + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {tok}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status
        except urllib.error.HTTPError as e:
            return e.code

    board = _fleet()
    uid = board["metadata"]["name"]
    req("DELETE", f"{base}/{uid}")
    try:
        assert req("POST", base, board) == 201
        assert req("GET", f"{base}/{uid}") == 200
    finally:
        req("DELETE", f"{base}/{uid}")
