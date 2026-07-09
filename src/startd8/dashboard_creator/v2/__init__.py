"""Grafana **v2 dynamic-schema** dashboard emit path (dynamic-dashboards M1).

A *second, additive* emit target alongside the untouched classic (`schemaVersion: 39`, jsonnet) path —
it emits Grafana ≥13.1 ``dashboard.grafana.app/v2`` JSON (``apiVersion``/``kind``/``spec{elements,
layout, variables}``) **directly from Python** (no jsonnet — OQ-2, verified in the M0 spike). Classic
``DashboardSpec``/`generator`/`compiler`/`json_validator` are **not touched** (NR-1/FR-10); v2 has its own
model tree, which also dissolves the classic-only ``panels min_length=1`` invariant (R1-S9 — a layout-only
v2 board is legal here).

Construct names + envelope shape are the M0-verified authority
(`docs/design/dynamic-dashboards/m0-spike/`). M1 ships the **foundation**: the envelope, ``Panel``
elements, ``GridLayout``/``RowsLayout``, and ``CustomVariable`` (= the FR-8 ``audience`` variable). Tabs
(M2), conditional rendering (M3), and section-level variables (M4) extend this cleanly.
"""

from __future__ import annotations

from .emitter import emit_v2_dashboard, persist_v2_dashboard, v2_json
from .models import (
    V2_API_VERSION,
    V2_KIND,
    AutoGridItem,
    AutoGridLayout,
    ConditionalRendering,
    CustomVariable,
    DataCondition,
    GridItem,
    GridLayout,
    RowsLayout,
    RowsLayoutRow,
    TabsLayout,
    TabsLayoutTab,
    TimeRangeSizeCondition,
    V2Panel,
    V2ValidationError,
    VariableCondition,
    show_when_variable,
    text_panel,
)

__all__ = [
    "V2_API_VERSION",
    "V2_KIND",
    "AutoGridItem",
    "AutoGridLayout",
    "ConditionalRendering",
    "CustomVariable",
    "DataCondition",
    "GridItem",
    "GridLayout",
    "RowsLayout",
    "RowsLayoutRow",
    "TabsLayout",
    "TabsLayoutTab",
    "TimeRangeSizeCondition",
    "V2Panel",
    "V2ValidationError",
    "VariableCondition",
    "show_when_variable",
    "text_panel",
    "emit_v2_dashboard",
    "persist_v2_dashboard",
    "v2_json",
]
