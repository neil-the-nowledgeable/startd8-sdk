"""Semantic, screen-reader-first requirements renderer — standalone (REQ-03 FR-1/FR-4/FR-6).

Port of the ContextCore navigator a11y renderer (`navigator/render_a11y.py`, the LIVE symbols only).
Reads the canonical NODE-SCHEMA `Node` model (via `.sources_requirements.nodes_from_requirements`) and
renders a requirement doc two ways — a dense speakable TEXT view and a semantic, screen-reader-native
HTML file (landmarks, ordered headings, keyboard-reachable disclosures, status-by-text+glyph never
colour-alone). Its own HTML shell: it imports **only** `.models` + `.render_tree` (the shared XSS
helpers) and NEVER `wireframe_view`/`wireframe`, so the app-scaffold path is untouched (REQ-03 FR-5)
and no wireframe summary-chrome can bleed in.

NR-3: the base `ReqView` + a11y view only — the Tier-2/3 lesson·principle validation cockpit
(CC `validate`/`recall_lessons`/`flag_principles`) and the feature-health overlay are deliberately
NOT ported. XSS mitigations (CC #398/#400) reuse REQ-02's already-tested `_safe_href`/`_safe_color`.
The whole document (CSS inlined, no JS required to read it) opens offline.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .models import Node
# Decision-1 (locked): reuse REQ-02's already-tested XSS helper. Every href goes through
# `_safe_href`. This renderer has NO user-controlled colour sink (all colours come from the fixed
# CSS palette, not from source), so `_safe_color` is not needed here — the index reuses `_safe_href`
# for the same reason. `esc`/`html.escape` handle all text escaping.
from .render_tree import _safe_href

# REQ-09 FR-2/FR-3: opt-in adoption of the shared audience×fluency lens transform — the same seam the
# tree + graph renderers use. Soft-import guarded exactly like render_graph/render_tree: if REQ-04 is
# absent (or role=None) the a11y view renders raw ``Node`` labels and stays byte-identical. The a11y
# renderer uses the same DIRECT ``apply_node_lenses`` bridge as the tree (FR-3), substituting only the
# ``does`` portion of its own ``{key} — {does}`` layout. It must NOT pull WireframePlan / compose / view.
try:  # pragma: no cover - exercised by the import-guard test via monkeypatch
    from ..wireframe_view.node_lenses import apply_node_lenses
except ImportError:  # pragma: no cover - REQ-04 absent → raw labels, byte-identical
    apply_node_lenses = None  # type: ignore[assignment]

try:  # pragma: no cover
    from ..wireframe.delivery_roles import effective_voice
except ImportError:  # pragma: no cover
    effective_voice = None  # type: ignore[assignment]

# The REQUIREMENTS status vocabulary (from sources_requirements.REQUIREMENTS_PROFILE),
# NOT the build vocabulary (built/spec/deprecated). status_key -> speakable label.
STATUS_LABEL = {
    "goal": "goal",
    "grounded": "grounded",
    "spec": "spec",
    "awaiting": "awaiting",
    "action": "do-next",
    "risk-high": "risk-high",
    "risk-med": "risk-med",
    "risk-low": "risk-low",
    "excluded": "excluded",
    "needs-human": "needs-you",
    "unknown": "unknown",
}


def esc(s: str) -> str:
    return html.escape(s or "")


# --- Node selection by kind (the source tags node.attributes["kind"]) ---------
def by_kind(nodes: List[Node], kind: str) -> List[Node]:
    return [n for n in nodes if n.attributes.get("kind") == kind]


def attr(n: Node, key: str, default: str = "") -> str:
    if n is None:
        return default
    return n.attributes.get(key, default)


def does(n: Node) -> str:
    """node.does, minus a dangling ' —' the OUTCOME-BRIEF ' — target:' split leaves."""
    return (n.does if n else "").rstrip(" —").rstrip()


def _lens_labels(
    nodes: Sequence[Node], *, role: Optional[str], fluency: str
) -> Dict[str, str]:
    """Return ``{node.key: humanised_does}`` via a DIRECT ``apply_node_lenses`` call (FR-2/FR-3).

    Mirrors the tree renderer's bridge: builds a flat item-view list ``[{"label": node.does, ...}]``,
    hands it to the shared aggregate, and keys the lensed ``label`` back to ``Node.key`` positionally.
    Label = ``node.does`` (not ``"{key} — {does}"``) so the humanised text substitutes ONLY the ``does``
    portion of the a11y renderer's own ``{key} — {does}`` layout. Soft dependency: transform absent or
    ``role`` None → ``{}`` → the caller falls back to raw ``does(node)`` → byte-identical (FR-5)."""
    if apply_node_lenses is None or role is None:
        return {}
    voice = effective_voice(role) if effective_voice is not None else role
    views = [
        {
            "label": n.does,
            "status": n.status,
            "detail": n.does,
            "route_state": getattr(n, "route_state", "") or "",
        }
        for n in nodes
    ]
    try:
        lensed = apply_node_lenses(views, role=role, fluency=fluency, voice=voice)
    except Exception:  # pragma: no cover - defensive; a broken lens never breaks the render
        return {}
    out: Dict[str, str] = {}
    for n, view in zip(nodes, lensed):
        label = view.get("label") if isinstance(view, dict) else None
        if label is not None:
            out[n.key] = label
    return out


def _lensed(n: Node, labels: Optional[Dict[str, str]]) -> Optional[str]:
    """The humanised label for ``n`` when ``labels`` (the lens map) carries its key, else ``None``.

    Returns ``None`` when there is no lens override so each call site keeps its OWN original fallback
    expression verbatim (``does(o)`` vs raw ``f.does``) — the guarantee that ``role=None`` (empty map)
    is byte-identical to the pre-REQ-09 render (FR-5)."""
    if not labels or n is None:
        return None
    return labels.get(n.key)


def status_label(n: Node) -> str:
    return STATUS_LABEL.get(attr(n, "status_key"), attr(n, "status_key") or "—")


def _evidence_lines(f: Node) -> List[str]:
    """EVIDENCE-1 leaf: locate + flag unknown when a done-claim lacks strong evidence."""
    lines: List[str] = []
    if attr(f, "fr_health") == "unknown":
        ann = attr(f, "verify") or "done"
        lines.append(f"evidence: UNKNOWN — verify ({ann}); done-claim without Lives locator")
        return lines
    lives = getattr(f, "lives", ()) or ()
    authored = [ev for ev in lives if getattr(ev, "note", "") in ("authored", "honest-skip")]
    show = authored or list(lives)[:1]
    for ev in show:
        et = getattr(ev, "type", "") or ""
        ref = getattr(ev, "ref", "") or ""
        enote = getattr(ev, "note", "") or ""
        note = f" ({enote})" if enote else ""
        lines.append(f"lives: {et} {ref}{note}")
    return lines


# --- visual encoding: ONE colour axis (health) + a coherent type-icon set -----
# Every colour is paired with a glyph AND a word (WCAG 1.4.1); icons are decorative
# (aria-hidden) — the section NAME text is the accessible name.
_HEALTH_GLYPH = {"ok": "✓", "call": "»", "risk": "✗", "warn": "⚠", "info": "•"}
# 16px geometric line icons, currentColor, no external assets.
_ICON_PATHS = {
    "glance": '<path d="M2.5 12a5.5 5.5 0 0 1 11 0"/><path d="M8 12l3-3.4"/>',
    "outcomes": '<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2.2"/>',
    "capabilities": '<path d="M8 2.5l5.5 3L8 8.5 2.5 5.5z"/><path d="M2.5 8.5L8 11.5l5.5-3"/>',
    "decisions": '<path d="M4.2 2.2v11.6"/><path d="M4.2 3h7l-1.6 2.3L11.2 7.6H4.2z"/>',
    "floor": '<circle cx="8" cy="8" r="6"/><path d="M4 4l8 8"/>',
    "trace": '<circle cx="4" cy="8" r="1.5"/><circle cx="12" cy="4.5" r="1.5"/>'
             '<circle cx="12" cy="11.5" r="1.5"/><path d="M5.4 7.3l5.2-2.3M5.4 8.7l5.2 2.3"/>',
}


def _ico(name: str) -> str:
    return (f'<svg class="ico" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" '
            f'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
            f'stroke-linejoin="round">{_ICON_PATHS.get(name, "")}</svg>')


def _touch_tags(frs) -> list:
    """Counted 'what does this requirement touch' facet — top path segment (a subsystem) for a
    repo-relative path, else the file stem. Ranked by frequency."""
    from collections import Counter

    c: Counter = Counter()
    for f in frs:
        for ev in getattr(f, "lives", ()) or ():
            ref = (getattr(ev, "ref", "") or "").strip("` ")
            if not ref:
                continue
            if ref.startswith(("~", "/")):  # home/abs → the file, not the '~'/'' path prefix
                area = Path(ref).stem
            else:
                parts = ref.split("/")
                area = parts[0] if len(parts) > 1 else Path(ref).stem
            area = area.strip()
            if area:
                c[area] += 1
    return c.most_common()


def _row(sid: str, icon: str, health: str, name: str, verdict_html: str) -> str:
    """A status-line <summary>: [type-icon muted] Name — [health-glyph] verdict.
    health ∈ ok|call|risk|warn|info; colour lives on the glyph + left rail, never alone."""
    g = _HEALTH_GLYPH.get(health, "•")
    return (f'<summary id="{esc(sid)}" class="row {esc(health)}">{_ico(icon)}'
            f'<span class="nm">{esc(name)}</span>'
            f'<span class="vd"> — <b class="g" aria-hidden="true">{g}</b> {verdict_html}</span>'
            f'</summary>')


def _inline_md(text: str) -> str:
    """Render inline Markdown emphasis SAFELY: escape first (no injection), then convert
    ``**bold**`` → <strong>, `` `code` `` → <code>, ``*italic*`` → <em>."""
    s = esc(text or "")
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*([^*\s](?:[^*]*[^*\s])?)\*", r"<em>\1</em>", s)
    return s


# =============================================================================
# View model — computed ONCE, consumed by both the text and HTML renderers.
# =============================================================================
class ReqView:
    def __init__(self, nodes: List[Node]):
        self.nodes = nodes
        self.masthead = (by_kind(nodes, "masthead") or [None])[0]
        self.objectives = by_kind(nodes, "objective")
        self.frs = by_kind(nodes, "fr")
        self.risks = by_kind(nodes, "risk")
        self.nongoals = by_kind(nodes, "non_goal")
        self.owned = by_kind(nodes, "owned_field")
        self.high_risks = [r for r in self.risks if attr(r, "priority") == "high"]

    def frs_for(self, obj_key: str) -> List[Node]:
        """Capabilities grouped under the objective each Serves."""
        return [f for f in self.frs if attr(f, "serves").strip() == obj_key]

    def unlinked_frs(self) -> List[Node]:
        """FRs not grouped under any objective (no OR broken Serves) — for display grouping."""
        obj_keys = {o.key for o in self.objectives}
        return [f for f in self.frs if attr(f, "serves").strip() not in obj_keys]

    def uses_serves(self) -> bool:
        """Does this doc use the OPTIONAL `Serves: O-n` micro-syntax at all? (det-req §5)."""
        return any(self._serve_keys(f) for f in self.frs)

    def _serve_keys(self, f) -> set:
        raw = attr(f, "serves").strip()
        if not raw or raw.startswith("—"):
            return set()
        return {p.strip() for p in raw.split(",") if re.match(r"^O-\d+$", p.strip())}

    def orphan_frs(self) -> List[Node]:
        """An FR that *claims* to serve an objective that doesn't exist (broken Serves)."""
        obj_keys = {o.key for o in self.objectives}
        orphans = []
        for f in self.frs:
            keys = self._serve_keys(f)
            if keys and not keys.issubset(obj_keys):
                orphans.append(f)
        return orphans

    def masthead_line(self) -> str:
        m = self.masthead
        parts = []
        crit = attr(m, "criticality") if m else ""
        ver = attr(m, "version") if m else ""
        if crit:
            parts.append(f"criticality {crit}")
        if ver:
            parts.append(f"v{ver}")
        parts.append(f"{len(self.frs)} capabilities")
        parts.append(f"{len(self.objectives)} outcomes")
        parts.append(
            f"{len(self.risks)} risks"
            + (f" ({len(self.high_risks)} high)" if self.high_risks else "")
        )
        return " · ".join(parts)


