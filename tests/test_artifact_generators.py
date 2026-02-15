"""Tests for artifact generation.

This module contains test classes for each generator type:
- TestServiceMonitorGenerator (F-009)
- TestPrometheusRuleGenerator (F-010)

All generator tests are encapsulated in classes to support the
shared test file convention (tests/test_artifact_generators.py) used across
all generator types. Shared fixtures live in tests/conftest.py to prevent
redefinition conflicts across features.
"""

import copy

import pytest
import yaml
from pathlib import Path

from contextcore.generators import generate_service_monitor
from contextcore.generators import generate_prometheus_rule
from contextcore.generators import GenerationResult
from contextcore.generators import registry


# ═══════════════════════════════════════════════════════════════════
# TestServiceMonitorGenerator (F-009)
# ═══════════════════════════════════════════════════════════════════


class TestServiceMonitorGenerator:
    """Tests for ServiceMonitor artifact generation (F-009).

    Preserved from the original file for backward compatibility.
    Additional ServiceMonitor tests can be added here as needed.
    """

    def test_service_monitor_generation_succeeds(
        self, sample_context_manifest, output_dir
    ):
        """ServiceMonitor generation returns success."""
        spec = {
            "artifact_type": "ServiceMonitor",
            "service": "cartservice",
            "namespace": "default",
        }
        result = generate_service_monitor(spec, sample_context_manifest, output_dir)
        assert isinstance(result, GenerationResult)
        assert result.artifact_type == "ServiceMonitor"
        assert result.success is True


