"""Inspect — find the DERIVATIVE value of non-node-driven chrome (legacy value SUSPECTED, not guilt).

The constructive inverse of the Cruft Sentinel. The cruft loop presumes **guilt** — all content is
cruft until it proves its origin, and an orphan is purged. The inspect loop presumes a **legacy
value** — these elements (the masthead, the summary band, the legend) were built for a reason — and
asks the opposite question: *what derivative information or updated context would make each element
useful in the CURRENT sense* (a node-debugging navigator)? Its output is not a purge list but a
**repurpose / enhancement worklist**: for each element, its original intent, the derivative value it
could carry now, and whether that value is already REALIZED (dialect-corrected / re-aimed) or a
CANDIDATE (latent value worth wiring).

Object = the non-node-driven chrome (the sections + node cards are node-driven and out of scope).
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..wireframe.plan import WireframePlan
from ..wireframe.profile import RenderProfile
from .models import Node
from .provenance import chrome_provenance

# The node-driven elements (their content comes from the nodes themselves) — out of scope here.
_NODE_DRIVEN = {"sections", "node_keys"}

# Authored inspection per non-node-driven chrome element: its original (app-scaffold) intent, the
# DERIVATIVE value it could carry in the updated (node-debugging) sense, and a verdict —
#   realized  : the derivative value is already serving (dialect-corrected / profile-re-aimed);
#   candidate : latent derivative value not yet wired (the enhancement worklist).
INSPECTIONS: Dict[str, Dict[str, str]] = {
    "eyebrow": {
        "original": "app breadcrumb (Wireframe · app_name)",
        "derivative": "source identity — which consumer + doc this view reflects",
        "verdict": "realized",
    },
    "headline": {
        "original": "'A first look at your app'",
        "derivative": "the view's title in its own domain",
        "verdict": "realized",
    },
    "summary_meta": {
        "original": "WIREFRAME_META — 'previews the $0 generation before any code'",
        "derivative": "the view's one-line purpose statement for this consumer",
        "verdict": "realized",
    },
    "why": {
        "original": "architect wireframe guidance — 'approve the shape at the DATA MODEL bookend'",
        "derivative": "how to READ this view (each field/requirement is a Node)",
        "verdict": "realized",
    },
    "do": {
        "original": "architect do-list — 'read top-down, approve if the shape is right'",
        "derivative": "the reading/scan order for this consumer's nodes",
        "verdict": "realized",
    },
    "status_band": {
        "original": "app status roll-up (planned / defaults / not_defined counts) — how much is ready to build",
        "derivative": "the GROUNDING COMPOSITION of the node set (N grounded/spec/thin) — a live debugging"
                      " metric; in an updated sense an interactive FILTER (click a status → filter nodes)"
                      " that pairs with the debug panel's provenance readout",
        "verdict": "candidate",
    },
    "shape_band": {
        "original": "app entity/page/view counts — the app's structural size",
        "derivative": "the node graph's scope (Nodes | Sections); derivative context: per-group"
                      " distribution / density to orient the debugger",
        "verdict": "candidate",
    },
    "legend": {
        "original": "app status-dot meanings (planned/not_defined = 'not set up yet')",
        "derivative": "the provenance/status colour KEY for the node badges — decode the dots",
        "verdict": "realized",
    },
    "section_lead": {
        "original": "'What your app includes'",
        "derivative": "the grouping intro ('What a Node is made of' / 'What this spec defines')",
        "verdict": "realized",
    },
}


def inspect_elements(
    nodes: Sequence[Node], plan: WireframePlan, profile: RenderProfile
) -> List[Dict[str, Any]]:
    """Join the live chrome provenance with the authored inspection for each non-node-driven element.

    An element present in the chrome but missing an inspection is itself surfaced (verdict
    ``uninspected``) — the inspect map mirrors the chrome set, so a new element can't slip past.
    """
    prov = {r["element"]: r for r in chrome_provenance(nodes, plan, profile)
            if r["element"] not in _NODE_DRIVEN and r["element"] != "doc_title"}
    out: List[Dict[str, Any]] = []
    for el, r in prov.items():
        insp = INSPECTIONS.get(el, {"original": "(unknown)", "derivative": "", "verdict": "uninspected"})
        out.append({"element": el, "origin": r.get("origin", ""), "value": r.get("value", ""), **insp})
    return out