# =============================================================================
# 1) DENSE SPEAKABLE TEXT VIEW — validation-ordered, every line is signal.
# =============================================================================
def render_text(v: ReqView, title: str = "") -> str:
    L: List[str] = []
    heading = title or (v.masthead.key if v.masthead else "requirement")
    L.append(f"REQUIREMENT — {heading}")
    L.append(f"  {v.masthead_line()}")
    L.append("")

    # (b) OUTCOMES — each objective + its target
    L.append(f"OUTCOMES ({len(v.objectives)})")
    for o in v.objectives:
        L.append(f"  [{status_label(o)}] {o.key} — {does(o)}")
        tgt = attr(o, "target")
        if tgt:
            L.append(f"        target: {tgt}")
    L.append("")

    # (c) CAPABILITIES — grouped under the objective each Serves, one line + verify
    L.append(f"CAPABILITIES ({len(v.frs)}) — grouped by outcome they serve")
    for o in v.objectives:
        serving = v.frs_for(o.key)
        if not serving:
            continue
        L.append(f"  ▸ {o.key} — {does(o)}")
        for f in serving:
            L.append(f"      [{status_label(f)}] {f.key} — {f.does}")
            ver = attr(f, "verify")
            if ver:
                L.append(f"          verify: {ver}")
            for el in _evidence_lines(f):
                L.append(f"          {el}")
    for f in v.unlinked_frs():
        L.append(f"  ▸ (unlinked) [{status_label(f)}] {f.key} — {f.does}")
        ver = attr(f, "verify")
        if ver:
            L.append(f"          verify: {ver}")
        for el in _evidence_lines(f):
            L.append(f"          {el}")
    L.append("")

    # (d) DECISIONS FOR YOU — high risks in FULL + owned fields
    L.append(f"DECISIONS FOR YOU ({len(v.high_risks)} high risk(s) + {len(v.owned)} owned field(s))")
    for r in v.high_risks:
        L.append(
            f"  [{status_label(r)}] {attr(r, 'priority').upper()} · {attr(r, 'risk_type')} "
            "— needs your sign-off"
        )
        L.append(f"        {attr(r, 'description')}")
        mit = attr(r, "mitigation")
        if mit:
            L.append(f"        mitigation: {mit}")
    for of in v.owned:
        L.append(f"  [{status_label(of)}] you decide: {of.key}")
    L.append("")

    # (e) THE FLOOR — non-goals (guard rails)
    L.append(f"THE FLOOR ({len(v.nongoals)} non-goal(s) — what this will NOT do)")
    for ng in v.nongoals:
        floor = (ng.wont[0] if ng.wont else attr(ng, "description"))
        L.append(f"  ✗ {floor}")
    return "\n".join(L)


