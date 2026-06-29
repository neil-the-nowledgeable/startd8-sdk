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

PROPOSAL_KINDS = ("instantiate", "friction", "capture", "schema", "manifest")

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
        if self.kind == "schema":
            ack = " (acknowledging contract drift)" if p.get("acknowledge_drift") else ""
            return (f"derive + promote the data-model contract → {p.get('contract_path', 'prisma/schema.prisma')}{ack}\n"
                    "    (from the confirmed requirements brief; gated round-trip + parity)")
        if self.kind == "manifest":
            rep = " (replacing existing)" if p.get("replace") else ""
            return (f"author the assembly manifest(s) from {p.get('source_label', 'authoring.md')}{rep}\n"
                    "    (extracted + round-trip-gated; written to their conventional prisma/ paths)")
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
            elif kind == "capture":
                vp = args.get("value_path", "") or ""
                val = str(args.get("value", ""))
                # Full validation + propose-time base_sha via a trial plan (allow-list, round-trip).
                plan = build_capture_plan(root, vp, val, config=cfg)
                action = ProposedAction("capture", {"value_path": vp, "value": val},
                                        id=_new_id(), base_sha=plan.base_sha)
            elif kind == "schema":  # RCT N2 — propose-time is lenient; the full emit/gate runs at apply (R1-F11)
                brief = args.get("brief", "") or ""
                if not brief.strip():
                    raise ConciergeInputError(
                        "missing_brief", "a requirements brief is required to derive the schema")
                action = ProposedAction(
                    "schema",
                    {"brief": brief,
                     "contract_path": args.get("contract_path", "prisma/schema.prisma"),
                     "acknowledge_drift": bool(args.get("acknowledge_drift", False))},
                    id=_new_id())
            else:  # manifest (RCT N1) — prose only; extraction + dest mapping happen at apply (R1-F2/F11)
                src = args.get("source", "") or ""
                if not src.strip():
                    raise ConciergeInputError(
                        "missing_source", "authoring prose is required for a manifest proposal")
                action = ProposedAction(
                    "manifest",
                    {"source": src, "source_label": args.get("source_label", "authoring.md"),
                     "replace": bool(args.get("replace", False))},
                    id=_new_id())
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
    # R1-F1/S1 — the closed apply-side allow-list FLOOR (the security invariant every Red Carpet
    # proposal kind rides): reject any kind outside PROPOSAL_KINDS *before* any write path. This is the
    # single source of truth shared with the propose handler, so a future RCT kind (e.g. `schema`,
    # `manifest`) cannot become a loop-reachable write until it is BOTH added here AND given an explicit
    # apply branch below.
    if action.kind not in PROPOSAL_KINDS:
        return ProposalOutcome(action.kind, "unknown_kind", f"unknown proposal kind {action.kind!r}")
    # Explicit kind dispatch (a malformed/unknown ProposedAction returns a typed outcome, never a
    # KeyError — apply_proposal is a public entry point). Params accessed defensively.
    p = action.params or {}

    if action.kind == "instantiate":
        posture = p.get("posture", "prototype")
        try:
            validate_posture(posture)  # R1-S4: re-validate at confirm
        except ConciergeInputError as exc:
            return ProposalOutcome("instantiate", exc.code, str(exc))
        res = apply_concierge_plan(root, build_instantiate_plan(root, posture))
        detail = f"{len(res.written)} written, {len(res.skipped)} skipped"
        return ProposalOutcome("instantiate", res.code,
                               detail + (f" — {res.message}" if res.message else ""))

    if action.kind == "friction":
        try:
            validate_friction(p.get("friction", ""), p.get("what_happened", ""),
                              p.get("implication", ""))
        except ConciergeInputError as exc:
            return ProposalOutcome("friction", exc.code, str(exc))
        plan = build_friction_entry(root, friction=p["friction"], what_happened=p["what_happened"],
                                    implication=p["implication"],
                                    timestamp=datetime.now(timezone.utc).isoformat())
        res = apply_concierge_plan(root, plan)
        return ProposalOutcome("friction", res.code, res.message or "")

    if action.kind == "schema":
        return _apply_schema(root, p)

    if action.kind == "manifest":
        return _apply_manifest(root, p)

    if action.kind == "capture":
        vp = p.get("value_path", "")
        if vp not in cfg.allowed_value_paths():  # R1-S4: allow-list may have changed since propose
            return ProposalOutcome("capture", CaptureCode.VALUE_PATH_NOT_ALLOWED,
                                   f"{vp} is no longer a capturable field")
        try:
            plan = build_capture_plan(root, vp, str(p.get("value", "")), config=cfg)
            # R1-F1: enforce the stale-file guard against the PROPOSE-time sha, not the confirm read.
            if action.base_sha is not None:
                plan = dataclasses.replace(plan, base_sha=action.base_sha)
            apply_capture(root, plan)
            return ProposalOutcome("capture", CaptureCode.OK, f"{vp} set")
        except CaptureError as exc:
            return ProposalOutcome("capture", exc.code, str(exc))

    return ProposalOutcome(action.kind, "unknown_kind", f"unknown proposal kind {action.kind!r}")


