# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""vipp CLI command group — VIPP (Very Important Project Person): the project-side counterpart.

The project-side negotiator/applier dual of the FDE. ``init`` opts the project in (creates the
``.startd8/vipp/`` posting so the host serializes pending proposals there); ``negotiate`` adjudicates
the host's proposal inbox against project ground truth ($0, deterministic) into a source-labeled
dispositions report; ``apply`` is **preview-by-default**, ``--apply`` to write accepted proposals at
the human's own privilege (each rendered for confirmation — FR-16).

Exit codes (FR-11): 0 advisory/in-sync · 1 drift · 2 unreadable/absent input · 3 a write was blocked
(confinement / stale-seq refusal).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .cli_shared import console

vipp_app = typer.Typer(
    name="vipp",
    help="VIPP: negotiate the host's onboarding proposals against project ground truth and "
    "apply accepted ones at project privilege (the project-side counterpart to the SDK Concierge).",
)

_EXIT_FATAL_INPUTS = 2
_EXIT_BLOCKED = 3
_EXIT_DRIFT = 1


def _sdk_version() -> str:
    try:
        from . import __version__

        return str(__version__)
    except Exception:
        return "0.0.0"


def _make_confirm(auto_yes: bool):
    """Build the FR-16 content-gate callback: render the concrete action, then confirm."""

    def confirm(action, disp) -> bool:
        reason = f" — {disp.reason}" if disp.reason else ""
        console.print(
            f"\n[bold]{disp.decision.value}[/bold] [cyan]{action.id}[/cyan] "
            f"([magenta]{action.kind}[/magenta]){reason}"
        )
        console.print(action.summary())  # the verbatim content the human is approving
        if auto_yes:
            console.print("[dim]--yes → auto-confirmed[/dim]")
            return True
        return typer.confirm("  Apply this proposal?", default=False)

    return confirm


@vipp_app.command("init")
def vipp_init(
    project_root: Optional[Path] = typer.Option(
        None, "--project-root", help="Project root (default: cwd)."
    ),
) -> None:
    """Opt the project into VIPP — create the ``.startd8/vipp/`` posting (the host then serializes here)."""
    from .vipp import context

    root = project_root or Path.cwd()
    path = context.ensure_posting(root, sdk_version=_sdk_version())
    console.print(f"[green]VIPP posting ready:[/green] {path}")
    console.print(
        "[dim]Opt-in active — the host now serializes pending proposals to "
        ".startd8/vipp/proposals-inbox.json. Then: `startd8 vipp negotiate` → `apply`.[/dim]"
    )


