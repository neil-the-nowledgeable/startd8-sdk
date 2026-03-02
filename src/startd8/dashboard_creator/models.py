"""
Pydantic v2 data models for the Dashboard Creator (dbrd-cr8r).

DashboardSpec is the primary input model — a declarative YAML/JSON spec
that drives Jsonnet generation, compilation, and provisioning.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class PanelType(str, Enum):
    """Panel types mapped to panels.libsonnet constructors."""

    STAT = "stat"
    GAUGE = "gauge"
    TIMESERIES = "timeseries"
    TABLE = "table"
    BARCHART = "barchart"
    BAR_GAUGE = "barGauge"
    PIECHART = "piechart"
    HISTOGRAM = "histogram"
    LOGS = "logs"
    ROW = "row"
    TRACEQL_STAT = "traceqlStat"
    TRACEQL_TABLE = "traceqlTable"
    TRACEQL_TIMESERIES = "traceqlTimeseries"
    TRACEQL_GAUGE = "traceqlGauge"
    TRACES = "traces"
    TEXT = "text"


class VariableType(str, Enum):
    """Variable types mapped to variables.libsonnet builders."""

    PROMETHEUS_DATASOURCE = "prometheusDatasource"
    TEMPO_DATASOURCE = "tempoDatasource"
    LOKI_DATASOURCE = "lokiDatasource"
    SERVICE_NAME = "serviceNameVariable"
    MODEL = "modelVariable"
    AGENT = "agentVariable"
    PROJECT = "projectVariable"
    CUSTOM = "customVariable"
    CONSTANT = "constantVariable"


class GridPos(BaseModel):
    """Grafana panel grid position."""

    h: int = 8
    w: int = 12
    x: int = 0
    y: int = 0


class TargetSpec(BaseModel):
    """A single query target within a multi-target panel."""

    expr: Optional[str] = None
    legendFormat: str = ""
    query: Optional[str] = None  # TraceQL
    refId: Optional[str] = None
    datasource: Optional[Dict[str, Any]] = None
    queryType: Optional[str] = None


class ThresholdStep(BaseModel):
    """A single threshold step for panel coloring."""

    value: Optional[float] = None
    color: str = "green"


class PanelSpec(BaseModel):
    """Specification for a single dashboard panel."""

    type: PanelType
    title: str
    # Single-target panels (stat, gauge, barGauge, logs, traceqlStat, etc.)
    expr: Optional[str] = None
    query: Optional[str] = None  # TraceQL
    # Multi-target panels (timeseries, table, barchart, piechart, histogram, etc.)
    targets: Optional[List[TargetSpec]] = None
    # Layout
    gridPos: Optional[GridPos] = None
    group: Optional[str] = None  # Row grouping (DC-108)
    # Common options
    unit: str = ""
    thresholds: List[ThresholdStep] = Field(default_factory=list)
    overrides: List[Dict[str, Any]] = Field(default_factory=list)
    # Panel-specific options (forwarded to constructor)
    options: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target_source(self) -> "PanelSpec":
        """Panels need either expr, query, targets, or content (text)."""
        if self.type == PanelType.ROW:
            return self  # Rows don't need targets
        if self.type == PanelType.TEXT:
            if "content" not in self.options:
                raise ValueError("Text panels require options.content")
            return self
        has_single = self.expr is not None or self.query is not None
        has_multi = self.targets is not None and len(self.targets) > 0
        if not has_single and not has_multi:
            raise ValueError(
                f"Panel '{self.title}' ({self.type.value}) requires "
                f"'expr', 'query', or 'targets'"
            )
        return self


class VariableSpec(BaseModel):
    """Specification for a dashboard template variable."""

    type: VariableType
    name: str
    label: str = ""
    # For metric-based variables (model, agent, project)
    metric: Optional[str] = None
    # For custom variables
    query: Optional[str] = None
    multi: bool = False
    # For constant variables
    value: Optional[str] = None

    @model_validator(mode="after")
    def validate_variable_params(self) -> "VariableSpec":
        metric_types = {
            VariableType.MODEL,
            VariableType.AGENT,
            VariableType.PROJECT,
        }
        if self.type in metric_types and not self.metric:
            raise ValueError(
                f"Variable '{self.name}' ({self.type.value}) requires 'metric'"
            )
        if self.type == VariableType.CUSTOM and not self.query:
            raise ValueError(
                f"Variable '{self.name}' (customVariable) requires 'query'"
            )
        if self.type == VariableType.CONSTANT and not self.value:
            raise ValueError(
                f"Variable '{self.name}' (constantVariable) requires 'value'"
            )
        return self


class DashboardSpec(BaseModel):
    """
    Primary input model for dashboard generation.

    Captures everything needed to generate a single Grafana dashboard
    from the startd8-mixin library.
    """

    title: str
    uid: Optional[str] = None  # Auto-generated if omitted (DC-006)
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    panels: List[PanelSpec] = Field(min_length=1)
    variables: List[VariableSpec] = Field(default_factory=list)
    datasources: Dict[str, str] = Field(default_factory=dict)
    refresh: Optional[str] = None  # Hydrated from config (DC-005)
    timezone: Optional[str] = None  # Hydrated from config (DC-005)
    time_from: Optional[str] = None  # Hydrated from config (DC-005)
    time_to: Optional[str] = None  # Hydrated from config (DC-005)
    config_overrides: Dict[str, Any] = Field(default_factory=dict)
