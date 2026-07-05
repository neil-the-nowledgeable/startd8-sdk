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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

from ..fde.ratification import RatificationError, assert_ratifiable
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
