"""Deterministic Perses lowering for the bounded neutral dashboard core."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..neutral import (
    Dashboard,
    Panel,
    Query,
    QueryLanguage,
    StaticListVariable,
    VisualizationKind,
)


class PersesCapabilityError(ValueError):
    """The neutral intent cannot be represented by the pinned Perses subset."""


_PERSES_FORMATS = {
    "count": "decimal",
    "short": "decimal",
    "percent": "percent",
    "percentunit": "percent-decimal",
    "currencyUSD": "usd",
    "bytes": "bytes",
    "seconds": "seconds",
    "milliseconds": "milliseconds",
}


def _datasource(query: Query) -> Any:
    name = query.datasource.name
    if name.startswith("$"):
        return name
    kind = {
        QueryLanguage.PROMQL: "PrometheusDatasource",
        QueryLanguage.LOGQL: "LokiDatasource",
    }[query.language]
    return {"kind": kind, "name": name}


def _query(query: Query) -> Dict[str, Any]:
    if query.instant:
        raise PersesCapabilityError(
            "Perses lowering does not yet support neutral instant queries; "
            f"query {query.ref_id!r} must remain on the Grafana target"
        )
    if query.language == QueryLanguage.PROMQL:
        outer_kind = "TimeSeriesQuery"
        plugin_kind = "PrometheusTimeSeriesQuery"
    elif query.language == QueryLanguage.LOGQL:
        outer_kind = "LogQuery"
        plugin_kind = "LokiLogQuery"
    else:  # pragma: no cover - exhaustive Enum guard
        raise PersesCapabilityError(f"unsupported query language {query.language!r}")
    return {
        "kind": outer_kind,
        "spec": {
            "name": query.ref_id,
            "plugin": {
                "kind": plugin_kind,
                "spec": {
                    "datasource": _datasource(query),
                    "query": query.expression,
                },
            },
        },
    }


def _format(unit: Optional[str]) -> Optional[Dict[str, str]]:
    if unit is None:
        return None
    mapped = _PERSES_FORMATS.get(unit)
    if mapped is None:
        raise PersesCapabilityError(
            f"unit {unit!r} has no reviewed Perses mapping in the pinned portable subset"
        )
    return {"unit": mapped}


def _time_series_plugin(panel: Panel) -> Dict[str, Any]:
    spec: Dict[str, Any] = {}
    fmt = _format(panel.unit)
    if fmt is not None:
        spec["yAxis"] = {"format": fmt}
    if panel.thresholds:
        baseline = next((t for t in panel.thresholds if t.value is None), None)
        steps = [
            {"value": threshold.value, "color": threshold.color}
            for threshold in panel.thresholds
            if threshold.value is not None
        ]
        thresholds: Dict[str, Any] = {"mode": "absolute", "steps": steps}
        if baseline is not None:
            thresholds["defaultColor"] = baseline.color
        spec["thresholds"] = thresholds
    return {"kind": "TimeSeriesChart", "spec": spec}


def _panel(panel: Panel) -> Dict[str, Any]:
    if panel.visualization == VisualizationKind.MARKDOWN:
        plugin = {"kind": "Markdown", "spec": {"text": panel.markdown or ""}}
    elif panel.visualization == VisualizationKind.TIME_SERIES:
        plugin = _time_series_plugin(panel)
    elif panel.visualization == VisualizationKind.LOGS:
        plugin = {
            "kind": "LogsTable",
            "spec": {"allowWrap": True, "enableDetails": True, "showTime": True},
        }
    else:  # pragma: no cover - exhaustive Enum guard
        raise PersesCapabilityError(
            f"visualization {panel.visualization!r} is outside the pinned Perses subset"
        )

    spec: Dict[str, Any] = {"display": {"name": panel.title}, "plugin": plugin}
    if panel.description:
        spec["display"]["description"] = panel.description
    if panel.queries:
        spec["queries"] = [_query(query) for query in panel.queries]
    return {"kind": "Panel", "spec": spec}


def _variable(variable: StaticListVariable) -> Dict[str, Any]:
    # Perses v0.54's published CUE leaves defaultValue unconstrained while the API accepts only a string
    # or list of strings. Preserve trust in the oracle: only the schema-validated subset is emitted for now.
    if variable.current is not None:
        raise PersesCapabilityError(
            f"static variable {variable.name!r} has an explicit current value; Perses v0.54's "
            "published CUE does not constrain the API's defaultValue representation, so this cannot be "
            "lowered safely until the upstream contract is resolved"
        )
    return {
        "kind": "ListVariable",
        "spec": {
            "name": variable.name,
            "allowAllValue": False,
            "allowMultiple": variable.multi,
            "plugin": {
                "kind": "StaticListVariable",
                "spec": {"values": list(variable.values)},
            },
        },
    }


def emit_perses_dashboard(
    dashboard: Dashboard,
    *,
    project: str = "default",
    validate: bool = True,
    cue_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Lower a portable dashboard to the Perses v0.54 resource shape.

    The neutral model cannot contain tabs/conditions/auto-grid or arbitrary plugin payloads, so those
    target-only capabilities are unrepresentable by construction. Reviewed partial mappings (currently
    instant queries, unknown units, and explicit static-variable defaults) fail loudly here.
    """

    layouts: List[Dict[str, Any]] = []
    for section in dashboard.sections:
        display: Dict[str, Any] = {
            "title": section.title,
            "collapse": {"open": not section.collapsed},
        }
        layouts.append(
            {
                "kind": "Grid",
                "spec": {
                    "display": display,
                    "items": [
                        {
                            "x": placement.x,
                            "y": placement.y,
                            "width": placement.width,
                            "height": placement.height,
                            "content": {"$ref": f"#/spec/panels/{placement.panel}"},
                        }
                        for placement in section.placements
                    ],
                },
            }
        )

    spec: Dict[str, Any] = {
        "display": {"name": dashboard.title, "description": dashboard.description},
        "duration": dashboard.duration,
        "panels": {key: _panel(panel) for key, panel in dashboard.panels.items()},
        "layouts": layouts,
    }
    if dashboard.variables:
        spec["variables"] = [_variable(variable) for variable in dashboard.variables]
    resource = {
        "kind": "Dashboard",
        "metadata": {"name": dashboard.name, "project": project, "tags": list(dashboard.tags)},
        "spec": spec,
    }
    if validate:
        from .validate import validate_perses_dashboard

        validate_perses_dashboard(resource, cue_binary=cue_binary)
    return resource


def perses_json(dashboard: Dict[str, Any]) -> str:
    """Canonical Perses JSON bytes used by goldens and validation."""

    return json.dumps(dashboard, sort_keys=True, indent=2) + "\n"
