"""Tests for observability artifact validators (REQ-KZ-OBS-100–601)."""

import textwrap

import pytest

from startd8.validators.observability_artifact_validators import (
    AlertValidationResult,
    CrossArtifactResult,
    DashboardValidationResult,
    ObservabilityPostmortemResult,
    ServiceArtifactScore,
    SloValidationResult,
    check_cross_artifact_consistency,
    check_metric_names,
    evaluate_observability_artifacts,
    score_artifact,
    score_service_triplet,
    validate_alert_rules,
    validate_dashboard_spec,
    validate_slo_definition,
)


# ---------------------------------------------------------------------------
# Dashboard Spec Validation (REQ-KZ-OBS-100)
# ---------------------------------------------------------------------------

VALID_DASHBOARD = textwrap.dedent("""\
    title: cartservice Observability
    uid: obs-cartservice
    datasources:
      prometheus: prometheus
    panels:
    - type: histogram
      title: Rpc Server Duration
      expr: histogram_quantile(0.99, rate(rpc_server_duration_bucket{service="cartservice"}[5m]))
      unit: s
    variables:
    - type: prometheusDatasource
      name: datasource
""")


class TestDashboardValidation:

    def test_valid_dashboard(self):
        r = validate_dashboard_spec(VALID_DASHBOARD, service_id="cartservice")
        assert r.yaml_valid
        assert r.has_title
        assert r.has_uid
        assert r.panel_count == 1
        assert r.checks_passed >= 8  # gridPos missing = 1 warning

    def test_invalid_yaml(self):
        r = validate_dashboard_spec("{{invalid yaml", service_id="test")
        assert not r.yaml_valid
        assert r.checks_passed == 0
        assert any(i["check"] == "OBS-100a" for i in r.issues)

    def test_missing_title(self):
        content = "uid: obs-test\npanels:\n- expr: up\n  type: stat\n  unit: short\n"
        r = validate_dashboard_spec(content)
        assert any(i["check"] == "OBS-100b" for i in r.issues)

    def test_missing_panels(self):
        content = "title: Test\nuid: obs-test\npanels: []\n"
        r = validate_dashboard_spec(content)
        assert any(i["check"] == "OBS-100d" for i in r.issues)

    def test_panel_missing_expr(self):
        content = "title: Test\nuid: obs-test\npanels:\n- type: stat\n  unit: s\n"
        r = validate_dashboard_spec(content)
        assert any(i["check"] == "OBS-100e" for i in r.issues)

    def test_no_gridpos_is_warning(self):
        r = validate_dashboard_spec(VALID_DASHBOARD)
        grid_issues = [i for i in r.issues if i["check"] == "OBS-100h"]
        assert len(grid_issues) == 1
        assert grid_issues[0]["severity"] == "warning"

    def test_no_variables_is_info(self):
        content = "title: Test\nuid: obs-test\npanels:\n- expr: up\n  type: stat\n  unit: s\n"
        r = validate_dashboard_spec(content)
        var_issues = [i for i in r.issues if i["check"] == "OBS-100j"]
        assert len(var_issues) == 1
        assert var_issues[0]["severity"] == "info"

    def test_checks_total_is_10(self):
        r = validate_dashboard_spec(VALID_DASHBOARD)
        assert r.checks_total == 10


# ---------------------------------------------------------------------------
# Alert Rule Validation (REQ-KZ-OBS-101)
# ---------------------------------------------------------------------------

VALID_ALERT = textwrap.dedent("""\
    groups:
    - name: cartservice.slo
      rules:
      - alert: CartserviceLatencyP99High
        expr: histogram_quantile(0.99, rate(rpc_server_duration_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: critical
          service: cartservice
          protocol: grpc
        annotations:
          summary: cartservice p99 latency exceeds 500ms
""")


