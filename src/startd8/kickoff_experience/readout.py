"""Shareable kickoff readout — the static-file parity of the terminal cockpit.

Turns an ephemeral kickoff session into a **self-contained, shareable document** (Markdown or
HTML) a founder can email a stakeholder or attach to a ticket. It renders the *same*
:class:`~startd8.kickoff_experience.agentic_view.AgenticView` read-model the Grafana board
(``build_workbook_v2``) and the terminal cockpit (``cockpit_view``) already render — one oracle,
so the three surfaces cannot drift (parity, FR-3). Read-only, ``$0``, no network, no writes: the
CLI (``kickoff readout``) does any file writing; these renderers are pure functions.

Mirrors the cockpit's section structure (Status / Assistant / Proposals) so the shared, printed
artifact reads like the live view.

Safety:

- **Markdown**: host-controlled cell content (a model-proposed ``value_path`` / summary / id) is
  neutralized with :func:`_md_cell` (the same pipe/backtick escaping the board uses) so it cannot
  break the table or the wrapping code span.
- **HTML (critical)**: *every* value that originates from the model / session / proposals
  (transcript text, proposal target/summary/id, next-step title/detail, project name) is passed
  through :func:`html.escape` before interpolation, so a planted ``<script>`` / ``<img onerror=…>``
  payload renders as inert text, never executable markup.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List

from . import schemas
from .session_snapshot import stop_reason_hint

#: Transcript turns rendered inline (matches the terminal cockpit's tail depth).
_TAIL = 12
_ROLE_LABEL = {"user": "you", "assistant": "assistant", "tool": "tool"}


# --------------------------------------------------------------------------- full (combined) readout


def build_full_readout(project_root: Any) -> Dict[str, Any]:
    """The combined ``startd8.kickoff.readout.v1`` payload: status + activation + retrospective.

    The richer, shareable single artifact = the current status oracle plus *how we got here*
    (retrospective) and *what's left* (activation). Built on the one dispatcher
    :func:`~startd8.kickoff_experience.report.kickoff_report`, so no view is re-derived here.
    Read-only, ``$0``. The default (non-``--full``) JSON stays byte-identical to ``status.v1``.
    """
    from .report import kickoff_report

    return {
        "schema": schemas.READOUT,
        "status": kickoff_report(project_root, "status"),
        "activation": kickoff_report(project_root, "activation"),
        "retrospective": kickoff_report(project_root, "retrospective"),
    }


# --------------------------------------------------------------------------- markdown escaping


def _md_cell(text: str) -> str:
    """Escape a value for a markdown table cell / wrapping code span (parity with portal_spec_v2).

    Pipes/newlines break the row; a backtick in host-controlled content would break the ```…```
    span the cell wraps it in — neutralize it to the modifier-letter apostrophe (display-only)."""
    return str(text).replace("|", "\\|").replace("\n", " ").replace("`", "ʼ")


def _project_name(view: Any) -> str:
    """A human-friendly project label from the view (snapshot project, else the root basename)."""
    snap = view.snapshot
    if snap is not None and getattr(snap, "project", ""):
        raw = str(snap.project)
    else:
        raw = str(view.project_root)
    # Prefer the last path component when the value looks like a path.
    tail = raw.rstrip("/").rsplit("/", 1)[-1]
    return tail or raw


# --------------------------------------------------------------------------- markdown


def _md_status(view: Any, lines: List[str]) -> None:
    lines.append("## Status\n")
    pct = view.readiness_percent()
    state = view.state
    if pct is not None and state is not None:
        c = state.attention_counts
        total = sum(c.values())
        lines.append(
            f"**{pct}% ready** — {c.get('ok', 0)} ok · {c.get('review', 0)} review · "
            f"{c.get('blocked', 0)} blocked · {c.get('backlog', 0)} backlog · {total} inputs\n"
        )
    else:
        lines.append("_No kickoff inputs yet — run `startd8 kickoff instantiate`._\n")

    na = view.next_action
    if na is not None:
        detail = getattr(na, "detail", "")
        line = f"➡️ **Next step:** {_md_cell(na.title)}"
        if detail:
            line += f"\n\n> {_md_cell(detail)}"
        lines.append(line + "\n")


def _md_assistant(view: Any, lines: List[str]) -> None:
    lines.append("## Assistant\n")
    if not view.has_snapshot:
        msg = view.assistant_message() or "No session yet — run `startd8 kickoff chat`."
        lines.append(f"_{_md_cell(msg)}_\n")
        return

    snap = view.snapshot
    lines.append(f"**Session at a glance:** {_md_cell(snap.at_a_glance())}\n")
    lines.append(f"_{_md_cell(snap.disclosure)} · {_md_cell(snap.cost_line())}_\n")
    hint = stop_reason_hint(getattr(snap, "stop_reason", None))
    if hint:
        lines.append(f"⏸ {_md_cell(hint)}\n")

    turns = list(snap.turns)
    hidden = max(0, len(turns) - _TAIL)
    if hidden:
        lines.append(f"_… {hidden} earlier turns omitted._\n")
    for t in turns[-_TAIL:]:
        label = _ROLE_LABEL.get(t.role, t.role)
        if t.role == "tool":
            body = f"[{_md_cell(t.tool_name or 'tool')}] {_md_cell(t.text or '(result)')}"
        else:
            calls = f"  _(→ {_md_cell(', '.join(t.tool_calls))})_" if t.tool_calls else ""
            body = f"{_md_cell(t.text or '(no text)')}{calls}"
        lines.append(f"**{label}:** {body}\n")


def _md_proposals(view: Any, lines: List[str]) -> None:
    lines.append("## Proposals\n")
    if not view.proposals:
        msg = view.proposals_message() or "No proposals awaiting confirmation."
        lines.append(f"_{_md_cell(msg)}_\n")
        return

    lines.append(
        "_The kickoff loop only **recommends** — you confirm every write. This document never "
        "acts; copy a command below to apply it at your own privilege._\n"
    )
    lines.append("| Kind | Target | Summary | ID |")
    lines.append("|---|---|---|---|")
    for r in view.proposals:
        lines.append(
            f"| {_md_cell(r.kind)} | `{_md_cell(r.target)}` | "
            f"{_md_cell(r.summary)} | `{_md_cell(r.id)}` |"
        )
    lines.append("\n**Confirm commands** (copy-paste to act on a proposal):\n")
    for r in view.proposals:
        lines.append(f"- `{_md_cell(r.id)}` ({_md_cell(r.kind)}):\n\n  ```\n  {r.confirm_command}\n  ```")


def _md_retrospective(retro: Dict[str, Any], lines: List[str]) -> None:
    """`--full`: "How it got here" — the journey milestones + adjudicated decision log."""
    lines.append("## How it got here\n")
    journey = retro.get("journey") or {}
    summary = retro.get("summary")
    if summary:
        lines.append(f"{_md_cell(summary)}\n")
    milestones = [m for m in (journey.get("milestones") or [])]
    if milestones:
        lines.append("**Journey milestones:**\n")
        for m in milestones:
            lines.append(f"- {_md_cell(m)}")
        lines.append("")
    else:
        lines.append("_No journey milestones recorded yet._\n")

    decisions = retro.get("decisions") or {}
    items = decisions.get("items") or []
    if items:
        lines.append("**Decision log:**\n")
        lines.append("| Proposal | Disposition | Rationale |")
        lines.append("|---|---|---|")
        for it in items:
            pid = it.get("proposal_id", "")
            disp = it.get("decision") or it.get("disposition") or ""
            why = it.get("rationale") or it.get("reason") or ""
            lines.append(f"| `{_md_cell(pid)}` | {_md_cell(disp)} | {_md_cell(why)} |")
        lines.append("")
    elif decisions.get("pending"):
        lines.append(f"_{decisions.get('pending')} decision(s) pending — none adjudicated yet._\n")


def _md_activation(activation: Dict[str, Any], lines: List[str]) -> None:
    """`--full`: "What's left" — the open activation conditions gating readiness."""
    lines.append("## What's left\n")
    overall = activation.get("overall", "unknown")
    ready = activation.get("ready", False)
    open_conditions = activation.get("open") or []
    if ready and not open_conditions:
        lines.append("✅ **Activated** — no open conditions. Nothing left blocking readiness.\n")
        return
    lines.append(
        f"**Status: {_md_cell(overall)}** — {len(open_conditions)} open condition(s) to clear.\n"
    )
    for c in open_conditions:
        title = _md_cell(c.get("title", c.get("key", "")))
        sev = _md_cell(c.get("severity", ""))
        line = f"- **[{sev}]** {title}"
        detail = c.get("detail")
        if detail:
            line += f"\n\n  > {_md_cell(detail)}"
        lines.append(line)
    lines.append("")


def render_markdown(view: Any, full: bool = False) -> str:
    """Render *view* as a complete, self-contained Markdown readout (Status / Assistant / Proposals).

    Pure, ``$0``, read-only. Host-controlled content is escaped via :func:`_md_cell`. When *full* is
    set, the standard readout is followed by two additive sections — "How it got here" (retrospective
    journey + decision log) and "What's left" (open activation conditions).
    """
    name = _md_cell(_project_name(view))
    lines: List[str] = [f"# Kickoff readout — {name}\n"]

    snap = view.snapshot
    if snap is not None and getattr(snap, "generated_at", ""):
        lines.append(f"_Generated {_md_cell(snap.generated_at)}._\n")
    disclosure = getattr(snap, "disclosure", None) if snap is not None else None
    lines.append(f"> _{_md_cell(disclosure or 'snapshot — not a live agent')}_\n")

    if view.state is None:
        lines.append("_No kickoff inputs yet._\n")

    _md_status(view, lines)
    _md_assistant(view, lines)
    _md_proposals(view, lines)
    _md_pipeline(view, lines)

    if full:
        from .report import kickoff_report

        _md_retrospective(kickoff_report(view.project_root, "retrospective"), lines)
        _md_activation(kickoff_report(view.project_root, "activation"), lines)
    return "\n".join(lines) + "\n"


def _md_pipeline(view: Any, lines: List[str]) -> None:
    """Convergence M1: the panel→bridge→VIPP funnel + stakeholders — only when there's activity."""
    pipe = view.pipeline_summary()
    stake = view.stakeholder_summary()
    if not pipe and not stake:
        return
    lines.append("## Pipeline & stakeholders\n")
    if stake:
        lines.append(f"**Stakeholders:** {_md_cell(stake)}\n")
    if pipe:
        lines.append(f"**Pipeline:** {_md_cell(pipe)}\n")


