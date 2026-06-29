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

    def to_dict(self) -> dict:
        return {
            "stages": [{"key": s.key, "status": s.status, "detail": s.detail} for s in self.stages],
            "next_stage": self.next_stage,
            "cascade_offerable": self.cascade_offerable,
            "unmet_gates": list(self.unmet_gates),
            "readiness_score": self.readiness_score,
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
            "value_inputs", "done" if value_inputs_done else "pending",
            "all four value-input domains present" if value_inputs_done
            else "fill conventions / build-preferences / business-targets / observability"),
        # Placeholder bucket-2 content is driven in a later increment; not gating the cascade offer.
        RedCarpetStage("content", "pending", "placeholder content + static test data (later)"),
        RedCarpetStage(
            "run", "done" if offerable else "pending",
            "the $0 cascade is offerable" if offerable
            else f"cascade not offerable — unmet: {', '.join(unmet)}"),
    )
    next_stage = next((s.key for s in stages if s.status != "done"), None)
    return RedCarpetState(
        stages=stages, next_stage=next_stage, cascade_offerable=offerable,
        unmet_gates=unmet, readiness_score=score,
    )


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
