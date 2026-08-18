"""``startd8 prime-ledger`` — query the cross-project Prime generation ledger (FR-4 / FR-6).

The read + trust surface over the data spine in ``generation_ledger.py``: which projects has Prime
worked on, every run per project (what/where/when/cost/status), where a run's artifacts are, and a
liveness ``verify`` that flags phantom artifact paths / cost drift. Every command has ``--json`` for CI.
"""

from __future__ import annotations

import dataclasses
import json as _json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import generation_ledger as gl

prime_ledger_app = typer.Typer(
    help="Cross-project Prime generation ledger — which projects, which runs, what cost, where artifacts.",
    no_args_is_help=True,
)
console = Console()

_EXIT_OK = 0
_EXIT_FINDINGS = 1
_EXIT_ERR = 2


@prime_ledger_app.command("list")
def list_projects(
    as_json: bool = typer.Option(
        False, "--json", help="Emit the index rows as JSON (for CI)."
    ),
    home: Optional[str] = typer.Option(
        None, "--home", help="Override the ledger home ($STARTD8_HOME)."
    ),
) -> None:
    """List every project Prime has worked on (the cross-project index)."""
    index = gl.load_index(home)
    if as_json:
        typer.echo(_json.dumps(index.to_dict(), indent=2, default=str))
        raise typer.Exit(_EXIT_OK)
    if not index.projects:
        console.print(
            "[yellow]no projects recorded yet[/yellow] (run a Prime generation, then record it)"
        )
        raise typer.Exit(_EXIT_OK)
    table = Table(title="Prime generation ledger — projects")
    for col in (
        "project",
        "runs",
        "batches",
        "last run",
        "cumulative $",
        "status",
        "features",
    ):
        table.add_column(col)
    for p in index.projects:
        table.add_row(
            p.get("project_id", ""),
            str(p.get("runs", 0)),
            str(p.get("batches", 0)),
            p.get("last_run_at", ""),
            f"{p.get('cumulative_cost_usd', 0.0):.4f}",
            p.get("status", ""),
            f"{p.get('features_passed', 0)}/{p.get('features_total', 0)}",
        )
    console.print(table)
    raise typer.Exit(_EXIT_OK)


@prime_ledger_app.command("show")
def show_project(
    project_id: str = typer.Argument(
        ..., help="The project id (see `prime-ledger list`)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the project ledger as JSON."
    ),
    home: Optional[str] = typer.Option(
        None, "--home", help="Override the ledger home."
    ),
) -> None:
    """Show every run for a project (what/where/when/cost/status)."""
    path = gl.project_ledger_path(project_id, home)
    if not path.is_file():
        console.print(
            f"[red]error:[/red] no ledger for project {project_id!r} ({path})"
        )
        raise typer.Exit(_EXIT_ERR)
    ledger = gl.load_project_ledger(project_id, home=home)
    if as_json:
        typer.echo(_json.dumps(ledger.to_dict(), indent=2, default=str))
        raise typer.Exit(_EXIT_OK)
    cum = ledger.cumulative()
    console.print(
        f"[bold]{ledger.project_id}[/bold]  {ledger.project_path}\n"
        f"  {cum['runs']} run(s) · ${cum['total_cost_usd']:.4f} · "
        f"{cum['features_passed']}/{cum['features_total_in_batch']} · {cum['status']}"
    )
    table = Table()
    for col in ("run", "when", "verdict", "passed", "cost $", "batch"):
        table.add_column(col)
    for batch in ledger.batches:
        for run in batch.get("runs", []):
            table.add_row(
                run.get("run_id", ""),
                run.get("generated_at", ""),
                run.get("verdict", ""),
                f"{run.get('features_passed', 0)}/{run.get('features_attempted', 0)}",
                f"{run.get('cost_usd', 0.0):.4f}",
                batch.get("batch_id", ""),
            )
    console.print(table)
    raise typer.Exit(_EXIT_OK)


@prime_ledger_app.command("artifacts")
def show_artifacts(
    project_id: str = typer.Argument(..., help="The project id."),
    run_id: str = typer.Argument(..., help="The run id (see `prime-ledger show`)."),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the artifact map as JSON."
    ),
    home: Optional[str] = typer.Option(
        None, "--home", help="Override the ledger home."
    ),
) -> None:
    """Print a run's artifact map (where the generation artifacts live)."""
    ledger = gl.load_project_ledger(project_id, home=home)
    run = next(
        (
            r
            for b in ledger.batches
            for r in b.get("runs", [])
            if r.get("run_id") == run_id
        ),
        None,
    )
    if run is None:
        console.print(f"[red]error:[/red] no run {run_id!r} for project {project_id!r}")
        raise typer.Exit(_EXIT_ERR)
    artifacts = run.get("artifacts", {})
    if as_json:
        typer.echo(_json.dumps(artifacts, indent=2, default=str))
        raise typer.Exit(_EXIT_OK)
    for role, path in artifacts.items():
        console.print(f"  {role:24} {path if path is not None else '—'}")
    raise typer.Exit(_EXIT_OK)


