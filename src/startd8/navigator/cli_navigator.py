"""`startd8 navigator` — build Node views + $0 grounding (Phase 1 / FR-7, FR-9).

Distinct from ``startd8 nav`` (generated-app top-nav registry).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .diff import diff_nodes, node_diff_to_json
from .govern import (
    govern_corpus,
    recurring_finding_classes,
    render_govern_json,
    render_govern_text,
)
from .ground import write_grounding
from .project import nodes_from_json, nodes_to_json, render_nodes_html
from .render_a11y import render_a11y_to_file
from .render_diff import render_navigator_diff_html
from .render_graph import render_navigator_graph_html
from .render_index import render_index_to_file
from .render_tree import render_navigator_tree_html
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
_EXIT_DRIFT = 1  # govern: fail-severity drift (distinct name, same code as build errors by design)
_EXIT_OPERATIONAL = 2  # govern: operational error (missing/not-a-dir)


@navigator_app.command("build")
def build(
    source: str = typer.Option(
        ...,
        "--source",
        help="Node source: capability-index | requirements | node-schema | nodes-json",
    ),
    fmt: str = typer.Option("json", "--format", help="Output format: json | html | a11y"),
    renderer: Optional[str] = typer.Option(
        None, "--renderer",
        help="HTML renderer: wireframe | tree | graph (default: tree for nodes-json, else wireframe)",
    ),
    semantic_only: bool = typer.Option(
        True,
        "--semantic-only/--full-graph",
        help="graph renderer: show only source nodes + semantic edges (default), "
        "or --full-graph to include the visual-editor view-markers",
    ),
    out: Optional[Path] = typer.Option(None, "--out", help="Output path (required for html)"),
    requirements: Optional[Path] = typer.Option(
        None, "--requirements", help="det-req markdown path (source=requirements)"
    ),
    capability_index: Optional[Path] = typer.Option(
        None, "--capability-index", help="Override capability YAML path"
    ),
    nodes_json: Optional[Path] = typer.Option(
        None, "--nodes-json", help="pre-projected NODE-SCHEMA-JSON graph (source=nodes-json)"
    ),
    group_by: str = typer.Option("category", "--group-by", help="Section grouping axis"),
    open_depth: int = typer.Option(2, "--open-depth", help="tree renderer: levels open by default"),
    role: Optional[str] = typer.Option(
        None, "--role",
        help="audience lens for tree/a11y labels (e.g. end_user); default None = raw labels "
        "(byte-identical). Not applied to the graph renderer (already lensed).",
    ),
    fluency: str = typer.Option(
        "intermediate", "--fluency", help="fluency lens for tree/a11y labels (with --role)"
    ),
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
        elif source == "nodes-json":
            if nodes_json is None:
                console.print("[red]error:[/red] --nodes-json is required for source=nodes-json")
                raise typer.Exit(_EXIT_ERR)
            data = json.loads(Path(nodes_json).read_text(encoding="utf-8"))
            nodes = nodes_from_json(data.get("nodes", data) if isinstance(data, dict) else data)
            profile = None  # a pre-projected graph brings its own domain; default to the tree renderer
            project_root = str(Path(nodes_json).parent)
        else:
            console.print(
                f"[red]error:[/red] unknown --source {source!r} "
                "(expected capability-index|requirements|node-schema|nodes-json)"
            )
            raise typer.Exit(_EXIT_ERR)
    except (FileNotFoundError, ValueError, OSError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    # Resolve the HTML renderer: explicit --renderer wins; else tree for a pre-projected graph
    # (the adopter seam), wireframe for the flat 2-level sources (back-compat).
    renderer = (renderer or ("tree" if source == "nodes-json" else "wireframe")).strip().lower()

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
        if renderer not in ("tree", "graph", "wireframe"):
            console.print(
                f"[red]error:[/red] unknown --renderer {renderer!r} (expected wireframe|tree|graph)"
            )
            raise typer.Exit(_EXIT_ERR)
        try:
            if renderer == "tree":
                render_navigator_tree_html(
                    list(nodes), out,
                    title=f"Node Navigator — {source}",
                    open_depth=open_depth,
                    role=role,
                    fluency=fluency,
                )
            elif renderer == "graph":
                render_navigator_graph_html(
                    list(nodes), out,
                    title=f"Node Graph — {source}",
                    semantic_only=semantic_only,
                )
            else:  # wireframe
                render_nodes_html(
                    nodes,
                    out,
                    project_root=project_root,
                    group_by=group_by,
                    profile=profile,
                )
        except OSError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(_EXIT_ERR)
        console.print(f"wrote {out} ({len(nodes)} nodes, {renderer})")
        raise typer.Exit(_EXIT_OK)

    if fmt == "a11y":
        # Standalone semantic accessible view (REQ-03 FR-1). Requires --out, like html.
        if out is None:
            console.print("[red]error:[/red] --out is required for --format a11y")
            raise typer.Exit(_EXIT_ERR)
        try:
            render_a11y_to_file(list(nodes), out, title=f"{source}",
                                role=role, fluency=fluency)
        except OSError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(_EXIT_ERR)
        console.print(f"wrote {out} ({len(nodes)} nodes, a11y)")
        raise typer.Exit(_EXIT_OK)

    console.print(f"[red]error:[/red] unknown --format {fmt!r} (expected json|html|a11y)")
    raise typer.Exit(_EXIT_ERR)


def _load_state(path: Path) -> list:
    """Load one diff side: sniff ``.json`` → ``nodes_from_json`` (unwrapping ``{"nodes":[...]}``
    exactly as ``build`` does), else treat as a det-req markdown → ``nodes_from_requirements``.

    Raises the same (FileNotFoundError | ValueError | OSError) the ``build`` guard already catches."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return nodes_from_json(data.get("nodes", data) if isinstance(data, dict) else data)
    return nodes_from_requirements(path)


