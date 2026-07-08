"""Unit tests for the Phase 2 M0 HTTP shell (stakeholder-run endpoint + posture-scoped auth)."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from startd8.kickoff_experience import stakeholder_run_server as srv
from startd8.kickoff_experience.stakeholder_run import derive_run_key, roster_version

pytestmark = pytest.mark.unit

TOKEN = "secret-token-abc"


class _P:
    def __init__(self, role_id):
        self.role_id = role_id
        self.display_name = role_id.title()


class _Roster:
    def __init__(self, ids):
        self.personas = [_P(i) for i in ids]

    def to_dict(self):
        return {"personas": [{"role_id": p.role_id, "display_name": p.display_name} for p in self.personas]}


class _Answer:
    def __init__(self, role_id, grounding="grounded"):
        self._d = {"role_id": role_id, "grounding": grounding, "text": "hi"}

    def to_dict(self):
        return dict(self._d)


class _Panel:
    def __init__(self, roster, **kw):
        self.roster = roster
        self.session_id = "sess-fake"

    async def ask_all(self, question, *, cap=None, value_path=""):
        n = len(self.roster.personas) if cap is None else min(cap, len(self.roster.personas))
        return [_Answer(self.roster.personas[i].role_id) for i in range(n)]

    def close(self):
        pass


class _Budget:
    def __init__(self, block=True, scope="stakeholder-panel"):
        self.block_on_exceed = block
        self.scope_project = scope


class _Manager:
    def __init__(self, budgets):
        self._b = budgets

    def list_budgets(self, active_only=True):
        return self._b


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _client(tmp_path, monkeypatch, roster=None, manager=None, strict=False, allowed=()):
    roster = roster if roster is not None else _Roster(["owner", "sre"])
    manager = manager if manager is not None else _Manager([_Budget()])
    cfg = srv.RunServerConfig(
        project_root=tmp_path, token=TOKEN, model="m",
        budget_manager=manager, panel_factory=_Panel, strict=strict, allowed_origins=allowed,
    )
    monkeypatch.setattr(srv, "_load_roster", lambda config: roster)
    return TestClient(srv.build_stakeholder_run_app(cfg)), roster


# --------------------------------------------------------------------------- build / health / auth


def test_build_requires_token(tmp_path):
    with pytest.raises(ValueError):
        srv.build_stakeholder_run_app(srv.RunServerConfig(project_root=tmp_path, token="", model="m"))


def test_healthz_is_unauthenticated(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.get("/healthz").status_code == 200


def test_run_requires_token(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/stakeholders/run", json={"question": "q", "dry_run": True}).status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert client.post("/stakeholders/run", json={"question": "q", "dry_run": True}, headers=bad).status_code == 401


# --------------------------------------------------------------------------- dry-run / confirm


def test_dry_run_returns_estimate_and_run_key(tmp_path, monkeypatch):
    client, roster = _client(tmp_path, monkeypatch)
    r = client.post("/stakeholders/run", json={"question": "q", "cap": 1, "dry_run": True}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["n_personas"] == 1
    assert body["run_key"] == derive_run_key("q", 1, roster_version(roster))
    assert "estimated_cost" in body and "estimate" in body["note"]


def test_confirm_run_spends_and_returns_answers(tmp_path, monkeypatch):
    client, roster = _client(tmp_path, monkeypatch)
    rk = derive_run_key("q", None, roster_version(roster))
    r = client.post("/stakeholders/run", json={"question": "q", "run_key": rk}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["session_id"] == "sess-fake"
    assert [a["role_id"] for a in body["answers"]] == ["owner", "sre"]


def test_confirm_dedup(tmp_path, monkeypatch):
    client, roster = _client(tmp_path, monkeypatch)
    rk = derive_run_key("q", None, roster_version(roster))
    client.post("/stakeholders/run", json={"question": "q", "run_key": rk}, headers=_auth())
    r2 = client.post("/stakeholders/run", json={"question": "q", "run_key": rk}, headers=_auth())
    assert r2.json()["status"] == "deduped"


def test_confirm_run_key_mismatch(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    r = client.post("/stakeholders/run", json={"question": "q", "run_key": "deadbeef"}, headers=_auth())
    assert r.status_code == 409


def test_fail_closed_without_budget(tmp_path, monkeypatch):
    client, roster = _client(tmp_path, monkeypatch, manager=_Manager([]))  # no blocking budget
    rk = derive_run_key("q", None, roster_version(roster))
    r = client.post("/stakeholders/run", json={"question": "q", "run_key": rk}, headers=_auth())
    assert r.status_code == 412  # Precondition Failed — refuses to spend


def test_missing_question(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/stakeholders/run", json={"dry_run": True}, headers=_auth()).status_code == 400


def test_confirm_requires_run_key(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/stakeholders/run", json={"question": "q"}, headers=_auth()).status_code == 400


def test_no_roster(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch, roster=_Roster([]))
    assert client.post("/stakeholders/run", json={"question": "q", "dry_run": True}, headers=_auth()).status_code == 400


# --------------------------------------------------------------------------- status


def test_status_roundtrip(tmp_path, monkeypatch):
    from startd8.stakeholder_panel.models import Grounding, PanelAnswer
    from startd8.stakeholder_panel.transcript import TranscriptStore

    TranscriptStore(tmp_path, "sess-x").append(
        PanelAnswer(role_id="owner", question="q", text="ship", grounding=Grounding.GROUNDED, session_id="sess-x")
    )
    client, _ = _client(tmp_path, monkeypatch)
    r = client.get("/stakeholders/run/sess-x", headers=_auth())
    assert r.status_code == 200 and r.json()["count"] == 1
    assert client.get("/stakeholders/run/nope", headers=_auth()).status_code == 404
    assert client.get("/stakeholders/run/sess-x").status_code == 401  # auth required


# --------------------------------------------------------------------------- strict mode


def test_strict_origin_allowlist(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch, strict=True, allowed=("http://grafana.local",))
    body = {"question": "q", "dry_run": True}
    hdr = {**_auth(), "Origin": "http://evil.test", "X-Nonce": "n1"}
    assert client.post("/stakeholders/run", json=body, headers=hdr).status_code == 403
    ok = {**_auth(), "Origin": "http://grafana.local", "X-Nonce": "n2"}
    assert client.post("/stakeholders/run", json=body, headers=ok).status_code == 200


def test_strict_replay_nonce(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch, strict=True)
    body = {"question": "q", "dry_run": True}
    h1 = {**_auth(), "X-Nonce": "same"}
    assert client.post("/stakeholders/run", json=body, headers=h1).status_code == 200
    assert client.post("/stakeholders/run", json=body, headers=h1).status_code == 403  # replay
    assert client.post("/stakeholders/run", json=body, headers=_auth()).status_code == 403  # missing nonce
