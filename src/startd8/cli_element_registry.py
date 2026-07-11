# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""element_registry CLI command group (extracted from cli.py, Pass E)."""

from typing import Optional, List
from pathlib import Path
from .paths import default_data_dir
from rich.table import Table
import typer
from .cli_shared import console


element_registry_app = typer.Typer(
    name="element-registry",
    help="Inspect and manage the element registry"
)


def _get_element_registry(state_dir: Optional[Path] = None):
    """Create an ElementRegistry pointing at the project state directory."""
    from .element_registry import ElementRegistry

    base = state_dir or default_data_dir() / "state"
    return ElementRegistry(state_dir=base)


@element_registry_app.command("list")
def element_registry_list(
    state_dir: Optional[Path] = typer.Option(
        None, "--state-dir", "-s", help="Registry state directory"
    ),
):
    """List all registered elements."""
    registry = _get_element_registry(state_dir)
    entries = registry.all_entries()

    table = Table(title="Element Registry")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Kind", style="magenta")
    table.add_column("Name", style="green")
    table.add_column("File", style="dim")

    for entry in entries:
        table.add_row(
            entry.element_id,
            entry.kind,
            entry.name,
            entry.file_path or "",
        )

    console.print(table)
    if not entries:
        console.print("[dim]No elements registered.[/dim]")


@element_registry_app.command("show")
def element_registry_show(
    element_id: str = typer.Argument(..., help="Element ID to look up"),
    state_dir: Optional[Path] = typer.Option(
        None, "--state-dir", "-s", help="Registry state directory"
    ),
):
    """Show details for a specific element."""
    registry = _get_element_registry(state_dir)
    entry = registry.get(element_id)

    if entry is None:
        console.print(f"[red]Error: element not found: {element_id}[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Element: {entry.element_id}", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("ID", entry.element_id)
    table.add_row("Kind", entry.kind)
    table.add_row("Name", entry.name)
    table.add_row("File", entry.file_path or "N/A")
    table.add_row("Parent Class", entry.parent_class or "N/A")
    table.add_row("Line", str(entry.line) if entry.line is not None else "N/A")
    table.add_row("Contract ID", entry.source_contract_id or "N/A")
    table.add_row("Context Checksum", entry.context_checksum or "N/A")

    if entry.phases:
        phase_lines = []
        for phase, records in entry.phases.items():
            latest = records[-1].status if records else "unknown"
            phase_lines.append(f"{phase}: {latest}")
        table.add_row("Phases", "\n".join(phase_lines))
    else:
        table.add_row("Phases", "N/A")

    console.print(table)


@element_registry_app.command("lineage")
def element_registry_lineage(
    element_id: str = typer.Argument(..., help="Element ID to look up"),
    state_dir: Optional[Path] = typer.Option(
        None, "--state-dir", "-s", help="Registry state directory"
    ),
):
    """Show the full lineage (time-sorted history) for an element."""
    registry = _get_element_registry(state_dir)
    lineage = registry.element_lineage(element_id)

    if lineage is None:
        console.print(f"[red]Error: element not found: {element_id}[/red]")
        raise typer.Exit(1)

    if not lineage.history:
        console.print(f"[dim]No history records found for {element_id}.[/dim]")
        return

    table = Table(title=f"Lineage: {element_id}")
    table.add_column("Timestamp", style="dim")
    table.add_column("Phase")
    table.add_column("Status")
    table.add_column("Detail")

    for record in lineage.history:
        detail = record.metadata.get("detail", "") if record.metadata else ""
        table.add_row(
            record.timestamp or "N/A",
            record.phase,
            record.status,
            str(detail),
        )

    console.print(table)

    if lineage.current_phases:
        summary = Table(title="Current Phase Status", show_header=False)
        summary.add_column("Phase", style="bold")
        summary.add_column("Status")
        for phase, status in lineage.current_phases.items():
            summary.add_row(phase, status)
        console.print(summary)


@element_registry_app.command("stats")
def element_registry_stats(
    state_dir: Optional[Path] = typer.Option(
        None, "--state-dir", "-s", help="Registry state directory"
    ),
):
    """Report reuse statistics as JSON."""
    import json as _json

    registry = _get_element_registry(state_dir)
    s = registry.summary()

    output = {
        "total_entries": s.total,
        "entries_by_kind": s.by_kind,
        "files_covered": s.files_covered,
        "by_phase_status": s.by_phase_status,
    }

    console.print(_json.dumps(output, indent=2))


@element_registry_app.command("clear")
def element_registry_clear(
    state_dir: Optional[Path] = typer.Option(
        None, "--state-dir", "-s", help="Registry state directory"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
):
    """Clear all entries from the registry."""
    registry = _get_element_registry(state_dir)
    count = len(registry)

    if count == 0:
        console.print("[dim]Registry is already empty.[/dim]")
        return

    if not yes:
        confirm = typer.confirm(
            f"This will remove {count} element(s) from the registry. Continue?"
        )
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    registry.clear()
    console.print(f"[green]Cleared {count} element(s) from the registry.[/green]")