# --------------------------------------------------------------------------- html


def _e(text: Any) -> str:
    """Escape any model/session/proposal-originated value for safe HTML interpolation (XSS gate)."""
    return html.escape(str(text))


def _html_status(view: Any, out: List[str]) -> None:
    out.append("<section><h2>Status</h2>")
    pct = view.readiness_percent()
    state = view.state
    if pct is not None and state is not None:
        c = state.attention_counts
        total = sum(c.values())
        out.append(
            f"<p><strong>{pct}% ready</strong> — {c.get('ok', 0)} ok &middot; "
            f"{c.get('review', 0)} review &middot; {c.get('blocked', 0)} blocked &middot; "
            f"{c.get('backlog', 0)} backlog &middot; {total} inputs</p>"
        )
    else:
        out.append("<p class='muted'>No kickoff inputs yet — run "
                   "<code>startd8 kickoff instantiate</code>.</p>")

    na = view.next_action
    if na is not None:
        out.append(f"<p class='next'>➡️ <strong>Next step:</strong> {_e(na.title)}</p>")
        detail = getattr(na, "detail", "")
        if detail:
            out.append(f"<blockquote>{_e(detail)}</blockquote>")
    out.append("</section>")


def _html_assistant(view: Any, out: List[str]) -> None:
    out.append("<section><h2>Assistant</h2>")
    if not view.has_snapshot:
        msg = view.assistant_message() or "No session yet — run `startd8 kickoff chat`."
        out.append(f"<p class='muted'>{_e(msg)}</p></section>")
        return

    snap = view.snapshot
    out.append(f"<p><strong>Session at a glance:</strong> {_e(snap.at_a_glance())}</p>")
    out.append(f"<p class='muted'>{_e(snap.disclosure)} &middot; {_e(snap.cost_line())}</p>")
    hint = stop_reason_hint(getattr(snap, "stop_reason", None))
    if hint:
        out.append(f"<p class='stop'>⏸ {_e(hint)}</p>")

    turns = list(snap.turns)
    hidden = max(0, len(turns) - _TAIL)
    if hidden:
        out.append(f"<p class='muted'>… {hidden} earlier turns omitted.</p>")
    out.append("<div class='transcript'>")
    for t in turns[-_TAIL:]:
        label = _ROLE_LABEL.get(t.role, t.role)
        if t.role == "tool":
            body = f"[{_e(t.tool_name or 'tool')}] {_e(t.text or '(result)')}"
        else:
            calls = f" <em>(→ {_e(', '.join(t.tool_calls))})</em>" if t.tool_calls else ""
            body = f"{_e(t.text or '(no text)')}{calls}"
        out.append(f"<p class='turn {_e(t.role)}'><strong>{_e(label)}:</strong> {body}</p>")
    out.append("</div></section>")


