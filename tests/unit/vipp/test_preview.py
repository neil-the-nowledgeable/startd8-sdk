# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""FR-R7 preview half — `preview_dispositions` must reconstruct the would-apply set with ZERO writes.

The load-bearing guarantee (CRP F-1): the v0.3 preview-via-`apply_dispositions(confirm→False)` recorded
REJECTs as `consumed` and could shred the inbox on an all-REJECT report. `preview_dispositions` mirrors
the actionable selection but writes nothing — the inbox + cursor are byte-identical afterward.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction
from startd8.vipp import context
from startd8.vipp.apply import apply_dispositions, preview_dispositions
from startd8.vipp.assistant import DISPOSITIONS_JSON
from startd8.vipp.models import Decision, VippDisposition, VippReport

YES = lambda action, disp: True  # noqa: E731


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


def _two_capture_proposals(proj) -> int:
    buf = ProposalBuffer()
    buf.add(ProposedAction(kind="capture", params={"value_path": "A.x", "value": "1"}, id="p1"))
    buf.add(ProposedAction(kind="capture", params={"value_path": "B.y", "value": "2"}, id="p2"))
    return _serialize(proj, buf)


# --------------------------------------------------------------------------- the byte-identical AC


def test_preview_is_byte_identical_even_on_all_reject(tmp_path):
    # The F-1 trap: an all-REJECT report would make apply_dispositions shred the inbox. Preview must not.
    proj = _proj(tmp_path)
    seq = _two_capture_proposals(proj)
    _write_dispositions(proj, seq, [
        VippDisposition(proposal_id="p1", decision=Decision.REJECT, envelope_seq=seq),
        VippDisposition(proposal_id="p2", decision=Decision.REJECT, envelope_seq=seq),
    ])
    inbox_path = seam.inbox_path(proj)
    before = inbox_path.read_bytes()
    cursor = context.cursor_path(proj)
    assert not cursor.exists()  # no cursor yet

    result = preview_dispositions(proj)

    assert result.would_apply == []  # all rejected → nothing would apply
    assert inbox_path.read_bytes() == before  # inbox byte-identical (NOT shredded)
    assert not cursor.exists()  # no REJECT recorded as consumed — zero writes


def test_preview_lists_only_actionable_and_is_repeatable(tmp_path):
    proj = _proj(tmp_path)
    seq = _two_capture_proposals(proj)
    _write_dispositions(proj, seq, [
        VippDisposition(proposal_id="p1", decision=Decision.ACCEPT, envelope_seq=seq),
        VippDisposition(proposal_id="p2", decision=Decision.REJECT, envelope_seq=seq),
    ])
    r1 = preview_dispositions(proj)
    assert [w["proposal_id"] for w in r1.would_apply] == ["p1"]
    assert r1.would_apply[0]["kind"] == "capture"
    assert r1.would_apply[0]["value_path"] == "A.x"
    # Deterministic + side-effect-free: a second preview yields an identical content hash.
    r2 = preview_dispositions(proj)
    assert r2.content_hash == r1.content_hash and r1.content_hash


def test_preview_content_hash_changes_with_the_would_apply_set(tmp_path):
    proj = _proj(tmp_path)
    seq = _two_capture_proposals(proj)
    _write_dispositions(proj, seq, [VippDisposition(proposal_id="p1", decision=Decision.ACCEPT, envelope_seq=seq)])
    only_p1 = preview_dispositions(proj).content_hash
    _write_dispositions(proj, seq, [
        VippDisposition(proposal_id="p1", decision=Decision.ACCEPT, envelope_seq=seq),
        VippDisposition(proposal_id="p2", decision=Decision.ACCEPT, envelope_seq=seq),
    ])
    p1_and_p2 = preview_dispositions(proj).content_hash
    assert only_p1 != p1_and_p2  # a different would-apply set → a different challenge binding


def test_preview_refuses_stale_seq(tmp_path):
    proj = _proj(tmp_path)
    seq = _two_capture_proposals(proj)
    _write_dispositions(proj, seq + 99, [VippDisposition(proposal_id="p1", decision=Decision.ACCEPT, envelope_seq=seq + 99)])
    result = preview_dispositions(proj)
    assert result.stale and "re-negotiate" in result.refused_reason
    assert result.would_apply == []


def test_preview_excludes_already_consumed(tmp_path):
    proj = _proj(tmp_path)
    seq = _two_capture_proposals(proj)
    _write_dispositions(proj, seq, [
        VippDisposition(proposal_id="p1", decision=Decision.ACCEPT, envelope_seq=seq),
        VippDisposition(proposal_id="p2", decision=Decision.ACCEPT, envelope_seq=seq),
    ])
    # Actually apply p1 only (confirm True just for p1), which consumes it.
    apply_dispositions(proj, confirm=lambda a, d: d.proposal_id == "p1")
    # Inbox still present (p2 pending). Preview should now list only the un-consumed p2.
    remaining = [w["proposal_id"] for w in preview_dispositions(proj).would_apply]
    assert "p1" not in remaining and "p2" in remaining


def test_preview_no_inbox_refuses(tmp_path):
    proj = _proj(tmp_path)
    result = preview_dispositions(proj)
    assert result.refused_reason == "no inbox to apply" and result.would_apply == []
