"""`startd8 navigator` — build Node views + $0 grounding (Phase 1 / FR-7, FR-9).

Distinct from ``startd8 nav`` (generated-app top-nav registry).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

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
from .render_a11y import (
    render_a11y_graph_to_file,
    render_a11y_to_file,
    render_a11y_tree_to_file,
)
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
from .sources_pipeline import (
    PIPELINE_PROFILE,
    nodes_from_pipeline,
    stages as pipeline_stages,
)
from .sources_requirements import nodes_from_requirements, requirements_profile_for
from .provenance import _FR_ID_RE, pipeline_provenance
from .verify_oracle import (
    OracleDescriptor,
    OracleVerdict,
    aggregate_exit_code,
    classify,
    evaluate,
    verdict_to_dict,
)
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
        help="Node source: capability-index | requirements | requirements+capabilities | node-schema | pipeline | nodes-json",
    ),
    fmt: str = typer.Option(
        "json", "--format", help="Output format: json | html | a11y"
    ),
    renderer: Optional[str] = typer.Option(
        None,
        "--renderer",
        help="HTML renderer: wireframe | tree | graph (default: tree for nodes-json, else wireframe)",
    ),
    semantic_only: bool = typer.Option(
        True,
        "--semantic-only/--full-graph",
        help="graph renderer: show only source nodes + semantic edges (default), "
        "or --full-graph to include the visual-editor view-markers",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output path (required for html)"
    ),
    requirements: Optional[Path] = typer.Option(
        None, "--requirements", help="det-req markdown path (source=requirements)"
    ),
    capability_index: Optional[Path] = typer.Option(
        None, "--capability-index", help="Override capability YAML path"
    ),
    nodes_json: Optional[Path] = typer.Option(
        None,
        "--nodes-json",
        help="pre-projected NODE-SCHEMA-JSON graph (source=nodes-json)",
    ),
    group_by: str = typer.Option(
        "category", "--group-by", help="Section grouping axis"
    ),
    open_depth: int = typer.Option(
        2, "--open-depth", help="tree renderer: levels open by default"
    ),
    role: Optional[str] = typer.Option(
        None,
        "--role",
        help="audience lens for tree/a11y labels (e.g. end_user); default None = raw labels "
        "(byte-identical). Not applied to the graph renderer (already lensed).",
    ),
    fluency: str = typer.Option(
        "intermediate",
        "--fluency",
        help="fluency lens for tree/a11y labels (with --role)",
    ),
    realization_provenance: Optional[Path] = typer.Option(
        None,
        "--realization-provenance",
        help="REQ-19: an emitted realization-provenance JSON artifact; grounds the determinism-% as "
        "`measured` (else the declared fallback). Applies to --format html --renderer wireframe.",
    ),
    rank_direction: Optional[str] = typer.Option(
        None,
        "--rank-direction",
        help="REQ-composition-rollup: graph layout rank. `ground-up` ranks capabilities above their "
        "composing features (bottom-up rollup); default (unset) keeps the current layout byte-identical. "
        "Applies to --renderer graph.",
    ),
    cross_link: Optional[List[str]] = typer.Option(
        None,
        "--cross-link",
        help="Move 1: a cross-topology link from the full-page requirement view, as "
        "`<topology>=<url-template>` (repeatable). The template may contain `{key}`, substituted by the "
        "requirement's key, e.g. `--cross-link a11y=reqs.a11y.html#{key}`. Author-supplied (the navigator "
        "fabricates no sibling path/anchor → no dead links); absent → byte-identical.",
    ),
) -> None:
    """Project a source into Nodes and write JSON or HTML."""
    source = source.strip().lower()
    fmt = fmt.strip().lower()
    frame_mode = False  # REQ-15: the domain-neutral bare-frame render
    # Move 1 FR-3/FR-4: parse the authored `<topology>=<url-template>` cross-links (verbatim, no fabrication).
    cross_links: Dict[str, str] = {}
    for cl in cross_link or []:
        if "=" not in cl:
            console.print(
                f"[red]error:[/red] --cross-link must be <topology>=<url-template>, got {cl!r}"
            )
            raise typer.Exit(_EXIT_ERR)
        topo, url = cl.split("=", 1)
        if topo.strip() and url.strip():
            cross_links[topo.strip()] = url.strip()
    try:
        if source == "capability-index":
            path = capability_index or default_capability_index_path()
            nodes = nodes_from_capability_index(path)
            profile = CAPABILITY_PROFILE
            project_root = str(path.parent)
        elif source == "requirements":
            if requirements is None:
                console.print(
                    "[red]error:[/red] --requirements is required for source=requirements"
                )
                raise typer.Exit(_EXIT_ERR)
            nodes = nodes_from_requirements(requirements)
            # Seat-req FR-6 (R1-F4): the parse-loss FLOOR — the projection must not SILENTLY drop a
            # hard-wrapped FR. Assert the projected node count equals the source's FR-marker count; a
            # mismatch (a dropped FR) exits non-zero with a named parse-loss (symmetry with FR-3's
            # fail-loud round-trip gate — the same round-trip must not lose FRs on the render side).
            import re as _re

            _markers = len(
                _re.findall(
                    r"^- \*\*FR-",
                    requirements.read_text(encoding="utf-8"),
                    _re.MULTILINE,
                )
            )
            if _markers and len(nodes) != _markers:
                console.print(
                    f"[red]error:[/red] parse-loss — {len(nodes)} node(s) projected from {_markers} FR "
                    f"marker(s) in {Path(requirements).name}: a hard-wrapped FR dropped fields the "
                    f"per-line parser can't see. Rejoin the FR to one physical line."
                )
                raise typer.Exit(_EXIT_ERR)
            # FR-17: masthead identity (eyebrow=key · headline=H1 title · sub=semantic name) derived
            # from THIS requirement, not the static 'This spec' / 'A first look at this spec' copy.
            profile = requirements_profile_for(requirements)
            project_root = str(requirements.parent)
        elif source in ("requirements+capabilities", "requirements+capability"):
            # REQ-feature-capability-composition-rollup FR-2: join the feature nodes and the capability
            # nodes into ONE node set so a feature→capability `serves` edge has BOTH endpoints present
            # (the add_semantic guard drops an edge whose target isn't in the graph). Neither source
            # function is modified — this concatenates them (composition is additive).
            if requirements is None:
                console.print(
                    "[red]error:[/red] --requirements is required for source=requirements+capabilities"
                )
                raise typer.Exit(_EXIT_ERR)
            req_nodes = list(nodes_from_requirements(requirements))
            cap_path = capability_index or default_capability_index_path()
            cap_nodes = list(nodes_from_capability_index(cap_path))
            nodes = req_nodes + cap_nodes
            profile = requirements_profile_for(requirements)
            project_root = str(requirements.parent)
        elif source == "node-schema":
            nodes = nodes_from_node_schema()
            profile = NODE_SCHEMA_PROFILE
            project_root = "."
        elif source == "pipeline":
            nodes = nodes_from_pipeline()
            # FR-7 (D-5): fold each stage's upstream provenance chain onto its Node's
            # ``attributes["artifact_chain"]`` — surfaces as a tree meta row (render_tree.py), no new
            # shell. The graph renderer shows the stage DAG; the chain is a tree affordance.
            _stages = pipeline_stages()
            for n in nodes:
                chain = pipeline_provenance(
                    nodes, _stages, query=n.attributes.get("sdk_artifact", n.key)
                )
                n.attributes["artifact_chain"] = (
                    " -> ".join(
                        f"{r['stage']}({'built' if r['present'] else 'spec'})"
                        for r in chain
                        if r["stage"]
                    )
                    or "(unowned)"
                )
            profile = PIPELINE_PROFILE
            project_root = "."
        elif source == "frame":
            # REQ-15: the domain-neutral bare frame — the View Definition's scaffolding, free of any
            # requirement. Zero nodes + the base profile (theme/control/regions), rendered scaffold-on
            # with all region content hidden (only the region meta-descriptions + control surface show).
            nodes = []
            profile = to_render_profile(
                resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY)
            )
            project_root = "."
            frame_mode = True
        elif source == "nodes-json":
            if nodes_json is None:
                console.print(
                    "[red]error:[/red] --nodes-json is required for source=nodes-json"
                )
                raise typer.Exit(_EXIT_ERR)
            data = json.loads(Path(nodes_json).read_text(encoding="utf-8"))
            nodes = nodes_from_json(
                data.get("nodes", data) if isinstance(data, dict) else data
            )
            profile = None  # a pre-projected graph brings its own domain; default to the tree renderer
            project_root = str(Path(nodes_json).parent)
        else:
            console.print(
                f"[red]error:[/red] unknown --source {source!r} "
                "(expected capability-index|requirements|node-schema|pipeline|frame|nodes-json)"
            )
            raise typer.Exit(_EXIT_ERR)
    except (FileNotFoundError, ValueError, OSError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    # Resolve the HTML renderer: explicit --renderer wins; else tree for a pre-projected graph
    # (the adopter seam), wireframe for the flat 2-level sources (back-compat).
    renderer = (
        (renderer or ("tree" if source == "nodes-json" else "wireframe"))
        .strip()
        .lower()
    )

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
                    list(nodes),
                    out,
                    title=f"Node Navigator — {source}",
                    open_depth=open_depth,
                    role=role,
                    fluency=fluency,
                )
            elif renderer == "graph":
                render_navigator_graph_html(
                    list(nodes),
                    out,
                    title=f"Node Graph — {source}",
                    semantic_only=semantic_only,
                    rank_direction=(
                        rank_direction.strip().lower() if rank_direction else None
                    ),
                )
            else:  # wireframe
                # REQ-19: load the measured provenance artifact (if given) → a join source that relabels
                # the determinism-% `measured`. Absent → declared fallback, byte-identical.
                _prov = None
                if realization_provenance is not None:
                    from .realization import MeasuredProvenanceSource
                    from .realization_provenance import load_provenance

                    _prov = MeasuredProvenanceSource(
                        load_provenance(realization_provenance)
                    )
                render_nodes_html(
                    nodes,
                    out,
                    project_root=project_root,
                    group_by=group_by,
                    profile=profile,
                    frame=frame_mode,
                    realization_provenance=_prov,
                    cross_links=cross_links or None,
                )
        except OSError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(_EXIT_ERR)
        console.print(f"wrote {out} ({len(nodes)} nodes, {renderer})")
        raise typer.Exit(_EXIT_OK)

    if fmt == "a11y":
        # REQ-26: a11y is a cross-topology lens — it composes with --renderer. The flat/requirement view
        # (renderer wireframe|None) is byte-identical (REQ-03 FR-7); tree|graph render the accessible
        # semantic view of that topology. Requires --out, like html.
        if out is None:
            console.print("[red]error:[/red] --out is required for --format a11y")
            raise typer.Exit(_EXIT_ERR)
        if renderer not in (None, "wireframe", "tree", "graph"):
            console.print(
                f"[red]error:[/red] unknown --renderer {renderer!r} for a11y "
                "(expected wireframe|tree|graph)"
            )
            raise typer.Exit(_EXIT_ERR)
        try:
            if renderer == "tree":
                render_a11y_tree_to_file(
                    list(nodes),
                    out,
                    title=f"Node tree — {source}",
                    role=role,
                    fluency=fluency,
                )
            elif renderer == "graph":
                render_a11y_graph_to_file(
                    list(nodes),
                    out,
                    title=f"Node graph — {source}",
                    role=role,
                    fluency=fluency,
                )
            else:  # wireframe / None — the flat requirement view (byte-identical, FR-7)
                render_a11y_to_file(
                    list(nodes), out, title=f"{source}", role=role, fluency=fluency
                )
        except OSError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(_EXIT_ERR)
        _topo = renderer if renderer in ("tree", "graph") else "flat"
        console.print(f"wrote {out} ({len(nodes)} nodes, a11y/{_topo})")
        raise typer.Exit(_EXIT_OK)

    console.print(
        f"[red]error:[/red] unknown --format {fmt!r} (expected json|html|a11y)"
    )
    raise typer.Exit(_EXIT_ERR)


# FR-7 (D-D): map an oracle verdict to a NodeStatus for the tree render (no new shell).
_VERDICT_STATUS = {
    "pass": "built",
    "fail": "deprecated",
    "skip": "spec",
    "error": "unknown",
}


@navigator_app.command("verify")
def verify(
    requirements: Path = typer.Option(
        ...,
        "--requirements",
        help="det-req markdown path whose Verify: clauses become the oracle",
    ),
    run_oracle: bool = typer.Option(
        False,
        "--run-oracle",
        help="Opt-in: execute command-shaped Verify: clauses (read-only startd8 navigator subcommands, "
        "argv/no-shell). Default OFF — every clause reports skip, no subprocess.",
    ),
    fmt: str = typer.Option("json", "--format", help="Output format: json | html"),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output path (required for html)"
    ),
    oracle_timeout: int = typer.Option(
        60,
        "--oracle-timeout",
        help="Per-command timeout in seconds under --run-oracle (a timeout is a "
        "distinct fail reason).",
    ),
) -> None:
    """Promote each requirement's ``Verify:`` clause to a checkable acceptance oracle (REQ-08 FR-5/FR-7).

    Emits a per-FR verdict (``pass|fail|skip|error``). Default inert: it evaluates nothing (every clause
    reports ``skip``, no subprocess). Only ``--run-oracle`` executes the extracted command — argv (no
    shell), gated by a read-only ``startd8 navigator`` subcommand allow-list, an argv-token self-exec
    guard, and ``--oracle-timeout``; ``pass`` means only "the extracted command exited 0" (the prose
    assertion rides alongside as the human-checkable residue). Aggregate process exit code: 0 iff no
    ``fail``/``error`` verdict, so CI can gate on it.
    """
    fmt = fmt.strip().lower()
    if fmt not in ("json", "html"):
        console.print(
            f"[red]error:[/red] unknown --format {fmt!r} (expected json|html)"
        )
        raise typer.Exit(_EXIT_ERR)
    try:
        descriptors: List[OracleDescriptor] = classify(requirements)
    except (FileNotFoundError, ValueError, OSError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    verdicts: List[OracleVerdict] = evaluate(
        descriptors, run_oracle=run_oracle, timeout=oracle_timeout
    )
    rc = aggregate_exit_code(verdicts)

    if fmt == "json":
        payload = {
            "requirements": str(requirements),
            "run_oracle": run_oracle,
            "verdicts": [verdict_to_dict(v) for v in verdicts],
        }
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        if out is None:
            sys.stdout.write(text)
        else:
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text, encoding="utf-8")
            except OSError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(_EXIT_ERR)
            console.print(f"wrote {out} ({len(verdicts)} verdicts)")
        raise typer.Exit(rc)

    # fmt == "html": project each verdict to a Node and reuse the existing tree renderer (D-D, no shell).
    if out is None:
        console.print("[red]error:[/red] --out is required for --format html")
        raise typer.Exit(_EXIT_ERR)
    from .models import Node

    verdict_nodes = [
        Node(
            key=v.fr_id or f"verdict-{i}",
            does=f"{v.verdict.upper()} — {v.reason}" if v.reason else v.verdict.upper(),
            status=_VERDICT_STATUS.get(v.verdict, "unknown"),
            category="oracle-verdict",
            attributes={
                "kind": "oracle-verdict",
                "verdict": v.verdict,
                "assertion_text": v.assertion_text,
                "reason": v.reason,
            },
        )
        for i, v in enumerate(verdicts)
    ]
    try:
        render_navigator_tree_html(
            verdict_nodes,
            out,
            title=f"Verify oracle — {requirements.name}",
        )
    except OSError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)
    console.print(f"wrote {out} ({len(verdict_nodes)} verdicts, tree)")
    raise typer.Exit(rc)


@navigator_app.command("provenance")
def provenance(
    query: str = typer.Option(
        ...,
        "--query",
        help="What to trace: an FR id (e.g. FR-3) or a file path. An FR id resolves to the FR's "
        "code Lives:/Touches: file via --requirements (R8-EB-4).",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        help="det-req markdown — required to resolve an FR-id query to its file (ignored for a path query).",
    ),
    fmt: str = typer.Option("json", "--format", help="Output format: json | html"),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output path (required for html)"
    ),
) -> None:
    """Trace an artifact (or an FR) back through the prose→product pipeline stages to its origin (FR-6/FR-9).

    Emits the ordered ``pipeline_provenance`` chain: one row per stage passed through (SPEC/un-built stages
    included so the trace shows the gap), or a single not-found row when nothing owns the artifact. ``--format
    json`` (default) writes the ``{query, chain}`` payload; ``--format html`` (R8-EB-6) projects each chain
    row to a ``Node`` rendered through the existing tree renderer — no new shell, mirroring ``verify --format
    html``. An FR-id ``--query`` resolves against ``--requirements`` to the FR's representative code file. Note
    the stages model the SDK's *compiler* pipeline (seeds → det_req → forward_manifest → backend_codegen →
    test_emitter → docs), so an FR-id traces only when its file falls under one of those; an FR implemented
    elsewhere honestly reports not-found (exit 1).
    """
    fmt = fmt.strip().lower()
    if fmt not in ("json", "html"):
        console.print(
            f"[red]error:[/red] unknown --format {fmt!r} (expected json|html)"
        )
        raise typer.Exit(_EXIT_ERR)
    # A friendly pre-check: an FR-id query needs a corpus to resolve against — name the CLI flag, not
    # the library param (which the not-found row would otherwise surface).
    if _FR_ID_RE.match(query.strip()) and requirements is None:
        console.print(
            "[red]error:[/red] an FR-id query requires --requirements <det-req.md> to resolve"
        )
        raise typer.Exit(_EXIT_ERR)
    if fmt == "html" and out is None:
        console.print("[red]error:[/red] --out is required for --format html")
        raise typer.Exit(_EXIT_ERR)
    _stages = pipeline_stages()
    stage_nodes = nodes_from_pipeline()
    req_nodes = None
    if requirements is not None:
        try:
            req_nodes = nodes_from_requirements(requirements)
        except (FileNotFoundError, ValueError, OSError) as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(_EXIT_ERR)
    chain = pipeline_provenance(
        stage_nodes, _stages, query=query, requirement_nodes=req_nodes
    )
    # A trace that reaches a real stage exits 0; a not-found (unowned / unresolvable FR) exits 1 so a
    # caller/CI can tell "traced" from "nothing owns this".
    traced = any(row.get("stage") is not None for row in chain)
    rc = _EXIT_OK if traced else _EXIT_ERR

    if fmt == "json":
        text = (
            json.dumps(
                {"query": query, "chain": chain},
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            + "\n"
        )
        sys.stdout.write(text)
        raise typer.Exit(rc)

    # fmt == "html" (R8-EB-6): project each chain row to a Node → existing tree renderer (no new shell).
    from .models import Node

    chain_nodes = [
        Node(
            key=str(row.get("stage") or f"row-{i}"),
            does=str(row.get("origin") or ""),
            status="built" if row.get("present") else "spec",
            category="pipeline-provenance",
            attributes={
                "kind": "pipeline-provenance",
                "element": str(row.get("element") or ""),
                "value": str(row.get("value") or ""),
                "present": "true" if row.get("present") else "false",
            },
        )
        for i, row in enumerate(chain)
    ]
    try:
        render_navigator_tree_html(chain_nodes, out, title=f"Provenance — {query}")
    except OSError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)
    console.print(f"wrote {out} ({len(chain_nodes)} rows, tree)")
    raise typer.Exit(rc)


def _validate_node_json(node_list, path: Path, where: str) -> None:
    """Structurally validate a decoded nodes-json payload BEFORE handing it to ``nodes_from_json``.

    ``nodes_from_json`` assumes each entry is a ``dict`` (and each ``lives`` element a ``dict``) and
    recurses into ``children``; a structurally-wrong-but-valid-JSON payload would otherwise leak an
    ``AttributeError``/``TypeError`` as a raw traceback out of the CLI. Raises ``ValueError`` (which
    the ``diff`` guard catches) with a path-qualified message. Recurses into ``children``.
    """
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
            raise ValueError(
                f"{path}: {where} entry #{i} ('lives') must be a list of objects"
            )
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
        False,
        "--json",
        help="Emit the machine-readable NodeDiff (for CI) instead of HTML",
    ),
    a11y: bool = typer.Option(
        False,
        "--a11y",
        help="REQ-26: render the delta as an accessible semantic view (added/removed/changed + "
        "status transitions as navigable regions) instead of the visual delta HTML",
    ),
    max_detail: Optional[int] = typer.Option(
        None,
        "--max-detail",
        help="Altitude cap: past N changed keys, render Changed counts-only",
    ),
    role: Optional[str] = typer.Option(
        None,
        "--role",
        help="audience lens for labels (e.g. end_user); default None = raw labels",
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
        text = (
            json.dumps(
                node_diff_to_json(delta), indent=2, sort_keys=True, ensure_ascii=True
            )
            + "\n"
        )
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
        if a11y:  # REQ-26 FR-4 — the accessible cross-topology view of the diff
            from .render_a11y import render_a11y_diff_to_file

            render_a11y_diff_to_file(
                delta,
                out,
                title=f"Corpus delta — {before.name} → {after.name}",
            )
        else:
            render_navigator_diff_html(
                delta,
                out,
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
    root: Path = typer.Option(
        Path("src"), "--root", help="Tree to scan for FR-/capability keys"
    ),
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
    realization_provenance: Optional[Path] = typer.Option(
        None,
        "--realization-provenance",
        help="REQ-19 FR-6: an emitted realization-provenance JSON artifact; when given, also reports "
        "planned-vs-realized determinism regressions (planned deterministic but measured llm).",
    ),
) -> None:
    """Govern a directory of requirement docs against the corpus contract (REQ-06, read-only).

    Runs the fixed check battery (name-block presence · single-line-FR · dangling cross-ref ·
    coverage · index-freshness) and emits a pass/fail governance report. With ``--realization-provenance``
    it also surfaces determinism regressions (REQ-19 FR-6). Read-only: never writes into the corpus.
    Exit 0 = clean · 1 = drift (any fail-severity finding) · 2 = operational error.
    """
    directory = Path(directory)
    if not directory.is_dir():
        console.print(f"[red]error:[/red] --dir {directory} is not a directory")
        raise typer.Exit(_EXIT_OPERATIONAL)
    fmt = fmt.strip().lower()
    if fmt not in ("text", "json"):
        console.print(
            f"[red]error:[/red] unknown --format {fmt!r} (expected text|json)"
        )
        raise typer.Exit(_EXIT_OPERATIONAL)
    try:
        _prov = None
        if realization_provenance is not None:
            from .realization import MeasuredProvenanceSource
            from .realization_provenance import load_provenance

            _prov = MeasuredProvenanceSource(load_provenance(realization_provenance))
        report = govern_corpus(directory, realization_provenance=_prov)
        rendered = (
            render_govern_json(report) if fmt == "json" else render_govern_text(report)
        )
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


@navigator_app.command("retrospective")
def retrospective(
    directory: Path = typer.Option(
        ..., "--dir", help="Directory of requirement docs (REQ-*.md)"
    ),
    realization_provenance: Path = typer.Option(
        ...,
        "--realization-provenance",
        help="An emitted realization-provenance JSON artifact — its measured regimes surface the "
        "determinism regressions each Lesson derives from (REQ-19 FR-6 → REQ-20).",
    ),
    fmt: str = typer.Option(
        "json", "--format", help="Output format: json | html (graph)"
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output path (required for html)"
    ),
    store: Optional[Path] = typer.Option(
        None,
        "--store",
        help="persist the derived Lessons into a store JSON, MERGING with any prior "
        "run — human dispositions (accept/reject + rationale) are preserved across runs (REQ-20 H3)",
    ),
) -> None:
    """Close the retrospective loop (REQ-20): build a grounded, human-gated Lesson per determinism
    regression, each proposing a `revises` to its offending contract. Read-only on the corpus, never
    auto-applies a revise — the Lessons are `proposed` for a human to accept/reject. With `--store`, the
    Lessons gain cross-run memory (a rejected Lesson stays rejected on the next run)."""
    from .realization import MeasuredProvenanceSource
    from .realization_provenance import load_provenance
    from .sources_retrospective import nodes_from_retrospective

    directory = Path(directory)
    if not directory.is_dir():
        console.print(f"[red]error:[/red] --dir {directory} is not a directory")
        raise typer.Exit(_EXIT_OPERATIONAL)
    fmt = fmt.strip().lower()
    try:
        prov = MeasuredProvenanceSource(load_provenance(realization_provenance))
        lessons = nodes_from_retrospective(directory, prov)
    except (OSError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_OPERATIONAL)

    if store is not None:
        from .lesson_store import load_lessons, merge_lessons, save_lessons

        try:
            lessons = merge_lessons(load_lessons(store), lessons)
            save_lessons(store, lessons)
        except (OSError, ValueError) as exc:
            console.print(f"[red]error:[/red] store {store}: {exc}")
            raise typer.Exit(_EXIT_OPERATIONAL)

    if fmt == "json":
        payload = {"source": "retrospective", "lessons": nodes_to_json(lessons)}
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        if out is None:
            sys.stdout.write(text)  # stdout carries ONLY the JSON (pipeable)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            console.print(f"built {len(lessons)} proposed lesson(s) → {out}")
        raise typer.Exit(_EXIT_OK)
    if fmt == "html":
        if out is None:
            console.print("[red]error:[/red] --out is required for --format html")
            raise typer.Exit(_EXIT_ERR)
        render_navigator_graph_html(
            list(lessons), out, title="Retrospective — proposed lessons"
        )
        console.print(f"wrote {out} ({len(lessons)} lessons)")
        raise typer.Exit(_EXIT_OK)
    console.print(f"[red]error:[/red] unknown --format {fmt!r} (expected json|html)")
    raise typer.Exit(_EXIT_ERR)


@navigator_app.command("revise-apply")
def revise_apply_cmd(
    schema: Path = typer.Option(
        ..., "--schema", help="the contract file (schema.prisma) the revise edits"
    ),
    lesson: Path = typer.Option(
        ..., "--lesson", help="JSON lesson node (its confidence gates the tier)"
    ),
    edit: Optional[Path] = typer.Option(
        None,
        "--edit",
        help="JSON revise-edit {target, path, before, after}; OMIT to derive it from the "
        "lesson when it carries a concrete `revise_edit` (a description-clarification lesson, REQ-24 H1)",
    ),
    apply: bool = typer.Option(
        False, "--apply", help="write the edit on proof (default: dry-run, no write)"
    ),
    commit: bool = typer.Option(
        False,
        "--commit",
        help="with --apply on proof, git-commit the written "
        "contract so the audit's revert_ref names a real commit (REQ-24 H3); off → the write is left "
        "uncommitted for the human to stage",
    ),
    kind: str = typer.Option(
        "backend",
        "--kind",
        help="the DETERMINISTIC output kind to byte-identity-"
        "guard against (REQ-24 H2): backend (default) | scaffold. A non-deterministic / polyglot kind "
        "has no regenerator → the revise fails safe to `human` (byte-identity is unprovable for LLM output)",
    ),
) -> None:
    """REQ-24 — apply a revise's concrete edit THROUGH a real byte-identity guard (regenerate the `$0`
    product + hash-compare). Auto-applies ONLY when the guard proves the product unchanged; any diff →
    `human` (the contract is left byte-identical). Dry-run by default — pass `--apply` to write on proof.

    The edit comes from `--edit`, or is DERIVED from `--lesson` when it carries a concrete `revise_edit`
    (the Lesson→ReviseEdit producer, REQ-24 H1); a lesson without one still requires `--edit`. `--kind`
    selects which deterministic product is guarded (REQ-24 H2); a polyglot/LLM kind fails safe to human.
    """
    import subprocess
    from datetime import datetime, timezone

    from .project import nodes_from_json
    from .revise_apply import apply_revise, is_deterministic_kind
    from .revise_tier import (
        ReviseEditError,
        eligibility_of,
        parse_revise_edit,
        revise_edit_from_lesson,
    )

    try:
        lesson_data = json.loads(Path(lesson).read_text(encoding="utf-8"))
        nodes = nodes_from_json(
            lesson_data if isinstance(lesson_data, list) else [lesson_data]
        )
        if not nodes:
            raise ReviseEditError("--lesson JSON produced no node")
        lesson_node = nodes[0]
        if edit is not None:
            edit_obj = parse_revise_edit(
                json.loads(Path(edit).read_text(encoding="utf-8"))
            )
        else:
            edit_obj = revise_edit_from_lesson(lesson_node)
            if edit_obj is None:
                raise ReviseEditError(
                    "no --edit given and the lesson carries no concrete `revise_edit` — a "
                    "determinism-regression lesson proposes a plan re-examination, not a mechanical edit; "
                    "supply --edit for those."
                )
    except (OSError, ValueError, ReviseEditError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    # claim byte_identical=True (the intent); the guard ENFORCES it. reversible = a git-tracked contract
    # edit, no spend. confidence comes from the lesson (gates the tier).
    elig = eligibility_of(lesson_node, byte_identical=True, effects=[])
    try:
        head = subprocess.run(
            ["git", "-C", str(Path(schema).parent), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        revert_ref = head.stdout.strip() if head.returncode == 0 else "uncommitted"
    except Exception:
        revert_ref = "uncommitted"
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        audit = apply_revise(
            schema,
            edit_obj,
            lesson_node,
            elig,
            timestamp=timestamp,
            revert_ref=revert_ref,
            dry_run=not apply,
            kind=kind,
        )
    except OSError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    if audit is not None:
        verb = "auto-applied" if apply else "auto-eligible (dry-run)"
        committed = ""
        if audit is not None and apply and commit:
            # REQ-24 H3 — capture the written contract as a real commit so revert is `git revert <sha>`,
            # not a manual `git checkout`. Only the schema file is staged (never `git add -A`).
            sdir = str(Path(schema).parent)
            try:
                add = subprocess.run(
                    ["git", "-C", sdir, "add", str(Path(schema).name)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                msg = (
                    f"revise(auto): clarify {audit.target} — byte-identity-proven ($0 product "
                    f"unchanged)\n\nlesson={audit.lesson} revert_ref={audit.revert_ref}"
                )
                cm = subprocess.run(
                    [
                        "git",
                        "-C",
                        sdir,
                        "commit",
                        "-m",
                        msg,
                        "--only",
                        str(Path(schema).name),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if add.returncode == 0 and cm.returncode == 0:
                    committed = " (committed)"
                else:
                    committed = " [yellow](commit skipped: git error)[/yellow]"
            except Exception:
                committed = " [yellow](commit skipped: git unavailable)[/yellow]"
        console.print(
            f"[green]{verb}[/green]{committed}: revise of {audit.target!r} — guard proved the "
            f"{kind} product byte-identical. audit: lesson={audit.lesson} revert={audit.revert_ref}"
        )
    elif not is_deterministic_kind(kind):
        console.print(
            f"[yellow]human[/yellow]: `--kind {kind}` is non-deterministic (polyglot / LLM) — "
            "it has no byte-identity regenerator, so the revise can't be auto-proven and stays "
            "human by construction. The contract is untouched."
        )
    else:
        console.print(
            "[yellow]human[/yellow]: not auto-applied — the tier is not `auto` or the guard "
            "did not prove the product unchanged. The contract is untouched; propose to a human."
        )
    raise typer.Exit(_EXIT_OK)


# REQ-20 H2 — the human-disposition surface over the persisted Lesson store (REQ-20 H3). The IR never
# self-disposes; these commands are the ONLY path that accepts/rejects a Lesson, and they always persist.
lesson_app = typer.Typer(
    help="Dispose persisted retrospective Lessons (REQ-20): list | accept | reject."
)
navigator_app.add_typer(lesson_app, name="lesson")


def _load_store_or_exit(store: Path):
    from .lesson_store import load_lessons

    try:
        return load_lessons(store)
    except (OSError, ValueError) as exc:
        console.print(f"[red]error:[/red] store {store}: {exc}")
        raise typer.Exit(_EXIT_OPERATIONAL)


@lesson_app.command("list")
def lesson_list(
    store: Path = typer.Option(
        ...,
        "--store",
        help="the Lesson store JSON (written by `retrospective --store`)",
    ),
) -> None:
    """List persisted Lessons with their disposition (proposed | accepted | rejected)."""
    lessons = _load_store_or_exit(store)
    if not lessons:
        console.print(f"(store {store} holds no lessons)")
        raise typer.Exit(_EXIT_OK)
    from .sources_retrospective import lesson_status

    for n in lessons:
        st = lesson_status(n)
        color = {"accepted": "green", "rejected": "yellow", "proposed": "cyan"}.get(
            st, "white"
        )
        proposes = n.attributes.get("proposes", "")
        console.print(f"[{color}]{st:<9}[/{color}] {n.key} — {proposes}")
    raise typer.Exit(_EXIT_OK)


@lesson_app.command("accept")
def lesson_accept(
    store: Path = typer.Option(..., "--store", help="the Lesson store JSON"),
    key: str = typer.Option(
        ..., "--key", help="the Lesson key (or its bare requirement key)"
    ),
) -> None:
    """Human disposition — ACCEPT a Lesson's `revises` proposal (persists; its revise becomes active)."""
    from .lesson_store import find_lesson, save_lessons, upsert_lesson
    from .sources_retrospective import accept_lesson

    lessons = _load_store_or_exit(store)
    target = find_lesson(lessons, key)
    if target is None:
        console.print(f"[red]error:[/red] no lesson {key!r} in {store}")
        raise typer.Exit(_EXIT_ERR)
    try:
        save_lessons(store, upsert_lesson(lessons, accept_lesson(target)))
    except (OSError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_OPERATIONAL)
    console.print(
        f"[green]accepted[/green]: {target.key} — the revise is now active (still applied only "
        f"through the byte-identity guard)."
    )
    raise typer.Exit(_EXIT_OK)


