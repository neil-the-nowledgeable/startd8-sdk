"""N-level tree renderer — nested, searchable, self-contained HTML drill-down over Node.children.

Port of the ContextCore navigator tree renderer (`navigator/render.py`, the LIVE pair — CC had a
shadowed duplicate; only the live copy is ported here). Standalone by design: it imports **only**
`.models` (never `wireframe_view`/`WireframePlan`), so it is a distinct presentation surface and the
app-scaffold wireframe path is untouched (REQ-02 FR-5). XSS mitigations from CC #398/#400 are carried
(`_safe_href` / `_safe_color`; evidence/attr text is escaped).

REQ-02 FR-1. The whole document (CSS + JS) is inlined so the file opens offline.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .models import Node, NodeEvidence, NodeStatus

_DEFAULT_LEGEND = {
    NodeStatus.BUILT: "built / ok",
    NodeStatus.THIN: "thin / moderate",
    NodeStatus.SPEC: "spec / info",
    NodeStatus.DEPRECATED: "deprecated / critical",
}


def _search_blob(node: Node) -> str:
    """The lowercased text a node is matched against by the search box."""
    parts = [node.key, node.does, node.category, node.orientation, node.route_state]
    parts.extend(node.triggers)
    parts.extend(node.child_keys)
    parts.extend(node.attributes.values())
    parts.extend(ev.ref for ev in node.lives)
    return " ".join(p for p in parts if p).lower()


_HREF_ATTR_KEYS = {"href", "route_url"}  # attributes rendered as a real <a> (#400)
_SAFE_URL_SCHEMES = {"", "http", "https", "mailto"}  # "" = relative/anchor path (no scheme)
_SAFE_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([\d\s.,%]+\)|[a-zA-Z]{1,20})$")


def _safe_href(url: str) -> Optional[str]:
    """Return *url* iff it uses a safe scheme (http/https/mailto) or is relative/anchor — else None.

    Blocks javascript:/data:/vbscript: so a projected href can't become a clickable XSS vector."""
    u = (url or "").strip()
    if not u:
        return None
    try:
        scheme = urlsplit(u).scheme.lower()
    except ValueError:
        return None
    return u if scheme in _SAFE_URL_SCHEMES else None


def _safe_color(color: str) -> str:
    """Return *color* iff it matches a safe CSS-colour pattern, else "" — so a source-declared facet
    colour injected into an inline style can't carry extra ;-separated declarations."""
    c = (color or "").strip()
    return c if _SAFE_COLOR_RE.match(c) else ""


def _facets_html(node: Node) -> str:
    """Render the status facets as chips — each with its own source-declared glyph + safe colour."""
    if not node.status_facets:
        return ""
    chips: List[str] = []
    for f in node.status_facets:
        g = (html.escape(f.glyph) + " ") if f.glyph else ""
        _c = _safe_color(f.color)
        style = f' style="color:{_c}"' if _c else ""
        chips.append(
            f'<span class="facet"{style} title="{html.escape(f.name)}">{g}{html.escape(f.value)}</span>'
        )
    return '<span class="facets">' + "".join(chips) + "</span>"


def _live_row_html(ev: NodeEvidence) -> str:
    """One evidence row. A ``type == "link"`` ref renders as a real <a> (#400); else inert <code>."""
    t = html.escape(ev.type or "ref")
    note = f" — {html.escape(ev.note)}" if ev.note else ""
    _safe = _safe_href(ev.ref) if ev.type == "link" else None
    if _safe is not None:
        ref = f'<a class="href" href="{html.escape(_safe, quote=True)}">{html.escape(ev.ref)}</a>'
    else:
        ref = f"<code>{html.escape(ev.ref)}</code>"
    return f'<li><span class="etype">{t}</span> {ref}{note}</li>'


def _attr_row_html(k: str, v: str) -> str:
    """One attribute row. A designated href key (#400) renders its value as a real <a>."""
    _safe = _safe_href(v) if k in _HREF_ATTR_KEYS else None
    if _safe is not None:
        cell = f'<a class="href" href="{html.escape(_safe, quote=True)}">{html.escape(v)}</a>'
    else:
        cell = html.escape(v)
    return f"<tr><th>{html.escape(k)}</th><td>{cell}</td></tr>"


