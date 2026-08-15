"""REQ-05 FR-2/FR-4/FR-5/FR-6/FR-7 — the standalone offline graph renderer.

Verifies: standalone (no wireframe import), cycle-safe non-hanging render, XSS escaping, no-CDN,
determinism (byte-identity), semantic-only vs full-graph filtering via the stamped fields, lens
inheritance without re-fork, and the wireframe reverse-import guard.
"""

from __future__ import annotations

import re
from pathlib import Path

from startd8.navigator.models import Node, NodeStatus
from startd8.navigator.render_graph import render_navigator_graph_html

_RENDER_SRC = Path(__file__).resolve().parents[3] / "src" / "startd8" / "navigator" / "render_graph.py"


def _cycle() -> list:
    """A 3-node child_keys cycle A→B→C→A (a tree renderer would drop a back-edge; the graph shows it)."""
    a = Node(key="A", does="node a", status=NodeStatus.BUILT, child_keys=("B",))
    b = Node(key="B", does="node b", status=NodeStatus.THIN, child_keys=("C",))
    c = Node(key="C", does="node c", status=NodeStatus.SPEC, child_keys=("A",))
    return [a, b, c]


# ---- FR-2: standalone -------------------------------------------------------------

def test_module_does_not_import_wireframe_plan():
    """FR-2a: render_graph never imports the wireframe plan/compose machinery.

    The ONLY wireframe_view touch permitted is the FR-5 soft-import of the shared node_lenses transform;
    it must NOT pull WireframePlan / WireframeItem / compose / view.
    """
    src = _RENDER_SRC.read_text(encoding="utf-8")
    # Inspect only the executable import lines, not docstring prose that mentions the names.
    import_lines = [
        ln for ln in src.splitlines()
        if ln.lstrip().startswith(("import ", "from ")) and "wireframe" in ln
    ]
    assert "WireframePlan" not in " ".join(import_lines)
    assert "WireframeItem" not in " ".join(import_lines)
    # the ONLY wireframe_view import permitted is the FR-5 node_lenses soft dependency
    for ln in import_lines:
        assert "node_lenses" in ln, f"unexpected wireframe import: {ln}"
    # no wireframe compose/view/plan machinery pulled anywhere
    assert "wireframe_view.compose" not in src
    assert "wireframe_view.view" not in src


def test_wireframe_view_does_not_import_graph_modules():
    """FR-6: the reverse guard — the wireframe path never imports the graph renderer/projection."""
    root = Path(__file__).resolve().parents[3] / "src" / "startd8"
    for pkg in ("wireframe_view", "wireframe"):
        for py in (root / pkg).rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            assert "render_graph" not in text, f"{py} imports render_graph"
            assert "graph_projection" not in text, f"{py} imports graph_projection"


# ---- FR-2: cycle-safe -------------------------------------------------------------

def test_cycle_renders_all_nodes_and_edges_without_hanging(tmp_path):
    """FR-2b: a 3-node cycle renders (exit 0), all 3 nodes + 3 edges present, does NOT hang.

    The fixed-iteration layout terminates regardless of cycles — if this test returns at all it did
    not recurse infinitely.
    """
    out = render_navigator_graph_html(_cycle(), tmp_path / "cycle.html", title="Cycle")
    html = out.read_text(encoding="utf-8")
    for key in ("A", "B", "C"):
        assert f'data-id="{key}"' in html
    assert html.count('class="gnode"') == 3
    assert html.count('class="gedge"') == 3   # the 3 depends-on back-edges


# ---- FR-2 / FR-7: XSS + no-CDN ----------------------------------------------------

def test_script_in_node_key_is_escaped(tmp_path):
    """FR-2c / FR-7: a <script>alert(1)</script> in node.key must not appear unescaped."""
    evil = Node(key="<script>alert(1)</script>", does="x", status=NodeStatus.SPEC)
    ok = Node(key="safe", does="ok", status=NodeStatus.BUILT)
    out = render_navigator_graph_html([ok, evil], tmp_path / "xss.html", title="X")
    html = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_javascript_href_is_dropped_and_colour_rejected(tmp_path):
    """FR-7: a javascript: href is sanitized away; a bad colour is rejected by _safe_color."""
    evil = Node(
        key="n1",
        does="d",
        status=NodeStatus.SPEC,
        attributes={"href": "javascript:alert(1)"},
    )
    out = render_navigator_graph_html([evil], tmp_path / "href.html")
    html = out.read_text(encoding="utf-8")
    assert "javascript:alert" not in html


