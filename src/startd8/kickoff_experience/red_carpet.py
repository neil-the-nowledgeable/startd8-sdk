"""Red Carpet Treatment — the conductor's stage model (N3, FR-RCT-2 / FR-RCT-10).

A **pure, read-only, $0** projection of ``build_assess`` (+ the on-disk manifests) into the staged
build map the experience drives: per-stage done/pending, the next gap, and the cascade-offer predicate.

Design note (R1-F6): the **filesystem is the single source of truth** — the state is recomputed from
``build_assess`` + the conventional manifest paths each call, so it is inherently *resumable* and there
is no stale cursor to reconcile. A persisted progress cursor (a hint, never authoritative) is a later
addition and is unnecessary for correctness.

The conductor never writes here — it reads this state to decide the next gap and whether to offer the
``$0`` cascade. All writes go through the proposal/confirm seam (the ``schema``/``manifest``/``capture``
kinds in :mod:`proposals`), at human privilege.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

# Ordered build stages (FR-RCT-2): data model first (the front bookend), then the manifests that
# derive from it, then the value inputs, then placeholder content, then the cascade run.
STAGES: Tuple[str, ...] = ("data_model", "manifests", "value_inputs", "content", "run")

# The minimal viable subset that makes the $0 cascade offerable (FR-RCT-10 / CRP R1-F7):
# a confirmed schema + an app manifest + at least one page + at least one view.
_CASCADE_GATE_KEYS: Tuple[str, ...] = ("schema", "app", "pages", "views")

# FR-RCA-17 — payload version for MCP/web consumers (parity with kickoff_state_tool).
_RED_CARPET_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RedCarpetStage:
    key: str
    status: str   # "done" | "pending"
    detail: str


@dataclass(frozen=True)
class RedCarpetState:
    """The conductor's read model — what to do next and whether the cascade can run."""

    stages: Tuple[RedCarpetStage, ...]
    next_stage: Optional[str]            # first non-done stage (None ⇒ build-ready)
    cascade_offerable: bool              # the R1-F7 predicate
    unmet_gates: Tuple[str, ...]         # which cascade gates are unmet (named, R1-F7)
    readiness_score: Optional[float]
    preview: Optional[dict] = None       # FR-RCT-11 wireframe preview {shape, counts}, set when offerable
    # FR-RCA — the prescriptive advisor layer (additive; advisory-only, never a gate).
    advisories: Tuple[Any, ...] = ()     # Tuple[Advisory, ...] — insights + per-input diagnosis
    next_steps: Tuple[Any, ...] = ()     # Tuple[NextStep, ...] — the ranked, command-bearing playbook
    perf: Optional[dict] = None          # CRP R1-S3 — {elapsed_ms, budget_ms, over_budget} for the build

    def to_dict(self) -> dict:
        d = {
            "schema_version": _RED_CARPET_SCHEMA_VERSION,
            "stages": [{"key": s.key, "status": s.status, "detail": s.detail} for s in self.stages],
            "next_stage": self.next_stage,
            "cascade_offerable": self.cascade_offerable,
            "unmet_gates": list(self.unmet_gates),
            "readiness_score": self.readiness_score,
            "preview": self.preview,
            "advisories": [a.to_dict() for a in self.advisories],
            "next_steps": [s.to_dict() for s in self.next_steps],
            # FR-RCA-22 — bounded summary header for scripting/CI (complements --check).
            "summary": {
                "errors": sum(1 for a in self.advisories if a.severity == "error"),
                "warns": sum(1 for a in self.advisories if a.severity == "warn"),
                "infos": sum(1 for a in self.advisories if a.severity == "info"),
                "next_steps": len(self.next_steps),
            },
        }
        if self.perf is not None:
            d["perf"] = self.perf
        return d


def _present(root: Path, key: str) -> bool:
    """A conventional manifest is present iff its file exists and is non-empty."""
    from ..wireframe.inputs import CONVENTION_PATHS

    target = root / CONVENTION_PATHS[key]
    return target.is_file() and target.stat().st_size > 0


# FR-RCA payload caps (OQ-E) — keep the per-turn chat tool result bounded.
_ADVISORY_CAP = 7
_NEXTSTEP_CAP = 7


