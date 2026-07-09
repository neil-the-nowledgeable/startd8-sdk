"""v2 dynamic-schema model tree (dynamic-dashboards M1 foundation).

Every construct name + nested shape here is the **M0-verified authority** (round-tripped intact through
live Grafana 13.1.0; see `docs/design/dynamic-dashboards/m0-spike/v2-construct-names.json`). Each model
emits its Grafana `{kind, spec}` dict via ``to_v2()``. Deterministic by construction (no ordering choices
that the serializer's ``sort_keys=True`` doesn't already fix).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

#: The M0-verified envelope identifiers (do not hardcode elsewhere — import these).
V2_API_VERSION = "dashboard.grafana.app/v2"
V2_KIND = "Dashboard"


class V2ValidationError(ValueError):
    """A v2 spec is malformed or opts in incorrectly (mirrors the classic validator's error style)."""


# --- elements (leaf panels) ---------------------------------------------------------------------


def _empty_query_group() -> Dict[str, Any]:
    """A no-target QueryGroup — valid for text/markdown panels that carry no datasource query."""
    return {
        "kind": "QueryGroup",
        "spec": {"queries": [], "transformations": [], "queryOptions": {}},
    }


def _text_viz(content: str) -> Dict[str, Any]:
    return {
        "kind": "text",
        "spec": {
            "options": {"content": content, "mode": "markdown"},
            "fieldConfig": {"defaults": {}, "overrides": []},
        },
    }


class V2Panel(BaseModel):
    """A v2 ``Panel`` element (a leaf, positioned by the *layout*, not by gridPos).

    ``viz_config`` is a Grafana ``{kind, spec}`` viz descriptor; ``data`` a ``QueryGroup``. Both default
    to a no-op text/empty shape so a foundation board needs no datasource. Richer panels pass through a
    prepared ``viz_config``/``data`` (the classic PanelSpec→viz mapping is reused by later consumers).
    """

    id: int
    title: str = ""
    description: str = ""
    viz_config: Dict[str, Any] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)
    links: List[Dict[str, Any]] = Field(default_factory=list)

    def to_v2(self) -> Dict[str, Any]:
        return {
            "kind": "Panel",
            "spec": {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "links": list(self.links),
                "data": self.data or _empty_query_group(),
                "vizConfig": self.viz_config or _text_viz(""),
            },
        }


def text_panel(id: int, title: str, content: str, *, description: str = "") -> V2Panel:
    """A markdown/text ``Panel`` element (the Workbook's dominant panel kind)."""
    return V2Panel(
        id=id, title=title, description=description, viz_config=_text_viz(content)
    )


# --- layouts ------------------------------------------------------------------------------------


class GridItem(BaseModel):
    """One placed element inside a ``GridLayout`` (``GridLayoutItem`` → ``ElementReference``)."""

    element: str  # the key in spec.elements this item references
    x: int = 0
    y: int = 0
    width: int = 24
    height: int = 8

    def to_v2(self) -> Dict[str, Any]:
        return {
            "kind": "GridLayoutItem",
            "spec": {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
                "element": {"kind": "ElementReference", "name": self.element},
            },
        }


class GridLayout(BaseModel):
    """The flat ``GridLayout`` (x/y/width/height items). The simplest v2 layout."""

    items: List[GridItem] = Field(default_factory=list)

    def to_v2(self) -> Dict[str, Any]:
        return {
            "kind": "GridLayout",
            "spec": {"items": [i.to_v2() for i in self.items]},
        }


class RowsLayoutRow(BaseModel):
    """One ``RowsLayoutRow`` — a titled, optionally-collapsed section wrapping a nested layout.

    By default the ``items`` are wrapped in a ``GridLayout`` (the M1 shorthand). For richer nesting (M2),
    pass an explicit ``layout`` (any v2 layout — e.g. an ``AutoGridLayout`` or another ``RowsLayout``);
    when set it takes precedence over ``items``.
    """

    title: str = ""
    collapse: bool = False
    items: List[GridItem] = Field(default_factory=list)
    layout: Any = None  # an explicit nested layout; None ⇒ wrap `items` in a GridLayout

    def to_v2(self) -> Dict[str, Any]:
        sub = self.layout if self.layout is not None else GridLayout(items=self.items)
        return {
            "kind": "RowsLayoutRow",
            "spec": {
                "title": self.title,
                "collapse": self.collapse,
                "layout": _sub_layout_v2(sub),
            },
        }


