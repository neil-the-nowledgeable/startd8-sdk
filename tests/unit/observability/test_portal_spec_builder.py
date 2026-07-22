"""Tests for portal_spec_builder — onboarding portal DashboardSpec generation."""

import pytest

from startd8.observability.artifact_generator import (
    ArtifactResult,
    BusinessContext,
    ConventionMetric,
    GenerationReport,
    ServiceHints,
)
from startd8.observability.portal_spec_builder import (
    build_all_portal_specs,
    build_portal_spec,
    _PERSONA_SECTIONS,
    _extract_alert_rules,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def business():
    return BusinessContext(
        criticality="critical",
        availability="99.9",
        latency_p99="200ms",
        owner="commerce-team",
        project_id="online-boutique",
        project_name="Online Boutique",
    )


@pytest.fixture
def services():
    return [
        ServiceHints(
            service_id="checkoutservice",
            transport="grpc",
            language="Go",
            detected_databases=["PostgreSQL"],
            convention_metrics=[
                ConventionMetric("rpc.server.duration", "histogram", "otel_semconv:grpc"),
            ],
        ),
        ServiceHints(
            service_id="frontend",
            transport="http",
            language="JavaScript",
            detected_databases=[],
            convention_metrics=[
                ConventionMetric("http.server.duration", "histogram", "otel_semconv:http"),
                ConventionMetric("http.server.request.body.size", "histogram", "otel_semconv:http"),
            ],
        ),
    ]


_CHECKOUT_ALERT_YAML = """\
groups:
- name: checkoutservice.slo
  rules:
  - alert: CheckoutserviceLatencyP99High
    expr: 'histogram_quantile(0.99, rate(rpc_server_duration_bucket{service="checkoutservice"}[5m])) > 0.2'
    for: 5m
    labels:
      severity: critical
      service: checkoutservice
    annotations:
      summary: checkoutservice p99 latency exceeds 200ms
"""

_FRONTEND_ALERT_YAML = """\
groups:
- name: frontend.slo
  rules:
  - alert: FrontendLatencyP99High
    expr: 'histogram_quantile(0.99, rate(http_server_duration_bucket{service="frontend"}[5m])) > 0.5'
    for: 5m
    labels:
      severity: critical
      service: frontend
    annotations:
      summary: frontend p99 latency exceeds 500ms
  - alert: FrontendErrorRateHigh
    expr: 'rate(http_server_duration_count{service="frontend",status_code=~"5.."}[5m]) > 0.001'
    for: 5m
    labels:
      severity: warning
      service: frontend
    annotations:
      summary: frontend error rate exceeds 0.1%
"""


@pytest.fixture
def report():
    return GenerationReport(
        project_id="online-boutique",
        generated_at="2026-03-23T12:00:00Z",
        artifacts=[
            ArtifactResult("alert_rule", "checkoutservice", "alerts/checkoutservice.yaml", "generated", content=_CHECKOUT_ALERT_YAML),
            ArtifactResult("dashboard_spec", "checkoutservice", "dashboards/checkoutservice.yaml", "generated"),
            ArtifactResult("slo_definition", "checkoutservice", "slos/checkoutservice.yaml", "generated"),
            ArtifactResult("alert_rule", "frontend", "alerts/frontend.yaml", "generated", content=_FRONTEND_ALERT_YAML),
            ArtifactResult("dashboard_spec", "frontend", "dashboards/frontend.yaml", "generated"),
            ArtifactResult("slo_definition", "frontend", "slos/frontend.yaml", "generated"),
        ],
        services_processed=2,
    )


@pytest.fixture
def metadata():
    return {
        "objectives": [
            {"description": "Availability", "metricKey": "availability", "target": "99.9", "unit": "%"},
            {"description": "Latency P99", "metricKey": "latency_p99", "target": "200", "unit": "ms"},
        ],
        "service_communication_graph": {
            "services": {
                "checkoutservice": {"calls_to": ["paymentservice"], "called_by": ["frontend"]},
                "frontend": {"calls_to": ["checkoutservice"], "called_by": []},
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests: build_portal_spec
# ---------------------------------------------------------------------------


class TestBuildPortalSpec:

    def test_returns_valid_dashboard_spec_shape(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)

        assert "title" in spec
        assert "uid" in spec
        assert "panels" in spec
        assert "tags" in spec
        assert "links" in spec
        assert len(spec["panels"]) > 0

    def test_uid_convention(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        assert spec["uid"] == "cc-portal-online-boutique"

    def test_uid_with_persona_suffix(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="engineer")
        assert spec["uid"] == "cc-portal-online-boutique-engineer"

    def test_operator_is_default_persona(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        # Operator UID has no suffix
        assert spec["uid"] == "cc-portal-online-boutique"
        assert "operator" in spec["tags"]

    def test_title_includes_project_id(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        assert "online-boutique" in spec["title"]

    def test_title_includes_persona_for_non_operator(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="manager")
        assert "Manager" in spec["title"]

    def test_tags_include_project_and_persona(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="engineer")
        assert "portal" in spec["tags"]
        assert "onboarding" in spec["tags"]
        assert "online-boutique" in spec["tags"]
        assert "engineer" in spec["tags"]

    def test_dashboard_links_for_each_service(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        links = spec["links"]
        assert len(links) == 2
        assert any("checkoutservice" in l["title"] for l in links)
        assert any("frontend" in l["title"] for l in links)
        # Links use Grafana internal routing
        assert links[0]["url"].startswith("/d/")

    def test_links_have_include_vars(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        for link in spec["links"]:
            assert link["includeVars"] is True
            assert link["keepTime"] is True


class TestProjectOverviewPanels:

    def test_overview_present_for_operator(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="operator")
        text_panels = [p for p in spec["panels"] if p["type"] == "text"]
        titles = [p["title"] for p in text_panels]
        assert "Project Overview" in titles

    def test_overview_contains_project_id(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        overview = next(p for p in spec["panels"] if p["title"] == "Project Overview")
        content = overview["options"]["content"]
        assert "online-boutique" in content

    def test_overview_contains_criticality(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        overview = next(p for p in spec["panels"] if p["title"] == "Project Overview")
        content = overview["options"]["content"]
        assert "CRITICAL" in content

    def test_overview_contains_owner(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        overview = next(p for p in spec["panels"] if p["title"] == "Project Overview")
        content = overview["options"]["content"]
        assert "commerce-team" in content

    def test_overview_contains_timestamp(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        overview = next(p for p in spec["panels"] if p["title"] == "Project Overview")
        content = overview["options"]["content"]
        assert "2026-03-23" in content

    def test_overview_has_group(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        overview = next(p for p in spec["panels"] if p["title"] == "Project Overview")
        assert overview["group"] == "Project Overview"


class TestServiceInventoryPanels:

    def test_service_table_present(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Service Inventory")
        content = inv["options"]["content"]
        assert "checkoutservice" in content
        assert "frontend" in content

    def test_service_table_contains_protocol(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Service Inventory")
        content = inv["options"]["content"]
        assert "GRPC" in content
        assert "HTTP" in content

    def test_service_table_contains_language(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Service Inventory")
        content = inv["options"]["content"]
        assert "Go" in content
        assert "JavaScript" in content

    def test_service_table_contains_databases(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Service Inventory")
        content = inv["options"]["content"]
        assert "PostgreSQL" in content

    def test_service_table_contains_metric_count(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Service Inventory")
        content = inv["options"]["content"]
        # checkoutservice has 1 metric, frontend has 2
        assert "| 1 |" in content
        assert "| 2 |" in content

    def test_stat_panels_present(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        stat_panels = [p for p in spec["panels"] if p["type"] == "stat"]
        assert len(stat_panels) == 2
        titles = [p["title"] for p in stat_panels]
        assert "Services" in titles
        assert "Artifacts Generated" in titles

    def test_service_count_stat(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        svc_stat = next(p for p in spec["panels"] if p["title"] == "Services")
        assert svc_stat["expr"] == "vector(2)"

    def test_artifact_count_stat(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        art_stat = next(p for p in spec["panels"] if p["title"] == "Artifacts Generated")
        assert art_stat["expr"] == "vector(6)"


class TestEmptyServices:

    def test_no_services_shows_placeholder(self, business, report, metadata):
        spec = build_portal_spec(business, [], report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Service Inventory")
        assert "No services detected" in inv["options"]["content"]

    def test_no_services_no_stat_panels(self, business, report, metadata):
        spec = build_portal_spec(business, [], report, metadata)
        stat_panels = [p for p in spec["panels"] if p["type"] == "stat"]
        assert len(stat_panels) == 0

    def test_no_services_still_has_links_empty(self, business, report, metadata):
        spec = build_portal_spec(business, [], report, metadata)
        assert spec["links"] == []


class TestPersonaGating:

    def test_all_personas_produce_valid_specs(self, business, services, report, metadata):
        for persona in _PERSONA_SECTIONS:
            spec = build_portal_spec(business, services, report, metadata, persona=persona)
            assert len(spec["panels"]) > 0
            assert spec["uid"].startswith("cc-portal-")

    def test_unknown_persona_defaults_to_operator(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="unknown")
        # Should get operator sections (the fallback)
        assert len(spec["panels"]) > 0


class TestBuildAllPortalSpecs:

    def test_produces_one_per_persona(self, business, services, report, metadata):
        specs = build_all_portal_specs(business, services, report, metadata)
        assert len(specs) == len(_PERSONA_SECTIONS)

    def test_uids_are_unique(self, business, services, report, metadata):
        specs = build_all_portal_specs(business, services, report, metadata)
        uids = [s["uid"] for s in specs]
        assert len(uids) == len(set(uids))


# ---------------------------------------------------------------------------
# Phase 2: Content section tests
# ---------------------------------------------------------------------------


class TestObjectivesSection:

    def test_objectives_present_for_operator(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Project Objectives" in titles

    def test_objectives_contains_availability_target(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        obj = next(p for p in spec["panels"] if p["title"] == "Project Objectives")
        content = obj["options"]["content"]
        assert "99.9" in content
        assert "availability" in content

    def test_objectives_contains_latency_target(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        obj = next(p for p in spec["panels"] if p["title"] == "Project Objectives")
        content = obj["options"]["content"]
        assert "200" in content
        assert "latency_p99" in content

    def test_objectives_omitted_when_missing(self, business, services, report):
        spec = build_portal_spec(business, services, report, {})
        titles = [p["title"] for p in spec["panels"]]
        assert "Project Objectives" not in titles

    def test_objectives_has_group(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        obj = next(p for p in spec["panels"] if p["title"] == "Project Objectives")
        assert obj["group"] == "Objectives"

    def test_objectives_excluded_for_engineer(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="engineer")
        titles = [p["title"] for p in spec["panels"]]
        assert "Project Objectives" not in titles


class TestAlertInventorySection:

    def test_alert_inventory_present(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Alert Inventory" in titles

    def test_alert_inventory_lists_all_rules(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Alert Inventory")
        content = inv["options"]["content"]
        assert "CheckoutserviceLatencyP99High" in content
        assert "FrontendLatencyP99High" in content
        assert "FrontendErrorRateHigh" in content

    def test_alert_inventory_shows_severity(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Alert Inventory")
        content = inv["options"]["content"]
        assert "CRITICAL" in content
        assert "WARNING" in content

    def test_alert_inventory_shows_duration(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Alert Inventory")
        content = inv["options"]["content"]
        assert "5m" in content

    def test_alert_inventory_omitted_when_no_alerts(self, business, services, metadata):
        empty_report = GenerationReport(
            project_id="online-boutique",
            generated_at="2026-03-23T12:00:00Z",
            artifacts=[],
        )
        spec = build_portal_spec(business, services, empty_report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Alert Inventory" not in titles

    def test_alert_inventory_has_group(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        inv = next(p for p in spec["panels"] if p["title"] == "Alert Inventory")
        assert inv["group"] == "Alert Inventory"


class TestDashboardLinksSection:

    def test_dashboard_links_panel_present(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Dashboard Links" in titles

    def test_dashboard_links_contain_service_ids(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Dashboard Links")
        content = panel["options"]["content"]
        assert "checkoutservice" in content
        assert "frontend" in content

    def test_dashboard_links_contain_grafana_urls(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Dashboard Links")
        content = panel["options"]["content"]
        assert "/d/cc-obs-checkoutservice/" in content
        assert "/d/cc-obs-frontend/" in content

    def test_dashboard_links_omitted_when_no_dashboards(self, business, services, metadata):
        empty_report = GenerationReport(
            project_id="online-boutique",
            generated_at="2026-03-23T12:00:00Z",
            artifacts=[],
        )
        spec = build_portal_spec(business, services, empty_report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Dashboard Links" not in titles


class TestCommunicationGraphSection:

    def test_communication_graph_present(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Service Communication" in titles

    def test_communication_graph_shows_edges(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Service Communication")
        content = panel["options"]["content"]
        assert "paymentservice" in content
        assert "frontend" in content

    def test_communication_graph_shows_no_deps_when_empty(self, business, services, report):
        empty_metadata = {
            "service_communication_graph": {
                "services": {
                    "checkoutservice": {"calls_to": [], "called_by": []},
                }
            }
        }
        spec = build_portal_spec(business, services, report, empty_metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Service Communication")
        assert "No inter-service dependencies detected" in panel["options"]["content"]

    def test_communication_graph_shows_no_deps_when_missing(self, business, services, report):
        spec = build_portal_spec(business, services, report, {})
        panel = next(p for p in spec["panels"] if p["title"] == "Service Communication")
        assert "No inter-service dependencies detected" in panel["options"]["content"]

    def test_communication_graph_has_group(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Service Communication")
        assert panel["group"] == "Communication Graph"

    def test_communication_excluded_for_manager(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="manager")
        titles = [p["title"] for p in spec["panels"]]
        assert "Service Communication" not in titles


class TestProvenanceSection:

    def test_provenance_present(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Run Provenance" in titles

    def test_provenance_contains_timestamp(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Run Provenance")
        content = panel["options"]["content"]
        assert "2026-03-23T12:00:00Z" in content

    def test_provenance_contains_project_id(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Run Provenance")
        content = panel["options"]["content"]
        assert "online-boutique" in content

    def test_provenance_contains_artifact_count(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Run Provenance")
        content = panel["options"]["content"]
        assert "6" in content  # 6 generated artifacts

    def test_provenance_includes_pipeline_version(self, business, services, report):
        meta_with_version = {"pipeline_version": "7.78.0"}
        spec = build_portal_spec(business, services, report, meta_with_version)
        panel = next(p for p in spec["panels"] if p["title"] == "Run Provenance")
        content = panel["options"]["content"]
        assert "7.78.0" in content

    def test_provenance_has_group(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        panel = next(p for p in spec["panels"] if p["title"] == "Run Provenance")
        assert panel["group"] == "Provenance"


class TestExtractAlertRules:

    def test_extracts_from_groups_format(self):
        rules = _extract_alert_rules(_CHECKOUT_ALERT_YAML)
        assert len(rules) == 1
        assert rules[0]["alert"] == "CheckoutserviceLatencyP99High"
        assert rules[0]["severity"] == "critical"
        assert rules[0]["for"] == "5m"

    def test_extracts_multiple_rules(self):
        rules = _extract_alert_rules(_FRONTEND_ALERT_YAML)
        assert len(rules) == 2
        names = [r["alert"] for r in rules]
        assert "FrontendLatencyP99High" in names
        assert "FrontendErrorRateHigh" in names

    def test_returns_empty_for_empty_content(self):
        assert _extract_alert_rules("") == []
        assert _extract_alert_rules(None) == []

    def test_returns_empty_for_invalid_yaml(self):
        assert _extract_alert_rules("not: [valid: yaml: {{") == []

    def test_returns_empty_for_non_dict(self):
        assert _extract_alert_rules("- just\n- a\n- list") == []


class TestOperatorHasAllSections:
    """Verify operator persona includes all Phase 1–3 sections."""

    def test_operator_has_all_sections(self, business, services, report, metadata):
        # Add quality scores to report for quality section
        for a in report.artifacts:
            a.quality = {"score": 0.85, "issues": [], "repairs_applied": []}
        spec = build_portal_spec(business, services, report, metadata, persona="operator")
        titles = [p["title"] for p in spec["panels"]]
        assert "Project Overview" in titles
        assert "Service Inventory" in titles
        assert "Project Objectives" in titles
        assert "Alert Inventory" in titles
        assert "Dashboard Links" in titles
        assert "Service Communication" in titles
        assert "Artifact Quality" in titles
        assert "Run Provenance" in titles


# ---------------------------------------------------------------------------
# Phase 3: Quality, security, health tests
# ---------------------------------------------------------------------------


@pytest.fixture
def report_with_quality():
    """Report with quality scores on artifacts."""
    artifacts = [
        ArtifactResult("alert_rule", "checkoutservice", "alerts/checkoutservice.yaml", "generated", content=_CHECKOUT_ALERT_YAML),
        ArtifactResult("dashboard_spec", "checkoutservice", "dashboards/checkoutservice.yaml", "generated"),
        ArtifactResult("slo_definition", "checkoutservice", "slos/checkoutservice.yaml", "generated"),
        ArtifactResult("alert_rule", "frontend", "alerts/frontend.yaml", "generated", content=_FRONTEND_ALERT_YAML),
        ArtifactResult("dashboard_spec", "frontend", "dashboards/frontend.yaml", "generated"),
        ArtifactResult("slo_definition", "frontend", "slos/frontend.yaml", "error"),
    ]
    # Add quality scores
    artifacts[0].quality = {"score": 0.90, "issues": [], "repairs_applied": []}
    artifacts[1].quality = {"score": 0.75, "issues": [{"check": "OBS-100", "severity": "warning", "message": "test"}], "repairs_applied": ["gridpos"]}
    artifacts[2].quality = {"score": 0.80, "issues": [], "repairs_applied": []}
    artifacts[3].quality = {"score": 0.85, "issues": [], "repairs_applied": []}
    artifacts[4].quality = {"score": 0.70, "issues": [{"check": "OBS-200", "severity": "info", "message": "test2"}], "repairs_applied": []}
    # artifacts[5] has no quality (errored)
    return GenerationReport(
        project_id="online-boutique",
        generated_at="2026-03-23T12:00:00Z",
        artifacts=artifacts,
        services_processed=2,
    )


class TestQualitySection:

    def test_quality_gauge_present(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata)
        gauge = next((p for p in spec["panels"] if p["title"] == "Artifact Quality"), None)
        assert gauge is not None
        assert gauge["type"] == "gauge"
        assert gauge["unit"] == "percentunit"

    def test_quality_breakdown_table(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata)
        breakdown = next(p for p in spec["panels"] if p["title"] == "Quality Breakdown")
        content = breakdown["options"]["content"]
        assert "alert_rule" in content
        assert "dashboard_spec" in content
        assert "slo_definition" in content
        assert "Composite" in content

    def test_quality_shows_issues_and_repairs(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata)
        breakdown = next(p for p in spec["panels"] if p["title"] == "Quality Breakdown")
        content = breakdown["options"]["content"]
        assert "Issues found" in content
        assert "Repairs applied" in content

    def test_quality_placeholder_when_no_scores(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        quality_panels = [p for p in spec["panels"] if p.get("group") == "Quality"]
        assert len(quality_panels) == 1
        assert "unavailable" in quality_panels[0]["options"]["content"]

    def test_quality_has_group(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata)
        gauge = next(p for p in spec["panels"] if p["title"] == "Artifact Quality")
        assert gauge["group"] == "Quality"

    def test_scoreless_functional_slo_does_not_break_quality_panels(
        self, business, services, report_with_quality, metadata
    ):
        # Regression (#254): a functional-SLO artifact carries a scoreless quality
        # dict ({emitted_fr_ids, unfulfilled}). It must not KeyError in
        # _build_quality_panels nor pollute the score averages.
        func_slo = ArtifactResult(
            "slo_definition", "checkoutservice",
            "slos/checkoutservice-functional-slo.yaml", "generated",
        )
        func_slo.quality = {"emitted_fr_ids": ["FR-006"], "unfulfilled": []}
        report_with_quality.artifacts.append(func_slo)
        spec = build_portal_spec(business, services, report_with_quality, metadata)
        gauge = next(p for p in spec["panels"] if p["title"] == "Artifact Quality")
        assert gauge["type"] == "gauge"

    def test_quality_included_for_manager(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="manager")
        titles = [p["title"] for p in spec["panels"]]
        assert "Artifact Quality" in titles

    def test_quality_excluded_for_engineer(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="engineer")
        titles = [p["title"] for p in spec["panels"]]
        assert "Artifact Quality" not in titles


class TestSecuritySection:

    def test_security_present_when_data_exists(self, business, services, report, metadata):
        metadata_with_sec = {
            **metadata,
            "security": {
                "aggregate_score": 0.95,
                "injection_blocked": 3,
                "credential_blocked": 1,
            },
        }
        spec = build_portal_spec(business, services, report, metadata_with_sec)
        titles = [p["title"] for p in spec["panels"]]
        assert "Security Posture" in titles

    def test_security_contains_score(self, business, services, report, metadata):
        metadata_with_sec = {
            **metadata,
            "security": {"aggregate_score": 0.95},
        }
        spec = build_portal_spec(business, services, report, metadata_with_sec)
        panel = next(p for p in spec["panels"] if p["title"] == "Security Posture")
        assert "95%" in panel["options"]["content"]

    def test_security_omitted_when_missing(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata)
        titles = [p["title"] for p in spec["panels"]]
        assert "Security Posture" not in titles

    def test_security_reads_from_kaizen_metrics(self, business, services, report, metadata):
        meta = {
            **metadata,
            "kaizen_metrics": {
                "security": {
                    "aggregate_score": 0.88,
                    "injection_blocked": 5,
                },
            },
        }
        spec = build_portal_spec(business, services, report, meta)
        panel = next(p for p in spec["panels"] if p["title"] == "Security Posture")
        assert "88%" in panel["options"]["content"]
        assert "Injection Blocked" in panel["options"]["content"]


class TestArtifactHealthSection:

    def test_health_present_for_manager(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="manager")
        stat_panels = [p for p in spec["panels"] if p.get("group") == "Artifact Health"]
        assert len(stat_panels) >= 1

    def test_health_shows_generated_count(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="manager")
        gen_panel = next(p for p in spec["panels"] if p["title"] == "Generated")
        assert "vector(5)" in gen_panel["expr"]  # 5 generated, 1 errored

    def test_health_shows_errored_count(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="manager")
        err_panel = next(p for p in spec["panels"] if p["title"] == "Errored")
        assert "vector(1)" in err_panel["expr"]

    def test_health_excluded_for_operator(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="operator")
        health_panels = [p for p in spec["panels"] if p.get("group") == "Artifact Health"]
        assert len(health_panels) == 0

    def test_health_excluded_for_engineer(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="engineer")
        health_panels = [p for p in spec["panels"] if p.get("group") == "Artifact Health"]
        assert len(health_panels) == 0


class TestExecutivePersona:

    def test_executive_has_minimal_sections(self, business, services, report_with_quality, metadata):
        spec = build_portal_spec(business, services, report_with_quality, metadata, persona="executive")
        titles = [p["title"] for p in spec["panels"]]
        assert "Project Overview" in titles
        assert "Project Objectives" in titles
        assert "Artifact Quality" in titles
        # Should NOT have operational details
        assert "Service Inventory" not in titles
        assert "Alert Inventory" not in titles
        assert "Service Communication" not in titles
        assert "Run Provenance" not in titles

    def test_executive_uid(self, business, services, report, metadata):
        spec = build_portal_spec(business, services, report, metadata, persona="executive")
        assert spec["uid"] == "cc-portal-online-boutique-executive"


# ---------------------------------------------------------------------------
# Phase 4: Portal validation tests
# ---------------------------------------------------------------------------


class TestPortalValidation:

    def test_valid_portal_json(self):
        from startd8.validators.observability_artifact_checks import validate_portal
        import json

        dashboard = {
            "title": "test — Onboarding Portal",
            "panels": [
                {"type": "text", "title": "Project Overview", "options": {"content": "# Test"}},
                {"type": "text", "title": "Service Inventory", "options": {"content": "| Service |"}},
            ],
        }
        result = validate_portal(json.dumps(dashboard))
        assert result.json_valid
        assert result.has_overview
        assert result.has_service_inventory
        assert result.score > 0.5

    def test_invalid_json(self):
        from startd8.validators.observability_artifact_checks import validate_portal

        result = validate_portal("not valid json")
        assert not result.json_valid
        assert result.score == 0.0

    def test_missing_overview_is_warning(self):
        from startd8.validators.observability_artifact_checks import validate_portal
        import json

        dashboard = {
            "title": "Onboarding Portal",
            "panels": [
                {"type": "text", "title": "Service Inventory", "options": {"content": "test"}},
            ],
        }
        result = validate_portal(json.dumps(dashboard))
        assert not result.has_overview
        assert any(i.check == "OBP-104-3" for i in result.issues)

    def test_no_text_panels_is_error(self):
        from startd8.validators.observability_artifact_checks import validate_portal
        import json

        dashboard = {
            "title": "Portal",
            "panels": [
                {"type": "stat", "title": "Count"},
            ],
        }
        result = validate_portal(json.dumps(dashboard))
        assert result.text_panel_count == 0
        assert any(i.check == "OBP-104-2" for i in result.issues)

    def test_title_check(self):
        from startd8.validators.observability_artifact_checks import validate_portal
        import json

        dashboard = {
            "title": "My Dashboard",
            "panels": [{"type": "text", "title": "Project Overview", "options": {"content": "x"}}],
        }
        result = validate_portal(json.dumps(dashboard))
        assert any(i.check == "OBP-104-6" for i in result.issues)


class TestCoverageGapPanels:
    """QW-1 (#226 FR-9 / #230-233): surface fr_coverage gaps in the portal, self-gating."""

    def _report_with_gaps(self):
        r = GenerationReport(project_id="p", generated_at="t", artifacts=[], services_processed=1)
        r.fr_coverage = {
            "empty_services": ["mailer", "ranker"],
            "ungrounded_kinds": [
                {"service": "ranker", "kind": "ml_inference", "observed_by_nothing": True,
                 "suggested_signals": ["saturation", "lag"], "reason": "..."},
            ],
            "unfulfilled": [{"id": "FR-7", "signal_kind": "freshness"}],
            "emitted": [],
        }
        return r

    def test_panel_absent_when_no_coverage_gaps(self, business, services, report, metadata):
        # report fixture carries no fr_coverage → byte-identical to pre-panel behavior.
        spec = build_portal_spec(business, services, report, metadata, persona="operator")
        assert not any(p["title"] == "Coverage Gaps" for p in spec["panels"])

    def test_panel_present_and_actionable_when_gaps_exist(self, business, services, metadata):
        spec = build_portal_spec(business, services, self._report_with_gaps(), metadata, persona="operator")
        panel = next((p for p in spec["panels"] if p["title"] == "Coverage Gaps"), None)
        assert panel is not None
        content = panel["options"]["content"]
        # P1a: kind-specific next step; P1b: the ∅ symptom folded into the ungrounded row.
        assert "ranker" in content and "saturation/lag" in content
        assert "observed by nothing" in content
        # LH-1: ranker (ungrounded + empty) is NOT double-listed as a bare empty service.
        assert content.count("`ranker`") == 1
        # a plain empty service (mailer, not ungrounded) still shows.
        assert "mailer" in content
        # unfulfilled FR surfaces too.
        assert "FR-7" in content

    def test_panel_gated_out_for_executive_persona(self, business, services, metadata):
        # 'services' section is operator/engineer only — executive never sees the gap panel.
        spec = build_portal_spec(business, services, self._report_with_gaps(), metadata, persona="executive")
        assert not any(p["title"] == "Coverage Gaps" for p in spec["panels"])
