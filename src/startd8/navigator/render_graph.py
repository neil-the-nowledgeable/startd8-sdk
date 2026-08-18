"""Graph / network-topology renderer — standalone offline node-link HTML over the Node graph.

REQ-05 FR-2. Fills the empty TOPOLOGY cell (``VISUALIZATION_VARIANTS_ANALYSIS`` §7): every renderer
built so far (wireframe, tree REQ-02, a11y/index REQ-03) draws a **tree** — a single-parent recursion
that structurally cannot show back-edges, multiple parents, or cycles. This renderer draws the Node
relationships as a general **graph**: ``child_keys`` dependency edges (which can cross the tree and form
cycles), plus ``serves``/``built_by``/``delivers`` cross-references and the ``children`` containment
edges, each visually distinguished by kind.

Standalone by design: it imports **only** ``.models``, ``.graph_projection`` and ``.render_tree`` (for
the shared XSS helpers ``_safe_href``/``_safe_color`` — reused, never re-copied, Kagami). It NEVER
imports ``wireframe_view`` / ``WireframePlan``, so the deterministic app-scaffold path is byte-identical
(FR-6). The audience × fluency lenses are inherited from the shared ``wireframe_view.node_lenses``
transform behind a soft-import guard (FR-5) — no lens logic is re-forked here.

Layout (LOCKED D1): the node x/y are computed **deterministically in Python** — seeded from the
projection's built-in ``at:{x,y}`` coordinates, then refined by a FIXED-ITERATION force pass (constant
iteration count, no RNG; any tie-break jitter is derived from ``key`` hash, never ``random``). The
output is a single self-contained HTML doc with a static ``<svg>`` (nodes + edges + edge labels +
kind-distinguished styling) and a thin CSS/JS layer for pan/zoom/hover-highlight-neighbours ONLY — no
live physics sim. Same input → byte-identical bytes; cycle-safe by construction (fixed iterations,
never a DAG recursion). No CDN, no ``<script src>`` (NR-6).
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .graph_projection import nodes_to_graph, validate_graph_model
from .models import Node, NodeStatus
from .render_tree import _safe_color, _safe_href  # reuse — do not re-copy (Kagami, D2)

# FR-5 soft dependency: the shared lens transform. Absent REQ-04 the renderer falls back to raw labels
# and still exits 0. project_nodes returns a positional flat list of item-view dicts (one per node, in
# input order) — zip by index against the same flat node list (D3).
try:  # pragma: no cover - exercised by the import-guard test via monkeypatch
    from ..wireframe_view.node_lenses import project_nodes
except ImportError:  # pragma: no cover
    project_nodes = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Visual constants — a minimal offline dark shell consistent with _TREE_CSS (NR-4).
# ---------------------------------------------------------------------------

# The five semantic edge kinds get distinct colours + a dash pattern so the network reads at a glance.
_EDGE_STYLE: Dict[str, Tuple[str, str]] = {
    # label:            (stroke colour, stroke-dasharray)
    "depends-on": ("#f85149", ""),  # dependency — solid red
    "serves": ("#3fb950", "5 3"),  # serves — dashed green
    "built-by": ("#58a6ff", "2 3"),  # built-by — dotted blue
    "delivers": ("#d29922", "7 3"),  # delivers — long-dash amber
    "contains-child": ("#9aa4b2", "1 4"),  # containment — faint grey
    # REQ-16/REQ-20 typed derivation edges — the compilation + feedback loop, visibly distinguished:
    "derived-from": ("#39c5cf", ""),  # forward grounding — solid cyan
    "revises": (
        "#bc8cff",
        "6 3",
    ),  # backward FEEDBACK proposal (REQ-20) — dashed violet
    # presentation-only view markers (only reachable under --full-graph)
    "has-section": ("#3a4150", "2 6"),
    "contains": ("#3a4150", "2 6"),
}
_DEFAULT_EDGE_STYLE = ("#6b7280", "")

# Node fill by NODE-SCHEMA status (mirrors _TREE_CSS status accents).
_STATUS_FILL: Dict[str, str] = {
    NodeStatus.BUILT: "#3fb950",
    NodeStatus.THIN: "#d29922",
    NodeStatus.SPEC: "#58a6ff",
    NodeStatus.DEPRECATED: "#f85149",
}
_SECTION_FILL = "#30363d"  # view-marker section nodes (full-graph only)
_DEFAULT_FILL = "#484f58"

# SVG canvas (viewBox units). Node ``at`` coords are 0..1 fractions of these.
_W = 1600
_H = 1000
_MARGIN = 80
_NODE_R = 9
_ITERATIONS = 60  # FIXED — cycle-safe, deterministic, no early-exit on convergence

_GRAPH_CSS = """
:root{--bg:#0f1115;--card:#171a21;--edge:#262b36;--fg:#e6e9ef;--mut:#9aa4b2;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
header{position:sticky;top:0;z-index:5;background:var(--bg);
border-bottom:1px solid var(--edge);padding:14px 20px;}
h1{margin:0;font-size:17px;font-weight:650}
.sub{color:var(--mut);font-size:12.5px;margin-top:3px}
.controls{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button{background:var(--card);border:1px solid var(--edge);color:var(--fg);
border-radius:7px;padding:7px 11px;font-size:12.5px;cursor:pointer}
button:hover{border-color:#3a4150}
.legend{color:var(--mut);font-size:12px;margin-left:auto;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.legend .swatch{display:inline-block;width:22px;height:0;border-top-width:3px;border-top-style:solid;
vertical-align:middle;margin-right:5px}
#stage{width:100vw;height:calc(100vh - 96px);overflow:hidden;cursor:grab}
#stage.grabbing{cursor:grabbing}
svg{display:block;width:100%;height:100%;touch-action:none}
.gnode circle{stroke:#0b0d11;stroke-width:1.5px;cursor:pointer}
.gnode text{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;fill:var(--fg);
pointer-events:none;paint-order:stroke;stroke:#0b0d11;stroke-width:3px}
.gedge{fill:none}
.gedge-label{font:9.5px ui-monospace,Menlo,monospace;fill:var(--mut);pointer-events:none}
.dim{opacity:.12}
.hot{opacity:1}
a.nodelink{text-decoration:none}
"""

# Pan/zoom + hover-highlight-neighbours ONLY (NR-2 — no editing, no physics). Layout is already baked in.
_GRAPH_JS = """
(function(){
  var stage=document.getElementById('stage');
  var root=document.getElementById('viewport');
  if(!stage||!root)return;
  var tx=0,ty=0,scale=1,dragging=false,sx=0,sy=0;
  function apply(){root.setAttribute('transform','translate('+tx+' '+ty+') scale('+scale+')');}
  stage.addEventListener('wheel',function(e){
    e.preventDefault();
    var r=stage.getBoundingClientRect();
    var mx=e.clientX-r.left, my=e.clientY-r.top;
    var f=e.deltaY<0?1.1:1/1.1;
    var ns=Math.min(6,Math.max(0.15,scale*f));
    tx=mx-(mx-tx)*(ns/scale); ty=my-(my-ty)*(ns/scale); scale=ns; apply();
  },{passive:false});
  stage.addEventListener('mousedown',function(e){dragging=true;sx=e.clientX-tx;sy=e.clientY-ty;stage.classList.add('grabbing');});
  window.addEventListener('mousemove',function(e){if(!dragging)return;tx=e.clientX-sx;ty=e.clientY-sy;apply();});
  window.addEventListener('mouseup',function(){dragging=false;stage.classList.remove('grabbing');});
  document.getElementById('reset').onclick=function(){tx=0;ty=0;scale=1;apply();};
  // hover-highlight-neighbours
  var adj={};
  [].forEach.call(document.querySelectorAll('.gedge'),function(ed){
    var a=ed.getAttribute('data-from'),b=ed.getAttribute('data-to');
    (adj[a]=adj[a]||{})[b]=1;(adj[b]=adj[b]||{})[a]=1;
  });
  function setHL(id){
    var keep={}; keep[id]=1; var nb=adj[id]||{}; for(var k in nb)keep[k]=1;
    [].forEach.call(document.querySelectorAll('.gnode'),function(n){
      var nid=n.getAttribute('data-id');
      n.classList.toggle('dim',!keep[nid]); n.classList.toggle('hot',!!keep[nid]);
    });
    [].forEach.call(document.querySelectorAll('.gedge,.gedge-label'),function(ed){
      var a=ed.getAttribute('data-from'),b=ed.getAttribute('data-to');
      var on=(a===id||b===id); ed.classList.toggle('dim',!on); ed.classList.toggle('hot',on);
    });
  }
  function clearHL(){
    [].forEach.call(document.querySelectorAll('.dim,.hot'),function(el){el.classList.remove('dim');el.classList.remove('hot');});
  }
  [].forEach.call(document.querySelectorAll('.gnode'),function(n){
    n.addEventListener('mouseenter',function(){setHL(n.getAttribute('data-id'));});
    n.addEventListener('mouseleave',clearHL);
  });
})();
"""


def _det_jitter(key: str) -> Tuple[float, float]:
    """A tiny deterministic offset derived from the node key hash (never ``random`` — D1).

    Returns dx,dy in [-0.5, 0.5) fractions of a layout cell, used only to break exact coordinate ties
    so two nodes seeded at the same ``at`` don't stack perfectly on top of each other.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    dx = digest[0] / 255.0 - 0.5
    dy = digest[1] / 255.0 - 0.5
    return dx, dy


def _ground_up_rank_y(edges: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """REQ-feature-capability-composition-rollup FR-4 — a ground-up rank seed: a node that is the TARGET
    of a ``serves`` edge (the capability/objective a feature composes up to) ranks at the ROOT band (small
    y / top); a node that is the SOURCE of a ``serves`` edge (a composing feature) ranks at the BASE (large
    y). So a capability is shown assembled bottom-up from its features. Deterministic, no new renderer.
    """
    targets, sources = set(), set()
    for e in edges:
        if e.get("label") == "serves":
            if isinstance(e.get("to"), str):
                targets.add(e["to"])
            if isinstance(e.get("from"), str):
                sources.add(e["from"])
    rank: Dict[str, float] = {}
    for t in targets:
        rank[t] = 0.15  # capability / objective → root band (top)
    for s in sources:
        if (
            s not in targets
        ):  # a pure feature (composes up, nothing composes up to it) → base
            rank[s] = 0.85
    return rank


def _layout(
    graph_nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    rank_direction: Optional[str] = None,
) -> Dict[str, Tuple[float, float]]:
    """Deterministic force-refined layout → {node_id: (x_px, y_px)} in viewBox units.

    Seeds each node from its projection ``at:{x,y}`` (a 0..1 fraction), adds a key-derived jitter, then
    runs a FIXED number of force iterations (repulsion between all pairs + spring pull along edges).
    Constant iteration count and no RNG ⇒ byte-identical across runs and cycle-safe (the force model
    never recurses; a cycle is just three mutual springs). ``rank_direction="ground-up"`` overrides the
    seed y by a serves-composition rank (capabilities at the root band, features at the base — FR-4);
    ``None`` (default) keeps the projection's y so existing renders are byte-identical.
    """
    inner_w = _W - 2 * _MARGIN
    inner_h = _H - 2 * _MARGIN
    rank_y = _ground_up_rank_y(edges) if rank_direction == "ground-up" else {}
    ids: List[str] = []
    pos: Dict[str, List[float]] = {}
    for gn in graph_nodes:
        nid = gn.get("id")
        if not isinstance(nid, str) or not nid:
            continue
        at = gn.get("at") or {}
        fx = float(at.get("x", 0.5))
        fy = rank_y.get(
            nid, float(at.get("y", 0.5))
        )  # FR-4: ground-up rank seed overrides the projection y
        jx, jy = _det_jitter(nid)
        x = _MARGIN + (fx + jx * 0.02) * inner_w
        y = _MARGIN + (fy + jy * 0.02) * inner_h
        pos[nid] = [x, y]
        ids.append(nid)

    if len(ids) <= 1:
        return {nid: (p[0], p[1]) for nid, p in pos.items()}

    # Edge list restricted to placed nodes.
    springs: List[Tuple[str, str]] = []
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in pos and b in pos and a != b:
            springs.append((a, b))

    # Force constants (deterministic; tuned for the fixed viewBox).
    k_rep = (inner_w * inner_h) / max(len(ids), 1)  # repulsion strength
    ideal = (inner_w + inner_h) / (2 * max(len(ids) ** 0.5, 1))  # ideal spring length
    step = 0.09

    for _ in range(_ITERATIONS):
        disp: Dict[str, List[float]] = {nid: [0.0, 0.0] for nid in ids}
        # pairwise repulsion (O(n^2); n is small for a requirements graph)
        for i in range(len(ids)):
            ai = ids[i]
            ax, ay = pos[ai]
            for j in range(i + 1, len(ids)):
                bj = ids[j]
                bx, by = pos[bj]
                dx = ax - bx
                dy = ay - by
                dist2 = dx * dx + dy * dy
                if dist2 < 1e-6:
                    # deterministic tie-break nudge from the pair identity, never random
                    dh = hashlib.sha256((ai + "|" + bj).encode()).digest()
                    dx = (dh[0] / 255.0 - 0.5) * 0.01 + 1e-3
                    dy = (dh[1] / 255.0 - 0.5) * 0.01 + 1e-3
                    dist2 = dx * dx + dy * dy
                dist = dist2**0.5
                force = k_rep / dist2
                ux, uy = dx / dist, dy / dist
                disp[ai][0] += ux * force
                disp[ai][1] += uy * force
                disp[bj][0] -= ux * force
                disp[bj][1] -= uy * force
        # spring attraction along edges
        for a, b in springs:
            ax, ay = pos[a]
            bx, by = pos[b]
            dx = ax - bx
            dy = ay - by
            dist = (dx * dx + dy * dy) ** 0.5 or 1e-6
            force = (dist * dist) / ideal * 0.0006
            ux, uy = dx / dist, dy / dist
            disp[a][0] -= ux * force
            disp[a][1] -= uy * force
            disp[b][0] += ux * force
            disp[b][1] += uy * force
        # apply with damping + clamp to canvas
        for nid in ids:
            p = pos[nid]
            p[0] += disp[nid][0] * step
            p[1] += disp[nid][1] * step
            p[0] = min(_W - _MARGIN, max(_MARGIN, p[0]))
            p[1] = min(_H - _MARGIN, max(_MARGIN, p[1]))

    # FR-4: in ground-up mode re-clamp each ranked node's y to its rank band AFTER the force pass, so a
    # capability stays above its composing features (the serves springs would otherwise pull them together).
    for nid, frac in rank_y.items():
        if nid in pos:
            pos[nid][1] = _MARGIN + frac * inner_h

    return {nid: (round(p[0], 2), round(p[1], 2)) for nid, p in pos.items()}


def _labels_via_lenses(
    nodes: Sequence[Node], *, role: Optional[str], fluency: str
) -> Dict[str, str]:
    """Return {node.key: display_label} via the shared lens transform (FR-5), keyed by ``Node.key``.

    ``project_nodes`` returns a positional flat list of item-view dicts (one per node, in input order),
    so we zip by index against the same flat node list (D3). Soft dependency: if the transform is absent
    (import-guarded) or ``role`` is None, returns {} and the caller falls back to raw ``Node`` labels.
    """
    if project_nodes is None or role is None:
        return {}
    try:
        views = project_nodes(list(nodes), role=role, fluency=fluency)
    except (
        Exception
    ):  # pragma: no cover - defensive; a broken lens never breaks the render
        return {}
    out: Dict[str, str] = {}
    for node, view in zip(nodes, views):
        label = view.get("label") if isinstance(view, dict) else None
        if label:
            out[node.key] = label
    return out


def _flatten_source_nodes(nodes: Sequence[Node]) -> List[Node]:
    """Flatten the source Node tree exactly as the projection does (reuse ``_flatten``), so the lens
    label map (keyed by ``Node.key``) covers every projected source node once."""
    from .graph_projection import _flatten  # reuse the projection's flattener (D3)

    flat, _ = _flatten(nodes)
    return flat


def _edge_path(x1: float, y1: float, x2: float, y2: float) -> str:
    """A gently-curved quadratic path from (x1,y1) to (x2,y2) — a fixed perpendicular bow so parallel
    edges between the same pair are still visually separable and self-loops would arc (deterministic).
    """
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    # perpendicular offset, magnitude a fixed fraction of the edge length (no RNG)
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    off = min(40.0, length * 0.12)
    ox, oy = -dy / length * off, dx / length * off
    cx, cy = round(mx + ox, 2), round(my + oy, 2)
    return f"M{round(x1,2)},{round(y1,2)} Q{cx},{cy} {round(x2,2)},{round(y2,2)}"


def render_navigator_graph_html(
    nodes: List[Node],
    out_path: Path,
    *,
    title: str = "Node Graph",
    subtitle: str = "",
    semantic_only: bool = True,
    role: Optional[str] = None,
    fluency: str = "intermediate",
    rank_direction: Optional[str] = None,
) -> Path:
    """Render Nodes as a standalone, offline, interactive node-link **graph** (REQ-05 FR-2).

    Projects via :func:`nodes_to_graph` (FR-1), lays the graph out deterministically in Python (D1), and
    writes one self-contained HTML doc with a static ``<svg>`` (nodes + kind-distinguished edges + edge
    labels) plus a thin pan/zoom/hover-highlight JS layer. Cycle-safe (fixed-iteration layout, never a
    DAG recursion) and byte-identical across runs for the same input.

    ``semantic_only`` (default, FR-4) renders only source nodes + the semantic edges
    (``depends-on``/``serves``/``built-by``/``delivers``/``contains-child``), excluding the
    ``view:section:*`` view-marker nodes and their ``has-section``/``contains`` edges — the filter reads
    the projection-stamped ``data.view_marker`` / ``data.semantic`` fields, never a substring of the id.
    Set ``semantic_only=False`` (``--full-graph``) to include the visual-editor layout markers.

    ``role``/``fluency`` (FR-5, soft dependency) route node labels through the shared
    ``node_lenses.project_nodes`` transform when REQ-04 is present; absent it, raw ``Node`` labels are
    used and the render still succeeds. This module never re-forks the lens logic.

    Never imports ``wireframe_view`` (FR-6); no CDN / ``<script src>`` (NR-6). Returns the written path.
    """
    graph = nodes_to_graph(nodes)
    # EB-1: run the ported validator in the real render path ("wired, not just built") — a dangling or
    # duplicate edge is surfaced as a visible banner instead of drawn blind. The projection self-heals,
    # so a valid graph yields no issues and no banner → its output stays byte-identical.
    _issues = validate_graph_model(graph)
    graph_nodes: List[Dict[str, Any]] = list(graph["nodes"])
    edges: List[Dict[str, Any]] = list(graph["edges"])

    if semantic_only:
        # Exclude view-marker nodes + non-semantic edges via the STAMPED fields, not id prefixes (FR-4c).
        graph_nodes = [
            gn
            for gn in graph_nodes
            if not (gn.get("data") or {}).get("view_marker", False)
        ]
        kept_ids = {gn["id"] for gn in graph_nodes}
        edges = [
            e
            for e in edges
            if (e.get("data") or {}).get("semantic", False)
            and e.get("from") in kept_ids
            and e.get("to") in kept_ids
        ]

    # Lens labels (FR-5), keyed by Node.key over the flattened source nodes.
    lens_labels = _labels_via_lenses(
        _flatten_source_nodes(nodes), role=role, fluency=fluency
    )

    positions = _layout(graph_nodes, edges, rank_direction=rank_direction)

    # ---- draw edges (behind nodes) ------------------------------------------------
    edge_svg: List[str] = []
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a not in positions or b not in positions:
            continue
        x1, y1 = positions[a]
        x2, y2 = positions[b]
        label = str(e.get("label", ""))
        stroke, dash = _EDGE_STYLE.get(label, _DEFAULT_EDGE_STYLE)
        stroke = _safe_color(stroke) or "#6b7280"
        dash_attr = f' stroke-dasharray="{html.escape(dash)}"' if dash else ""
        path = _edge_path(x1, y1, x2, y2)
        fa, fb = html.escape(str(a)), html.escape(str(b))
        edge_svg.append(
            f'<path class="gedge" data-from="{fa}" data-to="{fb}" d="{path}" '
            f'stroke="{stroke}" stroke-width="1.6"{dash_attr} marker-end="url(#arrow)"></path>'
        )
        # edge label at the curve midpoint (escaped)
        lx = round((x1 + x2) / 2.0, 2)
        ly = round((y1 + y2) / 2.0 - 4, 2)
        edge_svg.append(
            f'<text class="gedge-label" data-from="{fa}" data-to="{fb}" x="{lx}" y="{ly}" '
            f'text-anchor="middle">{html.escape(label)}</text>'
        )

    # ---- draw nodes ---------------------------------------------------------------
    node_svg: List[str] = []
    for gn in graph_nodes:
        nid = gn.get("id")
        if nid not in positions:
            continue
        x, y = positions[nid]
        status = str(gn.get("status", "") or "")
        is_marker = bool((gn.get("data") or {}).get("view_marker", False))
        fill = _SECTION_FILL if is_marker else _STATUS_FILL.get(status, _DEFAULT_FILL)
        fill = _safe_color(fill) or _DEFAULT_FILL
        # label: lens (by source key) → projection label → id. Every path escaped.
        raw_label = lens_labels.get(str(nid)) or str(gn.get("label") or nid)
        safe_label = html.escape(raw_label)
        safe_id = html.escape(str(nid))
        does = html.escape(str(gn.get("does", "") or ""))
        tooltip = html.escape(f"{nid} — {gn.get('does','')}".strip(" —"))
        # optional href from attributes (sanitized) → wrap node in a link
        attrs = (gn.get("data") or {}).get("attributes") or {}
        href = None
        for hk in ("href", "route_url"):
            cand = _safe_href(str(attrs.get(hk, ""))) if attrs.get(hk) else None
            if cand:
                href = cand
                break
        inner = (
            f'<g class="gnode" data-id="{safe_id}" transform="translate({x} {y})">'
            f"<title>{tooltip}</title>"
            f'<circle r="{_NODE_R}" fill="{fill}"></circle>'
            f'<text x="{_NODE_R + 4}" y="4">{safe_label}</text>'
            f"</g>"
        )
        if href:
            node_svg.append(
                f'<a class="nodelink" href="{html.escape(href)}" target="_blank" '
                f'rel="noopener noreferrer">{inner}</a>'
            )
        else:
            node_svg.append(inner)
        _ = does  # does is folded into the tooltip; kept escaped above

    # ---- legend (edge kinds present) ---------------------------------------------
    present = []
    seen = set()
    for e in edges:
        lbl = str(e.get("label", ""))
        if lbl and lbl not in seen:
            seen.add(lbl)
            present.append(lbl)
    legend_parts: List[str] = []
    for kind in present:
        colour = _safe_color(_EDGE_STYLE.get(kind, _DEFAULT_EDGE_STYLE)[0]) or "#6b7280"
        legend_parts.append(
            f'<span><span class="swatch" style="border-top-color:{colour}"></span>'
            f"{html.escape(kind)}</span>"
        )
    legend_html = "".join(legend_parts)

    sub = f'<div class="sub">{html.escape(subtitle)}</div>' if subtitle else ""
    node_count = len(graph_nodes)
    edge_count = len(edges)

    # EB-1 banner: empty (byte-identical) for a valid graph; visible + escaped when issues exist.
    warn_html = ""
    if _issues:
        _items = "".join(f"<li>{html.escape(str(i))}</li>" for i in _issues)
        warn_html = (
            '<div class="graph-warn" role="alert" style="margin:8px 12px;padding:8px 12px;'
            'border:1px solid #b91c1c;background:#fef2f2;color:#7f1d1d;border-radius:6px">'
            f"⚠ graph model has {len(_issues)} integrity issue(s):<ul>{_items}</ul></div>"
        )

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_GRAPH_CSS}</style></head>
<body>
<header>
  <h1>{html.escape(title)}</h1>{sub}
  <div class="controls">
    <button id="reset">Reset view</button>
    <span class="sub">{node_count} nodes · {edge_count} edges · drag to pan · scroll to zoom · hover to highlight</span>
    <div class="legend">{legend_html}</div>
  </div>
</header>{warn_html}
<div id="stage">
<svg viewBox="0 0 {_W} {_H}" preserveAspectRatio="xMidYMid meet">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
      orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#6b7280"></path></marker>
  </defs>
  <g id="viewport">
    <g class="edges">{''.join(edge_svg)}</g>
    <g class="nodes">{''.join(node_svg)}</g>
  </g>
</svg>
</div>
<script>{_GRAPH_JS}</script>
</body></html>"""

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
