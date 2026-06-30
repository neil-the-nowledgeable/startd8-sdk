# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M6 security + observability tests (FR-9/12/14/17).

- FR-9 authority-spoof: VIPP only ever mints OBSERVED(project) claims — it cannot forge MECHANISM(sdk)
  authority (the narrator-fence is tested in test_negotiate).
- FR-9 inbound floor: a malicious inbox (path-traversal capture) is refused at apply by the host floor.
- FR-12: a capture COUNTER amends only the value-path — it never authors bucket-4 prose.
- FR-14: project_id propagates serialize → report and is the EventBus correlation (join) key.
- FR-17: a real EventBus event fires per negotiation, carrying counts + project_id and NO free-text.
"""

from __future__ import annotations

import os
from pathlib import Path

from startd8.events import EventBus, EventType
from startd8.fde.models import ClaimLabel
from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction
from startd8.sapper.ground_truth import GroundTruthAnswer, GroundTruthVerdict
from startd8.vipp import apply_dispositions, evaluate, run_vipp_negotiate
from startd8.vipp.models import Decision, EnvelopedProposal, ProposalEnvelope

YES = lambda action, disp: True  # noqa: E731


def _proj(tmp_path) -> Path:
    proj = Path(os.path.realpath(tmp_path))
    (proj / ".startd8" / "vipp").mkdir(parents=True)
    return proj


class _ScriptedOracle:
    def __init__(self, by_symbol):
        self._by = by_symbol

    def answer(self, question):
        return self._by.get(question.symbol) or GroundTruthAnswer.omit("unscripted")


# --- FR-9: VIPP cannot forge SDK-mechanism authority ----------------------------------------------


def test_vipp_only_mints_observed_claims_never_mechanism():
    env = ProposalEnvelope(
        project_id="p",
        envelope_seq=1,
        proposals=[
            EnvelopedProposal(kind="capture", params={"value_path": "A.b"}, id="v"),
            EnvelopedProposal(kind="capture", params={"value_path": "A.c"}, id="r"),
            EnvelopedProposal(
                kind="instantiate", params={"posture": "prototype"}, id="i"
            ),
        ],
    )
    oracle = _ScriptedOracle(
        {
            "A.b": GroundTruthAnswer(GroundTruthVerdict.VALIDATED, evidence="exists"),
            "A.c": GroundTruthAnswer(GroundTruthVerdict.REFUTED, evidence="nope"),
        }
    )
    for disp in evaluate.evaluate_envelope(env, oracle):
        for claim in disp.claims:
            # OBSERVED only — never MECHANISM(sdk)/PREDICTION (no authority spoof, R3-F3/C-F3).
            assert claim.label is ClaimLabel.OBSERVED


def test_malicious_path_traversal_capture_is_refused_at_apply(tmp_path):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(
        ProposedAction(
            kind="capture",
            params={"value_path": "../../../etc/passwd", "value": "x"},
            id="evil",
        )
    )
    seam.serialize_buffer(buf, proj)
    run_vipp_negotiate(seam.inbox_path(proj), project_root=proj, emit=False)

    res = apply_dispositions(proj, confirm=YES)

    # VIPP may OMIT-default ACCEPT it, but the apply floor (allowed_value_paths) refuses the write.
    assert res.wrote == 0
    assert res.outcomes[0]["ok"] is False
    assert not (
        proj.parent.parent / "etc" / "passwd"
    ).exists()  # nothing escaped the project


# --- FR-12: a COUNTER never authors bucket-4 prose ------------------------------------------------


def test_capture_counter_amends_only_value_path_never_invents_prose():
    env = ProposalEnvelope(
        project_id="p",
        envelope_seq=1,
        proposals=[
            EnvelopedProposal(
                kind="capture", params={"value_path": "P.headlne", "value": "x"}, id="c"
            )
        ],
    )
    oracle = _ScriptedOracle(
        {
            "P.headlne": GroundTruthAnswer(
                GroundTruthVerdict.REFUTED,
                evidence="closest is 'headline'",
                source="project_knowledge.field_sets",
            )
        }
    )
    disp = evaluate.evaluate_envelope(env, oracle)[0]
    assert disp.decision is Decision.COUNTER
    # counter_params carries ONLY the original inbox keys (value_path corrected) — no invented prose.
    assert set(disp.counter_params) <= {"value_path", "value"}
    assert disp.counter_params["value"] == "x"  # preserved verbatim


# --- FR-14: project_id propagation + join key -----------------------------------------------------


def test_project_id_propagates_serialize_to_report(tmp_path):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(
        ProposedAction(kind="instantiate", params={"posture": "prototype"}, id="p1")
    )
    seam.serialize_buffer(buf, proj, project_id="proj-XYZ")

    out = run_vipp_negotiate(seam.inbox_path(proj), project_root=proj, emit=False)
    assert out.report.project_id == "proj-XYZ"


# --- FR-17: real EventBus event, counts + project_id, no free-text --------------------------------


def test_eventbus_negotiate_complete_has_counts_and_no_free_text(tmp_path):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(
        ProposedAction(kind="instantiate", params={"posture": "prototype"}, id="p1")
    )
    seam.serialize_buffer(buf, proj, project_id="proj-XYZ")

    received = []
    EventBus.subscribe(EventType.VIPP_NEGOTIATE_COMPLETE, received.append)
    try:
        run_vipp_negotiate(seam.inbox_path(proj), project_root=proj, emit=True)
    finally:
        EventBus._listeners.pop(EventType.VIPP_NEGOTIATE_COMPLETE, None)

    assert received, "no VIPP_NEGOTIATE_COMPLETE event received"
    ev = received[-1]
    assert ev.source == "vipp"
    assert ev.correlation_id == "proj-XYZ"  # FR-14 join key
    assert set(ev.data) == {
        "project_id",
        "envelope_seq",
        "counts",
        "cost_usd",
        "llm_used",
        "report",
    }
    assert ev.data["counts"]["ACCEPT"] == 1
    # privacy posture: no claim text / reasons in the telemetry payload (FR-17, no free-text).
    assert (
        "claims" not in ev.data
        and "reason" not in ev.data
        and "dispositions" not in ev.data
    )
