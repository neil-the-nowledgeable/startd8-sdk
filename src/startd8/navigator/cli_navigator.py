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
from .sources_requirements import nodes_from_requirements, requirements_profile_for
from .view_definition import (
    BASE_NAVIG8R_DEFINITION,
    DEFINITION_REGISTRY,
    definition_diff,
    load_definition,
    resolve,
    resolve_external,
    to_render_profile,
    validate_definitions,
)

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
    frame_mode = False  # REQ-15: bare-frame render (scaffold-on, region content hidden)
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
            # FR-17: masthead identity (eyebrow=key · headline=H1 title · sub=semantic name) derived
            # from THIS requirement, not the static 'This spec' / 'A first look at this spec' copy.
            profile = requirements_profile_for(requirements)
            project_root = str(requirements.parent)
        elif source == "node-schema":
            nodes = nodes_from_node_schema()
            profile = NODE_SCHEMA_PROFILE
            project_root = "."
        elif source == "frame":
            # REQ-15: the domain-neutral bare frame — the View Definition's scaffolding, free of any
            # requirement. Zero nodes + the base profile (theme/control/regions), rendered scaffold-on
            # with all region content hidden (only the region meta-descriptions + control surface show).
            nodes = []
            profile = to_render_profile(resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY))
            project_root = "."
            frame_mode = True
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
                "(expected capability-index|requirements|node-schema|frame|nodes-json)"
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
                    frame=frame_mode,
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


def _validate_node_json(node_list, path: Path, where: str) -> None:
    """Structurally validate a decoded nodes-json payload BEFORE handing it to ``nodes_from_json``.

    ``nodes_from_json`` assumes each entry is a ``dict`` (and each ``lives`` element a ``dict``) and
    recurses into ``children``; a structurally-wrong-but-valid-JSON payload would otherwise leak an
    ``AttributeError``/``TypeError`` as a raw traceback out of the CLI. Raises ``ValueError`` (which
    the ``diff`` guard catches) with a path-qualified message. Recurses into ``children``."""
    if not isinstance(node_list, list):
        raise ValueError(
            f"{path}: expected a JSON array of node objects (or a {{'nodes': [...]}} object) "
            f"for {where}, got {type(node_list).__name__}"
        )
    for i, entry in enumerate(node_list):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path}: {where} entry #{i} is a {type(entry).__name__}, expected an object"
            )
        lives = entry.get("lives")
        if lives is not None and (
            not isinstance(lives, list) or any(not isinstance(ev, dict) for ev in lives)
        ):
            raise ValueError(f"{path}: {where} entry #{i} ('lives') must be a list of objects")
        children = entry.get("children")
        if children is not None:
            _validate_node_json(children, path, "children")


def _load_state(path: Path) -> list:
    """Load one diff side: sniff ``.json`` → ``nodes_from_json`` (unwrapping ``{"nodes":[...]}``
    exactly as ``build`` does), else treat as a det-req markdown → ``nodes_from_requirements``.

    Raises the same (FileNotFoundError | ValueError | OSError) the ``build`` guard already catches.
    A well-formed-JSON-but-structurally-wrong payload (a bare scalar, a non-object node entry, a
    non-object ``lives`` element) is normalized to a ``ValueError`` here — ``nodes_from_json`` itself
    assumes ``dict``-shaped entries and would otherwise leak an ``AttributeError``/``TypeError`` as a
    raw traceback out of the CLI."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        # JSONDecodeError / UnicodeDecodeError are ValueError subclasses (caught by the caller).
        data = json.loads(path.read_text(encoding="utf-8"))
        node_list = data.get("nodes", data) if isinstance(data, dict) else data
        _validate_node_json(node_list, path, "node list")
        return nodes_from_json(node_list)
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


@navigator_app.command("view-definition")
def view_definition(
    name: Optional[str] = typer.Option(
        None, "--name",
        help="Definition to resolve + dump (e.g. requirements | capability | node-schema | base). "
        "Omit to dump the whole registry.",
    ),
    resolved: bool = typer.Option(
        True, "--resolved/--raw",
        help="Dump the RESOLVED definition (extends chain flattened, default) or the raw authored delta.",
    ),
    diff: bool = typer.Option(
        False, "--diff",
        help="With --name: dump only the leaves this domain overrides/adds vs the base (its delta).",
    ),
    validate: bool = typer.Option(
        False, "--validate",
        help="Govern the registry: check every definition resolves + bindings reference known fields. "
        "Exit 0=clean, 1=issues (EC-6).",
    ),
    from_file: Optional[Path] = typer.Option(
        None, "--from",
        help="Consume an EXTERNAL VIEW-SCHEMA JSON file (REQ-13): load it, resolve against the shipped "
        "base, validate, and dump the resolved JSON. The cross-repo import seam.",
    ),
) -> None:
    """Dump a View Definition (REQ-10) as JSON — the cross-repo ``VIEW-SCHEMA`` seam.

    Serializes via the definition's own ``to_dict`` so an off-repo adopter (legal · benchmark · dev-os)
    can author its presentation as a base + a thin delta and consume it without importing Python.
    ``--name`` selects one definition; omitted, it dumps every definition in the registry. ``--diff``
    (with ``--name``) shows only what that domain overrides/adds vs the base (EC-4). ``--validate``
    governs the whole registry (EC-6). ``--from`` consumes an external VIEW-SCHEMA file (REQ-13 import).
    """
    if validate:
        issues = validate_definitions(DEFINITION_REGISTRY)
        if issues:
            for issue in issues:
                console.print(f"[red]definition:[/red] {issue}")
            raise typer.Exit(_EXIT_ERR)
        console.print(f"[green]ok:[/green] {len(DEFINITION_REGISTRY)} definitions valid")
        raise typer.Exit(_EXIT_OK)
    if from_file is not None:
        # REQ-13: consume an externally-authored definition — load, resolve against the shipped base,
        # validate the augmented registry, then dump the resolved JSON (the second-repo import proof).
        try:
            external = load_definition(from_file)
            augmented = {**DEFINITION_REGISTRY, external.name: external}
            issues = validate_definitions(augmented)
            if issues:
                for issue in issues:
                    console.print(f"[red]external:[/red] {issue}")
                raise typer.Exit(_EXIT_ERR)
            payload = resolve_external(external).to_dict()
        except (OSError, ValueError) as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(_EXIT_ERR)
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
        raise typer.Exit(_EXIT_OK)
    try:
        if name is not None:
            key = name.strip().lower()
            if key not in DEFINITION_REGISTRY:
                console.print(
                    f"[red]error:[/red] unknown definition {name!r} "
                    f"(known: {', '.join(sorted(DEFINITION_REGISTRY))})"
                )
                raise typer.Exit(_EXIT_ERR)
            defn = DEFINITION_REGISTRY[key]
            if diff:
                payload = definition_diff(defn, BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY)
            else:
                payload = resolve(defn, DEFINITION_REGISTRY).to_dict() if resolved else defn.to_dict()
        else:
            payload = {
                k: (resolve(d, DEFINITION_REGISTRY).to_dict() if resolved else d.to_dict())
                for k, d in DEFINITION_REGISTRY.items()
            }
    except (KeyError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
    raise typer.Exit(_EXIT_OK)
