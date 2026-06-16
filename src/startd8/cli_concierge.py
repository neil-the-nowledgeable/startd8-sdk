# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""concierge CLI command group — project-side SDK-onboarding assist.

Human-facing front door over the same SDK code path the `startd8_concierge` MCP tool uses
(FR-C13: one logic, two front doors). Read actions (`survey`, `assess`) are $0/read-only; write
actions (`instantiate-kickoff`, `log-friction`) write **only here** — the CLI is the sole writer
(OQ-7), running at the human's own privilege, preview-by-default, `--apply` to write.
Exit codes: 0 advisory; 2 unreadable/invalid input (FR-W9); 3 a write was blocked by a
confinement/clobber guard; 1 `--check` drift detected.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .cli_shared import console

concierge_app = typer.Typer(
    name="concierge",
    help="Onboarding assist: survey/assess a project (read-only) and instantiate-kickoff/log-friction (CLI-only writes).",
)

_EXIT_FATAL_INPUTS = 2
_EXIT_BLOCKED = 3
_EXIT_DRIFT = 1


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


def _render_write_result(res) -> None:
    for p in res.written:
        console.print(f"  [green]wrote[/green]    {p}")
    for s in res.skipped:
        console.print(f"  [yellow]skipped[/yellow]  {s['path']} — {s['reason']}")
    for b in res.blocked:
        console.print(f"  [red]BLOCKED[/red]  {b['path']} — {b['reason']}")
    for e in res.errors:
        console.print(f"  [red]error[/red]    {e['path']} — {e['error']}")


@concierge_app.command("instantiate-kickoff")
def concierge_instantiate(
    project_root: Path = typer.Argument(Path("."), help="Target project (default: current dir)."),
    posture: str = typer.Option("prototype", "--posture", help="prototype | production"),
    with_authoring: bool = typer.Option(False, "--with-authoring", help="Also project the REQUIREMENTS/PLAN/TEST_USERS authoring trio."),
    apply: bool = typer.Option(False, "--apply", help="Write the files (default: preview only)."),
    force: bool = typer.Option(False, "--force", help="With --apply: overwrite files that diverged from the template."),
    check: bool = typer.Option(False, "--check", help="Report drift (matches/diverged/absent) + verdict; non-zero exit on drift."),
    json_out: bool = typer.Option(False, "--json", help="Emit schema-versioned JSON."),
) -> None:
    """Project the kickoff package into a project (FR-C7). Preview by default; --apply to write."""
    from .concierge.safe_write import SafeWriteError, apply_write_plan
    from .concierge.writes import (
        ConciergeWriteError,
        build_instantiate_plan,
        compute_drift,
        to_planned_writes,
    )

    try:
        plan = build_instantiate_plan(project_root, posture, with_authoring=with_authoring)
    except ConciergeWriteError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if check:
        drift = compute_drift(plan, project_root)
        if json_out:
            _emit_json(drift)
        else:
            color = {"complete": "green", "partial": "yellow", "drifted": "red"}[drift["verdict"]]
            console.print(f"[bold]instantiate-kickoff --check[/bold] — verdict: [{color}]{drift['verdict']}[/{color}]")
            for f in drift["files"]:
                console.print(f"  {f['state']:<9} {f['path']}")
        raise typer.Exit(0 if drift["verdict"] == "complete" else _EXIT_DRIFT)

    if not apply:
        if json_out:
            _emit_json(plan)
        else:
            console.print(f"[bold]instantiate-kickoff[/bold] (preview, posture={plan['posture']}) — {plan['project_root']}")
            for w in plan["writes"]:
                console.print(f"  [{('green' if w['status']=='new' else 'yellow')}]{w['status']:<7}[/] {w['path']} ({w['bytes']} B)")
            for warn in plan["warnings"]:
                console.print(f"  [yellow]⚠[/yellow] {warn}")
            console.print("\n  [dim]preview only — re-run with --apply to write[/dim]")
        return

    try:
        res = apply_write_plan(project_root, to_planned_writes(plan), force=force)
    except SafeWriteError as exc:
        console.print(f"[red]concierge: blocked — {exc}[/red]")
        raise typer.Exit(_EXIT_BLOCKED)
    console.print(f"[bold]instantiate-kickoff[/bold] — {plan['project_root']}")
    _render_write_result(res)
    if not res.ok:
        raise typer.Exit(_EXIT_BLOCKED)


@concierge_app.command("log-friction")
def concierge_log_friction(
    project_root: Path = typer.Argument(Path("."), help="Project whose friction log to append (default: current dir)."),
    friction: str = typer.Option(..., "--friction", help="The friction encountered."),
    what_happened: str = typer.Option(..., "--what-happened", help="What happened."),
    implication: str = typer.Option(..., "--implication", help="Implication for the SDK / role."),
    apply: bool = typer.Option(False, "--apply", help="Append the entry (default: preview only)."),
    json_out: bool = typer.Option(False, "--json", help="Emit schema-versioned JSON."),
) -> None:
    """Append a structured friction entry to concierge-friction.jsonl (FR-C9)."""
    from datetime import datetime, timezone

    from .concierge.safe_write import SafeWriteError, apply_write_plan
    from .concierge.writes import ConciergeWriteError, build_friction_entry, to_planned_writes

    try:
        plan = build_friction_entry(
            project_root,
            friction=friction,
            what_happened=what_happened,
            implication=implication,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except ConciergeWriteError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if not apply:
        if json_out:
            _emit_json(plan)
        else:
            w = plan["writes"][0]
            console.print(f"[bold]log-friction[/bold] (preview) — would {w['status']=='new' and 'create' or 'append to'} {w['path']}")
            console.print(f"  {w['append_text'].rstrip()}")
            console.print("\n  [dim]preview only — re-run with --apply to write[/dim]")
        return

    try:
        res = apply_write_plan(project_root, to_planned_writes(plan))
    except SafeWriteError as exc:
        console.print(f"[red]concierge: blocked — {exc}[/red]")
        raise typer.Exit(_EXIT_BLOCKED)
    _render_write_result(res)
    if not res.ok:
        raise typer.Exit(_EXIT_BLOCKED)
