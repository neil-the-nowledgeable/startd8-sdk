"""Agentic Concierge — proposals (the propose→human-confirm→apply handoff).

The agentic loop **never writes**. It calls a read-effect ``propose_action`` tool whose handler
records a typed :class:`ProposedAction` into a host-owned :class:`ProposalBuffer` (in memory, no
disk). After the turn the host shows pending proposals; on an explicit human confirm the host calls
:func:`apply_proposal`, which **re-validates against live state** and applies through the existing
typed write path. The loop is not in the apply path.

CRP-R1 corrections baked in:
- **base_sha at propose time (R1-F1):** for a `capture` proposal the target file's sha is captured
  when proposed, so `apply_capture`'s stale-file guard still fires if the file changes in the
  propose→confirm window (a confirm-time-only read would make the guard vacuous).
- **confirm-time re-validation (R1-S4):** posture / value-path allow-list are re-checked at apply.
- **non-atomic outcomes (R1-F2/S3):** instantiate can return `PARTIAL` / `WRITE_REFUSED`; the outcome
  is typed and the proposal is retained for an idempotent resume.
- **pop on terminal success only (R1-F5/S2):** a retriable failure retains the proposal (no
  double-write, no silent loss); validation/refusal discards it.
- **no silent eviction mid-turn (R1-S5):** the buffer rejects a new proposal when full rather than
  evicting an undrained one.
"""

from __future__ import annotations

import dataclasses
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .capture import CaptureCode, CaptureError, apply_capture, build_capture_plan
from .concierge_apply import (
    ConciergeInputError,
    ConciergeWriteCode,
    apply_concierge_plan,
    validate_friction,
    validate_posture,
)
from .manifest import KickoffExperienceConfig, default_config

PROPOSAL_KINDS = ("instantiate", "friction", "capture")

# Outcomes that keep the proposal pending (user can retry / resume) vs consume it.
_RETRIABLE_CODES = frozenset({CaptureCode.STALE_FILE, ConciergeWriteCode.WRITE_BLOCKED,
                              ConciergeWriteCode.PARTIAL})
_TERMINAL_SUCCESS = frozenset({ConciergeWriteCode.OK, ConciergeWriteCode.SKIPPED, CaptureCode.OK})


class BufferFull(RuntimeError):
    """The pending-proposal buffer is full (the human must confirm/discard before more — R1-S5)."""


def _new_id() -> str:
    return secrets.token_urlsafe(8)


@dataclass(frozen=True)
class ProposedAction:
    """A recommendation the loop emits — params only, never a prebuilt plan (OQ-7)."""

    kind: str
    params: Dict[str, Any]
    id: str
    base_sha: Optional[str] = None   # capture: the target file's sha at PROPOSE time (R1-F1)

    def summary(self) -> str:
        """A human-readable, **verbatim** summary for the confirm prompt (R1-F4 for friction)."""
        p = self.params
        if self.kind == "friction":
            return ("log friction —\n"
                    f"    friction:      {p.get('friction', '')}\n"
                    f"    what_happened: {p.get('what_happened', '')}\n"
                    f"    implication:   {p.get('implication', '')}")
        if self.kind == "instantiate":
            return f"instantiate the kickoff package (posture={p.get('posture', 'prototype')})"
        if self.kind == "capture":
            return f"set {p.get('value_path')} = {p.get('value')!r}"
        return f"{self.kind} {p}"


@dataclass(frozen=True)
class ProposalOutcome:
    """The result of applying a confirmed proposal — the host renders this (FR-AC-9 structural)."""

    kind: str
    code: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.code in _TERMINAL_SUCCESS

    @property
    def retriable(self) -> bool:
        return self.code in _RETRIABLE_CODES


class ProposalBuffer:
    """Bounded, host-owned buffer of pending proposals (FR-NEW-4). Rejects when full (R1-S5)."""

    _MAX = 32

    def __init__(self) -> None:
        self._items: List[ProposedAction] = []

    def add(self, action: ProposedAction) -> None:
        if len(self._items) >= self._MAX:
            raise BufferFull(f"at most {self._MAX} pending proposals; confirm or discard first")
        self._items.append(action)

    def pending(self) -> List[ProposedAction]:
        return list(self._items)

    def pop(self, action_id: str) -> None:
        self._items = [a for a in self._items if a.id != action_id]

    def __len__(self) -> int:
        return len(self._items)


# --- propose handler (read-effect; records, never writes) --------------------------------------


