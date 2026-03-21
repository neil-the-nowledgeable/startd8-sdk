"""Tests for complexity routing config parsing, CLI overrides, and classifier wiring."""

from __future__ import annotations

import types
from typing import Any

import pytest

from startd8.complexity.models import ComplexityRoutingConfig, TaskComplexitySignals
from startd8.contractors.prime_contractor_config import (
    PrimeContractorConfig,
    _parse_config,
    apply_cli_overrides,
)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

class TestComplexityRoutingConfigDefaults:
    """ComplexityRoutingConfig has correct defaults for all threshold fields."""

    def test_defaults(self) -> None:
        cfg = ComplexityRoutingConfig()
        assert cfg.blast_radius_complex_threshold == 5
        assert cfg.loc_simple_max == 150
        assert cfg.loc_complex_min == 500
        assert cfg.caller_count_complex_threshold == 3
        assert cfg.mro_depth_complex_threshold == 3
        assert cfg.unresolved_calls_complex_threshold == 2
        assert cfg.non_python_trivial_loc_max == 100
        assert cfg.non_python_simple_loc_max == 300


# ---------------------------------------------------------------------------
# Config file parsing
# ---------------------------------------------------------------------------

class TestConfigFileParsing:
    """Config file with complexity_routing section parses all thresholds."""

    def test_full_section_parsed(self) -> None:
        raw: dict[str, Any] = {
            "complexity_routing": {
                "enabled": True,
                "blast_radius_complex_threshold": 10,
                "loc_simple_max": 200,
                "loc_complex_min": 800,
                "caller_count_complex_threshold": 5,
                "mro_depth_complex_threshold": 4,
                "unresolved_calls_complex_threshold": 3,
                "non_python_trivial_loc_max": 50,
                "non_python_simple_loc_max": 150,
            }
        }
        config = _parse_config(raw)
        assert config.complexity_routing_enabled is True
        assert config.complexity_config is not None
        assert config.complexity_config.blast_radius_complex_threshold == 10
        assert config.complexity_config.loc_simple_max == 200
        assert config.complexity_config.loc_complex_min == 800
        assert config.complexity_config.caller_count_complex_threshold == 5
        assert config.complexity_config.mro_depth_complex_threshold == 4
        assert config.complexity_config.unresolved_calls_complex_threshold == 3
        assert config.complexity_config.non_python_trivial_loc_max == 50
        assert config.complexity_config.non_python_simple_loc_max == 150

    def test_partial_section_merges_with_defaults(self) -> None:
        """Only some thresholds provided — rest use defaults."""
        raw: dict[str, Any] = {
            "complexity_routing": {
                "enabled": True,
                "loc_simple_max": 250,
            }
        }
        config = _parse_config(raw)
        assert config.complexity_config is not None
        assert config.complexity_config.loc_simple_max == 250
        # Other fields use defaults
        assert config.complexity_config.blast_radius_complex_threshold == 5
        assert config.complexity_config.loc_complex_min == 500

    def test_empty_section_no_config(self) -> None:
        """Empty complexity_routing section produces no config object."""
        raw: dict[str, Any] = {
            "complexity_routing": {"enabled": True}
        }
        config = _parse_config(raw)
        assert config.complexity_routing_enabled is True
        assert config.complexity_config is None

    def test_missing_section_defaults(self) -> None:
        """No complexity_routing section at all."""
        config = _parse_config({})
        assert config.complexity_routing_enabled is False
        assert config.complexity_config is None

    def test_unknown_keys_ignored(self) -> None:
        """Unknown keys in the section are silently ignored."""
        raw: dict[str, Any] = {
            "complexity_routing": {
                "enabled": True,
                "loc_simple_max": 200,
                "unknown_field": 999,
            }
        }
        config = _parse_config(raw)
        assert config.complexity_config is not None
        assert config.complexity_config.loc_simple_max == 200


# ---------------------------------------------------------------------------
# CLI overrides
# ---------------------------------------------------------------------------

