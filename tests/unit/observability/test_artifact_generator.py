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
