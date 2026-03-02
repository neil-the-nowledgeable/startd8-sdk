"""Tests for dashboard_creator.models — Pydantic v2 data models."""

import pytest
from pydantic import ValidationError

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
# PanelType enum
# ---------------------------------------------------------------------------


class TestPanelType:
    def test_all_16_values_accepted(self):
        expected = {
            "stat", "gauge", "timeseries", "table", "barchart", "barGauge",
            "piechart", "histogram", "logs", "row", "traceqlStat",
            "traceqlTable", "traceqlTimeseries", "traceqlGauge", "traces",
            "text",
        }
        assert {pt.value for pt in PanelType} == expected
        assert len(PanelType) == 16

    def test_string_enum_value(self):
        assert PanelType.STAT == "stat"
        assert PanelType.BAR_GAUGE == "barGauge"


# ---------------------------------------------------------------------------
# VariableType enum
# ---------------------------------------------------------------------------


class TestVariableType:
    def test_all_9_values_accepted(self):
        expected = {
            "prometheusDatasource", "tempoDatasource", "lokiDatasource",
            "serviceNameVariable", "modelVariable", "agentVariable",
            "projectVariable", "customVariable", "constantVariable",
        }
        assert {vt.value for vt in VariableType} == expected
        assert len(VariableType) == 9


# ---------------------------------------------------------------------------
# PanelSpec validation
# ---------------------------------------------------------------------------


class TestPanelSpec:
    def test_stat_panel_with_expr(self):
        panel = PanelSpec(type="stat", title="Test", expr="up")
        assert panel.type == PanelType.STAT
        assert panel.expr == "up"

    def test_timeseries_panel_with_targets(self):
        panel = PanelSpec(
            type="timeseries",
            title="Latency",
            targets=[TargetSpec(expr="rate(http_requests_total[5m])")],
        )
        assert len(panel.targets) == 1

    def test_row_panel_needs_no_targets(self):
        panel = PanelSpec(type="row", title="Section 1")
        assert panel.type == PanelType.ROW

    def test_text_panel_requires_content(self):
        with pytest.raises(ValidationError, match="options.content"):
            PanelSpec(type="text", title="Info")

    def test_text_panel_with_content(self):
        panel = PanelSpec(
            type="text", title="Info", options={"content": "# Hello"}
        )
        assert panel.options["content"] == "# Hello"

    def test_panel_without_expr_or_targets_rejected(self):
        with pytest.raises(ValidationError, match="requires.*'expr'"):
            PanelSpec(type="stat", title="Bad Panel")

    def test_traceql_panel_with_query(self):
        panel = PanelSpec(
            type="traceqlStat",
            title="Trace Count",
            query='{ name = "agent.generate" } | count()',
        )
        assert panel.query is not None

    def test_panel_with_gridpos(self):
        panel = PanelSpec(
            type="stat", title="Test", expr="up",
            gridPos=GridPos(h=4, w=6, x=0, y=0),
        )
        assert panel.gridPos.h == 4
        assert panel.gridPos.w == 6

    def test_panel_with_thresholds(self):
        panel = PanelSpec(
            type="gauge", title="CPU", expr="process_cpu",
            thresholds=[
                ThresholdStep(value=None, color="green"),
                ThresholdStep(value=80, color="yellow"),
                ThresholdStep(value=95, color="red"),
            ],
        )
        assert len(panel.thresholds) == 3

    def test_panel_with_group(self):
        panel = PanelSpec(type="stat", title="Grouped", expr="up", group="Health")
        assert panel.group == "Health"

    def test_empty_targets_list_rejected(self):
        with pytest.raises(ValidationError, match="requires.*'expr'"):
            PanelSpec(type="timeseries", title="No Targets", targets=[])


# ---------------------------------------------------------------------------
# VariableSpec validation
# ---------------------------------------------------------------------------


