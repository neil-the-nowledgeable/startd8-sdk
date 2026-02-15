"""Tests for the PrometheusRule generator (F-009).

Covers all 9 test categories specified in the design document:
  1. Registration
  2. Threshold extraction priority (3-tier fallback)
  3. Type validation and coercion
  4. Parameter validation (range & format)
  5. File generation and overwrite semantics
  6. Error isolation
  7. Derivation rules tracing
  8. Alert name generation (pascal_case)
  9. Metric name resolution (HTTP / gRPC / custom)
 10. Post-render structural validation
 11. Integration (all 11 Online Boutique services)
"""
from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from contextcore.generators.artifact_generators import (
    GenerationResult,
    DerivationRule,
    GENERATOR_REGISTRY,
    generate_prometheus_rule,
    _coerce_numeric,
    _extract_prometheus_thresholds,
    _validate_prometheus_params,
    _validate_rendered_output,
)
from contextcore.generators.options import GeneratorOptions


# ── Test Fixtures ──────────────────────────────────────────────

SAMPLE_SPEC: dict = {
    "id": "prometheus-rule-cartservice-001",
    "type": "PrometheusRule",
    "service": "cartservice",
    "namespace": "online-boutique",
    "parameters": {},
}

SAMPLE_MANIFEST: dict = {
    "services": {
        "cartservice": {
            "protocol": "grpc",
            "slos": {
                "error_rate_threshold_pct": 1.0,
                "latency_p99_threshold_ms": 400,
                "availability_target_pct": 99.95,
            },
        }
    }
}


# ── 1. Registration ───────────────────────────────────────────

class TestRegistration:
    """Verify the generator is discoverable in the global registry."""

    def test_registered_in_registry(self) -> None:
        assert "PrometheusRule" in GENERATOR_REGISTRY

    def test_registry_points_to_function(self) -> None:
        assert GENERATOR_REGISTRY["PrometheusRule"] is generate_prometheus_rule


# ── 2. Happy Path: Threshold Extraction Priority ──────────────

class TestThresholdExtraction:
    """3-tier fallback: explicit → SLO → built-in default."""

    def test_explicit_params_override_slo_defaults(self) -> None:
        spec = {
            "service": "cartservice",
            "parameters": {"error_rate_threshold_pct": 2.5},
        }
        manifest = {
            "services": {
                "cartservice": {"slos": {"error_rate_threshold_pct": 1.0}}
            }
        }
        params, rules = _extract_prometheus_thresholds(spec, manifest)
        assert params["error_rate_threshold_pct"] == 2.5
        assert rules[0].source == "artifact_spec.parameters.error_rate_threshold_pct"

    def test_slo_fallback_when_no_explicit_param(self) -> None:
        spec = {"service": "cartservice", "parameters": {}}
        manifest = {
            "services": {
                "cartservice": {"slos": {"error_rate_threshold_pct": 0.5}}
            }
        }
        params, _ = _extract_prometheus_thresholds(spec, manifest)
        assert params["error_rate_threshold_pct"] == 0.5

    def test_builtin_defaults_when_no_slo(self) -> None:
        spec = {"service": "cartservice"}
        manifest = {"services": {"cartservice": {}}}
        params, rules = _extract_prometheus_thresholds(spec, manifest)
        assert params["error_rate_threshold_pct"] == 1.0
        assert any(r.source == "built_in_default" for r in rules)


# ── 3. Type Validation and Coercion ───────────────────────────

