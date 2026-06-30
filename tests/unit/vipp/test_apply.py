# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M4 provenance-pinned applier tests (FR-5/10/16/18).

Covers: the live two-process flow (serialize → negotiate → apply, B-S4); provenance pinning (ACCEPT/
COUNTER use the TRUSTED inbox kind/base_sha, a tampered disposition cannot override them, R3-F2);
REJECT/unconfirmed write nothing; unknown kind blocked by the floor; partial-failure consumes terminal
+ retains retriable + resumes; stale-seq refusal (FR-18).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.capture import CaptureCode
from startd8.kickoff_experience.concierge_apply import ConciergeWriteCode
from startd8.kickoff_experience.proposals import (
    ProposalBuffer,
    ProposalOutcome,
    ProposedAction,
)
from startd8.vipp import context
from startd8.vipp.apply import apply_dispositions
from startd8.vipp.assistant import DISPOSITIONS_JSON, run_vipp_negotiate
from startd8.vipp.models import Decision, ProposalEnvelope, VippDisposition, VippReport

YES = lambda action, disp: True  # noqa: E731 — terse confirm stub
NO = lambda action, disp: False  # noqa: E731


def _proj(tmp_path) -> Path:
    proj = Path(os.path.realpath(tmp_path))
    (proj / ".startd8" / "vipp").mkdir(parents=True)
    return proj


def _serialize(proj, buffer) -> int:
    seam.serialize_buffer(buffer, proj)
    return seam.read_inbox(proj)["envelope_seq"]


def _write_dispositions(proj, seq, dispositions) -> None:
    report = VippReport(project_id="p", envelope_seq=seq, dispositions=dispositions)
    (context.vipp_dir(proj) / DISPOSITIONS_JSON).write_text(
        json.dumps(report.to_dict()), encoding="utf-8"
    )


# --- the live two-process flow (B-S4) -------------------------------------------------------------


def test_live_serialize_negotiate_apply_friction(tmp_path):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(
        ProposedAction(
            kind="friction",
            params={"friction": "slow", "what_happened": "x", "implication": "y"},
            id="f1",
        )
    )
    seam.serialize_buffer(buf, proj)
    run_vipp_negotiate(seam.inbox_path(proj), project_root=proj, emit=False)

    res = apply_dispositions(proj, confirm=YES)

    assert res.actionable == 1 and res.wrote == 1
    assert res.inbox_shredded is True
    assert seam.read_inbox(proj) is None  # consumed
    assert (proj / "concierge-friction.jsonl").exists()  # real write happened


# --- provenance pinning (R3-F2) -------------------------------------------------------------------


def test_accept_uses_trusted_inbox_kind_and_base_sha_over_tampered_disposition(
    tmp_path, monkeypatch
):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(
        ProposedAction(
            kind="capture",
            params={"value_path": "Profile.headlne", "value": "x"},
            id="p1",
            base_sha="GOOD-SHA",
        )
    )
    seq = _serialize(proj, buf)
    # A tampered disposition trying to escalate kind/base_sha and rename the field.
    _write_dispositions(
        proj,
        seq,
        [
            VippDisposition(
                proposal_id="p1",
                decision=Decision.COUNTER,
                envelope_seq=seq,
                counter_params={
                    "value_path": "Profile.headline",
                    "base_sha": "EVIL",
                    "kind": "schema",
                },
            )
        ],
    )
    captured = {}

    def _fake_apply(project_root, action, *, config=None):
        captured["action"] = action
        return ProposalOutcome(action.kind, ConciergeWriteCode.OK, "ok")

    monkeypatch.setattr("startd8.vipp.apply.apply_proposal", _fake_apply)
    apply_dispositions(proj, confirm=YES)

    act = captured["action"]
    assert act.kind == "capture"  # inbox kind, NOT the disposition's "schema"
    assert act.base_sha == "GOOD-SHA"  # inbox base_sha, NOT "EVIL"
    assert (
        act.params["value_path"] == "Profile.headline"
    )  # the legit COUNTER amend survives


# --- REJECT / unconfirmed write nothing -----------------------------------------------------------


