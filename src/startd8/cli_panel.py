# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""panel CLI command group — query the live Stakeholder Panel (FR-8).

``list`` is ``$0``/read-only (just reads the roster). ``ask`` / ``ask-all`` are the **paid** surface
and, per OQ-7/NR-7, live here on the CLI (the only spend-authorized path) — never on the ``$0``
Concierge read floor. Every synthetic answer is rendered with an "unratified" banner so it is never
mistaken for a ratified fact (FR-19). Exit codes: 0 advisory; 2 unreadable/invalid roster.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from .cli_shared import console

panel_app = typer.Typer(
    name="panel",
    help="Query the synthetic stakeholder panel: list (read-only), ask/ask-all (paid, synthetic).",
)

_EXIT_FATAL_INPUTS = 2
_ROSTER_REL = Path("docs") / "kickoff" / "inputs" / "stakeholders.yaml"


def _emit_json(result) -> None:
    import sys

    sys.stdout.write(json.dumps(result, indent=2) + "\n")


def _roster_path(project_root: Path) -> Path:
    return project_root / _ROSTER_REL


def _load_or_exit(project_root: Path):
    """Load + validate the roster or exit(2) with a readable message."""
    from .stakeholder_panel import RosterError, load_roster, validate_roster

    path = _roster_path(project_root)
    if not path.is_file():
        console.print(
            f"[red]panel:[/red] no roster at {path} — run `startd8 concierge instantiate-kickoff` first."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    try:
        roster = load_roster(path)
    except RosterError as exc:
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    issues = validate_roster(roster)
    if issues:
        console.print("[red]panel:[/red] roster is invalid:")
        for issue in issues:
            console.print(f"  - {issue}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    return roster


def _render_answer(answer) -> None:
    """Print one answer with a persistent synthetic/unratified banner (FR-19)."""
    from .stakeholder_panel.models import Grounding

    head = f"[bold]{answer.role_id}[/bold] [dim]({answer.grounding.value})[/dim]"
    console.print(head)
    console.print(f"  {answer.text}")
    if answer.grounding is Grounding.UNAVAILABLE:
        console.print(
            "  [yellow]⚠ stakeholder unavailable — no answer produced[/yellow]"
        )
    else:
        console.print(
            "  [yellow]⚠ SYNTHETIC, UNRATIFIED[/yellow] — a role-played stand-in, not a real "
            "stakeholder. Confirm with a human before relying on it."
        )
    if answer.cost_usd:
        console.print(f"  [dim]cost ${answer.cost_usd:.5f} · {answer.model}[/dim]")


@panel_app.command("list")
def panel_list(
    project_root: Path = typer.Argument(
        Path("."), help="Project root (default: current dir)."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit roster JSON to stdout."),
) -> None:
    """List the personas on the roster ($0, read-only — no LLM)."""
    roster = _load_or_exit(project_root)
    if json_out:
        _emit_json(roster.to_dict())
        return
    console.print(
        f"[bold]Stakeholder panel roster[/bold] — {_roster_path(project_root)}"
    )
    for p in roster.personas:
        console.print(
            f"  [bold]{p.role_id}[/bold] — {p.display_name} ({len(p.goals)} goals)"
        )


@panel_app.command("ask")
def panel_ask(
    role_id: str = typer.Option(
        ..., "--role", help="The persona to ask (a roster role_id)."
    ),
    question: str = typer.Argument(..., help="The question to pose."),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    model: Optional[str] = typer.Option(
        None, "--model", help="Agent spec (default: SDK cheap model)."
    ),
) -> None:
    """Ask ONE persona a question (paid). The answer is synthetic, unratified input."""
    roster = _load_or_exit(project_root)
    from .stakeholder_panel import UnknownPersonaError
    from .stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel

    panel = StakeholderPanel(
        roster, project_root=project_root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        answer = asyncio.run(panel.ask(role_id, question))
    except UnknownPersonaError as exc:
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    finally:
        panel.close()
    _render_answer(answer)


@panel_app.command("ask-all")
def panel_ask_all(
    question: str = typer.Argument(..., help="The question to pose to every persona."),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    cap: Optional[int] = typer.Option(
        None, "--cap", help="Max personas to actually query (FR-17)."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Agent spec (default: SDK cheap model)."
    ),
) -> None:
    """Ask EVERY persona the same question (paid, bounded by --cap)."""
    roster = _load_or_exit(project_root)
    from .stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel

    panel = StakeholderPanel(
        roster, project_root=project_root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        answers = asyncio.run(panel.ask_all(question, cap=cap))
    finally:
        panel.close()
    for answer in answers:
        _render_answer(answer)
    total = sum(a.cost_usd for a in answers)
    if total:
        console.print(
            f"[dim]total cost ${total:.5f} across {len(answers)} personas[/dim]"
        )
