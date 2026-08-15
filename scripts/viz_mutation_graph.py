#!/usr/bin/env python3
"""viz_mutation_graph — render the requirements-visualization capability's MUTATION lineage as a Node tree.

Self-referential dogfood: the visualization capability visualizing *its own evolution*, through the
N-level tree renderer it just grew (REQ-02). Each node is one mutation, tagged with the AXIS it moved
along (presentation · abstraction · source · evidence · topology · audience · self-reference ·
governance) and its REQ/PLAN. Declared here (Kagami: the graph is a mirror of this declaration, not a
hand-drawn HTML), so re-running reproduces it as the analysis (`VISUALIZATION_VARIANTS_ANALYSIS.md`)
evolves.

    python3 scripts/viz_mutation_graph.py --out /tmp/viz-mutations-tree.html
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from startd8.navigator.models import Node, NodeEvidence, NodeStatus  # noqa: E402
from startd8.navigator.render_tree import render_navigator_tree_html  # noqa: E402


def _n(key, does, axis, *, status=NodeStatus.BUILT, req="", mutation="", lives=(), children=()):
    attrs = {"axis": axis}
    if req:
        attrs["req"] = req
    if mutation:
        attrs["mutation"] = mutation
    return Node(
        key=key, does=does, status=status, category=axis,
        lives=tuple(NodeEvidence(type="code", ref=r) for r in lives),
        children=tuple(children), attributes=attrs,
    )


def lineage() -> list:
    # Leaves of the debug layer + loop family (M6/M7) — the self-inspection + governance mutations.
    debug = [
        _n("viz.structure-only", "bare keys + structural metadata, no prose", "self-reference", req="REQ-01 FR-11"),
        _n("viz.combined", "content AND structural metadata together", "self-reference", req="REQ-01 FR-12"),
        _n("viz.scaffold-mode", "label each region by role + layer (control/descriptive/computed/node)", "self-reference", req="REQ-01 FR-15"),
        _n("viz.hide-app-scaffold", "non-destructive multi-stage cruft purge toggle", "governance", req="REQ-01 FR-14"),
        _n("viz.provenance-readout", "live chrome_score / cruft in-view", "governance", req="REQ-01 FR-13"),
        _n("viz.status-filter", "status roll-up as an interactive grounding filter", "audience", req="REQ-01 PF-1"),
    ]
    loops = [
        _n("viz.pilot-loop", "improve a node's grounding, per-node", "governance", lives=["scripts/navigator_pilot_loop.py"]),
        _n("viz.content-loop", "improve a node's authored content (Name/does/verify)", "governance", lives=["scripts/navigator_content_loop.py"]),
        _n("viz.origin-audit", "prove each chrome element's origin (chrome_score)", "governance", lives=["scripts/navigator_origin_audit.py"]),
        _n("viz.cruft-sentinel", "all content cruft until proven → /audit-then-metabolize", "governance", lives=["scripts/navigator_cruft_loop.py"]),
        _n("viz.inspect-loop", "legacy value: find derivative value → /enhancement-backlog", "governance", lives=["scripts/navigator_inspect_loop.py"]),
    ]
    typed_grounding = _n(
        "viz.typed-grounding", "lives/confidence/status derived + survive compose", "evidence",
        req="REQ-01", lives=["src/startd8/navigator/models.py"],
        children=[
            _n("viz.node-schema-source", "the Node model renders ITSELF (Kagami mirror)", "self-reference",
               req="REQ-01", lives=["src/startd8/navigator/sources_node_schema.py"]),
            _n("viz.debug-layer", "meta-debugging view modes over the nodes", "self-reference",
               req="REQ-01 FR-11..15", children=debug),
            _n("viz.loop-family", "the five governance loops (prove/salvage the render)", "governance",
               children=loops),
        ],
    )
    nav_sources = _n(
        "viz.navigator-sources", "invert ingestion — the SDK renders its own navigators", "source",
        req="REQ-01", lives=["src/startd8/navigator/sources_requirements.py",
                             "src/startd8/navigator/sources_capability.py"],
        children=[typed_grounding],
    )
    render_profile = _n(
        "viz.render-profile", "decouple domain vocabulary + chrome from the engine (the key seam)",
        "abstraction", req="REQ-01", lives=["src/startd8/wireframe/profile.py"],
        children=[
            nav_sources,
            _n("viz.tree-renderer", "N-level drill over node.children (2-level → N-level)", "topology",
               status=NodeStatus.BUILT, req="REQ-02", lives=["src/startd8/navigator/render_tree.py"],
               children=[_n("viz.nodes-json-seam", "accept a pre-projected graph — the adopter seam",
                            "source", req="REQ-02 FR-2", lives=["src/startd8/navigator/project.py"])]),
            _n("viz.a11y-renderer", "semantic screen-reader ReqView (audience: accessibility)", "audience",
               status=NodeStatus.SPEC, req="REQ-03",
               children=[_n("viz.corpus-index", "drill-to-leaf across many docs (doc → corpus)",
                            "topology", status=NodeStatus.SPEC, req="REQ-03")]),
        ],
    )
    wireframe = _n(
        "viz.wireframe-renderer", "automate the render; $0 deterministic app-shape preview", "presentation",
        lives=["src/startd8/wireframe_view/view.py"], children=[render_profile],
    )
    ancestor = _n(
        "viz.fsn-markdown-navigator", "hand-maintained markdown navigators — evidence-rotten (the ur-form)",
        "presentation", status=NodeStatus.DEPRECATED, children=[wireframe],
    )
    root = Node(
        key="viz.lineage",
        does="Requirements Visualization — mutation lineage; each node is one mutation along an axis",
        status=NodeStatus.BUILT, category="root", children=(ancestor,),
        attributes={"axis": "root",
                    "readiness": "9 mutations · 8 axes · REQ-01 built · REQ-02 built · REQ-03 spec"},
    )
    return [root]


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("/tmp/viz-mutations-tree.html"))
    args = ap.parse_args(argv[1:])
    out = render_navigator_tree_html(
        lineage(), args.out,
        title="Requirements Visualization — mutation lineage",
        subtitle="each node = one mutation, tagged by axis · rendered through the tree renderer it grew (REQ-02)",
        open_depth=4,
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
