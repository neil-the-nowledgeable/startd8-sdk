# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""project CLI command group (extracted from cli.py, Pass E)."""

from typing import Optional, List
from pathlib import Path
import typer
from .cli_shared import console


project_app = typer.Typer(
    name="project",
    help="Project scaffolding and initialization commands"
)


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Name of the new project"),
    template: str = typer.Option("basic-python", "--template", "-t", help="Template to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite conflicting files regardless of hash state")
):
    """Scaffold a new project or safely update an existing one using hybrid manifest tracking."""
    try:
        from .project.scaffolder import scaffold_project
    except ImportError as e:
        console.print(f"[red]Failed to load project scaffolder: {e}[/red]")
        raise typer.Exit(1)

    result = scaffold_project(
        name=name,
        template=template,
        output_dir=output,
        force=force
    )

    if not result.success:
        console.print(f"[red]Scaffolding Failed:[/red] {result.error}")
        raise typer.Exit(1)
        
    console.print(f"\n[green]Scaffolded {result.files_created} new file(s)[/green]")
    if result.files_updated > 0:
        console.print(f"[cyan]Safely updated {result.files_updated} file(s)[/cyan]")
    if result.files_skipped > 0:
        console.print(f"[yellow]Skipped {result.files_skipped} modified file(s) to protect custom logic[/yellow]")
