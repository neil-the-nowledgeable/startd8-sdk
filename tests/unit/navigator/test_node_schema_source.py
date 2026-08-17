"""Node-structure visualization (Kagami mirror of models.py) — the schema rendered as Nodes."""

from __future__ import annotations

from startd8.navigator.models import node_field_names
from startd8.navigator.sources_node_schema import nodes_from_node_schema


def test_mirror_covers_every_model_field():
    """Kagami: every Node dataclass field is visualized — the mirror can't silently drop one."""
    shown = {n.key.split(".", 1)[1] for n in nodes_from_node_schema()}
    assert shown == set(node_field_names())


def test_each_field_node_is_grounded_in_models_py():
    """Each field-node's Lives points at the git blob that defines it (grounded, not hand-drawn)."""
    for n in nodes_from_node_schema():
        assert n.lives, f"{n.key} has no Lives"
        assert all(e.ref.endswith("src/startd8/navigator/models.py") for e in n.lives)


def test_each_field_carries_type_default_and_deterministic_name():
    """Structural truth (type/default) is introspected; each field also gets a deterministic name."""
    nodes = {n.key: n for n in nodes_from_node_schema()}
    lives_field = nodes["Node.lives"]
    a = lives_field.attributes
    assert "Tuple" in a["field_type"] and "NodeEvidence" in a["field_type"]  # introspected type
    assert a["field_default"] == "()"
    assert a["name"].startswith("Node.lives holds")
    assert a["handle"].startswith("schema-field/")
    assert a["canonical"] == "cc:intent:node-schema:schema-field:lives"


def test_provenance_classes_are_known():
    for n in nodes_from_node_schema():
        assert n.attributes["provenance"] in {"authored", "derived", "computed", "meta"}


def test_chrome_provenance_traces_every_element_no_orphans():
    """Origin audit: every apex/chrome element of the node-schema view traces to a present source."""
    from startd8.navigator.project import nodes_to_wireframe_plan
    from startd8.navigator.provenance import chrome_provenance
    from startd8.navigator.sources_node_schema import NODE_SCHEMA_PROFILE

    nodes = nodes_from_node_schema()
    rows = chrome_provenance(nodes, nodes_to_wireframe_plan(nodes), NODE_SCHEMA_PROFILE)
    by = {r["element"]: r for r in rows}
    assert by["summary_meta"]["origin"].startswith("profile.summary_meta")
    assert "Kagami mirror" in by["summary_meta"]["value"]
    assert by["status_band"]["origin"].startswith("computed")
    assert "authored" in by["status_band"]["value"]              # 8 authored / 3 computed / …
    assert by["shape_band"]["value"].startswith("Nodes: 20")   # 15 + REQ-16/17 (4) + REQ-22 verify_gate
    assert all(r["present"] for r in rows), "no chrome element should be an orphan"


def test_chrome_provenance_flags_an_orphan():
    """A profile field with no value is an orphan (Kagami: sourceless chrome on the page)."""
    import dataclasses

    from startd8.navigator.project import nodes_to_wireframe_plan
    from startd8.navigator.provenance import chrome_provenance
    from startd8.navigator.sources_node_schema import NODE_SCHEMA_PROFILE

    empty_why = dataclasses.replace(NODE_SCHEMA_PROFILE, why="")
    nodes = nodes_from_node_schema()
    rows = chrome_provenance(nodes, nodes_to_wireframe_plan(nodes), empty_why)
    assert any(r["element"] == "why" and not r["present"] for r in rows)


def test_node_schema_items_carry_structure_only_metadata():
    """Each field-node's WireframeItem carries the compact meta shown by the "Show node metadata" overlay."""
    from startd8.navigator.project import nodes_to_wireframe_plan

    plan = nodes_to_wireframe_plan(nodes_from_node_schema())
    metas = [it.meta for sec in plan.sections for it in sec.items]
    assert metas and all(m for m in metas)                       # every field-node has meta
    assert any("models.py" in m and "default" in m for m in metas)


def test_inspect_loop_finds_derivative_value_in_non_node_chrome():
    """The inspect loop presumes legacy value: every non-node-driven chrome element carries an
    original intent + a derivative value, and the status/shape bands are flagged as candidates."""
    from startd8.navigator.inspect import inspect_elements
    from startd8.navigator.project import nodes_to_wireframe_plan
    from startd8.navigator.sources_node_schema import NODE_SCHEMA_PROFILE

    nodes = nodes_from_node_schema()
    rows = inspect_elements(nodes, nodes_to_wireframe_plan(nodes), NODE_SCHEMA_PROFILE)
    by = {r["element"]: r for r in rows}
    # node-driven elements are out of scope (they come from the nodes themselves)
    assert "sections" not in by and "node_keys" not in by
    # every inspected element has an original intent + a verdict
    assert all(r["original"] and r["verdict"] in {"realized", "candidate", "uninspected"} for r in rows)
    # the status/shape bands carry latent derivative value (candidates for /enhancement-backlog)
    assert by["status_band"]["verdict"] == "candidate"
    assert by["status_band"]["derivative"]                       # a derivative value is proposed
