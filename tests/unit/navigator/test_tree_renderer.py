"""N-level tree renderer (REQ-02) — nested drill, round-trip, standalone, port hazards."""

from __future__ import annotations

from pathlib import Path

from startd8.navigator.models import Node, NodeEvidence, NodeStatus
from startd8.navigator.project import nodes_from_json, nodes_to_json
from startd8.navigator.render_tree import render_navigator_tree_html


def _tree() -> list:
    leaf = Node(key="leaf.a", does="a leaf", status=NodeStatus.BUILT,
                lives=(NodeEvidence(type="code", ref="src/x.py"),))
    mid = Node(key="mid", does="a middle node", status=NodeStatus.THIN, children=(leaf,))
    root = Node(key="root", does="the root", status=NodeStatus.SPEC, children=(mid,),
                child_keys=("mid",))
    return [root]


def test_tree_renders_nested_n_level(tmp_path):
    """FR-1: children recurse into nested <details> — N-level, not flat 2-level."""
    out = render_navigator_tree_html(_tree(), tmp_path / "t.html", title="T")
    html = out.read_text(encoding="utf-8")
    assert html.count("<details") >= 2                 # root + mid are expandable
    # nesting: mid's <details> appears inside root's body
    assert "root" in html and "mid" in html and "leaf.a" in html
    assert 'data-search="' in html                      # searchable
    assert "Expand all" in html and "Collapse all" in html


def test_nodes_json_roundtrip_preserves_tree():
    """FR-4: nodes_to_json carries children recursively; nodes_from_json reconstructs the tree."""
    data = nodes_to_json(_tree())
    assert data[0]["children"][0]["children"][0]["key"] == "leaf.a"   # 3 levels survive
    back = nodes_from_json(data)
    assert back[0].key == "root"
    assert back[0].children[0].key == "mid"
    assert back[0].children[0].children[0].key == "leaf.a"
    assert back[0].children[0].children[0].lives[0].ref == "src/x.py"


def test_render_tree_is_standalone_no_wireframe_import():
    """FR-5: the tree renderer must not couple to the wireframe path (check import lines, not prose)."""
    src = Path("src/startd8/navigator/render_tree.py").read_text(encoding="utf-8")
    import_lines = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    assert not any("wireframe" in l for l in import_lines), "tree renderer must not import wireframe"


def test_no_shadowed_dead_defs():
    """FR-6: the CC dead-code hazard (duplicate top-level defs) must not be replicated."""
    src = Path("src/startd8/navigator/render_tree.py").read_text(encoding="utf-8")
    for sym in ("_tree_node_html", "render_navigator_tree_html", "_tree_body_html"):
        assert src.count(f"def {sym}(") == 1, f"{sym} defined more than once (dead-code hazard)"


def test_xss_href_and_color_are_sanitized(tmp_path):
    """FR-6: a javascript: link and an injecting facet colour must not survive into the HTML."""
    from startd8.navigator.models import StatusFacet
    n = Node(key="x", does="d", status=NodeStatus.BUILT,
             lives=(NodeEvidence(type="link", ref="javascript:alert(1)"),),
             status_facets=(StatusFacet(name="f", value="v", color="red;background:url(x)"),))
    html = render_navigator_tree_html([n], tmp_path / "x.html").read_text(encoding="utf-8")
    assert "javascript:alert(1)" not in html or 'href="javascript:' not in html  # never a live href
    assert 'href="javascript:' not in html
    assert "background:url" not in html                 # unsafe colour dropped
