"""Tests for startd8.observability.artifact_generator."""

import json
import textwrap
from pathlib import Path

import pytest
import yaml

from startd8.observability.artifact_generator import (
    ArtifactResult,
    BusinessContext,
    ConventionMetric,
    GenerationReport,
    ServiceHints,
    _alert_name,
    _error_filter_for_protocol,
    _panel_group,
    _panel_title,
    _parse_availability_to_fraction,
    _parse_duration_to_seconds,
    _prom_name,
    check_drift,
    extract_service_hints,
    generate_alert_rules,
    generate_dashboard_spec,
    generate_observability_artifacts,
    generate_slo_definitions,
    load_business_context,
    load_onboarding_metadata,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GRPC_METRICS = [
    ConventionMetric("rpc.server.duration", "histogram", "otel_semconv:grpc"),
    ConventionMetric("rpc.server.request.size", "counter", "otel_semconv:grpc"),
    ConventionMetric("rpc.server.response.size", "counter", "otel_semconv:grpc"),
    ConventionMetric("rpc.server.requests_per_rpc", "counter", "otel_semconv:grpc"),
]

HTTP_METRICS = [
    ConventionMetric("http.server.duration", "histogram", "otel_semconv:http"),
    ConventionMetric("http.server.request.body.size", "counter", "otel_semconv:http"),
    ConventionMetric("http.server.response.body.size", "counter", "otel_semconv:http"),
]


@pytest.fixture
def grpc_service():
    return ServiceHints(
        service_id="checkout-api",
        transport="grpc",
        language="go",
        detected_databases=["postgresql"],
        convention_metrics=GRPC_METRICS,
    )


@pytest.fixture
def http_service():
    return ServiceHints(
        service_id="frontend",
        transport="http",
        language="python",
        convention_metrics=HTTP_METRICS,
    )


@pytest.fixture
def business():
    return BusinessContext(
        criticality="high",
        availability="99.9",
        latency_p99="500ms",
        throughput="100rps",
        project_id="online-boutique",
        project_name="Online Boutique",
        slo_window="30d",
    )


@pytest.fixture
def business_defaults():
    """BusinessContext with no thresholds — forces defaults."""
    return BusinessContext(criticality="medium", project_id="test-project")


@pytest.fixture
def onboarding_metadata():
    return {
        "project_id": "online-boutique",
        "instrumentation_hints": {
            "checkout-api": {
                "service_id": "checkout-api",
                "transport": "grpc",
                "language": "go",
                "detected_databases": ["postgresql"],
                "metrics": {
                    "convention_based": [
                        {"name": "rpc.server.duration", "type": "histogram", "source": "otel_semconv:grpc"},
                        {"name": "rpc.server.requests_per_rpc", "type": "counter", "source": "otel_semconv:grpc"},
                    ],
                },
            },
            "frontend": {
                "service_id": "frontend",
                "transport": "http",
                "language": "python",
                "metrics": {
                    "convention_based": [
                        {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"},
                    ],
                },
            },
        },
    }


@pytest.fixture
def manifest_yaml(tmp_path):
    content = textwrap.dedent("""\
        apiVersion: contextcore.io/v1alpha2
        kind: ContextManifest
        spec:
          project:
            id: online-boutique
            name: Online Boutique
          business:
            criticality: high
            owner: platform-engineering
          requirements:
            availability: "99.9"
            latencyP99: "200ms"
            throughput: "500rps"
          observability:
            dashboardPlacement: overview
        strategy:
          objectives:
            - id: OBJ-1
              keyResults:
                - metricKey: availability
                  window: "7d"
    """)
    p = tmp_path / ".contextcore.yaml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Phase 1: Input loading tests
# ---------------------------------------------------------------------------


class TestLoadOnboardingMetadata:
    def test_valid(self, tmp_path):
        p = tmp_path / "onboarding-metadata.json"
        p.write_text(json.dumps({"project_id": "test"}))
        result = load_onboarding_metadata(p)
        assert result["project_id"] == "test"

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_onboarding_metadata(tmp_path / "missing.json")


class TestExtractServiceHints:
    def test_happy_path(self, onboarding_metadata):
        services = extract_service_hints(onboarding_metadata)
        assert len(services) == 2
        checkout = [s for s in services if s.service_id == "checkout-api"][0]
        assert checkout.transport == "grpc"
        assert checkout.language == "go"
        assert len(checkout.convention_metrics) == 2

    def test_missing_key(self):
        services = extract_service_hints({})
        assert services == []

    def test_skips_no_transport(self):
        metadata = {
            "instrumentation_hints": {
                "bad-svc": {"service_id": "bad-svc", "metrics": {}},
                "good-svc": {"service_id": "good-svc", "transport": "http", "metrics": {}},
            }
        }
        services = extract_service_hints(metadata)
        assert len(services) == 1
        assert services[0].service_id == "good-svc"


class TestLoadBusinessContext:
    def test_from_manifest(self, manifest_yaml):
        ctx = load_business_context(manifest_yaml, {})
        assert ctx.criticality == "high"
        assert ctx.availability == "99.9"
        assert ctx.latency_p99 == "200ms"
        assert ctx.dashboard_placement == "overview"
        assert ctx.project_id == "online-boutique"
        assert ctx.slo_window == "7d"

    def test_fallback_to_metadata(self):
        ctx = load_business_context(None, {"project_id": "from-metadata"})
        assert ctx.project_id == "from-metadata"
        assert ctx.criticality == "medium"

    def test_all_defaults(self):
        ctx = load_business_context(None, {})
        assert ctx.criticality == "medium"
        assert ctx.availability is None
        assert ctx.slo_window == "30d"


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_duration_ms(self):
        assert _parse_duration_to_seconds("500ms") == 0.5

    def test_parse_duration_s(self):
        assert _parse_duration_to_seconds("2s") == 2.0

    def test_parse_duration_bare(self):
        assert _parse_duration_to_seconds("200") == 0.2

    def test_parse_availability(self):
        assert _parse_availability_to_fraction("99.9") == pytest.approx(0.999)

    def test_parse_availability_high(self):
        assert _parse_availability_to_fraction("99.95") == pytest.approx(0.9995)

    def test_prom_name(self):
        assert _prom_name("rpc.server.duration") == "rpc_server_duration"

    def test_alert_name(self):
        assert _alert_name("checkout-api", "LatencyP99High") == "CheckoutApiLatencyP99High"

    def test_error_filter_grpc(self):
        assert "grpc_code" in _error_filter_for_protocol("grpc")

    def test_error_filter_http(self):
        assert "status" in _error_filter_for_protocol("http")

    def test_panel_title(self):
        assert _panel_title("rpc.server.duration") == "Rpc Server Duration"

    def test_panel_group_latency(self):
        assert _panel_group("rpc.server.duration") == "Latency"

    def test_panel_group_throughput(self):
        assert _panel_group("rpc.server.requests_per_rpc") == "Throughput"

    def test_panel_group_size(self):
        assert _panel_group("rpc.server.request.size") == "Size"


# ---------------------------------------------------------------------------
# Phase 2: Alert rule tests
# ---------------------------------------------------------------------------


class TestGenerateAlertRules:
    def test_grpc_service(self, grpc_service, business):
        result = generate_alert_rules(grpc_service, business)
        assert result.status == "generated"
        assert result.artifact_type == "alert_rule"
        parsed = yaml.safe_load(result.content.split("\n\n", 1)[1])
        rules = parsed["groups"][0]["rules"]
        alert_names = [r["alert"] for r in rules]
        assert "CheckoutApiLatencyP99High" in alert_names
        assert "CheckoutApiAvailabilityLow" in alert_names

    def test_http_service(self, http_service, business):
        result = generate_alert_rules(http_service, business)
        assert result.status == "generated"
        parsed = yaml.safe_load(result.content.split("\n\n", 1)[1])
        rules = parsed["groups"][0]["rules"]
        assert any("duration" in r["expr"] for r in rules)

    def test_criticality_mapping(self, grpc_service, business):
        result = generate_alert_rules(grpc_service, business)
        parsed = yaml.safe_load(result.content.split("\n\n", 1)[1])
        rules = parsed["groups"][0]["rules"]
        for r in rules:
            assert r["labels"]["severity"] == "critical"  # high → critical

    def test_uses_defaults_when_no_slo(self, grpc_service, business_defaults):
        result = generate_alert_rules(grpc_service, business_defaults)
        assert result.status == "generated"
        # Should use default thresholds
        assert any(d.tier == "default" for d in result.derivations)

    def test_derivation_traces(self, grpc_service, business):
        result = generate_alert_rules(grpc_service, business)
        fields = [d.field for d in result.derivations]
        assert "alert_severity" in fields
        assert "latency_p99" in fields

    def test_valid_yaml(self, grpc_service, business):
        result = generate_alert_rules(grpc_service, business)
        # Should parse without error
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        assert "groups" in parsed

    def test_no_alertable_metrics(self, business):
        svc = ServiceHints(service_id="static", transport="http", convention_metrics=[])
        result = generate_alert_rules(svc, business)
        assert result.status == "skipped"


# ---------------------------------------------------------------------------
# Phase 3: Dashboard spec tests
# ---------------------------------------------------------------------------


class TestGenerateDashboardSpec:
    def test_grpc_service(self, grpc_service, business):
        result = generate_dashboard_spec(grpc_service, business)
        assert result.status == "generated"
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        assert parsed["title"] == "checkout-api Observability"
        # GRPC_METRICS panels + synthesized Rate + Error panels
        assert len(parsed["panels"]) >= len(GRPC_METRICS)
        titles = [p["title"] for p in parsed["panels"]]
        assert "Request Rate" in titles
        assert "Error Rate" in titles

    def test_http_service(self, http_service, business):
        result = generate_dashboard_spec(http_service, business)
        assert result.status == "generated"
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        # HTTP_METRICS panels + synthesized Rate + Error panels
        assert len(parsed["panels"]) >= len(HTTP_METRICS)
        titles = [p["title"] for p in parsed["panels"]]
        assert "Request Rate" in titles
        assert "Error Rate" in titles

    def test_panel_types(self, grpc_service, business):
        result = generate_dashboard_spec(grpc_service, business)
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        types = {p["type"] for p in parsed["panels"]}
        assert "histogram" in types  # from duration metric
        assert "timeseries" in types  # from counter metrics

    def test_valid_yaml(self, grpc_service, business):
        result = generate_dashboard_spec(grpc_service, business)
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        assert "panels" in parsed
        assert "datasources" in parsed

    def test_threshold_from_slo(self, grpc_service, business):
        result = generate_dashboard_spec(grpc_service, business)
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        duration_panel = [p for p in parsed["panels"] if "duration" in p.get("title", "").lower()]
        assert len(duration_panel) > 0
        assert "thresholds" in duration_panel[0]

    def test_placement_critical(self, grpc_service):
        biz = BusinessContext(criticality="critical", dashboard_placement="overview")
        result = generate_dashboard_spec(grpc_service, biz)
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        assert "overview" in parsed["tags"]

    def test_no_convention_metrics_still_generates_red(self, business):
        """Services with no convention metrics still get synthesized RED panels."""
        svc = ServiceHints(service_id="empty", transport="http", convention_metrics=[])
        result = generate_dashboard_spec(svc, business)
        # RED panels are synthesized even without convention metrics
        assert result.status == "generated"
        body = result.content.split("\n\n", 1)[1]
        parsed = yaml.safe_load(body)
        titles = [p["title"] for p in parsed["panels"]]
        assert "Request Rate" in titles
        assert "Error Rate" in titles


# ---------------------------------------------------------------------------
# Phase 4: SLO definition tests
# ---------------------------------------------------------------------------


class TestGenerateSloDefinitions:
    def test_generates_both(self, grpc_service, business):
        result = generate_slo_definitions(grpc_service, business)
        assert result.status == "generated"
        docs = result.content.split("---")
        # Should have availability + latency (plus header)
        slo_docs = [d for d in docs if "kind: SLO" in d]
        assert len(slo_docs) == 2

    def test_availability_slo(self, grpc_service, business):
        result = generate_slo_definitions(grpc_service, business)
        body = result.content.split("\n\n", 1)[1]
        first_doc = yaml.safe_load(body.split("---")[0])
        assert first_doc["metadata"]["name"] == "checkout-api-availability"
        assert first_doc["spec"]["target"] == 99.9

    def test_latency_slo(self, grpc_service, business):
        result = generate_slo_definitions(grpc_service, business)
        body = result.content.split("\n\n", 1)[1]
        docs = list(yaml.safe_load_all(body))
        latency_docs = [d for d in docs if d and "latency" in d.get("metadata", {}).get("name", "")]
        assert len(latency_docs) == 1
        assert latency_docs[0]["spec"]["indicator"]["spec"]["thresholdMetric"]["threshold"] == 0.5

    def test_uses_defaults(self, grpc_service, business_defaults):
        result = generate_slo_definitions(grpc_service, business_defaults)
        assert result.status == "generated"
        assert any(d.tier == "default" for d in result.derivations)

    def test_window_from_objectives(self, grpc_service):
        biz = BusinessContext(availability="99.5", slo_window="7d")
        result = generate_slo_definitions(grpc_service, biz)
        body = result.content.split("\n\n", 1)[1]
        first_doc = yaml.safe_load(body.split("---")[0])
        assert first_doc["spec"]["timeWindow"]["duration"] == "7d"

    def test_valid_yaml(self, grpc_service, business):
        result = generate_slo_definitions(grpc_service, business)
        body = result.content.split("\n\n", 1)[1]
        docs = list(yaml.safe_load_all(body))
        assert all(d is not None for d in docs)

    def test_severity_from_criticality(self, grpc_service, business):
        result = generate_slo_definitions(grpc_service, business)
        body = result.content.split("\n\n", 1)[1]
        first_doc = yaml.safe_load(body.split("---")[0])
        assert first_doc["spec"]["alerting"]["labels"]["severity"] == "critical"

    def test_no_eligible_metrics(self, business):
        svc = ServiceHints(service_id="empty", transport="http", convention_metrics=[])
        result = generate_slo_definitions(svc, business)
        assert result.status == "skipped"


# ---------------------------------------------------------------------------
# Phase 5: Orchestration tests
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def test_happy_path(self, tmp_path, onboarding_metadata, manifest_yaml):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(onboarding_metadata))
        output = tmp_path / "observability"

        report = generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
            manifest_path=manifest_yaml,
        )

        assert report.services_processed == 2
        generated = [a for a in report.artifacts if a.status == "generated"]
        assert len(generated) >= 4  # at least alerts + dashboards for 2 services

        # Verify files exist
        assert (output / "observability-manifest.yaml").exists()
        assert (output / "alerts").exists()
        assert (output / "dashboards").exists()

    def test_no_services(self, tmp_path):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps({"project_id": "empty"}))
        output = tmp_path / "observability"

        report = generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
        )
        assert report.services_processed == 0
        assert len(report.artifacts) == 0

    def test_dry_run(self, tmp_path, onboarding_metadata):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(onboarding_metadata))
        output = tmp_path / "observability"

        report = generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
            dry_run=True,
        )

        assert report.services_processed == 2
        assert not output.exists()  # nothing written

    def test_partial_failure(self, tmp_path):
        """One service with bad data shouldn't block others."""
        metadata = {
            "instrumentation_hints": {
                "good-svc": {
                    "transport": "http",
                    "metrics": {
                        "convention_based": [
                            {"name": "http.server.duration", "type": "histogram", "source": "x"},
                        ],
                    },
                },
            },
        }
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(metadata))
        output = tmp_path / "observability"

        report = generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
        )
        assert report.services_processed == 1
        generated = [a for a in report.artifacts if a.status == "generated"]
        assert len(generated) >= 1

    def test_index_file_structure(self, tmp_path, onboarding_metadata, manifest_yaml):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(onboarding_metadata))
        output = tmp_path / "observability"

        generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
            manifest_path=manifest_yaml,
        )

        index = yaml.safe_load((output / "observability-manifest.yaml").read_text())
        assert index["manifest_id"] == "observability-artifacts"
        assert "summary" in index
        assert "artifacts" in index
        assert "derivation_rules" in index
        assert index["summary"]["services_processed"] == 2


