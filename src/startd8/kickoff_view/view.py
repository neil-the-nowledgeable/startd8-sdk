"""Render surfaces over a kickoff-panel transcript (FR-UX-4..23).

Two renderers over the **same** graceful-optional read model, mirroring
:mod:`startd8.consultation.view`:

* :func:`render_html` — a standalone, offline, dependency-free HTML viewer with two-axis
  (round × role) navigation. ``serve is None`` today (static only); the byte-identity seam is
  kept so a served mode can be added later without changing the static output.
* :func:`render_text` — a plain-text dump for ``startd8 kickoff-panel show`` (no rich dep).

**Security (FR-UX-22):** all transcript text is untrusted. The embedded JSON neutralizes ``<``
so a ``</script>`` inside any answer cannot break out of the ``<script type=application/json>``
container; the client template escapes-then-Markdown-renders (the exact consult helpers).
"""

from __future__ import annotations

import json
from typing import Optional

from ._webview_template import WEBVIEW_TEMPLATE
from .models import KickoffTranscript, PanelEntry, PanelRound, model_family


# ── payload (only the fields the client renderer reads) ──
def _entry_payload(t: KickoffTranscript, entry: PanelEntry) -> dict:
    d: dict = {
        "role_id": entry.role_id,
        "display_name": entry.display_name or entry.role_id,
        "model": entry.model,
        "family": entry.family,
        "grounding": entry.grounding or "",
        "flags": list(entry.flags),
        "is_adversary": t.is_adversary(entry.role_id),
        "text": entry.text or "",
    }
    if entry.prompt:
        d["prompt"] = entry.prompt
    for field in ("input_tokens", "output_tokens", "cost_usd"):
        val = getattr(entry, field, None)
        if val is not None:
            d[field] = val
    return d


def _round_payload(t: KickoffTranscript, rnd: PanelRound) -> dict:
    return {
        "round_id": rnd.round_id,
        "title": rnd.title,
        "kind": rnd.kind,
        "entry_count": len(rnd.entries),
        "entries": [_entry_payload(t, e) for e in rnd.entries],
    }


def _session_payload(t: KickoffTranscript) -> dict:
    prep = None
    if t.prep is not None and not t.prep.is_empty():
        prep = {
            "grounded_context": t.prep.grounded_context,
            "key_assumptions": t.prep.key_assumptions,
            "outside_view": t.prep.outside_view,
        }
    synthesis = None
    if t.synthesis is not None and (t.synthesis.text or t.synthesis.open_tension_ids):
        synthesis = {
            "model": t.synthesis.model,
            "text": t.synthesis.text,
            "open_tension_ids": list(t.synthesis.open_tension_ids),
            "smoothed_tension_ids": list(t.synthesis.smoothed_tension_ids),
            "raw_tension_ids": list(t.synthesis.raw_tension_ids),
        }
    return {
        "session_id": t.session_id,
        "project": t.project,
        "objective": t.objective,
        "strategy": t.strategy,
        "created_at": t.created_at or "",
        "facilitator_model": t.facilitator_model,
        "facilitator_family": model_family(t.facilitator_model),
        "status": t.status or "",
        "halt": t.halt,
        "is_halted": t.is_halted,
        "cost_total_usd": t.cost_total_usd,
        "roster_size": t.roster_size,
        "family_distribution": t.family_distribution(),
        "model_assignment": dict(t.model_assignment),
        "adversaries": list(t.adversaries),
        "active_round": t.active_round_id(),
        "prep": prep,
        "rounds": [_round_payload(t, r) for r in t.rounds],
        "synthesis": synthesis,
    }


def _embed_json(obj) -> str:
    """JSON safe to embed in a ``<script type=application/json>`` block (escape ``<``, FR-UX-22)."""
    return json.dumps(obj, ensure_ascii=True).replace("<", "\\u003c")


def _inject_live(html: str, secs: int, t: KickoffTranscript) -> str:
    """Add a browser-side auto-refresh + a LIVE banner for ``--watch`` (FR-UX-17).

    No server: a ``<meta http-equiv="refresh">`` reloads the (re-rendered) file every ``secs``
    seconds. Applied only in watch mode — the non-watch static output is untouched.
    """
    from html import escape

    meta = f'<meta http-equiv="refresh" content="{int(secs)}">'
    html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + meta, 1)
    active = t.active_round_id()
    tail = f" · filling {escape(active)}" if active else ""
    landed = len(t.rounds)
    banner = (
        '<div class="live-banner"><span class="pulse"></span>● LIVE — following '
        f"{escape(t.session_id)} · {landed} round(s) landed · status {escape(t.status or 'in_progress')}{tail}"
        "</div>"
    )
    return html.replace('<div class="wrap">', banner + '\n<div class="wrap">', 1)


