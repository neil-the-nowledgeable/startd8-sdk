"""Tests for the dashboard <-> Proven Exemplar Pipeline bridge (REQ-PEP-300..342)."""

import json

from startd8.dashboard_creator.exemplar_bridge import (
    REFERENCE_TIER,
    apply_recipe_hint,
    classify_archetype,
    dashboard_fingerprint,
    find_dashboard_exemplar,
    score_dashboard,
    seed_reference_exemplars,
    suggest_recipes,
)
from startd8.dashboard_creator.models import DashboardSpec, PanelSpec, PanelType
from startd8.exemplars.registry import ExemplarRegistry


def _dash(panels, uid="cc-x", title="D", tags=None, schema=39):
    return {"title": title, "uid": uid, "tags": tags or [],
            "schemaVersion": schema, "panels": panels}


def _p(t):
    return {"type": t, "title": t}


class TestClassify:
    def test_primary_visualization(self):
        assert classify_archetype(_dash([_p("stat"), _p("stat"), _p("gauge")])) == "kpi_dashboard"
        assert classify_archetype(_dash([_p("timeseries"), _p("timeseries")])) == "observability_dashboard"
        assert classify_archetype(_dash([_p("table"), _p("table"), _p("stat")])) == "table_dashboard"
        assert classify_archetype(_dash([_p("geomap")])) == "geo_dashboard"
        assert classify_archetype(_dash([_p("canvas")])) == "creative_dashboard"

    def test_domain_hint_overrides(self):
        # SLO tag -> observability even though the primary viz is stat
        assert classify_archetype(_dash([_p("stat")], tags=["slo"])) == "observability_dashboard"

    def test_text_only_defaults_kpi(self):
        assert classify_archetype(_dash([_p("text")])) == "kpi_dashboard"

    def test_unwraps_api_envelope(self):
        wrapped = {"dashboard": _dash([_p("timeseries"), _p("timeseries")]), "meta": {}}
        assert classify_archetype(wrapped) == "observability_dashboard"


class TestFingerprintAndScore:
    def test_fingerprint_shape(self):
        fp = dashboard_fingerprint(_dash([_p("stat")]))
        assert str(fp) == "grafana:dashboard:none:kpi_dashboard"

    def test_binary_score(self):
        assert score_dashboard(_dash([_p("stat")])).disk_quality_score == 1.0
        bad = {"title": "x", "uid": "", "panels": []}  # invalid
        s = score_dashboard(bad)
        assert s.disk_quality_score == 0.0 and s.semantic_error_count == 1

    def test_reference_score_always_one(self):
        assert score_dashboard({"anything": True}, is_reference=True).requirement_score == 1.0


class TestSeedAndRetrieve:
    def test_seed_is_idempotent_and_tiered(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps(_dash([_p("timeseries"), _p("timeseries")], uid="a")))
        (tmp_path / "b.json").write_text(json.dumps(_dash([_p("stat"), _p("gauge")], uid="b")))
        reg = ExemplarRegistry()
        assert seed_reference_exemplars(tmp_path, reg) == 2
        seed_reference_exemplars(tmp_path, reg)  # re-seed
        # idempotent: still 2 distinct entries
        assert len(reg._exemplars) == 2
        for e in reg._exemplars:
            assert e.maturity == REFERENCE_TIER
            assert e.agent_specs["provenance"] == "external_reference"
            assert e.fingerprint.language == "grafana"

    def test_retrieval_matches_by_archetype(self, tmp_path):
        (tmp_path / "obs.json").write_text(json.dumps(_dash([_p("timeseries"), _p("timeseries")], uid="obs")))
        (tmp_path / "kpi.json").write_text(json.dumps(_dash([_p("stat"), _p("gauge")], uid="kpi")))
        reg = ExemplarRegistry()
        seed_reference_exemplars(tmp_path, reg)
        match = find_dashboard_exemplar(_dash([_p("timeseries"), _p("timeseries")]), reg)
        assert match is not None
        assert match.fingerprint.archetype == "observability_dashboard"

    def test_no_match_returns_none(self):
        assert find_dashboard_exemplar(_dash([_p("stat")]), ExemplarRegistry()) is None


class TestHint:
    def test_suggest_recipes_for_archetype(self):
        assert "stat.kpi" in suggest_recipes(_dash([_p("stat"), _p("gauge")]))
        assert "timeseries.observability" in suggest_recipes(_dash([_p("timeseries"), _p("timeseries")]))


class TestApplyRecipeHint:
    def _spec(self, panels):
        return DashboardSpec(title="D", uid="cc-x-d", panels=panels)

    def test_applies_to_unreciped_panels_by_type(self):
        spec = self._spec([
            PanelSpec(type=PanelType.STAT, title="A", expr="up"),
            PanelSpec(type=PanelType.GAUGE, title="B", expr="up"),
        ])
        out = apply_recipe_hint(spec)
        assert out.panels[0].recipe == "stat.kpi"        # kpi archetype -> stat.kpi
        assert out.panels[1].recipe == "gauge.threshold"

    def test_explicit_recipe_untouched(self):
        spec = self._spec([
            PanelSpec(type=PanelType.STAT, title="A", expr="up", recipe="stat.headline")])
        out = apply_recipe_hint(spec)
        assert out.panels[0].recipe == "stat.headline"   # spec wins

    def test_noop_for_uncovered_type(self):
        # a logs panel in a kpi dashboard — kpi recipes don't cover logs
        spec = self._spec([
            PanelSpec(type=PanelType.STAT, title="A", expr="up"),
            PanelSpec(type=PanelType.LOGS, title="L", expr="up")])
        out = apply_recipe_hint(spec)
        assert out.panels[1].recipe is None

    def test_deterministic(self):
        spec = self._spec([PanelSpec(type=PanelType.TIMESERIES, title="T", expr="up")])
        a = apply_recipe_hint(spec).panels[0].recipe
        b = apply_recipe_hint(spec).panels[0].recipe
        assert a == b == "timeseries.observability"

    def test_registry_gate_blocks_when_no_match(self):
        # with an empty registry, no proven exemplar exists -> no hint
        spec = self._spec([PanelSpec(type=PanelType.STAT, title="A", expr="up")])
        out = apply_recipe_hint(spec, registry=ExemplarRegistry())
        assert out.panels[0].recipe is None

    def test_registry_gate_allows_when_match(self, tmp_path):
        (tmp_path / "kpi.json").write_text(json.dumps(_dash([_p("stat"), _p("gauge")], uid="kpi")))
        reg = ExemplarRegistry()
        seed_reference_exemplars(tmp_path, reg)
        spec = self._spec([PanelSpec(type=PanelType.STAT, title="A", expr="up")])
        out = apply_recipe_hint(spec, registry=reg)
        assert out.panels[0].recipe == "stat.kpi"
