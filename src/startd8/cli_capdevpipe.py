"""``startd8 capdevpipe`` — embed install (headless CLI + TUI) and orchestration run (FR-17)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from .capdevpipe_runner import run_embedded_pipeline
from .cli_shared import console
from .exceptions import Startd8Error

capdevpipe_app = typer.Typer(
    help="Embed and run the cap-dev-pipe capability delivery pipeline.",
)

_EXIT_OK = 0
_EXIT_ERROR = 1


def _parse_set_env(pairs: Optional[List[str]]) -> dict[str, str]:
    """Parse repeatable ``--set-env KEY=VALUE`` overrides into a dict."""
    out: dict[str, str] = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise typer.BadParameter(f"--set-env expects KEY=VALUE, got: {raw!r}")
        key, _, value = raw.partition("=")
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"--set-env has an empty key: {raw!r}")
        out[key] = value
    return out


def _parse_profiles(specs: Optional[List[str]]):
    """Parse repeatable ``--profile lang[:plan[:reqs]]`` into ProfileSpec objects."""
    from .capdevpipe_installer import ProfileSpec

    profiles = []
    for raw in specs or []:
        parts = raw.split(":")
        lang = parts[0].strip()
        if not lang:
            raise typer.BadParameter(f"--profile needs a language, got: {raw!r}")
        plan = Path(parts[1]).expanduser() if len(parts) > 1 and parts[1] else None
        reqs = Path(parts[2]).expanduser() if len(parts) > 2 and parts[2] else None
        profiles.append(ProfileSpec(lang=lang, plan=plan, reqs=reqs))
    return profiles


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


@capdevpipe_app.command(
    "install",
    help="Embed cap-dev-pipe into a project (headless; wraps the install engine).",
)
def install_command(
    target_root: Path = typer.Option(
        Path.cwd(),
        "--target-root",
        "-t",
        help="Project root to install into (default: current directory).",
    ),
    source_path: Optional[Path] = typer.Option(
        None,
        "--source-path",
        "-s",
        help="cap-dev-pipe checkout to embed (default: ~/Documents/dev/cap-dev-pipe).",
    ),
    method: str = typer.Option(
        "symlink",
        "--method",
        "-m",
        help="Embed method: symlink (single source of truth) or copy (self-contained).",
    ),
    embed_profile: str = typer.Option(
        "full",
        "--embed-profile",
        help="Embed profile from embed-manifest.yaml: minimal | orchestrator | full.",
    ),
    default_lang: str = typer.Option(
        "python", "--default-lang", help="Default language for the generated wrapper."
    ),
    profile: Optional[List[str]] = typer.Option(
        None,
        "--profile",
        help="Language profile as lang[:plan[:reqs]] (repeatable).",
    ),
    set_env: Optional[List[str]] = typer.Option(
        None,
        "--set-env",
        help="Override a managed pipeline.env key: KEY=VALUE (repeatable).",
    ),
    rerun_mode: Optional[str] = typer.Option(
        None,
        "--rerun-mode",
        help="On an existing install: reconfigure | upgrade | repair | "
        "replace-pipeline.env | doctor.",
    ),
    trust_source: bool = typer.Option(
        False,
        "--trust-source",
        help="Allow the copy installer to run from a non-default source checkout.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the exact action list without writing anything.",
    ),
) -> None:
    """Install cap-dev-pipe into *target_root*, driving ``CapDevPipeInstaller`` headlessly.

    Mirrors the TUI install flow (``mixin_capdevpipe``) without any prompts: build a fully
    resolved ``InstallConfig``, populate the four managed ``pipeline.env`` keys (detect +
    ``--set-env``), then either apply a re-run mode against an existing install or plan →
    (preview on ``--dry-run``) → execute → verify a fresh one.
    """
    from .capdevpipe_installer import (
        CapDevPipeInstaller,
        InstallConfig,
        InstallMethod,
        ReRunMode,
    )

    try:
        install_method = InstallMethod(method)
    except ValueError as exc:
        raise typer.BadParameter(f"--method must be 'symlink' or 'copy', got {method!r}") from exc
    mode: Optional[ReRunMode] = None
    if rerun_mode is not None:
        try:
            mode = ReRunMode(rerun_mode)
        except ValueError as exc:
            valid = ", ".join(m.value for m in ReRunMode)
            raise typer.BadParameter(
                f"--rerun-mode must be one of: {valid}; got {rerun_mode!r}"
            ) from exc

    installer = CapDevPipeInstaller()
    try:
        source = installer.locate_source(source_path)  # validates the checkout (FR-2)
        cfg = InstallConfig(
            source_path=source,
            target_root=target_root.expanduser(),
            method=install_method,
            pipeline_env={},
            default_lang=default_lang or "python",
            profiles=_parse_profiles(profile),
            rerun_mode=mode,
            trust_source=trust_source,
            embed_profile=embed_profile,
        )
        # Populate the four managed keys (detect, then apply --set-env overrides). execute()
        # blocks on any blank managed key, so this must happen before we call it (D5/FR-A9).
        env = installer.detect_pipeline_env(cfg)
        env.update(_parse_set_env(set_env))
        cfg.pipeline_env = env

        state = installer.detect_existing(cfg.target_root)

        # Existing install + explicit re-run mode → apply that mode, then verify.
        if state.exists and mode is not None:
            if mode is ReRunMode.DOCTOR:
                vr = installer.doctor(cfg.target_root)
            else:
                installer.apply_mode(cfg.target_root, mode, cfg)
                vr = installer.verify(cfg.target_root)
            _render_verify(cfg, vr, mode=mode)
            raise typer.Exit(_EXIT_OK if vr.passed else _EXIT_ERROR)

        # Fresh install: plan → (preview and stop on --dry-run) → execute → verify.
        actions = installer.plan_actions(cfg)
        if dry_run:
            console.print(
                f"[bold]cap-dev-pipe install — dry run[/bold] "
                f"(target: {cfg.target_root}, method: {cfg.method.value}, "
                f"profile: {cfg.embed_profile})"
            )
            for action in actions:
                console.print(f"  • {action.describe()}")
            console.print(f"[dim]{len(actions)} action(s) planned; nothing written.[/dim]")
            return

        result = installer.execute(cfg, actions=actions)
        if not result.success:
            tail = (
                "Rolled back cleanly."
                if result.rolled_back
                else "Left repairable — re-run with --rerun-mode repair."
                if result.repairable
                else ""
            )
            console.print(f"[red]install failed[/red]: {result.error}\n{tail}")
            raise typer.Exit(_EXIT_ERROR)

        vr = installer.verify(cfg.target_root)
        _render_verify(cfg, vr, installed=True)
        raise typer.Exit(_EXIT_OK if vr.passed else _EXIT_ERROR)
    except Startd8Error as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(_EXIT_ERROR) from exc


def _render_verify(cfg, vr, *, mode=None, installed: bool = False) -> None:
    """Render a verify/doctor result for the headless CLI (no Rich Panels / prompts)."""
    label = f" ({mode.value})" if mode is not None else ""
    if vr.passed:
        console.print(f"[green]✓ cap-dev-pipe verified{label}[/green]: {vr.message}")
        if installed:
            wrapper = f"./.cap-dev-pipe/{cfg.target_root.name}-cap-dlv-pipe.sh"
            console.print(f"  run the pipeline with: [cyan]{wrapper}[/cyan]")
    else:
        console.print(f"[red]✗ cap-dev-pipe verify FAILED{label}[/red]: {vr.message}")
