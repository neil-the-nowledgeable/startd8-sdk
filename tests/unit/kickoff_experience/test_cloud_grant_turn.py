"""M3 — chat turns under a grant, with per-turn re-validation (R1-S9 / FR-15).

A session consumes ONE use at creation (M2); each turn re-validates the bound grant's liveness WITHOUT
consuming, so a session created just before expiry/revocation is denied on its **next** action — the
use consumed at creation buys no unbounded post-expiry session.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import GrantStore, GrantTarget  # noqa: E402
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction  # noqa: E402
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

KEY = "consumer-key"
ORIGIN = "https://cloud.example.com"
DEP, PROJ = "dep-1", "proj"
T0 = 1_000_000.0


@dataclass
class _Result:
    text: str = "ok"
    stop_reason: str = "completed"
    turns: int = 1
    total_tokens: int = 5
    total_cost_usd: float = 0.001


class _FakeChat:
    def __init__(self):
        self.buffer = ProposalBuffer()

    async def ask(self, message: str) -> _Result:
        self.buffer.add(ProposedAction("friction", {"friction": "f"}, id="p1"))
        return _Result(text=f"echo:{message}")

    def cost_line(self, result) -> str:
        return "cost=0.001"


class _Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def _app(store, clock):
    return build_kickoff_app(
        "/tmp/m3-proj-does-not-need-to-exist", cloud=True, api_key=KEY,
        grant_store=store, deployment_id=DEP, project_id=PROJ,
        cloud_origins=frozenset({ORIGIN}), grant_clock=clock,
        chat_factory=lambda: _FakeChat(),
    )


def _issue(store, *, uses=1, ttl=1000.0, now=T0):
    return store.issue(GrantTarget(DEP, PROJ, "chat-write"), uses=uses,
                       ttl_seconds=ttl, now=now, issued_by="operator:test")


_HDRS = {"x-api-key": KEY, "origin": ORIGIN}


def _open(client):
    return client.get("/concierge/chat", headers=_HDRS)


def _turn(client, msg="hi"):
    return client.post("/concierge/chat/message", data={"message": msg}, headers=_HDRS)


def test_turn_works_under_a_live_grant(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    _issue(store, uses=1, ttl=1000.0, now=T0)
    c = TestClient(_app(store, clock))
    assert _open(c).status_code == 200
    clock.t = T0 + 5
    r = _turn(c)
    assert r.status_code == 200 and r.json()["ok"] is True


def test_turn_does_not_reconsume_the_use(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    g = _issue(store, uses=1, ttl=1000.0, now=T0)
    c = TestClient(_app(store, clock))
    _open(c)                                   # session creation consumes the 1 use → 0 left
    assert store.get(g.id).uses_remaining == 0
    for i in range(3):                         # three turns re-validate, never re-consume
        clock.t = T0 + 1 + i
        assert _turn(c).json()["ok"] is True
    assert store.get(g.id).uses_remaining == 0


def test_turn_denied_after_expiry_even_though_use_was_consumed(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    _issue(store, uses=1, ttl=100.0, now=T0)
    c = TestClient(_app(store, clock))
    clock.t = T0 + 99                          # create just before expiry
    assert _open(c).status_code == 200
    clock.t = T0 + 101                         # grant now expired
    r = _turn(c)
    assert r.status_code == 501 and r.json()["code"] == "cloud_write_deferred"


def test_turn_denied_after_revocation(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    g = _issue(store, uses=1, ttl=1000.0, now=T0)
    c = TestClient(_app(store, clock))
    assert _open(c).status_code == 200
    store.revoke(g.id)
    clock.t = T0 + 1
    assert _turn(c).status_code == 501


def test_turn_denied_with_wrong_origin(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    _issue(store, uses=1, ttl=1000.0, now=T0)
    c = TestClient(_app(store, clock))
    assert _open(c).status_code == 200
    clock.t = T0 + 1
    r = c.post("/concierge/chat/message", data={"message": "hi"},
               headers={"x-api-key": KEY, "origin": "https://evil.example.com"})
    assert r.status_code == 501


def test_message_without_a_bound_session_denies(tmp_path):
    # A cloud message POST with a valid api-key/Origin but no session (never opened) → no grant binding → deny.
    store, clock = GrantStore(), _Clock(T0)
    _issue(store, uses=1, ttl=1000.0, now=T0)
    c = TestClient(_app(store, clock))
    assert _turn(c).status_code == 501
