"""``startd8 capdevpipe`` — embed install (TUI) and headless orchestration run (FR-17)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .capdevpipe_runner import run_embedded_pipeline
from .cli_shared import console
from .exceptions import Startd8Error

capdevpipe_app = typer.Typer(
    help="Embed and run the cap-dev-pipe capability delivery pipeline.",
)

_EXIT_OK = 0
_EXIT_ERROR = 1


@capdevpipe_app.callback()
def _capdevpipe_callback() -> None:
    """cap-dev-pipe embed + orchestration helpers."""


@capdevpipe_app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Run the embedded pipeline (`python3 -m pipeline run` equivalent without bash).",
)
def run_command(
    ctx: typer.Context,
    embed_dir: Optional[Path] = typer.Option(
        None,
        "--embed-dir",
        help=f"Path to {'.cap-dev-pipe'}/ (default: discover under current directory)",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to pipeline.yaml (default: <embed-dir>/pipeline.yaml)",
    ),
) -> None:
    """Delegate to the embedded Python orchestrator with passthrough pipeline flags."""
    try:
        exit_code = run_embedded_pipeline(
            cwd=Path.cwd(),
            embed_dir=embed_dir,
            extra_argv=list(ctx.args),
            config_path=config,
        )
    except Startd8Error as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(_EXIT_ERROR) from exc

    if exit_code != _EXIT_OK:
        raise typer.Exit(exit_code)
