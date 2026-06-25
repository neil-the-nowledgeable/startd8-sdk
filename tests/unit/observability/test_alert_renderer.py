# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M1: domain alert renderer — declared thresholds become ACTIVE rules (the gap close)."""

from __future__ import annotations

import pytest
import yaml

from startd8.observability.alert_renderer import render_domain_alert_rules, _alert_name, _expr_for
from startd8.observability.spec import ObservabilitySpec, Signal, Threshold, from_observability_yaml

pytestmark = pytest.mark.unit


def _rules(result):
    return yaml.safe_load(result.content.split("\n\n", 1)[1])["groups"][0]["rules"]


def test_thresholded_signal_becomes_active_rule():
    spec = ObservabilitySpec(signals=[
        Signal("household_chore_overdue", Threshold(op=">", value=0, severity="warning", for_="0m")),
    ])
    res = render_domain_alert_rules(spec, project_id="household")
    assert res.status == "generated"
    rule = _rules(res)[0]
    # an ACTIVE rule (not a commented stub) with the declarative expr
    assert rule["alert"] == "HouseholdChoreOverdue"
    assert rule["expr"] == "household_chore_overdue > 0"
    assert rule["for"] == "0m"
    assert rule["labels"]["severity"] == "warning"
    assert "# " not in res.content.split("\n\n", 1)[1]  # body has no commented-out stub lines


@pytest.mark.parametrize("op,value,expected", [
    (">", 0, "m > 0"), ("<", 7, "m < 7"), (">=", 3, "m >= 3"),
    ("<=", 5, "m <= 5"), ("==", 1, "m == 1"), (">", 0.05, "m > 0.05"),
])
def test_op_value_to_expr(op, value, expected):
    spec = ObservabilitySpec(signals=[Signal("m", Threshold(op=op, value=value))])
    assert _rules(render_domain_alert_rules(spec))[0]["expr"] == expected


def test_value_type_preserved_in_expr():
    spec = ObservabilitySpec(signals=[
        Signal("ratio_metric", Threshold(op=">", value=0.02)),
        Signal("count_metric", Threshold(op=">", value=0)),
    ])
    exprs = {r["alert"]: r["expr"] for r in _rules(render_domain_alert_rules(spec))}
    assert exprs["RatioMetric"] == "ratio_metric > 0.02"  # float keeps its form
    assert exprs["CountMetric"] == "count_metric > 0"     # int has no .0


def test_raw_expr_escape_hatch_passthrough():
    spec = ObservabilitySpec(signals=[Signal("custom", expr="rate(x[5m]) > 0.1", origin="declared")])
    rule = _rules(render_domain_alert_rules(spec))[0]
    assert rule["expr"] == "rate(x[5m]) > 0.1"  # verbatim, not rebuilt


def test_panel_only_signal_skipped():
    # a signal with neither threshold nor expr is panel-only → not an alert rule
    spec = ObservabilitySpec(signals=[Signal("just_a_panel")])
    res = render_domain_alert_rules(spec)
    assert res.status == "skipped" and "no alertable" in (res.error_message or "")


def test_full_household_shaped_yaml_end_to_end():
    # the real shape: observability.yaml → spec → active domain rules (the closed gap)
    data = {
        "alerting": {"metric_thresholds": {
            "household_rx_days_to_runout": {"op": "<", "value": 7, "unit": "days",
                                            "severity": "warning", "for": "5m"},
            "household_bill_overdue": {"op": ">", "value": 0, "unit": "count",
                                       "severity": "critical", "for": "0m"},
        }},
    }
    res = render_domain_alert_rules(from_observability_yaml(data), project_id="household")
    rules = {r["alert"]: r for r in _rules(res)}
    assert rules["HouseholdRxDaysToRunout"]["expr"] == "household_rx_days_to_runout < 7"
    assert rules["HouseholdRxDaysToRunout"]["for"] == "5m"
    assert rules["HouseholdBillOverdue"]["labels"]["severity"] == "critical"


def test_helpers():
    assert _alert_name("household_chore_overdue") == "HouseholdChoreOverdue"
    assert _alert_name("app.error-rate") == "AppErrorRate"
    assert _expr_for(Signal("m", Threshold(op=">", value=1))) == "m > 1"
    assert _expr_for(Signal("m")) is None


def test_orchestrator_wiring_additive_and_red_byte_identical(tmp_path):
    """FR-OAA-10/12 at the orchestrator level: the observability.yaml param is purely additive —
    absent ⇒ no domain artifact and every other artifact byte-identical; present ⇒ one new active
    domain-alert artifact, RED output unchanged."""
    import json
    from startd8.observability.artifact_generator import generate_observability_artifacts

    meta = {
        "project_id": "demo",
        "instrumentation_hints": {
            "app": {"service_id": "app", "transport": "http", "language": "python",
                    "metrics": {"convention_based": [
                        {"name": "http.server.duration", "type": "histogram",
                         "source": "otel_semconv:http"}]}}},
    }
    meta_path = tmp_path / "onboarding-metadata.json"
    meta_path.write_text(json.dumps(meta))
    obs = tmp_path / "observability.yaml"
    obs.write_text(
        "alerting:\n"
        "  metric_thresholds:\n"
        "    widget_overdue: {op: '>', value: 0, severity: warning, for: 0m}\n"
    )
    out = tmp_path / "out"

    r0 = generate_observability_artifacts(
        onboarding_metadata_path=meta_path, output_dir=out, dry_run=True)
    r1 = generate_observability_artifacts(
        onboarding_metadata_path=meta_path, output_dir=out, dry_run=True,
        observability_yaml_path=obs)

    # absent → no domain artifacts at all
    assert not any("domain-" in a.output_path for a in r0.artifacts)
    # present → exactly one active domain-alert artifact with the declared expr
    dom = [a for a in r1.artifacts if "domain-alerts" in a.output_path]
    assert len(dom) == 1 and dom[0].status == "generated"
    assert "widget_overdue > 0" in dom[0].content
    # E1: present → also exactly one domain-dashboard artifact (same observability.yaml)
    dash = [a for a in r1.artifacts if "domain-dashboard" in a.output_path]
    assert len(dash) == 1 and dash[0].status == "generated"
    # RED / everything-else byte-identical between the two runs (excludes BOTH domain artifacts)
    def others(r):
        return {a.output_path: a.content for a in r.artifacts if "domain-" not in a.output_path}
    assert others(r0) == others(r1)
