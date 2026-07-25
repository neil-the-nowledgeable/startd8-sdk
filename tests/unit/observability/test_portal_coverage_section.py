# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Portal coverage section (REQ-TCP-120..124) — integration with coverage_reconcile.

Builds a real reconciliation from an inline LiveComparisonReport, threads it through
build_portal_spec / build_all_portal_specs, and asserts the persona-scoped coverage panels.
"""

from __future__ import annotations

import pytest

from startd8.observability.artifact_generator import (
    BusinessContext,
    GenerationReport,
    ServiceHints,
)
from startd8.observability import coverage_reconcile as cr
from startd8.observability.portal_spec_builder import (
    build_all_portal_specs,
    build_portal_spec,
)


@pytest.fixture
def business():
    return BusinessContext(
        criticality="critical", availability="99.9", latency_p99="200ms",
        owner="commerce-team", project_id="online-boutique", project_name="Online Boutique",
    )


@pytest.fixture
def services():
    return [ServiceHints(service_id="checkoutservice"), ServiceHints(service_id="cartservice")]


@pytest.fixture
def report():
    return GenerationReport(
        project_id="online-boutique", generated_at="2026-07-24T00:00:00Z",
        artifacts=[], services_processed=2,
    )


@pytest.fixture
def metadata():
    return {}


@pytest.fixture
def coverage():
    # checkout: critical + bound; cart: critical + no_telemetry
    live_report = {
        "report_version": 2, "status": "fail", "reason": "cart dark",
        "tier_a": {"gaps": {}},
        "tier_b": {
            "per_service": {
                "checkoutservice": {"total": 1, "passed": 1, "coverage": 1.0,
                                    "signals": {"latency": {"total": 1, "passed": 1}}},
                "cartservice": {"total": 1, "passed": 0, "coverage": 0.0,
                                "signals": {"latency": {"total": 1, "passed": 0}}},
            },
            "target_drift": {"declared_absent": [], "checked": True},
            "verdicts": [],
        },
        "pending_verdicts": [],
    }
    crit = {"checkoutservice": "critical", "cartservice": "critical"}
    records = cr.reconcile(live_report, criticality_map=crit)
    return {"records": [r.to_dict() for r in records], "summary": cr.summarize(records)}


def _titles(spec):
    return [p.get("title") for p in spec["panels"]]


def _content(spec, title):
    for p in spec["panels"]:
        if p.get("title") == title:
            return p.get("options", {}).get("content", "")
    return ""


# ─────────────────────────── backward compatibility ────────────────────────


def test_no_coverage_payload_means_no_coverage_panel(business, services, report, metadata):
    spec = build_portal_spec(business, services, report, metadata, persona="operator")
    assert not any("Coverage" in (t or "") and "Telemetry" in (t or "") for t in _titles(spec))


def test_empty_records_render_data_readiness_note(business, services, report, metadata):
    spec = build_portal_spec(business, services, report, metadata, persona="operator",
                             coverage={"records": [], "summary": {}})
    assert "Telemetry Coverage" in _titles(spec)
    assert "data-readiness" in _content(spec, "Telemetry Coverage")


# ─────────────────────────── persona-scoped rendering ──────────────────────


def test_executive_shows_coverage_by_criticality(business, services, report, metadata, coverage):
    spec = build_portal_spec(business, services, report, metadata, persona="executive", coverage=coverage)
    body = _content(spec, "Business Observability — Coverage by Criticality")
    assert "Critical-tier coverage:" in body
    assert "50%" in body                       # 1 of 2 critical bound
    assert "cartservice" in body               # named as not-observable


def test_operator_shows_incident_readiness_for_dark_service(business, services, report, metadata, coverage):
    spec = build_portal_spec(business, services, report, metadata, persona="operator", coverage=coverage)
    body = _content(spec, "Incident Readiness — Telemetry Coverage")
    assert "cartservice" in body
    assert "no telemetry" in body
    assert "checkoutservice" not in body       # bound services are not in the gap list


def test_manager_shows_portfolio_health(business, services, report, metadata, coverage):
    spec = build_portal_spec(business, services, report, metadata, persona="manager", coverage=coverage)
    body = _content(spec, "Portfolio Health — Telemetry Coverage")
    assert "checkoutservice" in body and "cartservice" in body   # ALL services


def test_engineer_shows_expected_vs_actual_axes(business, services, report, metadata, coverage):
    spec = build_portal_spec(business, services, report, metadata, persona="engineer", coverage=coverage)
    body = _content(spec, "Per-Service Coverage — Expected vs Actual")
    assert "latency" in body                   # the expected axis
    assert "Expected axes" in body


def test_build_all_personas_thread_coverage(business, services, report, metadata, coverage):
    specs = build_all_portal_specs(business, services, report, metadata, coverage=coverage)
    # every generated persona spec that gates "coverage" carries a coverage panel
    assert specs
    for spec in specs:
        titles = " ".join(t or "" for t in _titles(spec))
        assert "Coverage" in titles
