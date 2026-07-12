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
    from .kickoff_experience.cloud_grant import AuditLog, FileGrantStore, GrantMetrics

    audit_cb = AuditLog(audit) if audit is not None else None
    # FR-E4: emit issue/revoke counters (fail-open — a no-op if OTel isn't configured for the CLI).
    return FileGrantStore(store, audit=audit_cb, metrics=GrantMetrics())


def _fmt_expiry(expires_at: float) -> str:
    when = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(timespec="seconds")
    remaining = expires_at - time.time()
    return f"{when} ({'expired' if remaining <= 0 else f'~{int(remaining)}s left'})"


def _parse_ttl(s: str) -> float:
    """Parse a TTL that is either raw seconds ("900") or a human duration ("15m", "1h", "2h30m", "1d")."""
    s = s.strip().lower()
    if not s:
        raise ValueError("empty ttl")
    try:
        return float(s)                          # bare number → seconds
    except ValueError:
        pass
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    total, num = 0.0, ""
    for ch in s:
        if ch.isdigit() or ch == ".":
            num += ch
        elif ch in units and num:
            total += float(num) * units[ch]
            num = ""
        else:
            raise ValueError(f"bad ttl {s!r} (use e.g. 900, 15m, 1h, 2h30m, 1d)")
    if num:                                      # a trailing bare number is seconds
        total += float(num)
    return total


@cloud_grant_app.command("issue")
def issue(
    deployment: str = typer.Option(
        "", "--deployment", envvar="STARTD8_DEPLOYMENT_ID", help="Deployment id the grant is bound to."
    ),
    project: Optional[str] = typer.Option(None, "--project", help="Project id the grant is bound to."),
    for_serve: Optional[Path] = typer.Option(
        None, "--for-serve",
        help="Derive --project from this served project root (matches `kickoff start`'s project_id = "
        "the directory name) so issue and serve cannot drift.",
    ),
    issued_by: str = typer.Option(
        ..., "--issued-by", help="Issuer label (attribution — e.g. your ops handle / change ticket)."
    ),
    capability: str = typer.Option(
        _DEFAULT_CAPABILITY, "--capability", help="Granted capability (default: chat-write)."
    ),
    uses: int = typer.Option(1, "--uses", help="Max uses (default 1)."),
    ttl: str = typer.Option("15m", "--ttl", help="Lifetime — seconds or human (900, 15m, 1h, 2h30m, 1d)."),
    store: Path = typer.Option(
        Path(_DEFAULT_STORE), "--store", envvar="STARTD8_GRANT_STORE",
        help="Grant store path (the served app reads THIS file).",
    ),
    audit: Path = typer.Option(
        Path(_DEFAULT_AUDIT), "--audit", envvar="STARTD8_GRANT_AUDIT",
        help="Append-only audit log path (fail-closed).",
    ),
) -> None:
    """Mint a temporary grant. Fail-closed: an un-writable store or audit sink aborts with no grant."""
    from .kickoff_experience.cloud_grant import GrantTarget

    project = project or (for_serve.resolve().name if for_serve else None)
    if not project:
        console.print("[red]provide --project or --for-serve <project-root>[/red]")
        raise typer.Exit(2)
    if not deployment:
        console.print("[red]provide --deployment (or set STARTD8_DEPLOYMENT_ID)[/red]")
        raise typer.Exit(2)
    try:
        ttl_seconds = _parse_ttl(ttl)
        s = _open_store(store, audit)
        g = s.issue(
            GrantTarget(deployment, project, capability),
            uses=uses, ttl_seconds=ttl_seconds, now=time.time(), issued_by=issued_by,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2)
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
    store: Path = typer.Option(
        Path(_DEFAULT_STORE), "--store", envvar="STARTD8_GRANT_STORE", help="Grant store path."
    ),
    live_only: bool = typer.Option(False, "--live-only", help="Show only live (unexpired/unexhausted) grants."),
) -> None:
    """List grants in the store (read-only; does not consume). Warns on grants near expiry."""
    try:
        grants = _open_store(store, None).all_grants()
    except Exception as exc:
        console.print(f"[red]list failed:[/red] {exc}")
        raise typer.Exit(1)
    now = time.time()

    def _live(g):
        return not g.revoked and g.uses_remaining > 0 and g.expires_at > now

    if live_only:
        grants = [g for g in grants if _live(g)]
    if not grants:
        console.print("[dim]no grants in the store.[/dim]")
        return
    for g in sorted(grants, key=lambda x: x.issued_at, reverse=True):
        state = "[red]revoked[/red]" if g.revoked else (
            "[yellow]exhausted[/yellow]" if g.uses_remaining <= 0 else (
                "[yellow]expired[/yellow]" if g.expires_at <= now else "[green]live[/green]"))
        near = ""
        if _live(g) and (g.expires_at - now) <= 60:
            near = "  [yellow]⚠ expires <60s[/yellow]"
        console.print(
            f"[cyan]{g.id}[/cyan]  {state}  {g.target.deployment_id}/{g.target.project_id}/"
            f"{g.target.capability}  uses={g.uses_remaining}  expires={_fmt_expiry(g.expires_at)}  "
            f"by={g.issued_by}{near}"
        )


@cloud_grant_app.command("status")
def status(
    audit: Path = typer.Option(
        Path(_DEFAULT_AUDIT), "--audit", envvar="STARTD8_GRANT_AUDIT", help="Append-only audit log path."
    ),
    tail: int = typer.Option(10, "--tail", help="How many recent events to show."),
) -> None:
    """Summarize grant activity from the audit log — issued/consumed/revoked counts + recent events.

    Offline + no metrics stack required: reads the append-only audit JSONL the store writes.
    """
    import json

    if not audit.is_file():
        console.print(f"[dim]no audit log at {audit} — nothing issued/consumed yet.[/dim]")
        return
    events = []
    for line in audit.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    counts = {}
    for e in events:
        counts[e.get("event", "?")] = counts.get(e.get("event", "?"), 0) + 1
    console.print(
        f"[bold]grant activity[/bold] ({len(events)} events): "
        + "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    )
    for e in events[-max(0, tail):]:
        ev = e.get("event", "?")
        gid = str(e.get("grant_id", ""))[:12]
        extra = e.get("issued_by") or (f"uses_after={e.get('uses_remaining_after')}"
                                        if ev == "consume" else "")
        console.print(f"  [cyan]{ev:<8}[/cyan] {gid}  {extra}")


@cloud_grant_app.command("gc")
def gc(
    store: Path = typer.Option(
        Path(_DEFAULT_STORE), "--store", envvar="STARTD8_GRANT_STORE", help="Grant store path."
    ),
) -> None:
    """Prune expired / exhausted / revoked grants from the store (keeps it from growing unbounded)."""
    try:
        removed = _open_store(store, None).prune(time.time())
    except Exception as exc:
        console.print(f"[red]gc failed:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[green]pruned {removed}[/green] dead grant(s) from {store}.")