# =============================================================================
# 2) SEMANTIC ACCESSIBLE HTML — same content/order, screen-reader-native, no JS.
#    Own shell (no FONT_CSS/wireframe): system font stack keeps it offline/no-CDN.
# =============================================================================
CSS = """
:root { --fg:#1a1a1a; --muted:#555; --line:#d9d5cc; --bg:#fbfaf7;
        --focus:#0b5cad; --risk:#8a2f24; --goal:#2f5d3f; --spec:#5a5344;
        --owned:#8a5a10; }
* { box-sizing:border-box; }
body { font:18px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       color:var(--fg); background:var(--bg); margin:0; padding:0 0 4rem; }
main { max-width:min(1360px, 94vw); margin:0 auto; padding:0 1.5rem; }
h1 { font-family:Georgia,"Iowan Old Style",ui-serif,serif; font-size:2rem; font-weight:600;
     margin:1rem 0 .5rem; letter-spacing:-0.01em; }
h2 { font-size:1.1rem; margin:1.1rem 0 .3rem; padding-top:.3rem; border-top:2px solid var(--line); }
h3 { font-size:.98rem; margin:.7rem 0 .15rem; color:var(--muted); }
p { margin:.2rem 0; }
ul,dl { margin:.2rem 0 .2rem; padding-left:1.1rem; }
li { margin:.1rem 0; }
dl { padding-left:0; }
dt { font-weight:600; }
dd { margin:0 0 .3rem .9rem; color:var(--muted); }
.masthead { color:var(--muted); font-size:.9rem; margin:0 0 .3rem; }
/* collapsible drill sections */
details.drill { border:1px solid var(--line); border-left:3px solid var(--line);
                border-radius:4px; margin:.3rem 0; background:#fff; }
details.drill > summary { cursor:pointer; padding:.85rem 1.1rem; min-height:3.5rem;
                          transition:background .12s ease; }
details.drill > summary:hover { background:#f4f1ea; }
@media (prefers-reduced-motion:reduce){ details.drill > summary { transition:none; } }
details.drill[open] > summary { border-bottom:1px solid var(--line); }
details.drill > *:not(summary) { padding-left:1.1rem; padding-right:1.1rem; }
summary.row { display:flex; align-items:baseline; gap:.6rem; font-size:1.15rem; }
summary.row .ico { flex:0 0 auto; width:1.25em; height:1.25em; color:var(--muted); align-self:center; }
summary.row .nm { font-weight:700; color:var(--fg); }
summary.row .vd { color:var(--muted); font-weight:400; }
summary.row .vd .g { font-weight:800; font-size:1.02em; }
/* the ONE colour axis = health. Colour rides on the rail + glyph, always beside a word. */
details.drill.ok   { border-left-color:var(--goal); }
details.drill.call { border-left-color:var(--owned); background:#fdfaf3; }
details.drill.risk { border-left-color:var(--risk); background:#fdf5f4; }
details.drill.info { border-left-color:var(--line); }
summary.row.ok   .g { color:var(--goal); }
summary.row.call .g { color:var(--owned); }
summary.row.risk .g { color:var(--risk); }
summary.row.info .g { color:var(--muted); }
details.drill > summary:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
/* status is a WORD, never color-only (WCAG 1.4.1) */
.tag { font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.03em;
       padding:.05rem .35rem; border-radius:3px; border:1px solid currentColor; margin-right:.35rem;
       white-space:nowrap; }
.tag.goal,.tag.grounded { color:var(--goal); }
.tag.spec,.tag.awaiting { color:var(--spec); }
.tag.risk-high,.tag.risk-med { color:var(--risk); }
.tag.excluded,.tag.unknown { color:var(--spec); }
.tag.needs-you { color:var(--owned); }
.cap { margin:.15rem 0 .35rem; }
.field { color:var(--muted); font-size:.9rem; margin:.05rem 0 .05rem 1.2rem; }
.field.warn { color:var(--risk); }
/* traceability table */
table.trace { border-collapse:collapse; width:100%; font-size:.92rem; margin:.3rem 0; }
table.trace caption { text-align:left; color:var(--muted); font-size:.82rem; margin-bottom:.25rem; }
table.trace th, table.trace td { border:1px solid var(--line); padding:.3rem .5rem;
                                 text-align:left; vertical-align:top; }
table.trace thead th { background:var(--bg); }
table.trace tr.warn td, table.trace tr.warn th { background:#fdf3f2; }
.chip { display:inline-block; font-size:.78rem; border:1px solid var(--line); border-radius:3px;
        padding:.02rem .3rem; margin:.05rem; background:#fff; }
.chip.warn { border-color:var(--risk); color:var(--risk); }
ul.tags { list-style:none; padding:.5rem 0 .3rem; margin:0; display:flex; flex-wrap:wrap; gap:.45rem; }
.tagchip { border:1px solid var(--line); border-radius:6px; padding:.3rem .65rem; font-size:1rem;
           background:var(--bg); }
.tagchip b { color:var(--muted); font-weight:800; margin-left:.15rem; }
.floor li { color:var(--spec); }
.legend { color:var(--muted); font-size:.8rem; margin:.3rem 0 0; }
a.href { color:var(--focus); }
a:focus-visible, [tabindex]:focus-visible {
  outline:3px solid var(--focus); outline-offset:2px; }
.skip-link { position:absolute; left:0; top:-3rem; background:#000; color:#fff;
             padding:.5rem 1rem; z-index:10; transition:top 150ms; }
.skip-link:focus { top:0; }
nav.toc ul { list-style:none; padding-left:0; display:flex; flex-wrap:wrap; gap:.5rem; margin:.5rem 0; }
nav.toc a { text-decoration:none; border:1px solid var(--line); border-radius:5px;
            padding:.45rem .8rem; font-size:.95rem; min-height:2.75rem; display:inline-flex;
            align-items:center; color:var(--fg); }
nav.toc a:hover { background:#f4f1ea; }
@media (prefers-reduced-motion: reduce) { .skip-link { transition:none; } }
@media print {
  nav.toc, .skip-link { display:none !important; }
  details.drill > *:not(summary) { display:block !important; }
  details.drill { break-inside:avoid; border-left-width:3px; }
  body { font-size:11pt; background:#fff; }
}
"""


