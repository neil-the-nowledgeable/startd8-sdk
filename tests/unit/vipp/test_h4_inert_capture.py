"""FR-H4 regression: a `capture` of an `<Entity>.<field>` value-path was adjudicated ACCEPT[VALIDATED]
at negotiate but refused `value_path_not_allowed` by the apply floor — a dishonest `wrote 1/2` split.

Client friction (household-o11y, envelope_seq 1): `Chore.name` is a real project field, so negotiate
VALIDATED and ACCEPTed it, but the kickoff apply floor's allow-list is config-YAML value-paths
(`conventions.yaml#/language`) — a different namespace (NR-4: we do NOT widen it). The fix predicts
the floor at negotiate (ACCEPT-but-inert, carrying the SAME typed CaptureCode) and excludes the inert
proposal from both apply's actionable count and preview's would-apply set.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.capture import CaptureCode
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction
from startd8.sapper.ground_truth import GroundTruthAnswer, GroundTruthVerdict
from startd8.vipp import context, evaluate
from startd8.vipp.apply import apply_dispositions, preview_dispositions
from startd8.vipp.assistant import DISPOSITIONS_JSON
from startd8.vipp.models import (
    ClaimLabel,
    Decision,
    EnvelopedProposal,
    LabeledClaim,
    ProposalEnvelope,
    VippDisposition,
    VippReport,
)


class _ScriptedOracle:
    def __init__(self, by_symbol):
        self._by = by_symbol

    def answer(self, question):
        return self._by[question.symbol]


def _envelope(proposals, *, seq=1):
    return ProposalEnvelope(project_id="proj-1", envelope_seq=seq, proposals=proposals)


# --- negotiate: entity.field capture → ACCEPT-but-inert ---------------------------------------- #

def test_validated_entity_field_capture_is_accept_but_inert():
    env = _envelope([
        EnvelopedProposal(kind="capture", params={"value_path": "Chore.name", "value": "x"}, id="p_ok"),
    ])
    oracle = _ScriptedOracle(
        {"Chore.name": GroundTruthAnswer(GroundTruthVerdict.VALIDATED, evidence="exists")}
    )
    disp = evaluate.evaluate_envelope(env, oracle)[0]
    # Still an ACCEPT (the field IS real), but inert — carries the SAME code the apply floor raises,
    # so the disposition no longer over-promises a write apply will refuse.
    assert disp.decision is Decision.ACCEPT
    assert any(c.qualifier == CaptureCode.VALUE_PATH_NOT_ALLOWED for c in disp.claims)


# --- apply + preview parity ------------------------------------------------------------------- #

def _proj(tmp_path) -> Path:
    proj = Path(os.path.realpath(tmp_path))
    (proj / ".startd8" / "vipp").mkdir(parents=True)
    return proj


def _inert_disposition(seq):
    return VippDisposition(
        proposal_id="p_inert", decision=Decision.ACCEPT, envelope_seq=seq,
        claims=[LabeledClaim(
            label=ClaimLabel.OBSERVED, text="inert", source="vipp:value-path-not-allowed",
            claim_id="p_inert", qualifier=CaptureCode.VALUE_PATH_NOT_ALLOWED,
        )],
    )


def _setup(proj):
    buf = ProposalBuffer()
    buf.add(ProposedAction(kind="capture", params={"value_path": "Chore.name", "value": "x"}, id="p_inert"))
    seam.serialize_buffer(buf, proj)
    seq = seam.read_inbox(proj)["envelope_seq"]
    report = VippReport(project_id="p", envelope_seq=seq, dispositions=[_inert_disposition(seq)])
    (context.vipp_dir(proj) / DISPOSITIONS_JSON).write_text(json.dumps(report.to_dict()), encoding="utf-8")
    return seq


def test_preview_excludes_inert_from_would_apply(tmp_path):
    proj = _proj(tmp_path)
    _setup(proj)
    result = preview_dispositions(proj)
    assert result.would_apply == []  # inert capture must not appear in the preview


def test_apply_reports_inert_not_a_failed_write(tmp_path):
    proj = _proj(tmp_path)
    _setup(proj)
    result = apply_dispositions(proj, confirm=lambda a, d: True)
    assert result.actionable == 0            # NOT counted as an actionable write (no `wrote 0/1`)
    assert result.wrote == 0
    codes = [o.get("code") for o in result.outcomes]
    assert CaptureCode.VALUE_PATH_NOT_ALLOWED in codes  # visible as inert, not a silent partial
