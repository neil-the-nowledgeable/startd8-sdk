# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""assist CLI command group — Service Assistant (project<->SDK bridge)."""

from pathlib import Path
from typing import Optional

import typer

from .cli_shared import console

assist_app = typer.Typer(
    name="assist",
    help="Service Assistant: detect completed Prime Contractor runs, triage failures, notify the SDK.",
)


@assist_app.command("scan")
def assist_scan(
    output_dir: Path = typer.Argument(
        ...,
        help="Run output dir to scan (contains prime-result*.json / prime-postmortem-report.json).",
    ),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Explicit run id (else auto-resolved)."),
    no_emit: bool = typer.Option(False, "--no-emit", help="Skip EventBus emission (write artifact only)."),
    no_write: bool = typer.Option(False, "--no-write", help="Skip writing the triage artifact."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress the summary print."),
) -> None:
    """Detect a completed/aborted run, synthesize a triage report, and notify the SDK.

    Idempotent: re-scanning an already-processed run is a no-op. Exits 0 always so the
    cap-dev-pipe post-run hook is never blocked by triage.
    """
    from .service_assistant import run_service_assistant

    report = run_service_assistant(
        output_dir,
        run_id=run_id,
        emit=not no_emit,
        write_artifact=not no_write,
    )

    if report is None:
        if not quiet:
            console.print("[dim]Service Assistant: nothing new to triage (or already processed).[/dim]")
        return

    if quiet:
        return

    verdict = report.verdict.aggregate_verdict
    color = {"PASS": "green", "PARTIAL": "yellow", "FAIL": "red", "ABORTED": "red"}.get(verdict, "white")
    console.print(f"[{color}]{report.summary.headline}[/{color}]")
    if report.summary.top_recommendation:
        console.print(f"  ↳ {report.summary.top_recommendation}")
    if report.events_emitted:
        console.print(f"  [dim]events: {', '.join(e.type for e in report.events_emitted)}[/dim]")


@assist_app.command("semantic-review")
def assist_semantic_review(
    output_dir: Path = typer.Argument(
        ..., help="Run output dir (contains prime-postmortem-report.json + prime-context-seed*.json)."
    ),
    project_root: Optional[Path] = typer.Option(
        None, "--project-root", help="Project root to resolve generated file paths against."
    ),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Explicit run id (else dir name)."),
    no_emit: bool = typer.Option(False, "--no-emit", help="Skip EventBus emission."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress the summary print."),
) -> None:
    """Review whether generated code semantically complies with its input requirement.

    Tiered Haiku→Sonnet; advisory (feeds Kaizen). Writes semantic-compliance-report.json/.md and
    appends structured Kaizen suggestions. Requires provider API keys for the reviewing models.
    """
    from .semantic_compliance import run_semantic_compliance

    report = run_semantic_compliance(
        output_dir, run_id=run_id, project_root=project_root, emit_events=not no_emit
    )
    if quiet:
        return
    s = report.summary
    agg = f"{s.semantic_compliance_aggregate:.2f}" if s.semantic_compliance_aggregate is not None else "—"
    color = "red" if s.fail else "green"
    console.print(
        f"[{color}]{report.run_id}: reviewed {s.reviewed}/{s.total_features} — "
        f"pass {s.pass_} · fail {s.fail} · inconclusive {s.inconclusive} (compliance {agg})[/{color}]"
    )
    for f in report.features:
        if f.verdict.verdict.value == "fail":
            top = f.issues[0].description if f.issues else ""
            console.print(f"  ✗ [red]{f.feature_id}[/red] ({f.verdict.confidence:.2f}): {top}")
    if report.summary.inconclusive_rate_exceeded:
        console.print("  [yellow]⚠ inconclusive rate exceeded — SYSTEM_WARNING[/yellow]")
