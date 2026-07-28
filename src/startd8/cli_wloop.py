# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Vendor-neutral Workflow Loop Queue CLI (``startd8 wloop``)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import typer

from .workflows.loop_queue import (
    LoopQueueBlockedError,
    LoopQueueConfig,
    LoopQueueError,
    LoopQueueValidationError,
    WithdrawalCause,
    WithdrawalVerdict,
    WorkflowLoopQueue,
    enqueue_withdrawal_remand,
    list_recipes,
    list_reviewer_tiers,
    list_surfaces,
)
from .workflows.loop_queue.cli_support import (
    DEFAULT_QUEUE_RELATIVE,
    ensure_queue_marker,
    print_json_stdout,
    quiet_otel_exporters,
    resolve_cli_root,
    route_sdk_logs_to_stderr,
    warn_if_fresh_queue_root,
)

wloop_app = typer.Typer(
    name="wloop",
    help="Durable vendor-neutral workflow/loop queue (experimental)",
    no_args_is_help=True,
)

T = TypeVar("T")

# FR-17: keep exporter failures and SDK logs out of agent-parsed stdout.
quiet_otel_exporters()
route_sdk_logs_to_stderr()

_ROOT_HELP = (
    "WLQ root directory (FR-24). Default: .startd8/workflow-loop-queue under "
    "CWD, or $STARTD8_WLOOP_ROOT when set and --root is left at default."
)


def _queue(root: Path) -> WorkflowLoopQueue:
    route_sdk_logs_to_stderr()
    return WorkflowLoopQueue(LoopQueueConfig(queue_root=resolve_cli_root(root)))


def _run(action: Callable[[], T]) -> T:
    """Translate WLQ's normative VASI exit codes at the CLI boundary."""
    route_sdk_logs_to_stderr()
    try:
        return action()
    except LoopQueueBlockedError as e:
        print(f"Blocked: {e}", file=sys.stderr)
        raise typer.Exit(3)
    except LoopQueueValidationError as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        raise typer.Exit(2)
    except LoopQueueError as e:
        print(f"WLQ error: {e}", file=sys.stderr)
        raise typer.Exit(1)


def _print_json(value: Any) -> None:
    route_sdk_logs_to_stderr()
    print_json_stdout(value)


@wloop_app.command("enqueue")
def enqueue(
    config: Path = typer.Option(
        ..., "--config", "-c", exists=True, file_okay=True, dir_okay=False
    ),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Validate and enqueue a job envelope JSON file."""

    def action():
        resolved = resolve_cli_root(root)
        warn_if_fresh_queue_root(resolved)
        ensure_queue_marker(resolved)
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except Exception as e:
            raise LoopQueueValidationError(
                f"cannot read job config {config}: {e}"
            ) from e
        return WorkflowLoopQueue(
            LoopQueueConfig(queue_root=resolved)
        ).enqueue_dict(data)

    _print_json(_run(action))


@wloop_app.command("status")
def status(
    job_id: Optional[str] = typer.Option(None, "--job-id"),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Show one job or the durable queue summary."""
    queue = _queue(root)
    _print_json(_run(lambda: queue.get(job_id) if job_id else queue.status_summary()))


@wloop_app.command("run-next")
def run_next(
    job_id: Optional[str] = typer.Option(None, "--job-id"),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Emit a VASI hand-off, or consume its drain-result write-back."""
    _print_json(_run(lambda: _queue(root).run_next(job_id)))


@wloop_app.command("drain")
def drain(
    job_id: Optional[str] = typer.Option(None, "--job-id"),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Alias for ``run-next``."""
    _print_json(_run(lambda: _queue(root).run_next(job_id)))


@wloop_app.command("render")
def render(
    job_id: str = typer.Option(..., "--job-id"),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Render/reuse an agent-surface CRP bundle without draining."""
    bundle = _run(lambda: _queue(root).render(job_id))
    _print_json({"job_id": job_id, "bundle_path": str(bundle)})


@wloop_app.command("cancel")
def cancel(
    job_id: str = typer.Option(..., "--job-id"),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Cancel a non-terminal job."""
    _print_json(_run(lambda: _queue(root).cancel(job_id)))


@wloop_app.command("requeue")
def requeue(
    job_id: str = typer.Option(..., "--job-id"),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Explicitly recover a processing, blocked, or failed job (v1 interim)."""
    _print_json(_run(lambda: _queue(root).requeue(job_id)))


@wloop_app.command("triage")
def triage(
    job_id: str = typer.Option(..., "--job-id"),
    decisions: Path = typer.Option(
        ..., "--decisions", exists=True, file_okay=True, dir_okay=False
    ),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
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


@wloop_app.command("channel-back")
def channel_back(
    requirements_path: Path = typer.Option(
        ..., "--requirements-path", exists=False, file_okay=True, dir_okay=False
    ),
    plan_path: Path = typer.Option(
        ..., "--plan-path", exists=False, file_okay=True, dir_okay=False
    ),
    verdict: Optional[str] = typer.Option(
        None, "--verdict", help="Withdrawal scope text (corrected premise)."
    ),
    verdict_file: Optional[Path] = typer.Option(
        None,
        "--verdict-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="Read withdrawal scope from a file (alternative to --verdict).",
    ),
    finding_id: Optional[str] = typer.Option(
        None, "--finding-id", help="Finding id (used in job_id + metadata)."
    ),
    job_id: Optional[str] = typer.Option(
        None, "--job-id", help="Override auto-generated refl-remand-<slug> id."
    ),
    surface_id: str = typer.Option("cursor", "--surface-id"),
    cause: str = typer.Option(
        "design_premise_invalid",
        "--cause",
        help="Withdrawal cause; only design_premise_invalid channels back.",
    ),
    root: Path = typer.Option(DEFAULT_QUEUE_RELATIVE, "--root", help=_ROOT_HELP),
) -> None:
    """Enqueue a reflective-requirements remand from an implement-tick withdrawal.

    Wires design-premise-invalid withdrawals into the existing reflective
    channel (config.scope = verdict). Does not drain; does not move lifecycle
    state.
    """

    def action():
        if bool(verdict) == bool(verdict_file):
            raise LoopQueueValidationError(
                "provide exactly one of --verdict or --verdict-file"
            )
        scope = (
            verdict_file.read_text(encoding="utf-8")
            if verdict_file is not None
            else (verdict or "")
        )
        try:
            cause_enum = WithdrawalCause(cause)
        except ValueError as e:
            raise LoopQueueValidationError(
                f"unknown withdrawal cause {cause!r}; "
                f"expected one of {[c.value for c in WithdrawalCause]}"
            ) from e
        resolved = resolve_cli_root(root)
        warn_if_fresh_queue_root(resolved)
        ensure_queue_marker(resolved)
        queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=resolved))
        return enqueue_withdrawal_remand(
            queue,
            WithdrawalVerdict(
                cause=cause_enum, scope=scope, finding_id=finding_id
            ),
            requirements_path=requirements_path,
            plan_path=plan_path,
            job_id=job_id,
            surface_id=surface_id,
        )

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


@wloop_app.command("list-reviewer-tiers")
def reviewer_tiers() -> None:
    """List FR-23 flagship/mid_tier Cursor Task reviewer presets."""
    _print_json(list_reviewer_tiers())


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
