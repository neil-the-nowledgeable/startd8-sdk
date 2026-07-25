# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Vendor-neutral Workflow Loop Queue CLI (``startd8 wloop``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import typer

from .cli_shared import console
from .workflows.loop_queue import (
    LoopQueueBlockedError,
    LoopQueueConfig,
    LoopQueueError,
    LoopQueueValidationError,
    WorkflowLoopQueue,
    list_recipes,
    list_surfaces,
)

wloop_app = typer.Typer(
    name="wloop",
    help="Durable vendor-neutral workflow/loop queue (experimental)",
    no_args_is_help=True,
)

T = TypeVar("T")


def _queue(root: Path) -> WorkflowLoopQueue:
    return WorkflowLoopQueue(LoopQueueConfig(queue_root=root))


def _run(action: Callable[[], T]) -> T:
    """Translate WLQ's normative VASI exit codes at the CLI boundary."""
    try:
        return action()
    except LoopQueueBlockedError as e:
        console.print(f"[yellow]Blocked:[/yellow] {e}")
        raise typer.Exit(3)
    except LoopQueueValidationError as e:
        console.print(f"[red]Validation failed:[/red] {e}")
        raise typer.Exit(2)
    except LoopQueueError as e:
        console.print(f"[red]WLQ error:[/red] {e}")
        raise typer.Exit(1)


def _print_json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    console.print_json(json.dumps(value, default=str))


@wloop_app.command("enqueue")
def enqueue(
    config: Path = typer.Option(
        ..., "--config", "-c", exists=True, file_okay=True, dir_okay=False
    ),
    root: Path = typer.Option(
        Path(".startd8/workflow-loop-queue"), "--root", help="WLQ root directory"
    ),
) -> None:
    """Validate and enqueue a job envelope JSON file."""

    def action():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except Exception as e:
            raise LoopQueueValidationError(
                f"cannot read job config {config}: {e}"
            ) from e
        return _queue(root).enqueue_dict(data)

    _print_json(_run(action))


@wloop_app.command("status")
def status(
    job_id: Optional[str] = typer.Option(None, "--job-id"),
    root: Path = typer.Option(Path(".startd8/workflow-loop-queue"), "--root"),
) -> None:
    """Show one job or the durable queue summary."""
    queue = _queue(root)
    _print_json(_run(lambda: queue.get(job_id) if job_id else queue.status_summary()))


@wloop_app.command("run-next")
def run_next(
    job_id: Optional[str] = typer.Option(None, "--job-id"),
    root: Path = typer.Option(Path(".startd8/workflow-loop-queue"), "--root"),
) -> None:
    """Emit a VASI hand-off, or consume its drain-result write-back."""
    _print_json(_run(lambda: _queue(root).run_next(job_id)))


@wloop_app.command("drain")
def drain(
    job_id: Optional[str] = typer.Option(None, "--job-id"),
    root: Path = typer.Option(Path(".startd8/workflow-loop-queue"), "--root"),
) -> None:
    """Alias for ``run-next``."""
    _print_json(_run(lambda: _queue(root).run_next(job_id)))


@wloop_app.command("render")
def render(
    job_id: str = typer.Option(..., "--job-id"),
    root: Path = typer.Option(Path(".startd8/workflow-loop-queue"), "--root"),
) -> None:
    """Render/reuse an agent-surface CRP bundle without draining."""
    bundle = _run(lambda: _queue(root).render(job_id))
    _print_json({"job_id": job_id, "bundle_path": str(bundle)})


@wloop_app.command("cancel")
def cancel(
    job_id: str = typer.Option(..., "--job-id"),
    root: Path = typer.Option(Path(".startd8/workflow-loop-queue"), "--root"),
) -> None:
    """Cancel a non-terminal job."""
    _print_json(_run(lambda: _queue(root).cancel(job_id)))


@wloop_app.command("requeue")
def requeue(
    job_id: str = typer.Option(..., "--job-id"),
    root: Path = typer.Option(Path(".startd8/workflow-loop-queue"), "--root"),
) -> None:
    """Explicitly recover a processing, blocked, or failed job (v1 interim)."""
    _print_json(_run(lambda: _queue(root).requeue(job_id)))


@wloop_app.command("triage")
def triage(
    job_id: str = typer.Option(..., "--job-id"),
    decisions: Path = typer.Option(
        ..., "--decisions", exists=True, file_okay=True, dir_okay=False
    ),
    root: Path = typer.Option(Path(".startd8/workflow-loop-queue"), "--root"),
) -> None:
    """Apply explicit CRP ACCEPT/REJECT decisions to Appendix A/B."""

    def action():
        try:
            data = json.loads(decisions.read_text(encoding="utf-8"))
        except Exception as e:
            raise LoopQueueValidationError(
                f"cannot read triage decisions {decisions}: {e}"
            ) from e
        if isinstance(data, dict):
            data = data.get("decisions")
        if not isinstance(data, list):
            raise LoopQueueValidationError(
                "decisions JSON must be a list or {'decisions': [...]}"
            )
        return _queue(root).triage(job_id, data)

    _print_json(_run(action))


@wloop_app.command("list-loops")
def list_loops() -> None:
    """List thin loop recipes and supported executors (FR-7)."""
    _print_json(
        [
            {
                "loop_id": recipe.loop_id,
                "description": recipe.description,
                "executors": list(recipe.executors),
                "workflow_ids": list(recipe.workflow_ids),
                "inputs": recipe.inputs,
                "completion": recipe.completion,
                "steps": list(recipe.steps),
            }
            for recipe in list_recipes()
        ]
    )


@wloop_app.command("list-surfaces")
def surfaces() -> None:
    """List advisory known surfaces; custom VASI surfaces remain allowed."""
    _print_json(
        [
            {
                "surface_id": surface.surface_id,
                "display_name": surface.display_name,
                "ownership": surface.ownership,
                "status": surface.status,
            }
            for surface in list_surfaces()
        ]
    )
