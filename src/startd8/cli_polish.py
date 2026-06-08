"""`startd8 polish` — make a structurally-complete app presentable (deterministic, $0).

Applies a curated, accessible design system (Tier 1) to a target project's generated UI: a real
mounted stylesheet built from design tokens, restyling the existing Jinja2/HTMX templates with a
WCAG 2.2 AA baseline. No LLM, no skill to install — the SDK ships the design knowledge internally.

The UX speaks in outcomes ("apply a polished, accessible theme"), not mechanism (FR-7). Subcommands:
``apply`` (write the polish), ``themes`` (list presets), ``check`` (audit drift, write nothing).
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .presentation_polish import (
    PolishConfig,
    apply_polish,
    get_theme,
    theme_names,
)
from .presentation_polish.engine import DEFAULT_THEME, FileStatus

console = Console()

polish_app = typer.Typer(
    help="Make a built app presentable: apply an accessible design theme ($0)."
)

_EXIT_OK = 0
_EXIT_DRIFT = 1
_EXIT_ERROR = 2


@polish_app.callback()
def _polish_callback() -> None:
    """Deterministic, $0 presentation polish for generated all-Python apps."""
    # Callback presence keeps this a command *group* (subcommand required).


def _run(project: Path, theme: str, check: bool) -> None:
    try:
        get_theme(theme)  # validate early with a friendly message
    except KeyError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(_EXIT_ERROR)
    try:
        result = apply_polish(
            PolishConfig(project_root=project, theme=theme, check=check)
        )
    except NotADirectoryError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(_EXIT_ERROR)

    # OTel telemetry at the CLI boundary (FR-23) — no-op when OTel is unavailable; never raises.
    from .presentation_polish.telemetry import record_polish

    record_polish(result, check=check)

    for relpath, status in result.files:
        color = {
            FileStatus.CREATED: "green",
            FileStatus.UPDATED: "green",
            FileStatus.UNCHANGED: "dim",
            FileStatus.SKIPPED_USER_OWNED: "yellow",
            FileStatus.DRIFT: "yellow",
            FileStatus.MISSING: "yellow",
        }.get(status, "white")
        console.print(f"  [{color}]{status.value}[/{color}]: {relpath}")

    for skipped in result.skipped_user_owned:
        console.print(
            f"[yellow]note[/yellow]: kept your edits to {skipped} (no polish marker); "
            "delete it to let polish manage it again."
        )

    if check:
        if result.has_drift:
            console.print(
                "[yellow]polish drift[/yellow]: re-run `startd8 polish apply` to refresh."
            )
            raise typer.Exit(_EXIT_DRIFT)
        console.print("[green]in_sync[/green]: polish is up to date.")
        raise typer.Exit(_EXIT_OK)

    console.print(
        f"[green]done[/green]: theme '[bold]{result.theme}[/bold]' applied; cost=$0.00. "
        "Re-run `generate backend` first if the stylesheet link isn't loading."
    )


@polish_app.command("apply")
def apply(
    project: Path = typer.Option(
        ..., "--project", help="Target project root (contains app/)."
    ),
    theme: str = typer.Option(
        DEFAULT_THEME,
        "--theme",
        help=f"Theme preset. Options: {', '.join(theme_names())}.",
    ),
) -> None:
    """Apply the design system to the project's generated UI (writes the stylesheet + static mount)."""
    _run(project, theme, check=False)


@polish_app.command("check")
def check(
    project: Path = typer.Option(
        ..., "--project", help="Target project root (contains app/)."
    ),
    theme: str = typer.Option(DEFAULT_THEME, "--theme", help="Theme to check against."),
) -> None:
    """Audit polish drift without writing. Exit 0=in-sync, 1=drift, 2=error."""
    _run(project, theme, check=True)


@polish_app.command("themes")
def themes() -> None:
    """List the available curated themes."""
    table = Table(title="Presentation Polish — themes")
    table.add_column("name", style="bold")
    table.add_column("description")
    for name in theme_names():
        t = get_theme(name)
        default = " [dim](default)[/dim]" if name == DEFAULT_THEME else ""
        table.add_row(name + default, t.label)
    console.print(table)
