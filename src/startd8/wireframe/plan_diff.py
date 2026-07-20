"""EC-1 — planned-vs-built diff: what changed since the last saved wireframe plan.

Compares two plan bodies (a persisted ``wireframe-plan.json`` baseline vs the current build) so an author
who approved a preview can see exactly what moved — added / removed items, per-item and per-section status
changes, and shape + content deltas. This is the *verify* half of the loop the preview opens:
**preview → approve (persist) → build → verify (diff against what you approved)**.

Pure over two dicts; reads only the stable canonical-body keys (``inputs_fingerprint``, ``shape``,
``content_completeness``, ``sections``) so it works whether the baseline carries ``_meta`` or not.
The ``inputs_fingerprint`` (FR-W12) is the cheap "did the inputs change at all?" signal.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def load_baseline(path: Path) -> Optional[dict]:
    """Load a persisted plan JSON (canonical fields live at the top level); ``None`` if absent/unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _items_by_label(section: dict) -> dict:
    return {it.get("label"): it for it in section.get("items", [])}


def _overall(body: dict):
    cc = body.get("content_completeness") or {}
    o = cc.get("overall") or {}
    return o.get("authored"), o.get("total")


def diff_plans(old: dict, new: dict) -> dict:
    """Structured diff of two plan bodies.

    Returns ``{unchanged, fingerprint_changed, shape:{k:(old,new)}, content:{old,new}|None,
    sections:[{key,title,sec_status,added,removed,status_changed}]}``.
    """
    shape = {}
    so, sn = old.get("shape", {}), new.get("shape", {})
    for k in sorted(set(so) | set(sn)):
        if so.get(k) != sn.get(k):
            shape[k] = (so.get(k), sn.get(k))

    content = None
    if _overall(old) != _overall(new):
        content = {"old": _overall(old), "new": _overall(new)}

    old_secs = {s.get("key"): s for s in old.get("sections", [])}
    new_secs = {s.get("key"): s for s in new.get("sections", [])}
    sections = []
    for key in sorted(set(old_secs) | set(new_secs), key=lambda k: str(k)):
        os_, ns_ = old_secs.get(key, {}), new_secs.get(key, {})
        oi, ni = _items_by_label(os_), _items_by_label(ns_)
        added = sorted(set(ni) - set(oi), key=lambda x: str(x))
        removed = sorted(set(oi) - set(ni), key=lambda x: str(x))
        status_changed = {
            lbl: (oi[lbl].get("status"), ni[lbl].get("status"))
            for lbl in sorted(set(oi) & set(ni), key=lambda x: str(x))
            if oi[lbl].get("status") != ni[lbl].get("status")
        }
        sec_status = None
        if os_ and ns_ and os_.get("status") != ns_.get("status"):
            sec_status = (os_.get("status"), ns_.get("status"))
        if added or removed or status_changed or sec_status:
            sections.append({
                "key": key, "title": ns_.get("title") or os_.get("title") or key,
                "sec_status": sec_status, "added": added, "removed": removed,
                "status_changed": status_changed,
            })

    return {
        "unchanged": not (shape or content or sections),
        "fingerprint_changed": old.get("inputs_fingerprint") != new.get("inputs_fingerprint"),
        "shape": shape, "content": content, "sections": sections,
    }


def format_diff(d: dict) -> str:
    """A readable terminal report (Rich markup) of a :func:`diff_plans` result."""
    if d["unchanged"]:
        note = "" if d["fingerprint_changed"] else " (inputs unchanged too)"
        return f"[green]✓ Nothing changed[/green] since the last saved preview{note}."
    out = ["[bold]Since the last saved preview:[/bold]"]
    if d["shape"]:
        out.append("  [bold]Shape:[/bold] " + " · ".join(f"{k} {o}→{n}" for k, (o, n) in d["shape"].items()))
    if d["content"]:
        (oa, ot), (na, nt) = d["content"]["old"], d["content"]["new"]
        out.append(f"  [bold]Content:[/bold] {oa}/{ot} → {na}/{nt} authored")
    for s in d["sections"]:
        head = f"  [bold]{s['title']}[/bold]"
        if s["sec_status"]:
            head += f"  [yellow]({s['sec_status'][0]} → {s['sec_status'][1]})[/yellow]"
        out.append(head)
        out += [f"    [green]+ {a}[/green]" for a in s["added"]]
        out += [f"    [red]- {r}[/red]" for r in s["removed"]]
        out += [f"    [yellow]~ {lbl}: {o} → {n}[/yellow]" for lbl, (o, n) in s["status_changed"].items()]
    return "\n".join(out)