class TestAlertValidation:

    def test_valid_alert(self):
        r = validate_alert_rules(VALID_ALERT, service_id="cartservice")
        assert r.yaml_valid
        assert r.rule_count == 1
        assert r.severity_labels_present
        assert r.summary_annotations_present
        assert r.checks_passed >= 8

    def test_invalid_yaml(self):
        r = validate_alert_rules("{{bad", service_id="test")
        assert not r.yaml_valid
        assert r.checks_passed == 0

    def test_no_rules(self):
        r = validate_alert_rules("groups:\n- name: empty\n  rules: []\n")
        assert any(i["check"] == "OBS-101b" for i in r.issues)

    def test_missing_severity(self):
        content = textwrap.dedent("""\
            groups:
            - name: test
              rules:
              - alert: TestAlert
                expr: up == 0
                for: 5m
                labels:
                  service: test
                annotations:
                  summary: test alert
        """)
        r = validate_alert_rules(content)
        assert not r.severity_labels_present
        assert any(i["check"] == "OBS-101f" for i in r.issues)

    def test_missing_summary(self):
        content = textwrap.dedent("""\
            groups:
            - name: test
              rules:
              - alert: TestAlert
                expr: up == 0
                for: 5m
                labels:
                  severity: warning
                  service: test
        """)
        r = validate_alert_rules(content)
        assert not r.summary_annotations_present

    def test_checks_total_is_9(self):
        r = validate_alert_rules(VALID_ALERT)
        assert r.checks_total == 9


# ---------------------------------------------------------------------------
# SLO Definition Validation (REQ-KZ-OBS-102)
# ---------------------------------------------------------------------------

VALID_SLO = textwrap.dedent("""\
    apiVersion: openslo/v1
    kind: SLO
    metadata:
      name: cartservice-latency-p99
      labels:
        service: cartservice
        generated_by: startd8
    spec:
      description: P99 latency SLO
      target: 99.9
      timeWindow:
        duration: 30d
        isRolling: true
      budgetPolicy: timeslices
      indicator:
        metadata:
          name: cartservice-latency-sli
        spec:
          thresholdMetric:
            metricSource:
              type: prometheus
              spec:
                query: histogram_quantile(0.99, rate(rpc_server_duration_bucket[5m]))
            threshold: 0.5
            operator: lte
      alerting:
        name: cartservice-latency-alert
        labels:
          severity: critical
""")


class TestSloValidation:

    def test_valid_slo(self):
        r = validate_slo_definition(VALID_SLO, service_id="cartservice")
        assert r.yaml_valid
        assert r.target_value == 99.9
        assert r.window_duration == "30d"
        assert r.has_indicator
        assert r.has_alerting
        assert r.checks_passed == 10

    def test_invalid_yaml(self):
        r = validate_slo_definition("{{bad", service_id="test")
        assert not r.yaml_valid
        assert r.checks_passed == 0

    def test_wrong_api_version(self):
        content = VALID_SLO.replace("openslo/v1", "openslo/v2")
        r = validate_slo_definition(content)
        assert any(i["check"] == "OBS-102b" for i in r.issues)

    def test_missing_target(self):
        content = VALID_SLO.replace("target: 99.9", "# target removed")
        r = validate_slo_definition(content)
        assert r.target_value is None
        assert any(i["check"] == "OBS-102d" for i in r.issues)

    def test_missing_time_window(self):
        content = VALID_SLO.replace("duration: 30d", "# removed")
        r = validate_slo_definition(content)
        assert any(i["check"] == "OBS-102e" for i in r.issues)

    def test_missing_alerting_is_info(self):
        # Remove alerting block entirely
        lines = VALID_SLO.splitlines()
        filtered = [l for l in lines if "alerting" not in l and "latency-alert" not in l and "severity: critical" not in l]
        content = "\n".join(filtered)
        r = validate_slo_definition(content)
        alert_issues = [i for i in r.issues if i["check"] == "OBS-102i"]
        assert len(alert_issues) == 1
        assert alert_issues[0]["severity"] == "info"

    def test_missing_query(self):
        # Replace query value with empty string
        content = VALID_SLO.replace(
            "query: histogram_quantile(0.99, rate(rpc_server_duration_bucket[5m]))",
            "query: \"\"",
        )
        r = validate_slo_definition(content)
        assert any(i["check"] == "OBS-102j" for i in r.issues)

    def test_ratio_metric_slo(self):
        content = textwrap.dedent("""\
            apiVersion: openslo/v1
            kind: SLO
            metadata:
              name: test-availability
              labels:
                service: test
            spec:
              target: 99.9
              timeWindow:
                duration: 30d
                isRolling: true
              budgetPolicy: occurrences
              indicator:
                metadata:
                  name: test-sli
                spec:
                  ratioMetric:
                    counter:
                      metricSource:
                        type: prometheus
                        spec:
                          query: rate(requests_total[5m])
                    good:
                      metricSource:
                        type: prometheus
                        spec:
                          query: rate(requests_total{status!~"5.."}[5m])
              alerting:
                name: test-alert
                labels:
                  severity: warning
        """)
        r = validate_slo_definition(content)
        assert r.yaml_valid
        assert r.has_indicator
        assert r.checks_passed == 10  # ratio metric query found

    def test_checks_total_is_10(self):
        r = validate_slo_definition(VALID_SLO)
        assert r.checks_total == 10


