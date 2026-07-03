# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``startd8 screens`` — the Manifest Suggester CLI (FR-MS-7).

The suggest → review → approve loop for composite screens. ``suggest`` (without ``--roles``) and
``review`` spend nothing; ``suggest --roles`` runs the paid persona pass. ``approve`` applies each
screen through the existing ``manifest`` proposal kind, accumulating into a running authoring doc so a
second screen never clobbers the first (FR-MS-5/7, R2-S1). The CLI is the sole writer (propose-confirm
floor). It reuses the requirements-elicitation roster (``docs/kickoff/inputs/stakeholders.yaml``).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List, Optional

import typer

from .cli_shared import console

screens_app = typer.Typer(
    help="Manifest Suggester — persona-driven screen (pages/views) suggestion."
)

_EXIT_FATAL_INPUTS = 2
_EXIT_RUNTIME = 1
_EXIT_CLOBBER = 5

_ROSTER_REL = Path("docs") / "kickoff" / "inputs" / "stakeholders.yaml"
_SCHEMA_REL = Path("prisma") / "schema.prisma"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _new_session_id() -> str:
    import uuid

    return f"suggest-{uuid.uuid4().hex[:8]}"


def _load_staged(project_root: Path, session: Optional[str]):
    from .manifest_suggester.store import ScreenCandidateStore, latest_session

    sid = session or latest_session(project_root)
    if sid is None:
        return None, []
    return sid, ScreenCandidateStore(project_root, sid).load()


class _SuggestError(Exception):
    def __init__(self, msg: str, code: int) -> None:
        super().__init__(msg)
        self.code = code


@screens_app.command("suggest")
def screens_suggest(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    roles: bool = typer.Option(
        False, "--roles", help="Run the PAID persona pass on top of the $0 baseline."
    ),
    cap: Optional[int] = typer.Option(
        None, "--cap", help="Max role-drafted screens (paid)."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Agent spec (paid pass)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the run as JSON."),
) -> None:
    """Suggest composite screens: the $0 schema-grounded baseline + an optional paid role pass."""
    from .manifest_suggester import baseline_views
    from .manifest_suggester.apply import all_existing_slugs
    from .manifest_suggester.store import ScreenCandidateStore, dedupe_missing

    schema_text = _read(project_root / _SCHEMA_REL)
    session_id = _new_session_id()

    candidates = list(baseline_views(schema_text, session_id=session_id))
    paid = {}
    if roles:
        try:
            candidates += _run_paid_pass(
                project_root, schema_text, session_id, cap, model, paid
            )
        except _SuggestError as exc:
            console.print(f"[red]screens:[/red] {exc}")
            raise typer.Exit(exc.code)

    # FR-MS-3: only suggest what is missing (dedupe against the running doc + live views/pages manifests).
    fresh = dedupe_missing(candidates, all_existing_slugs(project_root))
    ScreenCandidateStore(project_root, session_id).save(fresh)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "session_id": session_id,
                    "proposed": len(candidates),
                    "staged_after_dedupe": len(fresh),
                    "paid": paid,
                }
            )
        )
        return
    console.print(f"[green]screens:[/green] session [bold]{session_id}[/bold]")
    console.print(
        f"  $0 baseline + role: proposed {len(candidates)}, staged {len(fresh)} after dedupe"
    )
    if roles:
        console.print(
            f"  role-drafted: {paid.get('drafted', 0)} (cost ${paid.get('cost', 0):.4f})"
        )
    console.print(f"  next: startd8 screens review --session {session_id}")


