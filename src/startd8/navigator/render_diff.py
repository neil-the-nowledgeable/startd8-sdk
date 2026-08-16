"""Standalone diff renderer — a self-contained offline delta view over a :class:`NodeDiff` (REQ-07).

Mirrors ``render_graph.py``'s standalone discipline: its **own** ``<!doctype>`` shell with inlined
``_DIFF_CSS`` / ``_DIFF_JS`` (no CDN, no ``<script src>``), and it **NEVER** imports ``wireframe_view``
so the deterministic app-scaffold path stays byte-identical (FR-2 / FR-9). XSS is handled by
``html.escape`` on every authored string plus the reused ``render_tree`` helpers ``_safe_href`` /
``_safe_color`` (imported, never re-copied — Kagami) for hrefs / colours.

A11y (FR-3): each delta class carries colour **+ glyph + word** — added = green ``+ added``,
removed = red ``− removed``, changed = amber ``~ changed`` — so it survives greyscale/colour-blindness.

Lens inheritance (FR-6): labels for the union of before+after keys flow through the shared REQ-04
``wireframe_view.node_lenses.project_nodes`` transform behind a soft-import guard (as ``render_graph``
does) — no lens logic is re-forked here. ``role=None`` → raw labels → byte-identical.

Altitude (FR-7): a header roll-up (``+N / −M / ~K``) always renders (from ``NodeDiff.rollup``), changed
rows are in a collapse-by-default ``<details>``, and ``--max-detail N`` degrades the Changed section to
counts-only with a "diff too large — showing summary" banner past the threshold.

Determinism (FR-10): key-sorted buckets, fixed field order, no RNG → byte-identical HTML across runs.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .diff import FieldDelta, NodeDiff
from .models import Node, NodeEvidence
from .render_tree import _safe_href  # reuse — do not re-copy (Kagami)

# FR-6 soft dependency: the shared lens transform (REQ-04). Absent it, fall back to raw labels and
# still render. project_nodes returns a positional flat list of item-view dicts (one per node, in
# input order) — key it by Node.key over the union of before+after nodes.
try:  # pragma: no cover - exercised by the import-guard test via monkeypatch
    from ..wireframe_view.node_lenses import project_nodes
except ImportError:  # pragma: no cover
    project_nodes = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# A11y-safe delta-class palette (colour + glyph + word — never colour alone, FR-3)
# ---------------------------------------------------------------------------
_CLASS_STYLE: Dict[str, Dict[str, str]] = {
    "added": {"color": "#3fb950", "glyph": "+", "word": "added"},
    "removed": {"color": "#f85149", "glyph": "−", "word": "removed"},  # − minus sign
    "changed": {"color": "#d29922", "glyph": "~", "word": "changed"},
}

_DIFF_CSS = """
:root{--bg:#0f1115;--card:#171a21;--edge:#262b36;--fg:#e6e9ef;--mut:#9aa4b2;
--added:#3fb950;--removed:#f85149;--changed:#d29922;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
header{position:sticky;top:0;z-index:5;background:var(--bg);
border-bottom:1px solid var(--edge);padding:14px 20px;}
h1{margin:0;font-size:17px;font-weight:650}
.sub{color:var(--mut);font-size:12.5px;margin-top:3px}
main{padding:16px 20px;max-width:1100px}
h2{font-size:14.5px;margin:22px 0 8px;border-bottom:1px solid var(--edge);padding-bottom:5px}
.rollup{margin-top:10px;display:flex;gap:14px;flex-wrap:wrap;align-items:center;font-size:13px}
.count{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--edge);
border-radius:7px;padding:4px 10px;background:var(--card);font-variant-numeric:tabular-nums}
.glyph{font-weight:700;font-family:ui-monospace,Menlo,monospace}
.c-added{color:var(--added)} .c-removed{color:var(--removed)} .c-changed{color:var(--changed)}
.banner{margin:10px 0;padding:9px 12px;border:1px solid var(--changed);
background:#1c1710;color:var(--changed);border-radius:7px;font-size:13px}
ul.rows{list-style:none;margin:0;padding:0}
li.row{border:1px solid var(--edge);border-radius:8px;background:var(--card);
padding:9px 12px;margin:7px 0}
.tag{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:650;
border-radius:6px;padding:2px 8px;margin-right:8px;font-family:ui-monospace,Menlo,monospace}
.tag-added{color:var(--added);border:1px solid var(--added)}
.tag-removed{color:var(--removed);border:1px solid var(--removed)}
.tag-changed{color:var(--changed);border:1px solid var(--changed)}
.key{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
.does{color:var(--mut);margin-left:4px}
details{margin:7px 0}
summary{cursor:pointer;color:var(--fg)}
table.fields{border-collapse:collapse;margin:8px 0 2px;width:100%;font-size:12.5px}
table.fields th,table.fields td{border:1px solid var(--edge);padding:4px 8px;
vertical-align:top;text-align:left}
table.fields th{color:var(--mut);font-weight:600;width:12%}
td.before{color:var(--removed)} td.after{color:var(--added)}
.trans{font-family:ui-monospace,Menlo,monospace}
.trans .from{color:var(--mut)} .trans .arrow{color:var(--fg);margin:0 6px}
.trans .to{color:var(--added)}
.dangling{color:var(--removed);font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.empty{color:var(--mut);font-style:italic}
a{color:#58a6ff}
"""

# Expand/collapse-all only (no editing, no network). The <details> already collapse by default.
_DIFF_JS = """
(function(){
  function setAll(open){
    [].forEach.call(document.querySelectorAll('details.changed-row'),function(d){d.open=open;});
  }
  var e=document.getElementById('expand-all'); if(e)e.onclick=function(){setAll(true);};
  var c=document.getElementById('collapse-all'); if(c)c.onclick=function(){setAll(false);};
})();
"""


# ---------------------------------------------------------------------------
# Lens labels (FR-6) — keyed by Node.key over the union of before+after nodes
# ---------------------------------------------------------------------------
def _labels_via_lenses(
    nodes: Sequence[Node], *, role: Optional[str], fluency: str
) -> Dict[str, str]:
    """Return ``{node.key: display_label}`` via the shared REQ-04 lens transform, keyed by ``Node.key``.

    ``project_nodes`` returns a positional item-view list (one per node, input order), zipped by index
    against the same flat node list. Soft dependency: absent the transform (import-guarded) or with
    ``role`` None, returns ``{}`` and the caller falls back to raw labels (byte-identical)."""
    if project_nodes is None or role is None:
        return {}
    try:
        views = project_nodes(list(nodes), role=role, fluency=fluency)
    except Exception:  # pragma: no cover - a broken lens never breaks the render
        return {}
    out: Dict[str, str] = {}
    for node, view in zip(nodes, views):
        label = view.get("label") if isinstance(view, dict) else None
        if label:
            out[node.key] = label
    return out


def _union_nodes(diff: NodeDiff) -> List[Node]:
    """The union of before+after Node objects the diff carries (added + removed + both sides of each
    changed pair), de-duplicated by key with the *after* side winning — enough for a label map."""
    seen: Dict[str, Node] = {}
    for _k, b, a, _d in diff.changed:
        seen.setdefault(b.key, b)
        seen[a.key] = a  # after wins
    for n in diff.removed:
        seen.setdefault(n.key, n)
    for n in diff.added:
        seen[n.key] = n
    return list(seen.values())


# ---------------------------------------------------------------------------
# Field-value rendering (escaped)
# ---------------------------------------------------------------------------
def _fmt_field_value(field_name: str, value: Any) -> str:
    """Escaped, human-readable rendering of a raw field value for a changed-row cell.

    Every authored string is ``html.escape``-d; a ``lives`` link ref is routed through ``_safe_href``
    (a ``javascript:`` ref is neutralized). No colour sink from source."""
    if field_name == "lives":
        parts: List[str] = []
        for ev in value or ():
            if isinstance(ev, NodeEvidence):
                safe = _safe_href(ev.ref) if ev.type == "link" else None
                ref_html = (
                    f'<a href="{html.escape(safe)}" rel="noopener noreferrer">{html.escape(ev.ref)}</a>'
                    if safe
                    else html.escape(ev.ref)
                )
                parts.append(f"{html.escape(ev.type)}:{ref_html}")
        return ", ".join(parts) if parts else '<span class="empty">(none)</span>'
    if field_name == "children":
        keys = sorted(c.key for c in (value or ()))
        return html.escape(", ".join(keys)) if keys else '<span class="empty">(none)</span>'
    if field_name == "status_facets":
        parts = [
            html.escape(f"{f.name}={f.value}")
            for f in (value or ())
        ]
        return ", ".join(parts) if parts else '<span class="empty">(none)</span>'
    if field_name == "attributes":
        items = sorted((str(k), str(v)) for k, v in (value or {}).items())
        return (
            html.escape(", ".join(f"{k}={v}" for k, v in items))
            if items
            else '<span class="empty">(none)</span>'
        )
    if isinstance(value, (tuple, list)):
        return (
            html.escape(", ".join(str(x) for x in value))
            if value
            else '<span class="empty">(none)</span>'
        )
    text = str(value) if value is not None else ""
    return html.escape(text) if text else '<span class="empty">(empty)</span>'


def _tag(cls: str) -> str:
    """A11y delta tag — colour + glyph + word (FR-3), decodable in greyscale."""
    s = _CLASS_STYLE[cls]
    return (
        f'<span class="tag tag-{cls}">'
        f'<span class="glyph">{html.escape(s["glyph"])}</span> {html.escape(s["word"])}</span>'
    )


def _node_line(node: Node, lens_labels: Dict[str, str]) -> str:
    """A ``key — does`` line, lens-labelled when available, always escaped."""
    label = lens_labels.get(node.key)
    if label:
        return f'<span class="key">{html.escape(label)}</span>'
    does = (node.does or "").strip()
    does_html = f'<span class="does">— {html.escape(does)}</span>' if does else ""
    return f'<span class="key">{html.escape(node.key)}</span> {does_html}'


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------
def _render_added_removed(cls: str, nodes: Sequence[Node], lens_labels: Dict[str, str]) -> str:
    if not nodes:
        return f'<p class="empty">no {cls} nodes.</p>'
    rows = [
        f'<li class="row">{_tag(cls)}{_node_line(n, lens_labels)}</li>'
        for n in nodes  # already key-sorted by the engine
    ]
    return '<ul class="rows">' + "".join(rows) + "</ul>"


def _render_changed_row(
    key: str, after: Node, deltas: Sequence[FieldDelta], lens_labels: Dict[str, str]
) -> str:
    field_rows = []
    for d in deltas:  # fixed field order from the engine
        field_rows.append(
            "<tr>"
            f"<th>{html.escape(d.field)}</th>"
            f'<td class="before">{_fmt_field_value(d.field, d.before)}</td>'
            f'<td class="after">{_fmt_field_value(d.field, d.after)}</td>'
            "</tr>"
        )
    table = (
        '<table class="fields"><tr><th>field</th><th>before</th><th>after</th></tr>'
        + "".join(field_rows)
        + "</table>"
    )
    return (
        '<li class="row">'
        '<details class="changed-row">'
        f"<summary>{_tag('changed')}{_node_line(after, lens_labels)}"
        f" <span class=\"does\">({len(deltas)} field(s))</span></summary>"
        f"{table}"
        "</details>"
        "</li>"
    )


def _render_transitions(diff: NodeDiff) -> str:
    if not diff.status_transitions:
        return ""
    rows = []
    for t in diff.status_transitions:
        rows.append(
            '<li class="row"><span class="trans">'
            f'<span class="key">{html.escape(t.key)}</span>: '
            f'<span class="from">{html.escape(t.before)}</span>'
            '<span class="arrow">→</span>'
            f'<span class="to">{html.escape(t.after)}</span>'
            "</span></li>"
        )
    return (
        '<h2>Status transitions</h2><ul class="rows">' + "".join(rows) + "</ul>"
    )


def _render_dangling(diff: NodeDiff) -> str:
    if not diff.new_dangling_refs:
        return ""
    rows = []
    for r in diff.new_dangling_refs:
        rows.append(
            '<li class="row"><span class="dangling">'
            f'⚠ <span class="key">{html.escape(r.key)}</span> '
            f"new dangling {html.escape(r.ref_type)} ref: {html.escape(r.ref)}"
            "</span></li>"
        )
    return (
        '<h2>New dangling refs</h2>'
        '<p class="sub">A <span class="dangling">lives</span> ref present in <em>after</em> '
        'that no longer resolves on the local filesystem (and was not already dangling before).</p>'
        '<ul class="rows">' + "".join(rows) + "</ul>"
    )


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------
def render_navigator_diff_html(
    diff: NodeDiff,
    out_path: Path,
    *,
    title: str = "Node Corpus Delta",
    subtitle: str = "",
    max_detail: Optional[int] = None,
    role: Optional[str] = None,
    fluency: str = "intermediate",
) -> Path:
    """Render a :class:`NodeDiff` as a standalone, offline, self-contained delta view (REQ-07 FR-2).

    Writes one HTML doc with its own shell (inlined CSS+JS, no CDN) laying the delta out as a header
    roll-up (``+N / −M / ~K``, always) plus Added / Removed / Changed sections, a status-transition
    summary, and a new-dangling-refs list. Changed rows are collapse-by-default ``<details>``; past
    ``max_detail`` changed keys the Changed section degrades to counts-only with a banner (FR-7).

    ``role`` / ``fluency`` (FR-6, soft dependency) route the node labels through the shared REQ-04
    lens transform when present; absent it (or ``role=None``), raw labels are used and the render is
    byte-identical. Never imports ``wireframe_view`` (FR-2/FR-9); no CDN / ``<script src>``. Returns
    the written path. Deterministic: same ``diff`` → byte-identical bytes (FR-10).
    """
    lens_labels = _labels_via_lenses(_union_nodes(diff), role=role, fluency=fluency)

    rollup = diff.rollup
    s_add, s_rem, s_chg = _CLASS_STYLE["added"], _CLASS_STYLE["removed"], _CLASS_STYLE["changed"]
    rollup_html = (
        '<div class="rollup">'
        f'<span class="count c-added"><span class="glyph">{html.escape(s_add["glyph"])}'
        f'</span>{rollup["added"]} {html.escape(s_add["word"])}</span>'
        f'<span class="count c-removed"><span class="glyph">{html.escape(s_rem["glyph"])}'
        f'</span>{rollup["removed"]} {html.escape(s_rem["word"])}</span>'
        f'<span class="count c-changed"><span class="glyph">{html.escape(s_chg["glyph"])}'
        f'</span>{rollup["changed"]} {html.escape(s_chg["word"])}</span>'
        f'<span class="count">{rollup["unchanged"]} unchanged</span>'
        "</div>"
    )

    added_html = _render_added_removed("added", diff.added, lens_labels)
    removed_html = _render_added_removed("removed", diff.removed, lens_labels)

    # FR-7 altitude cap on the Changed section
    n_changed = len(diff.changed)
    over_cap = max_detail is not None and n_changed > max_detail
    if over_cap:
        changed_body = (
            f'<div class="banner">diff too large — showing summary '
            f"(~{n_changed} changed keys exceeds --max-detail {max_detail}). "
            f"Changed keys (counts-only):</div>"
            '<ul class="rows">'
            + "".join(
                f'<li class="row">{_tag("changed")}'
                f'<span class="key">{html.escape(key)}</span>'
                f' <span class="does">({len(deltas)} field(s))</span></li>'
                for (key, _b, _a, deltas) in diff.changed
            )
            + "</ul>"
        )
        controls = ""
    elif n_changed == 0:
        changed_body = '<p class="empty">no changed nodes.</p>'
        controls = ""
    else:
        changed_body = '<ul class="rows">' + "".join(
            _render_changed_row(key, a, deltas, lens_labels)
            for (key, _b, a, deltas) in diff.changed
        ) + "</ul>"
        controls = (
            '<div class="rollup">'
            '<button id="expand-all">Expand all</button>'
            '<button id="collapse-all">Collapse all</button></div>'
        )

    transitions_html = _render_transitions(diff)
    dangling_html = _render_dangling(diff)

    sub = f'<div class="sub">{html.escape(subtitle)}</div>' if subtitle else ""

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_DIFF_CSS}</style></head>
<body>
<header>
  <h1>{html.escape(title)}</h1>{sub}
  {rollup_html}
</header>
<main>
{transitions_html}
{dangling_html}
<h2>Added</h2>
{added_html}
<h2>Removed</h2>
{removed_html}
<h2>Changed</h2>
{controls}
{changed_body}
</main>
<script>{_DIFF_JS}</script>
</body></html>"""

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path


__all__ = ["render_navigator_diff_html"]