def _html_proposals(view: Any, out: List[str]) -> None:
    out.append("<section><h2>Proposals</h2>")
    if not view.proposals:
        msg = view.proposals_message() or "No proposals awaiting confirmation."
        out.append(f"<p class='muted'>{_e(msg)}</p></section>")
        return

    out.append(
        "<p class='muted'>The kickoff loop only <strong>recommends</strong> — you confirm every "
        "write. This document never acts; copy a command below to apply it at your own privilege.</p>"
    )
    out.append("<table><thead><tr><th>Kind</th><th>Target</th><th>Summary</th><th>ID</th></tr>"
               "</thead><tbody>")
    for r in view.proposals:
        out.append(
            f"<tr><td>{_e(r.kind)}</td><td><code>{_e(r.target)}</code></td>"
            f"<td>{_e(r.summary)}</td><td><code>{_e(r.id)}</code></td></tr>"
        )
    out.append("</tbody></table>")
    out.append("<h3>Confirm commands</h3>")
    for r in view.proposals:
        out.append(
            f"<p><strong>{_e(r.id)}</strong> ({_e(r.kind)}):</p>"
            f"<pre><code>{_e(r.confirm_command)}</code></pre>"
        )
    out.append("</section>")


_HTML_STYLE = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 46rem;
       margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
