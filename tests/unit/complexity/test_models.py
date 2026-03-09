"""Tests for complexity.models — enums, signals, and config."""

import pytest

from startd8.complexity.models import (
    ComplexityRoutingConfig,
    ComplexityTier,
    TaskComplexitySignals,
)


# ── ComplexityTier enum ──────────────────────────────────────────────


class TestComplexityTier:
    def test_values(self):
        assert ComplexityTier.TRIVIAL.value == "trivial"
        assert ComplexityTier.SIMPLE.value == "simple"
        assert ComplexityTier.MODERATE.value == "moderate"
        assert ComplexityTier.COMPLEX.value == "complex"

    def test_str_enum(self):
        assert isinstance(ComplexityTier.SIMPLE, str)
        assert ComplexityTier.SIMPLE == "simple"

    def test_from_artisan_tier_1(self):
        assert ComplexityTier.from_artisan_tier("tier_1") is ComplexityTier.SIMPLE

    def test_from_artisan_tier_2(self):
        assert ComplexityTier.from_artisan_tier("tier_2") is ComplexityTier.MODERATE

    def test_from_artisan_tier_3(self):
        assert ComplexityTier.from_artisan_tier("tier_3") is ComplexityTier.COMPLEX

    def test_from_artisan_tier_unknown(self):
        with pytest.raises(ValueError, match="Unknown Artisan tier"):
            ComplexityTier.from_artisan_tier("tier_99")


# ── TaskComplexitySignals ────────────────────────────────────────────


class TestTaskComplexitySignals:
    def test_defaults(self):
        signals = TaskComplexitySignals()
        assert signals.blast_radius == 0
        assert signals.caller_count == 0
        assert signals.has_dynamic_dispatch is False
        assert signals.is_closure is False
        assert signals.estimated_loc == 0
        assert signals.target_file_count == 1
        assert signals.edit_mode == "unknown"
        assert signals.mro_depth == 0
        assert signals.unresolved_call_count == 0
        assert signals.has_cross_file_edges is False
        assert signals.manifest_coverage == "none"

    def test_frozen(self):
        signals = TaskComplexitySignals()
        with pytest.raises(AttributeError):
            signals.blast_radius = 10  # type: ignore[misc]

    def test_to_dict(self):
        signals = TaskComplexitySignals(blast_radius=3, edit_mode="edit")
        d = signals.to_dict()
        assert isinstance(d, dict)
        assert d["blast_radius"] == 3
        assert d["edit_mode"] == "edit"
        assert d["caller_count"] == 0  # default preserved

    def test_to_dict_contains_all_fields(self):
        signals = TaskComplexitySignals()
        d = signals.to_dict()
        assert len(d) == 12


# ── ComplexityRoutingConfig ──────────────────────────────────────────


class TestComplexityRoutingConfig:
    def test_defaults(self):
        cfg = ComplexityRoutingConfig()
        assert cfg.enabled is True
        assert cfg.blast_radius_complex_threshold == 5
        assert cfg.loc_simple_max == 150
        assert cfg.loc_complex_min == 500
        assert cfg.caller_count_complex_threshold == 3
        assert cfg.mro_depth_complex_threshold == 3
        assert cfg.unresolved_calls_complex_threshold == 2
        assert cfg.templates_enabled is True

    def test_from_handler_config(self):
        """Duck-typed attribute access from an Artisan HandlerConfig-like object."""

        class FakeConfig:
            complexity_routing_enabled = True
            complexity_blast_radius_tier3 = 8
            complexity_loc_tier1_max = 200
            complexity_loc_tier3_min = 600
            complexity_caller_tier3 = 5

        cfg = ComplexityRoutingConfig.from_handler_config(FakeConfig())
        assert cfg.enabled is True
        assert cfg.blast_radius_complex_threshold == 8
        assert cfg.loc_simple_max == 200
        assert cfg.loc_complex_min == 600
        assert cfg.caller_count_complex_threshold == 5

    def test_from_handler_config_missing_attrs_uses_defaults(self):
        """Missing attributes fall back to defaults."""

        class MinimalConfig:
            pass

        cfg = ComplexityRoutingConfig.from_handler_config(MinimalConfig())
        assert cfg.enabled is True
        assert cfg.blast_radius_complex_threshold == 5
        assert cfg.loc_simple_max == 150