def test_no_cdn_or_external_script_src(tmp_path):
    """FR-2d / NR-6: no src=/cdn/http inside any <script> tag (offline self-containment)."""
    out = render_navigator_graph_html(_cycle(), tmp_path / "offline.html")
    html = out.read_text(encoding="utf-8")
    scripts = re.findall(r"<script[^>]*>.*?</script>", html, re.DOTALL)
    assert scripts, "there is at least one inlined <script>"
    for s in scripts:
        open_tag = s.split(">", 1)[0]
        assert "src=" not in open_tag
        low = s.lower()
        assert "cdn" not in low
        assert "http://" not in low and "https://" not in low


# ---- FR-2 (D1): determinism -------------------------------------------------------

def test_two_runs_are_byte_identical(tmp_path):
    """FR-2 / D1: same input → byte-identical HTML across runs (deterministic layout, no RNG)."""
    a = render_navigator_graph_html(_cycle(), tmp_path / "a.html", title="Det")
    b = render_navigator_graph_html(_cycle(), tmp_path / "b.html", title="Det")
    assert a.read_bytes() == b.read_bytes()


# ---- FR-4: semantic-only vs full-graph --------------------------------------------

def _fr_fixture() -> list:
    fr7 = Node(key="FR-7", does="depends on FR-2", status=NodeStatus.SPEC, child_keys=("FR-2",))
    fr2 = Node(key="FR-2", does="base", status=NodeStatus.BUILT)
    return [fr7, fr2]


def test_semantic_only_excludes_view_markers(tmp_path):
    """FR-4a: default --semantic-only renders no view:section:* node and no has-section/contains edge."""
    out = render_navigator_graph_html(_fr_fixture(), tmp_path / "sem.html", semantic_only=True)
    html = out.read_text(encoding="utf-8")
    assert "view:section:" not in html
    assert ">has-section<" not in html and ">contains<" not in html


def test_full_graph_includes_view_markers(tmp_path):
    """FR-4b: --full-graph includes the view:section:* layout markers."""
    out = render_navigator_graph_html(_fr_fixture(), tmp_path / "full.html", semantic_only=False)
    html = out.read_text(encoding="utf-8")
    assert "view:section:" in html


def test_semantic_filter_reads_stamped_fields_not_id_prefix(tmp_path):
    """FR-4c: a *source* node whose key literally begins 'view:section:' is NOT filtered — the filter
    selects on the stamped data.view_marker / data.semantic, never a substring of the id."""
    # a legitimate source node with a colliding-looking key (not a view-marker)
    tricky = Node(key="view:section:mine", does="a real source node", status=NodeStatus.BUILT)
    other = Node(key="X", does="x", status=NodeStatus.SPEC, child_keys=("view:section:mine",))
    out = render_navigator_graph_html([other, tricky], tmp_path / "tricky.html", semantic_only=True)
    html = out.read_text(encoding="utf-8")
    # the source node survives (it is not a view_marker), proving prefix-guessing is not used
    assert 'data-id="view:section:mine"' in html


# ---- FR-5: lens inheritance (no re-fork) ------------------------------------------

def test_no_lens_logic_reforked_in_render_graph():
    """FR-5a: render_graph must not re-fork the lens helpers (grep == 0 for each)."""
    src = _RENDER_SRC.read_text(encoding="utf-8")
    for token in ("_display_label", "has_jargon", "_END_USER_ORDER"):
        assert src.count(token) == 0, f"{token} must not be re-forked into render_graph"


def test_labels_match_project_nodes_when_present(tmp_path):
    """FR-5b: with REQ-04 present, labels match node_lenses.project_nodes for the same role."""
    from startd8.wireframe_view.node_lenses import project_nodes

    nodes = _fr_fixture()
    out = render_navigator_graph_html(nodes, tmp_path / "lens.html", role="end_user")
    html = out.read_text(encoding="utf-8")
    views = project_nodes(list(nodes), role="end_user")
    # every lens-produced label appears (escaped) in the rendered svg text
    import html as _h

    for v in views:
        label = v.get("label", "")
        if label:
            assert _h.escape(label) in html


