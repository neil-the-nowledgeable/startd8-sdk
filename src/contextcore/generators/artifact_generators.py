"""Tests for the ServiceMonitor generator (F-006).

Covers registration, happy path, derivation rules, interval fallback,
overwrite guard, error isolation, default values, labels edge cases,
YAML validity, and the full 11-service integration scenario.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from contextcore.generators.artifact_generators import (
    generate_service_monitor,
    GenerationResult,
    GenerationStatus,
    GENERATOR_REGISTRY,
)


# ── Registration ────────────────────────────────────────────────────
class TestRegistration:
    def test_registered_in_registry(self):
        assert "ServiceMonitor" in GENERATOR_REGISTRY

    def test_registry_points_to_function(self):
        assert GENERATOR_REGISTRY["ServiceMonitor"] is generate_service_monitor


# ── Happy path ──────────────────────────────────────────────────────
class TestHappyPath:
    def test_generates_valid_yaml(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "cartservice", "interval": "15s"}
        manifest = {"observability": {}}
        result = generate_service_monitor(spec, manifest, tmp_path)

        assert result.status == GenerationStatus.CREATED
        assert result.ok is True
        content = result.output_path.read_text()
        assert "kind: ServiceMonitor" in content
        assert "cartservice" in content
        assert "interval: 15s" in content

    def test_output_path_follows_convention(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        result = generate_service_monitor(spec, {}, tmp_path)
        expected = tmp_path / "service-monitors" / "frontend-service-monitor.yaml"
        assert result.output_path == expected
        assert expected.exists()


# ── Derivation rules ───────────────────────────────────────────────
class TestDerivationRules:
    def test_derivation_rules_in_output(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        result = generate_service_monitor(spec, {}, tmp_path)
        assert len(result.derivation_rules) >= 4
        content = result.output_path.read_text()
        assert "derivation_rules" in content

    def test_derivation_rules_count(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        result = generate_service_monitor(spec, {}, tmp_path)
        assert len(result.derivation_rules) == 5

    def test_no_duplicate_interval_rule(self, tmp_path: Path):
        """Only one derivation rule per field, even with a global fallback."""
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        manifest = {"observability": {"default_scrape_interval": "45s"}}
        result = generate_service_monitor(spec, manifest, tmp_path)
        interval_rules = [
            r for r in result.derivation_rules
            if r["field"] == "spec.endpoints[0].interval"
        ]
        assert len(interval_rules) == 1
        assert "45s" in interval_rules[0]["source"]

    def test_derivation_source_artifact_interval(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "x", "interval": "10s"}
        manifest = {"observability": {"default_scrape_interval": "45s"}}
        result = generate_service_monitor(spec, manifest, tmp_path)
        interval_rule = [
            r for r in result.derivation_rules
            if r["field"] == "spec.endpoints[0].interval"
        ][0]
        assert "artifact_spec.interval" in interval_rule["source"]

    def test_derivation_source_hardcoded_default(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "x"}
        result = generate_service_monitor(spec, {}, tmp_path)
        interval_rule = [
            r for r in result.derivation_rules
            if r["field"] == "spec.endpoints[0].interval"
        ][0]
        assert "hardcoded default" in interval_rule["source"]


# ── Interval fallback chain ────────────────────────────────────────
class TestIntervalFallback:
    def test_global_interval_fallback(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "cartservice"}
        manifest = {"observability": {"default_scrape_interval": "45s"}}
        result = generate_service_monitor(spec, manifest, tmp_path)
        content = result.output_path.read_text()
        assert "interval: 45s" in content

    def test_artifact_interval_overrides_global(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "cartservice", "interval": "10s"}
        manifest = {"observability": {"default_scrape_interval": "45s"}}
        result = generate_service_monitor(spec, manifest, tmp_path)
        content = result.output_path.read_text()
        assert "interval: 10s" in content

    def test_hardcoded_default_when_no_global(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "cartservice"}
        result = generate_service_monitor(spec, {}, tmp_path)
        content = result.output_path.read_text()
        assert "interval: 30s" in content


# ── Overwrite guard ─────────────────────────────────────────────────
class TestOverwriteGuard:
    def test_skips_existing_without_force(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        generate_service_monitor(spec, {}, tmp_path)
        result2 = generate_service_monitor(spec, {}, tmp_path)
        assert result2.status == GenerationStatus.SKIPPED
        assert result2.ok is True

    def test_overwrites_with_force(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        generate_service_monitor(spec, {}, tmp_path)
        result2 = generate_service_monitor(spec, {}, tmp_path, force=True)
        assert result2.status == GenerationStatus.CREATED

    def test_skipped_result_has_output_path(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        generate_service_monitor(spec, {}, tmp_path)
        result2 = generate_service_monitor(spec, {}, tmp_path)
        assert result2.output_path is not None
        assert result2.output_path.exists()


# ── Error isolation ─────────────────────────────────────────────────
class TestErrorIsolation:
    def test_missing_service_name_returns_failed(self, tmp_path: Path):
        result = generate_service_monitor({}, {}, tmp_path)
        assert result.status == GenerationStatus.FAILED
        assert result.ok is False
        assert result.error is not None
        assert result.service_name == "UNKNOWN"

    def test_bad_output_dir_returns_failed(self):
        spec = {"type": "ServiceMonitor", "service_name": "x"}
        result = generate_service_monitor(spec, {}, Path("/nonexistent/readonly"))
        assert result.status == GenerationStatus.FAILED

    def test_invalid_interval_returns_failed(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "cartservice", "interval": "bogus"}
        result = generate_service_monitor(spec, {}, tmp_path)
        assert result.status == GenerationStatus.FAILED
        assert "Invalid Prometheus duration" in result.error

    def test_empty_interval_string_returns_failed(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "cartservice", "interval": ""}
        result = generate_service_monitor(spec, {}, tmp_path)
        assert result.status == GenerationStatus.FAILED

    def test_never_raises(self, tmp_path: Path):
        """Regardless of input, the function must return, not raise."""
        bad_inputs = [
            ({}, {}, tmp_path),
            ({"service_name": "x", "interval": "nope"}, {}, tmp_path),
            ({"service_name": "x"}, {}, Path("/no/access")),
        ]
        for args in bad_inputs:
            result = generate_service_monitor(*args)
            assert isinstance(result, GenerationResult)


# ── Default values ──────────────────────────────────────────────────
class TestDefaults:
    def test_defaults_applied(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "emailservice"}
        result = generate_service_monitor(spec, {}, tmp_path)
        content = result.output_path.read_text()
        assert "interval: 30s" in content
        assert "/metrics" in content
        assert "namespace: monitoring" in content

    def test_port_default(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "emailservice"}
        result = generate_service_monitor(spec, {}, tmp_path)
        content = result.output_path.read_text()
        assert "port: http-metrics" in content


# ── Labels edge cases ──────────────────────────────────────────────
class TestLabels:
    def test_empty_labels_valid_yaml(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "cartservice", "labels": {}}
        result = generate_service_monitor(spec, {}, tmp_path)
        doc = yaml.safe_load(result.output_path.read_text())
        assert doc["metadata"]["labels"] == {"app": "cartservice"}

    def test_labels_with_special_characters(self, tmp_path: Path):
        spec = {
            "type": "ServiceMonitor",
            "service_name": "cartservice",
            "labels": {
                "app.kubernetes.io/part-of": "boutique",
                "team": "cart & payments",
            },
        }
        result = generate_service_monitor(spec, {}, tmp_path)
        doc = yaml.safe_load(result.output_path.read_text())
        assert doc["metadata"]["labels"]["app.kubernetes.io/part-of"] == "boutique"
        assert doc["metadata"]["labels"]["team"] == "cart & payments"

    def test_multiple_labels_present(self, tmp_path: Path):
        spec = {
            "type": "ServiceMonitor",
            "service_name": "cartservice",
            "labels": {"team": "cart", "env": "prod"},
        }
        result = generate_service_monitor(spec, {}, tmp_path)
        doc = yaml.safe_load(result.output_path.read_text())
        labels = doc["metadata"]["labels"]
        assert labels["app"] == "cartservice"
        assert labels["team"] == "cart"
        assert labels["env"] == "prod"


# ── YAML validity ──────────────────────────────────────────────────
class TestYamlValidity:
    def test_output_is_valid_yaml(self, tmp_path: Path):
        spec = {
            "type": "ServiceMonitor",
            "service_name": "cartservice",
            "labels": {"team": "cart"},
        }
        result = generate_service_monitor(spec, {}, tmp_path)
        raw = result.output_path.read_text()
        docs = list(yaml.safe_load_all(raw))
        assert len(docs) == 1
        assert docs[0]["kind"] == "ServiceMonitor"
        assert docs[0]["apiVersion"] == "monitoring.coreos.com/v1"

    def test_output_roundtrips_through_yaml(self, tmp_path: Path):
        """Stricter check: dump and reload to verify structural integrity."""
        spec = {
            "type": "ServiceMonitor",
            "service_name": "cartservice",
            "labels": {"team": "cart", "env": "prod"},
            "interval": "15s",
        }
        result = generate_service_monitor(spec, {}, tmp_path)
        doc = yaml.safe_load(result.output_path.read_text())
        redumped = yaml.dump(doc)
        reloaded = yaml.safe_load(redumped)
        assert reloaded["spec"]["endpoints"][0]["interval"] == "15s"
        assert reloaded["metadata"]["labels"]["team"] == "cart"

    def test_metadata_name_has_monitor_suffix(self, tmp_path: Path):
        spec = {"type": "ServiceMonitor", "service_name": "frontend"}
        result = generate_service_monitor(spec, {}, tmp_path)
        doc = yaml.safe_load(result.output_path.read_text())
        assert doc["metadata"]["name"] == "frontend-monitor"


# ── Integration: all 11 Online Boutique services ───────────────────
ONLINE_BOUTIQUE_SERVICES = [
    "adservice",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "frontend",
    "loadgenerator",
    "paymentservice",
    "productcatalogservice",
    "recommendationservice",
    "shippingservice",
]


class TestAllServices:
    def test_all_11_services_generate(self, tmp_path: Path):
        results = []
        for svc in ONLINE_BOUTIQUE_SERVICES:
            spec = {"type": "ServiceMonitor", "service_name": svc}
            results.append(generate_service_monitor(spec, {}, tmp_path))

        assert all(r.status == GenerationStatus.CREATED for r in results)
        sm_dir = tmp_path / "service-monitors"
        assert len(list(sm_dir.glob("*.yaml"))) == 11

    def test_all_11_produce_valid_yaml(self, tmp_path: Path):
        for svc in ONLINE_BOUTIQUE_SERVICES:
            spec = {"type": "ServiceMonitor", "service_name": svc}
            result = generate_service_monitor(spec, {}, tmp_path)
            doc = yaml.safe_load(result.output_path.read_text())
            assert doc["kind"] == "ServiceMonitor"
            assert doc["metadata"]["name"] == f"{svc}-monitor"


# ── GenerationResult.ok property ───────────────────────────────────
class TestGenerationResultOk:
    def test_created_is_ok(self):
        r = GenerationResult("X", "x", GenerationStatus.CREATED)
        assert r.ok is True

    def test_skipped_is_ok(self):
        r = GenerationResult("X", "x", GenerationStatus.SKIPPED)
        assert r.ok is True

    def test_dry_run_is_ok(self):
        r = GenerationResult("X", "x", GenerationStatus.DRY_RUN)
        assert r.ok is True

    def test_failed_is_not_ok(self):
        r = GenerationResult("X", "x", GenerationStatus.FAILED, error="boom")
        assert r.ok is False