"""`startd8 kickoff` — the kickoff CLI family. First command: `check` (contract OQ-2 / plan K1).

The author's pre-flight: run the deterministic manifest extraction as a dry-run against
kickoff docs, render the conformance report, write nothing. Every `not_extracted` row that is
NOT a generator-gap is the co-work worklist (the contract's §3 friction loop): reformat the
prose, re-check, repeat — zero LLM calls in the loop itself.

Exit semantics — this is an AUTHORING tool, distinct from the wireframe's advisory-only rule:
default exit 0; ``--strict`` exits 1 when any conformance-class failure remains (generator-gap
flags and honest `defaulted` derivations never gate — they are backlog/provenance, not author
errors).

Scope note: this lands plan **K1** (the command + contract DIFF). The **K2** §2.7 env-keys
agreement check (declared env defaults vs ``inputs/build-preferences.yaml``) is a deferred
follow-up — it needs a ``build_preferences_text`` pass added to ``extract_manifests``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from .manifest_extraction import (
    Status,
    extract_manifests,
    report_to_json,
)
from .manifest_extraction.models import ExtractionRecord, ExtractionResult

console = Console()

kickoff_app = typer.Typer(
    help="[DEPRECATED — renamed to `kickoff-legacy`] Kickoff-package metaphor tooling "
    "(authoring contract, conformance). The `kickoff` name now hosts the onboarding kernel."
)

# stderr so the notice never pollutes any `--json` stdout contract.
_stderr_console = Console(stderr=True)

_EXIT_CONFORMANCE = 1
_EXIT_FATAL = 2

_GENERATOR_GAP_MARKER = "generator-gap"


def _persist_kickoff_snapshot(project: Path, chat: object) -> None:
    """Persist a durable session snapshot for the agentic Workbook cockpit (FR-1).

    Fully best-effort and self-contained: any failure is swallowed so a snapshot hiccup can never
    break session exit. Prints a dim confirmation only when a snapshot is actually written (a session
    that never produced a turn is presence-gated to no file).
    """
    try:
        from .kickoff_experience.session_snapshot import persist_snapshot_for_chat

        path = persist_snapshot_for_chat(str(project), chat)
    except Exception as exc:  # never break session exit
        console.print(f"[dim]session snapshot skipped: {exc}[/dim]")
        return
    if path is not None:
        console.print(
            "[dim]snapshot: session mirrored to .startd8/kickoff/agentic-session.json[/dim]"
        )
        console.print(
            "[dim]  → see it in the agentic cockpit (Status / Assistant / Proposals):[/dim]"
        )
        console.print(
            "[cyan]     startd8 kickoff portal --dynamic --provision http://localhost:3000[/cyan]"
        )


def _is_conformance_failure(record: ExtractionRecord) -> bool:
    """Author-actionable failures gate `--strict`; generator-gaps are SDK backlog, not author
    errors."""
    return record.status == Status.NOT_EXTRACTED and _GENERATOR_GAP_MARKER not in (
        record.reason or ""
    )


@kickoff_app.callback()
def _kickoff_callback() -> None:
    """[DEPRECATED] The metaphor group moved to `startd8 kickoff-legacy` (M0a).

    The `kickoff` name now hosts the onboarding kernel (survey/assess/instantiate/derive). These
    metaphor commands keep working under `kickoff-legacy` for the transition.
    """
    import warnings

    warnings.warn(
        "`startd8 kickoff <metaphor-command>` moved to `startd8 kickoff-legacy`; "
        "the `kickoff` name now hosts the onboarding kernel.",
        DeprecationWarning,
        stacklevel=2,
    )
    _stderr_console.print(
        "[yellow]deprecation:[/yellow] these metaphor commands moved to "
        "`startd8 kickoff-legacy` (the `kickoff` name now hosts the onboarding kernel)."
    )


@kickoff_app.command("check")
def check(
    docs: List[Path] = typer.Argument(
        ...,
        help="Kickoff doc(s) in the authoring-contract format (REQUIREMENTS/PLAN markdown).",
    ),
    project: Optional[Path] = typer.Option(
        None,
        "--project",
        help="Consumer project root: enables the contract DIFF against prisma/schema.prisma.",
    ),
    contract: Optional[Path] = typer.Option(
        None,
        "--contract",
        help="Path to an authored schema.prisma. Contract-first projects (no prose `## Entities`) "
        "resolve assembly-manifest entity references — views Root, completeness, imports — against it "
        "(FR-CFE). Overrides --project's prisma/schema.prisma when both are given.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit the extraction report JSON to stdout (machine output).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit 1 when any author-actionable conformance failure remains "
        "(generator-gap flags never gate).",
    ),
) -> None:
    """Check kickoff docs against the authoring contract — extraction dry-run, writes nothing."""
    doc_texts = {}
    for doc in docs:
        try:
            doc_texts[doc.name] = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            console.print(f"[red]kickoff check:[/red] cannot read {doc}: {exc}")
            raise typer.Exit(_EXIT_FATAL)

    live_schema_text = None
    # An explicit --contract wins over --project's conventional prisma/schema.prisma.
    schema_path = (
        contract
        if contract is not None
        else (project / "prisma" / "schema.prisma" if project is not None else None)
    )
    if schema_path is not None and schema_path.is_file():
        live_schema_text = schema_path.read_text(encoding="utf-8")

    result = extract_manifests(doc_texts, live_schema_text=live_schema_text)

    if json_out:
        sys.stdout.write(report_to_json(result))
    else:
        _render(result)

    # FR-F1a/F1d: advisories (e.g. a truncated `choice of:`) are values that DID extract but are
    # suspicious. Warn visibly by default (exit 0 preserved); `--strict` promotes them to failures so
    # silent data loss cannot pass a green gate. Warnings go to stderr so `--json` stdout stays clean.
    advisories = [r for r in result.records if r.is_advisory]
    if advisories and not json_out:
        for r in advisories:
            _stderr_console.print(f"[yellow]advisory:[/yellow] {r.reason}")

    if strict and (
        any(_is_conformance_failure(r) for r in result.records) or advisories
    ):
        raise typer.Exit(_EXIT_CONFORMANCE)


def _render(result: ExtractionResult) -> None:
    worklist = [r for r in result.sorted_records() if _is_conformance_failure(r)]
    gaps = [
        r
        for r in result.by_status(Status.NOT_EXTRACTED)
        if _GENERATOR_GAP_MARKER in (r.reason or "")
    ]
    extracted = len(result.by_status(Status.EXTRACTED))
    defaulted = len(result.by_status(Status.DEFAULTED))

    console.print(
        f"[bold]Conformance:[/bold] {extracted} extracted · {defaulted} defaulted (derived) · "
        f"[yellow]{len(gaps)} generator-gap[/yellow] (SDK backlog, not author errors) · "
        + (
            f"[red]{len(worklist)} to fix[/red]"
            if worklist
            else "[green]0 to fix — docs conform[/green]"
        )
    )
    console.print(
        f"[dim]Manifests extractable: {', '.join(sorted(result.manifests)) or 'none'} "
        f"(grammar {result.grammar_version})[/dim]"
    )

    if worklist:
        table = Table(
            title="Co-work worklist (contract §3: reformat the prose, re-check)"
        )
        table.add_column("Manifest")
        table.add_column("Value")
        table.add_column("Fix")
        table.add_column("Source")
        for r in worklist:
            src = ""
            if r.source:
                src = " › ".join(r.source.heading_path) or r.source.doc
                if r.source.row_index is not None:
                    src += f" (row {r.source.row_index})"
            table.add_row(r.manifest, r.value_path, r.reason or "", src)
        console.print(table)

    if result.contract_diff:
        console.print("\n[bold]Contract DIFF (docs vs live schema.prisma):[/bold]")
        for line in result.contract_diff:
            console.print(f"  [yellow]• {line}[/yellow]")
    elif result.contract_diff == [] and result.records:
        console.print("[dim]Contract DIFF: clean (or no live contract supplied).[/dim]")


@kickoff_app.command("lint-config")
def lint_config_cmd() -> None:
    """Lint the SDK-internal kickoff experience config (R3-S2). Exit 1 if any issue."""
    from .kickoff_experience.manifest import default_config, lint_config

    issues = lint_config(default_config())
    if not issues:
        console.print("[green]kickoff config: clean[/green]")
        return
    for issue in issues:
        console.print(
            f"[red]✗[/red] {issue.field_key}: [yellow]{issue.code}[/yellow] — {issue.message}"
        )
    raise typer.Exit(_EXIT_CONFORMANCE)


@kickoff_app.command("inspect")
def inspect_cmd(
    project: Path = typer.Argument(
        Path("."), help="Project root (default: current directory)."
    ),
    json_out: bool = typer.Option(
        True, "--json/--no-json", help="Emit inspect JSON to stdout."
    ),
) -> None:
    """Read-only kickoff state for CI/agents (R4-F3): no serve, no port, no write."""
    import json as _json

    from .kickoff_experience.serve import inspect_payload

    payload = inspect_payload(project)
    if json_out:
        sys.stdout.write(_json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        state = payload["state"]
        na = payload["next_action"]
        console.print(
            f"[bold]Kickoff state[/bold] — {state['counts']} · next: [cyan]{na['title']}[/cyan]"
        )
        console.print(f"[dim]preflight ok={payload['preflight']['ok']}[/dim]")


def _render_red_carpet_state(state, *, verbose: bool = False) -> None:
    """KICKOFF_UX — the focused status view: one progress spine (rendered once), one honest '% filled'
    headline, a never-hidden error banner, and THE single next action. Full advisories/playbook only
    under --verbose. Plain language via the single-source GLOSSARY (no jargon in the default view).
    """
    from .kickoff_experience.presentation import build_spine, headline

    hl = headline(state)
    console.print(f"[bold]🟥 Red Carpet[/bold] · [bold]{hl['pct_label']}[/bold]")
    # FR-UX-5/F4 — error advisories are NEVER hidden, even in the default view.
    if hl["n_errors"]:
        console.print(
            f"  [red]⚠ {hl['n_errors']} problem(s) need fixing[/red] → [cyan]--verbose[/cyan]"
        )

    # FR-UX-6 — the ONE progress spine (three things + Build), glossary-named, said once.
    glyph = {
        "done": "[green]✓[/green]",
        "next": "[cyan]→[/cyan]",
        "todo": "[dim]·[/dim]",
        "ready": "[green]◆[/green]",
        "later": "[dim]∘[/dim]",
    }
    for n in build_spine(state):
        meter = (
            f"  [dim]{n.filled}/{n.total}[/dim]"
            if n.filled is not None and n.total
            else ""
        )
        style = "dim" if (n.optional or n.status in ("todo", "later")) else "bold"
        console.print(
            f"  {glyph.get(n.status, '·')} [{style}]{n.plain_name}[/{style}]{meter}"
        )

    # FR-UX-4/15 — the single next action (plain, from the spine — never playbook jargon), with its
    # one-line *why* so the user understands not just what to do but why it's next.
    na = hl["next_action"]
    why = f" [dim]— {na['why']}[/dim]" if na.get("why") else ""
    console.print(f"[bold]▸ Do next:[/bold] {na['title']}{why}")
    if na.get("command"):
        console.print(f"   [cyan]{na['command']}[/cyan]")

    if not verbose:
        extra = len(getattr(state, "advisories", ()) or ()) + len(
            getattr(state, "next_steps", ()) or ()
        )
        if extra:
            console.print(f"  [dim]{extra} more details → --verbose[/dim]")
        return

    # --verbose — the full advisory list + ranked playbook (the prior detail), plain-labeled.
    if state.advisories:
        console.print("[bold]Insights[/bold]")
        sev_style = {"error": "red", "warn": "yellow", "info": "dim"}
        for a in state.advisories:
            style = sev_style.get(a.severity, "dim")
            console.print(f"  [{style}]•[/{style}] [bold]{a.title}[/bold] — {a.detail}")
            console.print(f"      [dim]→ {a.action}[/dim]")
            if a.command:
                console.print(f"      [cyan]{a.command}[/cyan]")
    if state.next_steps:
        console.print("[bold]Playbook[/bold]")
        for step in state.next_steps:
            cmd = f"  [cyan]{step.command}[/cyan]" if step.command else ""
            console.print(f"  {step.rank}. {step.title}{cmd}")
    if state.readiness_score is not None:
        console.print(
            f"[dim]cascade readiness: {int(round(state.readiness_score * 100))}%[/dim]"
        )


@kickoff_app.command("red-carpet")
def red_carpet_cmd(
    project: Path = typer.Argument(
        Path("."), help="Project root to build (default: current directory)."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the staged build state as JSON."
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show the full insights + playbook detail (default view is a focused summary).",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="CI signal ($0, read-only): exit 1 if any error-severity advisory (hard readiness "
        "problem) is present, else 0. warn/info never fail.",
    ),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Run the agentic interview loop with this agent (spends tokens).",
    ),
) -> None:
    """Red Carpet Treatment — the staged, agentic build-from-scratch conductor.

    Without a flag: read-only staged status ($0) — where the build stands, the next gap, completion %.
    (The interactive `--wizard` was retired — use `startd8 kickoff confirm` for value inputs and
    `startd8 kickoff guided` for the plan.)
    With `--agent`: the conversational interview loop — the agent works the next gap and RECOMMENDS each
    input; you confirm every write.
    With `--check`: an advisory CI signal — exit 1 iff an error-severity advisory is present.
    """
    import json as _json

    from .kickoff_experience.red_carpet import build_red_carpet_state

    # FR-UX-16 — the high-level banner leads every human-facing invocation (status, agent).
    # Never on --json (machine payload) or --check (CI signal).
    if not json_out and not check:
        from .cli_shared import render_intro_banner

        render_intro_banner()

    # FR-RCA-15 — advisory CI exit-code mode (not a build gate; warn/info never fail).
    if check:
        try:
            state = build_red_carpet_state(project)
        except Exception as exc:  # internal error → distinct exit code
            console.print(f"[red]red-carpet --check:[/red] {exc}")
            raise typer.Exit(_EXIT_FATAL)
        errors = [a for a in state.advisories if a.severity == "error"]
        if errors:
            console.print(
                f"[red]red-carpet --check: {len(errors)} error advisory(ies)[/red]"
            )
            for a in errors:
                console.print(f"  [red]•[/red] {a.title} — {a.detail}")
            raise typer.Exit(_EXIT_CONFORMANCE)
        console.print("[green]red-carpet --check: no error advisories[/green]")
        raise typer.Exit(0)

    if json_out:
        sys.stdout.write(
            _json.dumps(
                build_red_carpet_state(project).to_dict(), indent=2, ensure_ascii=False
            )
            + "\n"
        )
        return
    if not agent:
        _render_red_carpet_state(build_red_carpet_state(project), verbose=verbose)
        return

    # Agentic interview loop (FR-RCT) — propose-only; the human confirms every write.
    import asyncio

    from .kickoff_experience.chat import new_red_carpet_chat
    from .kickoff_experience.proposals import apply_proposal
    from .kickoff_experience.red_carpet import (
        prescriptive_banner,
        record_red_carpet_progress,
        reflection_text,
        run_red_carpet_repl,
    )
    from .kickoff_experience.telemetry import EV_RED_CARPET_STARTED, emit
    from .utils.agent_resolution import resolve_agent_spec

    try:
        the_agent = resolve_agent_spec(agent)
        chat = new_red_carpet_chat(the_agent, str(project))
    except (
        Exception
    ) as exc:  # missing key / no tool support → actionable, not a traceback
        console.print(
            f"[red]could not start the Red Carpet agent {agent!r}:[/red] {exc}"
        )
        raise typer.Exit(_EXIT_FATAL)

    def _on_proposal(action) -> Optional[str]:
        # Human-privilege confirm → apply (or discard). The loop never applies on its own.
        console.print(f"[yellow]Proposed:[/yellow] {action.summary()}")
        if typer.confirm("Apply this?", default=False):
            outcome = apply_proposal(project, action)
            chat.buffer.pop(action.id)
            return f"  → [{'green' if outcome.ok else 'red'}]{outcome.code}[/] {outcome.detail}"
        chat.buffer.pop(action.id)
        return "  → discarded"

    def _read(prompt: str) -> Optional[str]:
        try:
            return typer.prompt(prompt, default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            return None

    # Stage funnel (FR-RCT-14) + per-increment reflection (FR-RCT-12). _render fires on load + after
    # each turn; it emits the stage transition and (after the first render) shows the reflection.
    _prev = {"state": None}

    def _render() -> None:
        st = build_red_carpet_state(project)
        _render_red_carpet_state(st)
        record_red_carpet_progress(_prev["state"], st)
        if (
            _prev["state"] is not None
        ):  # an increment just completed → reflect (advisory)
            console.print(f"[dim]{reflection_text(st)}[/dim]")
        _prev["state"] = st

    console.print(f"[dim]agent: {agent}[/dim]")
    emit(EV_RED_CARPET_STARTED)
    # FR-RCA-21 — seed the turn-0 banner with the top insight + top next step so the user sees
    # prescriptive guidance before the model calls a tool.
    _banner = prescriptive_banner(chat.banner(), build_red_carpet_state(project))
    run_red_carpet_repl(
        banner=_banner,
        ask_sync=lambda m: asyncio.run(chat.ask(m)),
        read_input=_read,
        emit_line=lambda line: console.print(line),
        pending=lambda: list(chat.buffer.pending()),
        on_proposal=_on_proposal,
        render_state=_render,
        cost_line=chat.cost_line,
    )

    # Durable session snapshot (FR-1) — mirror the Red Carpet transcript to the Workbook cockpit.
    _persist_kickoff_snapshot(project, chat)


@kickoff_app.command("start")
def start_cmd(
    project: Path = typer.Argument(
        Path("."), help="Project root to serve the kickoff UI for."
    ),
    mode: str = typer.Option(
        "write", "--mode", help="inspect | preview | write | demo (R4-F5)."
    ),
    theme: str = typer.Option(
        "professional", "--theme", help="Presentation-polish theme."
    ),
    port: Optional[int] = typer.Option(
        None, "--port", help="Bind port (default: ephemeral)."
    ),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Enable the web agentic chat panel with this agent (spends tokens).",
    ),
    red_carpet: bool = typer.Option(
        False,
        "--red-carpet",
        help="Make the web chat the stage-aware Red Carpet build conductor.",
    ),
    cloud: bool = typer.Option(
        False,
        "--cloud",
        help="Cloud read/preview-only posture (GE-M5, FR-GE-8): all writes + the paid "
        "facilitation/chat panel are refused (cloud-write deferred to OQ-GE-7). Reads only.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Static X-API-Key gating POSTs when serving --cloud (coarse cloud auth, not tenancy).",
    ),
    grant_store: Optional[Path] = typer.Option(
        None,
        "--grant-store",
        help="Path to a cloud-authorization grant store (the file `startd8 cloud-grant issue` writes). "
        "With --cloud, makes the serve GRANT-CAPABLE: the agentic chat-write path is enabled only for a "
        "valid grant (FR-14 trust chain), consumed per session. Requires --api-key, --deployment-id, "
        "and at least one --cloud-origin.",
    ),
    deployment_id: str = typer.Option(
        "", "--deployment-id", help="This deployment's id — grants are bound to it (with --grant-store)."
    ),
    cloud_origin: Optional[List[str]] = typer.Option(
        None, "--cloud-origin", help="Allowed cloud Origin (repeatable) — the FR-14 Origin factor."
    ),
    mirror_cockpit: bool = typer.Option(
        True,
        "--mirror-cockpit/--no-mirror-cockpit",
        help="Mirror this LOCAL agentic session (redacted) to the .startd8 cockpit store so the "
        "Grafana Assistant/Proposals tabs populate. On by default for local; forced off under "
        "--cloud (FR-WM2-5d stays strict for hosted). Use --no-mirror-cockpit for a pure-ephemeral "
        "session (no chat artifact on disk).",
    ),
) -> None:
    """Serve the interactive kickoff web app on the loopback (preflight first; teardown on exit).

    Pass --agent to enable the conversational Concierge chat panel at /concierge/chat; add --red-carpet
    to make that panel the stage-aware Red Carpet build conductor. Pass --cloud for a read/preview-only
    surface (no writes, no paid facilitation; cloud-write deferred to OQ-GE-7).
    """
    from .kickoff_experience.concierge_agent import resolve_concierge_agent_spec
    from .kickoff_experience.serve import (
        Mode,
        preflight,
        resolve_chat_panel,
        serve_kickoff,
    )

    if mode not in Mode.ALL:
        console.print(f"[red]unknown mode {mode!r}[/red] (one of {Mode.ALL})")
        raise typer.Exit(_EXIT_FATAL)
    pf = preflight(project, mode=mode)
    for c in pf.checks:
        mark = (
            "[green]✓[/green]"
            if c.ok
            else ("[red]✗[/red]" if c.blocking else "[yellow]•[/yellow]")
        )
        console.print(f"  {mark} {c.name}: {c.detail}")
    if not pf.ok:
        console.print("[red]preflight failed — not serving.[/red]")
        raise typer.Exit(_EXIT_FATAL)
    # The agentic panel spends tokens, so it stays opt-in: enable it only on an EXPLICIT agent choice
    # — the --agent flag or a configured `concierge_agent` (project/global) — never the bare default.
    # GE-M5: a --cloud serve is read/preview-only, so the LLM panel is force-disabled regardless.
    grant_capable = bool(cloud and grant_store is not None)
    spec, source = resolve_concierge_agent_spec(project, agent)
    # Cloud is read-only UNLESS grant-capable (a grant store gates chat-write per-request via the FR-14
    # trust chain). Local always allows the panel when an agent is configured.
    panel_spec = (spec if source != "default" else None) if (not cloud or grant_capable) else None
    # M5: build the out-of-band grant store the served app CONSUMES (NR-6 — the app never mints).
    grant_store_obj = None
    origins = frozenset(cloud_origin or ())
    if grant_capable:
        missing = [n for n, v in (("--api-key", api_key), ("--deployment-id", deployment_id)) if not v]
        if not origins:
            missing.append("--cloud-origin")
        if missing:
            console.print(
                f"[red]--grant-store requires {', '.join(missing)}[/red] — "
                "the FR-14 trust chain (api-key ∧ Origin ∧ grant) can never be satisfied without them."
            )
            raise typer.Exit(_EXIT_FATAL)
        from .kickoff_experience.cloud_grant import AuditLog, FileGrantStore
        try:
            grant_store_obj = FileGrantStore(grant_store, audit=AuditLog(grant_store.parent / "audit.jsonl"))
        except Exception as exc:
            console.print(f"[red]could not open grant store {grant_store}:[/red] {exc}")
            raise typer.Exit(_EXIT_FATAL)
        console.print(
            f"  [green]✓[/green] grant-capable cloud serve: chat-write enabled per valid grant "
            f"(store: {grant_store}, deployment: {deployment_id}, origins: {len(origins)})"
        )
    elif cloud:
        console.print(
            "  [yellow]•[/yellow] cloud read/preview-only: writes + paid facilitation refused "
            "(cloud-write deferred, OQ-GE-7). Pass --grant-store to enable grant-gated chat-write."
        )
    mirror = bool(mirror_cockpit) and not cloud
    if panel_spec:
        resolution = resolve_chat_panel(project, panel_spec, red_carpet=red_carpet)
        flavor = "Red Carpet build conductor" if red_carpet else "Concierge"
        if resolution.factory is not None:
            console.print(
                f"  [green]✓[/green] agentic chat ({flavor}): "
                f"enabled ({panel_spec}, source: {source})"
            )
            console.print(
                "  [green]✓[/green] cockpit mirror: on — this local session is persisted "
                "(redacted) to .startd8 for the Grafana cockpit (`--no-mirror-cockpit` to disable)"
                if mirror
                else "  [yellow]•[/yellow] cockpit mirror: off — session stays ephemeral "
                "(no chat artifact on disk)"
            )
        else:
            console.print(
                f"  [yellow]•[/yellow] agentic chat ({flavor}) disabled "
                f"(source: {source}) — {resolution.reason}"
            )
    console.print(
        f"[green]serving kickoff[/green] (mode={mode}, theme={theme}) — Ctrl-C to stop"
    )
    serve_kickoff(
        project,
        mode=mode,
        theme=theme,
        port=port,
        agent_spec=panel_spec,
        red_carpet=red_carpet,
        cloud=cloud,
        api_key=api_key,
        mirror_cockpit=mirror,
        grant_store=grant_store_obj,
        deployment_id=deployment_id,
        cloud_origins=origins,
    )


@kickoff_app.command("chat")
def chat_cmd(
    project: Path = typer.Argument(
        Path("."), help="Project root to discuss (read-only)."
    ),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Agent spec provider:model (default: balanced catalog model).",
    ),
) -> None:
    """Conversational, READ-ONLY kickoff assistant (spends LLM tokens).

    Hosts the agentic loop with exactly the read tools survey/assess/field_states — it can explain
    inputs, report what the grammar understood, and advise the next step, but never edits files.
    """
    import asyncio

    from .kickoff_experience.chat import new_kickoff_chat, run_kickoff_repl
    from .kickoff_experience.concierge_agent import resolve_concierge_agent_spec
    from .utils.agent_resolution import resolve_agent_spec

    spec, source = resolve_concierge_agent_spec(project, agent)
    try:
        the_agent = resolve_agent_spec(spec)
    except (
        Exception
    ) as exc:  # missing key / unknown provider → actionable, not a traceback
        console.print(f"[red]could not start agent {spec!r}:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL)
    try:
        chat = new_kickoff_chat(the_agent, str(project))
    except Exception as exc:
        console.print(f"[red]agent {spec!r} does not support tool use:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL)

    def _read(prompt: str) -> Optional[str]:
        try:
            return typer.prompt(prompt, default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            return None

    console.print(f"[dim]agent: {spec} (source: {source})[/dim]")
    run_kickoff_repl(
        banner=chat.banner(),
        ask_sync=lambda m: asyncio.run(chat.ask(m)),
        read_input=_read,
        emit_line=lambda line: console.print(line),
        cost_line=chat.cost_line,
    )

    # Durable session snapshot (FR-1) — mirror this read-only transcript to the agentic Workbook
    # cockpit. Best-effort; a snapshot hiccup never breaks session exit.
    _persist_kickoff_snapshot(project, chat)


@kickoff_app.command("concierge-chat")
def concierge_chat_cmd(
    project: Path = typer.Argument(
        Path("."), help="Project root to onboard (agentic Concierge)."
    ),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Agent spec provider:model (default: balanced catalog model).",
    ),
) -> None:
    """Agentic Concierge — conversational onboarding that RECOMMENDS actions you confirm.

    The assistant surveys/assesses and can propose writes (scaffold the package, draft friction, set
    a field). It never writes to disk: after each turn you confirm each recommendation, and only then
    is it applied through the safe-writer. Spends LLM tokens.
    """
    import asyncio

    from .kickoff_experience.chat import new_agentic_kickoff_chat, run_kickoff_repl
    from .kickoff_experience.concierge_agent import resolve_concierge_agent_spec
    from .kickoff_experience.proposals import apply_proposal
    from .kickoff_experience.tui_concierge import _questionary_confirm
    from .utils.agent_resolution import resolve_agent_spec

    spec, source = resolve_concierge_agent_spec(project, agent)
    try:
        the_agent = resolve_agent_spec(spec)
    except Exception as exc:
        console.print(f"[red]could not start agent {spec!r}:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL)
    try:
        chat = new_agentic_kickoff_chat(the_agent, str(project))
    except Exception as exc:
        console.print(f"[red]agent {spec!r} does not support tool use:[/red] {exc}")
        raise typer.Exit(_EXIT_FATAL)

    def _read(prompt: str) -> Optional[str]:
        try:
            return typer.prompt(prompt, default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            return None

    console.print(
        f"[dim]agent: {spec} (source: {source}) · propose-only (you confirm every write)[/dim]"
    )
    run_kickoff_repl(
        banner=chat.banner(),
        ask_sync=lambda m: asyncio.run(chat.ask(m)),
        read_input=_read,
        emit_line=lambda line: console.print(line),
        cost_line=chat.cost_line,
        pending=lambda: chat.buffer.pending(),
        confirm=_questionary_confirm,
        apply_proposal=lambda a: apply_proposal(str(project), a),
        consume=lambda a: chat.buffer.pop(a.id),
    )

    # VIPP hand-off (opt-in; no-op when not enabled → byte-identical). On session end, serialize any
    # proposals the human did not confirm to the .startd8/vipp/ inbox so the project-side VIPP can
    # negotiate/apply them out-of-process (`startd8 vipp negotiate` → `apply`).
    try:
        from .kickoff_experience.vipp_seam import maybe_serialize_buffer

        handoff = maybe_serialize_buffer(chat.buffer, str(project))
    except Exception as exc:  # never break session exit on a hand-off hiccup
        handoff = None
        console.print(f"[dim]VIPP hand-off skipped: {exc}[/dim]")
    # A pure no-clobber skip is WriteResult.ok==True but wrote nothing — gate the success message
    # on an actual write, and surface the undrained-inbox case distinctly (code-review M2).
    if handoff is not None and handoff.written:
        console.print(
            "[dim]VIPP: pending proposals serialized to .startd8/vipp/proposals-inbox.json — "
            "run `startd8 vipp negotiate`.[/dim]"
        )
    elif handoff is not None and handoff.skipped:
        console.print(
            "[yellow]VIPP: an undrained inbox already exists — run `startd8 vipp negotiate`/`apply` "
            "to consume it before this session's proposals can be serialized.[/yellow]"
        )

    # Durable session snapshot (FR-1), AFTER the inbox handoff (R1-S1 ordering: inbox first, then
    # snapshot). temp-then-rename means a snapshot failure leaves the inbox intact and no partial
    # agentic-session.json. Best-effort — never breaks session exit.
    _persist_kickoff_snapshot(project, chat)


@kickoff_app.command("concierge")
def concierge_cmd(
    project: Path = typer.Argument(
        Path("."), help="Project root to onboard (Concierge mode)."
    ),
    posture: str = typer.Option(
        "prototype", "--posture", help="prototype | production (instantiate)."
    ),
) -> None:
    """Concierge mode in the terminal: survey, instantiate a kickoff package, log friction.

    Read-only triage + readiness; writes (instantiate / friction) happen only on an explicit
    confirmation and fail closed when no interactive terminal is available.
    """
    from .kickoff_experience.tui_concierge import (
        _questionary_confirm,
        _questionary_prompt,
        run_concierge,
    )

    run_concierge(
        str(project),
        confirm=_questionary_confirm,
        prompt=_questionary_prompt,
        emit_line=lambda line: console.print(line),
        posture=posture,
    )


@kickoff_app.command("plan")
def kickoff_plan(
    project: Path = typer.Option(Path("."), "--project", help="Project root."),
    as_json: bool = typer.Option(False, "--json", help="Emit the plan as JSON."),
) -> None:
    """Show the guided greenfield path — the advisor's ranked playbook, cost-labeled (FR-KO-1).

    Read-only: it spends/writes nothing; run each command yourself at its gate.
    """
    import json as _json

    from .kickoff_experience.orchestrator import build_kickoff_plan

    plan = build_kickoff_plan(project)
    if as_json:
        console.print_json(_json.dumps(plan.to_dict()))
        return
    console.print(plan.render(), markup=False, highlight=False)


@kickoff_app.command("next")
def kickoff_next(
    project: Path = typer.Option(Path("."), "--project", help="Project root."),
    as_json: bool = typer.Option(False, "--json", help="Emit the next step as JSON."),
) -> None:
    """Show the single immediate next action in the greenfield path (FR-KO-1)."""
    import json as _json

    from .kickoff_experience.orchestrator import build_kickoff_plan

    step = build_kickoff_plan(project).next_step
    if as_json:
        console.print_json(_json.dumps(step.to_dict() if step else None))
        return
    if step is None:
        console.print(
            "kickoff: no next step — build-ready or nothing to do.", markup=False
        )
        return
    console.print(f"next: [{step.cost}] {step.title}  ({step.stage})", markup=False)
    if step.detail:
        console.print(f"  {step.detail}", markup=False)
    if step.command:
        console.print(f"  $ {step.command}", markup=False)
