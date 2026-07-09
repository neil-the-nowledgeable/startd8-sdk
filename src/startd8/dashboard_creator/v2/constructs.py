"""The M0-verified v2 construct allowlists — the single in-code source (dynamic-dashboards M5, NR-6).

These mirror `docs/design/dynamic-dashboards/m0-spike/v2-construct-names.json` (a test asserts they do not
drift). The validator (`validate.py`) uses them to reject **out-of-scope** v2 constructs — a layout or
variable kind the SDK does not support — so scope creep is caught, not silently emitted (R1-F7 / NR-6).
Viz/data kinds (e.g. ``text``, ``QueryGroup``) are panel internals and legitimately varied, so they are
**not** allowlisted here.
"""

from __future__ import annotations

#: The v2 envelope identifiers.
V2_API_VERSION = "dashboard.grafana.app/v2"
V2_KIND = "Dashboard"

#: The four supported layout kinds (FR-4).
LAYOUT_KINDS = frozenset({"GridLayout", "AutoGridLayout", "TabsLayout", "RowsLayout"})

#: Container/item kinds within a layout.
LAYOUT_ITEM_KINDS = frozenset(
    {
        "GridLayoutItem",
        "AutoGridLayoutItem",
        "RowsLayoutRow",
        "TabsLayoutTab",
        "ElementReference",
    }
)

#: Conditional-rendering construct kinds (FR-2).
CONDITION_KINDS = frozenset(
    {
        "ConditionalRenderingGroup",
        "ConditionalRenderingVariable",
        "ConditionalRenderingData",
        "ConditionalRenderingTimeRangeSize",
    }
)

#: Supported variable kinds (M1–M4 scope: the audience-style allowlist only). A board using any other
#: ``*Variable`` kind (Query/Datasource/Adhoc/…) is out of scope until a later milestone adds it.
VARIABLE_KINDS = frozenset({"CustomVariable"})
