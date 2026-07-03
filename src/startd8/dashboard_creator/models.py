"""
Pydantic v2 data models for the Dashboard Creator (dbrd-cr8r).

DashboardSpec is the primary input model — a declarative YAML/JSON spec
that drives Jsonnet generation, compilation, and provisioning.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
    # Phase 5 — new panel types (gap analysis backlog)
    GEOMAP = "geomap"
    CANVAS = "canvas"
    HEATMAP = "heatmap"
    STATE_TIMELINE = "state-timeline"
    XYCHART = "xychart"
    CANDLESTICK = "candlestick"


class VariableType(str, Enum):
    """Variable types mapped to variables.libsonnet builders."""

    PROMETHEUS_DATASOURCE = "prometheusDatasource"
    TEMPO_DATASOURCE = "tempoDatasource"
    LOKI_DATASOURCE = "lokiDatasource"
    SERVICE_NAME = "serviceNameVariable"
    MODEL = "modelVariable"
    AGENT = "agentVariable"
    PROJECT = "projectVariable"
    QUERY = "queryVariable"  # GAP-VAR-01: generic label_values(...) query variable
    INTERVAL = "intervalVariable"  # GAP-VAR-03
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
    instant: bool = False  # Instant query (vs range)
    format: Optional[str] = None  # "table", "time_series", "heatmap"

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"table", "time_series", "heatmap"}:
            raise ValueError(
                f"format must be 'table', 'time_series', or 'heatmap', got '{v}'"
            )
        return v


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
    # Explicit datasource override (DC-112): `tempo`|`mimir`|`prometheus`|`loki`. Wins over the
    # query-language + panel-type inference. `None` = infer.
    datasource: Optional[str] = None
    # Layout
    gridPos: Optional[GridPos] = None
    group: Optional[str] = None  # Row grouping (DC-108)
    # Named recipe (REQ-DCR-RCP-010) — corpus-mode finish merged under explicit values
    recipe: Optional[str] = None
    # Common options
    unit: str = ""
    thresholds: List[ThresholdStep] = Field(default_factory=list)
    overrides: List[Dict[str, Any]] = Field(default_factory=list)
    # Panel-specific options (forwarded to constructor)
    options: Dict[str, Any] = Field(default_factory=dict)
    # Extended panel fields
    description: str = ""
    fieldConfig: Dict[str, Any] = Field(default_factory=dict)  # Pass-through
    dataLinks: List["DataLink"] = Field(default_factory=list)
    transformations: List["TransformSpec"] = Field(default_factory=list)

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
    # For custom/query/interval variables — the options list or the query definition
    # (e.g. "label_values(up, instance)" for a query var, "1m,10m,1h" for interval).
    query: Optional[str] = None
    multi: bool = False
    # For constant variables
    value: Optional[str] = None
    # Extended variable options
    includeAll: bool = False  # "All" option in dropdown
    allValue: Optional[str] = None  # Custom value for "All" (e.g. ".*")
    default: Optional[str] = None  # Default selected value
    hide: int = 0  # 0=visible, 1=label-only, 2=hidden
    skipUrlSync: bool = False  # Exclude from URL state
    # For query / datasource variables (GAP-VAR-01/02)
    regex: Optional[str] = None  # Regex filter applied to the variable's values
    datasource_var: Optional[str] = None  # Datasource-UID binding, e.g. "${ds}"

    @field_validator("hide")
    @classmethod
    def validate_hide(cls, v: int) -> int:
        if v not in {0, 1, 2}:
            raise ValueError(
                f"hide must be 0 (visible), 1 (label-only), or 2 (hidden), got {v}"
            )
        return v

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
        query_types = {
            VariableType.CUSTOM,
            VariableType.QUERY,
            VariableType.INTERVAL,
        }
        if self.type in query_types and not self.query:
            raise ValueError(
                f"Variable '{self.name}' ({self.type.value}) requires 'query'"
            )
        if self.type == VariableType.CONSTANT and not self.value:
            raise ValueError(
                f"Variable '{self.name}' (constantVariable) requires 'value'"
            )
        if self.allValue is not None and not self.includeAll:
            raise ValueError(
                f"Variable '{self.name}': allValue requires includeAll=True"
            )
        return self


class DashboardLink(BaseModel):
    """A dashboard-level link (external URL or tag-based dashboard list)."""

    title: str
    url: str = ""  # Empty for type="dashboards" (tag-based)
    icon: str = "external link"
    tooltip: str = ""
    targetBlank: bool = True
    type: str = "link"  # "link" or "dashboards"
    tags: List[str] = Field(default_factory=list)
    asDropdown: bool = False  # Show matching dashboards as dropdown
    includeVars: bool = False  # Forward current variable values
    keepTime: bool = False  # Preserve current time range


class DataLink(BaseModel):
    """A data link attached to panel field values (e.g. drill-down URLs)."""

    title: str
    url: str
    targetBlank: bool = True


class TransformSpec(BaseModel):
    """A Grafana panel transformation (e.g. organize, calculateField)."""

    id: str  # e.g. "organize", "calculateField", "filterByValue"
    options: Dict[str, Any] = Field(default_factory=dict)


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
    links: List[DashboardLink] = Field(default_factory=list)
    refresh: Optional[str] = None  # Hydrated from config (DC-005)
    timezone: Optional[str] = None  # Hydrated from config (DC-005)
    time_from: Optional[str] = None  # Hydrated from config (DC-005)
    time_to: Optional[str] = None  # Hydrated from config (DC-005)
    config_overrides: Dict[str, Any] = Field(default_factory=dict)
    # Phase 3 layout/intent (AES-050/051)
    density: str = "operational"  # "operational" (dense) | "executive" (larger, more whitespace)
    objective: Optional[str] = None  # One-line dashboard objective; renders a banner header
    banner: bool = False  # Force a banner header even without an objective

    @field_validator("density")
    @classmethod
    def validate_density(cls, v: str) -> str:
        if v not in {"operational", "executive"}:
            raise ValueError(
                f"density must be 'operational' or 'executive', got '{v}'"
            )
        return v