# ---------------------------------------------------------------------------
# Integration: validate run-093 artifacts
# ---------------------------------------------------------------------------

class TestRunArtifactValidation:
    """Validate against actual generated artifacts if available."""

    @pytest.fixture
    def run_093_obs_dir(self):
        from pathlib import Path
        d = Path("/Users/neilyashinsky/Documents/dev/online-boutique-demo/"
                 ".cap-dev-pipe/pipeline-output/online-boutique/"
                 "run-093-20260321T1726/observability")
        if not d.is_dir():
            pytest.skip("run-093 artifacts not available")
        return d

    def test_cartservice_dashboard(self, run_093_obs_dir):
        content = (run_093_obs_dir / "dashboards" / "cartservice-dashboard-spec.yaml").read_text()
        r = validate_dashboard_spec(content, service_id="cartservice")
        assert r.yaml_valid
        assert r.panel_count >= 3
        assert r.has_title
        assert r.has_uid

    def test_cartservice_alert(self, run_093_obs_dir):
        content = (run_093_obs_dir / "alerts" / "cartservice-alerts.yaml").read_text()
        r = validate_alert_rules(content, service_id="cartservice")
        assert r.yaml_valid
        assert r.rule_count >= 1
        assert r.severity_labels_present

    def test_cartservice_slo(self, run_093_obs_dir):
        content = (run_093_obs_dir / "slos" / "cartservice-slo.yaml").read_text()
        r = validate_slo_definition(content, service_id="cartservice")
        assert r.yaml_valid
        assert r.has_indicator


# ---------------------------------------------------------------------------
# Metric Name Validity (REQ-KZ-OBS-203)
# ---------------------------------------------------------------------------

class TestMetricNameChecks:

    def test_valid_grpc_metric(self):
        expr = 'histogram_quantile(0.99, rate(rpc_server_duration_bucket{service="x"}[5m]))'
        issues = check_metric_names(expr, transport="grpc")
        assert len(issues) == 0

    def test_transport_mismatch_grpc_gets_http(self):
        expr = 'rate(http_server_duration_bucket{service="x"}[5m])'
        issues = check_metric_names(expr, transport="grpc")
        assert any(i["check"] == "OBS-203b" for i in issues)

    def test_transport_mismatch_http_gets_grpc(self):
        expr = 'rate(rpc_server_duration_bucket{service="x"}[5m])'
        issues = check_metric_names(expr, transport="http")
        assert any(i["check"] == "OBS-203b" for i in issues)

    def test_histogram_quantile_without_bucket(self):
        expr = 'histogram_quantile(0.99, rate(rpc_server_duration_count{service="x"}[5m]))'
        issues = check_metric_names(expr, transport="grpc")
        assert any(i["check"] == "OBS-203c" for i in issues)

    def test_no_transport_skips_alignment(self):
        expr = 'rate(rpc_server_duration_bucket{service="x"}[5m])'
        issues = check_metric_names(expr)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Quality Scoring (REQ-KZ-OBS-300–303)
