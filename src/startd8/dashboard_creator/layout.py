"""
Row auto-grouping and GridPos auto-layout (DC-108, DC-109).

Transforms a flat list of PanelSpec into a properly ordered and
positioned list ready for Jsonnet generation.
"""

from typing import List, Optional

from startd8.dashboard_creator.models import DashboardSpec, GridPos, PanelSpec, PanelType

_GRID_COLS = 24
_DEFAULT_H = 8
_DEFAULT_W = 12
_ROW_H = 1
_ROW_W = 24


def auto_group_rows(panels: List[PanelSpec]) -> List[PanelSpec]:
    """DC-108: Insert row panels to group panels by their ``group`` field.

    Ordering rules:
    - Panels without a group come first (ungrouped).
    - For each unique group, a ``PanelType.ROW`` panel is inserted before
      the group's members.  Groups are emitted in first-appearance order.
    - A group name starting with ``"+"`` produces a collapsed row
      (the ``"+"`` prefix is stripped from the row title).
    """
    ungrouped: List[PanelSpec] = []
    groups: dict[str, List[PanelSpec]] = {}
    group_order: List[str] = []

    for panel in panels:
        if panel.group is None:
            ungrouped.append(panel)
        else:
            if panel.group not in groups:
                groups[panel.group] = []
                group_order.append(panel.group)
            groups[panel.group].append(panel)

    result: List[PanelSpec] = list(ungrouped)

    for group_name in group_order:
        collapsed = group_name.startswith("+")
        title = group_name.lstrip("+").strip() if collapsed else group_name
        row = PanelSpec(
            type=PanelType.ROW,
            title=title,
            options={"collapsed": True} if collapsed else {},
        )
        result.append(row)
        result.extend(groups[group_name])

    return result


def auto_layout(panels: List[PanelSpec]) -> List[PanelSpec]:
    """DC-109: Calculate ``gridPos`` for panels without explicit positioning.

    Layout rules:
    - 24-column grid with default panel size ``h=8, w=12`` (two per row).
    - Row panels span full width (``w=24, h=1``) and reset the Y cursor.
    - Panels with an explicit ``gridPos`` are placed at their specified
      position; auto-layout fills around them.
    """
    result: List[PanelSpec] = []
    cursor_x = 0
    cursor_y = 0

    for panel in panels:
        if panel.type == PanelType.ROW:
            # Rows always start on a new line and span full width
            if cursor_x > 0:
                cursor_y += _DEFAULT_H
                cursor_x = 0
            updated = panel.model_copy(
                update={"gridPos": GridPos(h=_ROW_H, w=_ROW_W, x=0, y=cursor_y)},
            )
            result.append(updated)
            cursor_y += _ROW_H
            cursor_x = 0
            continue

        if panel.gridPos is not None:
            # Explicit positioning — place as-is and update cursor
            result.append(panel)
            panel_bottom = panel.gridPos.y + panel.gridPos.h
            if panel_bottom > cursor_y:
                cursor_y = panel_bottom
            continue

        w = _DEFAULT_W
        h = _DEFAULT_H

        # Wrap to next row if panel doesn't fit
        if cursor_x + w > _GRID_COLS:
            cursor_y += h
            cursor_x = 0

        updated = panel.model_copy(
            update={"gridPos": GridPos(h=h, w=w, x=cursor_x, y=cursor_y)},
        )
        result.append(updated)
        cursor_x += w

        # If we've filled the row, advance
        if cursor_x >= _GRID_COLS:
            cursor_y += h
            cursor_x = 0

    return result


def apply_layout(spec: DashboardSpec) -> DashboardSpec:
    """Convenience: apply row grouping then auto-layout to a spec.

    Returns a new ``DashboardSpec`` with updated panels.
    """
    panels = auto_group_rows(spec.panels)
    panels = auto_layout(panels)
    return spec.model_copy(update={"panels": panels})


def nest_collapsed_rows(dashboard: dict) -> dict:
    """DC-110 / REQ-DCR-AES-033: enforce Grafana's collapsed-row nesting invariant.

    Grafana requires a **collapsed** row to own the panels that follow it (up to the
    next row) via ``row["panels"]``; an **expanded** row (``collapsed: false``) leaves
    them as top-level siblings positioned by ``gridPos``. The generator emits collapsed
    rows with an empty ``panels: []`` and the content as top-level siblings — an invalid
    combination that Grafana's renderer mis-handles, swallowing the trailing sections
    (only the first few render). Verified against the play.grafana.org corpus: 244/248
    real collapsed rows nest their panels.

    This post-compile pass folds each collapsed row's trailing siblings into its
    ``panels[]``. Operates on the compiled dashboard JSON (panels already carry ``id``
    and ``gridPos``), is **pure on structure, idempotent**, and leaves expanded rows /
    row-less dashboards untouched.

    Args:
        dashboard: Compiled Grafana dashboard model (mutated in place and returned).

    Returns:
        The same ``dashboard`` dict with collapsed rows nesting their section panels.
    """
    panels = dashboard.get("panels")
    if not isinstance(panels, list):
        return dashboard

    result: List[dict] = []
    owner: Optional[dict] = None  # the open collapsed row currently absorbing siblings
    for panel in panels:
        if not isinstance(panel, dict):
            result.append(panel)
            continue
        if panel.get("type") == "row":
            # A row (collapsed or not) ends the previous collapsed row's ownership.
            owner = panel if panel.get("collapsed") else None
            if owner is not None and not isinstance(panel.get("panels"), list):
                panel["panels"] = []
            result.append(panel)
        elif owner is not None:
            owner["panels"].append(panel)  # nest under the open collapsed row
        else:
            result.append(panel)

    dashboard["panels"] = result
    return dashboard
