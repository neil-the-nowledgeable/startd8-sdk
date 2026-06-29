"""`startd8 nav` — inspect the default top-navigation registry (deterministic, $0).

The always-on nav (FR-13) is visible by default and hidden per-item via a runtime ``nav.config.json``
(FR-6). ``nav keys`` makes that config authorable without reading source: it prints every nav entry's
stable ``key`` (what goes in the config's ``hidden`` list), plus its label/href/group, for the same
schema + manifests ``generate backend`` would use (FR-21).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

nav_app = typer.Typer(help="Inspect the default top-navigation registry.")
console = Console()

_EXIT_ERROR = 2


def _read(path: Optional[Path], label: str) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]error:[/red] cannot read {label} {path}: {exc}")
        raise typer.Exit(_EXIT_ERROR)


@nav_app.command("keys")
def keys(
    schema: Path = typer.Option(..., "--schema", help="Path to prisma/schema.prisma."),
    pages: Optional[Path] = typer.Option(None, "--pages", help="Path to pages.yaml (optional)."),
    views: Optional[Path] = typer.Option(None, "--views", help="Path to views.yaml (optional)."),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the registry as JSON (for scripting / CI)."
    ),
    config_template: bool = typer.Option(
        False,
        "--config-template",
        help="Instead of the table, print a ready-to-edit nav.config.json with every key listed "
        "(all commented-in under `hidden` would hide everything — delete the ones you want visible).",
    ),
) -> None:
    """Print the nav registry (key/label/href/group) — the keys are what `nav.config.json` hides (FR-21)."""
    from .backend_codegen.nav_generator import nav_registry

    schema_text = _read(schema, "schema") or ""
    try:
        entries = nav_registry(schema_text, _read(views, "views"), _read(pages, "pages"))
    except ValueError as exc:  # malformed schema / manifest — fail loud, same as generate
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERROR)

    if config_template:
        # A starting nav.config.json: every key listed so the operator deletes what should stay visible.
        console.print(json.dumps({"hidden": [e.key for e in entries]}, indent=2))
        return
    if as_json:
        console.print(
            json.dumps(
                [{"key": e.key, "label": e.label, "href": e.href, "group": e.group} for e in entries],
                indent=2,
            )
        )
        return

    table = Table(title="Default navigation registry")
    table.add_column("key", style="cyan", no_wrap=True)
    table.add_column("label")
    table.add_column("href", style="green")
    table.add_column("group")
    for e in entries:
        table.add_row(e.key, e.label, e.href, e.group)
    console.print(table)
    console.print(
        '\nHide an item across restarts: add its [cyan]key[/cyan] to "hidden" in '
        "[green]nav.config.json[/green] at the app root, then restart "
        "(or `startd8 nav keys --config-template` to scaffold the file)."
    )