# ---------------------------------------------------------------------------

class TestQualityScoring:

    def test_score_valid_dashboard(self):
        r = validate_dashboard_spec(VALID_DASHBOARD)
        score = score_artifact(r)
        assert 0.7 <= score <= 1.0  # gridPos warning reduces from perfect

    def test_score_invalid_yaml(self):
        r = validate_dashboard_spec("{{bad")
        assert score_artifact(r) == 0.0

    def test_score_perfect_slo(self):
        r = validate_slo_definition(VALID_SLO)
        assert score_artifact(r) == 1.0

    def test_service_triplet_composite(self):
        d = validate_dashboard_spec(VALID_DASHBOARD)
        a = validate_alert_rules(VALID_ALERT)
        s = validate_slo_definition(VALID_SLO)
        triplet = score_service_triplet(
            dashboard=d, alert=a, slo=s, service_id="test",
        )
        assert triplet.has_dashboard
        assert triplet.has_alert
        assert triplet.has_slo
        assert triplet.composite_score > 0.5

    def test_missing_artifact_scores_zero(self):
        a = validate_alert_rules(VALID_ALERT)
        triplet = score_service_triplet(alert=a, service_id="test")
        assert not triplet.has_dashboard
        assert triplet.dashboard_score == 0.0
        assert triplet.composite_score < triplet.alert_score


# ---------------------------------------------------------------------------
# Cross-Artifact Consistency (REQ-KZ-OBS-400–403)
# ---------------------------------------------------------------------------

class TestCrossArtifactConsistency:

    def test_unvisualized_alert_metric(self):
        dashboard = "panels:\n- expr: rate(rpc_server_duration_bucket[5m])\n"
        alert = "expr: rate(rpc_server_errors_total[5m]) > 0.01\n"
        r = check_cross_artifact_consistency(
            dashboard_content=dashboard, alert_content=alert,
        )
        assert "rpc_server_errors_total" in r.unvisualized_alerts

    def test_aligned_metrics_no_issues(self):
        content = "expr: rate(rpc_server_duration_bucket[5m])\n"
        r = check_cross_artifact_consistency(
            dashboard_content=content, alert_content=content,
        )
        assert len(r.unvisualized_alerts) == 0

    def test_unalerted_slo(self):
        alert = "expr: rate(rpc_server_duration_bucket[5m]) > 0.5\n"
        slo = "query: rate(rpc_server_errors_total[5m])\n"
        r = check_cross_artifact_consistency(
            alert_content=alert, slo_content=slo,
        )
        assert "rpc_server_errors_total" in r.unalerted_slos

    def test_threshold_mismatch(self):
        dashboard = "expr: histogram_quantile(0.99, rate(x[5m])) > 0.5\n"
        slo = "threshold: 0.3\n"
        r = check_cross_artifact_consistency(
            dashboard_content=dashboard, slo_content=slo,
        )
        assert len(r.misaligned_thresholds) > 0

    def test_threshold_alignment_no_issue(self):
        dashboard = "expr: x > 0.5\n"
        slo = "threshold: 0.5\n"
        r = check_cross_artifact_consistency(
            dashboard_content=dashboard, slo_content=slo,
        )
        assert len(r.misaligned_thresholds) == 0

    def test_unused_derivation(self):
        derivations = [{"field": "latency_p99", "transformation": "500ms"}]
        r = check_cross_artifact_consistency(
            dashboard_content="expr: up\n",
            manifest_derivations=derivations,
        )
        assert "latency_p99" in r.unused_derivations

    def test_consumed_derivation(self):
        derivations = [{"field": "latency_p99", "transformation": "0.5"}]
        r = check_cross_artifact_consistency(
            dashboard_content="expr: x > 0.5\n",
            manifest_derivations=derivations,
        )
        assert "latency_p99" not in r.unused_derivations

    def test_total_issues_property(self):
        r = CrossArtifactResult(
            unvisualized_alerts=["a"],
            unalerted_slos=["b", "c"],
            unused_derivations=["d"],
        )
        assert r.total_issues == 4


