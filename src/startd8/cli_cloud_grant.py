"""M4b — the operator control-plane CLI for cloud-authorization grants (OQ-4).

``startd8 cloud-grant issue|revoke|list`` is run by a human/operator **with the deployment platform's
own identity** (SSH / cloud IAM / kubectl / CI), writing the grant store **out-of-band**. The served
kickoff app only **reads + consumes** what you issue here — issuance is intentionally **not** a served
endpoint (NR-6), and the issuance surface (this CLI + your platform credentials) is **distinct** from
the served app's consumer ``--api-key``. Every issue/revoke is appended to a fail-closed audit log.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from .cli_shared import console

cloud_grant_app = typer.Typer(
    name="cloud-grant",
    help="Operator control plane for cloud-authorization grants (OQ-4): temporarily authorize a cloud "
    "kickoff deployment's agentic chat-write path — use-limited, expiring, revocable. Run with the "
    "platform's identity; the served app only consumes what you issue here.",
)

_DEFAULT_STORE = ".startd8/cloud-grants/grants.json"
_DEFAULT_AUDIT = ".startd8/cloud-grants/audit.jsonl"
_DEFAULT_CAPABILITY = "chat-write"
_DEFAULT_TTL = 900.0   # 15 min (OQ-3 lean)


def _open_store(store: Path, audit: Optional[Path]):
    from .kickoff_experience.cloud_grant import AuditLog, FileGrantStore

    audit_cb = AuditLog(audit) if audit is not None else None
    return FileGrantStore(store, audit=audit_cb)


def _fmt_expiry(expires_at: float) -> str:
    when = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(timespec="seconds")
    remaining = expires_at - time.time()
    return f"{when} ({'expired' if remaining <= 0 else f'~{int(remaining)}s left'})"


@cloud_grant_app.command("issue")
def issue(
    deployment: str = typer.Option(..., "--deployment", help="Deployment id the grant is bound to."),
    project: str = typer.Option(..., "--project", help="Project id the grant is bound to."),
    issued_by: str = typer.Option(
        ..., "--issued-by", help="Issuer label (attribution — e.g. your ops handle / change ticket)."
    ),
    capability: str = typer.Option(
        _DEFAULT_CAPABILITY, "--capability", help="Granted capability (default: chat-write)."
    ),
    uses: int = typer.Option(1, "--uses", help="Max uses (default 1)."),
    ttl: float = typer.Option(_DEFAULT_TTL, "--ttl", help="Lifetime in seconds (default 900 = 15 min)."),
    store: Path = typer.Option(
        Path(_DEFAULT_STORE), "--store", help="Grant store path (the served app reads THIS file)."
    ),
    audit: Path = typer.Option(
        Path(_DEFAULT_AUDIT), "--audit", help="Append-only audit log path (fail-closed)."
    ),
) -> None:
    """Mint a temporary grant. Fail-closed: an un-writable store or audit sink aborts with no grant."""
    from .kickoff_experience.cloud_grant import GrantTarget

    try:
        s = _open_store(store, audit)
        g = s.issue(
            GrantTarget(deployment, project, capability),
            uses=uses, ttl_seconds=ttl, now=time.time(), issued_by=issued_by,
        )
    except Exception as exc:
        console.print(f"[red]issue failed[/red] (fail-closed — no grant written): {exc}")
        raise typer.Exit(1)
    console.print(f"[green]grant issued:[/green] [cyan]{g.id}[/cyan]")
    console.print(
        f"  target={deployment}/{project}/{capability}  uses={g.uses_remaining}  "
        f"expires={_fmt_expiry(g.expires_at)}  by={issued_by}"
    )
    console.print(f"[dim]store: {store}  ·  the served app consumes this on session creation.[/dim]")


@cloud_grant_app.command("revoke")
def revoke(
    grant_id: str = typer.Argument(..., help="The grant id to revoke (immediately void)."),
    store: Path = typer.Option(Path(_DEFAULT_STORE), "--store", help="Grant store path."),
    audit: Path = typer.Option(Path(_DEFAULT_AUDIT), "--audit", help="Append-only audit log path."),
) -> None:
    """Immediately void a grant (FR-4). The next per-turn re-validation on any live session denies."""
    try:
        s = _open_store(store, audit)
        ok = s.revoke(grant_id)
    except Exception as exc:
        console.print(f"[red]revoke failed[/red] (fail-closed): {exc}")
        raise typer.Exit(1)
    if not ok:
        console.print(f"[yellow]no such grant:[/yellow] {grant_id}")
        raise typer.Exit(2)
    console.print(f"[green]grant revoked:[/green] {grant_id}")


@cloud_grant_app.command("list")
def list_grants(
    store: Path = typer.Option(Path(_DEFAULT_STORE), "--store", help="Grant store path."),
) -> None:
    """List all grants in the store (read-only; does not consume)."""
    try:
        grants = _open_store(store, None).all_grants()
    except Exception as exc:
        console.print(f"[red]list failed:[/red] {exc}")
        raise typer.Exit(1)
    if not grants:
        console.print("[dim]no grants in the store.[/dim]")
        return
    for g in sorted(grants, key=lambda x: x.issued_at, reverse=True):
        state = "[red]revoked[/red]" if g.revoked else (
            "[yellow]exhausted[/yellow]" if g.uses_remaining <= 0 else "[green]live[/green]")
        console.print(
            f"[cyan]{g.id}[/cyan]  {state}  {g.target.deployment_id}/{g.target.project_id}/"
            f"{g.target.capability}  uses={g.uses_remaining}  expires={_fmt_expiry(g.expires_at)}  "
            f"by={g.issued_by}"
        )