class TestVariableSpec:
    def test_prometheus_datasource(self):
        var = VariableSpec(
            type="prometheusDatasource", name="datasource", label="Prometheus"
        )
        assert var.type == VariableType.PROMETHEUS_DATASOURCE

    def test_model_variable_requires_metric(self):
        with pytest.raises(ValidationError, match="requires 'metric'"):
            VariableSpec(type="modelVariable", name="model", label="Model")

    def test_model_variable_with_metric(self):
        var = VariableSpec(
            type="modelVariable", name="model", label="Model",
            metric="${metrics.requestsTotal}",
        )
        assert var.metric == "${metrics.requestsTotal}"

    def test_agent_variable_requires_metric(self):
        with pytest.raises(ValidationError, match="requires 'metric'"):
            VariableSpec(type="agentVariable", name="agent", label="Agent")

    def test_project_variable_requires_metric(self):
        with pytest.raises(ValidationError, match="requires 'metric'"):
            VariableSpec(type="projectVariable", name="project", label="Project")

    def test_custom_variable_requires_query(self):
        with pytest.raises(ValidationError, match="requires 'query'"):
            VariableSpec(type="customVariable", name="env", label="Environment")

    def test_custom_variable_with_query(self):
        var = VariableSpec(
            type="customVariable", name="env", label="Environment",
            query="prod,staging,dev", multi=True,
        )
        assert var.multi is True

    def test_constant_variable_requires_value(self):
        with pytest.raises(ValidationError, match="requires 'value'"):
            VariableSpec(type="constantVariable", name="ver")

    def test_constant_variable_with_value(self):
        var = VariableSpec(type="constantVariable", name="ver", value="1.0")
        assert var.value == "1.0"

    def test_datasource_types_no_extra_params(self):
        for vtype in ["tempoDatasource", "lokiDatasource"]:
            var = VariableSpec(type=vtype, name="ds", label="DS")
            assert var.type.value == vtype

    def test_service_name_variable(self):
        var = VariableSpec(
            type="serviceNameVariable", name="service_name", label="Service"
        )
        assert var.type == VariableType.SERVICE_NAME


# ---------------------------------------------------------------------------
# DashboardSpec
# ---------------------------------------------------------------------------


class TestDashboardSpec:
    def test_minimal_valid_spec(self):
        spec = DashboardSpec(
            title="Test Dashboard",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )
        assert spec.title == "Test Dashboard"
        assert spec.uid is None
        assert len(spec.panels) == 1

    def test_panels_must_be_nonempty(self):
        with pytest.raises(ValidationError, match="at least 1"):
            DashboardSpec(title="Empty", panels=[])

    def test_full_spec_roundtrip(self):
        data = {
            "title": "Agent Performance Overview",
            "uid": "cc-startd8-agent-perf",
            "description": "Agent request latency and session health",
            "tags": ["startd8", "agents"],
            "panels": [
                {
                    "type": "timeseries",
                    "title": "Request Latency P99",
                    "targets": [
                        {
                            "expr": "histogram_quantile(0.99, rate(${metrics.responseTimeMs}[$__rate_interval]))",
                            "legendFormat": "p99",
                        }
                    ],
                    "unit": "ms",
                },
                {
                    "type": "stat",
                    "title": "Active Sessions",
                    "expr": "${metrics.activeSessions}",
                    "unit": "short",
                },
            ],
            "variables": [
                {"type": "prometheusDatasource", "name": "datasource", "label": "Prometheus"},
                {"type": "modelVariable", "name": "model", "label": "Model", "metric": "${metrics.requestsTotal}"},
            ],
            "datasources": {"mimir": "grafanacloud-prom"},
            "refresh": "30s",
            "timezone": "browser",
            "config_overrides": {"metrics": {"responseTimeMs": "custom_latency_metric"}},
        }
        spec = DashboardSpec(**data)
        dumped = spec.model_dump()
        assert dumped["title"] == "Agent Performance Overview"
        assert dumped["uid"] == "cc-startd8-agent-perf"
        assert len(dumped["panels"]) == 2
        assert len(dumped["variables"]) == 2

    def test_optional_fields_have_defaults(self):
        spec = DashboardSpec(
            title="Minimal",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )
        assert spec.description == ""
        assert spec.tags == []
        assert spec.variables == []
        assert spec.datasources == {}
        assert spec.refresh is None
        assert spec.timezone is None
        assert spec.time_from is None
        assert spec.time_to is None
        assert spec.config_overrides == {}

    def test_model_json_schema_produced(self):
        schema = DashboardSpec.model_json_schema()
        assert "properties" in schema
        assert "title" in schema["properties"]
        assert "panels" in schema["properties"]
