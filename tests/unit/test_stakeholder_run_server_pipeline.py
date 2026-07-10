"""Unit tests for the Increment 3 pipeline-drive routes ($0) on the stakeholder-run endpoint.

Covers FR-R2 (triage), FR-R4 (disposition), FR-R5 (serialize), FR-R6 (negotiate). Every route threads
THROUGH the CLI code paths; these tests assert the routing contract + the load-bearing traps the CRP
flagged (the ``"accepted"`` literal, no-op-when-unstaged → 404, rejected-not-dropped, the explicit
narrative ``max_cost_usd`` ceiling) and that disposition/serialize inherit the store's ``0600`` write.
"""
from __future__ import annotations

import json
import stat

import pytest
from starlette.testclient import TestClient

from startd8.kickoff_experience import stakeholder_run_server as srv

pytestmark = pytest.mark.unit

TOKEN = "secret-token-abc"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _client(tmp_path):
    cfg = srv.RunServerConfig(project_root=tmp_path, token=TOKEN, model="mock:mock-model")
    return TestClient(srv.build_stakeholder_run_app(cfg))


# --------------------------------------------------------------------------- auth (every route)


@pytest.mark.parametrize(
    "path", ["triage", "disposition", "serialize", "negotiate"]
)
def test_pipeline_routes_require_token(tmp_path, path):
    client = _client(tmp_path)
    assert client.post(f"/stakeholders/{path}", json={}).status_code == 401


# --------------------------------------------------------------------------- FR-R2 triage


class _FakeSynthesis:
    def __init__(self, text):
        self.text = text


class _FakeTranscript:
    def __init__(self, sid, text):
        self.session_id = sid
        self.objective = "ship the thing"
        self.synthesis = _FakeSynthesis(text) if text is not None else None


def _patch_service(monkeypatch, *, latest="s1", transcripts=None):
    transcripts = transcripts or {}

    class _FakeService:
        def __init__(self, project_root):
            pass

        def latest_session_id(self):
            return latest

        def load(self, sid):
            if sid not in transcripts:
                raise FileNotFoundError(sid)
            return transcripts[sid]

    import startd8.kickoff_view as kv

    monkeypatch.setattr(kv, "KickoffViewService", _FakeService)


def test_triage_returns_report_with_synthesis_present(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "We should set the budget.")})
    client = _client(tmp_path)
    r = client.post("/stakeholders/triage", json={}, headers=_auth())  # default → latest
    assert r.status_code == 200
    body = r.json()
    assert body["synthesis_present"] is True
    assert body["session_id"] == "s1"  # from TriageReport.to_dict()


def test_triage_degrades_when_no_synthesis(tmp_path, monkeypatch):
    # An ask-all run has no facilitated synthesis — degrade cleanly (200, empty, present=False).
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", None)})
    client = _client(tmp_path)
    r = client.post("/stakeholders/triage", json={"session_id": "s1"}, headers=_auth())
    assert r.status_code == 200
    assert r.json()["synthesis_present"] is False


def test_triage_no_sessions_is_404(tmp_path, monkeypatch):
    _patch_service(monkeypatch, latest=None)
    client = _client(tmp_path)
    assert client.post("/stakeholders/triage", json={}, headers=_auth()).status_code == 404


def test_triage_unknown_session_is_404(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "x")})
    client = _client(tmp_path)
    assert client.post("/stakeholders/triage", json={"session_id": "nope"}, headers=_auth()).status_code == 404


def test_triage_carries_backlog_markdown_superset(tmp_path, monkeypatch):
    # M1a (FR-4/R1-S6): the triage response gains `backlog_markdown` (a str), and stays a SUPERSET —
    # every pre-existing key still present so the additive field can't mask a shape change.
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "We should set the budget.")})
    body = _client(tmp_path).post("/stakeholders/triage", json={}, headers=_auth()).json()
    prior_keys = {"kind", "session_id", "counts", "kind_counts", "health", "candidates", "synthesis_present"}
    assert prior_keys <= set(body)  # superset — no key dropped
    assert "backlog_markdown" in body and isinstance(body["backlog_markdown"], str)


