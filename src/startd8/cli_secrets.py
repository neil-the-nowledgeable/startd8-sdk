# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""secrets CLI command group — inspect/validate the active secrets backend.

All secret values are masked via ``security.mask_api_key`` before display (FR-11).
"""

import os

import typer
from rich.table import Table

from .cli_shared import console
from .security import mask_api_key

secrets_app = typer.Typer(
    name="secrets",
    help="Secrets management — inspect and validate the active backend (e.g. Doppler).",
)


def _manager():
    from .secrets import SecretsManager
    return SecretsManager


def _active_backend_name() -> str:
    """Resolve the configured backend name: env (highest) then SDK config, else 'local'."""
    name = os.environ.get("STARTD8_SECRETS_BACKEND")
    if not name:
        try:
            from .config import get_config_manager
            name = (get_config_manager().get_secrets_backend_config() or {}).get("backend")
        except Exception:
            name = None
    return (name or "local").lower()


@secrets_app.command("status")
def secrets_status() -> None:
    """Show the active backend and how known secrets resolve (masked)."""
    SecretsManager = _manager()
    result = SecretsManager.hydrate()

    console.print(f"[bold]Active secrets backend:[/bold] {result.backend}")
    console.print(f"[bold]Outcome:[/bold] {result.outcome}")
    if result.fetch_failure:
        console.print(f"[yellow]Fetch failure (fail-open):[/yellow] {result.fetch_failure}")
    if result.skipped_dangerous:
        console.print(
            f"[red]Denied (process-control keys):[/red] "
            f"{', '.join(sorted(result.skipped_dangerous))}"
        )

    table = Table(title="Provider credentials")
    table.add_column("Variable", style="cyan")
    table.add_column("Present", justify="center")
    table.add_column("Source")
    table.add_column("Value (masked)")

    known = [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
        "MISTRAL_API_KEY", "NVIDIA_API_KEY", "OLLAMA_HOST",
    ]
    for var in known:
        value = os.environ.get(var)
        present = "✓" if value else "—"
        source = SecretsManager.get_secret_source(var) or "—"
        masked = mask_api_key(value) if value else "—"
        table.add_row(var, present, source, masked)

    console.print(table)


@secrets_app.command("list")
def secrets_list() -> None:
    """List secret names available from the active backend (values masked)."""
    from .secrets import SecretsProviderRegistry

    backend_name = _active_backend_name()
    if backend_name == "local":
        console.print("[dim]Backend 'local' surfaces no remote secrets "
                      "(env + ~/.startd8/config.json apply directly).[/dim]")
        return

    backend = SecretsProviderRegistry.get_backend(backend_name)
    if backend is None:
        console.print(f"[red]Unknown secrets backend: {backend_name}[/red]")
        raise typer.Exit(2)
    try:
        secrets = backend.get_all_secrets()
    except Exception as e:
        console.print(f"[red]Could not list secrets: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Secrets in backend '{backend_name}'")
    table.add_column("Name", style="cyan")
    table.add_column("Value (masked)")
    for name in sorted(secrets):
        table.add_row(name, mask_api_key(secrets[name]) if secrets[name] else "***")
    console.print(table)


@secrets_app.command("test")
def secrets_test() -> None:
    """Validate connectivity/auth to the configured backend.

    Exit codes: 0 = ok (or local no-op), non-zero = auth/connectivity failure.
    """
    from .secrets import SecretsProviderRegistry
    from .secrets.protocol import SecretsBackendError
    from .exceptions import ConfigurationError

    backend_name = _active_backend_name()
    if backend_name == "local":
        console.print("[green]✓[/green] backend 'local' — no remote backend to test (ok).")
        raise typer.Exit(0)

    backend = SecretsProviderRegistry.get_backend(backend_name)
    if backend is None:
        console.print(f"[red]Unknown secrets backend: {backend_name}[/red]")
        raise typer.Exit(2)
    try:
        backend.validate_config()
        count = len(backend.get_all_secrets())
        console.print(f"[green]✓[/green] backend '{backend_name}' reachable — "
                      f"{count} secret(s) available.")
        raise typer.Exit(0)
    except (SecretsBackendError, ConfigurationError) as e:
        console.print(f"[red]✗ backend '{backend_name}' check failed:[/red] {e}")
        raise typer.Exit(1)