# ---------------------------------------------------------------------------
# Postmortem Integration (REQ-KZ-OBS-500–502)
# ---------------------------------------------------------------------------

class TestPostmortemResult:

    def test_to_dict(self):
        r = ObservabilityPostmortemResult(
            services_evaluated=2,
            avg_dashboard_score=0.8,
            avg_alert_score=0.9,
            avg_slo_score=1.0,
            avg_composite_score=0.89,
            cross_artifact_issues={"unvisualized_alerts": 1},
        )
        d = r.to_dict()
        assert d["services_evaluated"] == 2
        assert d["avg_composite_score"] == 0.89
        assert d["cross_artifact_issues"]["unvisualized_alerts"] == 1

    def test_to_summary_md(self):
        r = ObservabilityPostmortemResult(
            services_evaluated=3,
            phantom_services_detected=1,
            avg_dashboard_score=0.72,
            avg_alert_score=0.85,
            avg_slo_score=0.90,
            cross_artifact_issues={"unvisualized_alerts": 2, "unalerted_slos": 1},
        )
        md = r.to_summary_md()
        assert "## Observability Artifacts" in md
        assert "3" in md
        assert "1 phantom" in md
        assert "0.72" in md


class TestEvaluateObservabilityArtifacts:

    def test_empty_dir(self, tmp_path):
        r = evaluate_observability_artifacts(str(tmp_path))
        assert r.services_evaluated == 0

    def test_nonexistent_dir(self):
        r = evaluate_observability_artifacts("/nonexistent/path")
        assert r.services_evaluated == 0

    def test_single_service_triplet(self, tmp_path):
        # Create a minimal artifact set
        (tmp_path / "dashboards").mkdir()
        (tmp_path / "alerts").mkdir()
        (tmp_path / "slos").mkdir()

        (tmp_path / "dashboards" / "myservice-dashboard-spec.yaml").write_text(
            VALID_DASHBOARD.replace("cartservice", "myservice"),
        )
        (tmp_path / "alerts" / "myservice-alerts.yaml").write_text(
            VALID_ALERT.replace("cartservice", "myservice"),
        )
        (tmp_path / "slos" / "myservice-slo.yaml").write_text(
            VALID_SLO.replace("cartservice", "myservice"),
        )

        r = evaluate_observability_artifacts(str(tmp_path))
        assert r.services_evaluated == 1
        assert r.services_with_complete_triplet == 1
        assert r.avg_composite_score > 0.5
        assert len(r.per_service) == 1
        assert r.per_service[0]["service_id"] == "myservice"

    def test_multiple_services(self, tmp_path):
        (tmp_path / "dashboards").mkdir()
        (tmp_path / "alerts").mkdir()

        for svc in ("svc1", "svc2"):
            (tmp_path / "dashboards" / f"{svc}-dashboard-spec.yaml").write_text(
                VALID_DASHBOARD.replace("cartservice", svc),
            )
            (tmp_path / "alerts" / f"{svc}-alerts.yaml").write_text(
                VALID_ALERT.replace("cartservice", svc),
            )

        r = evaluate_observability_artifacts(str(tmp_path))
        assert r.services_evaluated == 2
        assert r.services_with_complete_triplet == 0  # no SLOs
        assert len(r.per_service) == 2

    def test_run_093_integration(self):
        """Evaluate actual run-093 artifacts."""
        from pathlib import Path
        obs_dir = Path(
            "/Users/neilyashinsky/Documents/dev/online-boutique-demo/"
            ".cap-dev-pipe/pipeline-output/online-boutique/"
            "run-093-20260321T1726/observability"
        )
        if not obs_dir.is_dir():
            pytest.skip("run-093 artifacts not available")

        r = evaluate_observability_artifacts(str(obs_dir))
        assert r.services_evaluated >= 2
        assert r.avg_composite_score > 0
        assert len(r.per_service) >= 2
        # Should have cross-artifact issues (latency-only dashboards)
        assert sum(r.cross_artifact_issues.values()) >= 0


