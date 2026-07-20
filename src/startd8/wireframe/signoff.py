"""EC-2 wiring — ingest an exported wireframe sign-off so it *feeds the loop*.

The HTML preview's "Export sign-off" button (``wireframe_view/_template.py::exportSign``) downloads the
owner's per-section verdict as JSON::

    {app, audience: {role, fluency}, reviewed_at, sections: [{key, title, status, note}]}

where ``status`` ∈ {``ok`` (looks right), ``flag`` (wants a change, with a note), ``unreviewed``}. Until
now nothing read it — a dead-end export. This module loads + validates it and renders a terminal report
so ``startd8 wireframe --signoff <file>`` becomes the gate between preview-approval and build: it exits
non-zero when the owner has open flags, so a handoff/CI step can block on "the owner flagged something".
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

_STATUSES = {"ok", "flag", "unreviewed"}


class SignoffError(ValueError):
    """The sign-off file is missing, unreadable, or not a wireframe sign-off export."""


def load_signoff(path: Path) -> dict:
    """Parse + validate a sign-off export; normalize its sections. Raises :class:`SignoffError` on a
    missing/garbled file or a payload that isn't a wireframe sign-off (degrade-never-fabricate)."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SignoffError(f"cannot read sign-off {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise SignoffError(f"sign-off {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        raise SignoffError(
            f"sign-off {path} has no 'sections' list — is it a wireframe sign-off export?"
        )
    sections = []
    for s in data["sections"]:
        if not isinstance(s, dict) or "key" not in s:
            raise SignoffError(f"sign-off {path}: a section entry is malformed (missing 'key').")
        status = s.get("status", "unreviewed")
        sections.append({
            "key": s["key"],
            "title": s.get("title") or s["key"],
            "status": status if status in _STATUSES else "unreviewed",
            "note": (s.get("note") or "").strip(),
        })
    return {
        "app": data.get("app") or "(unknown app)",
        "audience": data.get("audience") or {},
        "reviewed_at": data.get("reviewed_at") or "",
        # SO-1: the plan identity the verdict was made against (None for pre-provenance exports).
        "inputs_fingerprint": data.get("inputs_fingerprint") or None,
        "schema_version": data.get("schema_version"),
        "sections": sections,
    }


def open_flags(signoff: dict) -> list:
    """The sections the owner flagged for change — the build blockers (the ``--signoff`` gate signal)."""
    return [s for s in signoff["sections"] if s["status"] == "flag"]


def stale_approvals(diff: dict, signoff: dict) -> list:
    """approve↔diff: the sections the owner APPROVED (``ok``) that have since CHANGED in the plan — their
    sign-off is stale and needs re-review. Takes an EC-1 :func:`plan_diff.diff_plans` result (whose
    ``sections`` list holds only changed sections) and the loaded sign-off; returns the changed-section
    dicts whose key was approved."""
    approved = {s["key"] for s in signoff["sections"] if s["status"] == "ok"}
    return [s for s in diff.get("sections", []) if s.get("key") in approved]


def format_approval_check(diff: dict, signoff: dict) -> str:
    """The approve↔diff headline: cross-references the structural diff with the owner's verdict so a change
    to an approved section reads as 'changed since you approved it' (rendered above the full diff)."""
    aud = signoff["audience"] or {}
    who = aud.get("label") or aud.get("role") or "reviewer"
    stale = stale_approvals(diff, signoff)
    flagged = open_flags(signoff)
    lines = [f"[bold]Approval check[/bold] [dim](you signed off as {who})[/dim]:"]
    if stale:
        lines.append(
            f"  [bold red]⚠ {len(stale)} section(s) you approved changed since — "
            "re-review before build:[/bold red]"
        )
        lines += [f"    ⚑ {s['title']}" for s in stale]
    else:
        lines.append("  [green]✓ none of the sections you approved have changed.[/green]")
    if flagged:
        lines.append(
            "  [yellow]⚑ still flagged from your sign-off:[/yellow] "
            + ", ".join(s["title"] for s in flagged)
        )
    return "\n".join(lines)


def format_signoff(signoff: dict) -> str:
    """A plain-text report of the owner's verdict: counts, the flagged to-do (with notes), unreviewed."""
    secs = signoff["sections"]
    c = Counter(s["status"] for s in secs)
    ok, flagged, unrev = c.get("ok", 0), c.get("flag", 0), c.get("unreviewed", 0)
    aud = signoff["audience"] or {}
    who = aud.get("label") or aud.get("role") or "reviewer"
    when = f", {signoff['reviewed_at']}" if signoff["reviewed_at"] else ""
    lines = [
        f"[bold]Sign-off[/bold] — {signoff['app']}  [dim](as {who}{when})[/dim]",
        f"  ✓ approved {ok} · ⚑ flagged {flagged} · ◻ unreviewed {unrev}  (of {len(secs)} sections)",
        "",
    ]
    if flagged:
        lines.append("[bold]Flagged — the owner wants these changed before build:[/bold]")
        for s in open_flags(signoff):
            note = f" — {s['note']}" if s["note"] else " — [dim](no note)[/dim]"
            lines.append(f"  ⚑ {s['title']}{note}")
        lines.append("")
    if unrev:
        titles = ", ".join(s["title"] for s in secs if s["status"] == "unreviewed")
        lines.append(f"[yellow]Not yet reviewed:[/yellow] {titles}")
    if not flagged and not unrev:
        lines.append("[green]✓ fully signed off — every section approved.[/green]")
    return "\n".join(lines)
