# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for the fidelity scorecard renderer (A2)."""

from __future__ import annotations

from startd8.observability.fidelity_scorecard import build_fidelity_scorecard


def _report(**over):
    base = {
        "status": "fail",
        "reason": "binding_coverage 0.50 < min 0.9",
        "queries_replayed": 4,
        "queries_excluded": 1,
        "binding_coverage": 0.5,
        "data_coverage": 0.25,
        "bound_no_data": 1,
        "min_coverage": 0.9,
        "suggested_metrics_profile": "span-metrics-connector",
        "per_service": {
            "checkout": {"total": 2, "passed": 2, "coverage": 1.0},
            "cart": {"total": 2, "passed": 0, "coverage": 0.0},
        },
        "per_axis_mismatch_counts": {"service_label_key": 2, "metric_name.throughput": 1},
        "excluded_artifacts": {"loki_rule": 13, "service_monitor": 13},
        "excluded_by_reason": {"unresolved_template_var": 1},
    }
    base.update(over)
    return base


def test_scorecard_headline_and_fix():
    md = build_fidelity_scorecard(_report())
    assert "binding fidelity 50%" in md
    assert "FAIL" in md
    # the one-line fix surfaces the suggested profile
    assert "metricsProfile: span-metrics-connector" in md


def test_scorecard_leaderboard_sorted_desc():
    md = build_fidelity_scorecard(_report())
    # highest-coverage service listed before the lowest
    assert md.index("checkout") < md.index("cart")
    assert "100%" in md and "0%" in md


def test_scorecard_shows_exclusions_degrade_honest():
    md = build_fidelity_scorecard(_report())
    assert "Excluded, honestly" in md
    assert "loki_rule" in md and "service_monitor" in md
    assert "unresolved_template_var" in md


def test_scorecard_no_axis_mismatch_message():
    md = build_fidelity_scorecard(_report(per_axis_mismatch_counts={}))
    assert "No axis mismatches" in md


def test_scorecard_pass_icon():
    md = build_fidelity_scorecard(_report(status="pass", binding_coverage=1.0))
    assert "PASS" in md and "100%" in md
