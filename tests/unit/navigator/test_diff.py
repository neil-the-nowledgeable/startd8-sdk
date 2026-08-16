"""REQ-07 FR-1/FR-4/FR-9/FR-10 — the navigator diff engine (pure, renderer-independent)."""

from __future__ import annotations

from pathlib import Path

from startd8.navigator.diff import (
    _DIFF_FIELDS,
    diff_nodes,
    node_diff_to_json,
)
from startd8.navigator.models import Node, NodeEvidence, NodeStatus, StatusFacet


def _n(key, does="d", status=NodeStatus.SPEC, **kw):
    return Node(key=key, does=does, status=status, **kw)


# --------------------------------------------------------------------------- #
# Identity + empty
# --------------------------------------------------------------------------- #
def test_diff_of_identical_states_is_empty():
    a = [_n("A"), _n("B", status=NodeStatus.BUILT)]
    d = diff_nodes(a, a)
    assert d.is_empty
    assert d.added == () and d.removed == () and d.changed == ()
    assert set(d.unchanged) == {"A", "B"}


def test_added_key_lands_in_added():
    d = diff_nodes([_n("A")], [_n("A"), _n("B")])
    assert [n.key for n in d.added] == ["B"]
    assert d.removed == ()


def test_dropped_key_lands_in_removed():
    d = diff_nodes([_n("A"), _n("B")], [_n("A")])
    assert [n.key for n in d.removed] == ["B"]
    assert d.added == ()


def test_does_edit_is_changed_with_field_delta():
    d = diff_nodes([_n("A", does="old")], [_n("A", does="new")])
    assert len(d.changed) == 1
    key, before, after, deltas = d.changed[0]
    assert key == "A"
    fields = {fd.field: (fd.before, fd.after) for fd in deltas}
    assert fields["does"] == ("old", "new")


def test_status_edit_is_changed():
    d = diff_nodes(
        [_n("A", status=NodeStatus.SPEC)], [_n("A", status=NodeStatus.BUILT)]
    )
    _, _, _, deltas = d.changed[0]
    assert any(fd.field == "status" for fd in deltas)


# --------------------------------------------------------------------------- #
# Order-insensitive collection compare (the false-"changed" risk)
# --------------------------------------------------------------------------- #
def test_reordered_child_keys_is_unchanged():
    before = [_n("A", child_keys=("B", "C"))]
    after = [_n("A", child_keys=("C", "B"))]
    d = diff_nodes(before, after)
    assert d.changed == ()
    assert list(d.unchanged) == ["A"]


def test_reordered_lives_is_unchanged():
    e1 = NodeEvidence(type="code", ref="src/a.py")
    e2 = NodeEvidence(type="test", ref="tests/a.py")
    d = diff_nodes([_n("A", lives=(e1, e2))], [_n("A", lives=(e2, e1))])
    assert d.changed == ()


def test_reordered_wont_is_unchanged():
    d = diff_nodes([_n("A", wont=("x", "y"))], [_n("A", wont=("y", "x"))])
    assert d.changed == ()


def test_reordered_children_is_unchanged():
    b1, b2 = _n("B"), _n("C")
    d = diff_nodes([_n("A", children=(b1, b2))], [_n("A", children=(b2, b1))])
    # A itself unchanged (same child-key set); B and C are their own unchanged keys
    assert d.changed == ()
    assert set(d.unchanged) == {"A", "B", "C"}


def test_reordered_attributes_is_unchanged():
    d = diff_nodes(
        [_n("A", attributes={"x": "1", "y": "2"})],
        [_n("A", attributes={"y": "2", "x": "1"})],
    )
    assert d.changed == ()


def test_reordered_status_facets_is_unchanged():
    f1 = StatusFacet(name="cov", value="ok")
    f2 = StatusFacet(name="lint", value="warn")
    d = diff_nodes([_n("A", status_facets=(f1, f2))], [_n("A", status_facets=(f2, f1))])
    assert d.changed == ()


def test_real_child_key_change_is_changed():
    d = diff_nodes([_n("A", child_keys=("B",))], [_n("A", child_keys=("B", "C"))])
    _, _, _, deltas = d.changed[0]
    assert any(fd.field == "child_keys" for fd in deltas)


# --------------------------------------------------------------------------- #
# Derived-field exclusion (no false-fire on re-derivation)
# --------------------------------------------------------------------------- #
def test_confidence_and_category_changes_do_not_fire():
    before = [_n("A", confidence=0.4, category="x", orientation="a", route_state="r1")]
    after = [_n("A", confidence=0.9, category="y", orientation="b", route_state="r2")]
    d = diff_nodes(before, after)
    assert d.changed == ()  # all four are excluded from _DIFF_FIELDS
    assert "confidence" not in _DIFF_FIELDS
    assert "category" not in _DIFF_FIELDS
    assert "orientation" not in _DIFF_FIELDS
    assert "route_state" not in _DIFF_FIELDS