# ---------------------------------------------------------------------------
# Phase 6: Drift detection tests
# ---------------------------------------------------------------------------


class TestDriftDetection:
    def test_no_drift(self, tmp_path, onboarding_metadata, manifest_yaml):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(onboarding_metadata))
        output = tmp_path / "observability"

        # Generate first
        generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
            manifest_path=manifest_yaml,
        )

        # Check drift (same inputs) → should be 0
        result = check_drift(meta_path, output, manifest_yaml)
        assert result == 0

    def test_drift_ignores_toolchain_dependent_dashboard(
        self, tmp_path, onboarding_metadata, manifest_yaml, monkeypatch
    ):
        """Drift must not flip when the derived Grafana JSON is absent because the
        jsonnet toolchain happened to be unavailable on the drift-check run."""
        import startd8.observability.artifact_generator as gen

        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(onboarding_metadata))
        output = tmp_path / "observability"

        # First generation: dashboard JSON produced and recorded in the index.
        gen.generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
            manifest_path=manifest_yaml,
        )

        # Simulate the toolchain being unavailable on the drift-check run.
        monkeypatch.setattr(
            gen, "_convert_dashboards_to_grafana_json", lambda *a, **k: None
        )
        assert gen.check_drift(meta_path, output, manifest_yaml) == 0

    def test_new_service_detected(self, tmp_path, onboarding_metadata, manifest_yaml):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(onboarding_metadata))
        output = tmp_path / "observability"

        # Generate with 2 services
        generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
            manifest_path=manifest_yaml,
        )

        # Add a third service
        onboarding_metadata["instrumentation_hints"]["new-svc"] = {
            "transport": "http",
            "metrics": {
                "convention_based": [
                    {"name": "http.server.duration", "type": "histogram", "source": "x"},
                ],
            },
        }
        meta_path.write_text(json.dumps(onboarding_metadata))

        result = check_drift(meta_path, output, manifest_yaml)
        assert result == 1  # drift detected

    def test_no_existing_index(self, tmp_path, onboarding_metadata):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(onboarding_metadata))
        output = tmp_path / "observability"

        result = check_drift(meta_path, output)
        assert result == 1  # no index = drift


