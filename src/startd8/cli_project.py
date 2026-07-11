# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""project CLI command group (extracted from cli.py, Pass E)."""

from typing import Optional
from pathlib import Path
import typer
from rich.console import Console
from .cli_shared import console

# Deprecation / advisory notices go to stderr so `--json` stdout stays parseable (mirrors cli_concierge).
_stderr_console = Console(stderr=True)


project_app = typer.Typer(
    name="project",
    help="Project scaffolding and initialization commands"
)

# Posture-encoding exit codes (project-init FR-9/FR-10), mirroring cli_vipp/cli_generate:
# 0 = ok / in-sync · 1 = drift (--check) · 2 = bad input · 3 = a write was blocked (confinement).
_EXIT_DRIFT = 1
_EXIT_BAD_INPUT = 2
_EXIT_BLOCKED = 3


def _sdk_version() -> str:
    try:
        from . import __version__

        return str(__version__)
    except Exception:
        return "0.0.0"


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


@project_app.command("init")
def project_init(
    project_root: Optional[Path] = typer.Argument(
        None, help="Project root to onboard (default: current directory)."
    ),
    with_vipp: Optional[bool] = typer.Option(
        None,
        "--with-vipp/--no-vipp",
        help=(
            "Establish the VIPP / ground-truth-adjudication posting + inbox. Default (unset): posted "
            "for consumer safety during the alias window, with a deprecation notice. --with-vipp = "
            "explicit opt-in (no notice); --no-vipp = opt out (no VIPP posting, no `import vipp`)."
        ),
    ),
    with_fde: bool = typer.Option(
        False, "--with-fde", help="Also establish the FDE posting."
    ),
    instantiate: bool = typer.Option(
        False,
        "--instantiate",
        help="Greenfield only: produce a single `instantiate` proposal (the $0 kickoff-package gap).",
    ),
    proposals: Optional[Path] = typer.Option(
        None,
        "--proposals",
        help="Produce an inbox from an authored proposal set (YAML/JSON list of {kind, ...params}).",
    ),
    posture: str = typer.Option(
        "prototype", "--posture", help="Posture for the greenfield --instantiate proposal."
    ),
    check: bool = typer.Option(
        False, "--check", help="Read-only drift audit; write nothing. Exit 0=in-sync, 1=drift, 2=error."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the machine-readable summary as JSON (for CI)."
    ),
) -> None:
    """Set up the un-bundled VIPP / ground-truth-adjudication capability on a directory ($0, no LLM).

    Re-filed (M3, FR-1a/FR-14/OQ-8): this is the **setup entrypoint of the opt-in VIPP capability**,
    not kernel onboarding — greenfield onboarding is ``startd8 kickoff instantiate``. It detects
    greenfield/brownfield, establishes the ``.startd8/`` role postings, makes the project
    VIPP-inbox-ready, and (on a declared gap) produces a first inbox non-interactively. Re-runnable as
    a clean no-op.

    The VIPP posting is **opt-in**, default-on during a consumer-safe alias window (the two live
    consumers reach VIPP through this command) — pass ``--no-vipp`` to opt out (no ``import vipp``),
    or ``--with-vipp`` to opt in explicitly and silence the deprecation notice.
    """
    import json as _json

    from .concierge.safe_write import SafeWriteError
    from .project.init import ProposalsFileError, run_project_init

    root = project_root or Path.cwd()

    # Tri-state resolution of the VIPP posting (FR-1a alias window):
    #   None  -> default-on for consumer safety; emit the deprecation notice pointing at the opt-in.
    #   True  -> explicit opt-in (post VIPP, no notice — the user chose the VIPP capability).
    #   False -> opt out (no VIPP posting, and run_project_init never `import vipp`).
    resolved_with_vipp = True if with_vipp is None else with_vipp
    if with_vipp is None and not check:
        # Consumer-safe default: keep posting VIPP so household-o11y / benchmark portal do not break,
        # but announce the scope-out so callers migrate to `--with-vipp` (or the VIPP-capability home).
        import warnings as _warnings

        _warnings.warn(
            "`startd8 project init` now sets up the opt-in VIPP / ground-truth-adjudication "
            "capability, not kernel onboarding. VIPP is still posted by default for one release; "
            "pass `--with-vipp` to opt in explicitly (no notice) or `--no-vipp` to opt out. "
            "For plain greenfield onboarding use `startd8 kickoff instantiate`.",
            DeprecationWarning,
            stacklevel=2,
        )
        _stderr_console.print(
            "[yellow]deprecation:[/yellow] `startd8 project init` is now VIPP-capability setup "
            "(not kernel onboarding); VIPP is posted by default for one release — pass `--with-vipp` "
            "to opt in explicitly, `--no-vipp` to opt out. Greenfield onboarding: `startd8 kickoff instantiate`."
        )

    try:
        summary = run_project_init(
            root,
            with_vipp=resolved_with_vipp,
            with_fde=with_fde,
            instantiate=instantiate,
            proposals_file=proposals,
            posture=posture,
            check=check,
            sdk_version=_sdk_version(),
        )
    except ProposalsFileError as exc:  # FR-12 — bad producer input (bad file or flag conflict)
        console.print(f"[red]project init: bad input:[/red] {exc}")
        raise typer.Exit(_EXIT_BAD_INPUT)
    except SafeWriteError as exc:  # confinement / symlink refusal (FR-7)
        console.print(f"[red]project init blocked:[/red] {exc}")
        raise typer.Exit(_EXIT_BLOCKED)

    if json_out:
        # Plain stdout (not Rich console) so CI gets unwrapped, parseable JSON.
        typer.echo(_json.dumps(summary, indent=2, sort_keys=True))
    else:
        _render_summary(summary)

    # Exit-code mapping (FR-9/FR-10).
    if check:
        if summary.get("error"):
            raise typer.Exit(_EXIT_BAD_INPUT)  # exit 2 = error (unreadable / non-dir root)
        raise typer.Exit(0 if summary.get("in_sync") else _EXIT_DRIFT)
    producer_status = (summary.get("producer") or {}).get("status")
    if producer_status == "blocked":
        raise typer.Exit(_EXIT_BLOCKED)
    if producer_status == "rejected":
        raise typer.Exit(_EXIT_BAD_INPUT)
    raise typer.Exit(0)


