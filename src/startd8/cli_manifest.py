# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""manifest CLI command group (extracted from cli.py, Pass E)."""

from rich.console import Console
from typing import Optional, List
from pathlib import Path
from rich.table import Table
import typer
from .cli_shared import console


manifest_app = typer.Typer(
    name="manifest",
    help="Code manifest generation and inspection commands"
)


@manifest_app.command("generate")
def manifest_generate(
    path: Optional[str] = typer.Argument(None, help="Source path to scan (default: src/)"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Cache/output directory"),
    fmt: str = typer.Option("json", "--format", help="Output format: json or yaml"),
    mode: str = typer.Option("static", "--mode", help="Analysis mode: ast_only, static, bytecode"),
    check: bool = typer.Option(False, "--check", help="Exit non-zero if manifests are stale"),
    strict: bool = typer.Option(False, "--strict", help="Treat parse errors as hard failures"),
    verbose: bool = typer.Option(False, "--verbose", help="Print per-file status"),
):
    """Generate code manifests for Python files."""
    from pathlib import Path as P
    from rich.console import Console
    from startd8.utils.manifest_cache import generate_project_manifests, check_manifests_fresh

    console = Console()
    project_root = P.cwd()
    source_root = P(path) if path else None
    cache_dir = P(output_dir) if output_dir else None

    if check:
        fresh, stale = check_manifests_fresh(project_root, source_root, cache_dir)
        if fresh:
            console.print("[green]All manifests are up to date.[/green]")
            raise SystemExit(0)
        else:
            console.print(f"[yellow]{len(stale)} stale manifest(s):[/yellow]")
            for f in stale:
                console.print(f"  {f}")
            raise SystemExit(1)

    manifests = generate_project_manifests(project_root, source_root, cache_dir, mode=mode)

    error_count = sum(1 for m in manifests.values() if m.errors)
    if strict and error_count > 0:
        console.print(f"[red]--strict: {error_count} file(s) had parse errors[/red]")
        raise SystemExit(1)

    if verbose:
        for rel_path, m in sorted(manifests.items()):
            status = "[red]ERROR[/red]" if m.errors else "[green]OK[/green]"
            console.print(f"  {status} {rel_path} ({len(m.elements)} elements)")

    console.print(
        f"[green]Generated manifests for {len(manifests)} file(s)[/green]"
        + (f" ({error_count} with errors)" if error_count else "")
    )


@manifest_app.command("check")
def manifest_check(
    path: Optional[str] = typer.Argument(None, help="Source path to check"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Cache directory"),
):
    """Check if cached manifests are up to date (no regeneration)."""
    from pathlib import Path as P
    from rich.console import Console
    from startd8.utils.manifest_cache import check_manifests_fresh

    console = Console()
    project_root = P.cwd()
    source_root = P(path) if path else None
    cache_dir = P(output_dir) if output_dir else None

    fresh, stale = check_manifests_fresh(project_root, source_root, cache_dir)
    if fresh:
        console.print("[green]All manifests are up to date.[/green]")
        raise SystemExit(0)
    else:
        console.print(f"[yellow]{len(stale)} stale manifest(s):[/yellow]")
        for f in stale:
            console.print(f"  {f}")
        raise SystemExit(1)


@manifest_app.command("show")
def manifest_show(
    file: str = typer.Argument(..., help="Python file to show manifest for"),
    fqn: Optional[str] = typer.Option(None, "--fqn", help="Show specific element by FQN"),
    fmt: str = typer.Option("tree", "--format", help="Output format: json, yaml, or tree"),
):
    """Show the manifest for a single Python file."""
    import json
    from pathlib import Path as P
    from rich.console import Console
    from rich.tree import Tree
    from startd8.utils.code_manifest import generate_file_manifest, lookup_element

    console = Console()
    project_root = P.cwd()
    file_path = P(file)

    if not file_path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise SystemExit(1)

    manifest = generate_file_manifest(file_path, project_root)

    if fqn:
        elem = lookup_element(manifest, fqn)
        if elem is None:
            console.print(f"[red]Element not found: {fqn}[/red]")
            raise SystemExit(1)
        console.print_json(json.dumps(elem.model_dump(), indent=2, default=str))
        return

    if fmt == "json":
        console.print_json(json.dumps(manifest.model_dump(), indent=2, default=str))
    elif fmt == "yaml":
        console.print(manifest.to_yaml())
    else:
        # Tree view
        tree = Tree(f"[bold]{manifest.module}[/bold] ({manifest.file})")
        tree.add(f"digest: {manifest.digest[:20]}...")
        tree.add(f"schema: {manifest.schema_version}")

        if manifest.imports:
            imp_branch = tree.add(f"[cyan]imports[/cyan] ({len(manifest.imports)})")
            for imp in manifest.imports:
                flags = []
                if imp.is_conditional:
                    flags.append("conditional")
                if imp.is_reexport:
                    flags.append("reexport")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                imp_branch.add(f"{imp.module}{flag_str}")

        if manifest.elements:
            elem_branch = tree.add(f"[green]elements[/green] ({len(manifest.elements)})")
            _add_elements_to_tree(elem_branch, manifest.elements)

        if manifest.errors:
            err_branch = tree.add(f"[red]errors[/red] ({len(manifest.errors)})")
            for err in manifest.errors:
                err_branch.add(f"{err.kind.value}: {err.message}")

        console.print(tree)


def _add_elements_to_tree(branch, elements):
    """Recursively add elements to a Rich tree."""
    for elem in elements:
        sig_str = ""
        if elem.signature:
            params = ", ".join(
                f"{p.name}: {p.annotation}" if p.annotation else p.name
                for p in elem.signature.params
            )
            ret = f" -> {elem.signature.return_annotation}" if elem.signature.return_annotation else ""
            sig_str = f"({params}){ret}"

        label = f"[bold]{elem.kind.value}[/bold] {elem.name}{sig_str}"
        if elem.scope_guard:
            label += f" [dim][{elem.scope_guard}][/dim]"

        child_branch = branch.add(label)
        if elem.children:
            _add_elements_to_tree(child_branch, elem.children)


@manifest_app.command("validate-capabilities")
def manifest_validate_capabilities(
    capability_file: str = typer.Argument(
        ..., help="Path to capability index YAML file"
    ),
    enrich: bool = typer.Option(
        False, "--enrich", help="Enrich evidence with manifest data (dry-run by default)"
    ),
    write: bool = typer.Option(
        False, "--write", help="Write enriched YAML (requires --enrich)"
    ),
):
    """Validate capability index evidence refs against manifest data (CI-1..CI-4).

    Checks that each evidence[].ref with type: "code" exists in the manifest registry.
    Reports drift when refs are missing from manifests.

    When --enrich is used, shows a diff of what would change (dry-run default).
    Use --enrich --write to actually modify the file.
    """
    import yaml
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry, _flatten_elements

    console = Console()
    project_root = Path.cwd()

    # Load manifest registry
    registry = ManifestRegistry.from_cache(project_root)

    cap_path = Path(capability_file)
    if not cap_path.exists():
        console.print(f"[red]Capability file not found: {capability_file}[/red]")
        raise SystemExit(1)

    try:
        cap_data = yaml.safe_load(cap_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]Failed to parse YAML: {exc}[/red]")
        raise SystemExit(1)

    if not isinstance(cap_data, dict):
        console.print("[red]Invalid capability YAML: expected a mapping[/red]")
        raise SystemExit(1)

    errors: list[str] = []
    enrichments: dict[str, int] = {}  # ref → element_count

    capabilities = cap_data.get("capabilities", [])
    if not isinstance(capabilities, list):
        capabilities = []

    for cap in capabilities:
        cap_id = cap.get("id", cap.get("name", "<unknown>"))
        evidence_list = cap.get("evidence", [])
        if not isinstance(evidence_list, list):
            continue

        for ev in evidence_list:
            if not isinstance(ev, dict):
                continue
            if ev.get("type") != "code":
                continue

            ref = ev.get("ref", "")
            if not ref:
                continue

            # Path traversal sanitization (req R1-S8)
            ref_path = Path(ref)
            if ref_path.is_absolute() or ".." in ref_path.parts:
                errors.append(
                    f"SECURITY: {cap_id} evidence ref '{ref}' "
                    f"contains path traversal (absolute path or '..' component)"
                )
                continue

            # Path normalization (plan R1-S9): normalize to POSIX
            normalized_ref = ref.replace("\\", "/")

            if registry is not None:
                # Registry-first validation (plan R2-S7)
                manifest = registry.get(normalized_ref)
                if manifest is None:
                    errors.append(
                        f"DRIFT: {cap_id} evidence ref '{ref}' not found in manifests"
                    )
                else:
                    enrichments[ref] = len(_flatten_elements(manifest.elements))
            else:
                # No registry loaded — fall back to disk check
                full_path = project_root / normalized_ref
                if not full_path.exists():
                    errors.append(
                        f"DRIFT: {cap_id} evidence ref '{ref}' not found on disk"
                    )

    if errors:
        for err in errors:
            if err.startswith("SECURITY"):
                console.print(f"[red]{err}[/red]")
            else:
                console.print(f"[yellow]{err}[/yellow]")
        console.print(f"\n[red]{len(errors)} issue(s) found[/red]")
        raise SystemExit(1)
    else:
        console.print(
            f"[green]All evidence refs validated ({len(enrichments)} code refs checked)[/green]"
        )

    if enrich and enrichments:
        if write:
            # TODO(phase4): implement ruamel.yaml round-trip writing per req R3-S9
            console.print("[yellow]--write: enrichment writing not yet implemented[/yellow]")
        else:
            console.print("\n[cyan]Enrichment preview (--dry-run):[/cyan]")
            for ref, count in sorted(enrichments.items()):
                console.print(f"  {ref}: manifest_element_count={count}")


@manifest_app.command("validate-forward")
def manifest_validate_forward(
    manifest_path: str = typer.Argument(..., help="Path to the ForwardManifest JSON schema or seed"),
    source_path: Optional[str] = typer.Option(None, "--source-path", help="Path to project root (default: cwd)"),
):
    """Validate codebase against a prescribed ForwardManifest contract."""
    import json
    from pathlib import Path as P
    from rich.console import Console
    from rich.table import Table
    from startd8.forward_manifest import ForwardManifest
    from startd8.utils.manifest_registry import ManifestRegistry
    from startd8.forward_manifest_validator import validate_forward_manifest

    console = Console()
    project_root = P(source_path) if source_path else P.cwd()
    manifest_file = P(manifest_path)

    if not manifest_file.exists():
        console.print(f"[red]Manifest file not found: {manifest_file}[/red]")
        raise SystemExit(1)

    try:
        raw_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        
        # Determine if it's a raw ContextSeed or a pure ForwardManifest
        if "forward_manifest" in raw_data:
            manifest_dict = raw_data["forward_manifest"]
        else:
            manifest_dict = raw_data
            
        manifest = ForwardManifest.model_validate(manifest_dict)
    except Exception as exc:
        console.print(f"[red]Failed to parse ForwardManifest: {exc}[/red]")
        raise SystemExit(1)

    # Load manifest registry to scan the current codebase topology
    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No codebase manifest cache found. Run 'startd8 manifest generate' first.[/red]")
        raise SystemExit(1)

    # Execute validator engine
    violations = validate_forward_manifest(manifest, registry)

    if not violations:
        console.print("[green]✅ ForwardManifest validation passed. Codebase aligns with contracts.[/green]")
        raise SystemExit(0)

    # Summarize and format violations
    table = Table(title=f"Contract Violations ({len(violations)})")
    table.add_column("Severity", style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Contract ID", style="magenta")
    table.add_column("Expected", style="green")
    table.add_column("Actual", style="red")
    
    error_count = 0
    warning_count = 0

    for v in violations:
        sev_color = "red" if v.severity == "error" else "yellow"
        if v.severity == "error":
            error_count += 1
        else:
            warning_count += 1
            
        table.add_row(
            f"[{sev_color}]{v.severity.upper()}[/{sev_color}]",
            v.violation_type,
            v.contract_id,
            v.expected,
            v.actual or "-"
        )

    console.print(table)
    
    if error_count > 0:
        console.print(f"[red]❌ Validation failed with {error_count} error(s) and {warning_count} warning(s).[/red]")
        raise SystemExit(1)
    else:
        console.print(f"[yellow]⚠️ Validation passed with {warning_count} warning(s).[/yellow]")
        raise SystemExit(0)


@manifest_app.command("calls")
def manifest_calls(
    fqn: str = typer.Argument(..., help="Fully-qualified name to inspect"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """Show outbound calls for a specific element."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.code_manifest import generate_file_manifest, lookup_element
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    result = registry.resolve_fqn(fqn)
    if result is None:
        console.print(f"[red]FQN not found: {fqn}[/red]")
        raise SystemExit(1)

    _file_path, element = result
    if element.call_graph is None:
        console.print(f"[yellow]No call graph data for {fqn}. Regenerate with --mode bytecode.[/yellow]")
        raise SystemExit(0)

    cg = element.call_graph
    if fmt == "json":
        console.print_json(json_mod.dumps(cg.model_dump(), indent=2, default=str))
    else:
        console.print(f"[bold]Calls from {fqn}[/bold] ({len(cg.calls)} total)")
        for call in cg.calls:
            status = "[green]resolved[/green]" if call.target_fqn else "[yellow]unresolved[/yellow]"
            receiver = f" on {call.receiver}" if call.receiver else ""
            console.print(f"  {call.target}{receiver} ({call.kind.value}) {status}")
            if call.target_fqn:
                console.print(f"    -> {call.target_fqn}")
        if cg.attribute_reads:
            console.print(f"\n[cyan]Attribute reads:[/cyan] {', '.join(cg.attribute_reads)}")
        if cg.attribute_writes:
            console.print(f"[cyan]Attribute writes:[/cyan] {', '.join(cg.attribute_writes)}")
        if cg.has_dynamic_dispatch:
            console.print("[yellow]Dynamic dispatch detected[/yellow]")


@manifest_app.command("callers")
def manifest_callers(
    fqn: str = typer.Argument(..., help="Fully-qualified name to find callers of"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """Show direct callers of a specific element."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    callers = registry.callers_of(fqn)
    if fmt == "json":
        console.print_json(json_mod.dumps({"fqn": fqn, "callers": sorted(callers)}, indent=2))
    else:
        console.print(f"[bold]Callers of {fqn}[/bold] ({len(callers)} total)")
        for caller in sorted(callers):
            console.print(f"  {caller}")
        if not callers:
            console.print("  [dim]No callers found[/dim]")


@manifest_app.command("blast-radius")
def manifest_blast_radius(
    fqn: str = typer.Argument(..., help="Fully-qualified name to compute blast radius for"),
    max_depth: int = typer.Option(10, "--max-depth", help="Maximum traversal depth"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """Compute transitive callers (blast radius) for a planned change."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    radius = registry.blast_radius(fqn, max_depth=max_depth)
    if fmt == "json":
        console.print_json(json_mod.dumps({
            "fqn": fqn, "max_depth": max_depth,
            "blast_radius": sorted(radius), "count": len(radius),
        }, indent=2))
    else:
        console.print(f"[bold]Blast radius for {fqn}[/bold] (depth={max_depth}, {len(radius)} callers)")
        for caller in sorted(radius):
            console.print(f"  {caller}")
        if not radius:
            console.print("  [dim]No transitive callers found[/dim]")


@manifest_app.command("dead-code")
def manifest_dead_code(
    path: Optional[str] = typer.Argument(None, help="Filter by file path prefix"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """List public callables with zero inbound call edges (dead code candidates)."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    candidates = registry.dead_candidates()
    if path:
        # Filter by file path prefix
        filtered = []
        for fqn in candidates:
            result = registry.resolve_fqn(fqn)
            if result and result[0].startswith(path):
                filtered.append(fqn)
        candidates = filtered

    if fmt == "json":
        console.print_json(json_mod.dumps({
            "dead_candidates": candidates, "count": len(candidates),
        }, indent=2))
    else:
        console.print(f"[bold]Dead code candidates[/bold] ({len(candidates)} total)")
        for fqn in candidates:
            console.print(f"  {fqn}")
        if not candidates:
            console.print("  [dim]No dead code candidates found[/dim]")


@manifest_app.command("contract-drift")
def manifest_contract_drift(
    old: str = typer.Argument(..., help="Path to the OLD ContextCore ContextContract (YAML)"),
    new: str = typer.Argument(..., help="Path to the NEW ContextCore ContextContract (YAML)"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """Detect propagation-breaking drift between two ContextContract versions (FR-REG-1/2).

    Off-run / CI-friendly: flags added/removed phases and fields a phase stops producing
    that a downstream phase requires. Exit 1 when breaking changes are found (so CI can gate),
    0 otherwise. No-op exit 0 with a notice when ContextCore is not installed.
    """
    import json as json_mod
    from startd8.workflows._contracts_integration import compare_contracts

    report = compare_contracts(old, new)
    if report is None:
        console.print(
            "[yellow]ContextCore not installed (or contract unreadable) — contract-drift "
            "is a no-op.[/yellow]"
        )
        raise SystemExit(0)

    breaking = getattr(report, "breaking_count", 0) or 0
    total = getattr(report, "total_changes", 0) or 0
    changes = getattr(report, "changes", []) or []

    if fmt == "json":
        console.print_json(json_mod.dumps({
            "total_changes": total,
            "breaking_count": breaking,
            "non_breaking_count": getattr(report, "non_breaking_count", 0),
            "changes": [str(c) for c in changes],
        }, indent=2))
    else:
        color = "red" if breaking else ("yellow" if total else "green")
        console.print(
            f"[bold]Contract drift[/bold]: [{color}]{total} change(s), "
            f"{breaking} breaking[/{color}]"
        )
        for c in changes:
            console.print(f"  {c}")
        if not total:
            console.print("  [dim]No drift — contracts are compatible[/dim]")

    raise SystemExit(1 if breaking else 0)
