"""``startd8 deploy`` — run a generated app locally and grade it (deploy harness, FR-14).

``deploy local <root>`` deploys one app root; ``deploy batch <dir>`` (M3) deploys a directory of
per-model app roots. v1 isolation is throwaway-venv + subprocess + loopback — the apps are UNTRUSTED
(raw LLM output). See ``docs/design/local-deploy-harness/``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .cli_shared import console

deploy_app = typer.Typer(
    help="Deploy a generated app locally and grade it (discover→boot→health→smoke)."
)


@deploy_app.callback()
def _deploy_callback() -> None:
    """Presence of a callback keeps this a command *group* (subcommand name required)."""


_STAGE_STYLE = {
    "pass": "green",
    "fail": "red",
    "skipped": "yellow",
    "not_reached": "dim",
}


@deploy_app.command("local")
def local(
    app_root: Path = typer.Argument(
        ..., help="App root (dir containing the generated app/ package)."
    ),
    model: str = typer.Option(
        None, "--model", help="Verbatim model id, recorded in the result."
    ),
    install_timeout: float = typer.Option(
        600.0, "--install-timeout", help="pip install timeout (s)."
    ),
    boot_timeout: float = typer.Option(
        60.0, "--boot-timeout", help="Server boot timeout (s)."
    ),
    keep: bool = typer.Option(
        False, "--keep", help="Keep the throwaway venv/work dir for debugging."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the LadderResult as JSON (for CI)."
    ),
) -> None:
    """Run one generated app through the graded ladder and report the outcome."""
    from .deploy_harness import deploy_app_local

    if not app_root.is_dir():
        console.print(f"[red]not a directory:[/red] {app_root}")
        raise typer.Exit(2)

    result = deploy_app_local(
        app_root,
        model=model,
        install_timeout_s=install_timeout,
        boot_timeout_s=boot_timeout,
        keep=keep,
    )

    if json_out:
        console.print_json(result.to_json())
    else:
        console.print(f"[bold]{result.summary()}[/bold]")
        for stage_name, sr in result.stages.items():
            style = _STAGE_STYLE.get(sr.status.value, "white")
            reason = f" — {sr.reason}" if sr.reason else ""
            console.print(
                f"  [{style}]{stage_name:9}[/{style}] {sr.status.value}{reason}"
            )
        if result.deviations:
            console.print(
                "  [yellow]deviations:[/yellow] "
                + ", ".join(d.code for d in result.deviations)
            )

    # Exit code: 0 if the app reached a clean health rung, else 1 (3 if it never started).
    health = result.stages.get("health")
    if health and health.status.value == "pass":
        raise typer.Exit(0)
    raise typer.Exit(1)
