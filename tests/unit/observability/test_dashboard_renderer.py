# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""E1: domain dashboard renderer — observability.yaml signals → a DashboardSpec (declare-once)."""

from __future__ import annotations

import pytest
import yaml

from startd8.observability.dashboard_renderer import render_domain_dashboard, _title
from startd8.observability.spec import ObservabilitySpec, Signal, Threshold, from_observability_yaml

pytestmark = pytest.mark.unit


def _dash(result):
    return yaml.safe_load(result.content.split("\n\n", 1)[1])


def test_signal_becomes_panel():
    spec = ObservabilitySpec(signals=[
        Signal("household_chore_overdue", Threshold(op=">", value=0, severity="warning", unit="count")),
    ])
    res = render_domain_dashboard(spec, project_id="household")
    assert res.status == "generated" and res.artifact_type == "dashboard_spec"
    d = _dash(res)
    assert d["uid"] == "obs-domain-household"
    panel = d["panels"][0]
    assert panel["type"] == "timeseries"
    assert panel["title"] == "Household Chore Overdue"
    assert panel["expr"] == "household_chore_overdue"          # charts the METRIC, not the comparison
    assert panel["unit"] == "count"
    # threshold line at the declared value, severity-coloured (warning → orange)
    assert panel["thresholds"][-1] == {"color": "orange", "value": 0.0}


def test_critical_threshold_is_red():
    spec = ObservabilitySpec(signals=[Signal("m", Threshold(op=">", value=1, severity="critical"))])
    assert _dash(render_domain_dashboard(spec))["panels"][0]["thresholds"][-1]["color"] == "red"


def test_grid_layout_two_per_row():
    spec = ObservabilitySpec(signals=[Signal(f"m{i}", Threshold(op=">", value=0)) for i in range(3)])
    gp = [p["gridPos"] for p in _dash(render_domain_dashboard(spec))["panels"]]
    assert (gp[0]["x"], gp[0]["y"]) == (0, 0)
    assert (gp[1]["x"], gp[1]["y"]) == (12, 0)
    assert (gp[2]["x"], gp[2]["y"]) == (0, 8)   # wraps to the next row


def test_expr_only_signal_charts_its_expr():
    spec = ObservabilitySpec(signals=[Signal("custom", expr="rate(x[5m])")])
    panel = _dash(render_domain_dashboard(spec))["panels"][0]
    assert panel["expr"] == "rate(x[5m])" and "thresholds" not in panel


def test_no_signals_skipped():
    res = render_domain_dashboard(ObservabilitySpec())
    assert res.status == "skipped"


def test_output_validates_against_dashboardspec_model():
    """The emitted YAML must parse through /dbrd-cr8r's own DashboardSpec model (round-trip/validity)."""
    from startd8.dashboard_creator.models import DashboardSpec
    spec = ObservabilitySpec(signals=[
        Signal("household_rx_days_to_runout", Threshold(op="<", value=7, severity="warning")),
        Signal("household_bill_overdue", Threshold(op=">", value=0, severity="critical")),
    ])
    d = _dash(render_domain_dashboard(spec, project_id="household"))
    model = DashboardSpec.model_validate(d)        # raises if the shape is invalid
    assert len(model.panels) == 2


def test_full_seam_yaml_to_dashboard():
    """observability.yaml → spec → dashboard (the same file the alerts use)."""
    data = {"alerting": {"metric_thresholds": {
        "household_chore_overdue": {"op": ">", "value": 0, "unit": "count", "severity": "warning", "for": "0m"},
    }}}
    res = render_domain_dashboard(from_observability_yaml(data), project_id="household")
    assert _dash(res)["panels"][0]["expr"] == "household_chore_overdue"


def test_title_helper():
    assert _title("household_rx_days_to_runout") == "Household Rx Days To Runout"