def tag(n: Node) -> str:
    sk = status_label(n)
    return f'<span class="tag {esc(sk)}">{esc(sk)}</span>'


def render_html(
    v: ReqView,
    title: str = "",
    up_href: str = "",
    up_label: str = "",
    *,
    role: Optional[str] = None,
    fluency: str = "intermediate",
) -> str:
    """Render a ReqView to a self-contained, screen-reader-native HTML document.

    ``title`` titles the requirement (the doc's H1); falls back to the masthead key.
    ``up_href``/``up_label`` add a breadcrumb back to a parent view (a corpus index links its
    leaves back to itself). Every href is passed through the REQ-02 `_safe_href` sanitizer.

    ``role`` (FR-2, opt-in) routes the requirement ``does`` labels through the shared
    ``apply_node_lenses`` transform (soft-import guarded); ``role=None`` (the default) renders raw
    ``Node`` labels and is byte-identical to the pre-REQ-09 output.
    """
    labels = _lens_labels(v.nodes, role=role, fluency=fluency)
    title = esc(title or (v.masthead.key if v.masthead else "requirement"))
    P: List[str] = []
    P.append("<!doctype html>")
    P.append('<html lang="en"><head><meta charset="utf-8">')
    P.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    P.append(f"<title>{title} — requirement view</title>")
    P.append(f"<style>{CSS}</style></head><body>")
    P.append('<a class="skip-link" href="#main">Skip to the content</a>')

    # Breadcrumb — wayfinding back to the parent view (defence-in-depth: sanitize the href).
    if up_href:
        _uh = _safe_href(up_href)
        if _uh is not None:
            P.append(
                '<nav class="crumb" aria-label="Breadcrumb" '
                'style="padding:.5rem 1rem;font-size:1.05rem;font-weight:600">'
                f'<a class="href" href="{esc(_uh)}">{esc(up_label or "← Back")}</a></nav>'
            )

    # nav landmark — table of contents (screen readers jump by region)
    P.append('<nav class="toc" aria-label="Sections">')
    P.append("<ul>")
    for anchor, label in [
        ("outcomes", "Outcomes"), ("trace", "Traceability"),
        ("capabilities", "Capabilities"), ("decisions", "Decisions"),
        ("floor", "The floor"),
    ]:
        P.append(f'<li><a class="href" href="#{esc(anchor)}">{esc(label)}</a></li>')
    P.append("</ul></nav>")

    P.append('<main id="main" tabindex="-1">')
    P.append(f"<h1>{title}</h1>")
    P.append(f'<p class="masthead">{esc(v.masthead_line())}</p>')

    # ---- OUTCOMES ----
    _no_tgt = [o for o in v.objectives if not attr(o, "target").strip()]
    if not v.objectives:
        _oh, _ov = "info", "No outcomes declared — Serves is optional (det-req §5)"
    elif _no_tgt:
        _oh, _ov = "risk", f"{len(_no_tgt)} without a target"
    else:
        _oh, _ov = "ok", "all have a target"
    P.append(f'<details class="drill {_oh}" open>')
    P.append(_row("outcomes", "outcomes", _oh, f"Outcomes ({len(v.objectives)})", esc(_ov)))
    P.append("<ul>")
    for o in v.objectives:
        tgt = attr(o, "target")
        head = f'{tag(o)}<strong>{esc(o.key)}</strong>'
        _o_does = _lensed(o, labels) or does(o)
        P.append(f"<li>{head} — {esc(tgt) if tgt else esc(_o_does)}")
        if tgt:
            P.append(f'<div class="field">{esc(_o_does)}</div>')
        P.append("</li>")
    P.append("</ul></details>")

    # ---- TRACEABILITY — the spine (Serves is optional, det-req §5) ----
    _traced = v.uses_serves()
    _n_served = len([o for o in v.objectives if v.frs_for(o.key)])
    _orph = v.orphan_frs()
    if not _traced:
        _thealth, _tv = "info", "Serves not declared (optional) — FRs grouped by section"
    elif _orph or _n_served < len(v.objectives):
        _thealth = "risk"
        _tv = (f"{_n_served}/{len(v.objectives)} outcomes served"
               + (f" · {len(_orph)} broken ref(s)" if _orph else ""))
    else:
        _thealth, _tv = "ok", f"{_n_served}/{len(v.objectives)} outcomes served"
    P.append(f'<details class="drill {_thealth}">')
    P.append(_row("trace", "trace", _thealth, "Traceability", esc(_tv)))
    P.append('<table class="trace">')
    P.append('<caption>Each outcome and the capabilities that serve it (via the optional Serves: '
             'field). An outcome with no capability, or a capability with a missing outcome, '
             'is a spine gap.</caption>')
    P.append('<thead><tr><th scope="col">Outcome</th><th scope="col">Served by</th>'
             '<th scope="col">Status</th></tr></thead><tbody>')
    for o in v.objectives:
        serving = v.frs_for(o.key)
        chips = " ".join(f'<span class="chip">{esc(f.key)}</span>' for f in serving) or "—"
        if serving:
            st, rc = "✓ served", ""
        elif _traced:
            st, rc = "⚠ no capability", ' class="warn"'
        else:
            st, rc = "○ not traced", ""
        P.append(f'<tr{rc}><th scope="row">{esc(o.key)}</th><td>{chips}</td><td>{esc(st)}</td></tr>')
    if _orph:
        chips = " ".join(f'<span class="chip warn">{esc(f.key)}</span>' for f in _orph)
        P.append(f'<tr class="warn"><th scope="row">broken</th><td>{chips}</td>'
                 f'<td>⚠ serve a missing outcome</td></tr>')
    P.append("</tbody></table></details>")

    # ---- TOUCHES — counted-chip facet of the subsystems this requirement spans ----
    _tags = _touch_tags(v.frs)
    if _tags:
        P.append('<details class="drill info">')
        _span = ", ".join(a for a, _ in _tags[:6]) + ("…" if len(_tags) > 6 else "")
        P.append(_row("touches", "trace", "info", f"Touches ({len(_tags)} areas)",
                      "spans " + esc(_span)))
        P.append('<ul class="tags">')
        for area, n in _tags:
            P.append(f'<li class="tagchip">{esc(area)} <b>{n}</b></li>')
        P.append("</ul></details>")

    # ---- CAPABILITIES — grouped by served outcome ----
    _ch = "risk" if (v.orphan_frs() or [f for f in v.frs if not attr(f, "verify").strip()]) else "ok"
    _cv = ("all have a verify" + (" & serve an outcome" if v.uses_serves() else "")
           if _ch == "ok" else "has a verify / broken-Serves gap")
    P.append(f'<details class="drill {_ch}" open>')
    P.append(_row("capabilities", "capabilities", _ch, f"Capabilities ({len(v.frs)})", esc(_cv)))

    def _emit_cap(f: Node) -> None:
        P.append(
            f'<li class="cap" id="cap-{esc(f.key)}">{tag(f)}'
            f'<strong>{esc(f.key)}</strong> — {esc(_lensed(f, labels) or f.does)}'
        )
        ver = attr(f, "verify")
        if ver:
            P.append(f'<div class="field"><em>verify:</em> {_inline_md(ver)}</div>')
        for el in _evidence_lines(f):
            if el.startswith("evidence: UNKNOWN"):
                P.append(f'<div class="field warn"><em>evidence:</em> '
                         f'{esc(el[len("evidence:"):].strip())}</div>')
            elif el.startswith("lives: "):
                P.append(f'<div class="field"><em>lives:</em> {esc(el[len("lives: "):])}</div>')
            else:
                P.append(f'<div class="field">{esc(el)}</div>')
        P.append("</li>")

    for o in v.objectives:
        serving = v.frs_for(o.key)
        if not serving:
            continue
        P.append(f"<h3>Serves {esc(o.key)} — {esc(_lensed(o, labels) or does(o))}</h3><ul>")
        for f in serving:
            _emit_cap(f)
        P.append("</ul>")
    unlinked = v.unlinked_frs()
    if unlinked:
        _h = ("Not traced to an outcome (Serves optional)"
              if not v.uses_serves() else "Unlinked to an outcome")
        P.append(f"<h3>{esc(_h)}</h3><ul>")
        for f in unlinked:
            _emit_cap(f)
        P.append("</ul>")
    P.append("</details>")

    # ---- DECISIONS FOR YOU ----
    _dh = "call" if (v.high_risks or v.owned) else "ok"
    _dv = (f"{len(v.high_risks) + len(v.owned)} need you — "
           f"{len(v.high_risks)} sign-off · {len(v.owned)} owned") if _dh == "call" else "none"
    P.append(f'<details class="drill {_dh}">')
    P.append(_row("decisions", "decisions", _dh, "Decisions for you", esc(_dv)))
    for r in v.high_risks:
        pill = f'<span class="tag risk-high">{esc(attr(r, "priority").upper())} RISK</span>'
        head = f'{pill}{_inline_md(attr(r, "risk_type"))}'
        P.append(f"<details open><summary>{head} — needs your sign-off</summary>")
        P.append(f'<p class="field">{_inline_md(attr(r, "description"))}</p>')
        mit = attr(r, "mitigation")
        if mit:
            P.append(f'<p class="field"><em>mitigation:</em> {_inline_md(mit)}</p>')
        P.append("</details>")
    if v.owned:
        P.append("<h3>Owned fields — you decide these</h3><ul>")
        for of in v.owned:
            P.append(f"<li>{tag(of)}<strong>{esc(of.key)}</strong></li>")
        P.append("</ul>")
    P.append("</details>")

    # ---- THE FLOOR — non-goals ----
    P.append('<details class="drill info">')
    P.append(_row("floor", "floor", "info", "The floor",
                  esc(f"{len(v.nongoals)} non-goal(s) — will NOT do")))
    P.append('<ul class="floor">')
    for ng in v.nongoals:
        floor = (ng.wont[0] if ng.wont else attr(ng, "description"))
        P.append(f"<li>✗ {esc(floor)}</li>")
    P.append("</ul></details>")

    P.append('<p class="legend">✓ ok · ⚠ needs attention · » your call — glyph + word '
             '(grayscale + screen-reader legible; status is never colour-only).</p>')
    P.append("</main></body></html>")
    return "\n".join(P)


