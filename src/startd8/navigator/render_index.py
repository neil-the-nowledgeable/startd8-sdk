"""Requirements-corpus index (REQ-03 FR-2) — a static, offline, no-JS overview of MANY requirement
docs: one health-encoded row per REQ + a facet-count coverage strip, drilling to one a11y leaf per doc.

Port of the ContextCore navigator corpus index (`navigator/render_index.py`, LIVE symbols only).
Standalone: reuses REQ-03's a11y renderer (`.render_a11y`) for the shell styling and leaf rendering,
and `.sources_requirements.nodes_from_requirements` for projection — it never imports `wireframe_view`.
Relative hrefs only, so the generated folder is portable/offline. Robust to a heterogeneous corpus:
one unparseable doc degrades to a plain (non-linked) span and never breaks the index.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, List

from .render_a11y import (
    CSS,
    ReqView,
    _HEALTH_GLYPH,
    _ico,
    _touch_tags,
    attr,
    esc,
    render_a11y_to_file,
)
from .render_tree import _safe_href  # shared XSS helper (REQ-02, decision-1)
from .sources_requirements import nodes_from_requirements

_HEALTH_ORDER = {"risk": 0, "call": 1, "ok": 2, "info": 3}  # attention-first

_INDEX_CSS = """
ul.idx { list-style:none; padding:0; margin:.5rem 0; }
li.idxrow { border:1px solid var(--line); border-left:4px solid var(--line); border-radius:5px;
            margin:.35rem 0; padding:.7rem 1rem; display:flex; align-items:baseline; gap:.6rem;
            flex-wrap:wrap; }