def render_html(
    transcript: KickoffTranscript,
    serve: Optional[dict] = None,
    live_reload_secs: Optional[int] = None,
) -> str:
    """Render the standalone two-axis HTML viewer over a transcript (FR-UX-4..23).

    ``serve is None`` and ``live_reload_secs is None`` ⇒ the static offline file (the default
    surface), byte-identical to the no-arg call. The single ``__SESSION_JSON__`` substitution is
    escape-first (FR-UX-22). ``live_reload_secs`` (``--watch``) injects a meta-refresh + LIVE
    banner so an open browser auto-updates as the orchestrator lands rounds (FR-UX-17); when a
    served mode is later added it must keep the ``serve is None`` static byte-identity guarantee.
    """
    html = WEBVIEW_TEMPLATE.replace(
        "__SESSION_JSON__", _embed_json(_session_payload(transcript))
    )
    if live_reload_secs and live_reload_secs > 0:
        html = _inject_live(html, live_reload_secs, transcript)
    if serve is None:
        return html
    # Reserved for a future served mode (read-only, loopback) — pre-specified, not built.
    return html


# ── plain-text surface (CLI ``show``) ──
def _fmt_cost(value: Optional[float]) -> str:
    """FR-UX-23: render cost only when present and non-zero; else 'not recorded'."""
    if value is None or value == 0.0:
        return "not recorded"
    return f"${value:.4f}"


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …[truncated]"


def render_text(
    transcript: KickoffTranscript, *, by_role: bool = False, max_chars: int = 800
) -> str:
    """Plain-text dump of a transcript — round-major (default) or role-major (``by_role``)."""
    t = transcript
    lines: list[str] = []
    lines.append(
        "⚠ SYNTHETIC PANEL — persona outputs are unratified; for human judgment only."
    )
    lines.append("")
    header = f"Kickoff panel {t.session_id or '(no id)'} — project {t.project or '(unknown)'}"
    lines.append(header)
    if t.objective:
        lines.append(f"objective : {t.objective}")
    if t.strategy:
        lines.append(f"strategy  : {t.strategy}")
    fam = ", ".join(f"{k}×{v}" for k, v in sorted(t.family_distribution().items()))
    lines.append(f"roster    : {t.roster_size} personas ({fam or 'n/a'})")
    if t.adversaries:
        lines.append(f"adversaries: {', '.join(t.adversaries)}")
    lines.append(f"cost      : {_fmt_cost(t.cost_total_usd)}")
    lines.append("")

    if t.prep is not None and not t.prep.is_empty():
        lines.append("── Prep (R0) ──")
        if t.prep.grounded_context:
            lines.append(
                f"  grounded context : {_truncate(t.prep.grounded_context, 300)}"
            )
        if t.prep.key_assumptions:
            lines.append(
                f"  key assumptions  : {_truncate(t.prep.key_assumptions, 300)}"
            )
        if t.prep.outside_view:
            lines.append(f"  outside view     : {_truncate(t.prep.outside_view, 300)}")
        lines.append("")

    if t.is_halted:
        reason = (
            (t.halt or {}).get("message")
            or (t.halt or {}).get("reason")
            or "premise not validated"
        )
        lines.append(f"⛔ PANEL HALTED after R0: {reason}")
        lines.append("   (validate the premise first — no rounds were run.)")
        return "\n".join(lines)

    def render_entry(entry: PanelEntry, indent: str = "  ") -> None:
        adv = " [ADVERSARY]" if t.is_adversary(entry.role_id) else ""
        ground = f" · {entry.grounding}" if entry.grounding else ""
        flags = f" · flags={','.join(entry.flags)}" if entry.flags else ""
        name = entry.display_name or entry.role_id
        lines.append(
            f"{indent}▸ {name} [{entry.model}·{entry.family}]{adv}{ground}{flags}"
        )
        for para in _truncate(entry.text, max_chars).splitlines():
            lines.append(f"{indent}  {para}")

    if by_role:
        # Role-major: one thread per persona across rounds (FR-UX-5), same records re-pivoted.
        by_role_map: dict[str, list[tuple[PanelRound, PanelEntry]]] = {}
        for rnd, entry in t.all_entries():
            by_role_map.setdefault(entry.role_id, []).append((rnd, entry))
        for role_id, pairs in by_role_map.items():
            name = pairs[0][1].display_name or role_id
            adv = " [ADVERSARY]" if t.is_adversary(role_id) else ""
            lines.append(
                f"══ {name} [{pairs[0][1].model}·{pairs[0][1].family}]{adv} ══"
            )
            for rnd, entry in pairs:
                lines.append(f"  {rnd.round_id} · {rnd.title}")
                for para in _truncate(entry.text, max_chars).splitlines():
                    lines.append(f"    {para}")
            lines.append("")
    else:
        # Round-major (default): entries grouped under each round (FR-UX-4).
        active = t.active_round_id()
        for rnd in t.rounds:
            progress = f" ({len(rnd.entries)}/{t.roster_size or len(rnd.entries)})"
            fill = "  ◀ filling" if rnd.round_id == active else ""
            lines.append(
                f"══ {rnd.round_id} · {rnd.title} [{rnd.kind}]{progress}{fill} ══"
            )
            for entry in rnd.entries:
                render_entry(entry)
            lines.append("")
        if active and active not in {r.round_id for r in t.rounds}:
            lines.append(f"…awaiting {active} (status {t.status or 'in_progress'})")
            lines.append("")

    if t.synthesis is not None and t.synthesis.text:
        lines.append("── Synthesis (R5) — needs your judgment ──")
        lines.append(_truncate(t.synthesis.text, 4000))
        if t.synthesis.open_tension_ids:
            lines.append("")
            lines.append(
                f"  unresolved tensions: {', '.join(t.synthesis.open_tension_ids)}"
            )
    return "\n".join(lines)