def _run_paid_pass(project_root, schema_text, session_id, cap, model, summary) -> List:
    roster_path = project_root / _ROSTER_REL
    if not roster_path.is_file():
        raise _SuggestError(
            f"no roster at {roster_path} — run `startd8 requirements init-roster` to write a default",
            _EXIT_FATAL_INPUTS,
        )
    from .stakeholder_panel import RosterError, load_roster, validate_roster
    from .stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel

    from .manifest_suggester import suggest_screens

    try:
        roster = load_roster(roster_path)
    except RosterError as exc:
        raise _SuggestError(str(exc), _EXIT_FATAL_INPUTS)
    if validate_roster(roster):
        raise _SuggestError(
            "roster is invalid (run `startd8 panel` to inspect)", _EXIT_FATAL_INPUTS
        )

    panel = StakeholderPanel(
        roster, project_root=project_root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        run = asyncio.run(
            suggest_screens(
                project_root,
                panel,
                schema_text=schema_text,
                cap=cap,
                session_id=session_id,
            )
        )
    except Exception as exc:  # provider/auth/budget failure — clean message
        raise _SuggestError(f"paid pass failed: {exc}", _EXIT_RUNTIME)
    finally:
        panel.close()
    summary["drafted"] = len(run.candidates)
    summary["cost"] = run.total_cost_usd
    summary["skipped"] = run.skipped
    return run.candidates


@screens_app.command("review")
def screens_review(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    session: Optional[str] = typer.Option(
        None, "--session", help="Suggestion session id."
    ),
) -> None:
    """Render the literal authoring prose of each staged screen; grounding flags out-of-band."""
    from .manifest_suggester import PROV_BASELINE

    sid, candidates = _load_staged(project_root, session)
    if sid is None or not candidates:
        console.print("[red]screens:[/red] no staged screens — run `suggest` first.")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    for c in candidates:
        tag = "$0 baseline" if c.provenance == PROV_BASELINE else f"role:{c.role_id}"
        console.print(f"[bold]{c.name}[/bold] ({c.kind}, {tag})", markup=False)
        console.print(c.prose, markup=False, highlight=False)

    flagged = [(c.name, c.flags) for c in candidates if c.flags]
    console.print("\n[dim]— out-of-band (not part of the manifest) —[/dim]")
    if flagged:
        console.print("grounding flags:", markup=False)
        for name, flags in flagged:
            console.print(f"  {name}: {'; '.join(flags)}", markup=False)
    else:
        console.print("grounding: all staged screens resolve cleanly", markup=False)
    console.print(
        f"  next: startd8 screens approve --session {sid} --all", markup=False
    )


@screens_app.command("approve")
def screens_approve(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    session: Optional[str] = typer.Option(
        None, "--session", help="Suggestion session id."
    ),
    name: Optional[str] = typer.Option(
        None, "--name", help="Approve one screen by name/slug."
    ),
    approve_all: bool = typer.Option(
        False, "--all", help="Approve every staged screen."
    ),
) -> None:
    """Apply approved screen(s) via the manifest proposal kind (accumulation-aware, FR-MS-5/7)."""
    from .manifest_suggester.apply import apply_screen
    from .manifest_suggester.models import ScreenCandidate  # noqa: F401 (type clarity)
    from startd8.manifest_extraction.grammar import nfkd_kebab

    sid, candidates = _load_staged(project_root, session)
    if sid is None or not candidates:
        console.print("[red]screens:[/red] no staged screens — run `suggest` first.")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if not approve_all and name is None:
        console.print("[red]screens:[/red] pass --name <screen> or --all.")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    targets = (
        candidates
        if approve_all
        else [c for c in candidates if c.slug == nfkd_kebab(name)]
    )
    if not targets:
        console.print(f"[red]screens:[/red] no staged screen matches {name!r}.")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    applied = 0
    for c in targets:
        result = apply_screen(project_root, c)
        if result.applied:
            applied += 1
            console.print(f"[green]screens:[/green] applied {c.name}")
        elif result.code == "duplicate":
            console.print(f"[dim]screens: {c.name} already applied[/dim]", markup=False)
        else:
            console.print(
                f"[red]screens:[/red] {c.name}: {result.reason}", markup=False
            )
            if result.code == "would_clobber":
                raise typer.Exit(_EXIT_CLOBBER)
    console.print(
        f"  {applied}/{len(targets)} applied → prisma/views.yaml (via the manifest proposal)"
    )


@screens_app.command("reject")
def screens_reject(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    session: Optional[str] = typer.Option(
        None, "--session", help="Suggestion session id."
    ),
    name: str = typer.Option(
        ..., "--name", help="Reject (drop) one staged screen by name/slug."
    ),
) -> None:
    """Drop a staged screen so it is never proposed for approval (FR-MS-7). Writes nothing to the app."""
    from startd8.manifest_extraction.grammar import nfkd_kebab

    from .manifest_suggester.store import ScreenCandidateStore

    sid, candidates = _load_staged(project_root, session)
    if sid is None or not candidates:
        console.print("[red]screens:[/red] no staged screens — run `suggest` first.")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    slug = nfkd_kebab(name)
    kept = [c for c in candidates if c.slug != slug]
    if len(kept) == len(candidates):
        console.print(f"[red]screens:[/red] no staged screen matches {name!r}.")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    ScreenCandidateStore(project_root, sid).save(kept)
    console.print(
        f"[green]screens:[/green] rejected {name} ({len(candidates) - len(kept)} dropped, "
        f"{len(kept)} remain in session {sid})"
    )
