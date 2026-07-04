# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""panel CLI command group — query the live Stakeholder Panel (FR-8).

``list`` is ``$0``/read-only (just reads the roster). ``ask`` / ``ask-all`` are the **paid** surface
and, per OQ-7/NR-7, live here on the CLI (the only spend-authorized path) — never on the ``$0``
Concierge read floor. Every synthetic answer is rendered with an "unratified" banner so it is never
mistaken for a ratified fact (FR-19). ``import`` ingests an external persona format into a roster
($0, one-way). Exit codes: 0 ok; 1 runtime; 2 unreadable/invalid roster or unknown --format;
3 unreadable/malformed source; 4 round-trip-gate rejection; 5 clobber refused.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import List, Optional

import typer

from .cli_shared import console

panel_app = typer.Typer(
    name="panel",
    help="Query the synthetic stakeholder panel: list (read-only), ask/ask-all (paid, synthetic).",
)

_EXIT_FATAL_INPUTS = 2
_EXIT_RUNTIME = 1
# Distinct exit codes for `panel import` (FR-6/R2-F5), so a CI job can branch on WHY it failed.
_EXIT_SOURCE = 3  # source unreadable / malformed (adapter error during adapt)
_EXIT_GATE = 4  # adapter emitted a roster that failed the round-trip gate
_EXIT_CLOBBER = 5  # refused to overwrite an existing roster
_ROSTER_REL = Path("docs") / "kickoff" / "inputs" / "stakeholders.yaml"


def _emit_json(result) -> None:
    import sys

    sys.stdout.write(json.dumps(result, indent=2) + "\n")


def _roster_path(project_root: Path) -> Path:
    return project_root / _ROSTER_REL