# ---------------------------------------------------------------------------
# Derivation Completeness (REQ-KZ-OBS-403) — integration tests with real data
# ---------------------------------------------------------------------------


class TestDerivationCompletenessIntegration:
    """Tests for validate_derivation_completeness with production-like data."""

    def test_all_rules_consumed(self):
        """All derivation rules trace to values in artifacts."""
        from startd8.validators.observability_artifact_checks import (
            validate_derivation_completeness,
        )
        rules = [
            {
                "field": "alert_severity",
                "source": "manifest.spec.business.criticality",
                "transformation": "high → critical",
                "tier": "manifest",
                "applied_to": ["cartservice"],
            },
            {
                "field": "latency_p99",
                "source": "manifest.spec.requirements.latency_p99",
                "transformation": "500ms",
                "tier": "manifest",
                "applied_to": ["cartservice"],
            },
            {
                "field": "availability",
                "source": "manifest.spec.requirements.availability",
                "transformation": "99.9",
                "tier": "manifest",
                "applied_to": ["cartservice"],
            },
            {
                "field": "slo_window",
                "source": "manifest.strategy.objectives[].keyResults[].window",
                "transformation": "30d",
                "tier": "default",
                "applied_to": ["cartservice"],
            },
            {
                "field": "dashboard_placement",
                "source": "manifest.spec.observability.dashboardPlacement",
                "transformation": "standard",
                "tier": "manifest",
                "applied_to": ["cartservice"],
            },
        ]
        artifacts = [
            {
                "artifact_type": "alert_rule",
                "service_id": "cartservice",
                "content": VALID_ALERT,
            },
            {
                "artifact_type": "dashboard_spec",
                "service_id": "cartservice",
                "content": VALID_DASHBOARD,
            },
            {
                "artifact_type": "slo_definition",
                "service_id": "cartservice",
                "content": VALID_SLO,
            },
        ]
        unused, incorrect = validate_derivation_completeness(rules, artifacts)
        assert unused == [], f"Expected no unused derivations, got: {unused}"
        assert incorrect == [], f"Expected no incorrect consumptions, got: {incorrect}"

    def test_unused_rule_detected(self):
        """A derivation rule not consumed by any artifact is flagged."""
        from startd8.validators.observability_artifact_checks import (
            validate_derivation_completeness,
        )
        rules = [
            {
                "field": "custom_threshold",
                "source": "manifest.spec.requirements.custom",
                "transformation": "42ms",
                "tier": "manifest",
                "applied_to": ["cartservice"],
            },
        ]
        artifacts = [
            {
                "artifact_type": "alert_rule",
                "service_id": "cartservice",
                "content": VALID_ALERT,
            },
        ]
        unused, incorrect = validate_derivation_completeness(rules, artifacts)
        assert len(unused) == 1
        assert "custom_threshold" in unused[0]

    def test_incorrect_severity_detected(self):
        """A severity derivation consumed with wrong value is flagged."""
        from startd8.validators.observability_artifact_checks import (
            validate_derivation_completeness,
        )
        rules = [
            {
                "field": "alert_severity",
                "source": "manifest.spec.business.criticality",
                "transformation": "high → warning",  # expects "warning"
                "tier": "manifest",
                "applied_to": ["cartservice"],
            },
        ]
        # VALID_ALERT has severity: critical, but rule says "warning"
        artifacts = [
            {
                "artifact_type": "alert_rule",
                "service_id": "cartservice",
                "content": VALID_ALERT,
            },
        ]
        unused, incorrect = validate_derivation_completeness(rules, artifacts)
        assert len(incorrect) == 1
        assert "warning" in incorrect[0]
        assert "critical" in incorrect[0]

    def test_service_scoping(self):
        """Rules scoped to service A don't check service B artifacts."""
        from startd8.validators.observability_artifact_checks import (
            validate_derivation_completeness,
        )
        rules = [
            {
                "field": "latency_p99",
                "source": "manifest",
                "transformation": "500ms",
                "tier": "manifest",
                "applied_to": ["emailservice"],  # NOT cartservice
            },
        ]
        # Artifact is for cartservice — rule shouldn't match
        artifacts = [
            {
                "artifact_type": "alert_rule",
                "service_id": "cartservice",
                "content": VALID_ALERT,
            },
        ]
        unused, _ = validate_derivation_completeness(rules, artifacts)
        assert len(unused) == 1, "Rule scoped to emailservice should be unused for cartservice"

    def test_empty_inputs(self):
        """No rules or artifacts produces no findings."""
        from startd8.validators.observability_artifact_checks import (
            validate_derivation_completeness,
        )
        unused, incorrect = validate_derivation_completeness([], [])
        assert unused == []
        assert incorrect == []


