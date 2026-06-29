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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

# Ordered build stages (FR-RCT-2): data model first (the front bookend), then the manifests that
# derive from it, then the value inputs, then placeholder content, then the cascade run.
STAGES: Tuple[str, ...] = ("data_model", "manifests", "value_inputs", "content", "run")

# The minimal viable subset that makes the $0 cascade offerable (FR-RCT-10 / CRP R1-F7):
# a confirmed schema + an app manifest + at least one page + at least one view.
_CASCADE_GATE_KEYS: Tuple[str, ...] = ("schema", "app", "pages", "views")


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

    def to_dict(self) -> dict:
        return {
            "stages": [{"key": s.key, "status": s.status, "detail": s.detail} for s in self.stages],
            "next_stage": self.next_stage,
            "cascade_offerable": self.cascade_offerable,
            "unmet_gates": list(self.unmet_gates),
            "readiness_score": self.readiness_score,
            "preview": self.preview,
        }


def _present(root: Path, key: str) -> bool:
    """A conventional manifest is present iff its file exists and is non-empty."""
    from ..wireframe.inputs import CONVENTION_PATHS

    target = root / CONVENTION_PATHS[key]
    return target.is_file() and target.stat().st_size > 0


def build_red_carpet_state(project_root: str | Path) -> RedCarpetState:
    """Compute the staged build state from ``build_assess`` + the on-disk manifests (read-only, ``$0``)."""
    from .readiness import build_readiness

    root = Path(project_root)
    gates = {k: _present(root, k) for k in _CASCADE_GATE_KEYS}
    unmet = tuple(k for k in _CASCADE_GATE_KEYS if not gates[k])
    offerable = not unmet

    # Value inputs (the 4 domains) + the readiness score, via the existing projection (never recomputed).
    try:
        readiness = build_readiness(root)
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
    # FR-RCT-11 — the "$0 here's-what-we'll-build" preview, computed only at the offer point (inputs
    # exist), reusing the wireframe machinery via build_assess's cascade view.
    preview = None
    if offerable:
        try:
            from ..concierge.core import build_assess

            cascade = (build_assess(root) or {}).get("cascade") or {}
            preview = {"shape": cascade.get("shape"), "counts": cascade.get("status_counts")}
        except Exception:
            preview = None
    return RedCarpetState(
        stages=stages, next_stage=next_stage, cascade_offerable=offerable,
        unmet_gates=unmet, readiness_score=score, preview=preview,
    )


def record_red_carpet_progress(
    prev: Optional[RedCarpetState], new: RedCarpetState
) -> None:
    """Emit the stage funnel on a transition (FR-RCT-14). Bounded attrs only (stage/status) — never
    interview text or paths. The per-input propose/apply is already covered by proposal_made/confirmed;
    this adds the conductor's stage-level progress + the cascade-offered moment."""
    from .telemetry import EV_RED_CARPET_CASCADE_OFFERED, EV_RED_CARPET_STAGE, emit

    if prev is None or prev.next_stage != new.next_stage:
        emit(EV_RED_CARPET_STAGE,
             stage=new.next_stage or "complete",
             status="done" if new.next_stage is None else "next")
    if new.cascade_offerable and (prev is None or not prev.cascade_offerable):
        emit(EV_RED_CARPET_CASCADE_OFFERED)


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
    lines.append("  if the kickoff grammar rejected something, you can log friction "
                 "(`startd8 kickoff concierge`).")
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
