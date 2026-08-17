"""Guard tests for the source-bound Touches-kind derivation + its structured carry onto the card.

Covers REQ-requirement-detail-on-navigator-card FR-4 (path→kind classification, deterministic and
source-bound) and FR-5 (the typed list rides ``WireframeItem.touches`` structurally, never a
re-stringified blob).
"""
from __future__ import annotations

from startd8.navigator.models import Node, NodeStatus
from startd8.navigator.project import _classify_touch, _typed_touches, nodes_to_wireframe_plan


def test_classify_touch_is_source_bound_by_path():
    # FR-4: kind is a deterministic function of the path/extension alone — never inferred from meaning.
    assert _classify_touch("src/startd8/x.py") == "code"
    assert _classify_touch("pkg/main.go") == "code"
    assert _classify_touch("tests/unit/test_x.py") == "test"      # tests/ tree
    assert _classify_touch("src/foo_test.py") == "test"           # _test. suffix
    assert _classify_touch("app.yaml") == "config"
    assert _classify_touch("pyproject.toml") == "config"
    assert _classify_touch("README.md") == "doc"
    assert _classify_touch("Dockerfile") == "build"
    assert _classify_touch("go.mod") == "build"
    assert _classify_touch("poetry.lock") == "build"
    assert _classify_touch("navigator-build") == "other"          # a bare projection token, not a path
    assert _classify_touch("") == "other"


def test_classify_touch_test_beats_extension():
    # A file under a tests/ tree is test evidence even though it's a .py source file.
    assert _classify_touch("tests/unit/wireframe/test_render_profile.py") == "test"


def test_typed_touches_splits_strips_backticks_and_tags():
    # FR-4/FR-5: the joined ``touches`` attribute is split back to entries, backticks/space stripped,
    # each tagged — yielding ordered (path, kind) pairs (the structured list the card carries).
    out = _typed_touches("`src/x.py`, `tests/test_x.py`, `app.yaml`")
    assert out == [("src/x.py", "code"), ("tests/test_x.py", "test"), ("app.yaml", "config")]
    assert _typed_touches("") == []
    assert _typed_touches(None) == []  # tolerant of a missing attribute


def test_project_wires_typed_touches_onto_the_item():
    # FR-5: nodes_to_wireframe_plan populates WireframeItem.touches from the node's authored Touches,
    # as hashable ordered pairs — the structured carry the detail views read by key.
    node = Node(
        key="FR-1", does="do a thing", status=NodeStatus.SPEC,
        attributes={"touches": "`src/a.py`, `tests/test_a.py`, `conf.yaml`"},
    )
    plan = nodes_to_wireframe_plan([node])
    item = plan.sections[0].items[0]
    assert item.touches == (("src/a.py", "code"), ("tests/test_a.py", "test"), ("conf.yaml", "config"))


def test_item_touches_defaults_empty_when_no_touches_attribute():
    # Omit-when-empty is the byte-identity guard: a node with no Touches carries an empty tuple.
    node = Node(key="FR-2", does="x", status=NodeStatus.SPEC, attributes={})
    item = nodes_to_wireframe_plan([node]).sections[0].items[0]
    assert item.touches == ()
