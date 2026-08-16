"""REQ-05 FR-1 — the ported Node→graph projection (Mottainai port of CC graph_projection.py).

Verifies: single-live-def port-hazard gate (FR-1a/FR-7), the five edge kinds incl. `child_keys` →
`depends-on` (FR-1b), and `validate_graph_model` valid/dangling behaviour (FR-1c).
"""

from __future__ import annotations

from pathlib import Path

from startd8.navigator.graph_projection import (
    _flatten,
    _kind,
    _node_payload,
    _section,
    _slug,
    _split_ids,
    nodes_to_graph,
    validate_graph_model,
)
from startd8.navigator.models import Node, NodeStatus

_PORT_SRC = Path(__file__).resolve().parents[3] / "src" / "startd8" / "navigator" / "graph_projection.py"

# The 8 live singular symbols the port carries (task port-source contract).
_PORTED_SYMBOLS = (
    "nodes_to_graph",
    "validate_graph_model",
    "_flatten",
    "_node_payload",
    "_slug",
    "_kind",
    "_section",
    "_split_ids",
)


def _fixture() -> list:
    """FR-7 depends-on FR-2 (a cross-tree dependency edge)."""
    fr7 = Node(key="FR-7", does="depends on FR-2", status=NodeStatus.SPEC, child_keys=("FR-2",))
    fr2 = Node(key="FR-2", does="base capability", status=NodeStatus.BUILT)
    return [fr7, fr2]


def test_each_ported_symbol_is_single_live_def():
    """FR-1a / FR-7: the port drops dead/shadowed code — each ported top-level symbol appears once."""
    src = _PORT_SRC.read_text(encoding="utf-8")
    for sym in _PORTED_SYMBOLS:
        assert src.count(f"def {sym}") == 1, f"{sym} must be defined exactly once (Kagami gate)"


def test_port_does_not_import_contextcore():
    """FR-1: the port changes ONLY the import line — no residual ContextCore import."""
    src = _PORT_SRC.read_text(encoding="utf-8")
    assert "contextcore" not in src.lower()
    assert "from .models import Node" in src


def test_schema_string_preserved():
    """FR-1: the emitted schema string is carried verbatim from CC."""
    graph = nodes_to_graph(_fixture())
    assert graph["schema"] == "visual-editor.graph-model/21"


def test_child_keys_produce_depends_on_edge():
    """FR-1b: FR-7.child_keys=('FR-2',) → a semantic depends-on edge FR-7 → FR-2."""
    graph = nodes_to_graph(_fixture())
    dep = [e for e in graph["edges"] if e["label"] == "depends-on"]
    assert len(dep) == 1
    edge = dep[0]
    assert edge["from"] == "FR-7"
    assert edge["to"] == "FR-2"
    assert edge["label"] == "depends-on"
    assert edge["data"]["semantic"] is True
    # D4: the port carries an `id` beyond the spec example — assert presence, NOT an exact key set.
    assert "id" in edge


def test_five_edge_kinds_distinguished():
    """FR-1: the five semantic edge kinds are all derivable and stamped semantic=True."""
    parent = Node(
        key="O-1",
        does="objective",
        status=NodeStatus.SPEC,
        child_keys=("FR-1",),
        attributes={"serves": "O-2", "built_by": "team-a", "delivers": "value-x"},
    )
    child = Node(key="FR-1", does="child", status=NodeStatus.BUILT)
    # containment child so contains-child fires
    root = Node(key="root", does="r", status=NodeStatus.SPEC, children=(parent,))
    targets = Node(key="O-2", does="o2")
    tb = Node(key="team-a", does="t")
    dv = Node(key="value-x", does="v")
    graph = nodes_to_graph([root, child, targets, tb, dv])
    labels = {e["label"] for e in graph["edges"]}
    assert {"depends-on", "serves", "built-by", "delivers", "contains-child"} <= labels


def test_view_section_nodes_carry_view_marker():
    """FR-1: derived section nodes use the reserved prefix + view_marker=true (parity discipline)."""
    graph = nodes_to_graph(_fixture())
    sections = [n for n in graph["nodes"] if str(n["id"]).startswith("view:section:")]
    assert sections, "projection injects view:section:* layout nodes"
    assert all(n["data"]["view_marker"] is True for n in sections)


def test_identity_from_key_only():
    """FR-1: a node's graph id is its Node.key (identity is never inferred from prose)."""
    graph = nodes_to_graph(_fixture())
    ids = {n["id"] for n in graph["nodes"]}
    assert "FR-7" in ids and "FR-2" in ids


def test_validate_returns_empty_for_valid_graph():
    """FR-1c: validate_graph_model(valid) → ()."""
    graph = nodes_to_graph(_fixture())
    assert validate_graph_model(graph) == ()


def test_validate_flags_dangling_edge():
    """FR-1c: a hand-built edge pointing to a non-existent node → a non-empty issue tuple."""
    graph = {
        "schema": "visual-editor.graph-model/21",
        "nodes": [{"id": "A"}],
        "edges": [{"id": "e", "from": "A", "to": "GHOST", "label": "depends-on", "data": {"semantic": True}}],
    }
    issues = validate_graph_model(graph)
    assert issues != ()
    assert any("Dangling" in i for i in issues)


def test_validate_missing_list_fields():
    """FR-1c: a malformed graph (non-list fields) reports the structural issue, not a crash."""
    assert validate_graph_model({"nodes": "x", "edges": "y"}) != ()


def test_helper_functions_behave():
    """FR-1: the ported helper set is live and behaves (not dead-imported)."""
    assert _slug("Hello World!") == "hello-world"
    assert _split_ids("a, b ,c") == ("a", "b", "c")
    n = Node(key="k", does="d", attributes={"kind": "widget", "section": "Tools"})
    assert _kind(n) == "widget"
    assert _section(n) == "Tools"
    flat, nested = _flatten([Node(key="p", does="p", children=(Node(key="c", does="c"),))])
    assert {x.key for x in flat} == {"p", "c"}
    assert ("p", "c") in nested
    payload = _node_payload(n, {"x": 0.1, "y": 0.2})
    assert payload["id"] == "k"