@vipp_app.command("negotiate")
def vipp_negotiate(
    project_root: Optional[Path] = typer.Option(
        None, "--project-root", help="Project root (default: cwd)."
    ),
    narrative: bool = typer.Option(
        False, "--narrative", help="Add an opt-in LLM prose narrative (off by default)."
    ),
    no_write: bool = typer.Option(
        False, "--no-write", help="Preview without writing dispositions."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-negotiate even if unchanged."
    ),
) -> None:
    """Adjudicate the host proposal inbox into a source-labeled dispositions report ($0, deterministic)."""
    import json

    from .concierge.safe_write import SafeWriteError
    from .kickoff_experience.vipp_seam import inbox_path, vipp_opted_in
    from .vipp import run_vipp_negotiate

    root = project_root or Path.cwd()
    ip = inbox_path(root)
    if not ip.exists():
        # OQ-8: a missing inbox is NOT an error for an already-opted-in project — that is the normal
        # "inbox-ready" state after `startd8 project init`. Only a project that never opted in is a
        # mis-use worth exit 2.
        if vipp_opted_in(root):
            console.print(
                "[green]VIPP: inbox-ready[/green] — no proposals to negotiate yet. A producer must "
                "serialize proposals first (`startd8 project init --proposals FILE`, or the host)."
            )
            raise typer.Exit(0)
        console.print(
            "[red]VIPP negotiate: not opted in[/red] — run `startd8 project init` "
            "(or `startd8 vipp init`) first, then serialize proposals."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    try:
        outcome = run_vipp_negotiate(
            ip, project_root=root, narrative=narrative, write=not no_write, force=force
        )
    except SafeWriteError as exc:  # confinement / symlink refusal
        console.print(f"[red]VIPP negotiate blocked:[/red] {exc}")
        raise typer.Exit(_EXIT_BLOCKED)
    except (
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:  # future-protocol / malformed inbox
        console.print(f"[red]VIPP negotiate: unreadable or invalid inbox —[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    rep = outcome.report
    c = rep.counts()
    if outcome.skipped:
        console.print(
            f"[dim]VIPP negotiate: inbox unchanged — no-op → {outcome.report_path}[/dim]"
        )
        return
    color = "yellow" if (c["REJECT"] or c["COUNTER"]) else "green"
    console.print(
        f"[{color}]VIPP negotiate: ACCEPT {c['ACCEPT']} · REJECT {c['REJECT']} · "
        f"COUNTER {c['COUNTER']}[/{color}] → {outcome.report_path}"
    )
    for d in rep.dispositions:
        reason = f" — {d.reason}" if d.reason else ""
        console.print(f"  • {d.decision.value} {d.proposal_id}{reason}")


@vipp_app.command("apply")
def vipp_apply(
    project_root: Optional[Path] = typer.Option(
        None, "--project-root", help="Project root (default: cwd)."
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Actually write (default: preview only)."
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Auto-confirm every proposal (non-interactive)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Apply even when fully consumed (re-run)."
    ),
) -> None:
    """Preview (default) or apply (``--apply``) the VIPP dispositions at project human privilege."""
    import json

    from .concierge.safe_write import SafeWriteError
    from .vipp import apply_dispositions, context
    from .vipp.assistant import DISPOSITIONS_JSON
    from .vipp.models import VippReport

    root = project_root or Path.cwd()
    disp_path = context.vipp_dir(root) / DISPOSITIONS_JSON
    if not disp_path.exists():
        console.print(
            "[red]VIPP apply: no dispositions[/red] — run `startd8 vipp negotiate` first."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if not apply:
        try:
            report = VippReport.from_json(disp_path.read_text(encoding="utf-8"))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            console.print(f"[red]VIPP apply: unreadable dispositions —[/red] {exc}")
            raise typer.Exit(_EXIT_FATAL_INPUTS)
        c = report.counts()
        console.print(
            f"[bold]VIPP apply — preview[/bold] (envelope_seq {report.envelope_seq}); "
            "pass [cyan]--apply[/cyan] to write at project privilege."
        )
        for d in report.dispositions:
            reason = f" — {d.reason}" if d.reason else ""
            console.print(f"  • {d.decision.value} {d.proposal_id}{reason}")
        console.print(
            f"[dim]{c['ACCEPT']} ACCEPT + {c['COUNTER']} COUNTER would be offered for confirm; "
            f"{c['REJECT']} REJECT skipped.[/dim]"
        )
        return

    try:
        res = apply_dispositions(root, confirm=_make_confirm(yes), force=force)
    except SafeWriteError as exc:  # confinement / symlink refusal
        console.print(f"[red]VIPP apply blocked:[/red] {exc}")
        raise typer.Exit(_EXIT_BLOCKED)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        console.print(f"[red]VIPP apply: unreadable inbox/dispositions —[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    if res.stale:
        console.print(f"[red]VIPP apply blocked (stale):[/red] {res.refused_reason}")
        raise typer.Exit(_EXIT_BLOCKED)
    if res.refused_reason:
        console.print(f"[red]VIPP apply: {res.refused_reason}[/red]")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    tail = " — inbox consumed" if res.inbox_shredded else ""
    console.print(f"[green]VIPP apply: {res.summary()}[/green]{tail}")