class TestTypeCoercion:
    """Numeric type coercion, including edge-case rejections."""

    def test_non_numeric_threshold_raises_value_error(self) -> None:
        spec = {
            "service": "cartservice",
            "parameters": {"latency_p99_threshold_ms": "fast"},
        }
        manifest = {"services": {"cartservice": {}}}
        with pytest.raises(ValueError, match="must be numeric"):
            _extract_prometheus_thresholds(spec, manifest)

    def test_string_numeric_threshold_is_coerced(self) -> None:
        spec = {
            "service": "cartservice",
            "parameters": {"error_rate_threshold_pct": "2.5"},
        }
        manifest = {"services": {"cartservice": {}}}
        params, _ = _extract_prometheus_thresholds(spec, manifest)
        assert params["error_rate_threshold_pct"] == 2.5
        assert isinstance(params["error_rate_threshold_pct"], float)

    def test_non_numeric_threshold_returns_error_result(self, tmp_path: Path) -> None:
        spec = {
            **SAMPLE_SPEC,
            "parameters": {"latency_p99_threshold_ms": "fast"},
        }
        result = generate_prometheus_rule(spec, SAMPLE_MANIFEST, tmp_path)
        assert result.status == "error"
        assert "must be numeric" in result.message

    def test_int_is_coerced_to_float(self) -> None:
        assert _coerce_numeric("test", 5) == 5.0
        assert isinstance(_coerce_numeric("test", 5), float)

    def test_none_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="must be numeric"):
            _coerce_numeric("test", None)

    def test_list_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="must be numeric"):
            _coerce_numeric("test", [1, 2])


# ── 4. Parameter Validation ───────────────────────────────────

class TestParamValidation:
    """Range checks (warnings) and duration format checks (errors)."""

    def test_out_of_range_threshold_produces_warning(self, tmp_path: Path) -> None:
        spec = {**SAMPLE_SPEC, "parameters": {"error_rate_threshold_pct": 150.0}}
        result = generate_prometheus_rule(spec, SAMPLE_MANIFEST, tmp_path)
        assert result.status == "success"
        assert "outside [0, 100]" in result.message

    def test_invalid_duration_format_returns_error(self, tmp_path: Path) -> None:
        spec = {**SAMPLE_SPEC, "parameters": {"for_duration": "five-minutes"}}
        result = generate_prometheus_rule(spec, SAMPLE_MANIFEST, tmp_path)
        assert result.status == "error"
        assert "not a valid Prometheus duration" in result.message

    def test_negative_latency_produces_warning(self, tmp_path: Path) -> None:
        spec = {**SAMPLE_SPEC, "parameters": {"latency_p99_threshold_ms": -10.0}}
        result = generate_prometheus_rule(spec, SAMPLE_MANIFEST, tmp_path)
        assert result.status == "success"
        assert "must be positive" in result.message

    def test_valid_duration_formats(self) -> None:
        params = {
            "error_rate_threshold_pct": 1.0,
            "latency_p99_threshold_ms": 500.0,
            "availability_target_pct": 99.9,
            "evaluation_interval": "30s",
            "for_duration": "5m",
        }
        warnings, errors = _validate_prometheus_params(params)
        assert errors == []

    def test_all_valid_duration_units(self) -> None:
        for dur in ("1s", "5m", "1h", "1d", "1w", "1y"):
            params = {
                "error_rate_threshold_pct": 1.0,
                "latency_p99_threshold_ms": 500.0,
                "availability_target_pct": 99.9,
                "evaluation_interval": dur,
                "for_duration": dur,
            }
            _, errors = _validate_prometheus_params(params)
            assert errors == [], f"Duration '{dur}' should be valid"


# ── 5. File Generation and Overwrite Semantics ────────────────

class TestFileGeneration:
    """File writing, path conventions, and ``--force`` behaviour."""

    def test_generates_valid_yaml(self, tmp_path: Path) -> None:
        result = generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        assert result.status == "success"
        content = yaml.safe_load(result.output_path.read_text())
        assert content["kind"] == "PrometheusRule"
        assert content["apiVersion"] == "monitoring.coreos.com/v1"
        assert len(content["spec"]["groups"][0]["rules"]) == 3

    def test_output_path_follows_convention(self, tmp_path: Path) -> None:
        result = generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        expected = tmp_path / "cartservice" / "cartservice-prometheus-rules.yaml"
        assert result.output_path == expected
        assert expected.exists()

    def test_skips_existing_without_force(self, tmp_path: Path) -> None:
        generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        result = generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        assert result.status == "skipped"

    def test_overwrites_existing_with_force(self, tmp_path: Path) -> None:
        generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        options = GeneratorOptions(force=True)
        result = generate_prometheus_rule(
            SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path, options
        )
        assert result.status == "success"

    def test_skipped_has_no_output_path(self, tmp_path: Path) -> None:
        generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        result = generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        assert result.output_path is None

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        assert (tmp_path / "cartservice").is_dir()


