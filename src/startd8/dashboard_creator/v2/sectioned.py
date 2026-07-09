"""Generic **sectioned** v2 dashboard builder (dynamic-dashboards M7 — broaden beyond the Workbook).

The Workbook (M6) is one v2 consumer; M7 proves the capability generalizes to the plan's other named
use cases — **fleet** (a tab per service, each with a per-service section filter), **gov-budget** (a row
per department, with dashboard-level year variables + conditional sections), **o11y-artifact** boards —
via ONE reusable primitive rather than a heavy per-generator integration.

``build_sectioned_v2`` composes the shipped v2 models (``TabsLayout``/``RowsLayout`` + section
``variables`` + ``ConditionalRendering``) — it duplicates none of their logic. Each :class:`Section`
becomes a tab or row carrying its panels, an optional **section-level variable** (M4), and optional
**conditional visibility** (M3, ``show_when``). Deterministic element keys (``sec{S}-p{P}``); the result
validates against the M0 schema and round-trips through Grafana 13.1.

Per-generator *adoption* (wiring the real observability/fleet generators to emit v2) is follow-on; this
module is the reusable seam they build on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import (
    CustomVariable,
    GridItem,
    RowsLayout,
    RowsLayoutRow,
    TabsLayout,
    TabsLayoutTab,
    V2Panel,
    V2ValidationError,
    show_when_variable,
    text_panel,
)
from .emitter import emit_v2_dashboard

#: A panel spec: a ready ``V2Panel``, or ``(title, markdown_str)`` (a text panel), or
#: ``(title, viz_config_dict)`` (a passthrough viz).
PanelSpec = Union[V2Panel, Tuple[str, Any]]


@dataclass
class Section:
    """One section of a sectioned board — a tab (``layout_kind="tabs"``) or a row (``"rows"``).

    - ``panels``: the section's panels (see :data:`PanelSpec`).
    - ``section_variable``: an optional section-scoped ``CustomVariable`` (M4) filtering only this
      section (e.g. a per-service or per-department selector).
    - ``show_when``: an optional ``(variable, value)`` — the section shows only when that dashboard
      variable equals ``value`` (M3 conditional visibility).
    """

    title: str
    panels: List[PanelSpec] = field(default_factory=list)
    section_variable: Optional[CustomVariable] = None
    show_when: Optional[Tuple[str, str]] = None


def _panel(pid: int, spec: PanelSpec) -> V2Panel:
    if isinstance(spec, V2Panel):
        return spec
    if isinstance(spec, tuple) and len(spec) == 2:
        title, content = spec
        if isinstance(content, str):
            return text_panel(pid, title, content)
        if isinstance(content, dict):
            return V2Panel(id=pid, title=title, viz_config=content)
    raise V2ValidationError(
        "each panel must be a V2Panel or a (title, markdown|viz_config) tuple, "
        f"got {type(spec).__name__}"
    )


def build_sectioned_v2(
    *,
    name: str,
    title: str,
    sections: List[Section],
    layout_kind: str = "tabs",
    dashboard_variables: Optional[List[CustomVariable]] = None,
    tags: Optional[List[str]] = None,
    description: str = "",
) -> Dict[str, Any]:
    """Build a sectioned v2 board — one tab or row per :class:`Section`.

    ``layout_kind`` is ``"tabs"`` (a ``TabsLayout``) or ``"rows"`` (a ``RowsLayout``). Panels within a
    section stack vertically. Returns the deterministic v2 envelope dict (feed to ``v2_json`` /
    ``provision_v2``). Fails loud on an unknown ``layout_kind`` or a malformed panel.
    """
    if layout_kind not in ("tabs", "rows"):
        raise V2ValidationError(
            f"layout_kind must be 'tabs' or 'rows', got {layout_kind!r}"
        )

    elements: Dict[str, V2Panel] = {}
    tabs: List[TabsLayoutTab] = []
    rows: List[RowsLayoutRow] = []

    for s_idx, section in enumerate(sections):
        items: List[GridItem] = []
        for p_idx, pspec in enumerate(section.panels):
            key = f"sec{s_idx}-p{p_idx}"
            # element id is an int; derive a stable one from the section/panel index
            elements[key] = _panel(s_idx * 100 + p_idx + 1, pspec)
            items.append(GridItem(element=key, height=6))

        conditional = (
            show_when_variable(section.show_when[0], section.show_when[1])
            if section.show_when
            else None
        )
        section_vars = [section.section_variable] if section.section_variable else []

        if layout_kind == "tabs":
            tabs.append(
                TabsLayoutTab(
                    title=section.title,
                    items=items,
                    conditional=conditional,
                    variables=section_vars,
                )
            )
        else:
            rows.append(
                RowsLayoutRow(
                    title=section.title,
                    items=items,
                    conditional=conditional,
                    variables=section_vars,
                )
            )

    layout = TabsLayout(tabs=tabs) if layout_kind == "tabs" else RowsLayout(rows=rows)
    return emit_v2_dashboard(
        name=name,
        title=title,
        description=description,
        tags=list(tags or []),
        variables=dashboard_variables or [],
        elements=elements,
        layout=layout,
    )