def test_triage_backlog_markdown_empty_when_no_synthesis(tmp_path, monkeypatch):
    # No synthesis → no candidates → the renderer returns "" (H-5), not an error.
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", None)})
    body = _client(tmp_path).post("/stakeholders/triage", json={"session_id": "s1"}, headers=_auth()).json()
    assert body["backlog_markdown"] == ""


# --------------------------------------------------------------------------- FR-R4 disposition


def _stage(tmp_path, sid, mappings):
    from startd8.stakeholder_panel.synthesis_bridge import stage_recommendations

    return stage_recommendations(tmp_path, sid, mappings)


def test_disposition_writes_accepted_literal_and_0600(tmp_path):
    _stage(tmp_path, "s1", [{"value_path": "conventions.yaml#/language", "value": "python",
                             "domain": "conventions"}])
    client = _client(tmp_path)
    r = client.post(
        "/stakeholders/disposition",
        json={"session_id": "s1", "domain": "conventions",
              "value_path": "conventions.yaml#/language", "disposition": "accepted"},
        headers=_auth(),
    )
    assert r.status_code == 200 and r.json()["updated"] is True

    from startd8.stakeholder_panel.proposals import ProposalStore

    store = ProposalStore(tmp_path, "s1")
    rec = store.get("conventions", "conventions.yaml#/language")
    assert rec.disposition == "accepted"  # the exact literal serialize filters on (not "approved")
    mode = stat.S_IMODE(store.path.stat().st_mode)
    assert mode & 0o077 == 0  # inherits the store's 0600 write (no group/other bits)


def test_disposition_rejects_non_literal(tmp_path):
    _stage(tmp_path, "s1", [{"value_path": "conventions.yaml#/language", "value": "python",
                             "domain": "conventions"}])
    client = _client(tmp_path)
    r = client.post(
        "/stakeholders/disposition",
        json={"session_id": "s1", "domain": "conventions",
              "value_path": "conventions.yaml#/language", "disposition": "approved"},
        headers=_auth(),
    )
    assert r.status_code == 400  # only "accepted"/"rejected" are valid


def test_disposition_unstaged_is_404_not_false_success(tmp_path):
    # update_disposition no-ops (returns False) if the rec was never staged — surface it, don't lie.
    _stage(tmp_path, "s1", [{"value_path": "conventions.yaml#/language", "value": "python",
                             "domain": "conventions"}])
    client = _client(tmp_path)
    r = client.post(
        "/stakeholders/disposition",
        json={"session_id": "s1", "domain": "conventions",
              "value_path": "conventions.yaml#/money", "disposition": "accepted"},
        headers=_auth(),
    )
    assert r.status_code == 404


def test_disposition_missing_fields_is_400(tmp_path):
    client = _client(tmp_path)
    r = client.post("/stakeholders/disposition", json={"session_id": "s1"}, headers=_auth())
    assert r.status_code == 400


# --------------------------------------------------------------------------- FR-R5 serialize