# ---------------------------------------------------------------------------
# Gap 3 / Closure 2: semantic metric-coverage
# ---------------------------------------------------------------------------

# The thirteen metrics the pipeline discovered for strtd8 (3 convention + 10 declared).
STRTD8_EXPECTED = [
    "http.server.duration",
    "http.server.request.body.size",
    "http.server.response.body.size",
    "startd8_tokens_total",
    "startd8_cost_total",
    "startd8_active_sessions",
    "startd8_context_usage_ratio",
    "startd8_truncations_total",
    "startd8_requests_total",
    "startd8_response_time_ms",
    "contextcore_task_progress",
    "contextcore_task_status",
    "contextcore_install_completeness_percent",
]


class TestMetricNameNormalization:
    def test_strips_otel_dots_and_prom_suffixes(self):
        from startd8.validators.observability_artifact_checks import _normalize_metric_name

        assert _normalize_metric_name("http.server.duration") == "http_server_duration"
        assert _normalize_metric_name("http_server_duration_bucket") == "http_server_duration"
        assert _normalize_metric_name("startd8_cost_total") == "startd8_cost"
        assert _normalize_metric_name("foo_count") == "foo"
        assert _normalize_metric_name("plain_gauge") == "plain_gauge"


class TestExtractReferencedMetrics:
    def test_excludes_comment_lines(self):
        from startd8.validators.observability_artifact_checks import extract_referenced_metrics

        content = (
            "panels:\n"
            '- expr: rate(http_server_duration_count{service="s"}[5m])\n'
            "# TODO: domain-metric alerts\n"
            '#    expr: rate(startd8_cost_total{service="s"}[5m]) > <THRESHOLD>\n'
        )
        referenced = extract_referenced_metrics([content])
        assert "http_server_duration" in referenced
        # The commented-out stub must NOT count as referenced.
        assert "startd8_cost" not in referenced

    def test_handles_none_and_empty(self):
        from startd8.validators.observability_artifact_checks import extract_referenced_metrics

        assert extract_referenced_metrics([None, "", "   "]) == set()


