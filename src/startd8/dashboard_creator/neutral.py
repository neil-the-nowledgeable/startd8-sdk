"""Typed, target-neutral dashboard vocabulary for the Perses-portable subset.

This module deliberately contains no ``to_v2``/Grafana schema names and no free-form plugin payloads.
It captures semantic intent that both the retained Grafana lowering and the Perses lowering can
represent without silently changing behavior. Target-only capabilities stay in ``dashboard_creator.v2``.

The boundary is grounded by ``docs/design/dashboard-vendor-neutrality/T0_perses-coverage-matrix.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class VisualizationKind(str, Enum):
    """Panel kinds covered by the pinned Perses portable-subset decision."""

    MARKDOWN = "markdown"
    TIME_SERIES = "time_series"
    LOGS = "logs"


class QueryLanguage(str, Enum):
    """Query languages currently emitted by portable startd8 dashboards."""

    PROMQL = "promql"
    LOGQL = "logql"


class DatasourceRef(BaseModel):
    """A logical datasource reference; target lowerings choose their own wrapper shape."""

    name: str


class Query(BaseModel):
    """A typed dashboard query without Grafana QueryGroup/DataQuery wrappers."""

    expression: str
    language: QueryLanguage
    datasource: DatasourceRef
    ref_id: str = "A"
    instant: bool = False


class Threshold(BaseModel):
    """One absolute threshold transition in semantic form."""

    value: Optional[float] = None
    color: str


class Panel(BaseModel):
    """A portable panel: visualization intent plus typed queries and common presentation fields."""

    id: int
    title: str = ""
    description: str = ""
    visualization: VisualizationKind
    queries: List[Query] = Field(default_factory=list)
    markdown: Optional[str] = None
    unit: Optional[str] = None
    thresholds: List[Threshold] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_kind_payload(self) -> "Panel":
        if self.visualization == VisualizationKind.MARKDOWN:
            if self.markdown is None:
                raise ValueError("a markdown panel requires markdown content")
            if self.queries:
                raise ValueError("a markdown panel cannot carry datasource queries")
        elif self.markdown is not None:
            raise ValueError("markdown content is only valid for a markdown panel")

        expected = {
            VisualizationKind.TIME_SERIES: QueryLanguage.PROMQL,
            VisualizationKind.LOGS: QueryLanguage.LOGQL,
        }.get(self.visualization)
        if expected is not None:
            wrong = [q.language.value for q in self.queries if q.language != expected]
            if wrong:
                raise ValueError(
                    f"{self.visualization.value} panels require {expected.value} queries; got {wrong}"
                )
        return self


class Placement(BaseModel):
    """Explicit, deterministic grid placement of a panel within a section."""

    panel: str
    x: int = 0
    y: int = 0
    width: int = 24
    height: int = 8


class Section(BaseModel):
    """An ordered titled section; maps to Grafana row or a Perses Grid layout."""

    title: str = ""
    collapsed: bool = False
    placements: List[Placement] = Field(default_factory=list)


class StaticListVariable(BaseModel):
    """A dashboard-level fixed allowlist variable."""

    name: str
    values: List[str]
    current: Optional[str] = None
    multi: bool = False

    @model_validator(mode="after")
    def _validate_current(self) -> "StaticListVariable":
        if self.current is not None and self.current not in self.values:
            raise ValueError("current must be one of the static-list values")
        return self


class Dashboard(BaseModel):
    """The frozen in-process portable dashboard source model."""

    name: str
    title: str
    panels: Dict[str, Panel] = Field(default_factory=dict)
    sections: List[Section] = Field(default_factory=list)
    variables: List[StaticListVariable] = Field(default_factory=list)
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    duration: str = "6h"

    @model_validator(mode="after")
    def _validate_references(self) -> "Dashboard":
        referenced = {p.panel for section in self.sections for p in section.placements}
        missing = sorted(referenced - set(self.panels))
        if missing:
            raise ValueError(
                f"section placements reference undeclared panel(s): {missing}"
            )
        return self