def test_serialize_reports_non_allowlisted_not_dropped(tmp_path):
    # Bare project → allow-list empty → build_proposal rejects; the item is REPORTED, never silently dropped.
    _stage(tmp_path, "s1", [{"value_path": "Run.name", "value": "round3"}])
    from startd8.stakeholder_panel.proposals import ProposalStore

    ProposalStore(tmp_path, "s1").update_disposition("", "Run.name", "accepted")
    client = _client(tmp_path)
    r = client.post("/stakeholders/serialize", json={"session_id": "s1"}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["staged"] == []
    assert body["rejected"] and body["rejected"][0][0] == "Run.name"


def test_serialize_writes_inbox_for_accepted_only(tmp_path, monkeypatch):
    from startd8.kickoff_experience import proposals as kp

    def fake_build_proposal(args, *, project_root, config=None):
        return kp.ProposedAction(
            "capture", {"value_path": args["value_path"], "value": args["value"]},
            id="p1", base_sha="deadbeef",
        )

    monkeypatch.setattr(kp, "build_proposal", fake_build_proposal)
    _stage(tmp_path, "s1", [{"value_path": "business-targets.budget.target", "value": "$8,000"},
                            {"value_path": "business-targets.deadline.target", "value": "Q4 2026"}])
    from startd8.stakeholder_panel.proposals import ProposalStore

    ProposalStore(tmp_path, "s1").update_disposition("", "business-targets.budget.target", "accepted")
    client = _client(tmp_path)
    r = client.post("/stakeholders/serialize", json={"session_id": "s1"}, headers=_auth())
    assert r.status_code == 200
    assert r.json()["staged"] == ["business-targets.budget.target"]  # only the accepted one
    inbox = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    assert inbox.is_file()
    paths = [p["params"]["value_path"] for p in json.loads(inbox.read_text())["proposals"]]
    assert paths == ["business-targets.budget.target"]


def test_serialize_no_staged_is_404(tmp_path):
    client = _client(tmp_path)
    assert client.post("/stakeholders/serialize", json={"session_id": "s1"}, headers=_auth()).status_code == 404


def test_serialize_none_accepted_is_409(tmp_path):
    _stage(tmp_path, "s1", [{"value_path": "conventions.yaml#/language", "value": "python",
                             "domain": "conventions"}])  # staged as draft, none accepted
    client = _client(tmp_path)
    assert client.post("/stakeholders/serialize", json={"session_id": "s1"}, headers=_auth()).status_code == 409


def test_serialize_undrained_inbox_is_409_no_clobber(tmp_path, monkeypatch):
    # M1d (FR-10b): the FIRST serialize writes the inbox; a SECOND serialize while it's undrained must
    # 409 (not a silent 200) and leave the inbox byte-identical — else Apply mode ratifies a stale set.
    from startd8.kickoff_experience import proposals as kp

    def fake_build_proposal(args, *, project_root, config=None):
        return kp.ProposedAction("capture", {"value_path": args["value_path"], "value": args["value"]},
                                 id="p1", base_sha="deadbeef")

    monkeypatch.setattr(kp, "build_proposal", fake_build_proposal)
    _stage(tmp_path, "s1", [{"value_path": "business-targets.budget.target", "value": "$8,000"}])
    from startd8.stakeholder_panel.proposals import ProposalStore

    ProposalStore(tmp_path, "s1").update_disposition("", "business-targets.budget.target", "accepted")
    client = _client(tmp_path)
    first = client.post("/stakeholders/serialize", json={"session_id": "s1"}, headers=_auth())
    assert first.status_code == 200
    inbox = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    before = inbox.read_bytes()
    second = client.post("/stakeholders/serialize", json={"session_id": "s1"}, headers=_auth())
    assert second.status_code == 409 and "undrained" in second.json()["error"].lower()
    assert inbox.read_bytes() == before  # no-clobber — the existing inbox is untouched


# --------------------------------------------------------------------------- FR-R6 negotiate


def test_negotiate_no_inbox_is_409(tmp_path):
    client = _client(tmp_path)
    assert client.post("/stakeholders/negotiate", json={}, headers=_auth()).status_code == 409


def test_negotiate_zero_dollar_threads_through(tmp_path, monkeypatch):
    inbox = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("{}")

    captured = {}

    class _Report:
        def counts(self):
            return {"accept": 1}

        def to_dict(self):
            return {"dispositions": []}

    class _Outcome:
        skipped = False
        report = _Report()
        report_path = tmp_path / ".startd8" / "vipp" / "dispositions.md"

    def fake_negotiate(ip, **kw):
        captured.update(kw)
        return _Outcome()

    # The route imports run_vipp_negotiate lazily from startd8.vipp; patch it at that source.
    import startd8.vipp as vipp

    monkeypatch.setattr(vipp, "run_vipp_negotiate", fake_negotiate)
    client = _client(tmp_path)
    r = client.post("/stakeholders/negotiate", json={}, headers=_auth())
    assert r.status_code == 200
    assert r.json()["counts"] == {"accept": 1}
    assert captured["narrative"] is False and captured["agent"] is None  # $0 path
    assert captured["max_cost_usd"] is None


def test_negotiate_narrative_requires_ceiling(tmp_path):
    inbox = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("{}")
    client = _client(tmp_path)
    r = client.post("/stakeholders/negotiate", json={"narrative": True}, headers=_auth())
    assert r.status_code == 400  # FR-R6: narrative spend needs an explicit max_cost_usd
