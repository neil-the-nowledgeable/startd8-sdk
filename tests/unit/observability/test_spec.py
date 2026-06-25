# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M0: ObservabilitySpec model + observability.yaml normalizer (no generation change)."""

from __future__ import annotations

import pytest

from startd8.observability.spec import (
    ObservabilitySpec,
    Signal,
    Threshold,
    from_observability_yaml,
)

pytestmark = pytest.mark.unit

# A project-AGNOSTIC fixture (FR-OAA-8: no project identifiers in SDK source). Shapes mirror a real
# observability.yaml: a convention RED signal, a domain signal, a receiver, and verbatim context.
SAMPLE = {
    "domain": "observability",
    "provenance_default": "config-default",
    "industry_dataset": "end_user_application",
    "service_levels": {"availability": "99.5", "latency_p99": "500ms"},
    "collection": {"metrics_interval": "30s"},
    "alerting": {
        "channels": ["#alerts"],
        "receivers": [
            {"name": "default", "type": "webhook", "target": "${WEBHOOK_URL}",
             "severities": ["critical", "warning"]},
        ],
        "metric_thresholds": {
            "app_error_rate": {"op": ">", "value": 0.02, "unit": "ratio",
                               "severity": "critical", "for": "5m"},
            "widget_backlog": {"op": ">", "value": 0, "unit": "count",
                               "severity": "warning", "for": "0m"},
        },
    },
    "runbook": {"overview": "what failure looks like"},
}


def test_thresholds_become_signals():
    spec = from_observability_yaml(SAMPLE)
    names = {s.name for s in spec.signals}
    assert names == {"app_error_rate", "widget_backlog"}
    by_name = {s.name: s for s in spec.signals}
    assert by_name["app_error_rate"].threshold == Threshold(
        op=">", value=0.02, severity="critical", for_="5m", unit="ratio"
    )
    assert all(s.origin == "declared" for s in spec.signals)


def test_value_numeric_type_preserved():
    spec = from_observability_yaml(SAMPLE)
    by_name = {s.name: s.threshold.value for s in spec.signals}
    assert isinstance(by_name["app_error_rate"], float) and by_name["app_error_rate"] == 0.02
    assert isinstance(by_name["widget_backlog"], int) and by_name["widget_backlog"] == 0


def test_metric_thresholds_round_trip_exact():
    spec = from_observability_yaml(SAMPLE)
    assert spec.metric_thresholds() == SAMPLE["alerting"]["metric_thresholds"]


def test_receivers_round_trip_exact():
    spec = from_observability_yaml(SAMPLE)
    assert spec.receivers_list() == SAMPLE["alerting"]["receivers"]


def test_context_carries_the_rest_losslessly():
    spec = from_observability_yaml(SAMPLE)
    assert spec.context["service_levels"] == SAMPLE["service_levels"]
    assert spec.context["collection"] == SAMPLE["collection"]
    assert spec.context["runbook"] == SAMPLE["runbook"]
    assert spec.context["alerting"]["channels"] == ["#alerts"]
    # the modeled surfaces are NOT duplicated into context
    assert "metric_thresholds" not in spec.context.get("alerting", {})
    assert "receivers" not in spec.context.get("alerting", {})


def test_top_level_scalars():
    spec = from_observability_yaml(SAMPLE)
    assert spec.provenance_default == "config-default"
    assert spec.industry_dataset == "end_user_application"
    assert spec.domain == "observability"


def test_absent_alerting_is_empty_not_error():
    spec = from_observability_yaml({"domain": "observability"})
    assert spec.signals == [] and spec.receivers == []


@pytest.mark.parametrize("bad", [
    {"alerting": {"metric_thresholds": {"m": {"op": "=>", "value": 1}}}},   # bad op
    {"alerting": {"metric_thresholds": {"m": {"op": ">"}}}},                 # missing value
    {"alerting": {"metric_thresholds": {"m": "not-a-mapping"}}},             # malformed row
    {"alerting": {"receivers": [{"type": "webhook"}]}},                      # receiver without name
    {"alerting": []},                                                        # alerting not a mapping
])
def test_strict_loud_fail(bad):
    with pytest.raises(ValueError):
        from_observability_yaml(bad)


@pytest.mark.parametrize("bad_value", ["soon", True, [1, 2], None])
def test_non_numeric_threshold_value_rejected(bad_value):
    with pytest.raises(ValueError, match="number"):
        from_observability_yaml(
            {"alerting": {"metric_thresholds": {"m": {"op": ">", "value": bad_value}}}}
        )


def test_expr_escape_hatch_is_representable():
    # A signal may carry a raw PromQL expr instead of a declarative threshold (AlertTemplate shape).
    s = Signal(name="custom", expr='rate(x[5m]) > 0', origin="declared")
    spec = ObservabilitySpec(signals=[s])
    assert spec.metric_thresholds() == {}  # expr-only signals are not threshold rows
    assert spec.signals[0].expr == 'rate(x[5m]) > 0'
