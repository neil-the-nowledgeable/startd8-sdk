"""Tests for ServiceMonitor artifact generation.

This module contains the TestServiceMonitorGenerator class, which validates
ServiceMonitor YAML output correctness, parameter handling, and conformance
to the registry-based generator architecture.

All ServiceMonitor tests are encapsulated in a single class to support the
shared test file convention (tests/test_artifact_generators.py) used across
all 7 generator types.
"""

import pytest
import yaml
from pathlib import Path

from contextcore.generators import generate_service_monitor
from contextcore.generators import GenerationResult
from tests.conftest import ONLINE_BOUTIQUE_SERVICES


class TestServiceMonitorGenerator:
    """Tests for ServiceMonitor artifact generation.

    Validates:
    - YAML structural correctness (apiVersion, kind, metadata, spec)
    - Parameter handling (labels, selectors, endpoints, all services)
    - GenerationResult contract (type, fields, naming, derivation rules)
    - Error isolation (failures return GenerationResult, never raise)
    - Force-overwrite gating and options handling
    """

    # -- Fixtures scoped to this class --

    @pytest.fixture
    def sample_artifact_spec(self):
        """Sample artifact specification for cartservice ServiceMonitor."""
        return {
            "artifact_type": "ServiceMonitor",
            "service_name": "cartservice",
            "namespace": "online-boutique",
            "port": "grpc",
            "port_number": 7070,
            "interval": "30s",
            "path": "/metrics",
            "labels": {
                "app": "cartservice",
                "team": "cart-team",
            },
            "derivation_rules": {
                "interval": "manifest.sli.latency.collection_interval",
                "port": "manifest.service.ports[0].name",
            },
        }

    @pytest.fixture
    def sample_context_manifest(self, base_context_manifest):
        """Delegates to the shared conftest factory with default (cartservice) data."""
        return base_context_manifest()

    @pytest.fixture
    def generation_options(self):
        """Operational options separate from artifact specification.

        Returns default options with force=False.
        """
        return {"force": False}

    @pytest.fixture
    def output_dir(self, tmp_path):
        """Temporary output directory for generated artifacts."""
        return tmp_path / "generated"

    # -- 1. YAML Validation (structural correctness) --

    def test_generates_valid_yaml(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Generated output must be parseable YAML."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        assert result.success is True

        content = result.output_path.read_text()
        parsed = yaml.safe_load(content)
        assert parsed is not None
        assert isinstance(parsed, dict)

    def test_yaml_has_correct_api_version_and_kind(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Generated YAML must have correct apiVersion and kind for ServiceMonitor CRD."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        parsed = yaml.safe_load(result.output_path.read_text())

        assert parsed["apiVersion"] == "monitoring.coreos.com/v1"
        assert parsed["kind"] == "ServiceMonitor"

    def test_yaml_metadata_matches_spec(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Generated YAML metadata must match the artifact spec values."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        parsed = yaml.safe_load(result.output_path.read_text())

        assert parsed["metadata"]["name"] == "cartservice-monitor"
        assert parsed["metadata"]["namespace"] == "online-boutique"

    def test_yaml_endpoints_match_spec(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Generated YAML endpoints must match the artifact spec configuration."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        parsed = yaml.safe_load(result.output_path.read_text())

        endpoints = parsed["spec"]["endpoints"]
        assert len(endpoints) == 1
        assert endpoints[0]["port"] == "grpc"
        assert endpoints[0]["interval"] == "30s"
        assert endpoints[0]["path"] == "/metrics"

    def test_label_values_are_quoted_in_raw_output(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Verify that label values are quoted in the raw YAML for Kubernetes compatibility.

        The template renders values with quotes ("{{ value }}") to ensure
        Kubernetes treats them as strings regardless of content.
        """
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        raw_content = result.output_path.read_text()

        # Template renders values as "value" — verify quoting in the raw file
        assert '"cartservice"' in raw_content or "'cartservice'" in raw_content
        assert '"cart-team"' in raw_content or "'cart-team'" in raw_content

    # -- 2. Parameter Handling --

    def test_labels_are_included_in_metadata(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Labels from artifact spec must appear in generated metadata."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        parsed = yaml.safe_load(result.output_path.read_text())

        labels = parsed["metadata"]["labels"]
        assert labels["app"] == "cartservice"
        assert labels["team"] == "cart-team"

    def test_missing_labels_generates_without_labels_block(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """When labels is absent from artifact_spec, the output omits the labels block."""
        output_dir.mkdir(parents=True)
        del sample_artifact_spec["labels"]
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        assert result.success is True

        parsed = yaml.safe_load(result.output_path.read_text())
        # labels key should be absent from metadata (or present but empty — either is acceptable)
        assert parsed["metadata"].get("labels") in (None, {})

    def test_empty_labels_generates_without_labels_block(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """When labels is an empty dict, the output omits the labels block."""
        output_dir.mkdir(parents=True)
        sample_artifact_spec["labels"] = {}
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        assert result.success is True

        parsed = yaml.safe_load(result.output_path.read_text())
        assert parsed["metadata"].get("labels") in (None, {})

    def test_selector_matches_service_name(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Generated selector matchLabels must use the service name."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        parsed = yaml.safe_load(result.output_path.read_text())

        match_labels = parsed["spec"]["selector"]["matchLabels"]
        assert match_labels["app"] == "cartservice"

    @pytest.mark.parametrize("service_name", list(ONLINE_BOUTIQUE_SERVICES.keys()))
    def test_all_online_boutique_services(self, service_name, sample_artifact_spec, base_context_manifest, output_dir):
        """Verify generation works for all 11 Online Boutique services.

        Each parametrized case injects a matching context_manifest entry so that
        derivation rules can resolve against a valid manifest.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        sample_artifact_spec["service_name"] = service_name
        sample_artifact_spec["port"] = ONLINE_BOUTIQUE_SERVICES[service_name]["ports"][0]["name"]

        context_manifest = base_context_manifest(
            services={service_name: ONLINE_BOUTIQUE_SERVICES[service_name]}
        )

        result = generate_service_monitor(sample_artifact_spec, context_manifest, output_dir)
        assert result.success is True
        assert result.artifact_type == "ServiceMonitor"
        assert result.service_name == service_name

    # -- 3. GenerationResult Contract --

    def test_result_type_and_fields(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """GenerationResult must have correct type and all expected fields populated."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)

        assert isinstance(result, GenerationResult)
        assert result.artifact_type == "ServiceMonitor"
        assert result.service_name == "cartservice"
        assert result.success is True
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.error is None
        assert result.skipped is False

    def test_output_file_naming_convention(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Output file must follow the {service_name}-monitor.yaml naming convention."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        assert result.success is True
        assert result.output_path.name == "cartservice-monitor.yaml"
        assert result.output_path.parent == output_dir

    @pytest.mark.parametrize("service_name", ["frontend", "redis-cart", "productcatalogservice"])
    def test_output_file_naming_for_various_services(self, service_name, sample_artifact_spec, base_context_manifest, output_dir):
        """Naming convention holds for different service names, including hyphenated ones."""
        output_dir.mkdir(parents=True, exist_ok=True)
        sample_artifact_spec["service_name"] = service_name
        context_manifest = base_context_manifest(
            services={service_name: ONLINE_BOUTIQUE_SERVICES[service_name]}
        )
        result = generate_service_monitor(sample_artifact_spec, context_manifest, output_dir)
        assert result.success is True
        assert result.output_path.name == f"{service_name}-monitor.yaml"

    def test_derivation_rules_present_in_result(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Every generated artifact with derivation_rules in spec must include resolved tracing in result.

        The generator copies derivation_rules from artifact_spec and resolves each
        manifest path reference against context_manifest. The result contains the
        rule and its resolved value.
        """
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        assert result.derivation_rules is not None
        assert len(result.derivation_rules) > 0
        assert "interval" in result.derivation_rules
        # Verify structure: each entry contains the rule and resolved value
        assert "rule" in result.derivation_rules["interval"]
        assert "resolved_value" in result.derivation_rules["interval"]
        assert result.derivation_rules["interval"]["resolved_value"] == "30s"

    def test_no_derivation_rules_in_spec_yields_empty_in_result(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """When artifact_spec has no derivation_rules, result.derivation_rules is empty."""
        output_dir.mkdir(parents=True)
        del sample_artifact_spec["derivation_rules"]
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        assert result.success is True
        assert result.derivation_rules == {}

    # -- 4. Error/Edge Cases --

    def test_invalid_spec_returns_failure_not_exception(self, sample_context_manifest, output_dir):
        """Per-artifact errors must not raise — they return GenerationResult with success=False.

        This validates the per-artifact failure isolation requirement: a bad spec
        for one artifact must not abort the entire generation run.
        """
        bad_spec = {"artifact_type": "ServiceMonitor"}  # missing required fields
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(bad_spec, sample_context_manifest, output_dir)
        assert isinstance(result, GenerationResult)
        assert result.success is False
        assert result.error is not None

    def test_existing_file_without_force_is_skipped(self, sample_artifact_spec, sample_context_manifest, output_dir, generation_options):
        """Existing file without force=True must be skipped, preserving original content."""
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "cartservice-monitor.yaml"
        existing_file.write_text("existing content")

        result = generate_service_monitor(
            sample_artifact_spec, sample_context_manifest, output_dir, options=generation_options
        )
        assert result.skipped is True
        assert result.success is False
        assert existing_file.read_text() == "existing content"  # unchanged

    def test_existing_file_with_force_is_overwritten(self, sample_artifact_spec, sample_context_manifest, output_dir, generation_options):
        """Existing file with force=True must be overwritten with new content."""
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "cartservice-monitor.yaml"
        existing_file.write_text("existing content")

        generation_options["force"] = True
        result = generate_service_monitor(
            sample_artifact_spec, sample_context_manifest, output_dir, options=generation_options
        )
        assert result.success is True
        assert existing_file.read_text() != "existing content"

    def test_output_dir_created_if_missing(self, sample_artifact_spec, sample_context_manifest, tmp_path):
        """Non-existent output directory (including nested paths) must be created automatically."""
        non_existent = tmp_path / "deep" / "nested" / "dir"
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, non_existent)
        assert result.success is True
        assert non_existent.exists()

    def test_none_context_manifest_returns_failure(self, sample_artifact_spec, output_dir):
        """context_manifest=None is invalid — the contract requires a dict."""
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, None, output_dir)
        assert result.success is False
        assert result.error is not None
        assert "context_manifest" in result.error.lower() or "manifest" in result.error.lower()

    def test_empty_context_manifest_with_derivation_rules_returns_failure(self, sample_artifact_spec, output_dir):
        """An empty manifest fails when derivation_rules reference manifest paths.

        The sample_artifact_spec includes derivation_rules that reference manifest
        paths (e.g., 'manifest.sli.latency.collection_interval'). With an empty
        manifest, these cannot be resolved, so the generator returns failure.
        """
        output_dir.mkdir(parents=True)
        result = generate_service_monitor(sample_artifact_spec, {}, output_dir)
        assert result.success is False
        assert result.error is not None

    def test_empty_context_manifest_without_derivation_rules_succeeds(self, sample_artifact_spec, output_dir):
        """An empty manifest is acceptable when no derivation_rules reference it.

        Template rendering uses only artifact_spec fields, so the manifest is not
        required for the rendering step itself.
        """
        output_dir.mkdir(parents=True)
        del sample_artifact_spec["derivation_rules"]
        result = generate_service_monitor(sample_artifact_spec, {}, output_dir)
        assert result.success is True

    def test_idempotent_generation_with_force(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """Calling the generator twice with force=True produces identical output."""
        output_dir.mkdir(parents=True)
        options = {"force": True}

        result1 = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir, options=options)
        content1 = result1.output_path.read_text()

        result2 = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir, options=options)
        content2 = result2.output_path.read_text()

        assert result1.success is True
        assert result2.success is True
        assert content1 == content2

    # -- 5. Options Handling --

    def test_default_options_no_force(self, sample_artifact_spec, sample_context_manifest, output_dir):
        """When options is None (default), force defaults to False and existing files are skipped."""
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "cartservice-monitor.yaml"
        existing_file.write_text("existing content")

        # options=None (default)
        result = generate_service_monitor(sample_artifact_spec, sample_context_manifest, output_dir)
        assert result.skipped is True
        assert existing_file.read_text() == "existing content"