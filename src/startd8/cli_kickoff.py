"""`startd8 kickoff` — the kickoff CLI family. First command: `check` (contract OQ-2 / plan K1).

The author's pre-flight: run the deterministic manifest extraction as a dry-run against
kickoff docs, render the conformance report, write nothing. Every `not_extracted` row that is
NOT a generator-gap is the co-work worklist (the contract's §3 friction loop): reformat the
prose, re-check, repeat — zero LLM calls in the loop itself.

Exit semantics — this is an AUTHORING tool, distinct from the wireframe's advisory-only rule:
default exit 0; ``--strict`` exits 1 when any conformance-class failure remains (generator-gap
flags and honest `defaulted` derivations never gate — they are backlog/provenance, not author
errors).

Scope note: this lands plan **K1** (the command + contract DIFF). The **K2** §2.7 env-keys
agreement check (declared env defaults vs ``inputs/build-preferences.yaml``) is a deferred
follow-up — it needs a ``build_preferences_text`` pass added to ``extract_manifests``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from .manifest_extraction import (
    Status,
    extract_manifests,
    report_to_json,
)
from .manifest_extraction.models import ExtractionRecord, ExtractionResult

console = Console()

kickoff_app = typer.Typer(help="Kickoff-package tooling (authoring contract, conformance).")

_EXIT_CONFORMANCE = 1
_EXIT_FATAL = 2

_GENERATOR_GAP_MARKER = "generator-gap"


def _is_conformance_failure(record: ExtractionRecord) -> bool:
    """Author-actionable failures gate `--strict`; generator-gaps are SDK backlog, not author
    errors."""
    return record.status == Status.NOT_EXTRACTED and _GENERATOR_GAP_MARKER not in (
        record.reason or ""
    )


@kickoff_app.callback()
def _kickoff_callback() -> None:
    """Kickoff-package tooling (use `kickoff check`)."""


@kickoff_app.command("check")
def check(
    docs: List[Path] = typer.Argument(
        ..., help="Kickoff doc(s) in the authoring-contract format (REQUIREMENTS/PLAN markdown)."
    ),
    project: Optional[Path] = typer.Option(
        None,
        "--project",
        help="Consumer project root: enables the contract DIFF against prisma/schema.prisma.",
    ),
    contract: Optional[Path] = typer.Option(
        None,
        "--contract",
        help="Path to an authored schema.prisma. Contract-first projects (no prose `## Entities`) "
        "resolve assembly-manifest entity references — views Root, completeness, imports — against it "
        "(FR-CFE). Overrides --project's prisma/schema.prisma when both are given.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the extraction report JSON to stdout (machine output)."
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit 1 when any author-actionable conformance failure remains "
        "(generator-gap flags never gate).",
    ),
) -> None:
    """Check kickoff docs against the authoring contract — extraction dry-run, writes nothing."""
    doc_texts = {}
    for doc in docs:
        try:
            doc_texts[doc.name] = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            console.print(f"[red]kickoff check:[/red] cannot read {doc}: {exc}")
            raise typer.Exit(_EXIT_FATAL)

    live_schema_text = None
    # An explicit --contract wins over --project's conventional prisma/schema.prisma.
    schema_path = contract if contract is not None else (
        project / "prisma" / "schema.prisma" if project is not None else None
    )
    if schema_path is not None and schema_path.is_file():
        live_schema_text = schema_path.read_text(encoding="utf-8")

    result = extract_manifests(doc_texts, live_schema_text=live_schema_text)

    if json_out:
        sys.stdout.write(report_to_json(result))
    else:
        _render(result)

    if strict and any(_is_conformance_failure(r) for r in result.records):
        raise typer.Exit(_EXIT_CONFORMANCE)


def _render(result: ExtractionResult) -> None:
    worklist = [r for r in result.sorted_records() if _is_conformance_failure(r)]
    gaps = [
        r for r in result.by_status(Status.NOT_EXTRACTED)
        if _GENERATOR_GAP_MARKER in (r.reason or "")
    ]
    extracted = len(result.by_status(Status.EXTRACTED))
    defaulted = len(result.by_status(Status.DEFAULTED))

    console.print(
        f"[bold]Conformance:[/bold] {extracted} extracted · {defaulted} defaulted (derived) · "
        f"[yellow]{len(gaps)} generator-gap[/yellow] (SDK backlog, not author errors) · "
        + (
            f"[red]{len(worklist)} to fix[/red]"
            if worklist
            else "[green]0 to fix — docs conform[/green]"
        )
    )
    console.print(
        f"[dim]Manifests extractable: {', '.join(sorted(result.manifests)) or 'none'} "
        f"(grammar {result.grammar_version})[/dim]"
    )

    if worklist:
        table = Table(title="Co-work worklist (contract §3: reformat the prose, re-check)")
        table.add_column("Manifest")
        table.add_column("Value")
        table.add_column("Fix")
        table.add_column("Source")
        for r in worklist:
            src = ""
            if r.source:
                src = " › ".join(r.source.heading_path) or r.source.doc
                if r.source.row_index is not None:
                    src += f" (row {r.source.row_index})"
            table.add_row(r.manifest, r.value_path, r.reason or "", src)
        console.print(table)

    if result.contract_diff:
        console.print("\n[bold]Contract DIFF (docs vs live schema.prisma):[/bold]")
        for line in result.contract_diff:
            console.print(f"  [yellow]• {line}[/yellow]")
    elif result.contract_diff == [] and result.records:
        console.print("[dim]Contract DIFF: clean (or no live contract supplied).[/dim]")


@kickoff_app.command("lint-config")
def lint_config_cmd() -> None:
    """Lint the SDK-internal kickoff experience config (R3-S2). Exit 1 if any issue."""
    from .kickoff_experience.manifest import default_config, lint_config

    issues = lint_config(default_config())
    if not issues:
        console.print("[green]kickoff config: clean[/green]")
        return
    for issue in issues:
        console.print(f"[red]✗[/red] {issue.field_key}: [yellow]{issue.code}[/yellow] — {issue.message}")
    raise typer.Exit(_EXIT_CONFORMANCE)


@kickoff_app.command("inspect")
def inspect_cmd(
    project: Path = typer.Argument(Path("."), help="Project root (default: current directory)."),
    json_out: bool = typer.Option(True, "--json/--no-json", help="Emit inspect JSON to stdout."),
) -> None:
    """Read-only kickoff state for CI/agents (R4-F3): no serve, no port, no write."""
    import json as _json

    from .kickoff_experience.serve import inspect_payload

    payload = inspect_payload(project)
    if json_out:
        sys.stdout.write(_json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        state = payload["state"]
        na = payload["next_action"]
        console.print(
            f"[bold]Kickoff state[/bold] — {state['counts']} · next: [cyan]{na['title']}[/cyan]"
        )
        console.print(f"[dim]preflight ok={payload['preflight']['ok']}[/dim]")


@kickoff_app.command("start")
def start_cmd(
    project: Path = typer.Argument(Path("."), help="Project root to serve the kickoff UI for."),
    mode: str = typer.Option("write", "--mode", help="inspect | preview | write | demo (R4-F5)."),
    theme: str = typer.Option("professional", "--theme", help="Presentation-polish theme."),
    port: Optional[int] = typer.Option(None, "--port", help="Bind port (default: ephemeral)."),
) -> None:
    """Serve the interactive kickoff web app on the loopback (preflight first; teardown on exit)."""
    from .kickoff_experience.serve import Mode, preflight, serve_kickoff

    if mode not in Mode.ALL:
        console.print(f"[red]unknown mode {mode!r}[/red] (one of {Mode.ALL})")
        raise typer.Exit(_EXIT_FATAL)
    pf = preflight(project, mode=mode)
    for c in pf.checks:
        mark = "[green]✓[/green]" if c.ok else ("[red]✗[/red]" if c.blocking else "[yellow]•[/yellow]")
        console.print(f"  {mark} {c.name}: {c.detail}")
    if not pf.ok:
        console.print("[red]preflight failed — not serving.[/red]")
        raise typer.Exit(_EXIT_FATAL)
    console.print(f"[green]serving kickoff[/green] (mode={mode}, theme={theme}) — Ctrl-C to stop")
    serve_kickoff(project, mode=mode, theme=theme, port=port)


@kickoff_app.command("concierge")
def concierge_cmd(
    project: Path = typer.Argument(Path("."), help="Project root to onboard (Concierge mode)."),
    posture: str = typer.Option("prototype", "--posture", help="prototype | production (instantiate)."),
) -> None:
    """Concierge mode in the terminal: survey, instantiate a kickoff package, log friction.

    Read-only triage + readiness; writes (instantiate / friction) happen only on an explicit
    confirmation and fail closed when no interactive terminal is available.
    """
    from .kickoff_experience.tui_concierge import (
        _questionary_confirm,
        _questionary_prompt,
        run_concierge,
    )

    run_concierge(
        str(project),
        confirm=_questionary_confirm,
        prompt=_questionary_prompt,
        emit_line=lambda line: console.print(line),
        posture=posture,
    )
