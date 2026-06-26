"""Tests for the facts → EntityGraph mapper (derive-contract Step 2, FR-DC-4/5).

Synthetic facts assert each deterministic rule; a navig8 introspect→map→**emit** smoke proves the
graph feeds the existing `render_prisma_schema` (Step 3) and reproduces the hand-derived structure.
"""

from __future__ import annotations

import enum
from typing import Dict, List, Optional

import pytest
from pydantic import BaseModel, Field, computed_field

from startd8.concierge.derive.introspect import introspect_models
from startd8.concierge.derive.mapper import build_entity_graph
from startd8.manifest_extraction.entities import _lower_camel
from startd8.manifest_extraction.prisma_emitter import render_prisma_schema


class Bites(str, enum.Enum):
    AT_FORMATION = "at-formation"
    DONE = "done"


class Child(BaseModel):
    id: str
    name: str


class Parent(BaseModel):
    id: str
    title: Optional[str] = None
    count: int = 0
    tags: List[str] = []
    meta: Dict[str, str] = {}
    bites: Bites = Bites.DONE
    children: List[Child] = []
    best: Optional[Child] = None
    links: List[str] = Field(default=[], json_schema_extra={"prisma": {"join": "Other"}})

    @computed_field
    @property
    def display(self) -> str:
        return self.title or ""


def _graph():
    return build_entity_graph(introspect_models([Parent, Child]))


def test_relations_become_fk_parents_not_fields():
    g, _ = _graph()
    # Parent.children: List[Child] → Child carries the FK to Parent (1:N).
    assert "Parent" in g.fk_parents.get("Child", [])
    # Parent.best: Child → Parent is a child of Child (nested ref → FK).
    assert "Child" in g.fk_parents.get("Parent", [])
    # relation fields are NOT emitted as DocFields.
    parent_fields = {f.name for f in g.entities["Parent"].fields}
    assert "children" not in parent_fields and "best" not in parent_fields


def test_semantic_key_and_unique():
    g, report = _graph()
    parent_fields = {f.name: f for f in g.entities["Parent"].fields}
    assert "parentKey" in parent_fields and "id" not in parent_fields  # id → parentKey; cuid PK auto
    # Parent's FK parent is Child → parent_fk = childId → @@unique([childId, parentKey])
    assert ("childId", "parentKey") in g.uniques.get("Parent", [])
    assert any(t["rule"] == "semantic-key" and t["entity"] == "Parent" for t in report.transforms)


def test_scalar_enum_json_mapping():
    g, _ = _graph()
    f = {x.name: x for x in g.entities["Parent"].fields}
    assert f["title"].prisma_type == "String" and f["title"].required is False
    assert f["count"].prisma_type == "Int" and f["count"].default == "0"
    assert f["tags"].prisma_type == "Json"   # list[str] → Json (not String[])
    assert f["meta"].prisma_type == "Json"   # dict → Json
    assert f["bites"].prisma_type == "Bites" and f["bites"].default == "done"


def test_enum_in_graph_normalized():
    g, _ = _graph()
    assert g.enums["Bites"] == ("at_formation", "done")


def test_marked_join_becomes_join_model():
    g, report = _graph()
    assert any(j.name == "OtherParent" and {j.left, j.right} == {"Other", "Parent"} for j in g.joins)
    assert "OtherParent" in report.joins


def test_computed_field_excluded_in_report():
    _, report = _graph()
    assert any(e["field"] == "display" and e["entity"] == "Parent" for e in report.exclusions)


def test_unmarked_list_flag_carried_through():
    _, report = _graph()
    assert any(fl.get("field") == "tags" for fl in report.flags)


def test_graph_emits_valid_prisma():
    """The mapper's graph feeds the existing emitter (Step 3) without errors."""
    g, _ = _graph()
    res = render_prisma_schema(g)
    assert res.errors == ()
    assert "model Parent" in res.text and "model Child" in res.text
    assert "enum Bites" in res.text
    assert "@@unique([childId, parentKey])" in res.text
    # the M2M join model renders
    assert "model OtherParent" in res.text


def test_determinism_same_facts_same_graph():
    g1, _ = _graph()
    g2, _ = _graph()
    assert render_prisma_schema(g1).schema_sha256 == render_prisma_schema(g2).schema_sha256


# ── navig8 oracle: introspect → map → emit ───────────────────────────────────

def test_navig8_map_and_emit_smoke():
    import sys

    sys.path.insert(0, "/Users/neilyashinsky/Documents/dev/startd8-work/src")
    tm = pytest.importorskip("startd8_work.legal.tree_models")
    rm = pytest.importorskip("startd8_work.legal.register_models")
    md = pytest.importorskip("startd8_work.legal.models")

    result = introspect_models([
        tm.DecisionTree, tm.TreeNode, tm.Perspective,
        rm.LandmineRegister, rm.LandmineEntry, md.Citation,
    ])
    g, report = build_entity_graph(result)

    # 1:N from DecisionTree.nodes → TreeNode carries the FK to DecisionTree.
    assert "DecisionTree" in g.fk_parents.get("TreeNode", [])
    # Citation is referenced by both TreeNode.legal_basis and LandmineEntry.legal_basis.
    assert set(g.fk_parents.get("Citation", [])) >= {"TreeNode", "LandmineEntry"}
    # TreeNode has an explicit id → treeNodeKey + a compound unique with its parent FK.
    assert ("decisionTreeId", "treeNodeKey") in g.uniques.get("TreeNode", [])
    # WhenItBites enum normalized in the graph.
    assert g.enums["WhenItBites"][0] == "at_formation"
    # the whole graph emits.
    res = render_prisma_schema(g)
    assert res.errors == ()
    for model in ("model DecisionTree", "model TreeNode", "model Citation", "model LandmineEntry"):
        assert model in res.text