@prime_ledger_app.command("verify")
def verify(
    project_id: Optional[str] = typer.Argument(
        None, help="One project, or omit for all."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit findings as JSON."),
    home: Optional[str] = typer.Option(
        None, "--home", help="Override the ledger home."
    ),
) -> None:
    """Liveness oracle (FR-6): flag phantom artifact paths / cost drift. Exit 0 clean · 1 findings."""
    if project_id:
        findings = gl.verify_project(gl.load_project_ledger(project_id, home=home))
    else:
        findings = gl.verify_all(home)
    if as_json:
        typer.echo(_json.dumps([dataclasses.asdict(f) for f in findings], indent=2))
    elif not findings:
        console.print(
            "[green]clean[/green] — every recorded artifact resolves and costs match source"
        )
    else:
        for f in findings:
            colour = "red" if f.kind == "PHANTOM" else "yellow"
            console.print(
                f"[{colour}]{f.kind}[/{colour}] {f.project_id}/{f.run_id}: {f.detail}"
            )
    raise typer.Exit(_EXIT_FINDINGS if findings else _EXIT_OK)


@prime_ledger_app.command("record")
def record(
    project_root: str = typer.Argument(
        ...,
        help="A Prime-generated project root (must contain .startd8/generation-manifest.json).",
    ),
    home: Optional[str] = typer.Option(
        None, "--home", help="Override the ledger home."
    ),
) -> None:
    """Backfill: record an existing project's latest run into the ledger (FR-3, manual entry point).

    The postmortem hook (FR-5) records new runs automatically; this command brings *already-generated*
    projects into the index. Auto-derived from the project's real artifacts — safe to re-run (idempotent
    per run id).
    """
    try:
        ledger = gl.record_run(project_root, home=home)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)
    cum = ledger.cumulative()
    console.print(
        f"[green]recorded[/green] {ledger.project_id} — {cum['runs']} run(s) · "
        f"${cum['total_cost_usd']:.4f} · {cum['features_passed']}/"
        f"{cum['features_total_in_batch']} · {cum['status']}"
    )
    raise typer.Exit(_EXIT_OK)


@prime_ledger_app.command("trends")
def trends(
    project_id: str = typer.Argument(
        ..., help="The project id (see `prime-ledger list`)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the trend series + slopes as JSON."
    ),
    home: Optional[str] = typer.Option(
        None, "--home", help="Override the ledger home."
    ),
) -> None:
    """Per-project run-over-run trends: cost, features, and the $0-local (Micro Prime) ratio over time."""
    path = gl.project_ledger_path(project_id, home)
    if not path.is_file():
        console.print(
            f"[red]error:[/red] no ledger for project {project_id!r} ({path})"
        )
        raise typer.Exit(_EXIT_ERR)
    data = gl.project_trends(gl.load_project_ledger(project_id, home=home))
    if as_json:
        typer.echo(_json.dumps(data, indent=2, default=str))
        raise typer.Exit(_EXIT_OK)

    table = Table(title=f"{project_id} — run trends")
    for col in ("run", "when", "cost $", "passed", "$0-local / total"):
        table.add_column(col)
    for s in data["runs"]:
        table.add_row(
            s["run_id"],
            s["generated_at"],
            f"{s['cost_usd']:.4f}",
            str(s["features_passed"]),
            f"{s['local_features']}/{s['total_features']} ({s['local_ratio']:.0%})",
        )
    console.print(table)
    if len(data["runs"]) < 2:
        console.print("[dim]1 run — need ≥2 for a trend line.[/dim]")
    else:

        def _arrow(slope: float) -> str:
            return "↑" if slope > 0 else ("↓" if slope < 0 else "→")

        cs, rs = data["cost_slope"], data["local_ratio_slope"]
        console.print(
            f"cost/run {_arrow(cs)} ({cs:+.4f}/run) · "
            f"$0-local ratio {_arrow(rs)} ({rs:+.1%}/run) — "
            "a rising local ratio + falling cost is the decouple's Micro Prime win"
        )
    raise typer.Exit(_EXIT_OK)


@prime_ledger_app.command("metrics")
def metrics(
    out: str = typer.Option(
        "generation-ledger.prom",
        "--out",
        help="Output .prom path for a Prometheus textfile collector (the $0/offline datasource path).",
    ),
    push: bool = typer.Option(
        False,
        "--push",
        help="Push OTLP gauges → Alloy → Mimir (the live datasource path) instead of a textfile.",
    ),
    endpoint: str = typer.Option(
        "localhost:4317", "--endpoint", help="OTLP gRPC endpoint for --push."
    ),
    home: Optional[str] = typer.Option(
        None, "--home", help="Override the ledger home."
    ),
) -> None:
    """Export the portfolio as Prometheus metrics (the datasource path for the Grafana dashboard).

    Default writes a ``.prom`` textfile ($0/offline); ``--push`` sends OTLP gauges to a live
    Alloy→Mimir stack so the dashboard renders immediately.
    """
    from . import generation_ledger_metrics as glm

    if push:
        result = glm.push_ledger_metrics_otlp(home=home, endpoint=endpoint)
        console.print(
            f"[green]pushed[/green] {result['series']} gauge series via OTLP → {result['endpoint']}"
        )
    else:
        result = glm.write_ledger_metrics(out, home=home)
        console.print(
            f"[green]wrote[/green] {result['series']} metric series → {result['path']} "
            "(point a Prometheus textfile collector here)"
        )
    raise typer.Exit(_EXIT_OK)
