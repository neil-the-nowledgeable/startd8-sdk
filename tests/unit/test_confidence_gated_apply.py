# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""#8 — confidence-gated apply: provenance threading + consensus at preview (CRP-hardened).

Covers the write-boundary invariants the CRP flagged: FR-7 hash-safety, FR-8 M2 fingerprint, FR-2a
path-traversal, FR-2b one-session, FR-6 best-effort, and the vipp-stays-pure import graph.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _proj(tmp_path) -> Path:
    proj = Path(os.path.realpath(tmp_path))
    (proj / ".startd8" / "vipp").mkdir(parents=True, exist_ok=True)
    return proj


def _write_transcript(proj: Path, sid: str, entries) -> None:
    d = proj / ".startd8" / "kickoff-panel"
    d.mkdir(parents=True, exist_ok=True)
    doc = {"session_id": sid, "rounds": [{"round_id": "R1", "entries": entries}]}
    (d / f"{sid}.json").write_text(json.dumps(doc), encoding="utf-8")


# ── FR-2 / FR-2b — provenance derived from the staged recs ────────────────────
def _bypass_allowlist(monkeypatch):
    """Stage past the (empty) bare-project allow-list, like the existing serialize tests do."""
    from startd8.kickoff_experience import proposals as kp
    monkeypatch.setattr(kp, "build_proposal", lambda args, *, project_root, config=None: kp.ProposedAction(
        "capture", {"value_path": args["value_path"], "value": args["value"]}, id="p1", base_sha="d"))


def _stage(proj, sid, vp):
    from startd8.stakeholder_panel.proposals import ProposalStore
    from startd8.stakeholder_panel.synthesis_bridge import stage_recommendations
    stage_recommendations(proj, sid, [{"value_path": vp, "value": "x", "domain": "business-targets"}])
    ProposalStore(proj, sid).update_disposition("business-targets", vp, "accepted")


def test_provenance_single_session_carried(tmp_path, monkeypatch):
    _bypass_allowlist(monkeypatch)
    proj = _proj(tmp_path)
    _stage(proj, "s1", "business-targets.budget.target")
    from startd8.kickoff_experience import vipp_seam as seam
    from startd8.stakeholder_panel.proposals import ProposalStore
    from startd8.stakeholder_panel.synthesis_bridge import serialize_accepted_to_vipp
    result = serialize_accepted_to_vipp(proj, ProposalStore(proj, "s1").load(), accepted_only=True)
    assert result["source_session_id"] == "s1"
    assert seam.read_inbox(proj)["source_session_id"] == "s1"  # written to the envelope


def test_provenance_multi_session_empty(tmp_path, monkeypatch):
    # FR-2b: recs from 2 sessions in one serialize → source_session_id left EMPTY (→ n/a), not arbitrary.
    _bypass_allowlist(monkeypatch)
    proj = _proj(tmp_path)
    from startd8.kickoff_experience import vipp_seam as seam
    from startd8.stakeholder_panel.proposals import ProposalStore
    from startd8.stakeholder_panel.synthesis_bridge import serialize_accepted_to_vipp
    _stage(proj, "s1", "business-targets.budget.target")
    _stage(proj, "s2", "business-targets.deadline.target")
    recs = ProposalStore(proj, "s1").load() + ProposalStore(proj, "s2").load()
    result = serialize_accepted_to_vipp(proj, recs, accepted_only=True)
    assert result["source_session_id"] == ""  # mixed → empty
    assert seam.read_inbox(proj)["source_session_id"] == ""


# ── FR-2 read-side round-trip + old-inbox graceful ───────────────────────────
def test_envelope_roundtrip_read_side(tmp_path):
    from startd8.kickoff_experience import vipp_seam as seam
    from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction
    from startd8.vipp.models import ProposalEnvelope
    proj = _proj(tmp_path)
    buf = ProposalBuffer()
    buf.add(ProposedAction(kind="friction", params={"friction": "x", "what_happened": "y", "implication": "z"}, id="p1"))
    seam.serialize_buffer(buf, proj, source_session_id="kp-abc")
    env = ProposalEnvelope.from_json(json.dumps(seam.read_inbox(proj)))
    assert env.source_session_id == "kp-abc"  # survives write → from_json (read side, not just write)
    assert env.to_dict()["source_session_id"] == "kp-abc"


