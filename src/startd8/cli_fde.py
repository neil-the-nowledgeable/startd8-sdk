# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""fde CLI command group — Forward Deployed Engineer (SDK mechanism authority, posted to a project)."""

from pathlib import Path
from typing import List, Optional

import typer

from .cli_shared import console

fde_app = typer.Typer(
    name="fde",
    help="Forward Deployed Engineer: explain run failures with SDK-mechanism authority and "
    "spot SDK-mechanism landmines in plans before implementation.",
)


@fde_app.command("explain")
def fde_explain(
    output_dir: Optional[Path] = typer.Argument(
        None,
        help="Run output dir (contains service-assistant-triage.json + prime-* artifacts). "
        "Omit to explain the most recent run (FR-28).",
    ),
    latest: bool = typer.Option(
        False,
        "--latest",
        help="Explain the most recent run with a triage (same as omitting the arg).",
    ),
    base: Optional[Path] = typer.Option(
        None,
        "--base",
        help="Pipeline-output base to search for --latest "
        "(default: <project-root>/.cap-dev-pipe/pipeline-output).",
    ),
    feature_id: Optional[List[str]] = typer.Option(
        None, "--feature-id", help="Scope to specific feature(s); repeatable."
    ),
    project_root: Optional[Path] = typer.Option(
        None,
        "--project-root",
        help="Project root for the .startd8/fde/ posting (default: cwd).",
    ),
    narrative: bool = typer.Option(
        False,
        "--narrative",
        help="Add an LLM prose narrative (off by default; needs an API key).",
    ),
    max_cost_usd: Optional[float] = typer.Option(
        None,
        "--max-cost-usd",
        help="Budget for LLM narrative; over-budget drops to deterministic.",
    ),
    no_emit: bool = typer.Option(False, "--no-emit", help="Skip EventBus emission."),
    no_write: bool = typer.Option(False, "--no-write", help="Do not write artifacts."),
    force: bool = typer.Option(
        False, "--force", help="Recompute even if unchanged (ignore cursor)."
    ),
) -> None:
    """Compose SA project-evidence with SDK mechanism authority into a source-labeled explanation.

    With no run dir (or --latest), explains the most recent run with a triage under the
    pipeline-output base (FR-28). Exits non-zero when the SA triage is absent (degraded
    MECHANISM-only report) or a consumed artifact is malformed, so automation can detect an
    incomplete composition.
    """
    from .fde import run_fde_explain
    from .fde.sources import ArtifactTrustError, LatestRunError, resolve_latest_run

    # FR-28: resolve the latest run when no explicit path is given (explicit path always wins).
    if output_dir is None or latest:
        try:
            output_dir = resolve_latest_run(project_root=project_root, base=base)
        except LatestRunError as exc:
            console.print(f"[red]FDE: cannot resolve latest run:[/red] {exc}")
            raise typer.Exit(code=2)
        console.print(f"[dim]FDE: auto-selected latest run → {output_dir}[/dim]")

    try:
        outcome = run_fde_explain(
            output_dir,
            project_root=project_root,
            feature_ids=feature_id,
            narrative=narrative,
            max_cost_usd=max_cost_usd,
            emit=not no_emit,
            write=not no_write,
            force=force,
        )
    except ArtifactTrustError as exc:
        console.print(f"[red]FDE: consumed artifact failed trust gate:[/red] {exc}")
        raise typer.Exit(code=2)

    exp = outcome.explanation
    if outcome.skipped:
        console.print(f"[dim]FDE explain: {exp.run_id} unchanged — no-op.[/dim]")
        return

    color = "green" if exp.evidence_available else "yellow"
    console.print(
        f"[{color}]FDE explain: {exp.run_id} — {len(exp.failures)} failure(s), "
        f"{len(exp.all_claims())} labeled claim(s)[/{color}] → {outcome.report_path}"
    )
    if not exp.evidence_available:
        console.print(
            "  [yellow]⚠ degraded MECHANISM-only report — run `startd8 assist scan` first.[/yellow]"
        )
        raise typer.Exit(code=2)
    if not outcome.ref_attached:
        console.print(
            "  [yellow]⚠ explanation written but SA triage ref not attached (partial).[/yellow]"
        )
        raise typer.Exit(code=2)


@fde_app.command("preflight")
def fde_preflight(
    plan: Optional[Path] = typer.Option(
        None, "--plan", help="Plan markdown to review."
    ),
    requirements: Optional[Path] = typer.Option(
        None, "--requirements", help="Requirements markdown to review."
    ),
    project_root: Optional[Path] = typer.Option(
        None, "--project-root", help="Project root (default: cwd)."
    ),
    track2: bool = typer.Option(
        False,
        "--track2",
        help="Enable Track 2 tier prediction (plan-ingestion; LLM-backed).",
    ),
    max_cost_usd: Optional[float] = typer.Option(
        None, "--max-cost-usd", help="Track-2 LLM budget."
    ),
    no_emit: bool = typer.Option(False, "--no-emit", help="Skip EventBus emission."),
    no_write: bool = typer.Option(False, "--no-write", help="Do not write artifacts."),
    force: bool = typer.Option(False, "--force", help="Recompute even if unchanged."),
) -> None:
    """Spot SDK-mechanism landmines in a plan/requirements doc before implementation."""
    from .fde import run_fde_preflight

    if not plan and not requirements:
        console.print("[red]FDE preflight: pass --plan and/or --requirements.[/red]")
        raise typer.Exit(code=2)

    outcome = run_fde_preflight(
        plan_path=plan,
        requirements_path=requirements,
        project_root=project_root,
        enable_track2=track2,
        max_cost_usd=max_cost_usd,
        emit=not no_emit,
        write=not no_write,
        force=force,
    )
    rep = outcome.report
    n = len(rep.landmines)
    color = (
        "red"
        if any(m.severity in ("critical", "high") for m in rep.landmines)
        else ("yellow" if n else "green")
    )
    console.print(
        f"[{color}]FDE preflight: {n} landmine(s)[/{color}] → {outcome.report_path}"
    )
    for m in rep.sorted_landmines():
        console.print(f"  • [{m.severity}] (T{m.track}) {m.title}")
    if rep.redaction_manifest:
        console.print(f"  [dim]redacted: {', '.join(rep.redaction_manifest)}[/dim]")


@fde_app.command("init")
def fde_init(
    project_root: Optional[Path] = typer.Option(
        None, "--project-root", help="Project root (default: cwd)."
    ),
) -> None:
    """Establish the .startd8/fde/ posting explicitly (otherwise auto-created on first use)."""
    from .fde import context as fde_context

    root = project_root or Path.cwd()
    try:
        from . import __version__

        sdk_version = str(__version__)
    except Exception:
        sdk_version = "0.0.0"
    path = fde_context.ensure_posting(root, sdk_version=sdk_version)
    console.print(f"[green]FDE posting ready:[/green] {path}")
