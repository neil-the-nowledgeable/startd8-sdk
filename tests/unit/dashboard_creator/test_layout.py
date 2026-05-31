"""Tests for dashboard_creator.layout — DC-108, DC-109."""

import pytest

from startd8.dashboard_creator.layout import (
    apply_layout,
    auto_group_rows,
    auto_layout,
    nest_collapsed_rows,
)
from startd8.dashboard_creator.models import DashboardSpec, GridPos, PanelSpec, PanelType


# ---------------------------------------------------------------------------
# auto_group_rows (DC-108)
# ---------------------------------------------------------------------------


class TestAutoGroupRows:
    def test_ungrouped_panels_come_first(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="A", expr="up", group="Infra"),
            PanelSpec(type=PanelType.STAT, title="B", expr="up"),
        ]
        result = auto_group_rows(panels)
        # B (ungrouped) should come first, then Row, then A
        assert result[0].title == "B"
        assert result[1].type == PanelType.ROW
        assert result[1].title == "Infra"
        assert result[2].title == "A"

    def test_row_panels_inserted_before_each_group(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="A", expr="up", group="Alpha"),
            PanelSpec(type=PanelType.STAT, title="B", expr="up", group="Beta"),
        ]
        result = auto_group_rows(panels)
        types = [p.type for p in result]
        assert types == [PanelType.ROW, PanelType.STAT, PanelType.ROW, PanelType.STAT]
        assert result[0].title == "Alpha"
        assert result[2].title == "Beta"

    def test_groups_emitted_in_first_appearance_order(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="B1", expr="up", group="Beta"),
            PanelSpec(type=PanelType.STAT, title="A1", expr="up", group="Alpha"),
            PanelSpec(type=PanelType.STAT, title="B2", expr="up", group="Beta"),
        ]
        result = auto_group_rows(panels)
        row_titles = [p.title for p in result if p.type == PanelType.ROW]
        assert row_titles == ["Beta", "Alpha"]

    def test_collapsed_row_from_plus_prefix(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="A", expr="up", group="+Details"),
        ]
        result = auto_group_rows(panels)
        row = result[0]
        assert row.type == PanelType.ROW
        assert row.title == "Details"
        assert row.options.get("collapsed") is True

    def test_no_groups_returns_same_panels(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="A", expr="up"),
            PanelSpec(type=PanelType.STAT, title="B", expr="up"),
        ]
        result = auto_group_rows(panels)
        assert len(result) == 2
        assert result[0].title == "A"
        assert result[1].title == "B"


# ---------------------------------------------------------------------------
# auto_layout (DC-109)
# ---------------------------------------------------------------------------


class TestAutoLayout:
    def test_two_panels_side_by_side(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="A", expr="up"),
            PanelSpec(type=PanelType.STAT, title="B", expr="up"),
        ]
        result = auto_layout(panels)
        assert result[0].gridPos == GridPos(h=8, w=12, x=0, y=0)
        assert result[1].gridPos == GridPos(h=8, w=12, x=12, y=0)

    def test_three_panels_wrap_to_next_row(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="A", expr="up"),
            PanelSpec(type=PanelType.STAT, title="B", expr="up"),
            PanelSpec(type=PanelType.STAT, title="C", expr="up"),
        ]
        result = auto_layout(panels)
        assert result[0].gridPos == GridPos(h=8, w=12, x=0, y=0)
        assert result[1].gridPos == GridPos(h=8, w=12, x=12, y=0)
        assert result[2].gridPos == GridPos(h=8, w=12, x=0, y=8)

    def test_row_panel_spans_full_width(self):
        panels = [
            PanelSpec(type=PanelType.ROW, title="Section"),
        ]
        result = auto_layout(panels)
        assert result[0].gridPos == GridPos(h=1, w=24, x=0, y=0)

    def test_row_resets_y_cursor(self):
        panels = [
            PanelSpec(type=PanelType.STAT, title="A", expr="up"),
            PanelSpec(type=PanelType.ROW, title="Section"),
            PanelSpec(type=PanelType.STAT, title="B", expr="up"),
        ]
        result = auto_layout(panels)
        # A at y=0, row at y=8 (after A fills half-row, cursor wraps), B at y=9
        assert result[0].gridPos.y == 0
        assert result[1].gridPos.y == 8  # Row after partial row
        assert result[2].gridPos.y == 9  # After row (h=1)

    def test_explicit_gridpos_preserved(self):
        explicit = GridPos(h=4, w=6, x=3, y=10)
        panels = [
            PanelSpec(type=PanelType.STAT, title="Fixed", expr="up", gridPos=explicit),
        ]
        result = auto_layout(panels)
        assert result[0].gridPos == explicit

    def test_empty_panels_returns_empty(self):
        assert auto_layout([]) == []


