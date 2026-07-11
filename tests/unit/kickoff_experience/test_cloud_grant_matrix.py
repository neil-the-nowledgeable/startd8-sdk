"""M5 — the fail-closed matrix (R1-S5): each deny trigger independently → chat unavailable, no session,
no token spend. Driven through the real session-creation (chat-page) path with a durable FileGrantStore.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    FileGrantStore,
    GrantDeny,
    GrantTarget,
)
from startd8.kickoff_experience.proposals import ProposalBuffer  # noqa: E402
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

KEY, ORIGIN, DEP, PROJ = "k", "https://cloud.example.com", "dep-1", "proj"
T0 = 1_000_000.0
TGT = GrantTarget(DEP, PROJ, "chat-write")
HDRS = {"x-api-key": KEY, "origin": ORIGIN}


class _FakeChat:
    def __init__(self):
        self.buffer = ProposalBuffer()
        self.session = type("S", (), {"messages": []})()

    async def ask(self, message):
        return type("R", (), {"text": "ok", "stop_reason": "completed", "turns": 1,
                              "total_tokens": 1, "total_cost_usd": 0.0})()

    def cost_line(self, result):
        return "cost=0"


class _Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def _app(store_path, clock):
    return build_kickoff_app(
        "/private/tmp/m5-matrix-proj", cloud=True, api_key=KEY,
        grant_store=FileGrantStore(store_path), deployment_id=DEP, project_id=PROJ,
        cloud_origins=frozenset({ORIGIN}), grant_clock=clock, chat_factory=lambda: _FakeChat(),
    )


def _open(client):
    return client.get("/concierge/chat", headers=HDRS)


def _unavailable(resp) -> bool:
    return resp.status_code == 200 and "unavailable on cloud" in resp.text.lower()


def _created(resp) -> bool:
    return resp.status_code == 200 and "/concierge/chat/message" in resp.text


def _issue(path, clock, *, uses=1, ttl=1000.0):
    return FileGrantStore(path).issue(TGT, uses=uses, ttl_seconds=ttl, now=clock.t, issued_by="op")


def test_trigger_absent(tmp_path):
    c = TestClient(_app(tmp_path / "g.json", _Clock()))
    assert _unavailable(_open(c))                       # no grant issued


def test_trigger_expired(tmp_path):
    p, clock = tmp_path / "g.json", _Clock(T0)
    _issue(p, clock, ttl=100.0)
    clock.t = T0 + 101
    assert _unavailable(_open(TestClient(_app(p, clock))))


def test_trigger_exhausted(tmp_path):
    p, clock = tmp_path / "g.json", _Clock(T0)
    _issue(p, clock, uses=1)
    c = TestClient(_app(p, clock))
    assert _created(_open(c))                           # consumes the 1 use
    assert _unavailable(_open(c))                       # now exhausted


def test_trigger_revoked(tmp_path):
    p, clock = tmp_path / "g.json", _Clock(T0)
    g = _issue(p, clock)
    FileGrantStore(p).revoke(g.id)
    assert _unavailable(_open(TestClient(_app(p, clock))))


def test_trigger_store_unavailable(tmp_path):
    p, clock = tmp_path / "g.json", _Clock(T0)
    _issue(p, clock)
    store = FileGrantStore(p)                           # app loads the valid grant at build time
    app = build_kickoff_app(
        "/private/tmp/m5-matrix-proj", cloud=True, api_key=KEY, grant_store=store,
        deployment_id=DEP, project_id=PROJ, cloud_origins=frozenset({ORIGIN}),
        grant_clock=clock, chat_factory=lambda: _FakeChat(),
    )
    p.write_text("{ corrupt not json")                 # durable backend becomes unreadable AT RUNTIME
    # fail-closed: the next request's reload (`_sync`) fails → deny, not a 500
    assert _unavailable(_open(TestClient(app)))


def test_trigger_clock_untrusted_is_a_store_level_deny(tmp_path):
    # The web app always trusts its clock; the clock-untrusted trigger is enforced at the primitive.
    p, clock = tmp_path / "g.json", _Clock(T0)
    _issue(p, clock)
    d = FileGrantStore(p).resolve_and_consume(TGT, now=T0 + 1, clock_trusted=False)
    assert d.reason is GrantDeny.CLOCK_UNTRUSTED


def test_happy_path_valid_grant_creates_session(tmp_path):
    p, clock = tmp_path / "g.json", _Clock(T0)
    _issue(p, clock, uses=1, ttl=1000.0)
    assert _created(_open(TestClient(_app(p, clock))))


def test_store_unavailable_on_a_per_turn_revalidate_also_denies(tmp_path):
    # Store corruption AFTER session creation → the per-turn revalidate's reload fails → deny (not 500).
    # Completes the matrix: store-unavailable is fail-closed on BOTH consume and revalidate paths.
    p, clock = tmp_path / "g.json", _Clock(T0)
    _issue(p, clock, uses=1, ttl=1000.0)
    store = FileGrantStore(p)
    app = build_kickoff_app(
        "/private/tmp/m5-matrix-proj", cloud=True, api_key=KEY, grant_store=store,
        deployment_id=DEP, project_id=PROJ, cloud_origins=frozenset({ORIGIN}),
        grant_clock=clock, chat_factory=lambda: _FakeChat(),
    )
    c = TestClient(app)
    assert _created(_open(c))                          # session created (grant consumed)
    p.write_text("{ corrupt")                          # durable backend unreadable at runtime
    r = c.post("/concierge/chat/message", data={"message": "hi"}, headers=HDRS)
    assert r.status_code == 501 and r.json()["code"] == "cloud_write_deferred"
