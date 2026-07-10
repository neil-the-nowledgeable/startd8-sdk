"""``startd8 promote tsdb <metric>`` — M6, the CLI orchestrating M0→M5 (FR-10).

Wires the TSDB→relational pipeline into one command, modeled on ``generate contract``:
read (M0) → specimen (M1) → infer (M2) → confirm (M2.5) → imports.yaml (M3) → gate+promote
(M4) → backend + backfill payload (M5).

Two input modes (the gov series are retention-pruned, so a recorded specimen is the primary,
testable path):
  * ``--specimen <file>`` — load a durable M1 specimen JSON (no live TSDB); or
  * ``--endpoint <url>`` (+ ``--datasource-uid`` / ``--direct``) — read live via M0.

Flow control:
  * ``--dry-run``     — read → infer → show the confirmation surface + summary; write nothing.
  * ``--confirm``     — record the committed confirmation marker for the inferred key, then stop.
  * (default)         — gate + promote ``prisma/schema.prisma``, write ``imports.yaml`` + backend +
                        the backfill payload. Refused unless the key is confirmed (``--force`` bypasses).

Exit codes: 0 success · 1 refused (gate/confirmation/empty) · 2 input/read error.
"""

from __future__ import annotations

from pathlib import Path
from .paths import startd8_dir
from typing import Optional

import typer
from rich.console import Console

from .logging_config import get_logger
from .tsdb_maturation import (
    Specimen,
    build_payload,
    confirm_inference,
    gate_and_promote,
    generate_imports_yaml,
    infer_schema,
    load_specimen,
    summarize,
)
from .tsdb_maturation.reader import (
    DirectMimirEndpoint,
    GrafanaProxyEndpoint,
    TsdbReader,
    TsdbReaderError,
)
from .tsdb_maturation.specimen import Grain

logger = get_logger(__name__)
console = Console()

promote_app = typer.Typer(help="Promote observed TSDB metrics into a generated relational app.")

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_ERROR = 2


@promote_app.callback()
def _promote_callback() -> None:
    """Promote a metric (or specimen) into a generated relational app (use `promote tsdb`)."""


def _load_specimen_from_source(
    metric: str,
    *,
    specimen_path: Optional[Path],
    endpoint: Optional[str],
    datasource_uid: Optional[str],
    direct: bool,
    tenant: Optional[str],
    lookback: str,
) -> Specimen:
    """M0+M1: load a recorded specimen, or read live from a TSDB endpoint."""
    if specimen_path is not None:
        spec = load_specimen(specimen_path)
        console.print(f"[dim]loaded specimen from {specimen_path} ({spec.n_records} records)[/dim]")
        return spec
    if not endpoint:
        raise typer.BadParameter("provide either --specimen <file> or --endpoint <url>")
    ep = (
        DirectMimirEndpoint(base_url=endpoint, tenant=tenant)
        if direct
        else GrafanaProxyEndpoint(base_url=endpoint, datasource_uid=datasource_uid or "mimir")
    )
    with TsdbReader(ep) as reader:
        result = reader.read(metric, lookback=lookback)
    return Specimen.from_read_result(result, grain=Grain.TSDB_AGGREGATE)


