"""``startd8 openapi`` — OpenAPI overlay tooling (Role 2 FR-D1, $0)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

from .backend_codegen.openapi_normalize import (
    load_openapi_document,
    normalize_openapi_to_overlay,
    render_overlay_yaml,
)

console = Console()

openapi_app = typer.Typer(help="OpenAPI overlay helpers — brownfield ingest and api.yaml tooling ($0).")

_EXIT_OK = 0
_EXIT_ERROR = 2


@openapi_app.callback()
def _openapi_callback() -> None:
    """Deterministic OpenAPI overlay utilities (no LLM)."""


@openapi_app.command("normalize")
def normalize(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="External OpenAPI 3.0 document (.json or .yaml).",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Write human-reviewed api.yaml overlay subset here.",
    ),
    schema: Optional[Path] = typer.Option(
        None,
        "--schema",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Prisma schema — subtract Role 1 base paths and Prisma DTO schemas.",
    ),
) -> None:
    """Strip framework noise from external OpenAPI → ``api.yaml`` overlay subset (FR-D1)."""
    try:
        spec = load_openapi_document(input_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(_EXIT_ERROR) from exc

    schema_text: Optional[str] = None
    if schema is not None:
        schema_text = schema.read_text(encoding="utf-8")

    try:
        result = normalize_openapi_to_overlay(spec, schema_text=schema_text)
    except ValueError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(_EXIT_ERROR) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_overlay_yaml(result.overlay), encoding="utf-8")

    table = Table(title="openapi normalize", show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("paths kept", str(len(result.kept_paths)))
    table.add_row("paths stripped (base)", str(len(result.stripped_paths)))
    table.add_row("schemas stripped (base/prisma)", str(len(result.stripped_schemas)))
    table.add_row("warnings", str(len(result.warnings)))
    console.print(table)

    if result.kept_paths:
        console.print("[green]kept paths[/green]: " + ", ".join(result.kept_paths))
    if result.stripped_paths:
        console.print("[dim]stripped paths[/dim]: " + ", ".join(result.stripped_paths))

    for warning in result.warnings:
        console.print(f"[yellow]warn[/yellow]: {warning}")

    console.print(
        f"[green]done[/green]: wrote {out} — review before `startd8 generate backend --api`."
    )
    raise typer.Exit(_EXIT_OK)