def build_red_carpet_state(project_root: str | Path) -> RedCarpetState:
    """Compute the staged build state from ``build_assess`` + the on-disk manifests (read-only, ``$0``).

    CRP R1-S1: ``build_assess(root)`` is fetched **exactly once** at the top and threaded into readiness,
    the preview, and the FR-RCA advisor — no double scan on either the offerable or the greenfield path.
    """
    from .readiness import BUDGET_INITIAL_MS, PerfSample, _Timer, build_readiness

    root = Path(project_root)
    with _Timer() as timer:
        # Single build_assess fetch (CRP R1-S1) — degrade to {} on unexpected error, never re-scan.
        try:
            from ..concierge.core import build_assess

            assess = build_assess(root) or {}
        except Exception:
            assess = {}

        gates = {k: _present(root, k) for k in _CASCADE_GATE_KEYS}
        unmet = tuple(k for k in _CASCADE_GATE_KEYS if not gates[k])
        offerable = not unmet

        # Value inputs (the 4 domains) + the readiness score, via the existing projection (never
        # recomputed) — the one already-fetched `assess` is threaded in so it is not scanned twice.
        try:
            readiness = build_readiness(root, assess=assess)
            domains = dict(readiness.input_domains or {})
            score = readiness.score
        except Exception:
            domains, score = {}, None
        value_inputs_done = bool(domains) and all(
            (d or {}).get("status") == "present" for d in domains.values()
        )
    # Bootstrap-if-absent (N2-inc2): the value inputs live in the kickoff package; when it is missing
        # the value-inputs stage starts by scaffolding it (the `instantiate` proposal kind).
        package_present = (root / "docs" / "kickoff" / "inputs").is_dir()
        value_inputs_detail = (
            "all four value-input domains present" if value_inputs_done
            else ("scaffold the kickoff package (propose `instantiate`), then fill the four domains"
                  if not package_present
                  else "fill conventions / build-preferences / business-targets / observability"))

        data_model_done = gates["schema"]
        manifests_done = gates["app"] and gates["pages"] and gates["views"]

        stages = (
            RedCarpetStage(
                "data_model", "done" if data_model_done else "pending",
                "schema.prisma confirmed" if data_model_done
                else "interview → derive + promote the data-model contract (the front bookend)"),
            RedCarpetStage(
                "manifests", "done" if manifests_done else "pending",
                "app + pages + views present" if manifests_done
                else "author the assembly manifests (pages/views/app/…) from the schema"),
            RedCarpetStage(
                "value_inputs", "done" if value_inputs_done else "pending", value_inputs_detail),
            # Placeholder bucket-2 content is driven in a later increment; not gating the cascade offer.
            RedCarpetStage("content", "pending", "placeholder content + static test data (later)"),
            RedCarpetStage(
                "run", "done" if offerable else "pending",
                "the $0 cascade is offerable" if offerable
                else f"cascade not offerable — unmet: {', '.join(unmet)}"),
        )
        next_stage = next((s.key for s in stages if s.status != "done"), None)
        # FR-RCT-11 — the "$0 here's-what-we'll-build" preview, computed only at the offer point, reusing
        # the SINGLE already-fetched `assess` (CRP R1-S1 — no second build_assess).
        preview = None
        if offerable:
            cascade = (assess or {}).get("cascade") or {}
            if cascade:
                preview = {"shape": cascade.get("shape"), "counts": cascade.get("status_counts")}

        base = RedCarpetState(
            stages=stages, next_stage=next_stage, cascade_offerable=offerable,
            unmet_gates=unmet, readiness_score=score, preview=preview,
        )
        # FR-RCA — the deterministic $0 prescriptive advisor (advisory-only, never a gate). Reuses the
        # single `assess` + the on-disk schema; degrades to no advice on any error.
        try:
            from .docs import live_schema_text
            from .red_carpet_advisor import build_playbook, cap_advisories, derive_advisories

            schema_text = live_schema_text(root)
            # FR-RCA-19 — cap to top-N but never drop the headline schema insight.
            advisories = cap_advisories(derive_advisories(root, base, assess, schema_text), _ADVISORY_CAP)
            # FR-RCA-20 — thread the already-fetched preview into the run step.
            next_steps = build_playbook(root, base, advisories, cap=_NEXTSTEP_CAP, preview=base.preview)
        except Exception:
            advisories, next_steps = (), ()

    # CRP R1-S3 — the whole build (assess + readiness + advisor) is timed against the readiness budget,
    # so a large schema parsed per turn cannot silently blow the "live surface must not freeze" budget.
    perf = PerfSample(
        phase="red_carpet", elapsed_ms=timer.elapsed_ms, budget_ms=BUDGET_INITIAL_MS
    ).to_dict()
    return replace(base, advisories=tuple(advisories), next_steps=tuple(next_steps), perf=perf)


