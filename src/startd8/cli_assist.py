# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

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
