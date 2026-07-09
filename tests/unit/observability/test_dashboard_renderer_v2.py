"""Tests for the v2 dynamic domain dashboard adapter — dynamic-dashboards M7 adoption (additive)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from startd8.dashboard_creator.v2 import v2_json, validate_v2_dashboard
from startd8.observability.dashboard_renderer import render_domain_dashboard
from startd8.observability.dashboard_renderer_v2 import render_domain_dashboard_v2
from startd8.observability.spec import ObservabilitySpec, Signal, Threshold

pytestmark = pytest.mark.unit

_M0_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "docs/design/dynamic-dashboards/m0-spike/v2-envelope-schema.json"
)


def _spec():
    return ObservabilitySpec(
        signals=[
            Signal(
                "household_bill_overdue",
                Threshold(op=">", value=0, severity="critical", unit="count"),
            ),
            Signal(
                "household_rx_days_to_runout",
                Threshold(op="<", value=7, severity="warning"),
            ),
            Signal("custom_rate", expr="rate(x[5m])"),
        ]
    )


def test_sections_grouped_by_severity():
    board = render_domain_dashboard_v2(_spec(), "household")
    assert board["spec"]["layout"]["kind"] == "RowsLayout"
    titles = [r["spec"]["title"] for r in board["spec"]["layout"]["spec"]["rows"]]
    assert titles == ["Critical", "Warning", "Other"]


def test_timeseries_panel_with_threshold_and_query():
    board = render_domain_dashboard_v2(_spec(), "household")
    # the critical signal → a timeseries panel with a red threshold step and a prometheus query
    crit_item = board["spec"]["layout"]["spec"]["rows"][0]["spec"]["layout"]["spec"][
        "items"
    ][0]
    panel = board["spec"]["elements"][crit_item["spec"]["element"]["name"]]
    assert panel["spec"]["vizConfig"]["kind"] == "timeseries"
    steps = panel["spec"]["vizConfig"]["spec"]["fieldConfig"]["defaults"]["thresholds"][
        "steps"
    ]
    assert steps[-1]["color"] == "red" and steps[-1]["value"] == 0.0
    q = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]
    assert q["group"] == "prometheus" and q["spec"]["expr"] == "household_bill_overdue"


def test_expr_only_signal_charts_its_expr():
    board = render_domain_dashboard_v2(_spec(), "household")
    other = board["spec"]["layout"]["spec"]["rows"][2]["spec"]["layout"]["spec"][
        "items"
    ][0]
    panel = board["spec"]["elements"][other["spec"]["element"]["name"]]
    assert (
        panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
        == "rate(x[5m])"
    )


def test_validates_deterministic_schema():
    board = render_domain_dashboard_v2(_spec(), "household")
    assert validate_v2_dashboard(board) == []
    assert v2_json(board) == v2_json(render_domain_dashboard_v2(_spec(), "household"))
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(board, json.loads(_M0_SCHEMA.read_text(encoding="utf-8")))


def test_empty_spec_is_a_valid_empty_board():
    board = render_domain_dashboard_v2(ObservabilitySpec(), "empty")
    assert board["spec"]["layout"]["spec"]["rows"] == []
    assert validate_v2_dashboard(board) == []


def test_classic_renderer_untouched():
    # additive: the classic path renders exactly as before (a `panels:` DashboardSpec YAML)
    res = render_domain_dashboard(_spec(), "household")
    assert res.status == "generated" and "panels:" in res.content
    # and it does NOT contain any v2 marker
    assert "dashboard.grafana.app/v2" not in res.content


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
def test_live_round_trip_preserves_timeseries_query():
    tok = os.environ["GRAFANA_API_TOKEN"]
    G = "http://localhost:3000"
    base = "/apis/dashboard.grafana.app/v2/namespaces/default/dashboards"

    def req(method, path, body=None, parse=False):
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
                return (x.status, json.load(x)) if parse else x.status
        except urllib.error.HTTPError as e:
            return (e.code, None) if parse else e.code

    board = render_domain_dashboard_v2(_spec(), "obsv2test")
    uid = board["metadata"]["name"]
    req("DELETE", f"{base}/{uid}")
    try:
        assert req("POST", base, board) == 201
        _, got = req("GET", f"{base}/{uid}", parse=True)
        panel = list(got["spec"]["elements"].values())[0]
        assert panel["spec"]["vizConfig"]["kind"] == "timeseries"
        assert panel["spec"]["data"]["spec"]["queries"]  # the query survived
    finally:
        req("DELETE", f"{base}/{uid}")
