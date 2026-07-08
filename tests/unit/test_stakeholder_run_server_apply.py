"""Unit tests for the FR-R7 apply gate (M-apply) — preview + signed-challenge ratify.

The highest-risk write in the pipeline: it writes the project source of record. These assert the gate's
load-bearing properties — off unless enabled, strict mandatory, preview is byte-identical, the challenge
binds {seq, content-hash} and is single-use, a stale/changed set is refused, and ratify writes ONLY the
echoed proposal ids. A throwaway tmp project stands in; `friction` proposals write with no scaffold.
"""
from __future__ import annotations

import itertools
import json
import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from startd8.kickoff_experience import stakeholder_run_server as srv
from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction
from startd8.vipp import context
from startd8.vipp.assistant import DISPOSITIONS_JSON
from startd8.vipp.models import Decision, VippDisposition, VippReport

pytestmark = pytest.mark.unit

TOKEN = "secret-token-abc"
ORIGIN = "http://grafana.local"
_nonce = itertools.count()


def _hdr(strict=True):
    h = {"Authorization": f"Bearer {TOKEN}"}
    if strict:
        h["Origin"] = ORIGIN
        h["X-Nonce"] = f"n{next(_nonce)}"  # fresh each call — nonces are single-use in strict mode
    return h


def _proj(tmp_path) -> Path:
    # resolve_confined_root rejects a symlinked root (macOS tmp is /var → /private/var) — use realpath.
    proj = Path(os.path.realpath(tmp_path))
    (proj / ".startd8" / "vipp").mkdir(parents=True, exist_ok=True)
    return proj


def _client(proj, *, enable_apply=True, strict=True):
    cfg = srv.RunServerConfig(
        project_root=proj, token=TOKEN, model="m",
        strict=strict, allowed_origins=(ORIGIN,), enable_apply=enable_apply,
    )
    return TestClient(srv.build_stakeholder_run_app(cfg))


def _setup_frictions(proj, ids, decisions=None) -> int:
    """Serialize `friction` proposals + write an ACCEPT dispositions report pinned to the live seq."""
    decisions = decisions or {i: Decision.ACCEPT for i in ids}
    buf = ProposalBuffer()
    for i in ids:
        buf.add(ProposedAction(
            kind="friction",
            params={"friction": f"slow-{i}", "what_happened": "x", "implication": "y"},
            id=i,
        ))
    seam.serialize_buffer(buf, proj)
    seq = seam.read_inbox(proj)["envelope_seq"]
    report = VippReport(
        project_id="p", envelope_seq=seq,
        dispositions=[VippDisposition(proposal_id=i, decision=decisions[i], envelope_seq=seq) for i in ids],
    )
    (context.vipp_dir(proj) / DISPOSITIONS_JSON).write_text(json.dumps(report.to_dict()), encoding="utf-8")
    return seq


# --------------------------------------------------------------------------- gating


def test_apply_disabled_is_404(tmp_path):
    client = _client(_proj(tmp_path), enable_apply=False)
    assert client.post("/stakeholders/apply/preview", json={}, headers=_hdr()).status_code == 404
    assert client.post("/stakeholders/apply/ratify", json={}, headers=_hdr()).status_code == 404


def test_apply_requires_strict_mode(tmp_path):
    client = _client(_proj(tmp_path), enable_apply=True, strict=False)
    # non-strict → 403 even with a valid token (FR-R7 c: strict is mandatory for apply)
    assert client.post("/stakeholders/apply/preview", json={}, headers=_hdr(strict=False)).status_code == 403


def test_apply_requires_token(tmp_path):
    client = _client(_proj(tmp_path))
    assert client.post("/stakeholders/apply/preview", json={}).status_code == 401


# --------------------------------------------------------------------------- preview


def test_preview_returns_would_apply_and_challenge_and_is_byte_identical(tmp_path):
    proj = _proj(tmp_path)
    _setup_frictions(proj, ["f1", "f2"])
    inbox = seam.inbox_path(proj)
    before = inbox.read_bytes()
    client = _client(proj)
    r = client.post("/stakeholders/apply/preview", json={}, headers=_hdr())
    assert r.status_code == 200
    body = r.json()
    assert {w["proposal_id"] for w in body["would_apply"]} == {"f1", "f2"}
    assert body["challenge"] and "." in body["challenge"]
    assert "token-gated" in body["posture"]
    assert inbox.read_bytes() == before  # preview wrote nothing
    assert not context.cursor_path(proj).exists()


