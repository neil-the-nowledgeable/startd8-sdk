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