def _tree_body_html(node: Node) -> str:
    """The expanded card body: prose, meta, evidence, attributes, cross-refs."""
    out: List[str] = []
    is_intro = node.attributes.get("kind") == "intro"

    prose = node.attributes.get("description") or node.attributes.get("mechanism")
    if is_intro:
        if prose:
            out.append(f'<div class="intro-banner">{html.escape(prose.strip())}</div>')
        readiness = node.attributes.get("readiness")
        if readiness:
            out.append(f'<div class="readiness-chip">{html.escape(readiness)}</div>')
    elif prose and prose.strip() != node.does.strip():
        out.append(f'<p class="prose">{html.escape(prose.strip())}</p>')

    meta: List[str] = []
    if node.wont:
        meta.append("<b>Won't:</b> " + html.escape("; ".join(node.wont)))
    if node.ships_when:
        meta.append("<b>Ships when:</b> " + html.escape(node.ships_when))
    axis_bits = [b for b in (node.orientation, node.route_state) if b]
    if axis_bits:
        meta.append("<b>Axes:</b> " + html.escape(" · ".join(axis_bits)))
    if node.confidence is not None:
        meta.append(f"<b>Confidence:</b> {node.confidence:.2f}")
    if meta:
        out.append('<div class="meta">' + " &nbsp;·&nbsp; ".join(meta) + "</div>")

    if node.lives:
        rows = "".join(_live_row_html(ev) for ev in node.lives)
        out.append(f'<div class="evidence"><h4>Authority / evidence</h4><ul>{rows}</ul></div>')

    shown = {"description", "mechanism", "kind", "readiness"}
    attrs = [(k, v) for k, v in node.attributes.items() if k not in shown and v]
    if attrs:
        rows = "".join(_attr_row_html(k, v) for k, v in attrs)
        out.append(f'<table class="attrs">{rows}</table>')

    if node.child_keys:
        chips = "".join(f'<span class="chip">{html.escape(k)}</span>' for k in node.child_keys)
        out.append(f'<div class="xref"><h4>Cross-references</h4>{chips}</div>')

    return "".join(out)


def _tree_node_html(node: Node, depth: int, open_depth: int) -> str:
    """One node → nested <details> (recurses node.children); a childless bodyless node is a flat row."""
    blob = html.escape(_search_blob(node), quote=True)
    glyph = html.escape(node.glyph)
    key = html.escape(node.key)
    does = html.escape(node.does)
    status = html.escape(node.status)
    facets = _facets_html(node)
    summary = (
        f'<summary><span class="glyph">{glyph}</span>'
        f'<span class="key">{key}</span>'
        f'<span class="does">{does}</span>{facets}</summary>'
    )
    body = _tree_body_html(node)
    children_html = "".join(_tree_node_html(c, depth + 1, open_depth) for c in node.children)

    if not body and not children_html:
        return (
            f'<div class="node leaf s-{status}" data-search="{blob}">'
            f'<span class="glyph">{glyph}</span>'
            f'<span class="key">{key}</span>'
            f'<span class="does">{does}</span>{facets}</div>'
        )

    open_attr = " open" if depth < open_depth else ""
    intro_cls = " intro" if node.attributes.get("kind") == "intro" else ""
    inner = f'<div class="body">{body}{children_html}</div>'
    return (
        f'<details class="node s-{status}{intro_cls}" data-search="{blob}"{open_attr}>'
        f"{summary}{inner}</details>"
    )


def _count_nodes(nodes: List[Node]) -> int:
    return sum(1 + _count_nodes(list(n.children)) for n in nodes)


_TREE_CSS = """
:root{--bg:#0f1115;--card:#171a21;--edge:#262b36;--fg:#e6e9ef;--mut:#9aa4b2;
--ok:#3fb950;--thin:#d29922;--spec:#58a6ff;--crit:#f85149;--chip:#21262d;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
header{position:sticky;top:0;z-index:5;background:var(--bg);
border-bottom:1px solid var(--edge);padding:14px 20px;}
h1{margin:0;font-size:17px;font-weight:650}
.sub{color:var(--mut);font-size:12.5px;margin-top:3px}
.controls{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
#q{flex:1;min-width:220px;background:var(--card);border:1px solid var(--edge);
color:var(--fg);border-radius:7px;padding:7px 11px;font-size:13px}
button{background:var(--card);border:1px solid var(--edge);color:var(--fg);
border-radius:7px;padding:7px 11px;font-size:12.5px;cursor:pointer}
button:hover{border-color:#3a4150}
.legend{color:var(--mut);font-size:12px;margin-left:auto;display:flex;gap:12px;flex-wrap:wrap}
main{padding:14px 20px 60px;max-width:1080px;margin:0 auto}
.node{margin:4px 0}
details.node{border:1px solid var(--edge);border-radius:8px;background:var(--card);
margin:5px 0;overflow:hidden}
details.node>summary{list-style:none;cursor:pointer;padding:9px 12px;display:flex;
gap:9px;align-items:baseline;border-left:3px solid transparent}
details.node>summary::-webkit-details-marker{display:none}
summary:hover{background:#1c2029}
.glyph{flex:none}
.key{font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.does{color:var(--fg)}
.facets{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
.facet{font-size:11px;padding:1px 7px;border:1px solid var(--edge);border-radius:10px;background:var(--chip);white-space:nowrap}
a.href{color:var(--spec);text-decoration:none;border-bottom:1px dotted var(--spec)}
a.href:hover{text-decoration:underline}
.leaf{display:flex;gap:9px;align-items:baseline;padding:6px 12px;
border-left:3px solid transparent;color:var(--mut)}
.leaf .does{color:var(--mut)}
.body{padding:2px 12px 10px 26px}
.prose{margin:8px 0;color:#cbd3df}
.meta{color:var(--mut);font-size:12.5px;margin:6px 0}
.evidence,.xref{margin:9px 0}
h4{margin:8px 0 4px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut)}
.evidence ul{margin:0;padding-left:16px}
.evidence li{margin:2px 0}
.etype{display:inline-block;font-size:10.5px;text-transform:uppercase;color:var(--mut);
border:1px solid var(--edge);border-radius:4px;padding:0 5px;margin-right:4px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#e6e9ef}
table.attrs{border-collapse:collapse;margin:8px 0;font-size:12.5px}
table.attrs th{text-align:left;color:var(--mut);padding:2px 14px 2px 0;font-weight:500;
vertical-align:top;white-space:nowrap}
table.attrs td{padding:2px 0}
.chip{display:inline-block;background:var(--chip);border:1px solid var(--edge);
border-radius:12px;padding:1px 9px;margin:2px 4px 2px 0;font-size:12px;
font-family:ui-monospace,Menlo,monospace}
.s-built>summary,.leaf.s-built{border-left-color:var(--ok)}
.s-thin>summary,.leaf.s-thin{border-left-color:var(--thin)}
.s-spec>summary,.leaf.s-spec{border-left-color:var(--spec)}
.s-deprecated>summary,.leaf.s-deprecated{border-left-color:var(--crit)}
.readiness-band{margin-top:10px;padding:8px 12px;background:var(--card);border:1px solid var(--edge);
border-radius:7px;font-size:12.5px;color:#cbd3df}
.intro-banner{margin:8px 0;padding:10px 12px;background:#12161d;border:1px solid var(--edge);
border-left:3px solid var(--spec);border-radius:7px;color:#cbd3df;line-height:1.55}
.readiness-chip{display:inline-block;margin:2px 0 4px;padding:3px 10px;background:var(--chip);
border:1px solid var(--edge);border-radius:12px;font-size:12px;color:#cbd3df}
details.node.intro>summary{border-left-color:var(--spec)}
"""

