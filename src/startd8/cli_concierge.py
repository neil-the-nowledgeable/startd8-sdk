# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""concierge CLI command group — project-side SDK-onboarding assist.

Human-facing front door over the same SDK code path the `startd8_concierge` MCP tool uses
(FR-C13: one logic, two front doors). Read actions (`survey`, `assess`) are $0/read-only; write
actions (`instantiate-kickoff`, `log-friction`) write **only here** — the CLI is the sole writer
(OQ-7), running at the human's own privilege, preview-by-default, `--apply` to write.
Exit codes: 0 advisory; 2 unreadable/invalid input (FR-W9); 3 a write was blocked by a
confinement/clobber guard; 1 `--check` drift detected.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console as _Console

from .cli_shared import console, render_intro_banner

# Deprecation notices go to stderr so they never pollute the `--json` stdout contract.
_stderr_console = _Console(stderr=True)

# The kernel surface: `startd8 kickoff` (M0b). The same command bodies are registered here under
# the kernel names and, for one release, under the old `startd8 concierge` names as hidden aliases
# (M0b alias window, FR-10). `concierge_app` below is that deprecated alias group.
concierge_app = typer.Typer(
    name="concierge",
    help="[DEPRECATED — use `startd8 kickoff`] Onboarding assist alias (works for one release).",
)

kickoff_kernel_app = typer.Typer(
    name="kickoff",
    help="Onboarding kernel: survey/assess a project (read-only) and instantiate/derive/log-friction.",
)

_EXIT_FATAL_INPUTS = 2
_EXIT_BLOCKED = 3
_EXIT_DRIFT = 1


def _render_markdown(text: str) -> None:
    """Print instructional markdown — pretty on a TTY, plain text when piped/non-interactive."""
    if console.is_terminal:
        from rich.markdown import Markdown

        console.print(Markdown(text))
    else:
        console.print(text, markup=False, highlight=False)


# FR-2 / clause A: bare `startd8 kickoff` (no subcommand) must ORIENT, not error. Today the group
# exits 2 ("Missing command"); this callback flips it to a $0 intro + the subcommand list (exit 0).
# `--json` is a per-subcommand option, so this bare-group path never sees it. Scope: the top
# `kickoff` group only (OQ-9); `kickoff panel` keeps its current behavior.
@kickoff_kernel_app.callback(invoke_without_command=True)
def _kickoff_root(ctx: typer.Context) -> None:
    """Onboarding kernel — run a subcommand, or see the intro below."""
    if ctx.invoked_subcommand is not None:
        return
    # FR-UX-16 (CRP R2-S4) — the same shared banner every subcommand uses, then the command list.
    from .cli_shared import render_intro_banner

    render_intro_banner()
    console.print(ctx.get_help())


@concierge_app.callback()
def _concierge_deprecated() -> None:
    """[DEPRECATED] Renamed to `startd8 kickoff`. This alias works for one release (FR-10)."""
    warnings.warn(
        "`startd8 concierge` is deprecated; use `startd8 kickoff` "
        "(instantiate-kickoff→instantiate, derive-contract→derive). "
        "This alias will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    _stderr_console.print(
        "[yellow]deprecation:[/yellow] `startd8 concierge` is renamed to `startd8 kickoff` "
        "(instantiate-kickoff→instantiate, derive-contract→derive); this alias works for one release."
    )


def _emit_json(result: dict) -> None:
    import sys

    sys.stdout.write(json.dumps(result, indent=2) + "\n")