class TestMetricCoverage:
    def test_run003_scenario_low_coverage(self):
        """Old run-003 artifacts reference only the 3 convention metrics → 3/13."""
        from startd8.validators.observability_artifact_checks import compute_metric_coverage

        dashboard = (
            "panels:\n"
            '- expr: histogram_quantile(0.99, rate(http_server_duration_bucket{service="strtd8"}[5m]))\n'
            '- expr: rate(http_server_request_body_size_total{service="strtd8"}[5m])\n'
            '- expr: rate(http_server_response_body_size_total{service="strtd8"}[5m])\n'
        )
        cov = compute_metric_coverage(STRTD8_EXPECTED, [dashboard])
        assert cov.score == round(3 / 13, 4)
        assert len(cov.expected) == 13
        assert len(cov.covered) == 3
        assert "startd8_cost" in cov.uncovered

    def test_full_coverage_when_domain_metrics_present(self):
        from startd8.validators.observability_artifact_checks import compute_metric_coverage

        exprs = []
        for m in STRTD8_EXPECTED:
            prom = m.replace(".", "_")
            if prom.endswith("_total"):
                exprs.append(f'- expr: rate({prom}{{service="strtd8"}}[5m])')
            else:
                exprs.append(f'- expr: {prom}{{service="strtd8"}}')
        content = "panels:\n" + "\n".join(exprs)
        cov = compute_metric_coverage(STRTD8_EXPECTED, [content])
        assert cov.score == 1.0
        assert cov.uncovered == []

    def test_empty_expected_scores_one(self):
        from startd8.validators.observability_artifact_checks import compute_metric_coverage

        cov = compute_metric_coverage([], ["panels: []"])
        assert cov.score == 1.0


class TestCompositeBlend:
    def test_coverage_drags_composite_down(self):
        from startd8.validators.observability_artifact_checks import compute_service_composite

        structural_only = compute_service_composite(0.9167, 1.0, 1.0)
        blended = compute_service_composite(0.9167, 1.0, 1.0, metric_coverage=round(3 / 13, 4))
        assert blended < structural_only
        # Structural ~0.97 must drop appreciably when only 3/13 metrics are covered.
        assert blended < 0.8

    def test_none_coverage_preserves_legacy_behaviour(self):
        from startd8.validators.observability_artifact_checks import compute_service_composite

        assert compute_service_composite(0.9, 0.8, 1.0) == pytest.approx(
            0.9 * 0.35 + 0.8 * 0.35 + 1.0 * 0.30
        )

    def test_full_coverage_barely_moves_composite(self):
        from startd8.validators.observability_artifact_checks import compute_service_composite

        blended = compute_service_composite(1.0, 1.0, 1.0, metric_coverage=1.0)
        assert blended == pytest.approx(1.0)


class TestCoverageGate:
    def test_no_thresholds_always_passes(self):
        from startd8.validators.observability_artifact_checks import evaluate_coverage_gate

        result = evaluate_coverage_gate(metric_coverage=0.1, artifact_type_coverage=0.1)
        assert result.passed
        assert result.failures == []

    def test_metric_coverage_below_minimum_fails(self):
        from startd8.validators.observability_artifact_checks import evaluate_coverage_gate

        result = evaluate_coverage_gate(
            metric_coverage=0.23, min_metric_coverage=0.5
        )
        assert not result.passed
        assert any("metric_coverage" in f for f in result.failures)

    def test_artifact_type_coverage_below_minimum_fails(self):
        from startd8.validators.observability_artifact_checks import evaluate_coverage_gate

        result = evaluate_coverage_gate(
            artifact_type_coverage=0.375, min_artifact_type_coverage=0.5
        )
        assert not result.passed
        assert any("artifact_type_coverage" in f for f in result.failures)

    def test_passes_when_at_or_above_minimum(self):
        from startd8.validators.observability_artifact_checks import evaluate_coverage_gate

        result = evaluate_coverage_gate(
            metric_coverage=0.8,
            artifact_type_coverage=1.0,
            min_metric_coverage=0.8,
            min_artifact_type_coverage=0.5,
        )
        assert result.passed

    def test_missing_score_with_threshold_is_a_failure(self):
        from startd8.validators.observability_artifact_checks import evaluate_coverage_gate

        result = evaluate_coverage_gate(
            metric_coverage=None, min_metric_coverage=0.5
        )
        assert not result.passed
        assert any("unavailable" in f for f in result.failures)