# ── 6. Error Isolation ────────────────────────────────────────

class TestErrorIsolation:
    """The generator must never raise to the caller."""

    def test_missing_service_returns_error_not_exception(self, tmp_path: Path) -> None:
        result = generate_prometheus_rule({"type": "PrometheusRule"}, {}, tmp_path)
        assert result.status == "error"
        assert "service" in result.message.lower() or "key" in result.message.lower()

    def test_never_raises(self, tmp_path: Path) -> None:
        bad_inputs = [
            ({}, {}, tmp_path),
            (
                {
                    "service": "x",
                    "parameters": {"latency_p99_threshold_ms": "nope"},
                },
                {},
                tmp_path,
            ),
            ({"service": "x"}, {}, Path("/no/access/allowed")),
            ({"type": "PrometheusRule"}, {}, tmp_path),
        ]
        for args in bad_inputs:
            result = generate_prometheus_rule(*args)
            assert isinstance(result, GenerationResult)

    def test_derivation_rules_always_present_on_success(self, tmp_path: Path) -> None:
        result = generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        assert len(result.derivation_rules) >= 5


# ── 7. Derivation Rules Tracing ──────────────────────────────

class TestDerivationRules:
    """Machine- and human-readable traceability for every resolved parameter."""

    def test_derivation_rules_embedded_in_yaml_comments(self, tmp_path: Path) -> None:
        result = generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        content = result.output_path.read_text()
        assert "Derivation rules:" in content
        assert "error_rate_threshold_pct" in content

    def test_derivation_rule_values_sanitized_in_comments(
        self, tmp_path: Path
    ) -> None:
        spec = {**SAMPLE_SPEC, "parameters": {}}
        result = generate_prometheus_rule(spec, SAMPLE_MANIFEST, tmp_path)
        content = result.output_path.read_text()
        for line in content.split("\n"):
            if line.strip().startswith("#"):
                assert "\n" not in line.strip()

    def test_derivation_rules_count(self, tmp_path: Path) -> None:
        result = generate_prometheus_rule(SAMPLE_SPEC, SAMPLE_MANIFEST, tmp_path)
        assert len(result.derivation_rules) == 5

    def test_derivation_rules_source_tracking(self) -> None:
        spec = {
            "service": "cartservice",
            "parameters": {"error_rate_threshold_pct": 2.5},
        }
        manifest = {
            "services": {
                "cartservice": {"slos": {"latency_p99_threshold_ms": 300}}
            }
        }
        _, rules = _extract_prometheus_thresholds(spec, manifest)

        sources = {r.field: r.source for r in rules}
        assert (
            sources["error_rate_threshold_pct"]
            == "artifact_spec.parameters.error_rate_threshold_pct"
        )
        assert (
            sources["latency_p99_threshold_ms"]
            == "context_manifest.services.cartservice.slos.latency_p99_threshold_ms"
        )
        assert sources["availability_target_pct"] == "built_in_default"


# ── 8. Alert Name Generation ─────────────────────────────────