@concierge_app.command("survey")
def concierge_survey(
    project_root: Path = typer.Argument(
        Path("."), help="Project to triage (default: current dir). Read-only — never modified."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the schema-versioned JSON to stdout."),
) -> None:
    """Brownfield triage: requirement docs (+ extraction-format match), models, fixtures, PII flags."""
    from .concierge import ConciergeError, handle_concierge_tool

    # FR-UX-16 — the shared banner leads the human view (never before a --json payload).
    if not json_out:
        render_intro_banner()

    try:
        result = handle_concierge_tool("survey", project_root)
    except ConciergeError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if json_out:
        _emit_json(result)
        return

    console.print(f"[bold]Concierge survey[/bold] — {result['project_root']}")

    docs = result["requirement_docs"]
    if docs:
        console.print(f"\n[bold]Requirement docs[/bold] ({len(docs)}):")
        for d in docs:
            tag = "[green]extraction-format[/green]" if d["extraction_format"] else "[yellow]needs reformat (F-4)[/yellow]"
            console.print(f"  • {d['path']}  {tag}")
    else:
        console.print("\n[dim]No requirement/PRD/PLAN docs found.[/dim]")

    models = result["model_files"]
    console.print(f"\n[bold]Pydantic model files[/bold]: {len(models)}")
    for m in models[:10]:
        console.print(f"  • {m}")

    fixtures = result["fixture_candidates"]
    console.print(f"\n[bold]Test-fixture candidates[/bold]: {len(fixtures)}")
    for f in fixtures[:10]:
        console.print(f"  • {f}")

    pii = result["pii_risk_flags"]
    if pii:
        console.print(f"\n[bold red]Personal/PII risk flags[/bold red] ({len(pii)}) — review before any carve/commit:")
        for p in pii:
            console.print(f"  [red]⚠[/red] {p}")
    else:
        console.print("\n[green]No personal/PII-material flagged[/green] (name/extension heuristic).")


def _render_assess(result: dict) -> None:
    """Render the readiness surface (the Orient view). Extracted so the guided experience's
    Orient phase reuses THIS exact projection — no second readiness render (FR-GE-6)."""
    console.print(f"[bold]Concierge assess[/bold] — {result['project_root']}")

    console.print("\n[bold]Kickoff inputs[/bold] (provenance, honest — not graded):")
    for domain, info in result["kickoff_inputs"]["domains"].items():
        status = info.get("status")
        if status == "present":
            conf = info.get("confirmation") or {}
            tail = ""
            if conf.get("confirmable"):
                tail = (f"  ·  {conf.get('confirmed', 0)} of {conf['confirmable']} confirmed · "
                        f"{conf.get('awaiting', 0)} awaiting")
                # M2 (A-FR13): audience-defaulted fields — machine defaults the user can still ratify
                # via `kickoff confirm`. Surfaced only when present (omitted ⇒ no display change).
                if conf.get("audience_defaulted"):
                    tail += f" · [cyan]{conf['audience_defaulted']} audience-default[/cyan]"
                if conf.get("stale"):
                    tail += f" · [yellow]{conf['stale']} stale[/yellow]"
            console.print(f"  • {domain}: [green]present[/green] — provenance: "
                          f"{info.get('provenance_default')}{tail}")
        elif status == "absent":
            console.print(f"  • {domain}: [yellow]absent[/yellow]")
        else:
            console.print(f"  • {domain}: [red]{status}[/red] {info.get('error', '')}")

    cascade = result["cascade"]
    console.print("\n[bold]$0 cascade[/bold]:")
    if cascade.get("status") != "ok":
        console.print(f"  [red]{cascade.get('status')}[/red]: {cascade.get('error', '')}")
    else:
        shape = cascade["shape"]
        console.print(
            f"  shape: {shape['entities']} entities · {shape['crud_routes']} CRUD routes · "
            f"{shape['pages']} pages · {shape['views']} views · {shape['ai_passes']} AI passes"
        )
        for gen, state in cascade["readiness"].items():
            color = "green" if state == "ready" else "yellow"
            console.print(f"  {gen}: [{color}]{state}[/{color}]")

        # Wireframe↔kickoff merge (FR-B2/B3, FR-C1..3): surface "what will be built" inline — the exact
        # file count, the softer (defaults/placeholder) consequences the blocker list drops, content
        # coverage, and merge warnings — so the plan is visible without a separate `startd8 wireframe`.
        paths = cascade.get("claimed_paths") or []
        sections = cascade.get("sections") or []
        if paths:
            planned = [s for s in sections if s.get("status") == "planned"]
            console.print(
                f"\n[bold]Will build[/bold]: {len(paths)} files across "
                f"{len(planned)} planned section(s)."
            )
            for s in sections:  # FR-B1: the non-blocker consequences the projection used to drop
                if s.get("status") in ("defaults", "placeholder") and s.get("consequence"):
                    console.print(f"  • {s['title']} ([dim]{s['status']}[/dim]): {s['consequence']}")
            cov = (cascade.get("content_coverage") or {}).get("overall") or {}
            if cov.get("total"):
                console.print(f"  content authored: {cov['authored']}/{cov['total']} prose surface(s)")
            for w in cascade.get("merge_warnings") or []:
                console.print(f"  [yellow]⚠ merge:[/yellow] {w.get('message') or w.get('key') or w}")
            console.print("  [dim]full file-by-file plan →[/dim] [cyan]startd8 wireframe[/cyan]")

        # Blocker reframe (FR-3): HARD blockers (must fix) and OPTIONAL next steps are two honestly-
        # different tiers — an un-authored `pages`/`content` is NOT "blocking" a build.
        hard = cascade.get("hard_blockers") or []
        if hard:
            console.print("\n[bold red]Blocking[/bold red] (invalid manifest — fix to build):")
            for b in hard:
                console.print(f"  • {b['section']} ([red]{b['status']}[/red]): {b['consequence']}")
                if b.get("next_command"):
                    console.print(f"      → fix: [cyan]{b['next_command']}[/cyan]")
        blocked_gen = cascade.get("blocked_generators") or {}
        if cascade.get("buildable"):
            console.print("\n[green]Ready to build[/green] — the $0 cascade can generate now.")
        elif blocked_gen:
            console.print("\n[bold]Not yet buildable[/bold] — resolve the root, then everything downstream follows:")
            for gen, reason in blocked_gen.items():
                console.print(f"  • {gen}: [yellow]{reason}[/yellow]")
        optional = cascade.get("optional_next_steps") or []
        if optional:
            console.print("\n[bold]Optional next steps[/bold] (enrichments — the app builds without them):")
            for b in optional:
                console.print(f"  • {b['section']} ([dim]{b['status']}[/dim]): {b['consequence']}")
                if b.get("next_command"):
                    console.print(f"      → [cyan]{b['next_command']}[/cyan]")

    # FR-5: the handoff surface — the single exact next command to move forward.
    headline = result.get("next_command")
    if headline:
        console.print(f"\n[bold]Next command[/bold]: [cyan]{headline}[/cyan]")

    # Thread B / FR-B2: advisory cap-dev-pipe offer — rendered in a distinctly non-blocking
    # voice, AFTER the blocking headline, so it never reads as a required step. Only shown when
    # there is something to offer (absent+ready, or a broken existing embed); healthy = silent.
    capdevpipe = result.get("capdevpipe") or {}
    offer = capdevpipe.get("next_command")
    if offer:
        if capdevpipe.get("status") == "present_no_manifest":
            reason = "a cap-dev-pipe embed is present but incomplete"
        else:
            reason = "the project is ready — you can install the capability-delivery pipeline"
        console.print(f"\n[dim]Optional next step[/dim] ({reason}): [cyan]{offer}[/cyan]")


@concierge_app.command("assess")
def concierge_assess(
    project_root: Path = typer.Argument(
        Path("."), help="Project to assess (default: current dir). Read-only."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the schema-versioned JSON to stdout."),
    guided: Optional[bool] = typer.Option(
        None, "--guided/--no-guided",
        help="Offer (or silence) the guided kickoff experience. Overrides the project/global preference.",
    ),
) -> None:
    """Onboarding-readiness report: kickoff-input provenance + the $0-cascade view (wraps wireframe)."""
    from .concierge import ConciergeError, handle_concierge_tool

    # FR-UX-16 — the shared banner leads the human view (never before a --json payload).
    if not json_out:
        render_intro_banner()

    try:
        result = handle_concierge_tool("assess", project_root)
    except ConciergeError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if json_out:
        _emit_json(result)
        return

    _render_assess(result)

    # GE-M0/M1 (FR-GE-1/3): the guided-experience routing seam. One ignorable line on *stderr*, never a
    # gate, $0/no-LLM. Suppressed on `--json` (already returned above) and on a non-interactive stdout
    # so the kernel path stays byte-identical. GE-M1 wires the real tri-state `--guided/--no-guided`.
    _maybe_offer_guided(project_root, assess=result, flag=guided)


def _maybe_offer_guided(project_root: Path, *, assess: dict, flag: Optional[bool] = None) -> None:
    """Emit the single ignorable guided-experience offer line on stderr, if routing says so (GE-M0).

    Read-only, $0, defensive: any failure here must never perturb the kernel `assess` output.
    """
    try:
        from .kickoff_experience.guided_routing import decide_guided_routing, offer_line

        decision = decide_guided_routing(
            project_root,
            flag=flag,               # GE-M1: the real tri-state --guided/--no-guided (None ⇒ fall through)
            served_surface=False,    # a CLI invocation is not a served/TUI surface
            assess=assess,           # project-shape signal (reuse the payload we already computed)
            interactive=console.is_terminal,  # non-TTY (piped/CI) ⇒ suppressed, never blocking
        )
        line = offer_line(decision)
        if line:
            _stderr_console.print(line)
    except Exception:
        # The offer is a courtesy; never let it break or alter the kernel path.
        return


def _render_write_result(res) -> None:
    for p in res.written:
        console.print(f"  [green]wrote[/green]    {p}")
    for s in res.skipped:
        console.print(f"  [yellow]skipped[/yellow]  {s['path']} — {s['reason']}")
    for b in res.blocked:
        console.print(f"  [red]BLOCKED[/red]  {b['path']} — {b['reason']}")
    for e in res.errors:
        console.print(f"  [red]error[/red]    {e['path']} — {e['error']}")


@concierge_app.command("instantiate-kickoff")
def concierge_instantiate(
    project_root: Path = typer.Argument(Path("."), help="Target project (default: current dir)."),
    posture: str = typer.Option("prototype", "--posture", help="prototype | production"),
    with_authoring: bool = typer.Option(False, "--with-authoring", help="Also project the REQUIREMENTS/PLAN/TEST_USERS authoring trio."),
    apply: bool = typer.Option(False, "--apply", help="Write the files (default: preview only)."),
    force: bool = typer.Option(False, "--force", help="With --apply: overwrite files that diverged from the template."),
    check: bool = typer.Option(False, "--check", help="Report drift (matches/diverged/absent) + verdict; non-zero exit on drift."),
    json_out: bool = typer.Option(False, "--json", help="Emit schema-versioned JSON."),
) -> None:
    """Project the kickoff package into a project (FR-C7). Preview by default; --apply to write."""
    # FR-UX-16 — banner leads the human view; suppressed for --json and the --check CI signal.
    if not json_out and not check:
        render_intro_banner()
    from .concierge.safe_write import SafeWriteError, apply_write_plan
    from .concierge.writes import (
        ConciergeWriteError,
        build_instantiate_plan,
        compute_drift,
        to_planned_writes,
    )

    try:
        plan = build_instantiate_plan(project_root, posture, with_authoring=with_authoring)
    except ConciergeWriteError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if check:
        drift = compute_drift(plan, project_root)
        if json_out:
            _emit_json(drift)
        else:
            color = {"complete": "green", "partial": "yellow", "drifted": "red"}[drift["verdict"]]
            console.print(f"[bold]instantiate-kickoff --check[/bold] — verdict: [{color}]{drift['verdict']}[/{color}]")
            for f in drift["files"]:
                console.print(f"  {f['state']:<9} {f['path']}")
        raise typer.Exit(0 if drift["verdict"] == "complete" else _EXIT_DRIFT)

    if not apply:
        if json_out:
            _emit_json(plan)
        else:
            console.print(f"[bold]instantiate-kickoff[/bold] (preview, posture={plan['posture']}) — {plan['project_root']}")
            for w in plan["writes"]:
                console.print(f"  [{('green' if w['status']=='new' else 'yellow')}]{w['status']:<7}[/] {w['path']} ({w['bytes']} B)")
            for warn in plan["warnings"]:
                console.print(f"  [yellow]⚠[/yellow] {warn}")
            console.print("\n  [dim]preview only — re-run with --apply to write[/dim]")
        return

    try:
        res = apply_write_plan(project_root, to_planned_writes(plan), force=force)
    except SafeWriteError as exc:
        console.print(f"[red]concierge: blocked — {exc}[/red]")
        raise typer.Exit(_EXIT_BLOCKED)
    console.print(f"[bold]instantiate-kickoff[/bold] — {plan['project_root']}")
    _render_write_result(res)
    if not res.ok:
        raise typer.Exit(_EXIT_BLOCKED)


@concierge_app.command("log-friction")
def concierge_log_friction(
    project_root: Path = typer.Argument(Path("."), help="Project whose friction log to append (default: current dir)."),
    friction: str = typer.Option(..., "--friction", help="The friction encountered."),
    what_happened: str = typer.Option(..., "--what-happened", help="What happened."),
    implication: str = typer.Option(..., "--implication", help="Implication for the SDK / role."),
    apply: bool = typer.Option(False, "--apply", help="Append the entry (default: preview only)."),
    json_out: bool = typer.Option(False, "--json", help="Emit schema-versioned JSON."),
) -> None:
    """Append a structured friction entry to concierge-friction.jsonl (FR-C9)."""
    # FR-UX-16 — banner leads the human view (never before a --json payload).
    if not json_out:
        render_intro_banner()
    from datetime import datetime, timezone

    from .concierge.safe_write import SafeWriteError, apply_write_plan
    from .concierge.writes import ConciergeWriteError, build_friction_entry, to_planned_writes

    try:
        plan = build_friction_entry(
            project_root,
            friction=friction,
            what_happened=what_happened,
            implication=implication,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except ConciergeWriteError as exc:
        console.print(f"[red]concierge:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if not apply:
        if json_out:
            _emit_json(plan)
        else:
            w = plan["writes"][0]
            verb = "create" if w["status"] == "new" else "append to"
            console.print(f"[bold]log-friction[/bold] (preview) — would {verb} {w['path']}")
            console.print(f"  {w['append_text'].rstrip()}")
            console.print("\n  [dim]preview only — re-run with --apply to write[/dim]")
        return

    try:
        res = apply_write_plan(project_root, to_planned_writes(plan))
    except SafeWriteError as exc:
        console.print(f"[red]concierge: blocked — {exc}[/red]")
        raise typer.Exit(_EXIT_BLOCKED)
    _render_write_result(res)
    if not res.ok:
        raise typer.Exit(_EXIT_BLOCKED)


@concierge_app.command("derive-contract")
def concierge_derive_contract(
    project_root: Path = typer.Argument(Path("."), help="Project root (default: current dir)."),
    models: List[str] = typer.Option(..., "--models", help="Pydantic model module import path(s) (repeatable)."),
    pythonpath: Optional[Path] = typer.Option(None, "--pythonpath", help="Where to import the models from (default: project root)."),
    model_names: Optional[List[str]] = typer.Option(None, "--model-name", help="Restrict to these class names (repeatable)."),
    exclude: Optional[List[str]] = typer.Option(None, "--exclude", help="Exclude these models, FQ or bare class name (repeatable)."),
    out: Path = typer.Option(Path("prisma/schema.prisma"), "--out", help="Contract path (relative to project root) for --apply."),
    check: bool = typer.Option(False, "--check", help="Report drift vs the live contract; non-zero exit on drift (FR-DC-11)."),
    apply: bool = typer.Option(False, "--apply", help="Write the candidate contract (default: preview only)."),
    force: bool = typer.Option(False, "--force", help="With --apply: overwrite an existing contract."),
    json_out: bool = typer.Option(False, "--json", help="Emit schema-versioned JSON."),
) -> None:
    """Derive a candidate schema.prisma from a project's Pydantic models (FR-DC-1..14).

    Preview by default; --check reports drift; --apply writes the candidate (CLI is the sole
    writer, OQ-7). The emitted contract is marked `unratified` — the Architect ratifies (FR-DC-7c).
    """
    from .concierge.derive import DeriveImportError, build_derivation, check_drift
    from .concierge.safe_write import ACTION_NEW, ACTION_OVERWRITE, PlannedWrite, SafeWriteError, apply_write_plan

    # FR-UX-16 — banner leads the human view; suppressed for --json and the --check CI signal.
    if not json_out and not check:
        render_intro_banner()

    ppath = str(pythonpath) if pythonpath else str(project_root)
    try:
        if check:
            live_file = project_root / out
            if not live_file.is_file():
                console.print(f"[red]concierge:[/red] --check needs a live contract; none at {live_file}")
                raise typer.Exit(_EXIT_FATAL_INPUTS)
            drift = check_drift(list(models), live_schema_text=live_file.read_text(encoding="utf-8"),
                                project_pythonpath=ppath, model_names=model_names, exclude_models=exclude)
            if json_out:
                _emit_json(drift.__dict__)
            else:
                color = "green" if drift.verdict == "in_sync" else "red"
                console.print(f"[bold]derive-contract --check[/bold] — [{color}]{drift.verdict}[/{color}] "
                              f"({len(drift.drift)} drift, {len(drift.excluded_flagged)} ratified-flagged suppressed)")
                for line in drift.drift:
                    console.print(f"  [red]drift[/red] {line}")
            raise typer.Exit(0 if drift.verdict == "in_sync" else _EXIT_DRIFT)

        derivation = build_derivation(list(models), project_pythonpath=ppath,
                                      model_names=model_names, exclude_models=exclude)
    except DeriveImportError as exc:
        console.print(f"[red]concierge: derivation failed (fail-closed) — {exc}[/red]")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    r = derivation.report
    if json_out and not apply:
        _emit_json(derivation.__dict__)
        return
    console.print(f"[bold]derive-contract[/bold] {'(preview)' if not apply else ''} — "
                  f"{derivation.shape['entities']} entities, {derivation.shape['enums']} enums, "
                  f"{derivation.shape['joins']} joins")
    for e in derivation.errors:
        console.print(f"  [red]error[/red] {e}")
    if r.get("flags"):
        console.print(f"  [yellow]{len(r['flags'])} flag(s)[/yellow] for review (ambiguities/exclusions)")
    if derivation.unrenderable:
        console.print(f"  [yellow]{len(derivation.unrenderable)} unrenderable field(s)[/yellow]")

    if not apply:
        console.print("\n  [dim]preview only — re-run with --apply to write the candidate contract[/dim]")
        return

    rel = out.as_posix()
    action = ACTION_OVERWRITE if (project_root / out).is_file() else ACTION_NEW
    plan = [PlannedWrite(path=rel, action=action, content=derivation.contract_text)]
    try:
        res = apply_write_plan(project_root, plan, force=force)
    except SafeWriteError as exc:
        console.print(f"[red]concierge: blocked — {exc}[/red]")
        raise typer.Exit(_EXIT_BLOCKED)
    _render_write_result(res)
    console.print("  [dim]written as a CANDIDATE (unratified) — the Architect must ratify (FR-DC-7c)[/dim]")
    if not res.ok:
        raise typer.Exit(_EXIT_BLOCKED)


# --- GE-M1: the single guided entry point — Orient → Guide → Deepen ------------------------------
# `startd8 kickoff guided` sequences the three *functions* of the onboarding experience as *phases
# of one flow* over the existing kernel spine (FR-GE-5). It introduces NO new engine (FR-GE-6):
#   • Orient = the readiness surface — reuses `build_assess` + the same `_render_assess` projection.
#   • Guide  = the DETERMINISTIC $0 conductor — reuses `orchestrator.build_kickoff_plan`, which
#              itself renders `red_carpet_advisor`'s no-LLM ranked playbook. No LLM by default
#              (FR-GE-5): a no-agent user is walked to build-ready at ZERO LLM cost.
#   • Deepen = an OPTIONAL, clearly-marked hook to the facilitation panel — a thin pointer only
#              here (GE-M3 promotes/hardens the panel). `--deepen` names the existing surface; it
#              never invokes an LLM in GE-M1.


def kickoff_guided(
    project_root: Path = typer.Argument(
        Path("."), help="Project to guide (default: current dir). Orient + Guide are read-only, $0."
    ),
    deepen: bool = typer.Option(
        False, "--deepen",
        help="Surface the optional Deepen phase (facilitation panel) pointer. GE-M1: pointer only, no LLM.",
    ),
    agent: bool = typer.Option(
        False, "--agent",
        help="Opt in to the LLM-assisted interview during Guide (paid). OFF by default — Guide is $0/no-LLM.",
    ),
    brief: bool = typer.Option(
        False, "--brief", "--no-intro",
        help="Show the one-line intro pointer instead of the full process intro (FR-10).",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the combined guided view as JSON."),
) -> None:
    """The single guided kickoff experience: Orient → Guide → Deepen, over the existing kernel.

    Deterministic-first (FR-GE-5): Orient and Guide are **$0 / no-LLM**. The `--agent` LLM interview
    is strictly opt-in and never required — "guided for a no-agent user" costs zero LLM. Read-only:
    this command spends/writes nothing; each Guide step is a command the human runs at its gate.
    """
    from .concierge import ConciergeError, build_assess
    from .kickoff_experience.concierge_view import build_guided_view, render_deepen_lines
    from .kickoff_experience.orchestrator import build_kickoff_plan

    # ── Orient — the readiness surface (reuse `build_assess`; NO recompute — FR-GE-6). ──
    try:
        assess = build_assess(project_root)
    except ConciergeError as exc:
        console.print(f"[red]kickoff guided:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    # ── Guide — the deterministic $0 conductor (reuse the advisor's ranked playbook). ──
    plan = build_kickoff_plan(project_root)

    # GE-M4: the ONE guided view-model (parity oracle) — the CLI is now a pure function of it. Reuse
    # the already-computed Orient/Guide (no recompute); Deepen reads any persisted facilitation
    # session so its GE-M3b halted/cost states surface identically to the TUI and served surfaces.
    view = build_guided_view(project_root, assess=assess, plan=plan, load_deepen=True, brief=brief)

    if json_out:
        _emit_json(view)
        return

    console.print("[bold]Guided kickoff[/bold] — one experience, three phases (Orient → Guide → Deepen)\n")

    # FR-3 / clause A — lead with the process intro (full on first run, one-line pointer once past
    # onboarding or under --brief). FR-4 / clause B — surface posture as information, pointing at the
    # actionable `instantiate --posture`; the guided flow never records it (FR-GE-1).
    intro = view.get("intro") or {}
    if intro.get("text"):
        console.print(intro["text"], markup=False, highlight=False)
        console.print()
    posture = view.get("posture") or {}
    if posture.get("actionable_hint"):
        cur = posture.get("current_mode")
        state = f"current mode = {cur}" if cur else "not yet chosen"
        console.print(
            f"[bold cyan]Posture[/bold cyan] — {state}. Set it when you instantiate: "
            f"{posture['actionable_hint']}\n",
            highlight=False,
        )

    console.print("[bold cyan]1. Orient[/bold cyan] — where you are (readiness)\n")
    _render_assess(view["orient"])

    console.print("\n[bold cyan]2. Guide[/bold cyan] — the $0 conductor (deterministic, no LLM)\n")
    console.print(plan.render(), markup=False, highlight=False)
    if agent:
        # `--agent` is the strictly opt-in, propose-only LLM interview (FR-GE-5). Guide's *default*
        # remains $0; the interview lives on the existing red-carpet surface, run by the human.
        console.print(
            "\n  [dim]--agent: the optional LLM interview is available at "
            "[cyan]startd8 kickoff-legacy red-carpet --agent[/cyan] (paid, propose-only).[/dim]"
        )

    # ── Deepen — the shared projection (render_deepen_lines): a persisted session's status/halt/cost
    #    when engaged (GE-M3b), else the GE-M1 optional pointer. Same text the TUI emits (parity). ──
    console.print("\n[bold cyan]3. Deepen[/bold cyan] — optional multi-perspective facilitation")
    for line in render_deepen_lines(view["deepen"], deepen_flag=deepen):
        console.print(line, markup=False, highlight=False)

    # The guided flow itself writes nothing and calls no LLM (FR-GE-1 byte-identical residue).


def kickoff_deepen(
    project_root: Path = typer.Argument(
        Path("."), help="Project to deepen (default: current dir)."
    ),
) -> None:
    """The optional Deepen phase — the multi-perspective facilitation panel (GE-M1: pointer only).

    GE-M1 leaves this as a clearly-marked thin entry: it names the existing panel surface but does
    NOT invoke an LLM or promote the panel (GE-M3 promotes/hardens facilitation as a first-class
    phase). Read-only, $0.
    """
    console.print("[bold]Deepen[/bold] — optional multi-perspective facilitation (the discovery pass)")
    console.print(
        "  [dim]This first-class facilitation phase is coming in a later step (GE-M3). For now, drive "
        "the stakeholder panel directly via[/dim] [cyan]startd8 kickoff panel ask-all[/cyan] "
        "[dim](paid, synthetic — every answer is unratified input).[/dim]"
    )


# --- FR-5 / clauses E,G,H: the instructional surface — "what each input is and why we ask" --------
# `kickoff explain` renders the packaged instructional docs at runtime (no leaving the terminal, no
# instantiate required). `--intro` = the generic experience intro (render-only loader); `--inputs`
# (default) = the What/Why/Who explainer + the "inputs we do NOT ask here" boundary and the
# pre-non-demo contacts warning. Single-source: same packaged bytes instantiate would write (FR-6).

_INPUTS_EXPLAINED_KEY = "kickoff-inputs-explained"


def _strip_template_banner(text: str) -> str:
    """Drop a leading ``> **TEMPLATE** …`` blockquote (instantiate-only noise) for display."""
    lines = text.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(">") and "TEMPLATE" in line:
            while i < len(lines) and lines[i].startswith(">"):
                i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out).strip()


def kickoff_explain(
    domain: Optional[str] = typer.Argument(
        None,
        help="One input domain to explain (business-targets|observability|conventions|"
             "build-preferences). Omit for the whole explainer.",
    ),
    intro: bool = typer.Option(
        False, "--intro", help="Show the generic kickoff-process intro instead of the inputs explainer."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the doc content as JSON to stdout."),
) -> None:
    """Explain the kickoff inputs — what each is, why the build needs it, and who provides it ($0)."""
    from .concierge import ConciergeError, load_experience_doc
    from .concierge.core import explain_input_domain
    from .concierge.writes import get_template_entry, render_template_content

    # A single domain: registry routing metadata + its section sliced from the explainer (FR-5 / OQ-7).
    if domain:
        try:
            d = explain_input_domain(domain)
        except ConciergeError as exc:
            console.print(f"[red]kickoff explain:[/red] {exc}")
            raise typer.Exit(_EXIT_FATAL_INPUTS)
        if json_out:
            _emit_json({"schema": "kickoff.explain.v1", "action": "explain", "doc": f"domain:{domain}", **d})
            return
        console.print(f"[bold]{d['label']}[/bold] — {d['question']}")
        console.print(f"[dim]File:[/dim] {d['file']}    [dim]Provided by:[/dim] {d['who']}\n")
        _render_markdown(d["prose"])
        return

    if intro:
        doc, content = "kickoff-experience-intro", load_experience_doc("intro")
    else:
        entry = get_template_entry(_INPUTS_EXPLAINED_KEY)
        if entry is None:  # pragma: no cover — manifest is a build-time invariant
            console.print("[red]kickoff explain:[/red] inputs explainer template not found.")
            raise typer.Exit(_EXIT_FATAL_INPUTS)
        doc, content = _INPUTS_EXPLAINED_KEY, _strip_template_banner(render_template_content(entry))

    if json_out:
        _emit_json({"schema": "kickoff.explain.v1", "action": "explain", "doc": doc, "content": content})
        return

    _render_markdown(content)


# --- Value-input confirmation: `kickoff confirm` (the honest replacement for the legacy wizard) ---
# $0 kernel verb: capture a REAL value (or --as-is) into a defaulted field and record the decision in
# the additive, committed ledger (docs/kickoff/confirmed.yaml). `kickoff assess` then shows the honest
# awaiting/confirmed count. Never writes a sentinel; partial-failure is loud (see confirmation.py).
def _kickoff_confirm_guided(project_root: Path, json_out: bool) -> None:
    """Bare `kickoff confirm` — the interactive guided walk over awaiting fields (FR-1/FR-7). TTY-only:
    under --json / a pipe / non-TTY it REFUSES to prompt (a write flow must not silently no-op) and
    instead lists the awaiting fields + the scriptable single-field form."""
    from .concierge.confirm_walk import awaiting_fields, run_confirm_walk

    awaiting = awaiting_fields(project_root)
    paths = [f["value_path"] for f in awaiting]

    if json_out or not console.is_terminal:   # FR-7: refuse, don't no-op — list instead.
        if json_out:
            _emit_json({"schema": "kickoff.confirm.walk.v1", "action": "confirm_walk",
                        "interactive": False, "awaiting": paths})
        elif paths:
            console.print("[yellow]The guided walk needs a terminal.[/yellow] Script these instead:")
            for p in paths:
                console.print(f"  startd8 kickoff confirm {p} --value <v>")
        else:
            console.print("[green]✓ nothing awaiting confirmation.[/green]")
        return

    if not awaiting:
        console.print("[green]✓ nothing awaiting confirmation.[/green]")
        return

    def _read(prompt: str) -> Optional[str]:
        try:
            return typer.prompt(prompt, default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            return None

    console.print("[bold]Guided confirm[/bold] — walk your defaulted inputs ($0, no LLM). "
                  "[dim]Enter = skip · a = as-is · q = quit[/dim]\n")
    summary = run_confirm_walk(
        project_root, read_input=_read,
        emit_line=lambda s: console.print(s, markup=False, highlight=False),
    )
    console.print(f"\n[bold]Done[/bold] — {len(summary['confirmed'])} confirmed this session · "
                  f"{summary['remaining']} still awaiting.")


def kickoff_confirm(
    value_path: Optional[str] = typer.Argument(
        None,
        help="The field to confirm, e.g. build-preferences.yaml#/budgets.per_pipeline_run "
             "(see `startd8 kickoff assess`). OMIT for the interactive guided walk.",
    ),
    value: Optional[str] = typer.Option(None, "--value", help="A real value to set and confirm."),
    as_is: bool = typer.Option(
        False, "--as-is", help="Confirm the current default value unchanged (no YAML value change)."
    ),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root (default: cwd)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the confirmation as JSON."),
) -> None:
    """Confirm a defaulted kickoff value-input ($0). Give a <value_path> to set/confirm one field, or
    OMIT it to walk all awaiting fields interactively."""
    from .concierge.confirmation import ConfirmError, apply_confirm, build_confirm_plan

    # Bare `kickoff confirm` → the guided walk (OQ-1).
    if value_path is None:
        if value is not None or as_is:
            console.print("[red]kickoff confirm:[/red] --value/--as-is need a <value_path>; "
                          "omit them for the guided walk")
            raise typer.Exit(_EXIT_FATAL_INPUTS)
        _kickoff_confirm_guided(project_root, json_out)
        return

    # FR-UX-16 — banner leads the direct-confirm human view; the guided walk above is exempt.
    if not json_out:
        render_intro_banner()

    if (value is not None) == as_is:   # need exactly one of --value / --as-is
        console.print("[red]kickoff confirm:[/red] provide exactly one of --value <v> or --as-is")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    mode = "as-is" if as_is else "set"
    try:
        plan = build_confirm_plan(project_root, value_path, value, mode=mode)
        result = apply_confirm(project_root, plan)
    except ConfirmError as exc:
        console.print(f"[red]kickoff confirm:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)

    if json_out:
        _emit_json({"schema": "kickoff.confirm.v1", "action": "confirm", **result})
        return
    console.print(
        f"  [green]✓ confirmed[/green] {result['value_path']} = {result['value']!r} "
        f"([dim]{result['mode']}[/dim]) — [dim]run[/dim] startd8 kickoff assess [dim]to see the count[/dim]"
    )


# --- Kickoff audience (fluency) — M1 (FR-1/FR-2/FR-3) --------------------------------------------
# `audience` is a lens over the one guided experience (orthogonal to `posture`): beginner /
# intermediate / advanced. M1 is the persistence spine only — `set` writes ONLY the preference; it
# never runs the pre-pass (that is M3, at walk-start). Unset ⇒ intermediate ⇒ byte-identical to today.
audience_app = typer.Typer(
    name="audience",
    help="Choose how much guidance kickoff gives you (beginner/intermediate/advanced).",
)


def _render_audience_show(project_root: Path, json_out: bool) -> None:
    """Resolve + render the current audience (shared by the group callback and `show`)."""
    from .concierge.audience import resolve_audience_preference

    res = resolve_audience_preference(project_root)
    if json_out:
        _emit_json({
            "schema": "kickoff.audience.v1",
            "action": "show",
            "audience": res.value.value,
            "source": res.source,
        })
        return
    from .cli_shared import render_intro_banner

    render_intro_banner()
    console.print(f"  audience: [cyan]{res.value.value}[/cyan]  ([dim]from {res.source}[/dim])")
    if res.source == "default":
        console.print(
            "  [dim]unset — defaulting to intermediate. set one with[/dim] "
            "startd8 kickoff audience set <beginner|intermediate|advanced>"
        )


@audience_app.callback(invoke_without_command=True)
def _audience_root(ctx: typer.Context) -> None:
    """Show or set your kickoff audience. With no subcommand, shows the current one."""
    if ctx.invoked_subcommand is not None:
        return
    _render_audience_show(Path("."), False)


@audience_app.command("show")
def _audience_show(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root (default: cwd)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the resolved audience as JSON."),
) -> None:
    """Show the resolved kickoff audience and which layer decided it ($0, read-only)."""
    _render_audience_show(project_root, json_out)


@audience_app.command("set")
def _audience_set(
    audience: str = typer.Argument(..., help="beginner | intermediate | advanced"),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root (default: cwd)."),
    global_scope: bool = typer.Option(
        False, "--global", help="Write the user-level preference instead of this project's."
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the write result as JSON."),
) -> None:
    """Set your kickoff audience ($0). Writes ONLY the preference — it takes effect the next time you
    run the guided walk, and never changes what gets built."""
    from .concierge.audience import set_audience_preference

    scope = "global" if global_scope else "project"
    try:
        result = set_audience_preference(audience, project_root=project_root, scope=scope)
    except ValueError as exc:
        console.print(f"[red]kickoff audience set:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL_INPUTS)
    if json_out:
        _emit_json({
            "schema": "kickoff.audience.v1",
            "action": "set",
            "audience": result.value.value,
            "scope": result.scope,
            "target": result.target,
        })
        return
    console.print(
        f"  [green]✓ audience set[/green] to [cyan]{result.value.value}[/cyan] "
        f"([dim]{result.scope}: {result.target}[/dim])"
    )
    console.print(
        "  [dim]takes effect on your next[/dim] startd8 kickoff guided [dim]— nothing was built[/dim]"
    )


# --- M0b: the `startd8 kickoff` kernel surface ---------------------------------------------------
# The kernel reuses the exact command bodies above under function-named verbs. `survey`/`assess`/
# `log-friction` keep their names; `instantiate-kickoff`→`instantiate` and `derive-contract`→`derive`
# are renamed (OQ-9: `derive` stays on-surface as the labeled brownfield on-ramp). The old
# `startd8 concierge …` subcommand names remain reachable via the deprecated `concierge_app` alias
# group (its callback emits the FR-10 deprecation warning).
kickoff_kernel_app.command("survey")(concierge_survey)
kickoff_kernel_app.command("assess")(concierge_assess)
# FR-5: the instructional surface (intro + inputs What/Why/Who). Read-only, $0.
kickoff_kernel_app.command("explain")(kickoff_explain)
# Value-input confirmation ($0): set/confirm a defaulted field; assess shows the honest count.
kickoff_kernel_app.command("confirm")(kickoff_confirm)
kickoff_kernel_app.command("instantiate")(concierge_instantiate)
kickoff_kernel_app.command("log-friction")(concierge_log_friction)
kickoff_kernel_app.command("derive")(concierge_derive_contract)
# GE-M1: the single guided entry point (Orient → Guide → Deepen). Lives under `kickoff` only.
kickoff_kernel_app.command("guided")(kickoff_guided)
# GE-M1: the optional Deepen phase as a standalone verb under `kickoff` (pointer only in GE-M1).
kickoff_kernel_app.command("deepen")(kickoff_deepen)
# Kickoff-audience M1: the `startd8 kickoff audience [show|set]` sub-group (fluency lens).
kickoff_kernel_app.add_typer(audience_app, name="audience")
