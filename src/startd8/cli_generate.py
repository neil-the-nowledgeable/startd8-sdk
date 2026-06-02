"""`startd8 generate frontend` — deterministic frontend code generation (Inc 8 / FR-8A, FR-11).

A no-LLM command that renders the Prisma→Zod schema file, or (with ``--check``) reports
drift without writing. Kept dependency-light (no framework/provider imports) so it loads
fast and is unit-testable in isolation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .frontend_codegen import check_drift, plan_frontend_skeleton, render_zod_schema
from .frontend_codegen.drift import ERROR as _EXIT_ERROR

console = Console()

generate_app = typer.Typer(help="Deterministic frontend code generation (no LLM).")


@generate_app.callback()
def _generate_callback() -> None:
    """Deterministic, no-LLM code generation (use `generate frontend`)."""
    # Presence of a callback keeps this a command *group* (so the `frontend` subcommand
    # name is required) instead of collapsing into a single-command app.


@generate_app.command("frontend")
def frontend(
    schema: Path = typer.Option(..., "--schema", help="Path to prisma/schema.prisma."),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output path for the Zod schema file (e.g. lib/value-model.ts).",
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", help="Project root, for convention-detection notes."
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="Drift-check only; write nothing. Exit 0=in-sync, 1=drift, 2=error.",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero if any field is unrenderable."
    ),
    source_label: str = typer.Option(
        "prisma/schema.prisma",
        "--source-label",
        help="Schema path written into the GENERATED header (must match across runs).",
    ),
) -> None:
    """Render the Prisma→Zod schema file deterministically (no LLM)."""
    try:
        schema_text = schema.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]error:[/red] cannot read schema {schema}: {exc}")
        raise typer.Exit(_EXIT_ERROR)

    if check:
        try:
            ondisk = out.read_text(encoding="utf-8") if out.exists() else None
        except OSError as exc:
            console.print(f"[red]error:[/red] cannot read {out}: {exc}")
            raise typer.Exit(_EXIT_ERROR)
        result = check_drift(schema_text, ondisk, source_file=source_label)
        color = "green" if result.status == "in_sync" else "yellow"
        console.print(f"[{color}]{result.status}[/{color}]: {result.detail}")
        raise typer.Exit(result.exit_code)

    rendered = render_zod_schema(schema_text, source_file=source_label)
    if rendered.unrenderable:
        console.print(
            f"[yellow]{len(rendered.unrenderable)} unrenderable field(s):[/yellow]"
        )
        for u in rendered.unrenderable:
            console.print(f"  - {u.entity}.{u.field} ({u.prisma_type}): {u.reason}")
        if strict:
            console.print(
                "[red]--strict:[/red] refusing to write with unrenderable fields"
            )
            raise typer.Exit(_EXIT_ERROR)

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered.text, encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]error:[/red] cannot write {out}: {exc}")
        raise typer.Exit(_EXIT_ERROR)
    console.print(
        f"[green]wrote[/green] {out}  (schema-sha256 {rendered.schema_sha256[:12]}…)"
    )

    if project is not None:
        plan = plan_frontend_skeleton(
            project, schema_text, schema_out=str(out), source_file=source_label
        )
        for note in plan.notes:
            console.print(f"  [dim]note:[/dim] {note}")