# ═══════════════════════════════════════════════════════════════════
# PrometheusRule-specific fixtures (module-level, prefixed)
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def prom_rule_artifact_spec():
    """Standard PrometheusRule artifact spec for cartservice.

    Contains two rules:
    - CartServiceHighErrorRate: critical severity, threshold derived from SLO availability
    - CartServiceHighLatency: warning severity, threshold derived from SLO latency_p99_ms

    Each rule includes derivation_rules metadata tracing values back to manifest fields.
    """
    return {
        "artifact_type": "PrometheusRule",
        "service": "cartservice",
        "name": "cartservice-alerts",
        "rules": [
            {
                "alert": "CartServiceHighErrorRate",
                "severity": "critical",
                "threshold": 0.001,  # 0.1% error rate → derived from 99.9% availability
                "expr_template": "error_rate",
                "for": "5m",
                "derivation_rules": {
                    "threshold": "1 - services.cartservice.slo.availability / 100",
                    "severity": "services.cartservice.tier",
                },
            },
            {
                "alert": "CartServiceHighLatency",
                "severity": "warning",
                "threshold": 200,
                "expr_template": "latency_p99",
                "for": "10m",
                "derivation_rules": {
                    "threshold": "services.cartservice.slo.latency_p99_ms",
                    "severity": "downgraded from tier due to latency-type alert",
                },
            },
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# TestPrometheusRuleGenerator (F-010)
# ═══════════════════════════════════════════════════════════════════


class TestPrometheusRuleGenerator:
    """Tests for PrometheusRule artifact generation (F-010).

    Validates:
    - Generator signature conformance (returns GenerationResult)
    - Severity validation (critical, warning, info only)
    - Threshold validation (non-negative numeric values)
    - Duration format validation (Prometheus duration strings)
    - Derivation rules tracing in annotations
    - Output YAML structure (PrometheusRule CRD)
    - Output file path convention ({output_dir}/prometheus-rules/{name}.yaml)
    - Edge cases (empty rules, duplicate alerts)
    - Per-artifact error isolation (no exceptions raised)
    - Output directory auto-creation
    - Overwrite protection (force=True required)
    - Registry integration
    """

    # ── Static helper methods (class-scoped to avoid naming collisions) ──

    @staticmethod
    def _with_severity(spec: dict, severity, rule_index: int = 0) -> dict:
        """Return a deep copy of spec with modified severity on the specified rule.

        Args:
            spec: The artifact specification dict.
            severity: The new severity value to set.
            rule_index: Index of the rule to modify (default 0, the first rule).

        Returns:
            A new dict with the specified rule's severity updated.
        """
        s = copy.deepcopy(spec)
        s["rules"][rule_index]["severity"] = severity
        return s

    @staticmethod
    def _with_threshold(spec: dict, rule_index: int, threshold) -> dict:
        """Return a deep copy of spec with modified threshold on the specified rule.

        Args:
            spec: The artifact specification dict.
            rule_index: Index of the rule to modify.
            threshold: The new threshold value to set.

        Returns:
            A new dict with the specified rule's threshold updated.
        """
        s = copy.deepcopy(spec)
        s["rules"][rule_index]["threshold"] = threshold
        return s

    @staticmethod
    def _with_for_duration(spec: dict, rule_index: int, duration) -> dict:
        """Return a deep copy of spec with modified 'for' duration on the specified rule.

        Args:
            spec: The artifact specification dict.
            rule_index: Index of the rule to modify.
            duration: The new 'for' duration value to set.

        Returns:
            A new dict with the specified rule's 'for' duration updated.
        """
        s = copy.deepcopy(spec)
        s["rules"][rule_index]["for"] = duration
        return s

    # ── Signature & Contract Tests ──

    def test_returns_generation_result(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Generator returns a GenerationResult object with correct artifact metadata."""
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert isinstance(result, GenerationResult)
        assert result.artifact_type == "PrometheusRule"
        assert result.service == "cartservice"

    def test_successful_generation_creates_file(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Successful generation returns success=True and creates the output file."""
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result.success is True
        assert result.output_path is not None
        assert Path(result.output_path).exists()

    # ── Severity Validation Tests ──

    @pytest.mark.parametrize("severity", ["critical", "warning", "info"])
    def test_valid_severities_accepted(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir, severity
    ):
        """Valid severity levels (critical, warning, info) are accepted and rendered."""
        spec = self._with_severity(prom_rule_artifact_spec, severity)
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is True

        content = yaml.safe_load(Path(result.output_path).read_text())
        rule = content["spec"]["groups"][0]["rules"][0]
        assert rule["labels"]["severity"] == severity

    @pytest.mark.parametrize("bad_severity", ["CRITICAL", "fatal", "", None, 42])
    def test_invalid_severity_returns_failure(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir, bad_severity
    ):
        """Invalid severity values (uppercase, unknown, empty, None, non-string) are rejected."""
        spec = self._with_severity(prom_rule_artifact_spec, bad_severity)
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is False
        assert "severity" in result.error.lower()

    # ── Threshold Validation Tests ──

    def test_threshold_matches_manifest_slo(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Generated rules include thresholds derived from manifest SLO values.

        CartServiceHighErrorRate threshold 0.001 is derived from:
            1 - services.cartservice.slo.availability / 100 = 1 - 99.9/100 = 0.001

        CartServiceHighLatency threshold 200 is derived from:
            services.cartservice.slo.latency_p99_ms = 200
        """
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result.success is True
        content = yaml.safe_load(Path(result.output_path).read_text())
        rules = content["spec"]["groups"][0]["rules"]

        error_rate_rule = next(
            (r for r in rules if r["alert"] == "CartServiceHighErrorRate"), None
        )
        assert error_rate_rule is not None
        # Threshold 0.001 derived from 1 - 99.9/100
        assert error_rate_rule["expr"].rstrip().endswith("0.001") or \
               "> 0.001" in error_rate_rule["expr"]

        latency_rule = next(
            (r for r in rules if r["alert"] == "CartServiceHighLatency"), None
        )
        assert latency_rule is not None
        assert latency_rule["expr"].rstrip().endswith("200") or \
               "> 200" in latency_rule["expr"]

    @pytest.mark.parametrize("bad_threshold", [-1, -0.5, "not_a_number", None])
    def test_invalid_threshold_returns_failure(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir, bad_threshold
    ):
        """Invalid threshold values (negative, non-numeric, None) are rejected."""
        spec = self._with_threshold(prom_rule_artifact_spec, 0, bad_threshold)
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is False
        assert "threshold" in result.error.lower()

    def test_zero_threshold_accepted(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Zero is accepted as a valid threshold value (edge of valid range)."""
        spec = self._with_threshold(prom_rule_artifact_spec, 0, 0)
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is True

    # ── Derivation Rules Tracing Tests ──

    def test_derivation_rules_in_annotations(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Every generated rule includes a 'derivation_rules' annotation.

        This annotation traces the rule's threshold and severity back to
        manifest SLO and tier fields (project constraint [warning]).
        The annotation key is pinned to exactly 'derivation_rules' — no aliases.
        """
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result.success is True
        content = yaml.safe_load(Path(result.output_path).read_text())
        for rule in content["spec"]["groups"][0]["rules"]:
            annotations = rule.get("annotations", {})
            assert "derivation_rules" in annotations, (
                f"Rule '{rule['alert']}' missing 'derivation_rules' annotation key"
            )
            derivation = annotations["derivation_rules"]
            assert "threshold" in derivation

    # ── Output YAML Structure Tests ──

    def test_generated_yaml_is_valid_prometheus_rule(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Generated YAML conforms to the PrometheusRule CRD specification.

        Validates: apiVersion, kind, spec.groups structure, and that each
        rule contains alert, expr, labels, and severity fields.
        """
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        content = yaml.safe_load(Path(result.output_path).read_text())
        assert content["apiVersion"] == "monitoring.coreos.com/v1"
        assert content["kind"] == "PrometheusRule"
        assert "groups" in content["spec"]
        for group in content["spec"]["groups"]:
            assert "name" in group
            assert "rules" in group
            for rule in group["rules"]:
                assert "alert" in rule
                assert "expr" in rule
                assert "labels" in rule
                assert "severity" in rule["labels"]

    def test_output_file_path_convention(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Output file follows the predictable path convention.

        Expected: {output_dir}/prometheus-rules/{name}.yaml
        This allows the 77-artifact generation pipeline to locate files reliably.
        """
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result.success is True
        output_path = Path(result.output_path)
        assert output_path.parent.name == "prometheus-rules"
        assert output_path.parent.parent == Path(output_dir)
        assert output_path.name == "cartservice-alerts.yaml"

    # ── Duration Format Validation Tests ──

    @pytest.mark.parametrize("valid_duration", ["5m", "10m", "1h", "30s", "1h30m"])
    def test_valid_for_durations_accepted(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir, valid_duration
    ):
        """Valid Prometheus duration formats are accepted."""
        spec = self._with_for_duration(prom_rule_artifact_spec, 0, valid_duration)
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is True

    @pytest.mark.parametrize("bad_duration", ["5x", "-5m", "", "forever", None, 300])
    def test_invalid_for_duration_returns_failure(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir, bad_duration
    ):
        """Invalid duration formats are rejected with descriptive error messages."""
        spec = self._with_for_duration(prom_rule_artifact_spec, 0, bad_duration)
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is False
        assert "duration" in result.error.lower() or "for" in result.error.lower()

    # ── Edge Cases & Error Handling Tests ──

    def test_empty_rules_list_returns_failure(
        self, sample_context_manifest, output_dir
    ):
        """A PrometheusRule with an empty rules list is not meaningful and is rejected."""
        spec = {
            "artifact_type": "PrometheusRule",
            "service": "cartservice",
            "name": "cartservice-alerts",
            "rules": [],
        }
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is False
        assert "rules" in result.error.lower() or "empty" in result.error.lower()

    def test_duplicate_alert_names_returns_failure(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Duplicate alert names within the same spec are rejected.

        Duplicate names would produce ambiguous alerting configurations
        that are difficult to debug in production.
        """
        spec = copy.deepcopy(prom_rule_artifact_spec)
        spec["rules"][1]["alert"] = spec["rules"][0]["alert"]
        result = generate_prometheus_rule(spec, sample_context_manifest, output_dir)
        assert result.success is False
        assert "duplicate" in result.error.lower()

    def test_invalid_spec_does_not_raise(
        self, sample_context_manifest, output_dir
    ):
        """Per-artifact errors are isolated and do not raise exceptions.

        The generator returns a failure GenerationResult rather than
        raising, ensuring the pipeline can continue processing other
        artifacts (project constraint [blocking]).
        """
        bad_spec = {"artifact_type": "PrometheusRule", "service": "cartservice"}
        # Must NOT raise — returns a failed GenerationResult instead
        result = generate_prometheus_rule(bad_spec, sample_context_manifest, output_dir)
        assert result.success is False
        assert result.error is not None

    def test_missing_service_in_manifest_returns_failure(
        self, prom_rule_artifact_spec, output_dir
    ):
        """A service referenced in the spec but absent from the manifest causes failure."""
        empty_manifest = {"project": "test", "services": {}}
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, empty_manifest, output_dir
        )
        assert result.success is False

    # ── Output Directory Handling Tests ──

    def test_generator_creates_output_dir_if_missing(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """The generator creates the output directory (and parents) if missing.

        Rather than raising FileNotFoundError, the generator ensures
        the directory structure exists before writing the file.
        The output_dir fixture intentionally does NOT pre-create the directory.
        """
        assert not output_dir.exists(), "Precondition: output_dir should not exist yet"
        result = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result.success is True
        assert output_dir.exists()
        assert Path(result.output_path).exists()

    def test_unwritable_output_dir_returns_failure(
        self, prom_rule_artifact_spec, sample_context_manifest, tmp_path
    ):
        """Permission errors when creating or writing to output_dir are caught.

        The generator returns a failure GenerationResult rather than raising,
        maintaining per-artifact error isolation.
        """
        unwritable = tmp_path / "readonly"
        unwritable.mkdir()
        unwritable.chmod(0o444)
        try:
            result = generate_prometheus_rule(
                prom_rule_artifact_spec,
                sample_context_manifest,
                unwritable / "nested" / "output",
            )
            assert result.success is False
            assert result.error is not None
        finally:
            # Restore permissions for cleanup
            unwritable.chmod(0o755)

    # ── Overwrite Protection Tests ──

    def test_existing_file_without_force_returns_failure(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Attempting to overwrite an existing artifact without force=True fails.

        The generator checks for existing files and requires explicit
        force=True to overwrite (project constraint [warning]).
        """
        result1 = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result1.success is True

        # Generate again without force → should fail
        result2 = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result2.success is False
        assert "exist" in result2.error.lower() or "overwrite" in result2.error.lower()

    def test_existing_file_with_force_overwrites(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """With force=True, an existing artifact is overwritten successfully."""
        result1 = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        assert result1.success is True

        result2 = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir, force=True
        )
        assert result2.success is True

    def test_force_overwrite_is_idempotent(
        self, prom_rule_artifact_spec, sample_context_manifest, output_dir
    ):
        """Consecutive force=True generations produce identical file content.

        This validates that template rendering is deterministic and
        generation is idempotent — important for CI/CD pipelines where
        re-running generation should not produce diff noise.
        """
        generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir
        )
        result_a = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir, force=True
        )
        content_a = Path(result_a.output_path).read_text()

        result_b = generate_prometheus_rule(
            prom_rule_artifact_spec, sample_context_manifest, output_dir, force=True
        )
        content_b = Path(result_b.output_path).read_text()

        assert content_a == content_b, (
            "Deterministic rendering: consecutive generations must produce identical output"
        )

    # ── Registry Integration Tests ──

    def test_prometheus_rule_registered_in_registry(self):
        """The PrometheusRule generator is registered and discoverable via the registry.

        The generator must be accessible through the registry pattern
        for dynamic invocation by the artifact generation pipeline.
        """
        generator_fn = registry.get_generator("PrometheusRule")
        assert generator_fn is not None
        assert callable(generator_fn)