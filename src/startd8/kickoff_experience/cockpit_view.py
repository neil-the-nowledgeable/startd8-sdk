"""Terminal parity view of the agentic cockpit (roadmap Tier 2).

The Grafana board (`build_workbook_v2`) and this terminal view derive from the **same**
:class:`~startd8.kickoff_experience.agentic_view.AgenticView` oracle (FR-3), so a user gets the
cockpit's value — readiness + next step (Status), the session at a glance + transcript tail
(Assistant), and the pending queue + copy-safe confirm commands (Proposals) — **without a running
Grafana**. Pure rendering, ``$0``, read-only (this view never acts — NR-2).

Kept presentation-only: all facts (`next_action`, `readiness_percent`, `snapshot.at_a_glance`,
`proposals[*].confirm_command`, `stop_reason`) come from the read-model, not recomputed here.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .session_snapshot import stop_reason_hint

#: Transcript turns rendered inline in the terminal (full depth lives in Grafana's Loki panel).
_TAIL = 12
_ROLE_LABEL = {"user": "you", "assistant": "assistant", "tool": "tool"}
_ROLE_STYLE = {"user": "blue", "assistant": "green", "tool": "dim"}


def _readiness_style(pct: int) -> str:
    return "bold green" if pct >= 80 else "bold yellow" if pct >= 40 else "bold red"


def _status_panel(view: Any) -> Panel:
    body = Text()
    pct = view.readiness_percent()
    state = view.state
    if pct is not None and state is not None:
        c = state.attention_counts
        total = sum(c.values())
        body.append(f"{pct}% ready", style=_readiness_style(pct))
        body.append(
            f"   {c.get('ok', 0)} ok · {c.get('review', 0)} review · "
            f"{c.get('blocked', 0)} blocked · {c.get('backlog', 0)} backlog · {total} inputs\n"
        )
    else:
        body.append("No kickoff inputs yet — run `startd8 kickoff instantiate`.\n", style="dim")

    na = view.next_action
    if na is not None:
        body.append("\n➡️  Next step: ", style="bold")
        body.append(str(na.title))
        detail = getattr(na, "detail", "")
        if detail:
            body.append(f"\n    {detail}", style="dim")
    return Panel(body, title="Status", border_style="cyan", title_align="left")


def _assistant_panel(view: Any) -> Panel:
    if not view.has_snapshot:
        msg = view.assistant_message() or "No session yet — run `startd8 kickoff chat`."
        return Panel(Text(msg, style="dim"), title="Assistant", border_style="magenta", title_align="left")

    snap = view.snapshot
    body = Text()
    body.append("Session at a glance: ", style="bold")
    body.append(snap.at_a_glance() + "\n")
    body.append(
        f"{snap.disclosure} · {snap.cost_line()} · generated {snap.generated_at}\n", style="dim"
    )
    hint = stop_reason_hint(getattr(snap, "stop_reason", None))
    if hint:
        body.append(f"⏸  {hint}\n", style="yellow")
    body.append("\n")

    turns = list(snap.turns)
    hidden = max(0, len(turns) - _TAIL)
    if hidden:
        body.append(
            f"… {hidden} earlier turns (full depth in the Grafana Loki panel)\n", style="dim"
        )
    for t in turns[-_TAIL:]:
        label = _ROLE_LABEL.get(t.role, t.role)
        style = _ROLE_STYLE.get(t.role, "white")
        body.append(f"{label}: ", style=f"bold {style}")
        if t.role == "tool":
            body.append(f"[{t.tool_name or 'tool'}] {t.text or '(result)'}\n", style="dim")
        else:
            calls = f"  (→ {', '.join(t.tool_calls)})" if t.tool_calls else ""
            body.append(f"{t.text or '(no text)'}{calls}\n")
    return Panel(body, title="Assistant", border_style="magenta", title_align="left")


def _proposals_panel(view: Any) -> Panel:
    if not view.proposals:
        msg = view.proposals_message() or "No proposals awaiting confirmation."
        return Panel(Text(msg, style="dim"), title="Proposals", border_style="yellow", title_align="left")

    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Kind")
    table.add_column("Target")
    table.add_column("Summary")
    table.add_column("ID", style="dim")
    for r in view.proposals:
        table.add_row(r.kind, r.target, r.summary, r.id)

    cmds = Text(
        "\nConfirm (copy-paste to apply — this view never acts; the CLI is the sole writer):\n",
        style="dim",
    )
    for r in view.proposals:
        cmds.append(f"  {r.id}: ", style="bold")
        cmds.append(f"{r.confirm_command}\n")
    return Panel(Group(table, cmds), title="Proposals", border_style="yellow", title_align="left")


def render_cockpit(view: Any) -> Group:
    """The three cockpit sections (Status / Assistant / Proposals) as a Rich renderable."""
    return Group(_status_panel(view), _assistant_panel(view), _proposals_panel(view))


def cockpit_to_text(view: Any, *, width: int = 100, color: bool = False) -> str:
    """Render the cockpit to a plain string (for tests, piping, and ``--plain``)."""
    console = Console(file=StringIO(), width=width, force_terminal=color, no_color=not color)
    console.print(render_cockpit(view))
    return console.file.getvalue()