# ---------------------------------------------------------------------------
# Phase 7: Provenance tests
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_append_to_provenance(self, tmp_path):
        from startd8.observability.artifact_generator import _append_to_provenance

        prov_path = tmp_path / "run-provenance.json"
        prov_path.write_text(json.dumps({"artifact_inventory": []}))
        output = tmp_path / "observability"

        _append_to_provenance(prov_path, output)

        result = json.loads(prov_path.read_text())
        assert len(result["artifact_inventory"]) == 1
        assert result["artifact_inventory"][0]["stage"] == "4.5"

    def test_missing_provenance(self, tmp_path):
        from startd8.observability.artifact_generator import _append_to_provenance

        # Should not raise
        _append_to_provenance(tmp_path / "missing.json", tmp_path / "obs")


# ---------------------------------------------------------------------------
# Closure 1 / Gap 1: manifest_declared domain metrics
# ---------------------------------------------------------------------------

# The ten domain metrics the pipeline discovered for strtd8 (gap analysis §1.1).
STRTD8_DECLARED = [
    {"name": "startd8_tokens_total", "type": "counter", "source": "manifest"},
    {"name": "startd8_cost_total", "type": "counter", "source": "manifest"},
    {"name": "startd8_active_sessions", "type": "gauge", "source": "manifest"},
    {"name": "startd8_context_usage_ratio", "type": "gauge", "source": "manifest"},
    {"name": "startd8_truncations_total", "type": "counter", "source": "manifest"},
    {"name": "startd8_requests_total", "type": "counter", "source": "manifest"},
    {"name": "startd8_response_time_ms", "type": "gauge", "source": "manifest"},
    {"name": "contextcore_task_progress", "type": "gauge", "source": "manifest"},
    {"name": "contextcore_task_status", "type": "gauge", "source": "manifest"},
    {"name": "contextcore_install_completeness_percent", "type": "gauge", "source": "manifest"},
]


