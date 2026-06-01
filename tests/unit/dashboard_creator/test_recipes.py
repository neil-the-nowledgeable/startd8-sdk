"""Tests for the panel recipe library (REQ-DCR-RCP)."""

import re

import pytest

from startd8.dashboard_creator.generator import _render_panel
from startd8.dashboard_creator.models import (
    DashboardSpec,
    PanelSpec,
    PanelType,
    TransformSpec,
)
from startd8.dashboard_creator.recipes import (
    RECIPE_REGISTRY,
    PanelRecipe,
    _deep_merge,
    hydrate_panel,
)
from startd8.dashboard_creator.validation import validate_spec


# --- Registry integrity (RCP-001/002/003/004) -------------------------------

class TestRegistry:
    def test_registry_nonempty_and_well_formed(self):
        assert RECIPE_REGISTRY
        for rid, r in RECIPE_REGISTRY.items():
            assert rid == r.id
            assert re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", rid)
            assert r.applies_to  # at least one panel type
            assert all(isinstance(t, PanelType) for t in r.applies_to)

    def test_expected_seed_ids_present(self):
        expected = {
            "stat.kpi", "stat.headline", "gauge.threshold", "bargauge.lcd",
            "bargauge.basic", "piechart.composition", "timeseries.observability",
            "timeseries.stacked", "table.aggregation", "table.ranking",
            "barchart.ranking", "text.banner",
            "canvas.display", "canvas.editable", "canvas.metric_card",
        }
        assert set(RECIPE_REGISTRY) == expected

    def test_bad_id_shape_rejected(self):
        with pytest.raises(ValueError):
            PanelRecipe(id="StatKpi", applies_to=[PanelType.STAT])


# --- Deep merge (RCP-021/022) -----------------------------------------------

class TestDeepMerge:
    def test_dicts_merge_lists_and_scalars_replace(self):
        base = {"a": 1, "nested": {"x": 1, "y": 2}, "lst": [1, 2]}
        override = {"a": 2, "nested": {"y": 9, "z": 3}, "lst": [9]}
        assert _deep_merge(base, override) == {
            "a": 2, "nested": {"x": 1, "y": 9, "z": 3}, "lst": [9]
        }

    def test_does_not_mutate_base(self):
        base = {"nested": {"x": 1}}
        _deep_merge(base, {"nested": {"y": 2}})
        assert base == {"nested": {"x": 1}}


# --- Hydration precedence (RCP-020/021/022/023) -----------------------------

class TestHydration:
    def test_no_recipe_is_noop(self):
        p = PanelSpec(type=PanelType.STAT, title="S", expr="up")
        eff, warns = hydrate_panel(p)
        assert eff is p and warns == []

    def test_recipe_fills_when_spec_silent(self):
        p = PanelSpec(type=PanelType.STAT, title="S", expr="up", recipe="stat.kpi")
        eff, _ = hydrate_panel(p)
        assert eff.options["colorMode"] == "value"      # from recipe
        assert eff.options["graphMode"] == "area"
        assert eff.unit == "short"                       # recipe unit fills empty

    def test_spec_wins_over_recipe(self):
        p = PanelSpec(type=PanelType.STAT, title="S", expr="up", recipe="stat.kpi",
                      options={"colorMode": "background"}, unit="bytes")
        eff, warns = hydrate_panel(p)
        assert eff.options["colorMode"] == "background"  # spec overrides recipe
        assert eff.options["graphMode"] == "area"        # recipe key the spec didn't set
        assert eff.unit == "bytes"                       # spec unit wins
        assert any("colorMode" in w for w in warns)      # shadow warning emitted

    def test_nested_deepmerge_coexists(self):
        p = PanelSpec(type=PanelType.TIMESERIES, title="T", expr="up",
                      recipe="timeseries.stacked",
                      fieldConfig={"defaults": {"custom": {"lineWidth": 3}}})
        # recipe sets defaults.custom.{stacking,fillOpacity}; spec sets defaults.custom.lineWidth
        eff, _ = hydrate_panel(p)
        custom = eff.fieldConfig["defaults"]["custom"]
        assert custom["fillOpacity"] == 20               # recipe
        assert custom["stacking"]["mode"] == "normal"    # recipe
        assert custom["lineWidth"] == 3                  # spec — coexists (deep merge)

    def test_transformations_fill_if_empty(self):
        recipe_tx = PanelRecipe(id="x.y", applies_to=[PanelType.TABLE],
                                transformations=[TransformSpec(id="organize")])
        RECIPE_REGISTRY["x.y"] = recipe_tx
        try:
            empty = PanelSpec(type=PanelType.TABLE, title="T", expr="up", recipe="x.y")
            eff, _ = hydrate_panel(empty)
            assert [t.id for t in eff.transformations] == ["organize"]
            owns = PanelSpec(type=PanelType.TABLE, title="T", expr="up", recipe="x.y",
                             transformations=[TransformSpec(id="merge")])
            eff2, _ = hydrate_panel(owns)
            assert [t.id for t in eff2.transformations] == ["merge"]  # spec wins entirely
        finally:
            del RECIPE_REGISTRY["x.y"]


# --- Validation (RCP-030/031) -----------------------------------------------

class TestRecipeValidation:
    # validate_spec returns a list of error strings ([] == valid).
    def test_unknown_recipe_errors(self):
        spec = DashboardSpec(title="D", uid="cc-x-d", panels=[
            PanelSpec(type=PanelType.STAT, title="S", expr="up", recipe="stat.bogus")])
        errors = validate_spec(spec, {})
        assert any("stat.bogus" in e for e in errors)

    def test_type_mismatch_errors(self):
        spec = DashboardSpec(title="D", uid="cc-x-d", panels=[
            PanelSpec(type=PanelType.TIMESERIES, title="T", expr="up", recipe="stat.kpi")])
        errors = validate_spec(spec, {})
        assert any("stat.kpi" in e and "timeseries" in e for e in errors)

    def test_valid_recipe_passes(self):
        spec = DashboardSpec(title="D", uid="cc-x-d", panels=[
            PanelSpec(type=PanelType.STAT, title="S", expr="up", recipe="stat.kpi")])
        assert validate_spec(spec, {}) == []


# --- Render integration (RCP-010/020) ---------------------------------------

class TestRenderWithRecipe:
    def test_no_recipe_render_unchanged(self):
        a = _render_panel(PanelSpec(type=PanelType.STAT, title="S", expr="up"))
        b = _render_panel(PanelSpec(type=PanelType.STAT, title="S", expr="up"))
        assert a == b

    def test_recipe_values_appear_in_render(self):
        result = _render_panel(
            PanelSpec(type=PanelType.STAT, title="S", expr="up", recipe="stat.kpi"))
        # options+: merge block, _to_jsonnet form (unquoted key, JSON value)
        assert "options+: {" in result
        assert 'colorMode: "value"' in result
        assert "unit='short'" in result
