# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""concierge CLI command group — project-side SDK-onboarding assist (read-only, $0).

Human-facing front door over the same SDK code path the `startd8_concierge` MCP tool uses
(FR-C13: one logic, two front doors). v1 actions are read-only (`survey`, `assess`); write
actions (`instantiate-kickoff`, `log-friction`) land here later as the CLI is the sole writer
(OQ-7 resolution). Advisory: exits 0 regardless of readiness; exit 2 only for an unreadable
input (the wireframe FR-W9 convention).
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .cli_shared import console

concierge_app = typer.Typer(
    name="concierge",
    help="Onboarding assist: survey a project and assess its SDK-onboarding readiness ($0, read-only).",
)

_EXIT_FATAL_INPUTS = 2


def _emit_json(result: dict) -> None:
    import sys

    sys.stdout.write(json.dumps(result, indent=2) + "\n")


@concierge_app.command("survey")
def concierge_survey(
    project_root: Path = typer.Argument(
        Path("."), help="Project to triage (default: current dir). Read-only — never modified."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the schema-versioned JSON to stdout."),
) -> None:
    """Brownfield triage: requirement docs (+ extraction-format match), models, fixtures, PII flags."""
    from .concierge import ConciergeError, handle_concierge_tool

    try:
        result = handle_concierge_tool("survey", project_root)
    except ConciergeError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if json_out:
        _emit_json(result)
        return

    console.print(f"[bold]Concierge survey[/bold] — {result['project_root']}")

    docs = result["requirement_docs"]
    if docs:
        console.print(f"\n[bold]Requirement docs[/bold] ({len(docs)}):")
        for d in docs:
            tag = "[green]extraction-format[/green]" if d["extraction_format"] else "[yellow]needs reformat (F-4)[/yellow]"
            console.print(f"  • {d['path']}  {tag}")
    else:
        console.print("\n[dim]No requirement/PRD/PLAN docs found.[/dim]")

    models = result["model_files"]
    console.print(f"\n[bold]Pydantic model files[/bold]: {len(models)}")
    for m in models[:10]:
        console.print(f"  • {m}")

    fixtures = result["fixture_candidates"]
    console.print(f"\n[bold]Test-fixture candidates[/bold]: {len(fixtures)}")
    for f in fixtures[:10]:
        console.print(f"  • {f}")

    pii = result["pii_risk_flags"]
    if pii:
        console.print(f"\n[bold red]Personal/PII risk flags[/bold red] ({len(pii)}) — review before any carve/commit:")
        for p in pii:
            console.print(f"  [red]⚠[/red] {p}")
    else:
        console.print("\n[green]No personal/PII-material flagged[/green] (name/extension heuristic).")


@concierge_app.command("assess")
def concierge_assess(
    project_root: Path = typer.Argument(
        Path("."), help="Project to assess (default: current dir). Read-only."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the schema-versioned JSON to stdout."),
) -> None:
    """Onboarding-readiness report: kickoff-input provenance + the $0-cascade view (wraps wireframe)."""
    from .concierge import ConciergeError, handle_concierge_tool

    try:
        result = handle_concierge_tool("assess", project_root)
    except ConciergeError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if json_out:
        _emit_json(result)
        return

    console.print(f"[bold]Concierge assess[/bold] — {result['project_root']}")

    console.print("\n[bold]Kickoff inputs[/bold] (provenance, honest — not graded):")
    for domain, info in result["kickoff_inputs"]["domains"].items():
        status = info.get("status")
        if status == "present":
            console.print(f"  • {domain}: [green]present[/green] — provenance: {info.get('provenance_default')}")
        elif status == "absent":
            console.print(f"  • {domain}: [yellow]absent[/yellow]")
        else:
            console.print(f"  • {domain}: [red]{status}[/red] {info.get('error', '')}")

    cascade = result["cascade"]
    console.print("\n[bold]$0 cascade[/bold]:")
    if cascade.get("status") != "ok":
        console.print(f"  [red]{cascade.get('status')}[/red]: {cascade.get('error', '')}")
    else:
        shape = cascade["shape"]
        console.print(
            f"  shape: {shape['entities']} entities · {shape['crud_routes']} CRUD routes · "
            f"{shape['pages']} pages · {shape['views']} views · {shape['ai_passes']} AI passes"
        )
        for gen, state in cascade["readiness"].items():
            color = "green" if state == "ready" else "yellow"
            console.print(f"  {gen}: [{color}]{state}[/{color}]")
        blockers = cascade.get("blockers") or []
        if blockers:
            console.print("\n[bold]Blocking next step[/bold]:")
            for b in blockers:
                console.print(f"  • {b['section']} ([yellow]{b['status']}[/yellow]): {b['consequence']}")
