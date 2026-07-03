# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``startd8 requirements`` — the Requirements Panel CLI (FR-RP-8).

The elicit → synthesize → review → approve loop. The `$0` baseline (``elicit`` without ``--roles``),
``synthesize``, and ``review`` spend nothing; ``elicit --roles`` runs the paid persona pass.
``approve`` is readiness-gated, atomic, and one-shot (FR-RP-6). The CLI is the **sole writer** (P4).
"""

from __future__ import annotations

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


@requirements_app.command("init-roster")
def requirements_init_roster(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing roster."),
) -> None:
    """Write the default requirements-elicitation roster (FR-RP-10) so `elicit --roles` works."""
    from .requirements_panel import install_default_roster

    result = install_default_roster(project_root, force=force)
    if result.written:
        console.print(
            f"[green]requirements:[/green] wrote default roster {result.path}"
        )
        console.print("  edit the persona goals/constraints to your project, then:")
        console.print("  startd8 requirements elicit --roles")
        return
    console.print(f"[yellow]requirements:[/yellow] {result.reason}")
    raise typer.Exit(_EXIT_CLOBBER)


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
    target: Optional[Path] = typer.Option(
        None,
        "--target",
        help="The eventual approve target; if it already exists, refuse BEFORE any paid spend (FR-RP-6).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the run as JSON."),
) -> None:
    """Elicit candidate requirements: the $0 schema+brief baseline, plus an optional paid role pass."""
    from .requirements_panel import scaffold
    from .requirements_panel.store import CandidateStore

    # FR-RP-6 lifecycle (R2-S4), elicit half: once a versioned doc exists it is never regenerated over —
    # short-circuit here, BEFORE the paid pass, so `--roles` never spends against a doc approve will
    # refuse anyway. (Without --target the guarantee is still enforced at approve via O_EXCL.)
    if target is not None and Path(target).expanduser().exists():
        console.print(
            f"[yellow]requirements:[/yellow] {target} already exists — a versioned requirements doc "
            "is never regenerated over (edit it in place / take it through CRP). No spend."
        )
        raise typer.Exit(_EXIT_CLOBBER)

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
    CandidateStore.gc(project_root)  # FR-KO-2: bound leaked sessions to the keep-limit

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
    from .persona_drafting import PaidPassError, run_paid_pass
    from .requirements_panel import elicit_requirements

    async def _pass(panel):
        return await elicit_requirements(
            project_root,
            panel,
            brief=brief,
            schema_text=schema_text,
            cap=cap,
            session_id=session_id,
        )

    try:
        run = run_paid_pass(
            project_root, roster_rel=_ROSTER_REL, run=_pass, model=model
        )
    except PaidPassError as exc:
        code = _EXIT_RUNTIME if exc.kind == "failed" else _EXIT_FATAL_INPUTS
        raise _ElicitError(str(exc), code)
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
    as_json: bool = typer.Option(False, "--json", help="Emit the result as JSON."),
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
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "session_id": sid,
                    "frs": len(doc.candidates),
                    "open_questions": len(doc.open_questions),
                }
            )
        )
        return
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
    as_json: bool = typer.Option(
        False, "--json", help="Emit the doc + flags + readiness as JSON."
    ),
) -> None:
    """Render the LITERAL doc bytes that approve would write; surface grounding flags out-of-band."""
    from .requirements_panel import (
        RequirementDoc,
        check_readiness,
        coverage_report,
        synthesize,
    )

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

    if as_json:
        readiness = check_readiness(doc)
        console.print_json(
            json.dumps(
                {
                    "session_id": sid,
                    "doc": doc.render(),
                    "provenance": doc.provenance_manifest(),
                    "grounding_flags": {
                        c.fr_id: c.flags for c in doc.candidates if c.flags
                    },
                    "readiness_ok": readiness.ok,
                    "readiness_blockers": readiness.blockers,
                }
            )
        )
        return

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
    # Advisory coverage / "how done am I?" score (FR-RP-11) — never a gate.
    console.print("\n[dim]— coverage (advisory) —[/dim]")
    console.print(coverage_report(doc).render(), markup=False)

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
    as_json: bool = typer.Option(
        False, "--json", help="Emit the apply result as JSON."
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
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "written": result.written,
                    "path": str(result.path) if result.path else None,
                    "blockers": result.blockers,
                    "reason": result.reason,
                    "crp_handoff": result.crp_handoff if result.written else "",
                }
            )
        )
        if result.written:
            return
        raise typer.Exit(_EXIT_BLOCKED if result.blockers else _EXIT_CLOBBER)
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