# =============================================================================
# Verify + report — the bleed guard (a11y shell carries no wireframe summary chrome)
# =============================================================================
WIREFRAME_BLEED = ["Entities", "CRUD routes", "Pages", "Views", "AI passes"]


def check_no_bleed(html_text: str) -> Dict[str, object]:
    hits = [tok for tok in WIREFRAME_BLEED if tok in html_text]
    # a "0 / 0 / 0" shape row (any spacing) — the wireframe summary-chrome tell
    zero_shape = bool(re.search(r"\b0\s*/\s*0\s*/\s*0\b", html_text))
    return {"leaked_tokens": hits, "zero_shape_row": zero_shape,
            "pass": (not hits and not zero_shape)}


def render_a11y_to_file(
    nodes: List[Node], out_path, title: str = "",
    up_href: str = "", up_label: str = "",
    *,
    role: Optional[str] = None,
    fluency: str = "intermediate",
) -> str:
    """Render requirement Nodes to a self-contained, screen-reader-native HTML view.

    Requirement-native: reads only the Node model — it never imports or invokes the wireframe
    renderer, so no app-domain chrome can bleed in. ``up_href``/``up_label`` add a breadcrumb back
    to a parent view (a corpus index links its leaves back to itself).

    ``role`` (FR-2, opt-in) routes the requirement ``does`` labels through the shared lens transform;
    ``role=None`` (the default) is byte-identical to the pre-REQ-09 output. Returns the path written.
    """
    v = ReqView(list(nodes))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_html(v, title=title, up_href=up_href, up_label=up_label,
                    role=role, fluency=fluency),
        encoding="utf-8",
    )
    return str(out_path)
