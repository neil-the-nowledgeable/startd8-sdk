"""Tests for structural lint (REQ-DCR-AES-060/061/062, AES-031, RCP-032)."""

from startd8.dashboard_creator.models import (
    DashboardSpec,
    PanelSpec,
    PanelType,
    TargetSpec,
)
from startd8.dashboard_creator.validation import lint_spec


def _spec(panels):
    return DashboardSpec(title="D", uid="cc-x-d", panels=panels)


class TestLint:
    def test_signal_row_suggested_when_top_not_kpi(self):
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.TIMESERIES, title="T", expr="up", unit="s")]))
        assert any("signal-row" in w for w in warns)

    def test_no_signal_warning_when_top_is_stat(self):
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="S", expr="up", unit="short")]))
        assert not any("signal-row" in w for w in warns)

    def test_untitled_panel(self):
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="", expr="up", unit="short")]))
        assert any("no title" in w for w in warns)

    def test_missing_unit(self):
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="S", expr="up")]))  # no unit
        assert any("no unit" in w for w in warns)

    def test_recipe_unit_suppresses_missing_unit(self):
        # stat.kpi supplies unit='short' -> no missing-unit warning
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="S", expr="up", recipe="stat.kpi")]))
        assert not any("no unit" in w for w in warns)

    def test_timeseries_without_legendformat(self):
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="S", expr="up", unit="short"),
            PanelSpec(type=PanelType.TIMESERIES, title="T", unit="s",
                      targets=[TargetSpec(expr="up")])]))  # no legendFormat
        assert any("legendFormat" in w for w in warns)

    def test_rainbow(self):
        colors = ["red", "green", "blue", "purple", "orange", "yellow", "cyan"]
        overrides = [{"matcher": {"id": "byName", "options": c},
                      "properties": [{"id": "color", "value": {"fixedColor": c, "mode": "fixed"}}]}
                     for c in colors]
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="S", expr="up", unit="short"),
            PanelSpec(type=PanelType.TIMESERIES, title="T", unit="s",
                      targets=[TargetSpec(expr="up", legendFormat="x")],
                      overrides=overrides)]))
        assert any("Rainbow" in w for w in warns)

    def test_recipe_shadow_warning(self):
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="S", expr="up", recipe="stat.kpi",
                      options={"colorMode": "background"})]))  # overrides recipe colorMode
        assert any("overridden by spec" in w and "colorMode" in w for w in warns)

    def test_clean_dashboard_no_warnings(self):
        warns = lint_spec(_spec([
            PanelSpec(type=PanelType.STAT, title="OK", expr="up", unit="short")]))
        assert warns == []
