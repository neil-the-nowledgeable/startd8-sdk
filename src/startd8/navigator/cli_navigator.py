"""`startd8 navigator` — build Node views + $0 grounding (Phase 1 / FR-7, FR-9).

Distinct from ``startd8 nav`` (generated-app top-nav registry).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from .ground import write_grounding
from .project import nodes_to_json, render_nodes_html
from .sources_capability import (
    CAPABILITY_PROFILE,
    default_capability_index_path,
    nodes_from_capability_index,
)
from .sources_node_schema import NODE_SCHEMA_PROFILE, nodes_from_node_schema
from .sources_requirements import REQUIREMENTS_PROFILE, nodes_from_requirements

navigator_app = typer.Typer(
    help="NODE-SCHEMA navigator — render requirements / capability-index as Nodes.",
    no_args_is_help=True,
)
console = Console()

_EXIT_OK = 0
_EXIT_ERR = 1


@navigator_app.command("build")
def build(
    source: str = typer.Option(
        ...,
        "--source",
        help="Node source: capability-index | requirements | node-schema",
    ),
    fmt: str = typer.Option("json", "--format", help="Output format: json | html"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output path (required for html)"),
    requirements: Optional[Path] = typer.Option(
        None, "--requirements", help="det-req markdown path (source=requirements)"
    ),
    capability_index: Optional[Path] = typer.Option(
        None, "--capability-index", help="Override capability YAML path"
    ),
    group_by: str = typer.Option("category", "--group-by", help="Section grouping axis"),
) -> None:
    """Project a source into Nodes and write JSON or HTML."""
    source = source.strip().lower()
    fmt = fmt.strip().lower()
    try:
        if source == "capability-index":
            path = capability_index or default_capability_index_path()
            nodes = nodes_from_capability_index(path)
            profile = CAPABILITY_PROFILE
            project_root = str(path.parent)
        elif source == "requirements":
            if requirements is None:
                console.print("[red]error:[/red] --requirements is required for source=requirements")
                raise typer.Exit(_EXIT_ERR)
            nodes = nodes_from_requirements(requirements)
            profile = REQUIREMENTS_PROFILE
            project_root = str(requirements.parent)
        elif source == "node-schema":
            nodes = nodes_from_node_schema()
            profile = NODE_SCHEMA_PROFILE
            project_root = "."
        else:
            console.print(
                f"[red]error:[/red] unknown --source {source!r} "
                "(expected capability-index|requirements|node-schema)"
            )
            raise typer.Exit(_EXIT_ERR)
    except (FileNotFoundError, ValueError, OSError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    if fmt == "json":
        payload = {"source": source, "nodes": nodes_to_json(nodes)}
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        if out is None:
            sys.stdout.write(text)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            console.print(f"wrote {out} ({len(nodes)} nodes)")
        raise typer.Exit(_EXIT_OK)

    if fmt == "html":
        if out is None:
            console.print("[red]error:[/red] --out is required for --format html")
            raise typer.Exit(_EXIT_ERR)
        render_nodes_html(
            nodes,
            out,
            project_root=project_root,
            group_by=group_by,
            profile=profile,
        )
        console.print(f"wrote {out} ({len(nodes)} nodes)")
        raise typer.Exit(_EXIT_OK)

    console.print(f"[red]error:[/red] unknown --format {fmt!r} (expected json|html)")
    raise typer.Exit(_EXIT_ERR)


@navigator_app.command("ground")
def ground(
    root: Path = typer.Option(Path("src"), "--root", help="Tree to scan for FR-/capability keys"),
    out: Path = typer.Option(..., "--out", help="Grounding JSON output path"),
) -> None:
    """$0 mention-count grounding pass (FR-9)."""
    root = Path(root)
    if not root.exists():
        console.print(
            f"[red]error:[/red] --root {root} does not exist "
            f"(cwd={Path.cwd()}). Run from the startd8-sdk repo, or pass an absolute path."
        )
        raise typer.Exit(_EXIT_ERR)
    try:
        payload = write_grounding(root, out)
    except OSError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)
    console.print(
        f"wrote {out} ({payload['key_count']} keys, grounded {payload['grounded']})"
    )
    raise typer.Exit(_EXIT_OK)