def _load_or_exit(project_root: Path):
    """Load + validate the roster or exit(2) with a readable message."""
    from .stakeholder_panel import RosterError, load_roster, validate_roster

    path = _roster_path(project_root)
    if not path.is_file():
        console.print(
            f"[red]panel:[/red] no roster at {path} — run `startd8 kickoff instantiate` first."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    try:
        roster = load_roster(path)
    except RosterError as exc:
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    issues = validate_roster(roster)
    if issues:
        console.print("[red]panel:[/red] roster is invalid:")
        for issue in issues:
            console.print(f"  - {issue}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    return roster


def _render_answer(answer) -> None:
    """Print one answer with a persistent synthetic/unratified banner (FR-19)."""
    from .stakeholder_panel.models import Grounding

    head = f"[bold]{answer.role_id}[/bold] [dim]({answer.grounding.value})[/dim]"
    console.print(head)
    console.print(f"  {answer.text}")
    if answer.grounding is Grounding.UNAVAILABLE:
        console.print(
            "  [yellow]⚠ stakeholder unavailable — no answer produced[/yellow]"
        )
    else:
        console.print(
            "  [yellow]⚠ SYNTHETIC, UNRATIFIED[/yellow] — a role-played stand-in, not a real "
            "stakeholder. Confirm with a human before relying on it."
        )
    for flag in answer.flags:  # FR-7 (M3): grounding-guard advisories
        console.print(f"  [yellow]⚠ grounding check:[/yellow] {flag}")
    if answer.cost_usd:
        console.print(f"  [dim]cost ${answer.cost_usd:.5f} · {answer.model}[/dim]")


@panel_app.command("list")
def panel_list(
    project_root: Path = typer.Argument(
        Path("."), help="Project root (default: current dir)."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit roster JSON to stdout."),
) -> None:
    """List the personas on the roster ($0, read-only — no LLM)."""
    roster = _load_or_exit(project_root)
    if json_out:
        _emit_json(roster.to_dict())
        return
    console.print(
        f"[bold]Stakeholder panel roster[/bold] — {_roster_path(project_root)}"
    )
    for p in roster.personas:
        console.print(
            f"  [bold]{p.role_id}[/bold] — {p.display_name} ({len(p.goals)} goals)"
        )


@panel_app.command("ask")
def panel_ask(
    role_id: str = typer.Option(
        ..., "--role", help="The persona to ask (a roster role_id)."
    ),
    question: str = typer.Argument(..., help="The question to pose."),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    model: Optional[str] = typer.Option(
        None, "--model", help="Agent spec (default: SDK cheap model)."
    ),
) -> None:
    """Ask ONE persona a question (paid). The answer is synthetic, unratified input."""
    roster = _load_or_exit(project_root)
    from .stakeholder_panel import UnknownPersonaError
    from .stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel

    panel = StakeholderPanel(
        roster, project_root=project_root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        answer = asyncio.run(panel.ask(role_id, question))
    except UnknownPersonaError as exc:
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    except (
        Exception
    ) as exc:  # provider/auth/budget failure — clean message, not a traceback
        console.print(f"[red]panel:[/red] query failed: {exc}")
        raise typer.Exit(_EXIT_RUNTIME)
    finally:
        panel.close()
    _render_answer(answer)


@panel_app.command("ask-all")
def panel_ask_all(
    question: str = typer.Argument(..., help="The question to pose to every persona."),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    cap: Optional[int] = typer.Option(
        None, "--cap", help="Max personas to actually query (FR-17)."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Agent spec (default: SDK cheap model)."
    ),
) -> None:
    """Ask EVERY persona the same question (paid, bounded by --cap)."""
    roster = _load_or_exit(project_root)
    from .stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel

    panel = StakeholderPanel(
        roster, project_root=project_root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        answers = asyncio.run(panel.ask_all(question, cap=cap))
    except (
        Exception
    ) as exc:  # provider/auth/budget failure — clean message, not a traceback
        console.print(f"[red]panel:[/red] query failed: {exc}")
        raise typer.Exit(_EXIT_RUNTIME)
    finally:
        panel.close()
    for answer in answers:
        _render_answer(answer)
    total = sum(a.cost_usd for a in answers)
    if total:
        console.print(
            f"[dim]total cost ${total:.5f} across {len(answers)} personas[/dim]"
        )


@panel_app.command("import")
def panel_import(
    source: Path = typer.Argument(
        ..., help="External persona-format file to ingest (e.g. a reviewer_roles.yaml)."
    ),
    fmt: str = typer.Option(
        ...,
        "--format",
        help="Adapter name (see the roster-adapter registry, e.g. role-rubric).",
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Roster output path (default: the project's stakeholders.yaml).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing roster."),
) -> None:
    """Ingest an external persona format into a validated roster ($0, one-way, CLI-only writer)."""
    from .stakeholder_panel import AdapterError
    from .stakeholder_panel.adapters import available
    from .stakeholder_panel.ingest import IngestGateError, ingest, looks_generated

    # 1. Unknown format → exit 2, listing what is registered.
    known = available()
    if fmt not in known:
        console.print(
            f"[red]panel:[/red] unknown --format {fmt!r}. Available: {', '.join(known) or 'none'}"
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    # 2. Read the source (CLI owns file I/O; adapters take text).
    try:
        source_text = source.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]panel:[/red] cannot read source {source}: {exc}")
        raise typer.Exit(_EXIT_SOURCE)

    # 3. Adapt + round-trip gate.
    try:
        result = ingest(fmt, source_text, source=str(source))
    except IngestGateError as exc:  # adapter emitted a bad roster
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_GATE)
    except AdapterError as exc:  # malformed source
        console.print(f"[red]panel:[/red] {exc}")
        raise typer.Exit(_EXIT_SOURCE)

    # 4. Resolve destination + clobber guard (R1-S8).
    dest = out if out is not None else (project_root / _ROSTER_REL)
    if dest.exists():
        if (
            not dest.is_file()
        ):  # a directory (or socket/etc.) at the path — never overwrite
            console.print(f"[red]panel:[/red] {dest} exists but is not a regular file.")
            raise typer.Exit(_EXIT_CLOBBER)
        try:
            existing = dest.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(
                f"[red]panel:[/red] cannot read existing roster {dest}: {exc}"
            )
            raise typer.Exit(_EXIT_CLOBBER)
        if not force:
            hint = "" if looks_generated(existing) else "looks hand-authored — "
            console.print(
                f"[red]panel:[/red] {dest} already exists ({hint}pass --force to overwrite)."
            )
            raise typer.Exit(_EXIT_CLOBBER)
        if not looks_generated(existing):
            console.print(
                f"[yellow]panel:[/yellow] ⚠ overwriting a hand-authored roster at {dest} (--force)."
            )

    # 5. Write atomically (tmp + rename) so an interrupted write can't corrupt the prior roster.
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(result.yaml_text, encoding="utf-8")
    os.replace(tmp, dest)
    console.print(
        f"[green]panel:[/green] imported {len(result.roster.personas)} personas "
        f"via {fmt} → {dest}"
    )
    for warning in result.warnings:
        console.print(f"  [yellow]⚠[/yellow] {warning}")


# --------------------------------------------------------------------------- #
# Teian — proactive input recommendations (FR-KIR-8/9/10/11).
# recommend = paid drafting pass; review = $0 render; approve/reject = the human decision surface.
# --------------------------------------------------------------------------- #

_DRAFT_BANNER = (
    "[yellow]⚠ DRAFTED STARTERS, UNRATIFIED[/yellow] — role-played estimates, not real values. "
    "Review, then approve (or edit the YAML) before relying on them."
)


def _try_load_roster(project_root: Path):
    """Load the roster, returning ``None`` (not exiting) if absent/invalid — for review/approve."""
    from .stakeholder_panel import RosterError, load_roster, validate_roster

    path = _roster_path(project_root)
    if not path.is_file():
        return None
    try:
        roster = load_roster(path)
    except RosterError:
        return None
    return roster if not validate_roster(roster) else None


def _resolve_session(project_root: Path, session: Optional[str]) -> str:
    """Resolve the staging session: the named one, the only one, or exit(2) on absent/ambiguous (R1-F2)."""
    from .stakeholder_panel.proposals import session_ids

    ids = session_ids(project_root)
    if session:
        if session not in ids:
            console.print(
                f"[red]panel:[/red] no staged session {session!r} (have: {', '.join(ids) or 'none'})"
            )
            raise typer.Exit(_EXIT_FATAL_INPUTS)
        return session
    if not ids:
        console.print(
            "[red]panel:[/red] no staged proposals — run `startd8 panel recommend` first."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    if len(ids) > 1:
        console.print(
            f"[red]panel:[/red] multiple sessions ({', '.join(ids)}); pass --session <id>."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    return ids[0]


def _split_field(field: str) -> tuple:
    """Split a ``<domain>:<value_path>`` selector; exit(2) if malformed."""
    if ":" not in field:
        console.print(
            f"[red]panel:[/red] --field must be <domain>:<value_path>, got {field!r}"
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    domain, value_path = field.split(":", 1)
    return domain.strip(), value_path.strip()


def _field_now_filled(project_root: Path, rec) -> bool:
    """True iff the rec's field is no longer unfilled in the live YAML (stale draft, R3-S3)."""
    from .stakeholder_panel.input_domains import get_domain, unfilled_fields

    spec = get_domain(rec.domain)
    path = project_root / spec.rel_path() if spec else None
    if spec is None or path is None or not path.is_file():
        return False
    unfilled = {
        s.value_path for s in unfilled_fields(spec, path.read_text(encoding="utf-8"))
    }
    return rec.value_path not in unfilled


def _fmt_value(rec) -> str:
    if rec.is_composite and isinstance(rec.recommended_value, dict):
        return ", ".join(f"{k}={v!r}" for k, v in rec.recommended_value.items())
    return repr(rec.recommended_value)


@panel_app.command("recommend")
def panel_recommend(
    domain: Optional[List[str]] = typer.Option(
        None, "--domain", help="Restrict to these value domains (repeatable)."
    ),
    cap: Optional[int] = typer.Option(
        None, "--cap", help="Max fields to draft (FR-KIR-12)."
    ),
    redraft: bool = typer.Option(
        False, "--redraft", help="Re-draft fields that already have a pending draft."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Agent spec (default: cheap model)."
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
) -> None:
    """Draft starter values for unfilled kickoff-input fields (paid). Estimates, staged for review."""
    roster = _load_or_exit(project_root)
    from .stakeholder_panel import recommend_inputs
    from .stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel
    from .stakeholder_panel.proposals import gc_stale_proposals

    panel = StakeholderPanel(
        roster, project_root=project_root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        run = asyncio.run(
            recommend_inputs(
                project_root, panel, domains=domain or None, cap=cap, redraft=redraft
            )
        )
    except Exception as exc:  # provider/auth failure — clean message, not a traceback
        console.print(f"[red]panel:[/red] recommend failed: {exc}")
        raise typer.Exit(_EXIT_RUNTIME)
    finally:
        panel.close()
    gc_stale_proposals(project_root)

    console.print(
        f"[bold]drafted {run.fields_drafted} field(s)[/bold] "
        f"(session {run.session_id}, ${run.total_cost_usd:.5f})"
    )
    for rec in run.recommendations:
        console.print(
            f"  [bold]{rec.domain}:{rec.value_path}[/bold] → {_fmt_value(rec)}"
        )
    skipped = {}
    for s in run.skipped:
        skipped[s["status"]] = skipped.get(s["status"], 0) + 1
    if skipped:
        summary = ", ".join(f"{n} {k}" for k, n in sorted(skipped.items()))
        console.print(f"  [dim]skipped: {summary}[/dim]")
    if run.fields_drafted:
        console.print(_DRAFT_BANNER)
        console.print(
            "  next: [bold]startd8 panel review[/bold] then [bold]panel approve[/bold]"
        )


@panel_app.command("review")
def panel_review(
    session: Optional[str] = typer.Option(
        None, "--session", help="Staging session (default: the only/latest)."
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
) -> None:
    """Render pending drafts with their persona brief + the gap they fill ($0, anti-anchoring)."""
    from .stakeholder_panel.proposals import ProposalStore
    from .stakeholder_panel.recommend_apply import roster_version_of
    from .stakeholder_panel.telemetry import EV_REVIEWED, decision_event

    sess = _resolve_session(project_root, session)
    recs = [
        r for r in ProposalStore(project_root, sess).load() if r.disposition == "draft"
    ]
    roster = _try_load_roster(project_root)
    briefs = {p.role_id: p for p in roster.personas} if roster else {}
    live_ver = roster_version_of(roster) if roster else ""

    shown = 0
    for rec in recs:
        if _field_now_filled(project_root, rec):
            continue  # stale draft — the human filled it directly (R3-S3)
        shown += 1
        console.print(
            f"\n[bold]{rec.domain}:{rec.value_path}[/bold]  [dim]({rec.grounding.value})[/dim]"
        )
        console.print(f"  recommended: {_fmt_value(rec)}")
        if rec.rationale:
            console.print(f"  why: {rec.rationale}")
        console.print(f"  drafted by: [bold]{rec.role_id}[/bold] ({rec.origin})")
        brief = briefs.get(rec.role_id)
        if brief and brief.goals:
            console.print(
                f"  brief goals: {'; '.join(brief.goals)}"
            )  # brief adjacent (FR-KIR-9)
        if live_ver and rec.roster_version and rec.roster_version != live_ver:
            console.print(
                "  [yellow]⚠ roster context has changed since this draft (R4-F2)[/yellow]"
            )
        for flag in rec.flags:
            console.print(f"  [yellow]⚠ contradiction:[/yellow] {flag}")
        decision_event(
            EV_REVIEWED,
            domain=rec.domain,
            role_id=rec.role_id,
            value_path=rec.value_path,
        )
    if not shown:
        console.print(f"[dim]no pending drafts in session {sess}.[/dim]")
        return
    console.print(f"\n{_DRAFT_BANNER}")
    console.print(
        "  approve: [bold]startd8 panel approve --field <domain>:<value_path>[/bold] (or --all)"
    )


@panel_app.command("approve")
def panel_approve(
    field: Optional[str] = typer.Option(
        None, "--field", help="<domain>:<value_path> to approve."
    ),
    all_: bool = typer.Option(
        False, "--all", help="Approve every pending draft (R1-S2)."
    ),
    session: Optional[str] = typer.Option(
        None, "--session", help="Staging session (default: the only/latest)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Apply even if the field was edited in the YAML."
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
) -> None:
    """Promote approved drafts into the domain YAML via a comment-preserving splice (CLI-as-writer)."""
    if not field and not all_:
        console.print("[red]panel:[/red] pass --field <domain>:<value_path> or --all.")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    from .stakeholder_panel.input_domains import get_domain
    from .stakeholder_panel.proposals import ProposalStore
    from .stakeholder_panel.recommend_apply import (
        apply_recommendation,
        approvable,
        domain_fully_resolved,
    )
    from .stakeholder_panel.telemetry import EV_APPROVED, decision_event

    sess = _resolve_session(project_root, session)
    store = ProposalStore(project_root, sess)
    recs = store.load()
    if all_:
        targets = approvable(recs)
    else:
        domain, value_path = _split_field(field)
        rec = store.get(domain, value_path)
        if rec is None:
            console.print(
                f"[red]panel:[/red] no staged draft {domain}:{value_path} in session {sess}."
            )
            raise typer.Exit(_EXIT_FATAL_INPUTS)
        targets = [rec]

    gate_failed = False
    applied_domains = set()
    disposition_updates: dict = (
        {}
    )  # batched into one staging write (avoid O(N^2) rewrites)
    for rec in targets:
        res = apply_recommendation(project_root, rec, force=force)
        if res.ok:
            disposition_updates[(rec.domain, rec.value_path)] = "approved"
            applied_domains.add(rec.domain)
            decision_event(
                EV_APPROVED,
                domain=rec.domain,
                role_id=rec.role_id,
                value_path=rec.value_path,
            )
            console.print(f"[green]✓ approved[/green] {rec.domain}:{rec.value_path}")
        elif res.code == "round_trip_failed":
            disposition_updates[(rec.domain, rec.value_path)] = "invalid"
            console.print(f"[red]✗ gate rejected[/red] {rec.value_path}: {res.error}")
            gate_failed = True
        else:
            console.print(
                f"[yellow]✗ {res.code}[/yellow] {rec.value_path}: {res.error}"
            )
    store.update_dispositions(
        disposition_updates
    )  # one write for the whole batch (R1-S4)

    # Manual-flip reminder when a domain is fully resolved (R4-S2 / FR-KIR-7 — SDK never auto-flips).
    for dname in sorted(applied_domains):
        if domain_fully_resolved(project_root, dname):
            spec = get_domain(dname)
            console.print(
                f"[dim]all drafts for {dname} approved — to count toward readiness, set "
                f"`provenance_default: authored` in {spec.rel_path()}.[/dim]"
            )
    if gate_failed:
        raise typer.Exit(_EXIT_GATE)


@panel_app.command("reject")
def panel_reject(
    field: str = typer.Option(..., "--field", help="<domain>:<value_path> to reject."),
    session: Optional[str] = typer.Option(
        None, "--session", help="Staging session (default: the only/latest)."
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
) -> None:
    """Mark a staged draft rejected (no write); it drops out of review."""
    from .stakeholder_panel.proposals import ProposalStore
    from .stakeholder_panel.telemetry import EV_REJECTED, decision_event

    sess = _resolve_session(project_root, session)
    domain, value_path = _split_field(field)
    if ProposalStore(project_root, sess).update_disposition(
        domain, value_path, "rejected"
    ):
        decision_event(EV_REJECTED, domain=domain, value_path=value_path)
        console.print(f"[green]panel:[/green] rejected {domain}:{value_path}")
    else:
        console.print(
            f"[red]panel:[/red] no staged draft {domain}:{value_path} in session {sess}."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