@pytest.fixture
def strtd8_service():
    return ServiceHints(
        service_id="strtd8",
        transport="http",
        language="python",
        convention_metrics=HTTP_METRICS,
        declared_metrics=[
            ConventionMetric(m["name"], m["type"], m["source"]) for m in STRTD8_DECLARED
        ],
    )


class TestDeclaredMetricExtraction:
    def test_extract_populates_declared_metrics(self):
        metadata = {
            "project_id": "startd8/run-003-20260528t2314",
            "instrumentation_hints": {
                "strtd8": {
                    "service_id": "strtd8",
                    "transport": "http",
                    "metrics": {
                        "convention_based": [
                            {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"},
                        ],
                        "manifest_declared": STRTD8_DECLARED,
                    },
                },
            },
        }
        services = extract_service_hints(metadata)
        assert len(services) == 1
        svc = services[0]
        assert len(svc.convention_metrics) == 1
        assert len(svc.declared_metrics) == 10
        names = {m.name for m in svc.declared_metrics}
        assert "startd8_cost_total" in names
        assert "startd8_tokens_total" in names

    def test_missing_manifest_declared_is_empty(self):
        metadata = {
            "instrumentation_hints": {
                "svc": {
                    "transport": "http",
                    "metrics": {"convention_based": []},
                },
            },
        }
        services = extract_service_hints(metadata)
        assert services[0].declared_metrics == []


class TestDomainMetricHelpers:
    def test_panel_group_intent(self):
        from startd8.observability.artifact_generator import _domain_panel_group

        assert _domain_panel_group("startd8_cost_total") == "Cost & Tokens"
        assert _domain_panel_group("startd8_tokens_total") == "Cost & Tokens"
        assert _domain_panel_group("startd8_active_sessions") == "Sessions"
        assert _domain_panel_group("startd8_truncations_total") == "Health"
        assert _domain_panel_group("startd8_context_usage_ratio") == "Health"
        assert _domain_panel_group("contextcore_task_progress") == "Progress"
        assert _domain_panel_group("something_else") == "Domain Metrics"

    def test_metric_type_inference_from_name(self):
        from startd8.observability.artifact_generator import _domain_metric_type

        assert _domain_metric_type(ConventionMetric("x_total", "", "")) == "counter"
        assert _domain_metric_type(ConventionMetric("x_ratio", "", "")) == "gauge"
        # explicit type wins over name inference
        assert _domain_metric_type(ConventionMetric("x_total", "gauge", "")) == "gauge"

    def test_query_counter_vs_gauge(self):
        from startd8.observability.artifact_generator import _domain_query

        counter = ConventionMetric("startd8_cost_total", "counter", "manifest")
        gauge = ConventionMetric("startd8_active_sessions", "gauge", "manifest")
        assert _domain_query(counter, "strtd8") == (
            'rate(startd8_cost_total{service="strtd8"}[$__rate_interval])'
        )
        # already-_total names are not double-suffixed
        assert "_total_total" not in _domain_query(counter, "strtd8")
        assert _domain_query(gauge, "strtd8") == 'startd8_active_sessions{service="strtd8"}'


class TestDomainDashboardPanels:
    def test_dashboard_contains_cost_and_token_panels(self, strtd8_service, business):
        """Gap-analysis acceptance test: dashboard must surface domain metrics."""
        result = generate_dashboard_spec(strtd8_service, business)
        assert result.status == "generated"
        assert "startd8_cost_total" in result.content
        assert "startd8_tokens_total" in result.content

        spec = yaml.safe_load(result.content)
        groups = {p.get("group") for p in spec["panels"]}
        assert "Cost & Tokens" in groups
        assert "Sessions" in groups

    def test_ratio_metric_uses_percentunit_gauge(self, strtd8_service, business):
        spec = yaml.safe_load(generate_dashboard_spec(strtd8_service, business).content)
        ratio_panels = [
            p for p in spec["panels"]
            if "startd8_context_usage_ratio" in str(p.get("expr", ""))
        ]
        assert ratio_panels
        assert ratio_panels[0]["type"] == "gauge"
        assert ratio_panels[0]["unit"] == "percentunit"

    def test_no_declared_metrics_leaves_baseline_unchanged(self, http_service, business):
        """A service with no declared metrics gets only convention panels."""
        spec = yaml.safe_load(generate_dashboard_spec(http_service, business).content)
        for p in spec["panels"]:
            assert "startd8_" not in str(p.get("expr", ""))

    def test_domain_panel_derivation_recorded(self, strtd8_service, business):
        result = generate_dashboard_spec(strtd8_service, business)
        fields = {d.field for d in result.derivations}
        assert "domain_panels" in fields


class TestDomainAlertTodos:
    def test_alerts_contain_commented_todo_block(self, strtd8_service, business):
        result = generate_alert_rules(strtd8_service, business)
        assert result.status == "generated"
        assert "TODO: domain-metric alerts" in result.content
        assert "startd8_cost_total" in result.content
        assert "<THRESHOLD>" in result.content

    def test_todo_stubs_are_not_active_rules(self, strtd8_service, business):
        """Declared-metric alerts are commented out, not parsed as active rules."""
        result = generate_alert_rules(strtd8_service, business)
        # Strip the trailing commented TODO block before parsing YAML.
        active = "\n".join(
            ln for ln in result.content.splitlines() if not ln.lstrip().startswith("#")
        )
        parsed = yaml.safe_load(active)
        rule_names = [
            r["alert"] for g in parsed["groups"] for r in g["rules"]
        ]
        # No active rule references a domain metric.
        assert not any("Cost" in n or "Token" in n for n in rule_names)

    def test_declared_only_service_still_emits_file(self, business):
        """A service with declared metrics but no alertable convention metrics
        still produces an alerts file (with the TODO block), not a skip."""
        svc = ServiceHints(
            service_id="domain-only",
            transport="http",
            convention_metrics=[],
            declared_metrics=[ConventionMetric("startd8_cost_total", "counter", "manifest")],
        )
        result = generate_alert_rules(svc, business)
        assert result.status == "generated"
        assert "TODO: domain-metric alerts" in result.content

    def test_no_declared_metrics_no_todo_block(self, http_service, business):
        result = generate_alert_rules(http_service, business)
        assert "TODO: domain-metric alerts" not in result.content


class TestMetricCoverageInQualityReport:
    """Gap 3 / Closure 2: quality report surfaces semantic metric-coverage."""

    def _metadata_with_declared(self):
        return {
            "project_id": "startd8/run-003-20260528t2314",
            "instrumentation_hints": {
                "strtd8": {
                    "service_id": "strtd8",
                    "transport": "http",
                    "language": "python",
                    "metrics": {
                        "convention_based": [
                            {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"},
                        ],
                        "manifest_declared": STRTD8_DECLARED,
                    },
                },
            },
        }

    def test_quality_report_has_metric_coverage(self, tmp_path, manifest_yaml):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(self._metadata_with_declared()))
        output = tmp_path / "observability"

        generate_observability_artifacts(
            onboarding_metadata_path=meta_path,
            output_dir=output,
            manifest_path=manifest_yaml,
        )

        quality = json.loads((output / "observability-quality.json").read_text())
        svc = quality["services"]["strtd8"]
        assert "metric_coverage" in svc
        assert svc["metric_coverage"]["expected_count"] == 11  # 1 convention + 10 declared
        # Increment 1 adds domain panels, so most declared metrics are now covered.
        assert svc["metric_coverage"]["score"] > 0.5
        assert "avg_metric_coverage_score" in quality["aggregate"]


# ---------------------------------------------------------------------------
# Increment 3: RED completeness (gridPos, runbook_url, DB latency)
# ---------------------------------------------------------------------------


class TestGridPos:
    """REQ-OAG-105 / Gap 5: panels ship with gridPos at generation time."""

    def test_every_panel_has_gridpos(self, grpc_service, business):
        spec = yaml.safe_load(generate_dashboard_spec(grpc_service, business).content)
        assert spec["panels"]
        for p in spec["panels"]:
            assert "gridPos" in p
            assert set(p["gridPos"]) == {"h", "w", "x", "y"}

    def test_two_column_layout(self, grpc_service, business):
        spec = yaml.safe_load(generate_dashboard_spec(grpc_service, business).content)
        xs = {p["gridPos"]["x"] for p in spec["panels"]}
        assert xs <= {0, 12}  # half-width 2-column grid

    def test_obs_100h_not_dinged_and_repair_is_noop(self, grpc_service, business):
        from startd8.validators.observability_artifact_checks import (
            validate_dashboard, repair_gridpos,
        )
        result = generate_dashboard_spec(grpc_service, business)
        vr = validate_dashboard(
            result.content, result.output_path, autofix=True,
            service_id=grpc_service.service_id, transport="grpc",
        )
        assert not any(i.check == "OBS-100h" for i in vr.issues)
        # repair_gridpos finds nothing to fix on a freshly generated dashboard.
        _, repairs = repair_gridpos(yaml.safe_load(result.content))
        assert repairs == []


class TestRunbookUrl:
    """REQ-OAG-205: every active alert carries a runbook_url annotation."""

    def test_all_alerts_have_runbook_url(self, grpc_service, business):
        result = generate_alert_rules(grpc_service, business)
        parsed = yaml.safe_load(result.content)
        rules = [r for g in parsed["groups"] for r in g["rules"]]
        assert rules
        for r in rules:
            url = r["annotations"]["runbook_url"]
            assert url.startswith("https://runbooks.example.com/checkout-api/")
            assert r["alert"] in url


class TestDatabasePanels:
    """REQ-OAG-107: DB latency panels appear only when databases are detected."""

    def test_db_panel_present_when_database_detected(self, grpc_service, business):
        # grpc_service fixture has detected_databases=["postgresql"]
        spec = yaml.safe_load(generate_dashboard_spec(grpc_service, business).content)
        db_panels = [p for p in spec["panels"] if p.get("group") == "Database"]
        assert len(db_panels) == 1
        assert "db_client_operation_duration_bucket" in db_panels[0]["expr"]
        assert 'db_system="postgresql"' in db_panels[0]["expr"]

    def test_no_db_panel_without_databases(self, http_service, business):
        # http_service fixture has no detected_databases
        spec = yaml.safe_load(generate_dashboard_spec(http_service, business).content)
        assert not any(p.get("group") == "Database" for p in spec["panels"])


# ---------------------------------------------------------------------------
# A' / Gap 4: dashboard spec -> deployable Grafana JSON via DashboardCreatorWorkflow
# ---------------------------------------------------------------------------


class _FakeStep:
    def __init__(self, step_name, output):
        self.step_name = step_name
        self.output = output


class _FakeResult:
    def __init__(self, success, error=None, steps=None):
        self.success = success
        self.error = error
        self.steps = steps or []


class _FakeWorkflow:
    """Stand-in for DashboardCreatorWorkflow that avoids the jsonnet toolchain."""

    def __init__(self, *, succeed=True, write=True, raises=False, provision_succeeds=True):
        self._succeed = succeed
        self._write = write
        self._raises = raises
        self._provision_succeeds = provision_succeeds
        self.last_config = None

    def run(self, config):
        self.last_config = config
        if self._raises:
            raise RuntimeError("toolchain exploded")
        if self._succeed and self._write:
            uid = config["spec"]["uid"]
            out = Path(config["output_dir"])
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{uid}.json").write_text(json.dumps({"uid": uid, "panels": []}))
        steps = []
        if config.get("provision"):
            # Mirror the real workflow: provisioning is warn-don't-fail (a push
            # failure still returns success=True with a 'provision' step note).
            if self._provision_succeeds:
                steps.append(_FakeStep("provision", "Provisioned: /d/uid"))
            else:
                steps.append(_FakeStep("provision", "Provisioning failed: boom"))
        return _FakeResult(
            self._succeed, None if self._succeed else "compile failed", steps=steps
        )


def _report_with_dashboard_spec(service_id="strtd8", uid="obs-strtd8"):
    from startd8.observability.artifact_generator import ArtifactResult, GenerationReport

    report = GenerationReport(project_id="p", generated_at="t")
    report.artifacts.append(
        ArtifactResult(
            artifact_type="dashboard_spec",
            service_id=service_id,
            output_path=f"dashboards/{service_id}-dashboard-spec.yaml",
            status="generated",
            content=yaml.dump({"title": f"{service_id} Observability", "uid": uid, "panels": []}),
        )
    )
    return report


class TestGrafanaJsonConversion:
    def test_success_emits_dashboard_at_contracted_path(self, monkeypatch):
        import startd8.dashboard_creator.workflow as wf_mod
        from startd8.observability.artifact_generator import (
            _convert_dashboards_to_grafana_json,
        )

        fake = _FakeWorkflow()
        monkeypatch.setattr(wf_mod, "DashboardCreatorWorkflow", lambda: fake)

        report = _report_with_dashboard_spec()
        _convert_dashboards_to_grafana_json(report)

        dash = [a for a in report.artifacts if a.artifact_type == "dashboard"]
        assert len(dash) == 1
        assert dash[0].status == "generated"
        assert dash[0].output_path == "grafana/dashboards/strtd8-dashboard.json"
        assert json.loads(dash[0].content)["uid"] == "obs-strtd8"

    def test_uid_convention_preserved_via_enforce_uid_false(self, monkeypatch):
        import startd8.dashboard_creator.workflow as wf_mod
        from startd8.observability.artifact_generator import (
            _convert_dashboards_to_grafana_json,
        )

        fake = _FakeWorkflow()
        monkeypatch.setattr(wf_mod, "DashboardCreatorWorkflow", lambda: fake)

        _convert_dashboards_to_grafana_json(_report_with_dashboard_spec())
        # The obs-{service} uid must reach the workflow unchanged, with enforcement off.
        assert fake.last_config["enforce_uid"] is False
        assert fake.last_config["spec"]["uid"] == "obs-strtd8"

    def test_workflow_failure_degrades_to_skipped(self, monkeypatch):
        import startd8.dashboard_creator.workflow as wf_mod
        from startd8.observability.artifact_generator import (
            _convert_dashboards_to_grafana_json,
        )

        monkeypatch.setattr(
            wf_mod, "DashboardCreatorWorkflow", lambda: _FakeWorkflow(succeed=False)
        )
        report = _report_with_dashboard_spec()
        _convert_dashboards_to_grafana_json(report)

        dash = [a for a in report.artifacts if a.artifact_type == "dashboard"][0]
        assert dash.status == "skipped"
        assert "compile failed" in (dash.error_message or "")

    def test_workflow_exception_degrades_to_skipped(self, monkeypatch):
        import startd8.dashboard_creator.workflow as wf_mod
        from startd8.observability.artifact_generator import (
            _convert_dashboards_to_grafana_json,
        )

        monkeypatch.setattr(
            wf_mod, "DashboardCreatorWorkflow", lambda: _FakeWorkflow(raises=True)
        )
        report = _report_with_dashboard_spec()
        _convert_dashboards_to_grafana_json(report)

        dash = [a for a in report.artifacts if a.artifact_type == "dashboard"][0]
        assert dash.status == "skipped"
        assert "conversion raised" in (dash.error_message or "")

    def test_no_provision_url_means_no_provision_config(self, monkeypatch):
        import startd8.dashboard_creator.workflow as wf_mod
        from startd8.observability.artifact_generator import (
            _convert_dashboards_to_grafana_json,
        )

        fake = _FakeWorkflow()
        monkeypatch.setattr(wf_mod, "DashboardCreatorWorkflow", lambda: fake)
        _convert_dashboards_to_grafana_json(_report_with_dashboard_spec())
        assert "provision" not in fake.last_config

    def test_provision_url_threads_into_workflow_config(self, monkeypatch):
        import startd8.dashboard_creator.workflow as wf_mod
        from startd8.observability.artifact_generator import (
            _convert_dashboards_to_grafana_json,
        )

        fake = _FakeWorkflow()
        monkeypatch.setattr(wf_mod, "DashboardCreatorWorkflow", lambda: fake)
        _convert_dashboards_to_grafana_json(
            _report_with_dashboard_spec(), provision_url="http://grafana:3000"
        )
        assert fake.last_config["provision"] is True
        assert fake.last_config["grafana_url"] == "http://grafana:3000"

    def test_provision_failure_is_warn_dont_fail(self, monkeypatch):
        """A failed push must not demote the generated dashboard artifact."""
        import startd8.dashboard_creator.workflow as wf_mod
        from startd8.observability.artifact_generator import (
            _convert_dashboards_to_grafana_json,
        )

        monkeypatch.setattr(
            wf_mod,
            "DashboardCreatorWorkflow",
            lambda: _FakeWorkflow(provision_succeeds=False),
        )
        report = _report_with_dashboard_spec()
        _convert_dashboards_to_grafana_json(report, provision_url="http://grafana:3000")

        dash = [a for a in report.artifacts if a.artifact_type == "dashboard"][0]
        # Dashboard still generated despite the provisioning failure.
        assert dash.status == "generated"


# Toolchain-gated real compile (jsonnet binary + mixin vendor present).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HAS_TOOLCHAIN = (
    __import__("shutil").which("jsonnet") is not None
    and (_REPO_ROOT / "startd8-mixin" / "vendor").exists()
)


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_TOOLCHAIN, reason="jsonnet + startd8-mixin/vendor required")
class TestGrafanaJsonE2E:
    def test_observability_spec_compiles_to_grafana_json(self, tmp_path):
        meta = {
            "project_id": "startd8/run-003",
            "instrumentation_hints": {
                "strtd8": {
                    "service_id": "strtd8",
                    "transport": "http",
                    "metrics": {
                        "convention_based": [
                            {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"},
                        ],
                    },
                },
            },
        }
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(meta))
        out = tmp_path / "observability"

        generate_observability_artifacts(onboarding_metadata_path=meta_path, output_dir=out)

        gj = out / "grafana" / "dashboards" / "strtd8-dashboard.json"
        assert gj.is_file(), "contracted Grafana JSON must be written"
        dash = json.loads(gj.read_text())
        assert dash["uid"] == "obs-strtd8"  # obs uid convention preserved
        # threshold panels (the ISSUE_8 crash class) now compile successfully
        assert any(
            p.get("fieldConfig", {}).get("defaults", {}).get("thresholds")
            for p in dash["panels"]
        )


