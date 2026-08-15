"""REQ-04 — the shared node-lens transform (node_lenses.py).

Guards the lens lift: (FR-1) the shared transform is importable and applies the same lens logic that
lived inline in compose; (FR-2) the project_nodes bridge turns raw Nodes into lens-annotated
item-views; (FR-3) node_lenses.py carries no WireframePlan dependency; (FR-4) the package re-exports
the public surface; (FR-7) project_nodes stays byte-parity with compose across all role×fluency combos.

Byte-identity of the app-scaffold path is guarded by the untouched
tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical (FR-6).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from startd8.navigator.models import Node
from startd8.navigator.project import nodes_to_wireframe_plan
from startd8.wireframe_view.compose import compose
from startd8.wireframe_view.node_lenses import (
    GAP_STATUSES,
    HONEST_SKIP_ROUTES,
    apply_node_lenses,
    apply_section_lenses,
    has_jargon,
    project_nodes,
)

_NODE_LENSES_SRC = (
    Path(__file__).resolve().parents[3]
    / "src" / "startd8" / "wireframe_view" / "node_lenses.py"
)


# ── FR-1: the shared transform is present and behaves like the inline logic ──────────────────────

def test_apply_node_lenses_display_labels_and_jargon():
    # end_user voice plain-ifies a structural label and flags a jargon label as technical.
    views = [
        {"label": "home / index page", "status": "spec"},
        {"label": "FastAPI endpoints", "status": "built"},
        {"label": "Profile", "status": "planned"},  # a real data name is kept verbatim (FR-AUD-C5)
    ]
    out = apply_node_lenses(views, role="end_user")
    assert out[0]["label"] == "Home page"           # plain-ified structural label
    assert out[1]["technical"] is True              # jargon flagged
    assert out[2]["label"] == "Profile"             # data name unchanged


def test_apply_node_lenses_architect_keeps_labels_verbatim():
    views = [{"label": "home / index page", "status": "spec"}]
    out = apply_node_lenses(views, role="architect")
    assert out[0]["label"] == "home / index page"   # technical voice never plain-ifies


def test_apply_node_lenses_gap_floor_and_honest_skip():
    views = [
        {"label": "A", "status": "not_defined"},                              # gap
        {"label": "B", "status": "planned"},                                  # not a gap
        {"label": "C", "status": "not_defined", "route_state": "owned_elsewhere"},  # honest-skip
    ]
    out = apply_node_lenses(views, role="architect")
    assert out[0]["need_items"] is True
    assert out[1]["need_items"] is False
    assert out[2]["need_items"] is False            # honest-skip excluded from the floor


def test_has_jargon_and_constants_moved():
    assert has_jargon("export endpoints") is True
    assert has_jargon("Profile") is False
    assert "not_defined" in GAP_STATUSES
    assert "owned_elsewhere" in HONEST_SKIP_ROUTES


def test_apply_section_lenses_reorders_only_for_end_user():
    sections = [{"key": "scaffold"}, {"key": "pages"}, {"key": "forms"}]
    # architect: order preserved
    assert [s["key"] for s in apply_section_lenses(sections, voice="architect")] == \
        ["scaffold", "pages", "forms"]
    # end_user: leads with author-facing sections
    ordered = [s["key"] for s in apply_section_lenses(sections, voice="end_user")]
    assert ordered == ["pages", "forms", "scaffold"]


def test_compose_definitions_moved_out_of_compose():
    # FR-1 Verify (a): the lens definitions no longer live in compose.py (delegated, not duplicated).
    src = (
        Path(__file__).resolve().parents[3]
        / "src" / "startd8" / "wireframe_view" / "compose.py"
    ).read_text(encoding="utf-8")
    for token in ("def _display_label", "def _is_gap_item"):
        assert token not in src, f"{token} must move to node_lenses.py"
    tree = ast.parse(src)
    assigned = {
        t.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    assert "GAP_STATUSES" not in assigned
    assert "HONEST_SKIP_ROUTES" not in assigned
    assert "_END_USER_ORDER" not in assigned


# ── FR-2: the project_nodes bridge ───────────────────────────────────────────────────────────────

def test_project_nodes_basic_shape():
    # FR-2 Verify (a): a single node → one lens-annotated item-view with the {key} — {does} label.
    node = Node(key="FR-1", does="FR-1 sign in", status="spec")
    out = project_nodes([node], role="architect")
    assert len(out) == 1
    assert out[0]["label"] == "FR-1 — FR-1 sign in"
    assert {"label", "status", "detail", "technical", "need_items"} <= set(out[0])


def test_project_nodes_flags_jargon_for_end_user():
    # FR-2 Verify (b): a jargon label is flagged technical under the end_user voice.
    node = Node(key="X", does="FastAPI endpoints", status="spec")
    out = project_nodes([node], role="end_user")
    assert out[0]["technical"] is True


def test_project_nodes_need_items_gap_floor():
    gap = Node(key="G", does="todo", status="spec")               # spec → not_defined → gap
    ok = Node(key="K", does="done", status="built")               # built → planned → not a gap
    out = project_nodes([gap, ok], role="architect")
    by_key = {iv["label"].split(" — ")[0]: iv for iv in out}
    assert by_key["G"]["need_items"] is True
    assert by_key["K"]["need_items"] is False


# ── FR-3: node_lenses carries no WireframePlan dependency ────────────────────────────────────────

def test_node_lenses_does_not_import_wireframe_plan():
    # FR-3: node_lenses.py must not import WireframePlan/WireframeItem/WireframeSection, and the
    # module namespace must not expose them (the independence constraint is the whole point).
    import startd8.wireframe_view.node_lenses as nl

    for name in ("WireframePlan", "WireframeItem", "WireframeSection"):
        assert not hasattr(nl, name), f"node_lenses must not surface {name}"

    tree = ast.parse(_NODE_LENSES_SRC.read_text(encoding="utf-8"))
    imported_from: list[str] = []
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_from.append(node.module or "")
            imported_names.extend(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported_names.extend(a.name for a in node.names)
    # No import targets the wireframe plan/compose/view machinery.
    assert not any("wireframe.plan" in (m or "") for m in imported_from)
    assert not any(m.endswith("compose") or m.endswith("view") for m in imported_from)
    assert "WireframePlan" not in imported_names
    assert "WireframeItem" not in imported_names
    assert "WireframeSection" not in imported_names


# ── FR-4: the public surface is exported from the package root ────────────────────────────────────

def test_public_surface_exported_from_package_root():
    from startd8.wireframe_view import (  # noqa: F401  — resolution is the assertion
        GAP_STATUSES as _gs,
        HONEST_SKIP_ROUTES as _hsr,
        apply_node_lenses as _anl,
        has_jargon as _hj,
        project_nodes as _pn,
    )

    # Existing exports must remain (no symbols removed from the prior public surface).
    from startd8.wireframe_view import compose as _compose, render_html as _rh  # noqa: F401


# ── FR-7: project_nodes ↔ compose parity across all role×fluency combos ───────────────────────────

def _fixture_nodes() -> list[Node]:
    """≥2 sections (auth, ui) × ≥3 items each, spanning label patterns + statuses (FR-7)."""
    return [
        Node(key="FR-1", does="sign in", status="spec", category="auth"),
        Node(key="FR-2", does="reset password", status="built", category="auth"),
        Node(key="FR-3", does="view: user list", status="thin", category="auth"),
        Node(key="FR-4", does="home / index page", status="spec", category="ui"),
        Node(key="FR-5", does="page body: about", status="built", category="ui"),
        Node(key="FR-6", does="observability", status="invalid", category="ui"),
    ]


@pytest.mark.parametrize("role", ["end_user", "architect"])
@pytest.mark.parametrize("fluency", ["beginner", "intermediate", "advanced"])
def test_project_nodes_parity_with_compose(role, fluency):
    # FR-7: for the same set of nodes, project_nodes item labels equal compose's section item labels
    # under every role×fluency combo. Guards the bridge against drifting from the compose lens path.
    nodes = _fixture_nodes()
    plan = nodes_to_wireframe_plan(nodes)
    compose_labels = sorted(
        it["label"] for sec in compose(plan, role=role, fluency=fluency)["sections"]
        for it in sec["items"]
    )
    project_labels = sorted(iv["label"] for iv in project_nodes(nodes, role=role, fluency=fluency))
    assert project_labels == compose_labels
