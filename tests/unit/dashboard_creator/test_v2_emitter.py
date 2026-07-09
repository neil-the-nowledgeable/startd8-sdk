"""Tests for the v2 dynamic-schema emitter (dynamic-dashboards M1 foundation).

Covers FR-1 (single opt-in trigger), FR-5 (deterministic bytes via the classic serializer + atomic
write), FR-10/NR-1 (classic path untouched, layout-only board legal — R1-S9), and structural
conformance against the M0-verified `v2-envelope-schema.json`. The live-Grafana round-trip is proven
separately in the M0 spike; these tests are offline/CI-safe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.dashboard_creator.v2 import (
    CustomVariable,
    GridItem,
    GridLayout,
    RowsLayout,
    RowsLayoutRow,
    V2ValidationError,
    emit_v2_dashboard,
    persist_v2_dashboard,
    text_panel,
    v2_json,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_M0_SCHEMA = _REPO / "docs/design/dynamic-dashboards/m0-spike/v2-envelope-schema.json"
_GOLDEN = Path(__file__).parent / "fixtures/v2_foundation.golden.json"


def _foundation() -> dict:
    return emit_v2_dashboard(
        name="m1-foundation",
        title="M1 Foundation",
        description="Deterministic v2 foundation golden",
        tags=["m1"],
        variables=[
            CustomVariable(
                name="audience",
                options=["beginner", "intermediate", "advanced"],
                current="intermediate",
            )
        ],
        elements={"panel-1": text_panel(1, "Overview", "**Foundation** panel")},
        layout=RowsLayout(
            rows=[
                RowsLayoutRow(
                    title="Section",
                    items=[GridItem(element="panel-1", width=24, height=6)],
                )
            ]
        ),
    )


# --- FR-1: single explicit opt-in trigger -------------------------------------------------------


def test_opt_in_trigger_requires_schema_v2():
    with pytest.raises(V2ValidationError, match="schema='v2'"):
        emit_v2_dashboard(
            name="x", title="x", schema="classic", layout=GridLayout(), elements={}
        )


def test_envelope_identifiers_are_the_m0_verified_constants():
    board = _foundation()
    assert board["apiVersion"] == "dashboard.grafana.app/v2"
    assert board["kind"] == "Dashboard"
    assert board["metadata"]["name"] == "m1-foundation"


# --- FR-5: deterministic bytes ------------------------------------------------------------------


def test_deterministic_bytes():
    assert v2_json(_foundation()) == v2_json(_foundation())


def test_matches_committed_golden():
    assert v2_json(_foundation()) == _GOLDEN.read_text(encoding="utf-8")


def test_serializer_is_the_classic_one():
    # FR-5/R1-S4: v2 uses the exact same dump call as output.py — sorted keys, 2-space indent, trailing \n
    s = v2_json(_foundation())
    assert s.endswith("}\n")
    assert s == json.dumps(_foundation(), sort_keys=True, indent=2) + "\n"


# --- structural conformance (M0 schema, offline CI) ---------------------------------------------


def test_validates_against_m0_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_M0_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(_foundation(), schema)  # raises on nonconformance


# --- element-reference integrity ----------------------------------------------------------------


def test_undeclared_element_reference_raises():
    with pytest.raises(V2ValidationError, match="undeclared element"):
        emit_v2_dashboard(
            name="x",
            title="x",
            elements={"panel-1": text_panel(1, "a", "b")},
            layout=GridLayout(items=[GridItem(element="panel-MISSING")]),
        )


def test_layout_only_board_is_legal_no_min_length(tmp_path):
    # R1-S9: a v2 board with zero elements + an empty layout is valid (classic min_length=1 doesn't apply)
    board = emit_v2_dashboard(
        name="empty", title="Empty", layout=RowsLayout(rows=[]), elements={}
    )
    assert board["spec"]["elements"] == {}
    assert board["spec"]["layout"]["kind"] == "RowsLayout"


# --- the audience CustomVariable (FR-8 shape) ---------------------------------------------------


def test_audience_custom_variable_is_a_fixed_allowlist():
    board = _foundation()
    var = board["spec"]["variables"][0]
    assert var["kind"] == "CustomVariable"  # not a query/datasource variable (R1-F8)
    assert var["spec"]["query"] == "beginner,intermediate,advanced"
    assert var["spec"]["current"] == {"text": "intermediate", "value": "intermediate"}
    selected = [o["value"] for o in var["spec"]["options"] if o["selected"]]
    assert selected == ["intermediate"]


# --- persistence reuses the classic atomic writer -----------------------------------------------


def test_persist_reuses_classic_atomic_writer(tmp_path):
    res = persist_v2_dashboard(_foundation(), output_dir=tmp_path)
    assert res.json_path == tmp_path / "m1-foundation.json"
    # byte-identical to the emitter's own serialization (same serializer, R2-S7)
    assert res.json_path.read_text(encoding="utf-8") == v2_json(_foundation())


def test_persist_requires_metadata_name():
    with pytest.raises(V2ValidationError, match="metadata.name"):
        persist_v2_dashboard(
            {"apiVersion": "dashboard.grafana.app/v2", "kind": "Dashboard", "spec": {}}
        )


# --- NR-1 / FR-10: classic path untouched -------------------------------------------------------


def test_classic_dashboardspec_still_requires_panels():
    # The classic invariant is unchanged — v2 has its own model tree, so relaxing min_length for v2
    # never touched classic (FR-10). A classic spec with no panels still fails.
    from pydantic import ValidationError

    from startd8.dashboard_creator.models import DashboardSpec

    with pytest.raises(ValidationError):
        DashboardSpec(title="t", panels=[])


# --- M2: tabs / auto-grid layout + nesting (FR-4) ------------------------------------------------

from startd8.dashboard_creator.v2 import (  # noqa: E402
    AutoGridItem,
    AutoGridLayout,
    TabsLayout,
    TabsLayoutTab,
)

_M2_GOLDEN = Path(__file__).parent / "fixtures/v2_tabs.golden.json"


def _tabs_board() -> dict:
    return emit_v2_dashboard(
        name="m2-tabs",
        title="M2 Tabs",
        tags=["m2"],
        elements={"p1": text_panel(1, "A", "**a**"), "p2": text_panel(2, "B", "**b**")},
        layout=TabsLayout(
            tabs=[
                TabsLayoutTab(
                    title="Rows",
                    layout=RowsLayout(
                        rows=[
                            RowsLayoutRow(
                                title="R1", items=[GridItem(element="p1", height=6)]
                            )
                        ]
                    ),
                ),
                TabsLayoutTab(
                    title="Auto",
                    layout=AutoGridLayout(
                        items=[AutoGridItem(element="p2")], max_column_count=2
                    ),
                ),
            ]
        ),
    )


def test_tabs_layout_two_tabs_nesting():
    # FR-4: a 2-tab board; tab0 nests a RowsLayout, tab1 an AutoGridLayout
    lay = _tabs_board()["spec"]["layout"]
    assert lay["kind"] == "TabsLayout"
    tabs = lay["spec"]["tabs"]
    assert [t["spec"]["title"] for t in tabs] == ["Rows", "Auto"]
    assert tabs[0]["spec"]["layout"]["kind"] == "RowsLayout"
    assert tabs[1]["spec"]["layout"]["kind"] == "AutoGridLayout"
    # the nested row wraps a GridLayout referencing p1
    row = tabs[0]["spec"]["layout"]["spec"]["rows"][0]
    assert row["kind"] == "RowsLayoutRow"
    assert row["spec"]["layout"]["kind"] == "GridLayout"


def test_auto_grid_layout_shape():
    board = emit_v2_dashboard(
        name="ag",
        title="ag",
        elements={"p1": text_panel(1, "a", "b")},
        layout=AutoGridLayout(
            items=[AutoGridItem(element="p1")], max_column_count=4, fill_screen=True
        ),
    )
    spec = board["spec"]["layout"]["spec"]
    assert spec["maxColumnCount"] == 4 and spec["fillScreen"] is True
    assert spec["columnWidthMode"] == "standard" and spec["rowHeightMode"] == "standard"
    assert spec["items"][0]["kind"] == "AutoGridLayoutItem"
    assert spec["items"][0]["spec"]["element"] == {
        "kind": "ElementReference",
        "name": "p1",
    }


def test_tabs_board_matches_golden():
    assert v2_json(_tabs_board()) == _M2_GOLDEN.read_text(encoding="utf-8")


def test_tabs_board_validates_against_m0_schema():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(
        _tabs_board(), json.loads(_M0_SCHEMA.read_text(encoding="utf-8"))
    )


def test_element_ref_validation_walks_nested_tabs():
    # an undeclared element referenced deep inside a tab→autogrid must fail loud (FR-11 intent)
    with pytest.raises(V2ValidationError, match="undeclared element"):
        emit_v2_dashboard(
            name="bad",
            title="bad",
            elements={"p1": text_panel(1, "a", "b")},
            layout=TabsLayout(
                tabs=[
                    TabsLayoutTab(
                        title="t",
                        layout=AutoGridLayout(items=[AutoGridItem(element="ghost")]),
                    )
                ]
            ),
        )


def test_row_explicit_layout_overrides_items():
    # RowsLayoutRow.layout (explicit) wins over the items shorthand
    row = RowsLayoutRow(
        title="r",
        items=[GridItem(element="ignored")],
        layout=AutoGridLayout(items=[AutoGridItem(element="p1")]),
    ).to_v2()
    assert row["spec"]["layout"]["kind"] == "AutoGridLayout"


def test_bad_nested_layout_fails_loud():
    with pytest.raises(V2ValidationError, match="nested layout must be"):
        TabsLayoutTab(title="t", layout="not-a-layout").to_v2()


# --- M3: conditional rendering (FR-2) ------------------------------------------------------------

from startd8.dashboard_creator.v2 import (  # noqa: E402
    ConditionalRendering,
    DataCondition,
    TimeRangeSizeCondition,
    VariableCondition,
    show_when_variable,
)

_M3_GOLDEN = Path(__file__).parent / "fixtures/v2_conditional.golden.json"


def _conditional_board() -> dict:
    return emit_v2_dashboard(
        name="m3-cond",
        title="M3 Conditional",
        tags=["m3"],
        variables=[
            CustomVariable(
                name="audience", options=["beginner", "intermediate", "advanced"]
            )
        ],
        elements={
            "p1": text_panel(1, "Shielded", "for beginners"),
            "p2": text_panel(2, "Adv", "x"),
        },
        layout=RowsLayout(
            rows=[
                RowsLayoutRow(
                    title="Beginner only",
                    items=[GridItem(element="p1", height=6)],
                    conditional=show_when_variable("audience", "beginner"),
                ),
                RowsLayoutRow(
                    title="Advanced AND has-data",
                    items=[GridItem(element="p2", height=6)],
                    conditional=ConditionalRendering(
                        condition="and",
                        items=[
                            VariableCondition(variable="audience", value="advanced"),
                            DataCondition(value=True),
                        ],
                    ),
                ),
            ]
        ),
    )


def test_show_when_variable_row():
    row0 = _conditional_board()["spec"]["layout"]["spec"]["rows"][0]["spec"]
    cr = row0["conditionalRendering"]
    assert cr["kind"] == "ConditionalRenderingGroup"
    assert cr["spec"]["visibility"] == "show" and cr["spec"]["condition"] == "and"
    item = cr["spec"]["items"][0]
    assert item["kind"] == "ConditionalRenderingVariable"
    assert item["spec"] == {
        "variable": "audience",
        "operator": "equals",
        "value": "beginner",
    }


def test_and_or_groups_and_all_three_condition_kinds():
    cond = ConditionalRendering(
        condition="or",
        visibility="hide",
        items=[
            VariableCondition(
                variable="audience", value="beginner", operator="notEquals"
            ),
            DataCondition(value=False),
            TimeRangeSizeCondition(value="24h"),
        ],
    ).to_v2()
    assert cond["spec"]["condition"] == "or" and cond["spec"]["visibility"] == "hide"
    kinds = [i["kind"] for i in cond["spec"]["items"]]
    assert kinds == [
        "ConditionalRenderingVariable",
        "ConditionalRenderingData",
        "ConditionalRenderingTimeRangeSize",
    ]


def test_conditional_on_tab():
    board = emit_v2_dashboard(
        name="ct",
        title="ct",
        variables=[CustomVariable(name="audience", options=["beginner", "advanced"])],
        elements={"p1": text_panel(1, "a", "b")},
        layout=TabsLayout(
            tabs=[
                TabsLayoutTab(
                    title="Adv",
                    items=[GridItem(element="p1")],
                    conditional=show_when_variable("audience", "advanced"),
                )
            ]
        ),
    )
    tab = board["spec"]["layout"]["spec"]["tabs"][0]["spec"]
    assert tab["conditionalRendering"]["kind"] == "ConditionalRenderingGroup"


def test_conditional_board_matches_golden():
    assert v2_json(_conditional_board()) == _M3_GOLDEN.read_text(encoding="utf-8")


def test_conditional_board_validates_against_m0_schema():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(
        _conditional_board(), json.loads(_M0_SCHEMA.read_text(encoding="utf-8"))
    )


def test_undeclared_conditional_variable_fails_loud():
    # FR-11 guard: a conditional keyed on a variable that isn't declared must raise at build time
    with pytest.raises(V2ValidationError, match="undeclared variable"):
        emit_v2_dashboard(
            name="bad",
            title="bad",
            elements={"p1": text_panel(1, "a", "b")},
            layout=RowsLayout(
                rows=[
                    RowsLayoutRow(
                        items=[GridItem(element="p1")],
                        conditional=show_when_variable("ghost", "x"),
                    )
                ]
            ),
        )


def test_bad_operator_and_visibility_fail_loud():
    with pytest.raises(V2ValidationError, match="operator must be"):
        VariableCondition(variable="a", value="b", operator="LIKE").to_v2()
    with pytest.raises(V2ValidationError, match="visibility must be"):
        ConditionalRendering(visibility="maybe", items=[]).to_v2()
    with pytest.raises(V2ValidationError, match="group condition must be"):
        ConditionalRendering(condition="xor", items=[]).to_v2()