li.idxrow.ok{border-left-color:var(--goal)}
li.idxrow.call{border-left-color:var(--owned);background:#fdfaf3}
li.idxrow.risk{border-left-color:var(--risk);background:#fdf5f4}
li.idxrow.info{border-left-color:var(--line)}
li.idxrow .g{font-weight:800;font-size:1.05em}
li.idxrow.ok .g{color:var(--goal)} li.idxrow.call .g{color:var(--owned)}
li.idxrow.risk .g{color:var(--risk)}
li.idxrow .nm{font-weight:700;font-size:1.1rem} li.idxrow a.nm{color:var(--fg);text-decoration:none}
li.idxrow a.nm:hover{text-decoration:underline}
li.idxrow .meta{color:var(--muted)}
li.idxrow .ico{color:var(--muted);width:1.2em;height:1.2em;align-self:center}
.coverage{border:1px solid var(--line);border-radius:6px;padding:.7rem 1rem;margin:.5rem 0;
          background:#fff;font-size:1.1rem}
"""


def _doc_title(path: Path, fallback: str) -> str:
    """The requirement's own name (first H1), not the project key. Strip a trailing '— Requirements'."""
    try:
        for ln in path.read_text(encoding="utf-8").splitlines():
            if ln.startswith("# "):
                t = ln[2:].strip()
                for suf in (" — Requirements", " — requirements", " Requirements"):
                    if t.endswith(suf):
                        t = t[: -len(suf)].rstrip(" —")
                return t
    except Exception:
        pass
    return fallback


def _req_summary(path: Path) -> Dict:
    """One requirement → its corpus-index row data. Robust to a doc that won't parse."""
    name = _doc_title(path, path.stem)
    try:
        nodes = nodes_from_requirements(path)
        v = ReqView(nodes)
    except Exception as exc:  # heterogeneous corpus — never let one bad doc break the index
        return {"name": name, "path": path.name, "src": path, "health": "info",
                "error": str(exc)[:70], "n_fr": 0, "n_obj": 0, "n_risk": 0, "n_high": 0,
                "backend": "", "version": "", "tags": []}
    unmit = [r for r in v.high_risks if not attr(r, "mitigation").strip()]
    no_verify = [f for f in v.frs if not attr(f, "verify").strip()]
    # Serves is optional (det-req §5): a broken Serves or a missing verify/mitigation is a gap;
    # an FR simply not declaring Serves is conformant, not a gap.
    gap = (bool(v.orphan_frs()) or bool(no_verify) or bool(unmit)
           or (v.uses_serves() and any(not v.frs_for(o.key) for o in v.objectives)))
    # a doc with no parsed det-req sections is 'info' (not 'ok') — likely an older/foreign format
    if not v.frs and not v.objectives:
        health = "info"
    else:
        health = "risk" if gap else ("call" if (v.high_risks or v.owned) else "ok")
    m = v.masthead
    return {
        "name": name, "path": path.name, "src": path, "health": health,
        "error": ("no det-req sections parsed" if health == "info" else ""),
        "n_fr": len(v.frs), "n_obj": len(v.objectives), "n_risk": len(v.risks),
        "n_high": len(v.high_risks), "backend": (attr(m, "backend") if m else ""),
        "version": (attr(m, "version") if m else ""),
        "tags": [a for a, _ in _touch_tags(v.frs)[:5]],
    }


def _render_leaf(entry: Dict, leaves_dir: Path, index_name: str = "") -> str:
    """Render one parseable REQ's a11y leaf view to leaves/<stem>.html; return the relative href,
    or "" if the row is non-parseable or the leaf render throws (graceful skip — one bad doc must
    never break the corpus index).

    ``index_name`` is the corpus index's filename; the leaf gets a breadcrumb back to it
    (``../<index_name>``) so drill-to-leaf is round-trippable, not a dead-end."""
    if entry.get("error") or entry.get("src") is None:
        return ""  # info/unparseable rows get no (dead) link
    src = Path(entry["src"])
    stem = src.stem
    leaf_path = leaves_dir / f"{stem}.html"
    try:
        leaves_dir.mkdir(parents=True, exist_ok=True)
        render_a11y_to_file(
            nodes_from_requirements(src), leaf_path, title=entry["name"],
            up_href=(f"../{index_name}" if index_name else ""), up_label="← All requirements")
    except Exception:  # heterogeneous corpus — a bad leaf falls back to a plain span
        return ""
    return f"leaves/{stem}.html"


def render_index_to_file(req_dir: Path, out_path, title: str = "Requirements") -> str:
    req_dir = Path(req_dir)
    entries = [_req_summary(p) for p in sorted(req_dir.glob("REQ-*.md"))]
    entries.sort(key=lambda e: (_HEALTH_ORDER.get(e["health"], 9), e["name"]))
    # Drill-to-leaf (FR-2): render each parseable REQ's a11y leaf view to a sibling leaves/ dir
    # and link the row name to it. Relative hrefs only → the folder is portable/offline.
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    leaves_dir = out_path.resolve().parent / "leaves"
    index_name = out_path.name  # leaves link back to this file (../<index_name>)
    for e in entries:
        e["href"] = _render_leaf(e, leaves_dir, index_name)
    total = len(entries)
    sound = sum(1 for e in entries if e["health"] in ("ok", "call") and not e["error"])
    backends = Counter(e["backend"].split("(")[0].strip() for e in entries if e["backend"])
    risky = sum(1 for e in entries if e["n_high"])

    P: List[str] = ["<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
                    '<meta name="viewport" content="width=device-width, initial-scale=1">',
                    f"<title>{esc(title)} — corpus navigator</title>",
                    f"<style>{CSS}{_INDEX_CSS}</style></head><body>",
                    '<a class="skip-link" href="#main">Skip to the list</a>',
                    '<main id="main" tabindex="-1">',
                    f"<h1>{esc(title)} — {total} requirements</h1>"]
    P.append('<p class="coverage"><b>Coverage:</b> '
             f'{sound}/{total} structurally sound · {risky} with high risk(s)'
             + (" · " + ", ".join(f"{esc(b)} <b>{n}</b>" for b, n in backends.most_common())
                if backends else "")
             + "</p>")
    P.append('<ul class="idx">')
    for e in entries:
        g = _HEALTH_GLYPH.get(e["health"], "•")
        if e["error"]:
            body = f'<span class="meta">— could not parse ({esc(e["error"])})</span>'
        else:
            tags = " · ".join(esc(t) for t in e["tags"])
            body = (f'<span class="meta">— {e["n_fr"]} FR · {e["n_obj"]} outcomes · '
                    f'{e["n_risk"]} risks' + (f' ({e["n_high"]} high)' if e["n_high"] else "")
                    + (f' · {esc(e["backend"].split("(")[0].strip())}' if e["backend"] else "")
                    + (f' · v{esc(e["version"])}' if e["version"] else "")
                    + (f' · <span style="color:var(--muted)">touches {tags}</span>' if tags else "")
                    + "</span>")
        href = e.get("href", "")
        _safe = _safe_href(href) if href else None
        if _safe:  # parseable rows link to their a11y leaf view (relative, offline-portable)
            nm = f'<a class="nm" href="{esc(_safe)}">{esc(e["name"])}</a>'
        else:      # info/unparseable rows stay a plain span — no dead link
            nm = f'<span class="nm">{esc(e["name"])}</span>'
        P.append(f'<li class="idxrow {esc(e["health"])}">{_ico("outcomes")}'
                 f'<b class="g" aria-hidden="true">{g}</b>'
                 f'{nm} {body} '
                 f'<span class="meta" style="margin-left:auto;font-size:.9rem">'
                 f'{esc(e["path"])}</span></li>')
    P.append("</ul></main></body></html>")
    out_path.write_text("\n".join(P), encoding="utf-8")
    return str(out_path)