def _apply_schema(root: str, p: Dict[str, Any]) -> ProposalOutcome:
    """RCT N2 — derive + promote the data-model contract from the confirmed requirements brief.

    The `schema` kind is the SECOND ratification gate (FR-RCT-4): brief-confirm wrote no `.prisma`;
    this apply runs the existing `$0` `generate contract` pipeline (build_entity_graph → gated
    emit_schema_draft → promote_schema) at human privilege, then **only promotes when the gate passes**:
    - structural error / no round-trip  → `schema_gate_failed` (no write),
    - dropped (unrenderable) fields      → `schema_lossy` (no write, R1-F12 — never promote a lossy schema),
    - parity drift vs a live contract    → `schema_drift` unless `acknowledge_drift` (FR-RCT-16 — a
      revision after manifests may derive from the prior contract is blocked, not silent).
    """
    import tempfile

    from ..manifest_extraction.extract import build_entity_graph
    from ..manifest_extraction.prisma_emitter import emit_schema_draft, promote_schema

    brief = (p.get("brief") or "").strip()
    if not brief:
        return ProposalOutcome("schema", "missing_brief", "no requirements brief to derive from")
    rel_contract = p.get("contract_path", "prisma/schema.prisma")
    target = Path(root) / rel_contract
    live = target.read_text(encoding="utf-8") if target.is_file() else None

    graph = build_entity_graph({"requirements.md": brief})
    run_dir = tempfile.mkdtemp(prefix="startd8-rct-schema-")
    res = emit_schema_draft(graph, run_dir, live_text=live, source_file=rel_contract)

    if not res.round_trips or res.errors:                       # R1-F12 — never promote a broken schema
        return ProposalOutcome("schema", "schema_gate_failed",
                               "; ".join(res.errors) or "schema did not round-trip; not promoted")
    if res.unrenderable:                                        # R1-F12 — never promote a lossy schema
        return ProposalOutcome("schema", "schema_lossy",
                               "brief declares fields the contract can't express (not promoted): "
                               + ", ".join(map(str, res.unrenderable)))
    if res.parity_drift and not p.get("acknowledge_drift"):     # FR-RCT-16 — block silent revision
        return ProposalOutcome("schema", "schema_drift",
                               f"would change the live contract ({len(res.parity_drift)} drift) — "
                               "re-confirm with acknowledge_drift to proceed: "
                               + "; ".join(map(str, res.parity_drift[:3])))
    promote_schema(run_dir, str(target))                        # the sole `.prisma` write (FR-RCT-4)
    return ProposalOutcome("schema", ConciergeWriteCode.OK, f"promoted {rel_contract}")


def _apply_manifest(root: str, p: Dict[str, Any]) -> ProposalOutcome:
    """RCT N1 — materialize an authoring prose source's extracted manifest(s) into the project tree.

    The proposal supplies **prose, never a path** (R1-F2): the server extracts (round-trip-gated =
    apply-time re-validation, R1-F11) and maps each yielded manifest to its **server-derived**
    `CONVENTION_PATHS` destination — a payload-supplied `dest`/`path` is ignored. No-clobber by default;
    `replace` overwrites; the multi-file write is **all-or-nothing** via a pre-flight (R1-F3).
    """
    from ..concierge.safe_write import ACTION_NEW, ACTION_OVERWRITE, PlannedWrite, apply_write_plan
    from ..manifest_extraction.extract import RoundTripError, extract_manifests
    from ..wireframe.inputs import CONVENTION_PATHS

    source = (p.get("source") or "").strip()
    if not source:
        return ProposalOutcome("manifest", "missing_source", "no authoring prose to extract from")
    replace = bool(p.get("replace", False))
    rootp = Path(root)

    live = None
    schema = rootp / CONVENTION_PATHS["schema"]
    if schema.is_file():                                  # views/fk resolution needs the live contract
        live = schema.read_text(encoding="utf-8")
    try:
        result = extract_manifests({p.get("source_label", "authoring.md"): source}, live_schema_text=live)
    except RoundTripError as exc:                         # R1-F11 — extraction is the apply-time gate
        return ProposalOutcome("manifest", "manifest_round_trip_failed", str(exc))

    if not result.manifests:
        return ProposalOutcome("manifest", "no_manifest",
                               "the prose yielded no recognized assembly-manifest section")

    # Map each yielded manifest → its server-derived, confined dest (R1-F2). The proposal cannot
    # choose a path: an unknown manifest (no convention dest) is refused.
    targets: List[tuple] = []
    for filename, text in result.manifests.items():
        key = filename[:-5] if filename.endswith(".yaml") else filename
        dest = CONVENTION_PATHS.get(key)
        if dest is None:
            return ProposalOutcome("manifest", "unknown_manifest",
                                   f"no confined destination for {filename!r}")
        targets.append((dest, text))

    # Pre-flight all-or-nothing (R1-F3): refuse the WHOLE batch if any target would clobber, rather
    # than leave a partial materialization. (apply_write_plan is per-file, not transactional.)
    if not replace:
        clashes = sorted(dest for dest, _ in targets if (rootp / dest).exists())
        if clashes:
            return ProposalOutcome("manifest", "would_clobber",
                                   "exists (re-confirm with replace=true): " + ", ".join(clashes))

    act = ACTION_OVERWRITE if replace else ACTION_NEW
    planned = [PlannedWrite(path=dest, action=act, content=text) for dest, text in targets]
    res = apply_write_plan(root, planned, force=replace)
    if res.ok and len(res.written) == len(planned):
        return ProposalOutcome("manifest", ConciergeWriteCode.OK,
                               f"wrote {', '.join(sorted(res.written))}")
    issues = res.blocked + res.skipped + res.errors      # confinement re-check / OS error → no silent partial
    code = ConciergeWriteCode.PARTIAL if res.written else "manifest_refused"
    return ProposalOutcome("manifest", code, f"wrote {len(res.written)}/{len(planned)}; {issues}")