def test_preview_no_inbox_is_409(tmp_path):
    client = _client(_proj(tmp_path))
    r = client.post("/stakeholders/apply/preview", json={}, headers=_hdr())
    assert r.status_code == 409 and "no inbox" in r.json()["refused_reason"]


# --------------------------------------------------------------------------- ratify


def _preview(client):
    return client.post("/stakeholders/apply/preview", json={}, headers=_hdr()).json()


def test_ratify_writes_only_listed_proposals(tmp_path):
    proj = _proj(tmp_path)
    _setup_frictions(proj, ["f1", "f2"])
    client = _client(proj)
    pv = _preview(client)
    r = client.post(
        "/stakeholders/apply/ratify",
        json={"proposal_ids": ["f1"], "challenge": pv["challenge"]},
        headers=_hdr(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["wrote"] == 1
    codes = {o["proposal_id"]: o["code"] for o in body["outcomes"]}
    assert codes["f2"] == "unconfirmed"  # not echoed → not applied
    assert body["inbox_shredded"] is False  # f2 still pending → inbox retained
    assert (proj / "concierge-friction.jsonl").exists()  # the real write happened for f1


def test_ratify_forged_challenge_is_403_and_writes_nothing(tmp_path):
    proj = _proj(tmp_path)
    _setup_frictions(proj, ["f1"])
    client = _client(proj)
    _preview(client)
    r = client.post(
        "/stakeholders/apply/ratify",
        json={"proposal_ids": ["f1"], "challenge": "bogus.deadbeef"},
        headers=_hdr(),
    )
    assert r.status_code == 403
    assert not (proj / "concierge-friction.jsonl").exists()


def test_ratify_expired_challenge_is_403(tmp_path):
    proj = _proj(tmp_path)
    seq = _setup_frictions(proj, ["f1"])
    client = _client(proj)
    _preview(client)  # ensure the key exists
    # Forge a correctly-signed but already-expired challenge with the real per-project key.
    from startd8.vipp import preview_dispositions

    ch = preview_dispositions(proj).content_hash
    expired = srv._issue_challenge(srv._apply_hmac_key(client.app.state.config), seq, ch, ttl=-1)
    r = client.post(
        "/stakeholders/apply/ratify",
        json={"proposal_ids": ["f1"], "challenge": expired},
        headers=_hdr(),
    )
    assert r.status_code == 403 and "expired" in r.json()["error"]


def test_ratify_stale_seq_is_409(tmp_path):
    proj = _proj(tmp_path)
    _setup_frictions(proj, ["f1"])
    client = _client(proj)
    pv = _preview(client)  # challenge bound to the current seq
    # Simulate the host re-posting between preview and ratify: drain the inbox, then serialize a new
    # (different) envelope → envelope_seq bumps (serialize refuses to clobber an undrained inbox, and
    # the seq counter survives the shred). The old challenge is now stale.
    seam.shred_inbox(proj)
    _setup_frictions(proj, ["f1", "f2"])
    r = client.post(
        "/stakeholders/apply/ratify",
        json={"proposal_ids": ["f1"], "challenge": pv["challenge"]},
        headers=_hdr(),
    )
    assert r.status_code == 409  # stale seq → re-preview


def test_ratify_challenge_is_single_use(tmp_path):
    proj = _proj(tmp_path)
    _setup_frictions(proj, ["f1", "f2"])
    client = _client(proj)
    pv = _preview(client)
    ok = client.post("/stakeholders/apply/ratify",
                     json={"proposal_ids": ["f1"], "challenge": pv["challenge"]}, headers=_hdr())
    assert ok.status_code == 200
    # Same challenge again → refused (single-use), even though f2 is still pending.
    again = client.post("/stakeholders/apply/ratify",
                        json={"proposal_ids": ["f2"], "challenge": pv["challenge"]}, headers=_hdr())
    assert again.status_code == 409 and "already used" in again.json()["error"]


def test_ratify_requires_ids_and_challenge(tmp_path):
    client = _client(_proj(tmp_path))
    assert client.post("/stakeholders/apply/ratify", json={"challenge": "x.y"}, headers=_hdr()).status_code == 400
    assert client.post("/stakeholders/apply/ratify", json={"proposal_ids": ["f1"]}, headers=_hdr()).status_code == 400