def test_old_inbox_without_field_is_empty():
    from startd8.vipp.models import ProposalEnvelope
    env = ProposalEnvelope.from_json(json.dumps({"project_id": "p", "proposals": []}))  # pre-#8 shape
    assert env.source_session_id == ""  # graceful default, no KeyError


# ── FR-7 hash-safety: source_session_id outside content_checksum ─────────────
def test_content_checksum_invariant_to_source_session(tmp_path):
    from startd8.kickoff_experience import vipp_seam as seam
    from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction

    def _mk(proj, sid):
        buf = ProposalBuffer()
        buf.add(ProposedAction(kind="friction", params={"friction": "x", "what_happened": "y", "implication": "z"}, id="p1"))
        seam.serialize_buffer(buf, proj, source_session_id=sid)
        return seam.read_inbox(proj)["content_checksum"]

    a = _mk(_proj(tmp_path / "a"), "session-A")
    b = _mk(_proj(tmp_path / "b"), "session-B")
    assert a == b  # identical proposals → identical content_checksum regardless of source_session_id


# ── FR-8 M2 fingerprint: source_session_id excluded ──────────────────────────
def test_m2_fingerprint_invariant_to_source_session(tmp_path):
    from startd8.vipp import context
    p1 = tmp_path / "i1.json"
    p2 = tmp_path / "i2.json"
    base = {"project_id": "p", "envelope_seq": 3, "generated_at": "t", "content_checksum": "c", "proposals": []}
    p1.write_text(json.dumps({**base, "source_session_id": "A"}), encoding="utf-8")
    p2.write_text(json.dumps({**base, "source_session_id": "B"}), encoding="utf-8")
    ex = ("generated_at", "envelope_seq", "source_session_id")
    assert context.checksum_json_excluding(p1, exclude_keys=ex) == context.checksum_json_excluding(p2, exclude_keys=ex)


# ── FR-2a / FR-6 — _apply_consensus helper (path-safety, n/a, real) ──────────
def test_apply_consensus_real_label(tmp_path):
    from startd8.kickoff_experience.stakeholder_run_server import _apply_consensus
    proj = _proj(tmp_path)
    _write_transcript(proj, "s1", [{"role_id": "po", "text": "ship the payment service quickly"},
                                   {"role_id": "eu", "text": "ship the payment service quickly"}])
    c = _apply_consensus(proj, "s1")
    assert c["label"] == "high" and c["n"] == 2 and c["basis"] == "lexical-r1"


def test_apply_consensus_unsafe_session_is_na_no_load(tmp_path, monkeypatch):
    # FR-2a: a traversal component must degrade to n/a and MUST NOT reach the filesystem load.
    from startd8.kickoff_experience import stakeholder_run_server as srv
    import startd8.kickoff_view as kv
    loaded = []
    monkeypatch.setattr(kv, "KickoffViewService", lambda p: type("S", (), {"load": lambda self, s: loaded.append(s)})())
    c = srv._apply_consensus(_proj(tmp_path), "../../../etc/passwd")
    assert c["label"] == "n/a" and loaded == []  # never loaded with the unsafe component


def test_apply_consensus_missing_transcript_is_na(tmp_path):
    from startd8.kickoff_experience.stakeholder_run_server import _apply_consensus
    c = _apply_consensus(_proj(tmp_path), "kp-nonexistent")
    assert c["label"] == "n/a"  # missing transcript → benign n/a, no raise


def test_apply_consensus_empty_session_is_na(tmp_path):
    from startd8.kickoff_experience.stakeholder_run_server import _apply_consensus
    assert _apply_consensus(_proj(tmp_path), "")["label"] == "n/a"  # mixed/pre-#8 → n/a


# ── R1-S4 — importing vipp must NOT pull facilitation/consensus ──────────────
def test_vipp_import_stays_pure():
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[2] / "src"
    code = (
        "import sys, startd8.vipp\n"
        "bad = [m for m in ('startd8.stakeholder_panel.consensus', 'startd8.kickoff_view') if m in sys.modules]\n"
        "print('LEAK' if bad else 'PURE', bad)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(root)})
    assert out.stdout.startswith("PURE"), out.stdout + out.stderr
