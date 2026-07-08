"""Unit tests for the FR-R3 extract→stage route (M-drive-paid) on the stakeholder-run endpoint.

The one PAID pipeline step: dry-run token estimate → checksum-gated confirm, keyed on
``(session_id + synthesis-checksum)`` (NOT ``run_key``), fail-closed on the blocking budget, deduped on
resubmit, with actual token spend recorded (FR-9). A fake agent stands in for the LLM so no real spend
happens; the real ``extract_field_mappings`` + tracked mapper + cost recording are exercised end to end.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from startd8.kickoff_experience import stakeholder_run_server as srv

pytestmark = pytest.mark.unit

TOKEN = "secret-token-abc"
MAP_JSON = '[{"value_path": "conventions.yaml#/language", "value": "python", "rationale": "clear"}]'


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


# --------------------------------------------------------------------------- fakes


class _Budget:
    block_on_exceed = True
    scope_project = "stakeholder-panel"


class _Manager:
    def __init__(self, budgets):
        self._b = budgets

    def list_budgets(self, active_only=True):
        return self._b


class _Tracker:
    def __init__(self):
        self.calls = []

    def record_cost(self, **kw):
        self.calls.append(kw)


class _Pricing:
    def __init__(self, est=0.01, calc=0.002):
        self._est, self._calc = est, calc

    def estimate_cost(self, model, prompt_chars, expected_output_chars=0):
        return self._est

    def calculate_total_cost(self, model, input_tokens, output_tokens):
        return self._calc


class _FakeSynthesis:
    def __init__(self, text):
        self.text = text


class _FakeTranscript:
    def __init__(self, sid, text):
        self.session_id = sid
        self.objective = "ship it"
        self.synthesis = _FakeSynthesis(text) if text is not None else None


class _FakeAgent:
    def __init__(self, text):
        self._text = text
        self.name = "stakeholder-extract"
        self.model = "fake"

    async def agenerate(self, prompt, **kw):
        from startd8.models import GenerateResult, TokenUsage

        return GenerateResult(self._text, 1, TokenUsage(input=100, output=50, total=150))


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


def _patch_agent(monkeypatch, *, text=MAP_JSON, counter=None):
    def _resolve(spec, **kw):
        if counter is not None:
            counter.append(spec)
        return _FakeAgent(text)

    import startd8.utils.agent_resolution as ar

    monkeypatch.setattr(ar, "resolve_agent_spec", _resolve)


def _client(tmp_path, *, manager=None, tracker=None, pricing=None):
    cfg = srv.RunServerConfig(
        project_root=tmp_path, token=TOKEN, model="mock:mock-model",
        budget_manager=manager or _Manager([_Budget()]),
        cost_tracker=tracker or _Tracker(),
        pricing=pricing or _Pricing(),
    )
    return TestClient(srv.build_stakeholder_run_app(cfg))


# --------------------------------------------------------------------------- auth / dry-run


def test_extract_requires_token(tmp_path):
    client = _client(tmp_path)
    assert client.post("/stakeholders/extract", json={}).status_code == 401


def test_extract_dry_run_is_zero_dollar_estimate(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "Set the budget to $8k.")})
    # If the agent is ever constructed on a dry-run, this raises → proves dry-run never spends.
    import startd8.utils.agent_resolution as ar

    monkeypatch.setattr(ar, "resolve_agent_spec",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run must not spend")))
    client = _client(tmp_path, pricing=_Pricing(est=0.0123))
    r = client.post("/stakeholders/extract", json={"dry_run": True}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_cost"] == 0.0123
    assert body["synthesis_checksum"] and body["extract_key"]


def test_extract_no_synthesis_is_422(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", None)})
    client = _client(tmp_path)
    r = client.post("/stakeholders/extract", json={"session_id": "s1", "dry_run": True}, headers=_auth())
    assert r.status_code == 422


# --------------------------------------------------------------------------- confirm


def test_extract_confirm_wrong_checksum_is_409(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "Set the budget.")})
    client = _client(tmp_path)
    r = client.post("/stakeholders/extract",
                    json={"session_id": "s1", "confirm_checksum": "stale"}, headers=_auth())
    assert r.status_code == 409


def test_extract_confirm_stages_and_records_actual_cost(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "Use python everywhere.")})
    _patch_agent(monkeypatch)
    tracker = _Tracker()
    client = _client(tmp_path, tracker=tracker, pricing=_Pricing(est=0.01, calc=0.002))
    checksum = client.post("/stakeholders/extract", json={"dry_run": True},
                           headers=_auth()).json()["synthesis_checksum"]
    r = client.post("/stakeholders/extract",
                    json={"session_id": "s1", "confirm_checksum": checksum}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "staged"
    assert body["staged"] == [{"value_path": "conventions.yaml#/language", "value": "python"}]
    assert body["actual_cost"] == 0.002 and body["input_tokens"] == 100 and body["output_tokens"] == 50
    # FR-9: the paid call was recorded to the CostTracker with the real token counts.
    assert tracker.calls and tracker.calls[0]["input_tokens"] == 100
    # And it actually persisted a staged recommendation on disk.
    from startd8.stakeholder_panel.proposals import ProposalStore

    assert ProposalStore(tmp_path, "s1").get("", "conventions.yaml#/language") is not None


def test_extract_dedupes_on_resubmit_no_recharge(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "Use python everywhere.")})
    calls = []
    _patch_agent(monkeypatch, counter=calls)
    client = _client(tmp_path)
    checksum = client.post("/stakeholders/extract", json={"dry_run": True},
                           headers=_auth()).json()["synthesis_checksum"]
    body = {"session_id": "s1", "confirm_checksum": checksum}
    first = client.post("/stakeholders/extract", json=body, headers=_auth())
    second = client.post("/stakeholders/extract", json=body, headers=_auth())
    assert first.json()["status"] == "staged"
    assert second.json()["status"] == "deduped"
    assert len(calls) == 1  # the model ran exactly once — the replay did not re-charge


def test_extract_fail_closed_without_budget_412(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "Use python.")})
    _patch_agent(monkeypatch)
    client = _client(tmp_path, manager=_Manager([]))  # no blocking budget
    checksum = client.post("/stakeholders/extract", json={"dry_run": True},
                           headers=_auth()).json()["synthesis_checksum"]
    r = client.post("/stakeholders/extract",
                    json={"session_id": "s1", "confirm_checksum": checksum}, headers=_auth())
    assert r.status_code == 412


def test_extract_precall_ceiling_refuses_412(tmp_path, monkeypatch):
    _patch_service(monkeypatch, transcripts={"s1": _FakeTranscript("s1", "Use python.")})
    # If the agent runs, this fails — the estimate must gate BEFORE spending.
    import startd8.utils.agent_resolution as ar

    monkeypatch.setattr(ar, "resolve_agent_spec",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ceiling must prevent spend")))
    client = _client(tmp_path, pricing=_Pricing(est=5.0))
    checksum = client.post("/stakeholders/extract", json={"dry_run": True},
                           headers=_auth()).json()["synthesis_checksum"]
    r = client.post(
        "/stakeholders/extract",
        json={"session_id": "s1", "confirm_checksum": checksum, "max_cost_usd": 0.01},
        headers=_auth(),
    )
    assert r.status_code == 412
