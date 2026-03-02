"""Tests for dashboard_creator.generator — Jsonnet template engine."""

import pytest

from startd8.dashboard_creator.generator import (
    generate_dashboard_jsonnet,
    _render_expression,
    _render_panel,
    _render_variable,
)
from startd8.dashboard_creator.models import (
    DashboardSpec,
    GridPos,
    PanelSpec,
    PanelType,
    TargetSpec,
    ThresholdStep,
    VariableSpec,
    VariableType,
)


# ---------------------------------------------------------------------------
# _render_expression
# ---------------------------------------------------------------------------


class TestRenderExpression:
    def test_pure_metric_ref(self):
        result = _render_expression("${metrics.requestsTotal}")
        assert result == "m.requestsTotal"

    def test_pure_selector_ref(self):
        result = _render_expression("${selectors.serviceName}")
        assert result == "sel.serviceName"

    def test_mixed_metric_ref(self):
        result = _render_expression("rate(${metrics.requestsTotal}[5m])")
        assert result == "'rate(' + m.requestsTotal + '[5m])'"

    def test_mixed_selector_ref(self):
        result = _render_expression("up{${selectors.serviceName}}")
        assert result == "'up{' + sel.serviceName + '}'"

    def test_multiple_refs(self):
        result = _render_expression(
            "sum(${metrics.costTotal}{${selectors.model}})"
        )
        assert "m.costTotal" in result
        assert "sel.model" in result

    def test_literal_dollar_preserved(self):
        result = _render_expression("rate(up[$__rate_interval])")
        assert "$__rate_interval" in result

    def test_no_refs(self):
        result = _render_expression("up")
        assert result == "'up'"

    def test_empty_string(self):
        result = _render_expression("")
        assert result == "''"


# ---------------------------------------------------------------------------
# _render_panel
# ---------------------------------------------------------------------------


class TestRenderPanel:
    def test_stat_panel(self):
        panel = PanelSpec(type="stat", title="Active Sessions", expr="up")
        result = _render_panel(panel)
        assert "panels.stat(" in result
        assert "'Active Sessions'" in result
        assert "'up'" in result

    def test_timeseries_panel_with_targets(self):
        panel = PanelSpec(
            type="timeseries",
            title="Latency",
            targets=[TargetSpec(expr="rate(http_requests_total[5m])", legendFormat="p99")],
            unit="ms",
        )
        result = _render_panel(panel)
        assert "panels.timeseries(" in result
        assert "unit='ms'" in result
        assert "legendFormat:" in result

    def test_row_panel(self):
        panel = PanelSpec(type="row", title="Section 1")
        result = _render_panel(panel)
        assert "panels.row(" in result
        assert "'Section 1'" in result

    def test_text_panel(self):
        panel = PanelSpec(
            type="text", title="Info", options={"content": "# Hello"}
        )
        result = _render_panel(panel)
        assert "panels.text(" in result
        assert "'# Hello'" in result

    def test_gauge_panel_with_thresholds(self):
        panel = PanelSpec(
            type="gauge",
            title="CPU",
            expr="process_cpu",
            thresholds=[
                ThresholdStep(value=None, color="green"),
                ThresholdStep(value=80, color="yellow"),
            ],
        )
        result = _render_panel(panel)
        assert "panels.gauge(" in result
        assert "thresholds=" in result
        assert "color: 'green'" in result

    def test_traceql_stat_panel(self):
        panel = PanelSpec(
            type="traceqlStat",
            title="Count",
            query='{ name = "agent.generate" } | count()',
        )
        result = _render_panel(panel)
        assert "panels.traceqlStat(" in result
        assert "datasource=tempoDatasource" in result

    def test_logs_panel(self):
        panel = PanelSpec(
            type="logs",
            title="Logs",
            expr='{service_name="sdk"}',
        )
        result = _render_panel(panel)
        assert "panels.logs(" in result
        assert "datasource=lokiDatasource" in result

    def test_panel_with_gridpos(self):
        panel = PanelSpec(
            type="stat",
            title="Up",
            expr="up",
            gridPos=GridPos(h=4, w=6, x=12, y=0),
        )
        result = _render_panel(panel)
        assert "gridPos:" in result
        assert "h: 4" in result
        assert "w: 6" in result

    def test_barchart_multi_target(self):
        panel = PanelSpec(
            type="barchart",
            title="Tokens",
            targets=[
                TargetSpec(expr="sum(input_tokens)", legendFormat="input"),
                TargetSpec(expr="sum(output_tokens)", legendFormat="output"),
            ],
        )
        result = _render_panel(panel)
        assert "panels.barchart(" in result
        assert "refId: 'A'" in result
        assert "refId: 'B'" in result

    def test_metric_ref_in_panel_expr(self):
        panel = PanelSpec(
            type="stat",
            title="Sessions",
            expr="${metrics.activeSessions}",
        )
        result = _render_panel(panel)
        assert "m.activeSessions" in result

    def test_all_16_panel_types_renderable(self):
        """Every PanelType value produces output without error."""
        for pt in PanelType:
            if pt == PanelType.ROW:
                panel = PanelSpec(type=pt, title="Row")
            elif pt == PanelType.TEXT:
                panel = PanelSpec(type=pt, title="Text", options={"content": "hi"})
            elif pt in {
                PanelType.TIMESERIES, PanelType.TABLE, PanelType.BARCHART,
                PanelType.PIECHART, PanelType.HISTOGRAM,
                PanelType.TRACEQL_TABLE, PanelType.TRACEQL_TIMESERIES,
            }:
                panel = PanelSpec(type=pt, title=f"T-{pt.value}", targets=[TargetSpec(expr="up")])
            elif pt in {
                PanelType.TRACEQL_STAT, PanelType.TRACEQL_GAUGE, PanelType.TRACES,
            }:
                panel = PanelSpec(type=pt, title=f"T-{pt.value}", query="{ }")
            else:
                panel = PanelSpec(type=pt, title=f"T-{pt.value}", expr="up")
            result = _render_panel(panel)
            assert f"panels.{pt.value}(" in result, f"Panel type {pt.value} not rendered"


