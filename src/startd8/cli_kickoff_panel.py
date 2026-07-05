# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``startd8 kickoff-panel`` CLI — the read-only viewer over a facilitated-panel transcript.

Follow the facilitated kickoff panel round-by-round and role-by-role for
validation-by-observation and inspiration. **Observe only** — no scoring, acceptance, or
write-back (mirrors the facilitation design §8). A thin front door over the same
``KickoffViewService`` any TUI surface would drive (no logic fork).

``--watch`` live-follows an in-progress run (FR-UX-17/18): ``show --watch`` re-renders the
terminal on each landed round; ``view --watch`` re-writes an auto-refreshing HTML file so an
open browser updates itself. No server — the orchestrator writes the transcript atomically
round-by-round, so a poll-and-diff loop suffices (FR-UX-19).

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


def _load_or_exit(service, session_id: str):
    try:
        return service.load(session_id)
    except FileNotFoundError:
        console.print(f"[red]kickoff-panel:[/red] no such session: {session_id}")
        raise typer.Exit(_EXIT_BAD_INPUT)


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
    watch: bool = typer.Option(
        False,
        "--watch",
        "--follow",
        help="Live-follow: re-render on each landed round.",
    ),
    interval: float = typer.Option(
        2.0, "--interval", help="Watch poll interval (seconds)."
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", help="Project root (default: cwd)."
    ),
) -> None:
    """Print a kickoff-panel transcript to stdout (round-major, or --by-role)."""
    from .kickoff_view import render_text

    service = _service(project)
    sid = _resolve_session_or_exit(service, session_id)

    if watch and not json_out:
        _resolve_session_or_exit(service, sid)  # ensure the dir has it (or exit 2)
        watcher = service.watcher(sid, interval=interval)

        def _render(transcript) -> None:
            console.clear()
            console.print(f"[dim]watching {sid} — Ctrl-C to stop[/dim]\n")
            console.print(render_text(transcript, by_role=by_role))

        try:
            final = watcher.follow(_render)
        except KeyboardInterrupt:
            console.print("\n[dim]kickoff-panel: stopped watching.[/dim]")
            return
        if final is None:
            console.print(f"[red]kickoff-panel:[/red] no such session: {sid}")
            raise typer.Exit(_EXIT_BAD_INPUT)
        state = "halted" if final.is_halted else "complete"
        console.print(f"\n[green]kickoff-panel:[/green] run {state}.")
        return

    transcript = _load_or_exit(service, sid)
    if json_out:
        console.print(transcript.model_dump_json(indent=2))
    else:
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
    watch: bool = typer.Option(
        False,
        "--watch",
        "--follow",
        help="Live-follow: re-write an auto-refreshing page as rounds land.",
    ),
    interval: float = typer.Option(
        2.0, "--interval", help="Watch poll / browser-refresh interval (seconds)."
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", help="Project root (default: cwd)."
    ),
) -> None:
    """Render a kickoff-panel transcript as a standalone HTML viewer (offline, $0)."""
    from .kickoff_view import render_html

    service = _service(project)
    sid = _resolve_session_or_exit(service, session_id)
    target = out or (service.store.root / f"{sid}.view.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    refresh_secs = max(1, round(interval))

    def _write(transcript) -> None:
        secs = None if transcript.is_done else refresh_secs
        target.write_text(
            render_html(transcript, live_reload_secs=secs), encoding="utf-8"
        )

    if watch:
        watcher = service.watcher(sid, interval=interval)
        opened = {"done": False}

        def _on_change(transcript) -> None:
            _write(transcript)
            console.print(
                f"[green]kickoff-panel:[/green] rendered {len(transcript.rounds)} round(s) → {target}"
            )
            if open_browser and not opened["done"]:
                import webbrowser

                webbrowser.open(target.resolve().as_uri())
                opened["done"] = True

        try:
            final = watcher.follow(_on_change)
        except KeyboardInterrupt:
            console.print("\n[dim]kickoff-panel: stopped watching.[/dim]")
            return
        if final is None:
            console.print(f"[red]kickoff-panel:[/red] no such session: {sid}")
            raise typer.Exit(_EXIT_BAD_INPUT)
        state = "halted" if final.is_halted else "complete"
        console.print(f"[green]kickoff-panel:[/green] run {state} — {target}")
        return

    transcript = _load_or_exit(service, sid)
    target.write_text(render_html(transcript), encoding="utf-8")
    console.print(f"[green]kickoff-panel view:[/green] {target}")
    if open_browser:
        import webbrowser

        webbrowser.open(target.resolve().as_uri())
