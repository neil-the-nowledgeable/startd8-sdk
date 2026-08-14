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
