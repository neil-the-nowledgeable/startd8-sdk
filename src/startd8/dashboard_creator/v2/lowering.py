"""Grafana ``dashboard.grafana.app/v2`` lowering for the portable neutral core.

The legacy v2 model remains available for explicit Grafana-only capabilities. This lowering is the
behavior-preserving migration seam: portable producers can move to the neutral source model while the
existing emitter and canonical serializer continue to own the exact Grafana bytes.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..neutral import (
    Dashboard,
    Panel,
    Query,
    QueryLanguage,
    VisualizationKind,
)
from .emitter import emit_v2_dashboard
from .models import (
    CustomVariable,
    GridItem,
    RowsLayout,
    RowsLayoutRow,
    V2Panel,
    text_panel,
)


def _query_v2(query: Query) -> Dict[str, Any]:
    group = {
        QueryLanguage.PROMQL: "prometheus",
        QueryLanguage.LOGQL: "loki",
    }[query.language]
    spec: Dict[str, Any] = {"expr": query.expression, "refId": query.ref_id}
    if query.instant:
        spec["queryType"] = "instant"
    return {
        "kind": "PanelQuery",
        "spec": {
            "refId": query.ref_id,
            "hidden": False,
            "query": {
                "kind": "DataQuery",
                "group": group,
                "version": "v0",
                "datasource": {"name": query.datasource.name},
                "spec": spec,
            },
        },
    }


def _data_v2(queries: List[Query]) -> Dict[str, Any]:
    return {
        "kind": "QueryGroup",
        "spec": {
            "queries": [_query_v2(q) for q in queries],
            "transformations": [],
            "queryOptions": {},
        },
    }


def _panel_v2(panel: Panel) -> V2Panel:
    if panel.visualization == VisualizationKind.MARKDOWN:
        return text_panel(
            panel.id,
            panel.title,
            panel.markdown or "",
            description=panel.description,
        )

    defaults: Dict[str, Any] = {}
    if panel.unit is not None:
        defaults["unit"] = panel.unit
    if panel.thresholds:
        defaults["thresholds"] = {
            "mode": "absolute",
            "steps": [t.model_dump() for t in panel.thresholds],
        }

    if panel.visualization == VisualizationKind.TIME_SERIES:
        viz_kind = "timeseries"
        options: Dict[str, Any] = {}
    elif panel.visualization == VisualizationKind.LOGS:
        viz_kind = "logs"
        options = {
            "showTime": True,
            "showLabels": False,
            "wrapLogMessage": True,
            "enableLogDetails": True,
            "sortOrder": "Ascending",
            "dedupStrategy": "none",
        }
    else:  # pragma: no cover - exhaustive Enum guard
        raise ValueError(f"unsupported portable visualization {panel.visualization!r}")

    return V2Panel(
        id=panel.id,
        title=panel.title,
        description=panel.description,
        viz_config={
            "kind": viz_kind,
            "spec": {
                "options": options,
                "fieldConfig": {"defaults": defaults, "overrides": []},
            },
        },
        data=_data_v2(panel.queries),
    )


def lower_dashboard_to_grafana_v2(dashboard: Dashboard) -> Dict[str, Any]:
    """Lower a portable dashboard through the retained byte-stable Grafana v2 emitter."""

    elements = {key: _panel_v2(panel) for key, panel in dashboard.panels.items()}
    rows = [
        RowsLayoutRow(
            title=section.title,
            collapse=section.collapsed,
            items=[
                GridItem(
                    element=placement.panel,
                    x=placement.x,
                    y=placement.y,
                    width=placement.width,
                    height=placement.height,
                )
                for placement in section.placements
            ],
        )
        for section in dashboard.sections
    ]
    variables = [
        CustomVariable(
            name=variable.name,
            options=variable.values,
            current=variable.current,
            multi=variable.multi,
        )
        for variable in dashboard.variables
    ]
    time_settings = {
        "from": f"now-{dashboard.duration}",
        "to": "now",
        "autoRefresh": "",
        "autoRefreshIntervals": [],
        "hideTimepicker": False,
        "timezone": "browser",
    }
    return emit_v2_dashboard(
        name=dashboard.name,
        title=dashboard.title,
        description=dashboard.description,
        tags=dashboard.tags,
        variables=variables,
        elements=elements,
        layout=RowsLayout(rows=rows),
        time_settings=time_settings,
    )
