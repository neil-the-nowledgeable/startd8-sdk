# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M5a: prose (§2.12 ## Observability) → ObservabilitySpec, Slice 1 (Thresholds + Receivers).

The headline is `test_full_seam_*`: prose → spec → active alert rule (the "communicate by
formatting" goal), and `test_prose_matches_yaml_*`: the prose front door produces the SAME spec as
the YAML front door (FR-OTP-4/13)."""

from __future__ import annotations

import textwrap

import pytest
import yaml

from startd8.observability.spec import from_observability_yaml
from startd8.observability.spec_from_prose import extract_observability, secret_safe
from startd8.observability.alert_renderer import render_domain_alert_rules

pytestmark = pytest.mark.unit

# Project-AGNOSTIC fixture (FR-OTP-12). The prose and the YAML are the two front doors to the SAME
# spec — Slice 1 is the #### Thresholds + #### Receivers tables under ## Observability.
PROSE = textwrap.dedent("""\
    # Some Project — Observability (prose source)

    Intro prose here is tolerated and ignored.

    ## Observability

    - Provenance default: config-default
    - Industry dataset: end_user_application

    ### Alerting

    #### Receivers

    | Name | Type | Target | Severities |
    |------|------|--------|------------|
    | default | webhook | ${WEBHOOK_URL} | critical, warning |

    #### Thresholds

    | Metric | Op | Value | Unit | Severity | For |
    |--------|----|-------|------|----------|-----|
    | app_error_rate | > | 0.02 | ratio | critical | 5m |
    | widget_backlog | > | 0 | count | warning | 0m |
""")

YAML_EQUIV = {
    "provenance_default": "config-default",
    "industry_dataset": "end_user_application",
    "alerting": {
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
}


def test_prose_matches_yaml_signals_and_receivers():
    prose = extract_observability(PROSE)
    yml = from_observability_yaml(YAML_EQUIV)
    assert prose.metric_thresholds() == yml.metric_thresholds()   # one model, two front doors
    assert prose.receivers_list() == yml.receivers_list()


def test_scalars_and_value_types():
    spec = extract_observability(PROSE)
    assert spec.provenance_default == "config-default"
    assert spec.industry_dataset == "end_user_application"
    thr = {s.name: s.threshold for s in spec.signals}
    assert isinstance(thr["app_error_rate"].value, float) and thr["app_error_rate"].value == 0.02
    assert isinstance(thr["widget_backlog"].value, int) and thr["widget_backlog"].value == 0


def test_full_seam_prose_to_active_rule():
    """The closed seam: prose → spec → active alert rule (the 'communicate by formatting' goal)."""
    spec = extract_observability(PROSE)
    res = render_domain_alert_rules(spec, project_id="demo")
    assert res.status == "generated"
    rules = yaml.safe_load(res.content.split("\n\n", 1)[1])["groups"][0]["rules"]
    by = {r["alert"]: r for r in rules}
    assert by["AppErrorRate"]["expr"] == "app_error_rate > 0.02"
    assert by["AppErrorRate"]["for"] == "5m"
    assert by["WidgetBacklog"]["labels"]["severity"] == "warning"


def test_absent_section_is_empty_spec():
    spec = extract_observability("# A doc with no Observability section\n\njust prose.\n")
    assert spec.signals == [] and spec.receivers == []


@pytest.mark.parametrize("target,safe", [
    ("${HOOK_URL}", True), ("", True), ("ops@team.test", True), ("#alerts", True),
    ("https://hooks.slack.com/services/XXX", False), ("ops@real-company.com", False),
])
def test_secret_safe_predicate(target, safe):
    assert secret_safe(target) is safe


def test_literal_secret_target_loud_fails():
    bad = PROSE.replace("${WEBHOOK_URL}", "https://hooks.slack.com/services/SECRET")
    with pytest.raises(ValueError, match="secret"):
        extract_observability(bad)


def test_bad_op_loud_fails():
    bad = PROSE.replace("| > | 0.02 |", "| => | 0.02 |")
    with pytest.raises(ValueError):
        extract_observability(bad)