def _render_summary(summary: dict) -> None:
    """Human-readable render of the init/check summary (deterministic ordering)."""
    if summary.get("action") == "init-check":
        if summary.get("error"):
            console.print(f"[red]project init --check error:[/red] {summary['error']}")
            return
        shape = summary.get("shape", {})
        console.print(f"[bold]project init --check[/bold] ({shape.get('verdict', '?')})")
        console.print(f"  initialized: {summary.get('initialized')}  in-sync: {summary.get('in_sync')}")
        if summary.get("drift"):
            console.print(f"  [yellow]drift:[/yellow] {', '.join(summary['drift'])}")
        return

    shape = summary.get("shape", {})
    console.print(f"[green]project init[/green] — shape: [cyan]{shape.get('verdict', '?')}[/cyan]")
    postings = summary.get("postings", {})
    console.print(f"  postings: {', '.join(sorted(postings)) or '(none)'}")
    if summary.get("vipp") == "opted-out":
        console.print("  [dim]VIPP opted out (--no-vipp): no posting, no inbox.[/dim]")
        return
    inbox = summary.get("inbox_ready", {})
    if inbox.get("written"):
        console.print(f"  inbox-ready: created {', '.join(inbox['written'])}")
    else:
        console.print("  inbox-ready: already present (no-op)")
    prod = summary.get("producer", {})
    status = prod.get("status")
    if status == "produced":
        src = prod.get("source", {})
        console.print(
            f"  [green]inbox produced[/green]: {prod.get('proposal_count')} proposal(s) "
            f"from {src.get('kind')}"
        )
    elif status == "skipped_undrained":
        console.print(f"  [yellow]inbox skipped[/yellow]: {prod.get('detail')}")
    elif status == "not_greenfield":
        console.print(f"  [yellow]not produced[/yellow]: {prod.get('detail')}")
    elif status == "no_gap":
        console.print(f"  inbox-ready; {prod.get('detail')}")
    console.print(f"  [dim]next: {summary.get('next')}[/dim]")