def test_reject_and_unconfirmed_do_not_call_apply(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(ProposedAction(kind="capture", params={"value_path": "A.b"}, id="rej"))
    buf.add(ProposedAction(kind="capture", params={"value_path": "C.d"}, id="acc"))
    seq = _serialize(proj, buf)
    _write_dispositions(
        proj,
        seq,
        [
            VippDisposition(
                proposal_id="rej", decision=Decision.REJECT, envelope_seq=seq
            ),
            VippDisposition(
                proposal_id="acc", decision=Decision.ACCEPT, envelope_seq=seq
            ),
        ],
    )
    calls = []
    monkeypatch.setattr(
        "startd8.vipp.apply.apply_proposal",
        lambda pr, a, *, config=None: calls.append(a)
        or ProposalOutcome(a.kind, CaptureCode.OK),
    )

    res = apply_dispositions(proj, confirm=NO)  # human declines everything

    assert calls == []  # REJECT skipped; ACCEPT not confirmed → no apply
    codes = {o["proposal_id"]: o["code"] for o in res.outcomes}
    assert codes["rej"] == "rejected_no_write"
    assert codes["acc"] == "unconfirmed"
    assert res.inbox_shredded is False  # an unconfirmed actionable remains → keep inbox


# --- unknown kind blocked by the apply floor ------------------------------------------------------


def test_unknown_kind_blocked_by_apply_floor(tmp_path):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(ProposedAction(kind="evil", params={}, id="x"))  # not in PROPOSAL_KINDS
    seq = _serialize(proj, buf)
    _write_dispositions(
        proj,
        seq,
        [VippDisposition(proposal_id="x", decision=Decision.ACCEPT, envelope_seq=seq)],
    )

    res = apply_dispositions(proj, confirm=YES)  # real apply_proposal floor

    out = res.outcomes[0]
    assert out["code"] == "unknown_kind" and out["ok"] is False
    assert res.wrote == 0


# --- partial failure: consume terminal, retain retriable, resume (FR-18) ---------------------------


def test_partial_failure_consumes_terminal_retains_retriable_then_resumes(
    tmp_path, monkeypatch
):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    for i in range(1, 6):
        buf.add(
            ProposedAction(kind="friction", params={"friction": str(i)}, id=f"p{i}")
        )
    seq = _serialize(proj, buf)
    _write_dispositions(
        proj,
        seq,
        [
            VippDisposition(
                proposal_id=f"p{i}", decision=Decision.ACCEPT, envelope_seq=seq
            )
            for i in range(1, 6)
        ],
    )

    # p4 fails retriably; the rest succeed.
    def _apply_round1(pr, action, *, config=None):
        if action.id == "p4":
            return ProposalOutcome("friction", CaptureCode.STALE_FILE, "stale")
        return ProposalOutcome("friction", ConciergeWriteCode.OK, "ok")

    monkeypatch.setattr("startd8.vipp.apply.apply_proposal", _apply_round1)
    r1 = apply_dispositions(proj, confirm=YES)

    assert r1.wrote == 4 and r1.actionable == 5
    assert {o["proposal_id"]: o.get("retriable") for o in r1.outcomes}["p4"] is True
    assert r1.inbox_shredded is False  # p4 still pending → inbox kept

    # Resume: now p4 succeeds. Only p4 should be applied (the rest are already consumed).
    applied_ids = []

    def _apply_round2(pr, action, *, config=None):
        applied_ids.append(action.id)
        return ProposalOutcome("friction", ConciergeWriteCode.OK, "ok")

    monkeypatch.setattr("startd8.vipp.apply.apply_proposal", _apply_round2)
    r2 = apply_dispositions(proj, confirm=YES)

    assert applied_ids == ["p4"]  # cursor skipped the 4 already-consumed
    assert r2.wrote == 1
    assert r2.inbox_shredded is True  # all consumed now


# --- stale-seq refusal (FR-18) --------------------------------------------------------------------


def test_stale_seq_is_refused(tmp_path):
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(
        ProposedAction(
            kind="friction",
            params={"friction": "a", "what_happened": "b", "implication": "c"},
            id="f1",
        )
    )
    seam.serialize_buffer(buf, proj)
    run_vipp_negotiate(
        seam.inbox_path(proj), project_root=proj, emit=False
    )  # dispositions pin seq 1

    # Drain + re-serialize → inbox advances to seq 2, but the dispositions still pin seq 1.
    seam.shred_inbox(proj)
    seam.serialize_buffer(buf, proj)
    assert ProposalEnvelope.from_json(seam.read_inbox(proj)).envelope_seq == 2

    res = apply_dispositions(proj, confirm=YES)
    assert res.stale is True
    assert "re-negotiate" in res.refused_reason
    assert res.wrote == 0