_TREE_JS = """
const q=document.getElementById('q');
function applyFilter(){
  const term=q.value.trim().toLowerCase();
  const nodes=[...document.querySelectorAll('.node')];
  for(let i=nodes.length-1;i>=0;i--){
    const n=nodes[i];
    const own=(n.getAttribute('data-search')||'').includes(term);
    const kid=!!n.querySelector('.node[data-visible="1"]');
    const vis = term==='' || own || kid;
    n.setAttribute('data-visible', vis?'1':'0');
    n.style.display = vis?'':'none';
    if(term!=='' && (own||kid) && n.tagName==='DETAILS') n.open=true;
  }
}
q.addEventListener('input',applyFilter);
function toggleAll(open){document.querySelectorAll('details.node').forEach(d=>d.open=open);}
document.getElementById('expand').onclick=()=>toggleAll(true);
document.getElementById('collapse').onclick=()=>toggleAll(false);
"""


def render_navigator_tree_html(
    nodes: List[Node],
    out_path: Path,
    *,
    title: str = "Node Navigator",
    subtitle: str = "",
    open_depth: int = 2,
    status_legend: Optional[Dict[str, str]] = None,
    readiness: Optional[Any] = None,
) -> Path:
    """Render nodes as a nested, searchable, self-contained HTML tree (N-level drill over children).

    Dependency-free (inlined CSS+JS, opens offline). ``open_depth`` controls how many levels start
    expanded. ``readiness`` (dict with ``label``/``overall.label``, or a string) renders a header band;
    if omitted it falls back to the first root's ``attributes["readiness"]``. Returns the written path."""
    legend = dict(_DEFAULT_LEGEND)
    if status_legend:
        legend.update(status_legend)

    band_label: Optional[str] = None
    if isinstance(readiness, dict):
        band_label = readiness.get("label") or (readiness.get("overall") or {}).get("label")
    elif isinstance(readiness, str):
        band_label = readiness
    if not band_label and nodes:
        band_label = nodes[0].attributes.get("readiness")
    band_html = (
        f'<div class="readiness-band">{html.escape(band_label)}</div>' if band_label else ""
    )

    legend_html = "".join(
        f'<span>{NodeStatus.GLYPH.get(s, "•")} {html.escape(lbl)}</span>'
        for s, lbl in legend.items()
    )

    total = _count_nodes(nodes)
    body = "".join(_tree_node_html(n, 0, open_depth) for n in nodes)
    sub = f'<div class="sub">{html.escape(subtitle)}</div>' if subtitle else ""

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_TREE_CSS}</style></head>
<body>
<header>
  <h1>{html.escape(title)}</h1>{sub}
  <div class="controls">
    <input id="q" type="search" placeholder="Search {total} nodes — key, text, citation, tag…" autocomplete="off">
    <button id="expand">Expand all</button>
    <button id="collapse">Collapse all</button>
    <div class="legend">{legend_html}</div>
  </div>
  {band_html}
</header>
<main>{body}</main>
<script>{_TREE_JS}</script>
</body></html>"""

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path
