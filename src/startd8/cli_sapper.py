"""``startd8 sapper`` — run the pre-execution "meet in the middle" survey standalone.

Sits between plan-ingestion and the prime contractor: it reads the ForwardManifest +
skeletons that ingestion's EMIT step produced, bores them against the real project, and
emits a ranked friction report — so you decide whether to spend on generation *before* you do.

    startd8 sapper survey --from <ingestion-output> --project-root <target-project>

Advisory by default (exit 0). Pass ``--gate`` to exit non-zero when a REFUTED-high finding
would block under the (separately gated) FR-SAP-8 policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

sapper_app = typer.Typer(help="Pre-execution plan validation (the meet-in-the-middle survey).")
console = Console()


@sapper_app.command("survey")
def survey(
    from_: str = typer.Option(
        ..., "--from", "-f", help="Plan-ingestion output: the artisan-context-seed.json or its dir."
    ),
    project_root: Optional[str] = typer.Option(
        None, "--project-root", "-p", help="The real target project (ground truth the bore checks)."
    ),
    out: Optional[str] = typer.Option(
        None, "--out", "-o", help="Directory to write the friction report (default: alongside the seed)."
    ),
    gate: bool = typer.Option(
        False, "--gate/--no-gate", help="Exit non-zero if the survey would block (FR-SAP-8 policy)."
    ),
    ground_truth: bool = typer.Option(
        False, "--ground-truth", "-g",
        help="Consult the project ground-truth oracle for residual assumptions (Prisma/TS today; "
             "mostly OMITs on pure-Python until a Python authority lands).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the machine-readable report instead of a table."),
) -> None:
    """Run the survey against an ingestion output and print/persist the friction report."""
    from startd8.sapper.host import load_from_ingestion_seed, sapper_preflight_hook

    manifest, skeletons = load_from_ingestion_seed(from_)
    out_dir = out or (str(Path(from_) if Path(from_).is_dir() else Path(from_).parent))

    oracle = None
    if ground_truth and project_root:
        from startd8.sapper.ground_truth import oracle_for_project

        oracle = oracle_for_project(project_root)

    outcome = sapper_preflight_hook(
        manifest, skeletons, project_root=project_root, out_dir=out_dir, fde=oracle
    )
    report = outcome.result.report

    if as_json:
        console.print_json(report.to_json())
    else:
        _render(report, outcome, project_root)

    if gate and outcome.blocked:
        console.print("[bold red]BLOCKED[/] — survey gating is enabled and a high-severity finding fired.")
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


def _render(report, outcome, project_root: Optional[str]) -> None:
    counts = report.counts()
    status_color = {"checked": "green", "degraded": "yellow", "unavailable": "red"}.get(
        report.bore_status, "white"
    )
    console.print(
        f"\n[bold]Sapper survey[/] — bore: [{status_color}]{report.bore_status}[/]  "
        f"refuted: [red]{counts['refuted']}[/]  unresolved: [yellow]{counts['unresolved']}[/]  "
        f"validated: [green]{counts['validated']}[/]  unresolved_rate: {report.unresolved_rate()}"
    )
    if project_root is None:
        console.print("[dim]note: no --project-root → existence bore limited to stdlib/intra-skeleton.[/]")
    for n in report.notes:
        console.print(f"[dim]• {n}[/]")

    actionable = [f for f in report.ranked if f.verdict.value != "validated"]
    if not actionable:
        console.print("\n[green]No friction — plan is aligned within the validated scope.[/]")
    else:
        table = Table(title="Friction (ranked by avoidable cost)", show_lines=False)
        for col in ("#", "stage", "sev", "verdict", "kind", "file:line", "expected → found"):
            table.add_column(col, overflow="fold")
        for i, f in enumerate(actionable[:25], 1):
            verdict = f.verdict.value + (f"/{f.reason.value}" if f.reason else "")
            arrow = f"{f.expected} → {f.found}" if (f.expected or f.found) else ""
            table.add_row(
                str(i), f.avoidable_cost_stage.value, f.severity.value, verdict,
                f.kind.value, f"{f.file}:{f.line}", arrow,
            )
        console.print(table)

    if outcome.artifacts:
        console.print(f"\n[dim]report: {outcome.artifacts.get('json')}[/]")
        console.print(f"[dim]        {outcome.artifacts.get('md')}[/]")
    if outcome.injection_block:
        console.print(
            "\n[bold]Downstream warning block[/] (inject into generation prompts before running the contractor):"
        )
        console.print(outcome.injection_block)