@promote_app.command("tsdb")
def promote_tsdb(
    metric: str = typer.Argument(..., help="The metric name (or specimen's metric)."),
    specimen: Optional[Path] = typer.Option(None, "--specimen", help="Load a durable M1 specimen JSON (no live read)."),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", help="Grafana/Mimir base URL for a live read."),
    datasource_uid: Optional[str] = typer.Option(None, "--datasource-uid", help="Grafana datasource uid (proxy mode)."),
    direct: bool = typer.Option(False, "--direct", help="Query Mimir/Prometheus directly (not via the Grafana proxy)."),
    tenant: Optional[str] = typer.Option(None, "--tenant", help="X-Scope-OrgID tenant (direct Mimir)."),
    lookback: str = typer.Option("3000d", "--lookback", help="last_over_time lookback window."),
    entity: Optional[str] = typer.Option(None, "--entity", help="Model/table name (default: derived from the metric)."),
    identity: Optional[str] = typer.Option(None, "--identity", help="Declared identity columns (comma-separated); overrides inference."),
    aggregate: Optional[str] = typer.Option(None, "--aggregate", help="Key-collapse aggregation override: sum|last|avg."),
    reduce: Optional[str] = typer.Option(None, "--reduce", help="Cardinality reduction (FR-5 — not yet implemented)."),
    project: Path = typer.Option(Path("."), "--project", help="Project root (where schema/imports/app are written)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Read → infer → show surface; write nothing."),
    confirm: bool = typer.Option(False, "--confirm", help="Record the confirmation marker for the inferred key, then stop."),
    force: bool = typer.Option(False, "--force", help="Bypass the confirmation gate (still reports status)."),
    generate_app: bool = typer.Option(True, "--generate-app/--no-generate-app", help="Render the backend app on promote."),
) -> None:
    """Promote a metric into a generated relational app (M0→M5)."""
    if reduce is not None:
        console.print("[yellow]--reduce (FR-5 cardinality reduction) is not yet implemented (deferred M2 sub-task).[/yellow]")
        raise typer.Exit(EXIT_ERROR)

    # M0 + M1 — obtain the specimen.
    try:
        spec = _load_specimen_from_source(
            metric, specimen_path=specimen, endpoint=endpoint, datasource_uid=datasource_uid,
            direct=direct, tenant=tenant, lookback=lookback,
        )
    except TsdbReaderError as exc:
        console.print(f"[red]read error:[/red] {exc}")
        raise typer.Exit(EXIT_ERROR)

    if spec.n_records == 0:
        console.print(f"[red]empty specimen for {metric!r} — refusing (OQ-6).[/red]")
        raise typer.Exit(EXIT_REFUSED)

    # M2 — infer the schema.
    id_cols = [c.strip() for c in identity.split(",")] if identity else None
    try:
        result = infer_schema(spec, entity_name=entity, identity=id_cols)
    except Exception as exc:  # noqa: BLE001 — surface any inference failure as a clean error
        console.print(f"[red]inference error:[/red] {exc}")
        raise typer.Exit(EXIT_ERROR)

    console.print(summarize(spec).render())
    console.print("")
    from .tsdb_maturation import render_confirmation_surface

    console.print(render_confirmation_surface(result))

    # --confirm — record the committed marker and stop.
    if confirm:
        rec = confirm_inference(project, result, metric)
        console.print(f"[green]confirmed[/green] {metric} identity {list(rec.identity)} → {project}/docs/tsdb-maturation/confirmed.yaml")
        raise typer.Exit(EXIT_OK)

    # --dry-run — nothing written past this point.
    if dry_run:
        console.print("[dim]--dry-run: no schema/app written. Re-run with --confirm, then without --dry-run to promote.[/dim]")
        raise typer.Exit(EXIT_OK)

    # M4 — gate + promote.
    run_dir = startd8_dir(project) / "tsdb-run"
    outcome = gate_and_promote(
        result, spec, metric=metric, project_root=project, run_dir=run_dir,
        require_confirmed=not force,
    )
    if outcome.refused:
        console.print(f"[red]refused:[/red] {outcome.reason}")
        raise typer.Exit(EXIT_REFUSED)
    console.print(f"[green]promoted[/green] → {outcome.schema_path}")

    # M3 — imports.yaml.
    imports_text = generate_imports_yaml([result])
    imports_path = project / "imports.yaml"
    imports_path.write_text(imports_text, encoding="utf-8")
    console.print(f"[green]wrote[/green] {imports_path}")

    # M5 — backfill payload (+ optional backend app).
    built = build_payload(spec, result, metric=metric, aggregate=aggregate)
    for w in built.warnings:
        console.print(f"[yellow]warning:[/yellow] {w}")
    import json

    payload_path = project / f"backfill-{result.entity}.json"
    payload_path.write_text(json.dumps(built.payload, indent=2), encoding="utf-8")
    console.print(f"[green]wrote[/green] {payload_path} ({built.rows_out} rows, agg={built.agg_func.value})")

    if generate_app:
        from .backend_codegen import render_backend

        count = 0
        for rel, content in render_backend(result.schema_text, imports_text=imports_text):
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            count += 1
        console.print(f"[green]generated[/green] {count} backend files under {project}/app")
        console.print(f"[dim]backfill: import {payload_path.name} via the generated app's from_json.[/dim]")
