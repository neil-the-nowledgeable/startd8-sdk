# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""M3 host-side serialization-seam tests (VIPP FR-15/17/18, NR-7).

Covers: buffer→inbox→ProposalEnvelope round-trip + fixture-parity (the real serializer output feeds
the M2 evaluator, A-S6); base_sha/value_path survive verbatim (not redaction-touched); SOTTO
byte-identical-when-absent (no opt-in ⇒ nothing written); no-clobber-of-undrained; 0600 + .gitignore;
read-path symlink rejection (R3-F7); monotonic seq across shred; host↔vipp shape/protocol parity.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from startd8.fde.models import ClaimLabel
from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction
from startd8.sapper.ground_truth import GroundTruthAnswer, GroundTruthVerdict
from startd8.vipp import evaluate
from startd8.vipp.models import (
    HOST_PROPOSAL_FIELDS,
    PROTOCOL_VERSION,
    Decision,
    ProposalEnvelope,
)


def _real(p) -> Path:
    # resolve_confined_root rejects a symlinked root (macOS /var → /private/var); use the real path.
    return Path(os.path.realpath(p))


def _opted_in(tmp_path) -> Path:
    proj = _real(tmp_path)
    (proj / ".startd8" / "vipp").mkdir(parents=True)
    return proj


def _buffer() -> ProposalBuffer:
    b = ProposalBuffer()
    b.add(
        ProposedAction(
            kind="capture",
            params={"value_path": "Profile.email", "value": "a@b.c"},
            id="p1",
            base_sha="sha256:cafef00d",
        )
    )
    b.add(ProposedAction(kind="brief", params={"source": "Entities: Profile"}, id="p2"))
    return b


def _snapshot(root: Path):
    return {str(p.relative_to(root)) for p in root.rglob("*")}


# --- round-trip + fixture-parity (A-S6) -----------------------------------------------------------


def test_round_trip_and_m2_evaluator_accepts_real_serializer_output(tmp_path):
    proj = _opted_in(tmp_path)
    result = seam.serialize_buffer(_buffer(), proj, project_id="proj-1")
    assert result.ok

    raw = seam.read_inbox(proj)
    assert raw["kind"] == "vipp-proposal-envelope" and raw["project_id"] == "proj-1"

    env = ProposalEnvelope.from_json(raw)
    assert [p.id for p in env.proposals] == ["p1", "p2"]

    # Fixture-parity: the REAL serializer output must drive the M2 evaluator (A-S6).
    oracle = _ScriptedOracle(
        {
            "Profile.email": GroundTruthAnswer(
                GroundTruthVerdict.VALIDATED, evidence="exists"
            )
        }
    )
    disps = {d.proposal_id: d for d in evaluate.evaluate_envelope(env, oracle)}
    assert disps["p1"].decision is Decision.ACCEPT
    assert disps["p2"].decision is Decision.ACCEPT  # brief → no-entity ACCEPT
    assert disps["p1"].claims[0].label is ClaimLabel.OBSERVED


class _ScriptedOracle:
    def __init__(self, by_symbol):
        self._by = by_symbol

    def answer(self, question):
        return self._by.get(question.symbol) or GroundTruthAnswer.omit("unscripted")


def test_base_sha_and_value_path_survive_verbatim(tmp_path):
    proj = _opted_in(tmp_path)
    seam.serialize_buffer(_buffer(), proj)
    env = ProposalEnvelope.from_json(seam.read_inbox(proj))
    capture = next(p for p in env.proposals if p.id == "p1")
    assert capture.base_sha == "sha256:cafef00d"  # not dropped, not redacted
    assert capture.params["value_path"] == "Profile.email"


# --- SOTTO: byte-identical-when-absent (NR-7) -----------------------------------------------------


def test_no_vipp_opt_in_writes_nothing(tmp_path):
    proj = _real(tmp_path)  # NO .startd8/vipp dir, no env flag
    (proj / "keep.txt").write_text("x")  # some pre-existing content
    before = _snapshot(proj)

    result = seam.maybe_serialize_buffer(_buffer(), proj)

    assert result is None  # opt-in gate: nothing happened
    assert not (proj / ".startd8").exists()
    assert (
        _snapshot(proj) == before
    )  # dict-equality: the tree is byte-identical-when-absent


def test_maybe_serialize_runs_when_opted_in(tmp_path):
    proj = _opted_in(tmp_path)
    result = seam.maybe_serialize_buffer(_buffer(), proj)
    assert result is not None and result.ok
    assert seam.inbox_path(proj).exists()


# --- confinement / lifecycle ----------------------------------------------------------------------


def test_no_clobber_of_undrained_inbox(tmp_path):
    proj = _opted_in(tmp_path)
    seam.serialize_buffer(_buffer(), proj)
    first_seq = ProposalEnvelope.from_json(seam.read_inbox(proj)).envelope_seq

    # A second serialize while the inbox is undrained must NOT overwrite it.
    b2 = ProposalBuffer()
    b2.add(ProposedAction(kind="friction", params={"friction": "y"}, id="z"))
    result = seam.serialize_buffer(b2, proj)

    assert not result.ok or result.skipped  # reported as skipped/blocked, not written
    env = ProposalEnvelope.from_json(seam.read_inbox(proj))
    assert env.envelope_seq == first_seq  # unchanged
    assert [p.id for p in env.proposals] == ["p1", "p2"]  # original inbox intact


def test_inbox_is_0600_and_gitignored(tmp_path):
    proj = _opted_in(tmp_path)
    seam.serialize_buffer(_buffer(), proj)
    mode = stat.S_IMODE(os.stat(seam.inbox_path(proj)).st_mode)
    assert mode == 0o600
    assert (proj / ".startd8/vipp/.gitignore").read_text().strip() == "*"


def test_read_path_rejects_symlink(tmp_path):
    proj = _opted_in(tmp_path)
    seam.serialize_buffer(_buffer(), proj)
    ip = seam.inbox_path(proj)
    decoy = proj / "decoy.json"
    decoy.write_text('{"kind":"evil"}')
    seam.shred_inbox(proj)
    os.symlink(decoy, ip)  # plant a symlink where the inbox should be
    with pytest.raises(Exception):  # SafeWriteError — refuse to read through a symlink
        seam.read_inbox(proj)


def test_monotonic_seq_survives_shred(tmp_path):
    proj = _opted_in(tmp_path)
    seam.serialize_buffer(_buffer(), proj)
    seq1 = ProposalEnvelope.from_json(seam.read_inbox(proj)).envelope_seq
    assert seam.shred_inbox(proj) is True
    assert seam.read_inbox(proj) is None  # consumed

    seam.serialize_buffer(_buffer(), proj)
    seq2 = ProposalEnvelope.from_json(seam.read_inbox(proj)).envelope_seq
    assert seq2 == seq1 + 1  # monotonic across the shred


# --- host ↔ vipp parity (the cross-package contract) ----------------------------------------------


def test_host_and_vipp_protocol_and_shape_are_in_lockstep():
    assert seam.PROTOCOL_VERSION == PROTOCOL_VERSION
    assert seam._PROPOSAL_FIELDS == HOST_PROPOSAL_FIELDS
    assert seam.ENVELOPE_KIND == "vipp-proposal-envelope"