@navigator_app.command("diff")
def diff(
    before: Path = typer.Option(
        ..., "--before", help="Before state: a det-req markdown OR a nodes-json file"
    ),
    after: Path = typer.Option(
        ..., "--after", help="After state: a det-req markdown OR a nodes-json file"
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Delta HTML output path (required unless --json)"
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the machine-readable NodeDiff (for CI) instead of HTML"
    ),
    max_detail: Optional[int] = typer.Option(
        None, "--max-detail", help="Altitude cap: past N changed keys, render Changed counts-only"
    ),
    role: Optional[str] = typer.Option(
        None, "--role", help="audience lens for labels (e.g. end_user); default None = raw labels"
    ),
    fluency: str = typer.Option(
        "intermediate", "--fluency", help="fluency lens for labels (with --role)"
    ),
) -> None:
    """Diff two states of the Node corpus and render the delta (REQ-07).

    ``--before``/``--after`` each accept a requirements doc OR a nodes-json file. Writes a standalone
    delta HTML (added/removed/changed + status transitions + new dangling refs) to ``--out``, or the
    machine-readable NodeDiff to stdout with ``--json``. Additive: leaves build/ground/index/govern
    untouched. Exit 0 = ok · 1 = error (bad input / missing --out).
    """
    try:
        before_nodes = _load_state(before)
        after_nodes = _load_state(after)
    except (FileNotFoundError, ValueError, OSError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    delta = diff_nodes(before_nodes, after_nodes)

    if as_json:
        text = json.dumps(node_diff_to_json(delta), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        if out is None:
            sys.stdout.write(text)
        else:
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text, encoding="utf-8")
            except OSError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(_EXIT_ERR)
            console.print(f"wrote {out} (NodeDiff json)")
        raise typer.Exit(_EXIT_OK)

    if out is None:
        console.print("[red]error:[/red] --out is required (unless --json)")
        raise typer.Exit(_EXIT_ERR)
    try:
        render_navigator_diff_html(
            delta, out,
            title=f"Node Corpus Delta — {before.name} → {after.name}",
            max_detail=max_detail,
            role=role,
            fluency=fluency,
        )
    except OSError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)
    r = delta.rollup
    console.print(
        f"wrote {out} (+{r['added']} / -{r['removed']} / ~{r['changed']}, "
        f"{r['unchanged']} unchanged)"
    )
    raise typer.Exit(_EXIT_OK)


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


@navigator_app.command("index")
def index(
    directory: Path = typer.Option(
        ..., "--dir", help="Directory of requirement docs (REQ-*.md) to index"
    ),
    out: Path = typer.Option(..., "--out", help="Corpus index HTML output path"),
    title: str = typer.Option("Requirements", "--title", help="Corpus index title"),
) -> None:
    """Render a directory of requirement docs as a drill-to-leaf corpus index (REQ-03 FR-2).

    Writes an index page + one a11y leaf per parseable doc (each via `--format a11y`), with
    resolving relative hrefs. An unparseable doc degrades to a non-linked row.
    """
    directory = Path(directory)
    if not directory.is_dir():
        console.print(f"[red]error:[/red] --dir {directory} is not a directory")
        raise typer.Exit(_EXIT_ERR)
    try:
        render_index_to_file(directory, out, title=title)
    except OSError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)
    n = len(sorted(directory.glob("REQ-*.md")))
    console.print(f"wrote {out} ({n} requirements indexed)")
    raise typer.Exit(_EXIT_OK)


@navigator_app.command("govern")
def govern(
    directory: Path = typer.Option(
        ..., "--dir", help="Directory of requirement docs (REQ-*.md) to govern"
    ),
    fmt: str = typer.Option("text", "--format", help="Report format: text | json"),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write the report to a path (default: stdout)"
    ),
) -> None:
    """Govern a directory of requirement docs against the corpus contract (REQ-06, read-only).

    Runs the fixed 5-check battery (name-block presence · single-line-FR · dangling cross-ref ·
    coverage · index-freshness) and emits a pass/fail governance report. Read-only: never writes
    into the corpus. Exit 0 = clean · 1 = drift (any fail-severity finding) · 2 = operational error.
    """
    directory = Path(directory)
    if not directory.is_dir():
        console.print(f"[red]error:[/red] --dir {directory} is not a directory")
        raise typer.Exit(_EXIT_OPERATIONAL)
    fmt = fmt.strip().lower()
    if fmt not in ("text", "json"):
        console.print(f"[red]error:[/red] unknown --format {fmt!r} (expected text|json)")
        raise typer.Exit(_EXIT_OPERATIONAL)
    try:
        report = govern_corpus(directory)
        rendered = render_govern_json(report) if fmt == "json" else render_govern_text(report)
    except OSError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_OPERATIONAL)

    if out is not None:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(_EXIT_OPERATIONAL)
        console.print(f"wrote {out} (exit {report.exit_code})")
    else:
        sys.stdout.write(rendered if rendered.endswith("\n") else rendered + "\n")

    # FR-7: a finding-class recurring across many docs is a class to metabolize, not to re-file.
    recurring = recurring_finding_classes(report)
    if recurring:
        for check, n_docs in sorted(recurring.items()):
            console.print(
                f"[yellow]recurring:[/yellow] {check} fails across {n_docs} docs — "
                f"route to /metabolize-finding to make the class structurally impossible."
            )

    raise typer.Exit(_EXIT_DRIFT if not report.clean else _EXIT_OK)