def make_propose_handler(
    project_root: str | Path,
    buffer: ProposalBuffer,
    *,
    config: Optional[KickoffExperienceConfig] = None,
) -> Callable[[dict], str]:
    """Build the `propose_action` tool handler: validate by kind, record, return a tiny ack."""
    cfg = config or default_config()
    root = str(project_root)

    def handler(args: dict) -> str:
        kind = (args.get("kind") or "").strip()
        if kind not in PROPOSAL_KINDS:
            return f"error: unknown proposal kind {kind!r}; one of {PROPOSAL_KINDS}"
        try:
            if kind == "friction":
                fr = args.get("friction", "") or ""
                wh = args.get("what_happened", "") or ""
                im = args.get("implication", "") or ""
                validate_friction(fr, wh, im)
                action = ProposedAction("friction",
                                        {"friction": fr, "what_happened": wh, "implication": im},
                                        id=_new_id())
            elif kind == "instantiate":
                posture = args.get("posture", "prototype") or "prototype"
                validate_posture(posture)
                action = ProposedAction("instantiate", {"posture": posture}, id=_new_id())
            else:  # capture
                vp = args.get("value_path", "") or ""
                val = str(args.get("value", ""))
                # Full validation + propose-time base_sha via a trial plan (allow-list, round-trip).
                plan = build_capture_plan(root, vp, val, config=cfg)
                action = ProposedAction("capture", {"value_path": vp, "value": val},
                                        id=_new_id(), base_sha=plan.base_sha)
        except (ConciergeInputError, CaptureError) as exc:
            return f"error: proposal rejected ({getattr(exc, 'code', 'invalid')}): {exc}"
        try:
            buffer.add(action)
        except BufferFull as exc:
            return f"error: {exc}"
        from .telemetry import EV_PROPOSAL_MADE, emit

        emit(EV_PROPOSAL_MADE, kind=action.kind)   # kind only — no free-text (privacy)
        return f"recorded a proposal for the user to confirm — {action.summary()}"

    return handler


# --- confirm-time apply (re-validate against live state; never called by the loop) -------------


def apply_proposal(
    project_root: str | Path,
    action: ProposedAction,
    *,
    config: Optional[KickoffExperienceConfig] = None,
) -> ProposalOutcome:
    """Apply a human-confirmed proposal through the existing typed write path. Re-validates live."""
    from ..concierge.writes import build_friction_entry, build_instantiate_plan

    cfg = config or default_config()
    root = str(project_root)
    outcome = _apply_proposal_inner(root, action, cfg, build_instantiate_plan, build_friction_entry)
    from .telemetry import EV_PROPOSAL_CONFIRMED, emit

    emit(EV_PROPOSAL_CONFIRMED, kind=outcome.kind, code=outcome.code)   # kind/code only
    return outcome


def _apply_proposal_inner(root, action, cfg, build_instantiate_plan, build_friction_entry):

    if action.kind == "instantiate":
        posture = action.params["posture"]
        try:
            validate_posture(posture)  # R1-S4: re-validate at confirm
        except ConciergeInputError as exc:
            return ProposalOutcome("instantiate", exc.code, str(exc))
        res = apply_concierge_plan(root, build_instantiate_plan(root, posture))
        detail = f"{len(res.written)} written, {len(res.skipped)} skipped"
        return ProposalOutcome("instantiate", res.code, detail + (f" — {res.message}" if res.message else ""))

    if action.kind == "friction":
        p = action.params
        try:
            validate_friction(p["friction"], p["what_happened"], p["implication"])
        except ConciergeInputError as exc:
            return ProposalOutcome("friction", exc.code, str(exc))
        plan = build_friction_entry(root, friction=p["friction"], what_happened=p["what_happened"],
                                    implication=p["implication"],
                                    timestamp=datetime.now(timezone.utc).isoformat())
        res = apply_concierge_plan(root, plan)
        return ProposalOutcome("friction", res.code, res.message or "")

    # capture
    vp = action.params["value_path"]
    if vp not in cfg.allowed_value_paths():  # R1-S4: allow-list may have changed since propose
        return ProposalOutcome("capture", CaptureCode.VALUE_PATH_NOT_ALLOWED,
                               f"{vp} is no longer a capturable field")
    try:
        plan = build_capture_plan(root, vp, action.params["value"], config=cfg)
        # R1-F1: enforce the stale-file guard against the PROPOSE-time sha, not the confirm-time read.
        if action.base_sha is not None:
            plan = dataclasses.replace(plan, base_sha=action.base_sha)
        apply_capture(root, plan)
        return ProposalOutcome("capture", CaptureCode.OK, f"{vp} set")
    except CaptureError as exc:
        return ProposalOutcome("capture", exc.code, str(exc))
