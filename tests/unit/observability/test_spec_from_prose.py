# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

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
    ("https://hooks.test/x", True),                       # .test TLD with a path boundary → safe
    ("https://hooks.slack.com/services/XXX", False), ("ops@real-company.com", False),
    ("https://api.test.evil.com/hook", False),            # ".test." is NOT the TLD → unsafe (the fix)
])
def test_secret_safe_predicate(target, safe):
    assert secret_safe(target) is safe


def test_extraction_scoped_to_observability_section():
    """A same-named heading outside ## Observability must not leak into the spec (the scope fix)."""
    doc = textwrap.dedent("""\
        ## Other Section

        #### Thresholds

        | Metric | Op | Value |
        |--------|----|-------|
        | not_mine | > | 99 |

        ## Observability

        #### Thresholds

        | Metric | Op | Value | Severity | For |
        |--------|----|-------|----------|-----|
        | mine | > | 0 | warning | 0m |
    """)
    spec = extract_observability(doc)
    assert {s.name for s in spec.signals} == {"mine"}


def test_literal_secret_target_loud_fails():
    bad = PROSE.replace("${WEBHOOK_URL}", "https://hooks.slack.com/services/SECRET")
    with pytest.raises(ValueError, match="secret"):
        extract_observability(bad)


def test_bad_op_loud_fails():
    bad = PROSE.replace("| > | 0.02 |", "| => | 0.02 |")
    with pytest.raises(ValueError):
        extract_observability(bad)


# --- Slices 2-3: service-levels / collection / channels / runbook → context --- #

PROSE_FULL = textwrap.dedent("""\
    ## Observability

    - Provenance default: config-default

    ### Service levels

    - Availability: 99.5
    - Latency p99: 500ms

    #### Per service

    | Service | Availability | Latency p99 |
    |---------|--------------|-------------|
    | entry-app | 99.9 | 300ms |

    ### Collection

    - Metrics interval: 30s
    - Log level: info

    ### Alerting

    #### Channels

    - #alerts

    #### Receivers

    | Name | Type | Target | Severities |
    |------|------|--------|------------|
    | default | webhook | ${WEBHOOK_URL} | critical, warning |

    #### Thresholds

    | Metric | Op | Value | Unit | Severity | For |
    |--------|----|-------|------|----------|-----|
    | app_error_rate | > | 0.02 | ratio | critical | 5m |

    ### Runbook

    - Overview: what failure looks like
    - Escalation: solo -> vendor

    #### Risks

    | Type | Description | Mitigation | Priority |
    |------|-------------|------------|----------|
    | availability | scheduler stops | dead-man switch | high |

    #### Procedures

    - Triage from the dashboard: runtime or build?
    - Check the scheduler ran
""")

YAML_FULL = {
    "provenance_default": "config-default",
    "service_levels": {
        "availability": "99.5", "latency_p99": "500ms",
        "per_service": {"entry-app": {"availability": "99.9", "latency_p99": "300ms"}},
    },
    "collection": {"metrics_interval": "30s", "log_level": "info"},
    "alerting": {
        "channels": ["#alerts"],
        "receivers": [{"name": "default", "type": "webhook", "target": "${WEBHOOK_URL}",
                       "severities": ["critical", "warning"]}],
        "metric_thresholds": {"app_error_rate": {"op": ">", "value": 0.02, "unit": "ratio",
                                                 "severity": "critical", "for": "5m"}},
    },
    "runbook": {
        "overview": "what failure looks like",
        "escalation": "solo -> vendor",
        "risks": [{"type": "availability", "description": "scheduler stops",
                   "mitigation": "dead-man switch", "priority": "high"}],
        "procedures": ["Triage from the dashboard: runtime or build?", "Check the scheduler ran"],
    },
}


def test_prose_matches_yaml_full_spec_slices_1_3():
    """The prose and YAML front doors produce the SAME spec over the WHOLE observability.yaml."""
    prose = extract_observability(PROSE_FULL)
    yml = from_observability_yaml(YAML_FULL)
    assert prose.metric_thresholds() == yml.metric_thresholds()   # Slice 1
    assert prose.receivers_list() == yml.receivers_list()         # Slice 1
    assert prose.context == yml.context                           # Slices 2-3 (the whole context)


def test_context_pieces_parsed():
    ctx = extract_observability(PROSE_FULL).context
    assert ctx["service_levels"]["latency_p99"] == "500ms"
    assert ctx["service_levels"]["per_service"]["entry-app"] == {"availability": "99.9", "latency_p99": "300ms"}
    assert ctx["collection"]["metrics_interval"] == "30s"
    assert ctx["alerting"]["channels"] == ["#alerts"]
    assert ctx["runbook"]["risks"][0]["priority"] == "high"
    assert ctx["runbook"]["procedures"] == [
        "Triage from the dashboard: runtime or build?", "Check the scheduler ran"]