# ---------------------------------------------------------------------------
# apply_layout (combined)
# ---------------------------------------------------------------------------


class TestApplyLayout:
    def test_groups_and_positions_combined(self):
        spec = DashboardSpec(
            title="Test",
            panels=[
                PanelSpec(type=PanelType.STAT, title="Ungrouped", expr="up"),
                PanelSpec(type=PanelType.STAT, title="G1", expr="up", group="Infra"),
                PanelSpec(type=PanelType.STAT, title="G2", expr="up", group="Infra"),
            ],
        )
        result = apply_layout(spec)
        titles = [p.title for p in result.panels]
        # Ungrouped first, then row, then grouped panels
        assert titles == ["Ungrouped", "Infra", "G1", "G2"]
        # All panels should have gridPos set
        for p in result.panels:
            assert p.gridPos is not None

    def test_returns_new_spec_instance(self):
        spec = DashboardSpec(
            title="Test",
            panels=[PanelSpec(type=PanelType.STAT, title="A", expr="up")],
        )
        result = apply_layout(spec)
        assert result is not spec
        assert result.title == spec.title


# ---------------------------------------------------------------------------
# nest_collapsed_rows (DC-110 / REQ-DCR-AES-033)
# ---------------------------------------------------------------------------


def _row(title, collapsed=True):
    return {"type": "row", "title": title, "collapsed": collapsed, "panels": []}


def _text(title):
    return {"type": "text", "title": title, "id": title}


class TestNestCollapsedRows:
    def test_collapsed_row_absorbs_trailing_siblings(self):
        dash = {"panels": [
            _row("Welcome"), _text("w1"),
            _row("Services"), _text("s1"),
        ]}
        nest_collapsed_rows(dash)
        # top level is now just the two rows; each nests its text
        assert [p["type"] for p in dash["panels"]] == ["row", "row"]
        assert [c["title"] for c in dash["panels"][0]["panels"]] == ["w1"]
        assert [c["title"] for c in dash["panels"][1]["panels"]] == ["s1"]

    def test_expanded_rows_keep_siblings(self):
        dash = {"panels": [
            _row("A", collapsed=False), _text("a1"), _text("a2"),
        ]}
        nest_collapsed_rows(dash)
        # expanded row owns nothing; panels stay top-level siblings
        assert [p["type"] for p in dash["panels"]] == ["row", "text", "text"]
        assert dash["panels"][0]["panels"] == []

    def test_next_row_ends_ownership(self):
        dash = {"panels": [
            _row("A"), _text("a1"),
            _row("B", collapsed=False), _text("b1"),
        ]}
        nest_collapsed_rows(dash)
        assert [c["title"] for c in dash["panels"][0]["panels"]] == ["a1"]
        # b1 follows an EXPANDED row -> stays a top-level sibling
        assert dash["panels"][-1] == _text("b1")

    def test_idempotent(self):
        dash = {"panels": [_row("A"), _text("a1"), _row("B"), _text("b1")]}
        once = nest_collapsed_rows(dash)
        twice = nest_collapsed_rows({"panels": [p for p in once["panels"]]})
        assert once["panels"] == twice["panels"]

    def test_no_content_lost(self):
        dash = {"panels": [_row("A"), _text("a1"), _row("B"), _text("b1")]}
        nest_collapsed_rows(dash)
        texts = [c["title"] for r in dash["panels"] for c in r.get("panels", [])]
        assert sorted(texts) == ["a1", "b1"]

    def test_rowless_dashboard_untouched(self):
        dash = {"panels": [_text("x"), _text("y")]}
        nest_collapsed_rows(dash)
        assert [p["title"] for p in dash["panels"]] == ["x", "y"]

    def test_missing_panels_key_is_safe(self):
        assert nest_collapsed_rows({}) == {}
        assert nest_collapsed_rows({"panels": None}) == {"panels": None}