def record_red_carpet_progress(
    prev: Optional[RedCarpetState], new: RedCarpetState
) -> None:
    """Emit the stage funnel on a transition (FR-RCT-14). Bounded attrs only (stage/status) — never
    interview text or paths. The per-input propose/apply is already covered by proposal_made/confirmed;
    this adds the conductor's stage-level progress + the cascade-offered moment."""
    from .telemetry import (
        EV_RED_CARPET_ADVICE,
        EV_RED_CARPET_CASCADE_OFFERED,
        EV_RED_CARPET_STAGE,
        emit,
    )

    if prev is None or prev.next_stage != new.next_stage:
        emit(EV_RED_CARPET_STAGE,
             stage=new.next_stage or "complete",
             status="done" if new.next_stage is None else "next")
    if new.cascade_offerable and (prev is None or not prev.cascade_offerable):
        emit(EV_RED_CARPET_CASCADE_OFFERED)
    # FR-RCA-16 — bounded advisory summary (numeric counts only; never advisory text/values/paths).
    advs = new.advisories or ()
    by_sev = {"error": 0, "warn": 0, "info": 0}
    by_kind = {"schema-shape": 0, "input-gap": 0, "input-invalid": 0,
               "cascade-blocker": 0, "provenance-review": 0, "stakeholder": 0}
    for a in advs:
        if a.severity in by_sev:
            by_sev[a.severity] += 1
        if a.kind in by_kind:
            by_kind[a.kind] += 1
    emit(EV_RED_CARPET_ADVICE,
         n_advisories=len(advs),
         n_error=by_sev["error"], n_warn=by_sev["warn"], n_info=by_sev["info"],
         n_next_steps=len(new.next_steps or ()),
         n_schema_shape=by_kind["schema-shape"], n_input_gap=by_kind["input-gap"],
         n_input_invalid=by_kind["input-invalid"], n_cascade_blocker=by_kind["cascade-blocker"],
         n_provenance_review=by_kind["provenance-review"], n_stakeholder=by_kind["stakeholder"])


def reflection_text(state: RedCarpetState) -> str:
    """The per-increment RETROSPECTIVE reflection (FR-RCT-12) — advisory, never a gate. What was
    decided, the next gap, what still blocks the build, and the friction escape hatch."""
    done = [s.key for s in state.stages if s.status == "done"]
    lines = ["Reflection (advisory):",
             f"  decided so far: {', '.join(done) if done else 'nothing yet'}"]
    if state.next_stage is None:
        lines.append("  the input surface is complete — the $0 cascade is offerable.")
    else:
        detail = next((s.detail for s in state.stages if s.key == state.next_stage), "")
        lines.append(f"  next gap: {state.next_stage} — {detail}")
    if not state.cascade_offerable and state.unmet_gates:
        lines.append(f"  still blocking the build: {', '.join(state.unmet_gates)}")
    # FR-RCA-13 — make the retrospective prescriptive: the top insight + the top few next steps
    # (with their commands). Advisory, never a gate; gated on presence.
    if state.advisories:
        top = state.advisories[0]  # already severity-sorted (error → warn → info)
        lines.append(f"  top insight [{top.severity}]: {top.title} — {top.detail}")
    if state.next_steps:
        lines.append("  next steps:")
        for step in state.next_steps[:3]:
            cmd = f"  ⟶  {step.command}" if step.command else ""
            lines.append(f"    {step.rank}. {step.title}{cmd}")
    lines.append("  if the kickoff grammar rejected something, you can log friction "
                 "(`startd8 kickoff concierge`).")
    return "\n".join(lines)


def prescriptive_banner(base_banner: str, state: RedCarpetState) -> str:
    """FR-RCA-21 — seed the agent loop's turn-0 banner with the top insight + top next step, so the
    user sees prescriptive guidance before the model calls a tool. Pure/testable."""
    lines = [base_banner]
    if state.advisories:
        a = state.advisories[0]
        lines.append(f"Top insight [{a.severity}]: {a.title} — {a.detail}")
    if state.next_steps:
        s = state.next_steps[0]
        lines.append(f"Start here: {s.title}" + (f"  ⟶  {s.command}" if s.command else ""))
    return "\n".join(lines)


# Inputs the driver treats as "end the session".
_QUIT_WORDS = frozenset({"", "exit", "quit", ":q", "q"})


def run_red_carpet_repl(
    *,
    banner: str,
    ask_sync: "Callable[[str], Any]",
    read_input: "Callable[[str], Optional[str]]",
    emit_line: "Callable[[str], None]",
    pending: "Callable[[], List[Any]]",
    on_proposal: "Callable[[Any], Optional[str]]",
    render_state: "Callable[[], None]" = lambda: None,
    cost_line: "Callable[[Any], str]" = lambda r: "",
    max_turns: int = 100,
) -> int:
    """Drive the Red Carpet interview loop — **pure** of the agent/IO so it is unit-testable.

    Each turn: read a user line → one agent turn (``ask_sync``) → for every pending proposal, hand it to
    ``on_proposal`` (the host confirms + applies/discards at human privilege, returning a short outcome
    line or ``None``) → re-render the staged state. The loop never applies a write itself: ``on_proposal``
    is the sole human-privilege seam. Returns the number of completed turns.
    """
    emit_line(banner)
    render_state()
    turns = 0
    while turns < max_turns:
        message = read_input("you> ")
        if message is None or message.strip().lower() in _QUIT_WORDS:
            break
        result = ask_sync(message)
        emit_line(getattr(result, "text", str(result)))
        line = cost_line(result)
        if line:
            emit_line(line)
        for action in list(pending()):
            outcome = on_proposal(action)   # host: confirm → apply_proposal (or discard); pops the buffer
            if outcome:
                emit_line(outcome)
        render_state()
        turns += 1
    return turns
