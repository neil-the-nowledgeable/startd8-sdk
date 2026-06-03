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
from .frontend_codegen.telemetry import record_drift_check, record_render

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
        record_drift_check(result.status)
        color = "green" if result.status == "in_sync" else "yellow"
        console.print(f"[{color}]{result.status}[/{color}]: {result.detail}")
        raise typer.Exit(result.exit_code)

    rendered = render_zod_schema(schema_text, source_file=source_label)
    record_render(rendered)
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


@generate_app.command("backend")
def backend(
    schema: Path = typer.Option(..., "--schema", help="Path to prisma/schema.prisma."),
    out: Path = typer.Option(
        Path("."), "--out", help="Project root to write the app/ package into."
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="Drift-check the on-disk artifacts; write nothing. Exit 0=in-sync, 1=drift.",
    ),
    gate: bool = typer.Option(
        False,
        "--gate",
        help="After writing, run the Python build gate (compileall) over the project.",
    ),
    boot_smoke: bool = typer.Option(
        False,
        "--boot-smoke",
        help="After writing, boot app.main:app in a subprocess and assert it serves "
        "/openapi.json (C-6 runtime gate — catches import errors compileall misses).",
    ),
    ai_passes: Optional[Path] = typer.Option(
        None,
        "--ai-passes",
        help="Path to ai_passes.yaml. When given, also generate the owned AI layer "
        "(service/edge-schemas/harnesses/router + app/server.py) from the manifest.",
    ),
    human_inputs: Optional[Path] = typer.Option(
        None,
        "--human-inputs",
        help="Path to human_inputs.yaml (field-authorship policy; drives the C-4 edge-schema "
        "projection so AI-authored schemas omit human-only fields like Metric.value).",
    ),
    source_label: str = typer.Option(
        "prisma/schema.prisma",
        "--source-label",
        help="Schema path written into the GENERATED headers (must match across runs).",
    ),
) -> None:
    """Render the full all-Python backend (Pydantic + SQLModel + FastAPI + HTMX + derived).

    Deterministic, no LLM. Every artifact is owned/$0.00-skippable; an empty ``app/__init__.py``
    package marker is written but not drift-tracked.
    """
    from .backend_codegen import check_drift as _backend_drift
    from .backend_codegen import is_owned_generated_file, render_backend

    try:
        schema_text = schema.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]error:[/red] cannot read schema {schema}: {exc}")
        raise typer.Exit(_EXIT_ERROR)

    manifest_text: Optional[str] = None
    human_text: Optional[str] = None
    for label, path, dest in (("ai_passes", ai_passes, "manifest"), ("human_inputs", human_inputs, "human")):
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] cannot read {label} {path}: {exc}")
            raise typer.Exit(_EXIT_ERROR)
        if dest == "manifest":
            manifest_text = text
        else:
            human_text = text

    try:
        artifacts = render_backend(
            schema_text,
            source_label,
            manifest_text=manifest_text,
            human_inputs_text=human_text,
        )
    except (
        ValueError
    ) as exc:  # reserved attr name / malformed ai_passes manifest — fail loud
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERROR)

    if check:
        drifted = 0
        for rel, content in artifacts:
            if not is_owned_generated_file(content):
                continue  # the empty package marker — nothing to verify
            target = out / rel
            ondisk = target.read_text(encoding="utf-8") if target.exists() else None
            result = _backend_drift(
                schema_text,
                ondisk,
                source_file=source_label,
                manifest_text=manifest_text,
                human_inputs_text=human_text,
            )
            if result.status != "in_sync":
                drifted += 1
                console.print(
                    f"[yellow]{result.status}[/yellow]: {rel} — {result.detail}"
                )
        if drifted:
            console.print(f"[yellow]{drifted} artifact(s) drifted[/yellow]")
            raise typer.Exit(1)
        console.print(
            f"[green]in_sync[/green]: all {len(artifacts)} artifact(s) match the schema"
        )
        raise typer.Exit(0)

    written = 0
    for rel, content in artifacts:
        target = out / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written += 1
        except OSError as exc:
            console.print(f"[red]error:[/red] cannot write {target}: {exc}")
            raise typer.Exit(_EXIT_ERROR)
    console.print(f"[green]wrote[/green] {written} file(s) under {out}/app")

    if gate:
        from .validators.python_toolchain import run_project_check

        result = run_project_check(str(out), run_mypy=False, run_pytest=False)
        color = "green" if result.is_pass else "red"
        console.print(
            f"[{color}]build gate: {result.verdict}[/{color}] "
            f"(ran {', '.join(result.stages_run) or 'nothing'}; "
            f"skipped {', '.join(result.stages_skipped) or 'nothing'})"
        )
        for d in result.diagnostics:
            console.print(
                f"  [red]{d.stage}[/red] {d.file}:{d.line} {d.code}: {d.message}"
            )
        if not result.is_pass:
            raise typer.Exit(_EXIT_ERROR)

    if boot_smoke:
        from .validators.boot_smoke import run_boot_smoke

        bs = run_boot_smoke(str(out))
        color = "green" if bs.is_pass else "red"
        console.print(
            f"[{color}]boot smoke: {bs.verdict}[/{color}] "
            f"({bs.message}; {len(bs.routes)} route(s) served)"
        )
        for d in bs.diagnostics:
            console.print(f"  [red]{d}[/red]")
        if not bs.is_pass:
            raise typer.Exit(_EXIT_ERROR)
