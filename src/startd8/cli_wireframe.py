"""`startd8 wireframe` — pre-generation summary of the deterministic cascade (FR-W9).

Top-level command (OQ-1): not under `generate` (emits no app code), not under `assist` (that
family is run-triage). Advisory: exit 0 regardless of plan statuses; exit 2 only on a fatal
assembly-inputs problem (unreadable/non-UTF-8/garbled `--inputs` file, unknown keys, or a path
escaping the project root — FR-W9/R2-F3/R3-F4).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from .wireframe import (
    AssemblyInputsError,
    build_wireframe_plan,
    load_assembly_inputs,
)
from .wireframe.render import persist_plan, plan_to_json, render_plan, run_linkage

console = Console()

_EXIT_FATAL_INPUTS = 2


def wireframe(
    inputs: List[Path] = typer.Option(
        [], "--inputs", help="Assembly-inputs YAML (repeatable; merged in order, last wins)."
    ),
    project: Path = typer.Option(
        Path("."), "--project", help="Project root (read root — the wireframe never writes app files)."
    ),
    from_run: Optional[Path] = typer.Option(
        None,
        "--from-run",
        help="Plan-ingestion run dir (FR-WPI-6): consume its manifests/ (extracted, parser-"
        "clean) instead of project paths; keys the run didn't emit (e.g. the live contract) "
        "fall back to convention. Adds the FR-WPI-7 run_linkage block to the JSON.",
    ),
    schema: Optional[Path] = typer.Option(None, "--schema", help="Path to prisma/schema.prisma."),
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", "--app", help="Path to app.yaml (scaffold manifest; same flag as `generate scaffold`)."
    ),
    pages: Optional[Path] = typer.Option(None, "--pages", help="Path to pages.yaml."),
    views: Optional[Path] = typer.Option(None, "--views", help="Path to views.yaml."),
    ai_passes: Optional[Path] = typer.Option(None, "--ai-passes", help="Path to ai_passes.yaml."),
    human_inputs: Optional[Path] = typer.Option(
        None, "--human-inputs", help="Path to human_inputs.yaml."
    ),
    completeness: Optional[Path] = typer.Option(
        None, "--completeness", help="Path to completeness.yaml."
    ),
    pages_authoring: bool = typer.Option(
        False, "--pages-authoring", help="Include the page-authoring UI artifacts (requires --pages or a conventional pages.yaml)."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the WireframePlan JSON to stdout (suppresses the tree unless --verbose)."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="With --json: also render the Rich tree (to stderr-safe console)."
    ),
    only_issues: bool = typer.Option(
        False, "--only-issues", help="Render only non-`planned` sections (footer keeps full totals)."
    ),
    max_items: int = typer.Option(
        25, "--max-items", help="Per-section item cap in the tree (0 = unlimited)."
    ),
    no_write: bool = typer.Option(
        False, "--no-write", help="Skip persisting .startd8/wireframe/wireframe-plan.json."
    ),
    inventory: bool = typer.Option(
        False,
        "--inventory",
        help="Render the per-iteration delivery inventory (FR-WPI-9). Default in --from-run "
        "mode — it is the business walkthrough artifact.",
    ),
) -> None:
    """Show what the $0 deterministic cascade WILL build — and what is not yet defined."""
    overrides = {
        "schema": schema,
        "app": manifest,
        "pages": pages,
        "views": views,
        "ai_passes": ai_passes,
        "human_inputs": human_inputs,
        "completeness": completeness,
    }
    try:
        resolved = load_assembly_inputs(
            yaml_paths=list(inputs),
            overrides={k: v for k, v in overrides.items() if v is not None},
            project_root=project,
            from_run=from_run,
        )
    except AssemblyInputsError as exc:
        console.print(f"[red]wireframe:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    # FR-WPI-7: end-to-end fingerprint linkage (prose → extraction → manifest → wireframe).
    linkage = run_linkage(from_run) if from_run is not None else None

    # FR-W7/R5-F6: same contract as `generate backend` — the authoring UI is meaningless
    # without a pages manifest (here, resolved via flag, inputs YAML, or convention).
    if pages_authoring and not resolved.entry("pages").resolved_path.is_file():
        console.print(
            "[red]error:[/red] --pages-authoring requires --pages "
            "(the authoring UI edits the pages.yaml manifest; no pages.yaml was "
            "resolved via flag, --inputs, or the prisma/pages.yaml convention)."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    plan = build_wireframe_plan(resolved, authoring=pages_authoring)

    if json_out:
        # Machine contract (R4-F1): stdout is parseable JSON only; tree only with --verbose.
        sys.stdout.write(plan_to_json(plan, emit_context="cli", linkage=linkage))
        if verbose:
            render_plan(plan, console, only_issues=only_issues, max_items=max_items)
    else:
        render_plan(plan, console, only_issues=only_issues, max_items=max_items)

    # FR-WPI-9: the walkthrough artifact — default-on when consuming a run.
    if (inventory or from_run is not None) and not json_out:
        from .wireframe.render import render_delivery_inventory

        render_delivery_inventory(plan, console, max_items=max_items)

    if not no_write:
        persist_plan(
            plan,
            Path(project) / ".startd8" / "wireframe",
            emit_context="cli",
            linkage=linkage,
        )
