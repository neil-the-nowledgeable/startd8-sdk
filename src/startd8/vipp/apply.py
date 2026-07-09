# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Provenance-pinned applier (FR-5/10/16/18) — applies VIPP dispositions at PROJECT human privilege.

Reads the trusted host **inbox** (the FR-15 seam) and the VIPP **dispositions** report, joins them by
``proposal_id``, and applies each ACCEPT (and confirmed COUNTER) through the host's
``apply_proposal`` floor (`proposals.py:217`) — never ``apply_write_plan`` directly.

The load-bearing rule (CRP R1 R3-F2/S1) is **provenance pinning**: an ACCEPT's ``kind``/``params``/
``base_sha`` are taken from the **trusted inbox entry**, *not* from the disposition; a COUNTER overlays
only its explicitly amended params, and **never** ``base_sha`` or ``kind`` (else a tampered disposition
could disable the capture stale-file guard). The human-``confirm`` callback is the **sole content gate**
(FR-10/16) — no write happens without it, and it is handed the reconstructed action whose ``summary()``
renders the concrete content. apply_proposal's per-kind re-validation is the mechanism backstop.

Lifecycle (FR-18): refuse when the dispositions' pinned ``envelope_seq`` ≠ the live inbox seq
(re-negotiate); a cursor keyed by ``proposal_id`` + ``envelope_seq`` makes apply idempotent;
terminal outcomes are consumed, **retriable** outcomes (`_RETRIABLE_CODES`) are retained for resume;
the inbox is **shredded** once every proposal is consumed (the dispositions report is kept as the
durable FR-17 audit). Reports ``wrote N/M``.

Dependency direction: ``vipp`` → ``kickoff_experience`` is sanctioned (FR-8); this module legitimately
imports ``ProposedAction``/``apply_proposal`` (the contract models avoid that — F-5 scoping).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

from ..fde.ratification import RatificationError, assert_ratifiable
from ..kickoff_experience.capture import CaptureCode
from ..kickoff_experience.proposals import ProposedAction, apply_proposal
from ..kickoff_experience.vipp_seam import read_inbox, shred_inbox
from ..logging_config import get_logger
from . import context
from .assistant import DISPOSITIONS_JSON
from .models import Decision, ProposalEnvelope, VippDisposition, VippReport, oneline

logger = get_logger(__name__)

# (action, disposition) -> approve? The CLI renders action.summary() / capture preview here (FR-16).
ConfirmFn = Callable[[ProposedAction, VippDisposition], bool]

# FR-GE-14 / FR-RW-2: the human ``confirm()`` IS the ratification act. This sentinel is the
# non-empty token handed to ``assert_ratifiable`` once (and only once) the human has confirmed —
# there is exactly one human content gate (NR-4), so a synthetic claim is ratified by that same
# confirmation, never by a second prompt.
_RATIFY_TOKEN = "vipp:human-confirm"


@dataclass
class ApplyResult:
    """Per-run apply report (FR-18 partial-failure contract)."""

    wrote: int = 0  # terminal successes this run
    actionable: int = 0  # ACCEPT + COUNTER dispositions encountered
    outcomes: List[dict] = field(
        default_factory=list
    )  # per-proposal {proposal_id,decision,code,...}
    stale: bool = False
    refused_reason: str = ""
    inbox_shredded: bool = False

    def summary(self) -> str:
        if self.refused_reason:
            return f"refused: {self.refused_reason}"
        return f"wrote {self.wrote}/{self.actionable} actionable disposition(s)"


def _reconstruct(enveloped: Any, disposition: VippDisposition) -> ProposedAction:
    """Build the action to apply — provenance-pinned to the TRUSTED inbox entry (R3-F2)."""
    params = dict(enveloped.params or {})
    if disposition.decision is Decision.COUNTER and disposition.counter_params:
        amended = dict(disposition.counter_params)
        amended.pop("kind", None)  # kind is never VIPP-amendable
        amended.pop("base_sha", None)  # base_sha is never VIPP-amendable
        params.update(amended)
    # kind + base_sha ALWAYS from the inbox; only params may carry a COUNTER overlay.
    return ProposedAction(
        kind=enveloped.kind, params=params, id=enveloped.id, base_sha=enveloped.base_sha
    )


def _is_inert(disposition: VippDisposition) -> bool:
    """FR-H4b: an ACCEPT-but-inert `capture` (value_path validated as a project field but not a
    kickoff-writable value-path, FR-H4a) carries the `value_path_not_allowed` qualifier from
    negotiate. The apply floor would refuse it (reading as a `wrote 1/2` silent partial) and the
    preview would over-promise it — so both `apply_dispositions` and `preview_dispositions` treat it
    like a REJECT for write purposes: not attempted, not counted actionable, not in would-apply."""
    return disposition.decision is Decision.ACCEPT and any(
        getattr(c, "qualifier", "") == CaptureCode.VALUE_PATH_NOT_ALLOWED
        for c in (disposition.claims or [])
    )


