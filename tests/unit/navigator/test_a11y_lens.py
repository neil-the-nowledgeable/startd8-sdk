"""REQ-26 — a11y as a cross-topology lens. FR-keyed pins.

a11y is lifted from the flat-only renderer into ONE generic cross-topology projection
(``a11y_view_of_nodes``) wrapped by ONE shared accessible shell (the no-fork chokepoint). Tree/graph/
diff each render an accessible semantic view through it; the flat requirement view is byte-identical.
"""

from __future__ import annotations

import pytest

from startd8.navigator.models import Node
from startd8.navigator.render_a11y import (
    ReqView,
    a11y_view_of_diff,
    a11y_view_of_nodes,
    check_no_bleed,
    render_a11y_graph_to_file,
    render_a11y_to_file,
    render_a11y_tree_to_file,
    render_html,
)

pytestmark = pytest.mark.unit


def _n(key, does="does", *, status_key="grounded", status=None, child_keys=(), **attrs):
    a = {"status_key": status_key, **attrs}
    kw = {"key": key, "does": does, "child_keys": tuple(child_keys), "attributes": a}
    if (
        status is not None
    ):  # the real Node.status field (what diff_nodes compares), not the display word
        kw["status"] = status
    return Node(**kw)


def _has_a11y_chrome(html: str) -> bool:
    return (
        '<main id="main"' in html and "skip-link" in html and 'nav class="toc"' in html
    )


# ── FR-1: a11y is a lens value in the shared transform, consumed by >1 renderer ─────────────────────


def test_fr1_generic_projection_consumed_by_more_than_one_renderer(tmp_path):
    nodes = [_n("FR-1", "build a thing")]
    tree = tmp_path / "t.html"
    graph = tmp_path / "g.html"
    render_a11y_tree_to_file(nodes, tree)
    render_a11y_graph_to_file(nodes, graph)
    # both renderers route through the ONE shell (same accessible chrome) — a11y is not renderer-forked
    assert _has_a11y_chrome(tree.read_text())
    assert _has_a11y_chrome(graph.read_text())


def test_fr1_a11y_composes_with_the_audience_lens(tmp_path):
    # the a11y modality composes with the node_lenses audience lens (audience × a11y): a role changes
    # the spoken label. "observability" -> end_user "Monitoring" (node_lenses._END_USER_ITEM_LABELS).
    nodes = [_n("FR-1", "observability")]
    raw = a11y_view_of_nodes(nodes, role=None)
    lensed = a11y_view_of_nodes(nodes, role="end_user")
    assert "observability" in raw
    assert "Monitoring" in lensed and lensed != raw


# ── FR-2: a11y-of-tree (accessible N-level drill) ───────────────────────────────────────────────────


def test_fr2_tree_nests_by_child_keys():
    parent = _n("A", "root", child_keys=("B",))
    child = _n("B", "leaf")
    html = a11y_view_of_nodes([parent, child])
    assert _has_a11y_chrome(html)
    # the child region is nested INSIDE the parent region (drill hierarchy), not a flat sibling
    ai, bi = html.index('id="n-A"'), html.index('id="n-B"')
    parent_close = html.index("</details>", ai)
    assert ai < bi < parent_close, "child must render inside the parent's drill region"


# ── FR-3: a11y-of-graph (navigable textual equivalent of the node-link structure) ───────────────────


def test_fr3_graph_edges_spoken_as_relations():
    nodes = [_n("FR-1", "a"), _n("CAP-x", "b")]
    edges = [{"from": "FR-1", "to": "CAP-x", "label": "serves"}]
    html = a11y_view_of_nodes(nodes, edges=edges)
    assert "relations:" in html
    assert (
        "serves → CAP-x" in html
    )  # the edge is a navigable textual relation (inv. 8), not a blob


def test_fr3_graph_writer_end_to_end(tmp_path):
    # child_keys → nodes_to_graph draws a contains-child edge; the a11y graph speaks it.
    nodes = [_n("A", "root", child_keys=("B",)), _n("B", "leaf")]
    out = tmp_path / "g.html"
    render_a11y_graph_to_file(nodes, out)
    txt = out.read_text()
    assert "relations:" in txt and "→ B" in txt


# ── FR-4: a11y-of-diff (accessible delta) ───────────────────────────────────────────────────────────


def test_fr4_diff_regions_are_navigable():
    from startd8.navigator.diff import diff_nodes

    # B changes status (a real StatusTransition), A removed, C added, D's `does` changed.
    before = [_n("A", "old"), _n("B", "stays", status="spec"), _n("D", "d1")]
    after = [_n("B", "stays", status="built"), _n("C", "new"), _n("D", "d2")]
    delta = diff_nodes(before, after)
    html = a11y_view_of_diff(delta)
    assert _has_a11y_chrome(html)
    for anchor in ('id="added"', 'id="removed"', 'id="changed"', 'id="transitions"'):
        assert anchor in html
    assert "C" in html and "A" in html  # added C, removed A appear as regions
    assert "spec → built" in html  # the status transition is spoken before → after


# ── FR-5: check_no_bleed across every topology ──────────────────────────────────────────────────────


def test_fr5_no_bleed_on_tree_and_graph():
    nodes = [_n("A", "root", child_keys=("B",)), _n("B", "leaf")]
    edges = [{"from": "A", "to": "B", "label": "contains-child"}]
    assert check_no_bleed(a11y_view_of_nodes(nodes))["pass"] is True
    assert check_no_bleed(a11y_view_of_nodes(nodes, edges=edges))["pass"] is True


def test_fr5_injected_wireframe_bleed_fails_each_topology():
    # a leaked wireframe token ("Entities") must fail the bleed guard on any topology's a11y view
    leak = a11y_view_of_nodes([_n("A", "Entities")]) + "<p>Entities</p>"
    assert check_no_bleed(leak)["pass"] is False


# ── FR-6: no re-fork (FF-1 closed for a11y) ─────────────────────────────────────────────────────────


def test_fr6_synthetic_renderer_inherits_a11y_with_zero_a11y_code():
    # a "new renderer" is nothing but: hand its List[Node] to the generic projection. No a11y-specific
    # code, no per-renderer fork — it inherits the accessible view.
    def my_new_renderer(nodes):
        return a11y_view_of_nodes(nodes, title="My New Topology")

    html = my_new_renderer([_n("Z", "a node")])
    assert _has_a11y_chrome(html)
    assert (
        'class="tag' in html
    )  # status is a WORD (WCAG 1.4.1), inherited, not re-implemented


# ── FR-7: additive, byte-identical flat case ───────────────────────────────────────────────────────


def test_fr7_flat_render_untouched(tmp_path):
    # the flat requirement view still goes through render_html (ReqView) — NOT the new cross-topology
    # projection — so it is byte-identical to render_html for the same nodes.
    nodes = [_n("O-1", "an outcome", status_key="goal", kind="objective")]
    out = tmp_path / "flat.html"
    render_a11y_to_file(nodes, out, title="flat")
    assert out.read_text() == render_html(ReqView(list(nodes)), title="flat")
