# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``startd8 kickoff-panel`` CLI — the read-only viewer over a facilitated-panel transcript.

Follow the facilitated kickoff panel round-by-round and role-by-role for
validation-by-observation and inspiration. **Observe only** — no scoring, acceptance, or
write-back (mirrors the facilitation design §8). A thin front door over the same
``KickoffViewService`` any TUI surface would drive (no logic fork).

Exit codes: 0 ok; 2 bad input (no such session / no sessions).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .cli_shared import console

kickoff_panel_app = typer.Typer(
    name="kickoff-panel",
    help="View a facilitated kickoff-panel transcript by round and by role (read-only).",
)

_EXIT_BAD_INPUT = 2


def _service(project: Optional[Path]):
    from .kickoff_view import KickoffViewService

    return KickoffViewService(str(project) if project else ".")


def _resolve_session_or_exit(service, session_id: Optional[str]) -> str:
    """Return an explicit session id, or fall back to the newest; exit 2 if none exist."""
    if session_id:
        return session_id
    latest = service.latest_session_id()
    if not latest:
        console.print(
            "[red]kickoff-panel:[/red] no transcripts under .startd8/kickoff-panel/"
        )
        raise typer.Exit(_EXIT_BAD_INPUT)
    return latest


@kickoff_panel_app.command("list")
def kickoff_list(
    project: Optional[Path] = typer.Option(
        None, "--project", help="Project root (default: cwd)."
    ),
) -> None:
    """List saved kickoff-panel session ids (newest first)."""
    service = _service(project)
    ids = service.list_sessions()
    if not ids:
        console.print("[dim]no kickoff-panel sessions yet.[/dim]")
        return
    for sid in ids:
        console.print(sid)


@kickoff_panel_app.command("show")
def kickoff_show(
    session_id: Optional[str] = typer.Argument(
        None, help="Session id (default: newest)."
    ),
    by_role: bool = typer.Option(
        False, "--by-role", help="Group by role instead of by round."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the raw transcript JSON."
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", help="Project root (default: cwd)."
    ),
) -> None:
    """Print a kickoff-panel transcript to stdout (round-major, or --by-role)."""
    service = _service(project)
    sid = _resolve_session_or_exit(service, session_id)
    try:
        transcript = service.load(sid)
    except FileNotFoundError:
        console.print(f"[red]kickoff-panel:[/red] no such session: {sid}")
        raise typer.Exit(_EXIT_BAD_INPUT)
    if json_out:
        console.print(transcript.model_dump_json(indent=2))
    else:
        from .kickoff_view import render_text

        console.print(render_text(transcript, by_role=by_role))


@kickoff_panel_app.command("view")
def kickoff_view_cmd(
    session_id: Optional[str] = typer.Argument(
        None, help="Session id (default: newest)."
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output HTML path (default: <transcript>.view.html)."
    ),
    open_browser: bool = typer.Option(
        False, "--open", help="Open the page in a browser."
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", help="Project root (default: cwd)."
    ),
) -> None:
    """Render a kickoff-panel transcript as a standalone HTML viewer (offline, $0)."""
    from .kickoff_view import render_html

    service = _service(project)
    sid = _resolve_session_or_exit(service, session_id)
    try:
        transcript = service.load(sid)
    except FileNotFoundError:
        console.print(f"[red]kickoff-panel:[/red] no such session: {sid}")
        raise typer.Exit(_EXIT_BAD_INPUT)

    target = out or (service.store.root / f"{sid}.view.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(transcript), encoding="utf-8")
    console.print(f"[green]kickoff-panel view:[/green] {target}")
    if open_browser:
        import webbrowser

        webbrowser.open(target.resolve().as_uri())