class TestAlertNames:
    """PascalCase alert names for hyphenated/underscored service names."""

    def test_pascal_case_alert_names_for_hyphenated_services(
        self, tmp_path: Path
    ) -> None:
        spec = {**SAMPLE_SPEC, "service": "frontend-gateway"}
        manifest = {"services": {"frontend-gateway": {"slos": {}}}}
        result = generate_prometheus_rule(spec, manifest, tmp_path)
        content = result.output_path.read_text()
        assert "FrontendGatewayHighErrorRate" in content
        assert "FrontendGatewayHighLatency" in content
        assert "FrontendGatewayLowAvailability" in content

    def test_pascal_case_alert_names_for_underscore_services(
        self, tmp_path: Path
    ) -> None:
        spec = {**SAMPLE_SPEC, "service": "payment_service"}
        manifest = {"services": {"payment_service": {"slos": {}}}}
        result = generate_prometheus_rule(spec, manifest, tmp_path)
        content = result.output_path.read_text()
        assert "PaymentServiceHighErrorRate" in content

    def test_simple_service_name(self, tmp_path: Path) -> None:
        spec = {**SAMPLE_SPEC, "service": "cartservice"}
        result = generate_prometheus_rule(spec, SAMPLE_MANIFEST, tmp_path)
        content = result.output_path.read_text()
        assert "CartserviceHighErrorRate" in content


# ── 9. Metric Name Resolution ────────────────────────────────

class TestMetricResolution:
    """HTTP vs gRPC vs custom metric name selection."""

    def test_grpc_service_uses_grpc_metrics(self, tmp_path: Path) -> None:
        manifest = {
            "services": {"cartservice": {"protocol": "grpc", "slos": {}}}
        }
        result = generate_prometheus_rule(SAMPLE_SPEC, manifest, tmp_path)
        content = result.output_path.read_text()
        assert "grpc_server_handled_total" in content
        assert "grpc_server_handling_seconds_bucket" in content

    def test_http_service_uses_http_metrics(self, tmp_path: Path) -> None:
        spec = {**SAMPLE_SPEC, "service": "frontend"}
        manifest = {
            "services": {"frontend": {"protocol": "http", "slos": {}}}
        }
        result = generate_prometheus_rule(spec, manifest, tmp_path)
        content = result.output_path.read_text()
        assert "http_requests_total" in content
        assert "http_request_duration_seconds_bucket" in content

    def test_custom_metrics_override(self, tmp_path: Path) -> None:
        spec = {
            **SAMPLE_SPEC,
            "metrics": {"requests_total": "my_custom_requests_total"},
        }
        result = generate_prometheus_rule(spec, SAMPLE_MANIFEST, tmp_path)
        content = result.output_path.read_text()
        assert "my_custom_requests_total" in content
        # Partial override: request_duration_bucket falls back to gRPC default
        assert "grpc_server_handling_seconds_bucket" in content

    def test_default_protocol_is_http(self, tmp_path: Path) -> None:
        spec = {**SAMPLE_SPEC, "service": "myservice"}
        manifest = {"services": {"myservice": {"slos": {}}}}
        result = generate_prometheus_rule(spec, manifest, tmp_path)
        content = result.output_path.read_text()
        assert "http_requests_total" in content


# ── 10. Post-Render Structural Validation ─────────────────────