h1 { font-size: 1.6rem; } h2 { border-bottom: 1px solid #ccc; padding-bottom: .2rem; }
.disclosure { font-style: italic; opacity: .8; }
.muted { opacity: .7; } .next { font-size: 1.05rem; }
blockquote { margin: .3rem 0 .8rem; padding-left: .8rem; border-left: 3px solid #ccc; opacity: .85; }
.stop { color: #a15c00; } .transcript .turn { margin: .3rem 0; }
table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #ccc;
       padding: .3rem .5rem; text-align: left; }
pre { background: #f4f4f4; padding: .6rem; overflow-x: auto; border-radius: 4px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
@media print { body { max-width: none; } }
""".strip()


def _html_retrospective(retro: Dict[str, Any], out: List[str]) -> None:
    """`--full`: "How it got here" — journey milestones + decision log. Every value escaped (XSS gate)."""
    out.append("<section><h2>How it got here</h2>")
    journey = retro.get("journey") or {}
    summary = retro.get("summary")
    if summary:
        out.append(f"<p>{_e(summary)}</p>")
    milestones = [m for m in (journey.get("milestones") or [])]
    if milestones:
        out.append("<p><strong>Journey milestones:</strong></p><ul>")
        for m in milestones:
            out.append(f"<li>{_e(m)}</li>")
        out.append("</ul>")
    else:
        out.append("<p class='muted'>No journey milestones recorded yet.</p>")

    decisions = retro.get("decisions") or {}
    items = decisions.get("items") or []
    if items:
        out.append("<p><strong>Decision log:</strong></p>")
        out.append("<table><thead><tr><th>Proposal</th><th>Disposition</th><th>Rationale</th>"
                   "</tr></thead><tbody>")
        for it in items:
            pid = it.get("proposal_id", "")
            disp = it.get("decision") or it.get("disposition") or ""
            why = it.get("rationale") or it.get("reason") or ""
            out.append(
                f"<tr><td><code>{_e(pid)}</code></td><td>{_e(disp)}</td><td>{_e(why)}</td></tr>"
            )
        out.append("</tbody></table>")
    elif decisions.get("pending"):
        out.append(f"<p class='muted'>{_e(decisions.get('pending'))} decision(s) pending — none "
                   "adjudicated yet.</p>")
    out.append("</section>")


def _html_activation(activation: Dict[str, Any], out: List[str]) -> None:
    """`--full`: "What's left" — the open activation conditions. Every value escaped (XSS gate)."""
    out.append("<section><h2>What&#39;s left</h2>")
    overall = activation.get("overall", "unknown")
    ready = activation.get("ready", False)
    open_conditions = activation.get("open") or []
    if ready and not open_conditions:
        out.append("<p>✅ <strong>Activated</strong> — no open conditions. Nothing left blocking "
                   "readiness.</p></section>")
        return
    out.append(
        f"<p><strong>Status: {_e(overall)}</strong> — {len(open_conditions)} open "
        "condition(s) to clear.</p><ul>"
    )
    for c in open_conditions:
        title = _e(c.get("title", c.get("key", "")))
        sev = _e(c.get("severity", ""))
        detail = c.get("detail")
        body = f"<strong>[{sev}]</strong> {title}"
        if detail:
            body += f"<blockquote>{_e(detail)}</blockquote>"
        out.append(f"<li>{body}</li>")
    out.append("</ul></section>")


def render_html(view: Any, full: bool = False) -> str:
    """Render *view* as a complete, standalone HTML document (no external assets, printable).

    Pure, ``$0``, read-only. **Every** model/session/proposal-originated value is escaped with
    :func:`html.escape`, so a planted ``<script>`` / ``<img onerror=…>`` payload is inert text.
    When *full* is set, two additive sections follow — "How it got here" (retrospective) and
    "What's left" (open activation conditions) — with the same escape gate on every value.
    """
    name = _e(_project_name(view))
    snap = view.snapshot
    generated = _e(snap.generated_at) if snap is not None and getattr(snap, "generated_at", "") else ""
    disclosure = _e(
        getattr(snap, "disclosure", None) if snap is not None else None
    ) if snap is not None and getattr(snap, "disclosure", None) else _e("snapshot — not a live agent")

    out: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Kickoff readout — {name}</title>",
        f"<style>{_HTML_STYLE}</style>",
        "</head>",
        "<body>",
        f"<h1>Kickoff readout — {name}</h1>",
    ]
    if generated:
        out.append(f"<p class='muted'>Generated {generated}.</p>")
    out.append(f"<p class='disclosure'>{disclosure}</p>")
    if view.state is None:
        out.append("<p class='muted'>No kickoff inputs yet.</p>")

    _html_status(view, out)
    _html_assistant(view, out)
    _html_proposals(view, out)
    _html_pipeline(view, out)

    if full:
        from .report import kickoff_report

        _html_retrospective(kickoff_report(view.project_root, "retrospective"), out)
        _html_activation(kickoff_report(view.project_root, "activation"), out)

    out.append("</body></html>")
    return "\n".join(out) + "\n"


def _html_pipeline(view: Any, out: List[str]) -> None:
    """Convergence M1: the panel→bridge→VIPP funnel + stakeholders — only when there's activity."""
    pipe = view.pipeline_summary()
    stake = view.stakeholder_summary()
    if not pipe and not stake:
        return
    out.append("<section><h2>Pipeline &amp; stakeholders</h2>")
    if stake:
        out.append(f"<p><strong>Stakeholders:</strong> {_e(stake)}</p>")
    if pipe:
        out.append(f"<p><strong>Pipeline:</strong> {_e(pipe)}</p>")
    out.append("</section>")
