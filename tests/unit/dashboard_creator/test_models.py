"""Tests for dashboard_creator.models — Pydantic v2 data models."""

import pytest
from pydantic import ValidationError

from startd8.dashboard_creator.models import (
    DashboardLink,
    DashboardSpec,
    DataLink,
    GridPos,
    PanelSpec,
    PanelType,
    TargetSpec,
    ThresholdStep,
    TransformSpec,
    VariableSpec,
    VariableType,
)


# ---------------------------------------------------------------------------
# PanelType enum
# ---------------------------------------------------------------------------


class TestPanelType:
    def test_all_22_values_accepted(self):
        expected = {
            "stat", "gauge", "timeseries", "table", "barchart", "barGauge",
            "piechart", "histogram", "logs", "row", "traceqlStat",
            "traceqlTable", "traceqlTimeseries", "traceqlGauge", "traces",
            "text", "geomap", "canvas", "heatmap", "state-timeline",
            "xychart", "candlestick",
        }
        assert {pt.value for pt in PanelType} == expected
        assert len(PanelType) == 22

    def test_string_enum_value(self):
        assert PanelType.STAT == "stat"
        assert PanelType.BAR_GAUGE == "barGauge"


# ---------------------------------------------------------------------------
# VariableType enum
# ---------------------------------------------------------------------------


class TestVariableType:
    def test_all_11_values_accepted(self):
        expected = {
            "prometheusDatasource", "tempoDatasource", "lokiDatasource",
            "serviceNameVariable", "modelVariable", "agentVariable",
            "projectVariable", "queryVariable", "intervalVariable",
            "customVariable", "constantVariable",
        }
        assert {vt.value for vt in VariableType} == expected
        assert len(VariableType) == 11


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

    def test_links_default_empty(self):
        spec = DashboardSpec(
            title="Test",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
        )
        assert spec.links == []

    def test_links_populated(self):
        spec = DashboardSpec(
            title="Test",
            panels=[PanelSpec(type="stat", title="Up", expr="up")],
            links=[
                DashboardLink(title="Docs", url="https://example.com"),
                DashboardLink(title="Related", type="dashboards", tags=["team"]),
            ],
        )
        assert len(spec.links) == 2
        assert spec.links[0].title == "Docs"
        assert spec.links[1].type == "dashboards"


# ---------------------------------------------------------------------------
# TargetSpec extensions
# ---------------------------------------------------------------------------


class TestTargetSpecExtensions:
    def test_instant_default_false(self):
        target = TargetSpec(expr="up")
        assert target.instant is False

    def test_instant_true_roundtrip(self):
        target = TargetSpec(expr="up", instant=True)
        assert target.instant is True

    def test_format_default_none(self):
        target = TargetSpec(expr="up")
        assert target.format is None

    def test_format_table_roundtrip(self):
        target = TargetSpec(expr="up", format="table")
        assert target.format == "table"

    def test_format_time_series_roundtrip(self):
        target = TargetSpec(expr="up", format="time_series")
        assert target.format == "time_series"

    def test_format_heatmap_roundtrip(self):
        target = TargetSpec(expr="up", format="heatmap")
        assert target.format == "heatmap"

    def test_format_invalid_rejected(self):
        with pytest.raises(ValidationError, match="format must be"):
            TargetSpec(expr="up", format="invalid")

    def test_instant_and_format_together(self):
        target = TargetSpec(expr="up", instant=True, format="table")
        assert target.instant is True
        assert target.format == "table"


# ---------------------------------------------------------------------------
# VariableSpec extensions
# ---------------------------------------------------------------------------


class TestVariableSpecExtensions:
    def test_includeAll_default_false(self):
        var = VariableSpec(type="prometheusDatasource", name="ds")
        assert var.includeAll is False

    def test_includeAll_roundtrip(self):
        var = VariableSpec(
            type="customVariable", name="env", query="a,b",
            includeAll=True,
        )
        assert var.includeAll is True

    def test_allValue_with_includeAll(self):
        var = VariableSpec(
            type="customVariable", name="env", query="a,b",
            includeAll=True, allValue=".*",
        )
        assert var.allValue == ".*"

    def test_allValue_without_includeAll_rejected(self):
        with pytest.raises(ValidationError, match="allValue requires includeAll"):
            VariableSpec(
                type="customVariable", name="env", query="a,b",
                allValue=".*",
            )

    def test_default_roundtrip(self):
        var = VariableSpec(
            type="customVariable", name="env", query="a,b",
            default="prod",
        )
        assert var.default == "prod"

    def test_hide_default_zero(self):
        var = VariableSpec(type="prometheusDatasource", name="ds")
        assert var.hide == 0

    def test_hide_valid_values(self):
        for h in (0, 1, 2):
            var = VariableSpec(type="prometheusDatasource", name="ds", hide=h)
            assert var.hide == h

    def test_hide_invalid_rejected(self):
        with pytest.raises(ValidationError, match="hide must be"):
            VariableSpec(type="prometheusDatasource", name="ds", hide=3)

    def test_hide_negative_rejected(self):
        with pytest.raises(ValidationError, match="hide must be"):
            VariableSpec(type="prometheusDatasource", name="ds", hide=-1)

    def test_skipUrlSync_default_false(self):
        var = VariableSpec(type="prometheusDatasource", name="ds")
        assert var.skipUrlSync is False

    def test_skipUrlSync_roundtrip(self):
        var = VariableSpec(
            type="prometheusDatasource", name="ds", skipUrlSync=True,
        )
        assert var.skipUrlSync is True