class TestStructuralValidation:
    """YAML round-trip checks on rendered output."""

    def test_catches_broken_yaml(self) -> None:
        errors = _validate_rendered_output("not: a: prometheus: rule")
        assert len(errors) > 0
        assert any("apiVersion" in e for e in errors)

    def test_catches_wrong_kind(self) -> None:
        doc = yaml.dump(
            {
                "apiVersion": "monitoring.coreos.com/v1",
                "kind": "ServiceMonitor",
                "spec": {
                    "groups": [
                        {
                            "name": "test",
                            "rules": [{"alert": "x", "expr": "y"}],
                        }
                    ]
                },
            }
        )
        errors = _validate_rendered_output(doc)
        assert any("kind" in e for e in errors)

    def test_catches_missing_groups(self) -> None:
        doc = yaml.dump(
            {
                "apiVersion": "monitoring.coreos.com/v1",
                "kind": "PrometheusRule",
                "spec": {},
            }
        )
        errors = _validate_rendered_output(doc)
        assert any("groups" in e for e in errors)

    def test_catches_missing_alert_key(self) -> None:
        doc = yaml.dump(
            {
                "apiVersion": "monitoring.coreos.com/v1",
                "kind": "PrometheusRule",
                "spec": {
                    "groups": [
                        {"name": "test", "rules": [{"expr": "up == 1"}]}
                    ]
                },
            }
        )
        errors = _validate_rendered_output(doc)
        assert any("alert" in e for e in errors)

    def test_valid_structure_returns_empty(self) -> None:
        doc = yaml.dump(
            {
                "apiVersion": "monitoring.coreos.com/v1",
                "kind": "PrometheusRule",
                "spec": {
                    "groups": [
                        {
                            "name": "test",
                            "rules": [{"alert": "x", "expr": "y"}],
                        }
                    ]
                },
            }
        )
        errors = _validate_rendered_output(doc)
        assert errors == []

    def test_invalid_yaml_string(self) -> None:
        errors = _validate_rendered_output("{{{{not yaml")
        assert len(errors) > 0
        assert any("not valid YAML" in e for e in errors)


# ── 11. Integration: All 11 Online Boutique Services ─────────

class TestIntegration:
    """End-to-end generation for the full Online Boutique deployment."""

    def test_all_11_online_boutique_services(
        self, tmp_path: Path, online_boutique_manifest: dict
    ) -> None:
        options = GeneratorOptions(force=False)
        specs = [
            s
            for s in online_boutique_manifest["artifacts"]
            if s["type"] == "PrometheusRule"
        ]
        assert len(specs) == 11
        results = [
            generate_prometheus_rule(s, online_boutique_manifest, tmp_path, options)
            for s in specs
        ]
        failures = [
            (r.service, r.message) for r in results if r.status != "success"
        ]
        assert all(r.status == "success" for r in results), f"Failures: {failures}"
        assert len(list(tmp_path.rglob("*-prometheus-rules.yaml"))) == 11

    def test_grpc_services_use_correct_metrics(
        self, tmp_path: Path, online_boutique_manifest: dict
    ) -> None:
        options = GeneratorOptions(force=False)
        grpc_services = {
            name
            for name, svc in online_boutique_manifest["services"].items()
            if svc.get("protocol") == "grpc"
        }
        specs = [
            s
            for s in online_boutique_manifest["artifacts"]
            if s["service"] in grpc_services
        ]
        for spec in specs:
            result = generate_prometheus_rule(
                spec, online_boutique_manifest, tmp_path, options
            )
            assert result.status == "success"
            content = result.output_path.read_text()
            assert "grpc_server_handled_total" in content, (
                f"{result.service} should use gRPC metrics"
            )

    def test_http_services_get_http_metrics(
        self, tmp_path: Path, online_boutique_manifest: dict
    ) -> None:
        options = GeneratorOptions(force=False)
        http_services = {
            name
            for name, svc in online_boutique_manifest["services"].items()
            if svc.get("protocol") == "http"
        }
        specs = [
            s
            for s in online_boutique_manifest["artifacts"]
            if s["service"] in http_services
        ]
        for spec in specs:
            result = generate_prometheus_rule(
                spec, online_boutique_manifest, tmp_path, options
            )
            content = result.output_path.read_text()
            assert "http_requests_total" in content

    def test_all_outputs_are_valid_yaml(
        self, tmp_path: Path, online_boutique_manifest: dict
    ) -> None:
        options = GeneratorOptions(force=False)
        specs = [
            s
            for s in online_boutique_manifest["artifacts"]
            if s["type"] == "PrometheusRule"
        ]
        for spec in specs:
            result = generate_prometheus_rule(
                spec, online_boutique_manifest, tmp_path, options
            )
            doc = yaml.safe_load(result.output_path.read_text())
            assert doc["kind"] == "PrometheusRule"
            assert doc["apiVersion"] == "monitoring.coreos.com/v1"
            assert len(doc["spec"]["groups"][0]["rules"]) == 3