# --------------------------------------------------------------------------- #
# Determinism (FR-10)
# --------------------------------------------------------------------------- #
def test_shuffled_input_order_yields_identical_diff():
    before = [_n("A"), _n("B"), _n("C")]
    after = [_n("A", does="x"), _n("B"), _n("D")]
    d1 = diff_nodes(before, after)
    d2 = diff_nodes(list(reversed(before)), list(reversed(after)))
    assert node_diff_to_json(d1) == node_diff_to_json(d2)
    # buckets key-sorted
    assert [n.key for n in d1.added] == sorted(n.key for n in d1.added)
    assert [n.key for n in d1.removed] == sorted(n.key for n in d1.removed)


def test_changed_field_deltas_in_fixed_field_order():
    before = [_n("A", does="o", status=NodeStatus.SPEC, ships_when="q1")]
    after = [_n("A", does="n", status=NodeStatus.BUILT, ships_when="q2")]
    _, _, _, deltas = diff_nodes(before, after).changed[0]
    order = [fd.field for fd in deltas]
    # must follow _DIFF_FIELDS order (does before status before ships_when)
    assert order == [f for f in _DIFF_FIELDS if f in set(order)]


# --------------------------------------------------------------------------- #
# Rename = remove + add (NR-4, no fuzzy match)
# --------------------------------------------------------------------------- #
def test_renamed_key_is_one_removed_plus_one_added():
    d = diff_nodes([_n("OLD", does="same body")], [_n("NEW", does="same body")])
    assert [n.key for n in d.removed] == ["OLD"]
    assert [n.key for n in d.added] == ["NEW"]
    assert d.changed == ()


# --------------------------------------------------------------------------- #
# Status transitions (FR-4)
# --------------------------------------------------------------------------- #
def test_status_transition_surfaced():
    d = diff_nodes(
        [_n("A", status=NodeStatus.SPEC)], [_n("A", status=NodeStatus.BUILT)]
    )
    assert len(d.status_transitions) == 1
    t = d.status_transitions[0]
    assert (t.key, t.before, t.after) == ("A", "spec", "built")


# --------------------------------------------------------------------------- #
# New dangling refs (FR-4) — local FS only
# --------------------------------------------------------------------------- #
def test_new_dangling_ref_flagged(tmp_path: Path):
    # after introduces a lives ref to a path that does not exist under repo_root
    before = [_n("A")]
    after = [_n("A", lives=(NodeEvidence(type="code", ref="src/ghost.py"),))]
    d = diff_nodes(before, after, repo_root=tmp_path)
    assert len(d.new_dangling_refs) == 1
    assert d.new_dangling_refs[0].key == "A"
    assert d.new_dangling_refs[0].resolved_path == "src/ghost.py"


def test_already_dangling_ref_not_flagged_new(tmp_path: Path):
    ev = NodeEvidence(type="code", ref="src/ghost.py")
    # dangling in BOTH before and after → not a NEW dangling ref
    before = [_n("A", lives=(ev,))]
    after = [_n("A", lives=(ev,), does="changed body")]
    d = diff_nodes(before, after, repo_root=tmp_path)
    assert d.new_dangling_refs == ()


def test_resolving_ref_not_flagged(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    real = tmp_path / "src" / "real.py"
    real.write_text("x = 1\n")
    before = [_n("A")]
    after = [_n("A", lives=(NodeEvidence(type="code", ref="src/real.py"),))]
    d = diff_nodes(before, after, repo_root=tmp_path)
    assert d.new_dangling_refs == ()


def test_git_and_file_ref_prefixes_stripped(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "real.py").write_text("x=1\n")
    sha = "0" * 40
    before = [_n("A")]
    after = [
        _n("A", lives=(NodeEvidence(type="code", ref=f"git:{sha}:src/real.py"),)),
        _n("B", lives=(NodeEvidence(type="code", ref="file:src/ghost.py:12"),)),
    ]
    d = diff_nodes(before, after, repo_root=tmp_path)
    keys = {r.key for r in d.new_dangling_refs}
    assert keys == {"B"}  # A resolves (git prefix stripped), B is ghost


# --------------------------------------------------------------------------- #
# Flatten (last-write-wins) + full key-set
# --------------------------------------------------------------------------- #
def test_diff_covers_flattened_children():
    before = [_n("root", children=(_n("leaf", does="old"),))]
    after = [_n("root", children=(_n("leaf", does="new"),))]
    d = diff_nodes(before, after)
    changed_keys = {k for (k, *_r) in d.changed}
    assert "leaf" in changed_keys  # nested leaf edit is diffed


# --------------------------------------------------------------------------- #
# FR-9 reverse-import gate: wireframe_view must not import diff/render_diff
# --------------------------------------------------------------------------- #
def test_wireframe_view_does_not_import_diff():
    import startd8.wireframe_view as wv

    pkg_dir = Path(wv.__file__).parent
    for py in pkg_dir.rglob("*.py"):
        for line in py.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert "navigator.diff" not in stripped, f"{py}: {stripped}"
                assert "navigator.render_diff" not in stripped, f"{py}: {stripped}"


def test_diff_module_does_not_import_wireframe():
    src = Path(diff_nodes.__code__.co_filename)
    # check actual import lines only (docstring prose may mention the module by name)
    for line in src.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "wireframe" not in stripped, stripped