# ---------------------------------------------------------------------------
# DashboardLink
# ---------------------------------------------------------------------------


class TestDashboardLink:
    def test_minimal_construction(self):
        link = DashboardLink(title="Docs")
        assert link.title == "Docs"
        assert link.url == ""
        assert link.type == "link"

    def test_defaults(self):
        link = DashboardLink(title="X")
        assert link.icon == "external link"
        assert link.tooltip == ""
        assert link.targetBlank is True
        assert link.tags == []
        assert link.asDropdown is False
        assert link.includeVars is False
        assert link.keepTime is False

    def test_full_construction(self):
        link = DashboardLink(
            title="Budget Dashboard",
            url="https://example.com/budget",
            icon="dashboard",
            tooltip="View budget",
            targetBlank=False,
            type="dashboards",
            tags=["budget", "finance"],
            asDropdown=True,
            includeVars=True,
            keepTime=True,
        )
        assert link.type == "dashboards"
        assert link.asDropdown is True
        assert link.includeVars is True
        assert link.keepTime is True
        assert len(link.tags) == 2


# ---------------------------------------------------------------------------
# DataLink
# ---------------------------------------------------------------------------


class TestDataLink:
    def test_construction(self):
        link = DataLink(title="Drill Down", url="https://example.com/${__value.text}")
        assert link.title == "Drill Down"
        assert link.targetBlank is True

    def test_targetBlank_override(self):
        link = DataLink(title="X", url="http://x", targetBlank=False)
        assert link.targetBlank is False


# ---------------------------------------------------------------------------
# TransformSpec
# ---------------------------------------------------------------------------


class TestTransformSpec:
    def test_construction_minimal(self):
        t = TransformSpec(id="organize")
        assert t.id == "organize"
        assert t.options == {}

    def test_construction_with_options(self):
        t = TransformSpec(
            id="calculateField",
            options={"mode": "binary", "alias": "total"},
        )
        assert t.options["mode"] == "binary"


# ---------------------------------------------------------------------------
# PanelSpec extensions
# ---------------------------------------------------------------------------


class TestPanelSpecExtensions:
    def test_description_default_empty(self):
        panel = PanelSpec(type="stat", title="Up", expr="up")
        assert panel.description == ""

    def test_description_roundtrip(self):
        panel = PanelSpec(
            type="stat", title="Up", expr="up",
            description="Shows uptime",
        )
        assert panel.description == "Shows uptime"

    def test_fieldConfig_default_empty(self):
        panel = PanelSpec(type="stat", title="Up", expr="up")
        assert panel.fieldConfig == {}

    def test_fieldConfig_roundtrip(self):
        panel = PanelSpec(
            type="stat", title="Up", expr="up",
            fieldConfig={"defaults": {"unit": "percent"}},
        )
        assert panel.fieldConfig["defaults"]["unit"] == "percent"

    def test_dataLinks_default_empty(self):
        panel = PanelSpec(type="stat", title="Up", expr="up")
        assert panel.dataLinks == []

    def test_dataLinks_roundtrip(self):
        panel = PanelSpec(
            type="stat", title="Up", expr="up",
            dataLinks=[DataLink(title="Drill", url="http://x")],
        )
        assert len(panel.dataLinks) == 1
        assert panel.dataLinks[0].title == "Drill"

    def test_transformations_default_empty(self):
        panel = PanelSpec(type="stat", title="Up", expr="up")
        assert panel.transformations == []

    def test_transformations_roundtrip(self):
        panel = PanelSpec(
            type="table", title="Top",
            targets=[TargetSpec(expr="up")],
            transformations=[
                TransformSpec(id="organize", options={"excludeByName": {"Time": True}}),
            ],
        )
        assert len(panel.transformations) == 1
        assert panel.transformations[0].id == "organize"
