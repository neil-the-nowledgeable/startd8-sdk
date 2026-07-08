# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""panel CLI command group — query the live Stakeholder Panel (FR-8).

``list`` is ``$0``/read-only (just reads the roster). ``ask`` / ``ask-all`` are the **paid** surface
and, per OQ-7/NR-7, live here on the CLI (the only spend-authorized path) — never on the ``$0``
Concierge read floor. Every synthetic answer is rendered with an "unratified" banner so it is never
mistaken for a ratified fact (FR-19). ``import`` ingests an external persona format into a roster
($0, one-way). Exit codes: 0 ok; 1 runtime; 2 unreadable/invalid roster or unknown --format;
3 unreadable/malformed source; 4 round-trip-gate rejection; 5 clobber refused.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import List, Optional

import typer

from .cli_shared import console

panel_app = typer.Typer(
    name="panel",
    help="Query the synthetic stakeholder panel: list (read-only), ask/ask-all (paid, synthetic).",
)

# The stakeholder panel is a key part of the **Digital Project Workbook** (a dynamic, query-based
# evolution of Brooks' static workbook — "Why Did the Tower of Babel Fail?", The Mythical Man-Month). Its
# canonical surface is `startd8 kickoff stakeholders …`. Two hidden deprecated aliases stay reachable for
# one release: the old top-level `startd8 panel …` and the interim `startd8 kickoff panel …` (renamed to
# disambiguate from `startd8 kickoff portal`, the Grafana Workbook view). `panel_app` (above) is the
# clean group; the command bodies are re-registered on both deprecated apps at the bottom of this module.
panel_deprecated_app = typer.Typer(
    name="panel",
    help="[DEPRECATED — use `startd8 kickoff stakeholders`] Stakeholder-panel alias (works for one release).",
)


@panel_deprecated_app.callback()
def _panel_deprecated() -> None:
    """[DEPRECATED] Renamed to `startd8 kickoff stakeholders`. This alias works for one release."""
    import warnings
    from rich.console import Console as _Console

    warnings.warn(
        "`startd8 panel` is deprecated; use `startd8 kickoff stakeholders`. "
        "This alias will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    _Console(stderr=True).print(
        "[yellow]deprecation:[/yellow] `startd8 panel` is renamed to `startd8 kickoff stakeholders`; "
        "this alias works for one release."
    )


# Interim alias: `startd8 kickoff panel …` was canonical for one release before the rename to
# `stakeholders` (disambiguating it from `startd8 kickoff portal`, the Grafana Project Workbook view).
kickoff_panel_deprecated_app = typer.Typer(
    name="panel",
    help="[DEPRECATED — use `startd8 kickoff stakeholders`] Renamed (works for one release).",
)


@kickoff_panel_deprecated_app.callback()
def _kickoff_panel_deprecated() -> None:
    """[DEPRECATED] `kickoff panel` is renamed to `kickoff stakeholders`. Alias works for one release."""
    import warnings
    from rich.console import Console as _Console

    warnings.warn(
        "`startd8 kickoff panel` is renamed to `startd8 kickoff stakeholders`. "
        "This alias will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    _Console(stderr=True).print(
        "[yellow]deprecation:[/yellow] `startd8 kickoff panel` is renamed to "
        "`startd8 kickoff stakeholders`; this alias works for one release."
    )

_EXIT_FATAL_INPUTS = 2
_EXIT_RUNTIME = 1
# Distinct exit codes for `panel import` (FR-6/R2-F5), so a CI job can branch on WHY it failed.
_EXIT_SOURCE = 3  # source unreadable / malformed (adapter error during adapt)
_EXIT_GATE = 4  # adapter emitted a roster that failed the round-trip gate
_EXIT_CLOBBER = 5  # refused to overwrite an existing roster
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
            f"[red]panel:[/red] no roster at {path} — run `startd8 kickoff instantiate` first."
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
    for flag in answer.flags:  # FR-7 (M3): grounding-guard advisories
        console.print(f"  [yellow]⚠ grounding check:[/yellow] {flag}")
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
    except (
        Exception
    ) as exc:  # provider/auth/budget failure — clean message, not a traceback
        console.print(f"[red]panel:[/red] query failed: {exc}")
        raise typer.Exit(_EXIT_RUNTIME)
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
    except (
        Exception
    ) as exc:  # provider/auth/budget failure — clean message, not a traceback
        console.print(f"[red]panel:[/red] query failed: {exc}")
        raise typer.Exit(_EXIT_RUNTIME)
    finally:
        panel.close()
    for answer in answers:
        _render_answer(answer)
    total = sum(a.cost_usd for a in answers)
    if total:
        console.print(
            f"[dim]total cost ${total:.5f} across {len(answers)} personas[/dim]"
        )