# ---------------------------------------------------------------------------
# _render_variable
# ---------------------------------------------------------------------------


class TestRenderVariable:
    def test_prometheus_datasource(self):
        var = VariableSpec(type="prometheusDatasource", name="datasource", label="Prometheus")
        result = _render_variable(var)
        assert "variables.prometheusDatasource(" in result
        assert "name='datasource'" in result
        assert "label='Prometheus'" in result

    def test_model_variable_with_metric(self):
        var = VariableSpec(
            type="modelVariable", name="model", label="Model",
            metric="${metrics.requestsTotal}",
        )
        result = _render_variable(var)
        assert "variables.modelVariable(" in result
        assert "m.requestsTotal" in result

    def test_custom_variable(self):
        var = VariableSpec(
            type="customVariable", name="env", label="Environment",
            query="prod,staging,dev", multi=True,
        )
        result = _render_variable(var)
        assert "variables.customVariable(" in result
        assert "query='prod,staging,dev'" in result
        assert "multi=true" in result

    def test_constant_variable(self):
        var = VariableSpec(type="constantVariable", name="ver", value="1.0")
        result = _render_variable(var)
        assert "variables.constantVariable(" in result
        assert "'ver'" in result
        assert "'1.0'" in result

    def test_all_9_variable_types_renderable(self):
        """Every VariableType value produces output without error."""
        for vt in VariableType:
            kwargs = {"type": vt, "name": "test", "label": "Test"}
            if vt in {VariableType.MODEL, VariableType.AGENT, VariableType.PROJECT}:
                kwargs["metric"] = "up"
            if vt == VariableType.CUSTOM:
                kwargs["query"] = "a,b"
            if vt == VariableType.CONSTANT:
                kwargs["value"] = "x"
            var = VariableSpec(**kwargs)
            result = _render_variable(var)
            assert f"variables.{vt.value}(" in result


# ---------------------------------------------------------------------------
# generate_dashboard_jsonnet (full pipeline)
# ---------------------------------------------------------------------------


class TestGenerateDashboardJsonnet:
    def test_minimal_spec(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )
        result = generate_dashboard_jsonnet(spec)
        assert "local config = (import '../config.libsonnet')._config;" in result
        assert "local dashboards = import '../lib/dashboards.libsonnet';" in result
        assert "dashboards.dashboard(" in result
        assert "'Test'" in result
        assert "'cc-startd8-test'" in result
        assert "dashboards.withPanels(baseDashboard, [" in result
        assert "panels.stat(" in result

    def test_with_description_and_tags(self):
        spec = DashboardSpec(
            title="Agent Perf",
            uid="cc-startd8-agent-perf",
            description="Agent metrics",
            tags=["startd8", "agents"],
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )
        result = generate_dashboard_jsonnet(spec)
        assert "description='Agent metrics'" in result
        assert "'startd8'" in result
        assert "'agents'" in result

    def test_with_variables(self):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
            variables=[
                VariableSpec(type="prometheusDatasource", name="datasource", label="Prometheus"),
                VariableSpec(type="modelVariable", name="model", label="Model", metric="${metrics.costTotal}"),
            ],
        )
        result = generate_dashboard_jsonnet(spec)
        assert "templating:" in result
        assert "list:" in result
        assert "variables.prometheusDatasource(" in result
        assert "variables.modelVariable(" in result
        assert "m.costTotal" in result

    def test_config_imports_present(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-t",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )
        result = generate_dashboard_jsonnet(spec)
        assert "local m = config.metrics;" in result
        assert "local ds = config.datasources;" in result
        assert "local sel = config.selectors;" in result

    def test_datasource_locals_present(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-t",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )
        result = generate_dashboard_jsonnet(spec)
        assert "local mimirDatasource" in result
        assert "local tempoDatasource" in result
        assert "local lokiDatasource" in result

    def test_rate_interval_preserved(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-t",
            panels=[
                PanelSpec(
                    type="timeseries",
                    title="Rate",
                    targets=[TargetSpec(expr="rate(up[$__rate_interval])")],
                )
            ],
        )
        result = generate_dashboard_jsonnet(spec)
        assert "$__rate_interval" in result

    def test_multi_target_panel(self):
        spec = DashboardSpec(
            title="T",
            uid="cc-startd8-t",
            panels=[
                PanelSpec(
                    type="timeseries",
                    title="Latency",
                    targets=[
                        TargetSpec(expr="p50", legendFormat="p50"),
                        TargetSpec(expr="p99", legendFormat="p99"),
                    ],
                )
            ],
        )
        result = generate_dashboard_jsonnet(spec)
        assert "refId: 'A'" in result
        assert "refId: 'B'" in result
        assert "legendFormat: 'p50'" in result
        assert "legendFormat: 'p99'" in result
