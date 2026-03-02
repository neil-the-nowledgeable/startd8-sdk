"""Tests for dashboard_creator.config_merge — config override + default hydration."""

import pytest

from startd8.dashboard_creator.config_merge import (
    get_default_config,
    hydrate_spec_defaults,
    merge_config_overrides,
)
from startd8.dashboard_creator.models import DashboardSpec, PanelSpec
from startd8.exceptions import ValidationError


def _minimal_spec(**kwargs):
    """Create a minimal valid DashboardSpec with overrides."""
    defaults = {
        "title": "Test",
        "panels": [{"type": "stat", "title": "Up", "expr": "up"}],
    }
    defaults.update(kwargs)
    return DashboardSpec(**defaults)


# ---------------------------------------------------------------------------
# merge_config_overrides
# ---------------------------------------------------------------------------


class TestMergeConfigOverrides:
    def test_deep_merge_leaf_override(self):
        base = get_default_config()
        overrides = {"metrics": {"responseTimeMs": "custom_metric"}}
        merged = merge_config_overrides(base, overrides)
        assert merged["metrics"]["responseTimeMs"] == "custom_metric"
        # Other metrics preserved
        assert merged["metrics"]["activeSessions"] == "startd8_active_sessions"

    def test_deep_merge_preserves_unmodified(self):
        base = get_default_config()
        overrides = {"dashboardRefresh": "10s"}
        merged = merge_config_overrides(base, overrides)
        assert merged["dashboardRefresh"] == "10s"
        assert merged["dashboardTimeFrom"] == "now-6h"  # Unchanged

    def test_unknown_key_raises_validation_error(self):
        base = get_default_config()
        with pytest.raises(ValidationError, match="Unknown config override"):
            merge_config_overrides(base, {"nonexistent_key": "value"})

    def test_list_values_replaced_not_concatenated(self):
        base = get_default_config()
        overrides = {"dashboardTags": ["custom-tag"]}
        merged = merge_config_overrides(base, overrides)
        assert merged["dashboardTags"] == ["custom-tag"]

    def test_empty_overrides_returns_copy(self):
        base = get_default_config()
        merged = merge_config_overrides(base, {})
        assert merged == base
        assert merged is not base  # Deep copy

    def test_nested_dict_override(self):
        base = get_default_config()
        overrides = {"datasources": {"mimir": {"uid": "custom-prom", "type": "prometheus"}}}
        merged = merge_config_overrides(base, overrides)
        assert merged["datasources"]["mimir"]["uid"] == "custom-prom"
        # Other datasources preserved
        assert merged["datasources"]["tempo"]["uid"] == "tempo"

    def test_does_not_mutate_base(self):
        base = get_default_config()
        original_refresh = base["dashboardRefresh"]
        merge_config_overrides(base, {"dashboardRefresh": "5s"})
        assert base["dashboardRefresh"] == original_refresh


# ---------------------------------------------------------------------------
# hydrate_spec_defaults
# ---------------------------------------------------------------------------


class TestHydrateSpecDefaults:
    def test_fills_refresh_from_config(self):
        spec = _minimal_spec(refresh=None)
        config = get_default_config()
        hydrated = hydrate_spec_defaults(spec, config)
        assert hydrated.refresh == "30s"

    def test_fills_timezone_to_browser(self):
        spec = _minimal_spec(timezone=None)
        config = get_default_config()
        hydrated = hydrate_spec_defaults(spec, config)
        assert hydrated.timezone == "browser"

    def test_fills_time_from(self):
        spec = _minimal_spec(time_from=None)
        config = get_default_config()
        hydrated = hydrate_spec_defaults(spec, config)
        assert hydrated.time_from == "now-6h"

    def test_fills_time_to(self):
        spec = _minimal_spec(time_to=None)
        config = get_default_config()
        hydrated = hydrate_spec_defaults(spec, config)
        assert hydrated.time_to == "now"

    def test_fills_datasources_from_config(self):
        spec = _minimal_spec(datasources={})
        config = get_default_config()
        hydrated = hydrate_spec_defaults(spec, config)
        assert "tempo" in hydrated.datasources
        assert "loki" in hydrated.datasources
        assert "mimir" in hydrated.datasources

    def test_does_not_overwrite_explicit_values(self):
        spec = _minimal_spec(refresh="10s", timezone="UTC")
        config = get_default_config()
        hydrated = hydrate_spec_defaults(spec, config)
        assert hydrated.refresh == "10s"
        assert hydrated.timezone == "UTC"

    def test_does_not_mutate_input(self):
        spec = _minimal_spec(refresh=None)
        config = get_default_config()
        hydrated = hydrate_spec_defaults(spec, config)
        assert spec.refresh is None
        assert hydrated.refresh == "30s"
