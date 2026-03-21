"""Tests for P0 config extraction into PrimeContractorConfig.

Validates that 7 hardcoded settings are now configurable via the config
system while preserving identical defaults (no behavior change).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from startd8.contractors.prime_contractor_config import (
    IntegrationConfig,
    PrimeContractorConfig,
    QualityGateConfig,
    _parse_config,
    load_prime_contractor_config,
)


class TestDefaultValues:
    """All 7 settings must have the same defaults as the old hardcoded constants."""

    def test_integration_size_regression_threshold_default(self):
        cfg = PrimeContractorConfig()
        assert cfg.integration.size_regression_threshold == 0.60

    def test_integration_min_lines_default(self):
        cfg = PrimeContractorConfig()
        assert cfg.integration.min_lines == 50

    def test_integration_element_retention_threshold_default(self):
        cfg = PrimeContractorConfig()
        assert cfg.integration.element_retention_threshold == 0.80

    def test_quality_gate_min_score_default(self):
        cfg = PrimeContractorConfig()
        assert cfg.quality_gate.min_score == 60

    def test_plan_load_max_bytes_default(self):
        cfg = PrimeContractorConfig()
        assert cfg.plan_load_max_bytes == 16_384

    def test_file_copy_timeout_s_default(self):
        cfg = PrimeContractorConfig()
        assert cfg.file_copy_timeout_s == 30

    def test_integration_config_defaults(self):
        ic = IntegrationConfig()
        assert ic.size_regression_threshold == 0.60
        assert ic.min_lines == 50
        assert ic.element_retention_threshold == 0.80

    def test_quality_gate_config_default(self):
        qg = QualityGateConfig()
        assert qg.min_score == 60


class TestConfigFileOverrides:
    """Config file values override defaults for each setting."""

    def test_override_integration_size_regression_threshold(self):
        raw = {"integration": {"size_regression_threshold": 0.75}}
        cfg = _parse_config(raw)
        assert cfg.integration.size_regression_threshold == 0.75

    def test_override_integration_min_lines(self):
        raw = {"integration": {"min_lines": 100}}
        cfg = _parse_config(raw)
        assert cfg.integration.min_lines == 100

    def test_override_integration_element_retention_threshold(self):
        raw = {"integration": {"element_retention_threshold": 0.90}}
        cfg = _parse_config(raw)
        assert cfg.integration.element_retention_threshold == 0.90

    def test_override_quality_gate_min_score(self):
        raw = {"quality_gate": {"min_score": 80}}
        cfg = _parse_config(raw)
        assert cfg.quality_gate.min_score == 80

    def test_override_plan_load_max_bytes(self):
        raw = {"plan_load_max_bytes": 32_768}
        cfg = _parse_config(raw)
        assert cfg.plan_load_max_bytes == 32_768

    def test_override_file_copy_timeout_s(self):
        raw = {"file_copy_timeout_s": 60}
        cfg = _parse_config(raw)
        assert cfg.file_copy_timeout_s == 60


class TestEmptySections:
    """Empty or missing sections must not crash, and must use defaults."""

    def test_empty_integration_section(self):
        raw = {"integration": {}}
        cfg = _parse_config(raw)
        assert cfg.integration.size_regression_threshold == 0.60
        assert cfg.integration.min_lines == 50
        assert cfg.integration.element_retention_threshold == 0.80

    def test_empty_quality_gate_section(self):
        raw = {"quality_gate": {}}
        cfg = _parse_config(raw)
        assert cfg.quality_gate.min_score == 60

    def test_missing_sections_use_defaults(self):
        raw = {}
        cfg = _parse_config(raw)
        assert cfg.integration.size_regression_threshold == 0.60
        assert cfg.integration.min_lines == 50
        assert cfg.integration.element_retention_threshold == 0.80
        assert cfg.quality_gate.min_score == 60
        assert cfg.plan_load_max_bytes == 16_384
        assert cfg.file_copy_timeout_s == 30

    def test_non_dict_integration_ignored(self):
        raw = {"integration": "invalid"}
        cfg = _parse_config(raw)
        # Should use defaults since section is not a dict
        assert cfg.integration.size_regression_threshold == 0.60

    def test_non_dict_quality_gate_ignored(self):
        raw = {"quality_gate": 42}
        cfg = _parse_config(raw)
        assert cfg.quality_gate.min_score == 60


class TestPartialConfig:
    """Partial config (only some fields set) merges with defaults."""

    def test_partial_integration_config(self):
        raw = {"integration": {"min_lines": 200}}
        cfg = _parse_config(raw)
        assert cfg.integration.min_lines == 200
        # Other fields keep defaults
        assert cfg.integration.size_regression_threshold == 0.60
        assert cfg.integration.element_retention_threshold == 0.80

    def test_partial_with_top_level_and_section(self):
        raw = {
            "plan_load_max_bytes": 8192,
            "quality_gate": {"min_score": 70},
        }
        cfg = _parse_config(raw)
        assert cfg.plan_load_max_bytes == 8192
        assert cfg.quality_gate.min_score == 70
        # Unset fields keep defaults
        assert cfg.file_copy_timeout_s == 30
        assert cfg.integration.size_regression_threshold == 0.60


class TestMicroPrimeCircuitBreaker:
    """Circuit breaker fields on MicroPrimeConfig have correct defaults."""

    def test_circuit_breaker_per_file_default(self):
        from startd8.micro_prime.models import MicroPrimeConfig

        cfg = MicroPrimeConfig()
        assert cfg.circuit_breaker_per_file == 8

    def test_circuit_breaker_per_run_default(self):
        from startd8.micro_prime.models import MicroPrimeConfig

        cfg = MicroPrimeConfig()
        assert cfg.circuit_breaker_per_run == 12

    def test_circuit_breaker_custom_values(self):
        from startd8.micro_prime.models import MicroPrimeConfig

        cfg = MicroPrimeConfig(circuit_breaker_per_file=5, circuit_breaker_per_run=20)
        assert cfg.circuit_breaker_per_file == 5
        assert cfg.circuit_breaker_per_run == 20


class TestLoadFromFile:
    """Integration test: load config from a JSON file."""

    def test_load_full_config_file(self):
        config_data = {
            "integration": {
                "size_regression_threshold": 0.50,
                "min_lines": 75,
                "element_retention_threshold": 0.85,
            },
            "quality_gate": {"min_score": 75},
            "plan_load_max_bytes": 32768,
            "file_copy_timeout_s": 45,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            cfg = load_prime_contractor_config(config_path=f.name)

        assert cfg.integration.size_regression_threshold == 0.50
        assert cfg.integration.min_lines == 75
        assert cfg.integration.element_retention_threshold == 0.85
        assert cfg.quality_gate.min_score == 75
        assert cfg.plan_load_max_bytes == 32768
        assert cfg.file_copy_timeout_s == 45


class TestCLIOverrides:
    """CLI args override config file values."""

    def test_min_quality_score_override(self):
        from types import SimpleNamespace

        from startd8.contractors.prime_contractor_config import apply_cli_overrides

        cfg = PrimeContractorConfig()
        args = SimpleNamespace(min_quality_score=80)
        cfg = apply_cli_overrides(cfg, args)
        assert cfg.quality_gate.min_score == 80

    def test_plan_max_bytes_override(self):
        from types import SimpleNamespace

        from startd8.contractors.prime_contractor_config import apply_cli_overrides

        cfg = PrimeContractorConfig()
        args = SimpleNamespace(plan_max_bytes=8192)
        cfg = apply_cli_overrides(cfg, args)
        assert cfg.plan_load_max_bytes == 8192

    def test_none_cli_values_do_not_override(self):
        from types import SimpleNamespace

        from startd8.contractors.prime_contractor_config import apply_cli_overrides

        cfg = PrimeContractorConfig()
        cfg.quality_gate.min_score = 75
        args = SimpleNamespace(min_quality_score=None, plan_max_bytes=None)
        cfg = apply_cli_overrides(cfg, args)
        assert cfg.quality_gate.min_score == 75
        assert cfg.plan_load_max_bytes == 16_384
