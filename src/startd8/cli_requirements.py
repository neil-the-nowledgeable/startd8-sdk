# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``startd8 requirements`` — the Requirements Panel CLI (FR-RP-8).

The elicit → synthesize → review → approve loop. The `$0` baseline (``elicit`` without ``--roles``),
``synthesize``, and ``review`` spend nothing; ``elicit --roles`` runs the paid persona pass.
``approve`` is readiness-gated, atomic, and one-shot (FR-RP-6). The CLI is the **sole writer** (P4).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List, Optional

import typer

from .cli_shared import console

requirements_app = typer.Typer(
    help="Requirements Panel — persona-driven requirements drafting."
)

_EXIT_FATAL_INPUTS = 2
_EXIT_RUNTIME = 1
_EXIT_BLOCKED = 6  # readiness gate blocked approve
_EXIT_CLOBBER = 5  # refused to regenerate over an existing versioned doc

_ROSTER_REL = Path("docs") / "kickoff" / "inputs" / "stakeholders.yaml"
_SCHEMA_REL = Path("prisma") / "schema.prisma"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _new_session_id() -> str:
    import uuid

    return f"elicit-{uuid.uuid4().hex[:8]}"


def _stage(project_root: Path, session_id: str, candidates) -> None:
    from .requirements_panel.store import CandidateStore

    CandidateStore(project_root, session_id).save(candidates)


def _load_staged(project_root: Path, session_id: Optional[str]):
    from .requirements_panel.store import CandidateStore, latest_session

    sid = session_id or latest_session(project_root)
    if sid is None:
        return None, []
    return sid, CandidateStore(project_root, sid).load()


@requirements_app.command("elicit")
def requirements_elicit(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    roles: bool = typer.Option(
        False, "--roles", help="Run the PAID persona pass on top of the $0 baseline."
    ),
    brief_file: Optional[Path] = typer.Option(
        None, "--brief", help="Path to a problem-statement brief (markdown/text)."
    ),
    cap: Optional[int] = typer.Option(
        None, "--cap", help="Max persona areas to draft (paid)."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Agent spec (paid pass)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the run as JSON."),
) -> None:
    """Elicit candidate requirements: the $0 schema+brief baseline, plus an optional paid role pass."""
    from .requirements_panel import scaffold
    from .requirements_panel.store import CandidateStore

    brief = _read(brief_file) if brief_file else ""
    schema_text = _read(project_root / _SCHEMA_REL)
    session_id = _new_session_id()

    baseline = scaffold(brief, schema_text, session_id=session_id)
    candidates = list(baseline.candidates)

    paid_summary = {}
    if roles:
        try:
            candidates += _run_paid_pass(
                project_root, brief, schema_text, session_id, cap, model, paid_summary
            )
        except _ElicitError as exc:
            console.print(f"[red]requirements:[/red] {exc}")
            raise typer.Exit(exc.code)

    CandidateStore(project_root, session_id).save(candidates)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "session_id": session_id,
                    "baseline_stubs": len(baseline.candidates),
                    "candidates_total": len(candidates),
                    "paid": paid_summary,
                }
            )
        )
        return
    console.print(f"[green]requirements:[/green] session [bold]{session_id}[/bold]")
    console.print(f"  $0 baseline stubs: {len(baseline.candidates)}")
    if roles:
        console.print(
            f"  role-drafted: {paid_summary.get('areas_drafted', 0)} (cost ${paid_summary.get('cost', 0):.4f})"
        )
    console.print(f"  staged: {len(candidates)} candidates")
    console.print(f"  next: startd8 requirements synthesize --session {session_id}")


class _ElicitError(Exception):
    def __init__(self, msg: str, code: int) -> None:
        super().__init__(msg)
        self.code = code


