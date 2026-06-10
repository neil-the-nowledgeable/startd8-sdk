"""`startd8 generate frontend` — deterministic frontend code generation (Inc 8 / FR-8A, FR-11).

A no-LLM command that renders the Prisma→Zod schema file, or (with ``--check``) reports
drift without writing. Kept dependency-light (no framework/provider imports) so it loads
fast and is unit-testable in isolation.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

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
        help="After writing, boot the generated app in a subprocess and assert it serves "
        "/openapi.json (C-6 runtime gate — catches import errors compileall misses). The "
        "target is resolved from the scaffold manifest + on-disk entrypoints "
        "({package}.server:app when --ai-passes emitted server.py, else {package}.main:app).",
    ),
    pages: Optional[Path] = typer.Option(
        None,
        "--pages",
        help="Path to pages.yaml. When given, also generate owned content pages "
        "(app/pages.py + page templates) and inject a nav into base.html. Prose lives in "
        "app/pages/*.md (rendered at generate time; outside the drift hash).",
    ),
    pages_authoring: bool = typer.Option(
        False,
        "--pages-authoring",
        help="Also generate the in-app page-authoring UI (/ui/pages) that safely edits "
        "pages.yaml + app/pages/*.md from a web form. Requires --pages; adds pyyaml to the "
        "generated app's runtime deps. Pages still publish on the next generate (design-time author).",
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
    ai_agent_spec: Optional[str] = typer.Option(
        None,
        "--ai-agent-spec",
        help="Agent spec (provider:model) baked into the generated app's "
        "DEFAULT_AGENT_SPEC (the model the shipped app calls at runtime). "
        "Default: anthropic:claude-opus-4-8. Only meaningful with --ai-passes.",
    ),
    completeness: Optional[Path] = typer.Option(
        None,
        "--completeness",
        help="Path to completeness.yaml (domain-weighted thresholds: per-entity min_rows + "
        "weight + an exclude set). When given, app/completeness.py is weighted; absent → the "
        "flat presence rule. Threaded to both generate and --check so drift stays consistent.",
    ),
    views: Optional[Path] = typer.Option(
        None,
        "--views",
        help="Path to views.yaml (the same file `generate views` consumes). Only its top-level "
        "`forms:` section is read here: per-entity post-create behavior "
        "(on_create: detail|list|form|confirmation; default detail). Threaded to both generate "
        "and --check so drift stays consistent.",
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
    pages_text: Optional[str] = None
    _reads = {
        "manifest": None, "human": None, "pages": None, "completeness": None, "views": None,
    }
    for label, path, dest in (
        ("ai_passes", ai_passes, "manifest"),
        ("human_inputs", human_inputs, "human"),
        ("pages", pages, "pages"),
        ("completeness", completeness, "completeness"),
        ("views", views, "views"),
    ):
        if path is None:
            continue
        try:
            _reads[dest] = path.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] cannot read {label} {path}: {exc}")
            raise typer.Exit(_EXIT_ERROR)
    manifest_text, human_text, pages_text, completeness_text, views_text = (
        _reads["manifest"],
        _reads["human"],
        _reads["pages"],
        _reads["completeness"],
        _reads["views"],
    )

    if ai_agent_spec and manifest_text is None:
        console.print(
            "[yellow]warning:[/yellow] --ai-agent-spec is ignored without "
            "--ai-passes (no AI layer is generated)."
        )

    if pages_authoring and pages_text is None:
        console.print(
            "[red]error:[/red] --pages-authoring requires --pages "
            "(the authoring UI edits the pages.yaml manifest)."
        )
        raise typer.Exit(_EXIT_ERROR)

    try:
        artifacts = render_backend(
            schema_text,
            source_label,
            manifest_text=manifest_text,
            human_inputs_text=human_text,
            ai_agent_spec=ai_agent_spec,
            pages_text=pages_text,
            completeness_text=completeness_text,
            views_text=views_text,
            # On --check we don't render the untracked prose fragments (they need the .md on disk
            # and never participate in drift); on write we do, reading app/pages/*.md under --out.
            pages_app_dir=None if check else (out / "app"),
            authoring=pages_authoring,
        )
    except (
        ValueError
    ) as exc:  # reserved attr name / malformed ai_passes/pages/views manifest — fail loud
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
                pages_text=pages_text,
                completeness_text=completeness_text,
                forms_text=views_text,
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


@generate_app.command("scaffold")
def scaffold(
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", help="Path to app.yaml (project plumbing manifest). Absent → defaults."
    ),
    out: Path = typer.Option(
        Path("."), "--out", help="Project root to write the plumbing into."
    ),
    check: bool = typer.Option(
        False, "--check", help="Drift-check owned scaffold files instead of writing (exit 1 on drift)."
    ),
):
    """Deterministically emit project plumbing (pyproject/logging/alembic/Dockerfile) from app.yaml.

    Class-2 determinism — $0 LLM, owned, drift-checked. Non-overlapping with `generate backend`
    (which owns ``app/``); this owns the project *around* it.
    """
    from .scaffold_codegen import render_scaffold, scaffold_in_sync

    manifest_text = ""
    if manifest is not None:
        try:
            manifest_text = manifest.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] cannot read manifest {manifest}: {exc}")
            raise typer.Exit(_EXIT_ERROR)

    try:
        artifacts = render_scaffold(manifest_text)
    except ValueError as exc:  # malformed app.yaml — fail loud
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERROR)

    if check:
        drifted = 0
        for rel, content in artifacts:
            target = out / rel
            ondisk = target.read_text(encoding="utf-8") if target.exists() else None
            if ondisk is None:
                drifted += 1
                console.print(f"[yellow]missing[/yellow]: {rel}")
            elif not scaffold_in_sync(manifest_text, ondisk):
                drifted += 1
                console.print(
                    f"[yellow]drift[/yellow]: {rel} — differs from a fresh render "
                    "(stale, hand-edited, or generated with different flags/manifests)"
                )
        if drifted:
            console.print(f"[yellow]{drifted} scaffold artifact(s) drifted[/yellow]")
            raise typer.Exit(1)
        console.print(f"[green]in_sync[/green]: all {len(artifacts)} scaffold artifact(s) match app.yaml")
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
    console.print(f"[green]wrote[/green] {written} scaffold file(s) under {out}")


@generate_app.command("views")
def views(
    schema: Path = typer.Option(..., "--schema", help="Path to prisma/schema.prisma."),
    views_manifest: Path = typer.Option(..., "--views", help="Path to views.yaml (composite views)."),
    out: Path = typer.Option(Path("."), "--out", help="Project root to write app/views into."),
    check: bool = typer.Option(
        False, "--check", help="Drift-check owned view files instead of writing (exit 1 on drift)."
    ),
):
    """Deterministically emit composite/relational views (dashboard/board/workspace) from views.yaml.

    Class-3 determinism — $0 LLM, owned, drift-checked. Multi-entity views that backend_codegen
    (single-entity CRUD) does not emit. Closes the D1 view-generator gap.
    """
    from .view_codegen import is_owned_view_file, render_views, views_in_sync

    try:
        schema_text = schema.read_text(encoding="utf-8")
        views_text = views_manifest.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]error:[/red] cannot read input: {exc}")
        raise typer.Exit(_EXIT_ERROR)

    try:
        artifacts = render_views(schema_text, views_text)
    except ValueError as exc:  # malformed views.yaml / unknown entity — fail loud
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(_EXIT_ERROR)

    if check:
        drifted = 0
        for rel, content in artifacts:
            if not is_owned_view_file(content):
                continue  # the empty package marker
            target = out / rel
            ondisk = target.read_text(encoding="utf-8") if target.exists() else None
            if ondisk is None or not views_in_sync(schema_text, views_text, target, ondisk):
                drifted += 1
                console.print(
                    f"[yellow]drift[/yellow]: {rel} — missing or differs from a fresh render "
                    "(stale, hand-edited, or generated with different flags/manifests)"
                )
        if drifted:
            console.print(f"[yellow]{drifted} view artifact(s) drifted[/yellow]")
            raise typer.Exit(1)
        console.print("[green]in_sync[/green]: all view artifact(s) match schema + views.yaml")
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
    console.print(f"[green]wrote[/green] {written} view file(s) under {out}")


@generate_app.command("contract")
def contract(
    requirements: List[Path] = typer.Option(
        ..., "--requirements", "-r",
        help="Requirements/plan doc(s) — the source of truth. Repeatable (plan + requirements split).",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Run-dir for the gated DRAFT (default: a temp dir, printed)."),
    live: Optional[Path] = typer.Option(
        None, "--live", help="Current contract for the parity gate (default: auto-detect --contract-path)."),
    contract_path: Path = typer.Option(
        Path("prisma/schema.prisma"), "--contract-path",
        help="Project contract path (promote target + parity auto-detect)."),
    promote: bool = typer.Option(
        False, "--promote",
        help="FR-PE-7 explicit flip: copy the gated draft to --contract-path (only if the gate passes)."),
    with_manifests: bool = typer.Option(
        False, "--with-manifests",
        help="Also re-derive the YAML manifests (pages/views/completeness/…) alongside the contract."),
    force: bool = typer.Option(
        False, "--force",
        help="Allow --with-manifests to overwrite a live manifest whose content differs from a fresh "
             "derivation (default: skip hand-corrected manifests so they aren't silently clobbered)."),
    check: bool = typer.Option(
        False, "--check",
        help="Gate only; write nothing to the project. Exit 0=ok / 1=drift|round-trip-fail / 2=error."),
    json_out: bool = typer.Option(False, "--json", help="Emit the gate result as JSON."),
):
    """Emit `prisma/schema.prisma` from the requirements doc (FR-PE / FR-EMIT) — $0, no LLM.

    The inverse of the other `generate` subcommands: they READ the schema; this one PRODUCES it
    from prose. Default = a gated DRAFT written to a run-dir only (never the project tree); the gate
    runs round-trip (FR-PE-6) + parity vs the live contract. `--promote` performs the explicit,
    human-triggered flip to --contract-path (FR-PE-7), only when the gate passes.
    """
    import json as _json
    import tempfile

    from .manifest_extraction.extract import build_entity_graph, extract_manifests
    from .manifest_extraction.prisma_emitter import emit_schema_draft, promote_schema

    # 1. read the source doc(s) — label = path (provenance header + traceability)
    docs: dict = {}
    for req in requirements:
        try:
            docs[str(req)] = req.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] cannot read requirements doc {req}: {exc}")
            raise typer.Exit(_EXIT_ERROR)

    # 2. live contract for parity (explicit --live, else auto-detect the project contract)
    live_text: Optional[str] = None
    live_src = live if live is not None else (contract_path if contract_path.exists() else None)
    if live_src is not None:
        try:
            live_text = live_src.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] cannot read live contract {live_src}: {exc}")
            raise typer.Exit(_EXIT_ERROR)

    # 3. doc → graph → gated draft (FR-EMIT-1/2). --check writes the draft to a throwaway dir so
    #    nothing lands in the project tree; the gate result is identical.
    try:
        graph = build_entity_graph(docs)
    except Exception as exc:  # malformed entity blocks — fail loud, never an empty graph
        console.print(f"[red]error:[/red] could not parse entities from requirements: {exc}")
        raise typer.Exit(_EXIT_ERROR)

    run_dir = Path(tempfile.mkdtemp(prefix="startd8-emit-")) if (check or out is None) else out
    source_file = str(requirements[0])  # provenance header names the (primary) requirements doc
    res = emit_schema_draft(graph, str(run_dir), live_text=live_text, source_file=source_file)

    # 4. report the gate (FR-EMIT-2/7)
    if json_out:
        console.print_json(_json.dumps({
            "ok": res.ok, "round_trips": res.round_trips, "models": res.models,
            "parity_drift": list(res.parity_drift),
            "unrenderable": [f"{u.entity}.{u.field}: {u.reason}" for u in res.unrenderable],
            "draft_path": res.draft_path,
        }))
    else:
        console.print(f"models rendered: {res.models}")
        console.print(f"round-trips: {'[green]yes[/green]' if res.round_trips else '[red]no[/red]'}")
        if live_text is not None:
            if res.parity_drift:
                console.print(f"[yellow]parity drift ({len(res.parity_drift)}):[/yellow]")
                for d in res.parity_drift:
                    console.print(f"  - {d}")
            else:
                console.print("parity: [green]clean[/green] (matches the live contract)")
        for u in res.unrenderable:  # FR-EMIT-7: never silently drop
            console.print(f"[yellow]unrenderable[/yellow]: {u.entity}.{u.field} — {u.reason}")
        if res.draft_path:
            console.print(f"draft: {res.draft_path}")

    # 5. --check: gate only, nothing written to the project (FR-EMIT-4)
    if check:
        raise typer.Exit(0 if res.ok else 1)

    # 6. optional manifest re-derivation into the run-dir (OQ-EMIT-1)
    manifest_texts: dict = {}
    if with_manifests:
        try:
            mres = extract_manifests(docs, live_schema_text=live_text)
            manifest_texts = mres.manifests
            for fname, text in manifest_texts.items():
                (run_dir / fname).write_text(text, encoding="utf-8")
            console.print(f"[green]derived[/green] {len(manifest_texts)} manifest(s) into {run_dir}")
        except Exception as exc:
            console.print(f"[red]error:[/red] manifest derivation failed: {exc}")
            raise typer.Exit(_EXIT_ERROR)

    # 7. --promote: explicit, human-triggered flip (FR-PE-7/FR-EMIT-3). The blocking gate is
    #    round-trip + non-empty — parity DRIFT is the intended change being applied (you promote
    #    *because* the prose changed), so it is surfaced, not blocked. (Strict parity is `--check`.)
    if promote:
        if not res.round_trips or res.models == 0:
            console.print("[red]refusing to promote[/red]: the emitted schema did not round-trip "
                          f"to a non-empty model set (models={res.models}) — fix the requirements "
                          "doc (no parseable entities?) before flipping the contract.")
            raise typer.Exit(1)
        if live_text is not None and res.parity_drift:
            console.print(f"[cyan]applying {len(res.parity_drift)} change(s)[/cyan] vs the live contract.")
        try:
            target = promote_schema(str(run_dir), str(contract_path))
        except OSError as exc:
            console.print(f"[red]error:[/red] promote failed: {exc}")
            raise typer.Exit(_EXIT_ERROR)
        console.print(f"[green]promoted[/green] contract → {target}")
        if with_manifests:  # land manifests next to the contract so the $0 cascade reads them
            # Derivation is lossy vs hand-corrected manifests — never silently clobber one that
            # differs. New/identical manifests write; differing ones skip unless --force.
            skipped = []
            for fname, text in manifest_texts.items():
                dest = contract_path.parent / fname
                if dest.is_file() and dest.read_text(encoding="utf-8") != text and not force:
                    skipped.append(fname)
                    continue
                dest.write_text(text, encoding="utf-8")
            console.print(
                f"[green]promoted[/green] {len(manifest_texts) - len(skipped)} manifest(s) "
                f"→ {contract_path.parent}")
            if skipped:
                console.print(
                    f"[yellow]skipped[/yellow] {len(skipped)} hand-corrected manifest(s) that differ "
                    f"from a fresh derivation: {', '.join(skipped)}. Re-run with --force to overwrite.")
        raise typer.Exit(0)

    # 8. draft-only: a valid (round-tripping, non-empty) draft is success; parity drift is
    #    informational here (use `--check` for the strict in-sync gate).
    raise typer.Exit(0 if (res.round_trips and res.models > 0) else 1)