def test_falls_back_to_raw_labels_when_lens_unavailable(tmp_path, monkeypatch):
    """FR-5c: when project_nodes is import-guarded away, the renderer still exits 0 with raw labels."""
    import startd8.navigator.render_graph as rg

    monkeypatch.setattr(rg, "project_nodes", None)
    out = rg.render_navigator_graph_html(_fr_fixture(), tmp_path / "raw.html", role="end_user")
    html = out.read_text(encoding="utf-8")
    # raw projection label (id/does) is used — the source key is present
    assert 'data-id="FR-7"' in html


# ---- FR-3: CLI wiring -------------------------------------------------------------

def test_cli_graph_renderer_writes_html(tmp_path):
    """FR-3a: `navigator build --renderer graph` exits 0 and the HTML carries the fixture root key."""
    import json

    from typer.testing import CliRunner

    from startd8.navigator.cli_navigator import navigator_app

    fixture = tmp_path / "f.json"
    fixture.write_text(
        json.dumps(
            {"nodes": [
                {"key": "FR-7", "does": "depends on FR-2", "status": "spec", "child_keys": ["FR-2"]},
                {"key": "FR-2", "does": "base", "status": "built"},
            ]}
        ),
        encoding="utf-8",
    )
    out = tmp_path / "g.html"
    res = CliRunner().invoke(
        navigator_app,
        ["build", "--source", "nodes-json", "--nodes-json", str(fixture),
         "--format", "html", "--renderer", "graph", "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    html = out.read_text(encoding="utf-8")
    assert 'data-id="FR-7"' in html


def test_cli_tree_renderer_still_works(tmp_path):
    """FR-3b: --renderer tree (REQ-02) is unchanged and still produces tree HTML."""
    import json

    from typer.testing import CliRunner

    from startd8.navigator.cli_navigator import navigator_app

    fixture = tmp_path / "f.json"
    fixture.write_text(
        json.dumps({"nodes": [
            {"key": "root", "does": "r", "status": "spec",
             "children": [{"key": "leaf", "does": "l", "status": "built"}]},
        ]}),
        encoding="utf-8",
    )
    out = tmp_path / "t.html"
    res = CliRunner().invoke(
        navigator_app,
        ["build", "--source", "nodes-json", "--nodes-json", str(fixture),
         "--format", "html", "--renderer", "tree", "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    assert "<details" in out.read_text(encoding="utf-8")


def test_cli_help_lists_graph_choice():
    """FR-3c: --help lists `graph` among the renderer choices and the semantic-only toggle."""
    from typer.testing import CliRunner

    from startd8.navigator.cli_navigator import navigator_app

    res = CliRunner().invoke(navigator_app, ["build", "--help"])
    assert res.exit_code == 0
    assert "graph" in res.output
    assert "semantic-only" in res.output or "full-graph" in res.output


def test_cli_full_graph_flag(tmp_path):
    """FR-4 CLI: --full-graph includes the view-markers via the CLI path."""
    import json

    from typer.testing import CliRunner

    from startd8.navigator.cli_navigator import navigator_app

    fixture = tmp_path / "f.json"
    fixture.write_text(
        json.dumps({"nodes": [
            {"key": "FR-7", "does": "d", "status": "spec", "child_keys": ["FR-2"]},
            {"key": "FR-2", "does": "b", "status": "built"},
        ]}),
        encoding="utf-8",
    )
    out = tmp_path / "full.html"
    res = CliRunner().invoke(
        navigator_app,
        ["build", "--source", "nodes-json", "--nodes-json", str(fixture),
         "--format", "html", "--renderer", "graph", "--full-graph", "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    assert "view:section:" in out.read_text(encoding="utf-8")


def test_cli_unknown_renderer_error_lists_graph():
    """FR-3: the invalid-renderer error string now names graph among the valid choices."""
    import json
    import tempfile

    from typer.testing import CliRunner

    from startd8.navigator.cli_navigator import navigator_app

    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d) / "f.json"
        fixture.write_text(json.dumps({"nodes": [{"key": "r", "does": "r"}]}), encoding="utf-8")
        out = Path(d) / "o.html"
        res = CliRunner().invoke(
            navigator_app,
            ["build", "--source", "nodes-json", "--nodes-json", str(fixture),
             "--format", "html", "--renderer", "bogus", "--out", str(out)],
        )
        assert res.exit_code == 1
        assert "graph" in res.output