@dataclass
class PreviewResult:
    """Side-effect-free preview of what :func:`apply_dispositions` WOULD write (FR-R7 preview half)."""

    envelope_seq: int = 0
    # each: {proposal_id, kind, params, value_path} — the reconstructed, provenance-pinned action
    would_apply: List[dict] = field(default_factory=list)
    content_hash: str = ""  # canonical hash of {seq + would-apply set} — the challenge binds this
    stale: bool = False
    refused_reason: str = ""

    def summary(self) -> str:
        if self.refused_reason:
            return f"nothing to apply: {self.refused_reason}"
        return f"{len(self.would_apply)} proposal(s) would apply at seq {self.envelope_seq}"


def _content_hash(seq: int, would_apply: List[dict]) -> str:
    """Canonical, order-independent hash of the would-apply set — the FR-R7 challenge content binding."""
    items = sorted(
        ({"proposal_id": w["proposal_id"], "kind": w["kind"], "params": w["params"]} for w in would_apply),
        key=lambda x: x["proposal_id"],
    )
    canonical = json.dumps({"seq": seq, "items": items}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def preview_dispositions(project_root: Any) -> PreviewResult:
    """Reconstruct the would-apply set **purely** — the read-only half of the M-apply gate (FR-R7).

    Mirrors :func:`apply_dispositions`' actionable-selection but performs **zero writes**: it never
    calls ``record_processed`` or ``shred_inbox``, so ``vipp-cursor.json`` + the inbox are byte-identical
    afterward (CRP F-1 — the v0.3 preview-via-``confirm→False`` recorded REJECTs as consumed and could
    shred the inbox on an all-REJECT report). Returns the would-apply set + a canonical content hash the
    ratify challenge binds to.
    """
    project_root = Path(project_root)

    raw_inbox = read_inbox(project_root)
    if raw_inbox is None:
        return PreviewResult(refused_reason="no inbox to apply")
    envelope = ProposalEnvelope.from_json(raw_inbox)

    json_path = context.vipp_dir(project_root) / DISPOSITIONS_JSON
    if not json_path.exists():
        return PreviewResult(refused_reason="no dispositions to apply")
    report = VippReport.from_json(json_path.read_text(encoding="utf-8"))

    # Same FR-18 stale-seq refusal apply_dispositions enforces — a stale preview must not be issued.
    if report.envelope_seq != envelope.envelope_seq:
        return PreviewResult(
            stale=True,
            envelope_seq=envelope.envelope_seq,
            refused_reason=(
                f"dispositions pin envelope_seq {report.envelope_seq} but the inbox is "
                f"seq {envelope.envelope_seq} — re-negotiate"
            ),
        )

    inbox_by_id = {p.id: p for p in envelope.proposals}
    seq = envelope.envelope_seq
    would_apply: List[dict] = []
    for disp in report.dispositions:
        # REJECT never writes (in the real applier it only records the cursor — a side effect we skip).
        if disp.decision is Decision.REJECT:
            continue
        # FR-H4b: an ACCEPT-but-inert capture would be refused by the apply floor — exclude it from
        # the would-apply set so preview and apply agree (preview must not over-promise it).
        if _is_inert(disp):
            continue
        # Everything else is actionable in apply_dispositions; mirror that exactly.
        key = f"apply:{disp.proposal_id}:{seq}"
        if context.already_processed(project_root, key, "consumed"):
            continue  # already applied under this seq — not in the would-apply set (read-only check)
        enveloped = inbox_by_id.get(disp.proposal_id)
        if enveloped is None:
            continue  # no matching inbox entry → can never apply under this seq
        action = _reconstruct(enveloped, disp)
        would_apply.append(
            {
                "proposal_id": disp.proposal_id,
                "kind": action.kind,
                "params": dict(action.params),
                "value_path": action.params.get("value_path"),
            }
        )

    return PreviewResult(
        envelope_seq=seq, would_apply=would_apply, content_hash=_content_hash(seq, would_apply)
    )


def apply_dispositions(
    project_root: Any,
    *,
    confirm: ConfirmFn,
    config: Optional[Any] = None,
    force: bool = False,
) -> ApplyResult:
    """Apply the VIPP dispositions for ``project_root`` at project human privilege."""
    project_root = Path(project_root)

    raw_inbox = read_inbox(project_root)
    if raw_inbox is None:
        return ApplyResult(refused_reason="no inbox to apply")
    envelope = ProposalEnvelope.from_json(raw_inbox)

    json_path = context.vipp_dir(project_root) / DISPOSITIONS_JSON
    if not json_path.exists():
        return ApplyResult(refused_reason="no dispositions to apply")
    report = VippReport.from_json(json_path.read_text(encoding="utf-8"))

    # FR-18 stale-seq refusal: the dispositions must pin the SAME seq as the live inbox.
    if report.envelope_seq != envelope.envelope_seq:
        return ApplyResult(
            stale=True,
            refused_reason=(
                f"dispositions pin envelope_seq {report.envelope_seq} but the inbox is "
                f"seq {envelope.envelope_seq} — re-negotiate"
            ),
        )

    inbox_by_id = {p.id: p for p in envelope.proposals}
    seq = envelope.envelope_seq
    result = ApplyResult()
    consumed_all = True

    for disp in report.dispositions:
        key = f"apply:{disp.proposal_id}:{seq}"
        rec: dict = {"proposal_id": disp.proposal_id, "decision": disp.decision.value}

        if context.already_processed(project_root, key, "consumed"):
            rec.update(code="already_consumed", ok=True)
            result.outcomes.append(rec)
            continue

        if disp.decision is Decision.REJECT:
            context.record_processed(
                project_root, key, "consumed", {"decision": "REJECT"}
            )
            rec.update(code="rejected_no_write", ok=True)
            result.outcomes.append(rec)
            continue

        # FR-H4b: ACCEPT-but-inert (value_path validated but not kickoff-writable) — the apply floor
        # would refuse it, so DON'T attempt it and DON'T count it actionable (that produced the
        # dishonest `wrote 1/2`). Record it consumed + inert so it neither wedges the shred nor reads
        # as a failed write.
        if _is_inert(disp):
            context.record_processed(
                project_root, key, "consumed", {"decision": "ACCEPT", "code": CaptureCode.VALUE_PATH_NOT_ALLOWED}
            )
            rec.update(
                code=CaptureCode.VALUE_PATH_NOT_ALLOWED, ok=True,
                detail="inert: value_path is not a kickoff-writable field (not attempted)",
            )
            result.outcomes.append(rec)
            continue

        # ACCEPT / COUNTER → actionable
        result.actionable += 1
        enveloped = inbox_by_id.get(disp.proposal_id)
        if enveloped is None:
            # A disposition with no matching inbox entry can NEVER become applicable under this seq
            # (a corrupted/hand-edited dispositions.json) — record it consumed so it does not wedge
            # the shred forever (code-review M1). Defense-in-depth behind the stale-seq guard.
            context.record_processed(
                project_root, key, "consumed", {"code": "no_inbox_entry"}
            )
            rec.update(code="no_inbox_entry", ok=False)
            result.outcomes.append(rec)
            continue

        action = _reconstruct(enveloped, disp)
        confirmed = confirm(
            action, disp
        )  # FR-16 sole content gate — no write without it

        # FR-GE-14 / FR-RW-1..3: a synthetic (panel-authored) claim may only cross into the
        # project's load-bearing store with an explicit human ratification — and the confirm()
        # above IS that ratification (FR-RW-2). Gate every claim; a synthetic one reaching here
        # unconfirmed (token absent) is refused as "unratified", not silently written. Non-synthetic
        # claims pass untouched, so all of today's oracle-sourced dispositions apply byte-identically
        # (FR-RW-4). RatificationError is caught here, never propagated (don't crash the loop).
        token = _RATIFY_TOKEN if confirmed else None
        try:
            for claim in disp.claims:
                assert_ratifiable(claim, ratification_token=token)
        except RatificationError as exc:
            rec.update(code="unratified", ok=False, detail=oneline(str(exc)))
            result.outcomes.append(rec)
            consumed_all = (
                False  # leave pending; a later confirmed (ratifying) run applies it
            )
            continue

        if not confirmed:
            rec.update(code="unconfirmed", ok=False)
            result.outcomes.append(rec)
            consumed_all = False  # human declined this round → leave pending for resume
            continue

        outcome = apply_proposal(project_root, action, config=config)
        rec.update(
            code=outcome.code,
            ok=outcome.ok,
            retriable=outcome.retriable,
            detail=outcome.detail,
        )
        result.outcomes.append(rec)

        if outcome.retriable:
            consumed_all = False  # retain for idempotent resume (FR-18)
        else:
            context.record_processed(
                project_root, key, "consumed", {"code": outcome.code}
            )
            if outcome.ok:
                result.wrote += 1

    # Shred the inbox once every proposal is consumed (FR-15); keep dispositions.json as the audit.
    if consumed_all and not force:
        result.inbox_shredded = shred_inbox(project_root)

    logger.info(
        "VIPP apply: %s (seq %s, shredded=%s)",
        result.summary(),
        seq,
        result.inbox_shredded,
    )
    return result