# ---------------------------------------------------------------------------
# Closure 3A / Gap 2: honest coverage reporting for unimplemented artifact types
# ---------------------------------------------------------------------------

# The eight artifact types the onboarding contract declares (gap analysis §1.1).
DECLARED_8 = {
    "capability_index": {},
    "dashboard": {},
    "loki_rule": {},
    "notification_policy": {},
    "prometheus_rule": {},
    "runbook": {},
    "service_monitor": {},
    "slo_definition": {},
}


def _meta_with_declared_types(artifact_types):
    return {
        "project_id": "startd8/run-003",
        "artifact_types": artifact_types,
        "instrumentation_hints": {
            "strtd8": {
                "service_id": "strtd8",
                "transport": "http",
                "metrics": {
                    "convention_based": [
                        {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"},
                    ],
                },
            },
        },
    }


class TestUnimplementedArtifactTypeReporting:
    def test_declared_artifact_types_parsing(self):
        from startd8.observability.artifact_generator import _declared_artifact_types

        assert _declared_artifact_types({"artifact_types": DECLARED_8}) == sorted(DECLARED_8)
        assert _declared_artifact_types({"artifact_types": ["dashboard", "runbook"]}) == [
            "dashboard",
            "runbook",
        ]
        assert _declared_artifact_types({}) == []

    def test_all_eight_declared_types_now_generated(self, tmp_path):
        """Closure 3B: with all 8 standard types declared, all are produced."""
        meta_path = tmp_path / "m.json"
        meta_path.write_text(json.dumps(_meta_with_declared_types(DECLARED_8)))
        out = tmp_path / "obs"

        report = generate_observability_artifacts(
            onboarding_metadata_path=meta_path, output_dir=out
        )

        summary = yaml.safe_load((out / "observability-manifest.yaml").read_text())["summary"]
        assert summary["artifact_type_coverage"] == 1.0
        assert summary["unimplemented_artifact_types"] == []
        produced = {a.artifact_type for a in report.artifacts if a.status == "generated"}
        for expected in (
            "service_monitor",
            "notification_policy",
            "loki_rule",
            "runbook",
            "capability_index",
        ):
            assert expected in produced

    def test_truly_unimplemented_type_recorded_as_skipped(self, tmp_path):
        """A declared type with no native generator is still an honest skip (Gap 2)."""
        meta_path = tmp_path / "m.json"
        meta_path.write_text(
            json.dumps(
                _meta_with_declared_types(
                    {"dashboard": {}, "prometheus_rule": {}, "trace_pipeline": {}}
                )
            )
        )
        out = tmp_path / "obs"

        generate_observability_artifacts(onboarding_metadata_path=meta_path, output_dir=out)

        idx = yaml.safe_load((out / "observability-manifest.yaml").read_text())
        summary = idx["summary"]
        assert summary["unimplemented_artifact_types"] == ["trace_pipeline"]
        assert summary["artifact_type_coverage"] == round(2 / 3, 4)
        skipped_types = {a["type"] for a in idx["artifacts"] if a["status"] == "skipped"}
        assert "trace_pipeline" in skipped_types

    def test_no_declared_types_no_coverage_fields(self, tmp_path):
        # Metadata without artifact_types → no coverage section, no synthetic skips.
        meta = _meta_with_declared_types(None)
        del meta["artifact_types"]
        meta_path = tmp_path / "m.json"
        meta_path.write_text(json.dumps(meta))
        out = tmp_path / "obs"

        generate_observability_artifacts(onboarding_metadata_path=meta_path, output_dir=out)

        summary = yaml.safe_load((out / "observability-manifest.yaml").read_text())["summary"]
        assert "artifact_type_coverage" not in summary
        assert "unimplemented_artifact_types" not in summary

    def test_full_implementation_scores_one(self, tmp_path):
        # When only the implemented types are declared, coverage is 1.0 and nothing is skipped for type-coverage.
        meta_path = tmp_path / "m.json"
        meta_path.write_text(
            json.dumps(
                _meta_with_declared_types(
                    {"dashboard": {}, "prometheus_rule": {}, "slo_definition": {}}
                )
            )
        )
        out = tmp_path / "obs"

        generate_observability_artifacts(onboarding_metadata_path=meta_path, output_dir=out)

        summary = yaml.safe_load((out / "observability-manifest.yaml").read_text())["summary"]
        assert summary["artifact_type_coverage"] == 1.0
        assert summary["unimplemented_artifact_types"] == []


# ---------------------------------------------------------------------------
# #3: CLI coverage gate wiring (scripts/generate_observability_artifacts.py)
# ---------------------------------------------------------------------------


def _load_cli_module():
    import importlib.util

    repo = Path(__file__).resolve().parents[3]
    path = repo / "scripts" / "generate_observability_artifacts.py"
    spec = importlib.util.spec_from_file_location("gen_obs_cli", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_reports(out, *, metric_coverage=None, artifact_type_coverage=None):
    out.mkdir(parents=True, exist_ok=True)
    (out / "observability-quality.json").write_text(
        json.dumps({"aggregate": {"avg_metric_coverage_score": metric_coverage}})
    )
    (out / "observability-manifest.yaml").write_text(
        yaml.dump({"summary": {"artifact_type_coverage": artifact_type_coverage}})
    )


class TestCliCoverageGate:
    def test_no_thresholds_no_gate(self, tmp_path):
        import types

        mod = _load_cli_module()
        args = types.SimpleNamespace(
            min_metric_coverage=None, min_artifact_type_coverage=None, dry_run=False
        )
        assert mod._apply_coverage_gate(args, tmp_path) is False

    def test_gate_fails_below_threshold(self, tmp_path):
        import types

        mod = _load_cli_module()
        _write_reports(tmp_path, metric_coverage=0.23, artifact_type_coverage=0.375)
        args = types.SimpleNamespace(
            min_metric_coverage=0.5, min_artifact_type_coverage=0.5, dry_run=False
        )
        assert mod._apply_coverage_gate(args, tmp_path) is True  # FAILED

    def test_gate_passes_at_threshold(self, tmp_path):
        import types

        mod = _load_cli_module()
        _write_reports(tmp_path, metric_coverage=0.9, artifact_type_coverage=1.0)
        args = types.SimpleNamespace(
            min_metric_coverage=0.8, min_artifact_type_coverage=0.5, dry_run=False
        )
        assert mod._apply_coverage_gate(args, tmp_path) is False  # passed

    def test_gate_skipped_in_dry_run(self, tmp_path):
        import types

        mod = _load_cli_module()
        args = types.SimpleNamespace(
            min_metric_coverage=0.9, min_artifact_type_coverage=None, dry_run=True
        )
        assert mod._apply_coverage_gate(args, tmp_path) is False


# ---------------------------------------------------------------------------
# Closure 3B: native extended artifact generators
# ---------------------------------------------------------------------------


class TestExtendedGenerators:
    def test_service_monitor_is_valid_crd(self, grpc_service, business):
        from startd8.observability.artifact_generator import generate_service_monitor

        result = generate_service_monitor(grpc_service, business)
        assert result.artifact_type == "service_monitor"
        assert result.status == "generated"
        doc = yaml.safe_load(result.content)
        assert doc["apiVersion"] == "monitoring.coreos.com/v1"
        assert doc["kind"] == "ServiceMonitor"
        assert doc["spec"]["selector"]["matchLabels"]["app"] == "checkout-api"

    def test_notification_policy_routes_by_service(self, grpc_service, business):
        from startd8.observability.artifact_generator import generate_notification_policy

        result = generate_notification_policy(grpc_service, business)
        doc = yaml.safe_load(result.content)
        route = doc["route"]["routes"][0]
        assert "service = checkout-api" in route["matchers"]
        # high criticality → critical severity → receiver name
        assert route["receiver"] == "checkout-api-critical"

    def test_loki_rule_uses_logql_error_filter(self, grpc_service, business):
        from startd8.observability.artifact_generator import generate_loki_rule

        result = generate_loki_rule(grpc_service, business)
        doc = yaml.safe_load(result.content)
        rule = doc["groups"][0]["rules"][0]
        assert 'service="checkout-api"' in rule["expr"]
        assert '|= "error"' in rule["expr"]
        assert rule["labels"]["severity"] == "critical"

    def test_runbook_is_markdown_with_service_context(self, grpc_service, business):
        from startd8.observability.artifact_generator import generate_runbook

        result = generate_runbook(grpc_service, business)
        assert result.output_path.endswith(".md")
        assert "# Runbook: checkout-api" in result.content
        assert "/d/obs-checkout-api" in result.content
        assert "postgresql" in result.content  # detected_databases surfaced

    def test_capability_index_inventories_artifacts(self, grpc_service, business):
        from startd8.observability.artifact_generator import (
            generate_capability_index,
            GenerationReport,
            ArtifactResult,
        )

        report = GenerationReport(project_id="proj", generated_at="t")
        report.artifacts.append(
            ArtifactResult("alert_rule", "checkout-api", "x", "generated")
        )
        result = generate_capability_index([grpc_service], business, report)
        assert result.artifact_type == "capability_index"
        doc = yaml.safe_load(result.content)
        assert doc["services"] == ["checkout-api"]
        assert "alert_rule" in doc["observability_capabilities"]["artifact_types_generated"]