def _make_args(**kwargs: Any) -> types.SimpleNamespace:
    """Build a minimal argparse-like namespace."""
    defaults = {
        "complexity_routing": False,
        "tier3_agent": None,
        "complexity_loc_simple_max": None,
        "complexity_loc_complex_min": None,
        "complexity_blast_radius_complex_threshold": None,
        "complexity_non_python_trivial_loc_max": None,
        "complexity_non_python_simple_loc_max": None,
        # Other required attrs
        "micro_prime": False,
        "no_micro_prime": False,
        "micro_prime_dry_run": False,
        "no_repair": False,
        "strict_validation": False,
        "validate": False,
        "no_validate": False,
        "lead_agent": None,
        "drafter_agent": None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class TestCLIOverrides:
    """CLI overrides for complexity thresholds."""

    def test_loc_simple_max_override(self) -> None:
        config = PrimeContractorConfig()
        args = _make_args(complexity_loc_simple_max=300)
        apply_cli_overrides(config, args)
        assert config.complexity_config is not None
        assert config.complexity_config.loc_simple_max == 300

    def test_loc_complex_min_override(self) -> None:
        config = PrimeContractorConfig()
        args = _make_args(complexity_loc_complex_min=1000)
        apply_cli_overrides(config, args)
        assert config.complexity_config is not None
        assert config.complexity_config.loc_complex_min == 1000

    def test_blast_radius_override(self) -> None:
        config = PrimeContractorConfig()
        args = _make_args(complexity_blast_radius_complex_threshold=10)
        apply_cli_overrides(config, args)
        assert config.complexity_config is not None
        assert config.complexity_config.blast_radius_complex_threshold == 10

    def test_non_python_trivial_override(self) -> None:
        config = PrimeContractorConfig()
        args = _make_args(complexity_non_python_trivial_loc_max=50)
        apply_cli_overrides(config, args)
        assert config.complexity_config is not None
        assert config.complexity_config.non_python_trivial_loc_max == 50

    def test_non_python_simple_override(self) -> None:
        config = PrimeContractorConfig()
        args = _make_args(complexity_non_python_simple_loc_max=500)
        apply_cli_overrides(config, args)
        assert config.complexity_config is not None
        assert config.complexity_config.non_python_simple_loc_max == 500

    def test_cli_overrides_existing_config(self) -> None:
        """CLI overrides a value already set from config file."""
        raw: dict[str, Any] = {
            "complexity_routing": {
                "enabled": True,
                "loc_simple_max": 200,
                "blast_radius_complex_threshold": 7,
            }
        }
        config = _parse_config(raw)
        args = _make_args(complexity_loc_simple_max=400)
        apply_cli_overrides(config, args)
        # CLI wins
        assert config.complexity_config.loc_simple_max == 400
        # File value preserved
        assert config.complexity_config.blast_radius_complex_threshold == 7

    def test_none_cli_values_no_effect(self) -> None:
        """None CLI values don't create a complexity_config."""
        config = PrimeContractorConfig()
        args = _make_args()
        apply_cli_overrides(config, args)
        assert config.complexity_config is None

    def test_raw_dict_stays_in_sync(self) -> None:
        """CLI override also updates the raw dict for backward compat."""
        config = PrimeContractorConfig()
        args = _make_args(complexity_loc_simple_max=300)
        apply_cli_overrides(config, args)
        assert config.complexity_routing["loc_simple_max"] == 300


# ---------------------------------------------------------------------------
# Classifier wiring — config thresholds change routing
# ---------------------------------------------------------------------------

class TestClassifierUsesConfig:
    """Classifier uses config thresholds instead of hardcoded values."""

    def test_custom_loc_simple_max_changes_routing(self) -> None:
        """A task with 180 LOC is SIMPLE with raised threshold, COMPLEX with default."""
        from startd8.complexity.classifier import classify_tier

        signals = TaskComplexitySignals(
            estimated_loc=180,
            edit_mode="create",
            manifest_coverage="full",
            target_file_count=1,
        )
        # Default (loc_simple_max=150) -> not SIMPLE
        result_default = classify_tier(signals)
        assert result_default.tier != "simple"

        # Raised threshold -> SIMPLE
        cfg = ComplexityRoutingConfig(loc_simple_max=200)
        result_custom = classify_tier(signals, config=cfg)
        assert result_custom.tier == "simple"

    def test_custom_blast_radius_threshold(self) -> None:
        """Blast radius 7 is COMPLEX with default (5), not with raised (10)."""
        from startd8.complexity.classifier import classify_tier

        signals = TaskComplexitySignals(
            blast_radius=7,
            estimated_loc=100,
            edit_mode="create",
            manifest_coverage="full",
            target_file_count=1,
        )
        # Default (threshold=5) -> COMPLEX
        result_default = classify_tier(signals)
        assert result_default.tier == "complex"
        assert "blast_radius" in result_default.reason

        # Raised threshold (10) -> no blast_radius trigger
        cfg = ComplexityRoutingConfig(blast_radius_complex_threshold=10)
        result_custom = classify_tier(signals, config=cfg)
        assert "blast_radius" not in result_custom.reason

    def test_custom_non_python_trivial_threshold(self) -> None:
        """Non-Python file with 80 LOC: TRIVIAL at default, not at threshold=50."""
        from startd8.complexity.classifier import classify_tier

        signals = TaskComplexitySignals(
            estimated_loc=80,
            file_extension=".html",
        )
        # Default (non_python_trivial_loc_max=100) -> TRIVIAL
        result_default = classify_tier(signals)
        assert result_default.tier == "trivial"

        # Lowered threshold (50) -> not TRIVIAL (should be SIMPLE)
        cfg = ComplexityRoutingConfig(non_python_trivial_loc_max=50)
        result_custom = classify_tier(signals, config=cfg)
        assert result_custom.tier == "simple"