@panel_app.command("import")
def panel_import(
    source: Path = typer.Argument(
        ..., help="External persona-format file to ingest (e.g. a reviewer_roles.yaml)."
    ),
    fmt: str = typer.Option(
        ...,
        "--format",
        help="Adapter name (see the roster-adapter registry, e.g. role-rubric).",
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Roster output path (default: the project's stakeholders.yaml).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing roster."),
) -> None:
    """Ingest an external persona format into a validated roster ($0, one-way, CLI-only writer)."""
    from .stakeholder_panel import AdapterError
    from .stakeholder_panel.adapters import available
    from .stakeholder_panel.ingest import IngestGateError, ingest, looks_generated

    # 1. Unknown format → exit 2, listing what is registered.
    known = available()
    if fmt not in known:
        console.print(
            f"[red]panel:[/red] unknown --format {fmt!r}. Available: {', '.join(known) or 'none'}"
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    # 2. Read the source (CLI owns file I/O; adapters take text).
    try:
        source_text = source.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]panel:[/red] cannot read source {source}: {exc}")
        raise typer.Exit(_EXIT_SOURCE)

    # 3. Adapt + round-trip gate.
    try:
        result = ingest(fmt, source_text, source=str(source))
    except IngestGateError as exc:  # adapter emitted a bad roster
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_GATE)
    except AdapterError as exc:  # malformed source
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_SOURCE)

    # 4. Resolve destination + clobber guard (R1-S8).
    dest = out if out is not None else (project_root / _ROSTER_REL)
    if dest.exists():
        if (
            not dest.is_file()
        ):  # a directory (or socket/etc.) at the path — never overwrite
            console.print(f"[red]panel:[/red] {dest} exists but is not a regular file.")
            raise typer.Exit(_EXIT_CLOBBER)
        try:
            existing = dest.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(
                f"[red]panel:[/red] cannot read existing roster {dest}: {exc}"
            )
            raise typer.Exit(_EXIT_CLOBBER)
        if not force:
            hint = "" if looks_generated(existing) else "looks hand-authored — "
            console.print(
                f"[red]panel:[/red] {dest} already exists ({hint}pass --force to overwrite)."
            )
            raise typer.Exit(_EXIT_CLOBBER)
        if not looks_generated(existing):
            console.print(
                f"[yellow]panel:[/yellow] ⚠ overwriting a hand-authored roster at {dest} (--force)."
            )

    # 5. Write atomically (tmp + rename) so an interrupted write can't corrupt the prior roster.
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(result.yaml_text, encoding="utf-8")
    os.replace(tmp, dest)
    console.print(
        f"[green]panel:[/green] imported {len(result.roster.personas)} personas "
        f"via {fmt} → {dest}"
    )
    for warning in result.warnings:
        console.print(f"  [yellow]⚠[/yellow] {warning}")


# --- GE-M1: deprecated top-level `startd8 panel …` alias (folded under `startd8 kickoff panel`) ---
# Re-register the exact command bodies above under the deprecated alias group. Its callback emits the
# one-release FR-GE-7/FR-10 deprecation notice; the commands themselves are byte-identical.
panel_deprecated_app.command("list")(panel_list)
panel_deprecated_app.command("ask")(panel_ask)
panel_deprecated_app.command("ask-all")(panel_ask_all)
panel_deprecated_app.command("import")(panel_import)

# Interim `startd8 kickoff panel …` alias (renamed to `kickoff stakeholders`) — same command bodies.
kickoff_panel_deprecated_app.command("list")(panel_list)
kickoff_panel_deprecated_app.command("ask")(panel_ask)
kickoff_panel_deprecated_app.command("ask-all")(panel_ask_all)
kickoff_panel_deprecated_app.command("import")(panel_import)