@lesson_app.command("reject")
def lesson_reject(
    store: Path = typer.Option(..., "--store", help="the Lesson store JSON"),
    key: str = typer.Option(
        ..., "--key", help="the Lesson key (or its bare requirement key)"
    ),
    rationale: str = typer.Option(
        ..., "--rationale", help="why it's declined — retained across runs"
    ),
) -> None:
    """Human disposition — REJECT a Lesson, RETAINED with its rationale (the memory keeps *why*)."""
    from .lesson_store import find_lesson, save_lessons, upsert_lesson
    from .sources_retrospective import reject_lesson

    lessons = _load_store_or_exit(store)
    target = find_lesson(lessons, key)
    if target is None:
        console.print(f"[red]error:[/red] no lesson {key!r} in {store}")
        raise typer.Exit(_EXIT_ERR)
    try:
        save_lessons(store, upsert_lesson(lessons, reject_lesson(target, rationale)))
    except (OSError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_OPERATIONAL)
    console.print(
        f"[yellow]rejected[/yellow]: {target.key} — retained with rationale (survives re-runs)."
    )
    raise typer.Exit(_EXIT_OK)


@navigator_app.command("view-definition")
def view_definition(
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="Definition to resolve + dump (e.g. requirements | capability | node-schema | base). "
        "Omit to dump the whole registry.",
    ),
    resolved: bool = typer.Option(
        True,
        "--resolved/--raw",
        help="Dump the RESOLVED definition (extends chain flattened, default) or the raw authored delta.",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        help="With --name: dump only the leaves this domain overrides/adds vs the base (its delta).",
    ),
    validate: bool = typer.Option(
        False,
        "--validate",
        help="Govern the registry: every definition resolves, chrome.bindings reference known "
        "fields, resolved surface_links.via names a region or serves, drill links carry a "
        "{key} href, and presentation leaves are well-formed. "
        "Exit 0=clean, 1=issues (EC-6 / EC-CS-1/3/4/9).",
    ),
    from_file: Optional[Path] = typer.Option(
        None,
        "--from",
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
        console.print(
            f"[green]ok:[/green] {len(DEFINITION_REGISTRY)} definitions valid"
        )
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
        sys.stdout.write(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        )
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
                payload = definition_diff(
                    defn, BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY
                )
            else:
                payload = (
                    resolve(defn, DEFINITION_REGISTRY).to_dict()
                    if resolved
                    else defn.to_dict()
                )
        else:
            payload = {
                k: (
                    resolve(d, DEFINITION_REGISTRY).to_dict()
                    if resolved
                    else d.to_dict()
                )
                for k, d in DEFINITION_REGISTRY.items()
            }
    except (KeyError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERR)

    sys.stdout.write(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    )
    raise typer.Exit(_EXIT_OK)
