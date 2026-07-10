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


def _resolve_report(project: Optional[Path], session_id: Optional[str], source: str):
    """Load a TriageReport, auto-detecting the store (FR-6): a facilitation session (kickoff-panel) →
    ``build_triage``; an ask-all session (stakeholder-panel) → ``triage_ask_all``. Returns (report, sid)."""
    from .stakeholder_panel.synthesis_bridge import (
        build_triage,
        is_ask_all_session,
        list_ask_all_sessions,
        load_ask_all_session,
        triage_ask_all,
    )

    proj = project or Path(".")
    if source == "ask-all":
        use_ask_all = True
    elif source == "facilitation":
        use_ask_all = False
    elif session_id:  # auto with an explicit id → detect by which store has the file
        use_ask_all = is_ask_all_session(proj, session_id)
    else:  # auto, newest → prefer facilitation; fall back to ask-all only if no facilitation sessions
        use_ask_all = not _service(project).latest_session_id() and bool(list_ask_all_sessions(proj))

    if use_ask_all:
        answers, question = load_ask_all_session(proj, session_id)
        if not answers:
            console.print("[red]no ask-all session found[/red]")
            raise typer.Exit(1)
        sid = session_id or list_ask_all_sessions(proj)[0]
        return triage_ask_all(answers, session_id=sid, question=question), sid

    service = _service(project)
    sid = _resolve_session_or_exit(service, session_id)
    return build_triage(_load_or_exit(service, sid)), sid


@kickoff_panel_app.command("triage")
def kickoff_triage(
    session_id: Optional[str] = typer.Argument(
        None, help="Session id (default: newest)."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the triage report as JSON."),
    project: Optional[Path] = typer.Option(
        None, "--project", help="Project root (default: cwd)."
    ),
    source: str = typer.Option(
        "auto", "--source", help="Session store: auto | facilitation | ask-all."),
) -> None:
    """Triage a panel session into a typed routing report ($0, read-only).

    Auto-detects the source: a multi-round **facilitation** synthesis (sectioned) or a single-question
    **ask-all** (one role-tagged candidate per persona answer). NON-DECIDABLE items get a reason + owner;
    FIELD-LEVEL items (an allow-listed ``entity.field``) are flagged for a VIPP ``capture`` proposal.
    Nothing is silently dropped.
    """
    import json as _json

    report, _sid = _resolve_report(project, session_id, source)
    if json_out:
        console.print_json(_json.dumps(report.to_dict()))
    else:
        console.print(report.to_markdown())


@kickoff_panel_app.command("backlog")
def kickoff_backlog(
    session_id: Optional[str] = typer.Argument(None, help="Session id (default: newest)."),
    project: Optional[Path] = typer.Option(None, "--project", help="Project root (default: cwd)."),
    out: Optional[Path] = typer.Option(None, "--out", help="Write the backlog section to a NEW file."),
    append: Optional[Path] = typer.Option(
        None, "--append", help="Guard-append into an EXISTING backlog doc (preview unless --yes)."),
    yes: bool = typer.Option(False, "--yes", help="With --append: actually write (else preview + diff)."),
    source: str = typer.Option(
        "auto", "--source", help="Session store: auto | facilitation | ask-all."),
) -> None:
    """Fold a panel session into a requirements-backlog section ($0, deterministic).

    Auto-detects a facilitation synthesis or a single-question ask-all. Default prints the section;
    ``--out FILE`` writes a new file; ``--append FILE`` guard-appends into an existing
    ``ENHANCEMENTS_BACKLOG.md`` (idempotent by session marker, append-only, atomic, fail-closed) —
    without ``--yes`` it previews and exits 0 (in sync) or 2 (a write is pending).
    """
    from .stakeholder_panel.synthesis_bridge import (
        BacklogAppendError,
        append_backlog,
        render_backlog_section,
    )

    report, sid = _resolve_report(project, session_id, source)
    section = render_backlog_section(report, project=str(project or ""))

    if not section.strip():
        console.print("[yellow]No candidates — nothing to fold into the backlog.[/yellow]")
        raise typer.Exit(0)

    if append is not None:
        try:
            result = append_backlog(Path(append), section, sid, confirm=yes)
        except BacklogAppendError as exc:
            console.print(f"[red]append refused (fail-closed):[/red] {exc}")
            raise typer.Exit(2)
        if result.action == "written":
            console.print(f"[green]appended[/green] backlog block for {sid} → {append}")
            raise typer.Exit(0)
        if result.action == "no-op":
            console.print(f"[dim]in sync[/dim] — {result.reason}")
            raise typer.Exit(0)
        # would-write (preview): show it and signal drift via exit 2 (polish-check style, H-21)
        console.print(f"[yellow]would write[/yellow] a backlog block for {sid} → {append} "
                      f"(re-run with --yes). Preview:\n")
        console.print(section)
        raise typer.Exit(2)

    if out is not None:
        Path(out).write_text(section, encoding="utf-8")
        console.print(f"[green]wrote[/green] backlog section → {out}")
        raise typer.Exit(0)

    console.print(section)