def _run_paid_pass(
    project_root, brief, schema_text, session_id, cap, model, summary
) -> List:
    roster_path = project_root / _ROSTER_REL
    if not roster_path.is_file():
        raise _ElicitError(
            f"no roster at {roster_path} — run `startd8 concierge instantiate-kickoff` first",
            _EXIT_FATAL_INPUTS,
        )
    from .stakeholder_panel import RosterError, load_roster, validate_roster
    from .stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel
    from .requirements_panel import elicit_requirements

    try:
        roster = load_roster(roster_path)
    except RosterError as exc:
        raise _ElicitError(str(exc), _EXIT_FATAL_INPUTS)
    if validate_roster(roster):
        raise _ElicitError(
            "roster is invalid (run `startd8 panel` to inspect)", _EXIT_FATAL_INPUTS
        )

    panel = StakeholderPanel(
        roster, project_root=project_root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        run = asyncio.run(
            elicit_requirements(
                project_root,
                panel,
                brief=brief,
                schema_text=schema_text,
                cap=cap,
                session_id=session_id,
            )
        )
    except Exception as exc:  # provider/auth/budget failure — clean message
        raise _ElicitError(f"paid pass failed: {exc}", _EXIT_RUNTIME)
    finally:
        panel.close()
    summary["areas_drafted"] = run.areas_drafted
    summary["cost"] = run.total_cost_usd
    summary["skipped"] = run.skipped
    return run.candidates


@requirements_app.command("synthesize")
def requirements_synthesize(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    session: Optional[str] = typer.Option(
        None, "--session", help="Elicitation session id."
    ),
    brief_file: Optional[Path] = typer.Option(
        None, "--brief", help="Problem-statement brief."
    ),
) -> None:
    """Assemble the staged candidates into one coherent doc ($0, deterministic)."""
    from .requirements_panel import RequirementDoc, synthesize

    sid, candidates = _load_staged(project_root, session)
    if sid is None or not candidates:
        console.print(
            "[red]requirements:[/red] no staged candidates — run `elicit` first."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    brief = _read(brief_file) if brief_file else ""
    empty = RequirementDoc(title="Requirements (draft)", problem=brief)
    doc = synthesize(empty, candidates)
    console.print(
        f"[green]requirements:[/green] synthesized {len(doc.candidates)} FRs from session {sid}"
    )
    if doc.open_questions:
        console.print(f"  open questions (incl. conflicts): {len(doc.open_questions)}")
    console.print(f"  next: startd8 requirements review --session {sid}")


@requirements_app.command("review")
def requirements_review(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    session: Optional[str] = typer.Option(
        None, "--session", help="Elicitation session id."
    ),
    brief_file: Optional[Path] = typer.Option(
        None, "--brief", help="Problem-statement brief."
    ),
) -> None:
    """Render the LITERAL doc bytes that approve would write; surface grounding flags out-of-band."""
    from .requirements_panel import RequirementDoc, check_readiness, synthesize

    sid, candidates = _load_staged(project_root, session)
    if sid is None or not candidates:
        console.print(
            "[red]requirements:[/red] no staged candidates — run `elicit` first."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    brief = _read(brief_file) if brief_file else ""
    doc = synthesize(
        RequirementDoc(title="Requirements (draft)", problem=brief), candidates
    )

    # The literal bytes (FR-RP-8) — printed verbatim, no summary.
    console.print(doc.render(), markup=False, highlight=False)

    # Advisory grounding flags + provenance surfaced OUT-OF-BAND (R2-F4) — never inside the bytes.
    flagged = [(c.fr_id, c.flags) for c in doc.candidates if c.flags]
    console.print("\n[dim]— out-of-band (not part of the doc) —[/dim]")
    console.print(f"provenance: {json.dumps(doc.provenance_manifest())}", markup=False)
    if flagged:
        console.print("grounding flags:", markup=False)
        for fid, flags in flagged:
            console.print(f"  {fid}: {'; '.join(flags)}", markup=False)
    readiness = check_readiness(doc)
    if readiness.ok:
        console.print("[green]readiness: OK[/green] — approve may proceed")
    else:
        console.print("[yellow]readiness: BLOCKED[/yellow]")
        for b in readiness.blockers:
            console.print(f"  - {b}", markup=False)


@requirements_app.command("approve")
def requirements_approve(
    out: Path = typer.Argument(
        ..., help="Target path, e.g. docs/design/<f>/<F>_REQUIREMENTS.md"
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    session: Optional[str] = typer.Option(
        None, "--session", help="Elicitation session id."
    ),
    brief_file: Optional[Path] = typer.Option(
        None, "--brief", help="Problem-statement brief."
    ),
) -> None:
    """Readiness-gate, then atomically write v0.1 (one-shot; never regenerates over an existing doc)."""
    from .requirements_panel import RequirementDoc, apply_requirements, synthesize

    sid, candidates = _load_staged(project_root, session)
    if sid is None or not candidates:
        console.print(
            "[red]requirements:[/red] no staged candidates — run `elicit` first."
        )
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    brief = _read(brief_file) if brief_file else ""
    doc = synthesize(
        RequirementDoc(title="Requirements (draft)", problem=brief), candidates
    )

    result = apply_requirements(doc, out)
    if result.written:
        console.print(f"[green]requirements:[/green] wrote {result.path}")
        console.print(f"  next (external second gate): {result.crp_handoff}")
        return
    if result.blockers:
        console.print("[red]requirements:[/red] readiness gate blocked approve:")
        for b in result.blockers:
            console.print(f"  - {b}", markup=False)
        raise typer.Exit(_EXIT_BLOCKED)
    console.print(f"[red]requirements:[/red] {result.reason}")
    raise typer.Exit(_EXIT_CLOBBER)
