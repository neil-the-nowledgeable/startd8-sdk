"""Unit tests for the Pydantic introspector (derive-contract Step 1, FR-DC-3/5/12).

Synthetic models exercise every classification branch hermetically; a guarded smoke test
validates against the real navig8 models (the golden oracle) when importable.
"""

from __future__ import annotations

import enum
from typing import Dict, List, Optional

import pytest
from pydantic import BaseModel, Field, computed_field

from startd8.concierge.derive.introspect import (
    KIND_DICT,
    KIND_ENUM,
    KIND_LIST_MODEL,
    KIND_LIST_SCALAR,
    KIND_MARKED_JOIN,
    KIND_NESTED_MODEL,
    KIND_SCALAR,
    introspect_models,
)


class Bites(str, enum.Enum):
    AT_FORMATION = "at-formation"   # hyphen → must normalize
    DONE = "done"


class Child(BaseModel):
    id: str
    name: str


class Parent(BaseModel):
    id: str                                  # explicit id → has_explicit_id
    title: Optional[str] = None              # optional scalar
    count: int = 0                           # scalar with default
    tags: List[str] = []                     # list[str] → list_scalar + FLAG (ambiguous)
    meta: Dict[str, str] = {}                # dict → Json
    bites: Bites = Bites.DONE                # enum (+ hyphen value)
    children: List[Child] = []               # list_model → 1:N
    best: Optional[Child] = None             # nested_model → FK
    links: List[str] = Field(default=[], json_schema_extra={"prisma": {"join": "Other"}})  # marked_join

    @computed_field
    @property
    def display(self) -> str:                # computed → dropped
        return self.title or ""


def _fields(result, entity):
    ent = next(e for e in result.entities if e.name == entity)
    return ent, {f.name: f for f in ent.fields}


def test_entity_and_explicit_id():
    r = introspect_models([Parent, Child])
    parent, _ = _fields(r, "Parent")
    assert parent.has_explicit_id is True
    assert parent.module == __name__


def test_field_classification():
    r = introspect_models([Parent, Child])
    _, f = _fields(r, "Parent")
    assert f["title"].kind == KIND_SCALAR and f["title"].optional is True
    assert f["count"].kind == KIND_SCALAR and f["count"].has_default and f["count"].default == 0
    assert f["tags"].kind == KIND_LIST_SCALAR
    assert f["meta"].kind == KIND_DICT
    assert f["bites"].kind == KIND_ENUM and f["bites"].enum_name == "Bites"
    assert f["children"].kind == KIND_LIST_MODEL and f["children"].ref_model == "Child"
    assert f["best"].kind == KIND_NESTED_MODEL and f["best"].ref_model == "Child" and f["best"].optional
    assert f["links"].kind == KIND_MARKED_JOIN and f["links"].join_target == "Other"


def test_computed_field_dropped_and_recorded():
    r = introspect_models([Parent])
    parent, fmap = _fields(r, "Parent")
    assert "display" not in fmap                  # not a stored column
    assert "display" in parent.computed_excluded  # recorded for the report


def test_enum_hyphen_normalization():
    r = introspect_models([Parent])
    bites = next(e for e in r.enums if e.name == "Bites")
    assert bites.values == ("at-formation", "done")
    assert bites.normalized == ("at_formation", "done")
    assert bites.needs_normalization is True


def test_unmarked_list_str_is_flagged():
    """FR-DC-8: an unmarked list[str] is Json by default but flagged (could be M2M/loose-ref)."""
    r = introspect_models([Parent])
    flagged = [fl for fl in r.flags if fl["field"] == "tags" and fl["entity"] == "Parent"]
    assert flagged and "M2M" in flagged[0]["reason"]
    # the marked join is NOT flagged (it was confirmed)
    assert not any(fl["field"] == "links" for fl in r.flags)


def test_enum_collected_once_across_models():
    class A(BaseModel):
        x: Bites = Bites.DONE

    class B(BaseModel):
        y: Bites = Bites.DONE

    r = introspect_models([A, B])
    assert sum(1 for e in r.enums if e.name == "Bites") == 1


def test_non_basemodel_skipped():
    r = introspect_models([Parent, str])  # type: ignore[list-item]
    assert any("non-BaseModel" in w for w in r.warnings)
    assert {e.name for e in r.entities} == {"Parent"}


# ── guarded smoke test against the real navig8 oracle ────────────────────────

def test_navig8_models_smoke(monkeypatch):
    import sys

    sys.path.insert(0, "/Users/neilyashinsky/Documents/dev/startd8-work/src")
    tree_models = pytest.importorskip("startd8_work.legal.tree_models")
    register_models = pytest.importorskip("startd8_work.legal.register_models")

    r = introspect_models([
        tree_models.DecisionTree, tree_models.TreeNode, tree_models.Perspective,
        register_models.LandmineEntry,
    ])
    ents = {e.name: e for e in r.entities}
    # DecisionTree has no explicit `id` (→ cuid PK); TreeNode/LandmineEntry do (→ <entity>Key).
    assert ents["DecisionTree"].has_explicit_id is False
    assert ents["TreeNode"].has_explicit_id is True
    assert ents["LandmineEntry"].has_explicit_id is True
    # node_count is a @computed_field on DecisionTree → excluded.
    assert "node_count" in ents["DecisionTree"].computed_excluded
    # WhenItBites enum has hyphenated values that must normalize.
    bites = next((e for e in r.enums if e.name == "WhenItBites"), None)
    assert bites is not None and bites.needs_normalization is True