class RowsLayout(BaseModel):
    """The ``RowsLayout`` (stacked titled rows). The Workbook's per-domain sectioning maps here."""

    rows: List[RowsLayoutRow] = Field(default_factory=list)

    def to_v2(self) -> Dict[str, Any]:
        return {"kind": "RowsLayout", "spec": {"rows": [r.to_v2() for r in self.rows]}}


class AutoGridItem(BaseModel):
    """One element in an ``AutoGridLayout`` (auto-placed — no x/y/width/height)."""

    element: str

    def to_v2(self) -> Dict[str, Any]:
        return {
            "kind": "AutoGridLayoutItem",
            "spec": {"element": {"kind": "ElementReference", "name": self.element}},
        }


class AutoGridLayout(BaseModel):
    """The ``AutoGridLayout`` — Grafana auto-places items into a responsive grid (no manual gridPos)."""

    items: List[AutoGridItem] = Field(default_factory=list)
    max_column_count: int = 3
    column_width_mode: str = "standard"
    row_height_mode: str = "standard"
    fill_screen: bool = False

    def to_v2(self) -> Dict[str, Any]:
        return {
            "kind": "AutoGridLayout",
            "spec": {
                "maxColumnCount": self.max_column_count,
                "columnWidthMode": self.column_width_mode,
                "rowHeightMode": self.row_height_mode,
                "fillScreen": self.fill_screen,
                "items": [i.to_v2() for i in self.items],
            },
        }


class TabsLayoutTab(BaseModel):
    """One ``TabsLayoutTab`` — a titled tab wrapping any nested layout (rows/grid/auto-grid/tabs)."""

    title: str = ""
    items: List[GridItem] = Field(default_factory=list)
    layout: Any = None  # explicit nested layout; None ⇒ wrap `items` in a GridLayout

    def to_v2(self) -> Dict[str, Any]:
        sub = self.layout if self.layout is not None else GridLayout(items=self.items)
        return {
            "kind": "TabsLayoutTab",
            "spec": {"title": self.title, "layout": _sub_layout_v2(sub)},
        }


class TabsLayout(BaseModel):
    """The ``TabsLayout`` (top-level tabbed sections). Each tab carries its own nested layout."""

    tabs: List[TabsLayoutTab] = Field(default_factory=list)

    def to_v2(self) -> Dict[str, Any]:
        return {"kind": "TabsLayout", "spec": {"tabs": [t.to_v2() for t in self.tabs]}}


Layout = Union[GridLayout, RowsLayout, AutoGridLayout, TabsLayout]


def _sub_layout_v2(layout: Any) -> Dict[str, Any]:
    """Render a nested layout to its ``{kind, spec}`` dict — accepts any object exposing ``to_v2()``
    (the four v2 layout kinds). Fails loud on a non-layout so a bad nesting never ships a broken board.
    """
    if not hasattr(layout, "to_v2"):
        raise V2ValidationError(
            f"nested layout must be a v2 layout (GridLayout/RowsLayout/AutoGridLayout/TabsLayout), "
            f"got {type(layout).__name__}"
        )
    return layout.to_v2()


# --- variables ----------------------------------------------------------------------------------


class CustomVariable(BaseModel):
    """A ``CustomVariable`` — a fixed enumerated allowlist (the FR-8 ``audience`` variable shape).

    Deliberately the *only* variable kind M1 ships: it is a client-side allowlist, not a query/datasource
    variable, which is the shape FR-8 requires for the audience toggle (R1-F8 safety).
    """

    name: str
    options: List[str]
    current: Optional[str] = None
    hide: str = "dontHide"
    multi: bool = False
    include_all: bool = False

    def to_v2(self) -> Dict[str, Any]:
        cur = (
            self.current
            if self.current is not None
            else (self.options[0] if self.options else "")
        )
        return {
            "kind": "CustomVariable",
            "spec": {
                "name": self.name,
                "query": ",".join(self.options),
                "current": {"text": cur, "value": cur},
                "options": [
                    {"text": o, "value": o, "selected": o == cur} for o in self.options
                ],
                "multi": self.multi,
                "includeAll": self.include_all,
                "hide": self.hide,
                "skipUrlSync": False,
            },
        }
