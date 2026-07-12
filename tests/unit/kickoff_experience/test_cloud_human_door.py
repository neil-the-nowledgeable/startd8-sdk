"""FR-E12 — the cloud human door (magic-link one-time session).

Covers the store redemption (`redeem_link`: consume + burn, all deny paths), the `/kickoff/enter`
route (opens a session on the human's behalf without an X-API-Key header; one-time; host-confined;
generic no-oracle failure; absent on a non-grant build), and the CLI `issue --with-link`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    GrantStore,
    GrantTarget,
    StoreUnavailable,
    _grant_from_dict,
    _grant_to_dict,
)
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

KEY = "consumer-key"
ORIGIN = "https://cloud.example.com"
DEP, PROJ = "dep-1", "proj"
T0 = 1_000_000.0
TARGET = GrantTarget(DEP, PROJ, "chat-write")


class _FakeChat:
    def __init__(self):
        self.session = type("S", (), {"messages": [], "total_tokens": 0, "total_cost_usd": 0.0,
                                      "agent": type("A", (), {"model": "m"})()})()

    async def ask(self, message):
        return type("R", (), {"text": "ok", "stop_reason": "completed", "turns": 1,
                              "total_tokens": 1, "total_cost_usd": 0.0})()

    def cost_line(self, r):
        return "cost=0"


class _Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def _app(root, store, clock, *, grant_capable=True):
    return build_kickoff_app(
        root, cloud=True, api_key=KEY,
        grant_store=store if grant_capable else None,
        deployment_id=DEP, project_id=PROJ, cloud_origins=frozenset({ORIGIN}),
        grant_clock=clock, chat_factory=lambda: _FakeChat(),
    )


def _issue_link(store, *, token="LINKTOKEN-abc", uses=1, ttl=1000.0, now=T0):
    return store.issue(TARGET, uses=uses, ttl_seconds=ttl, now=now,
                       issued_by="operator:test", link_token=token)


# ----------------------------------------------------------------- store: redeem_link


def test_redeem_consumes_and_burns():
    store = GrantStore()
    g = _issue_link(store)
    d = store.redeem_link("LINKTOKEN-abc", TARGET, now=T0 + 1)
    assert d.allowed and d.grant_id == g.id and d.uses_remaining_after == 0
    # burned: a second redemption of the same token is a generic ABSENT (no oracle)
    d2 = store.redeem_link("LINKTOKEN-abc", TARGET, now=T0 + 2)
    assert not d2.allowed and d2.reason.value == "absent"


def test_redeem_deny_paths():
    # wrong target
    s = GrantStore()
    _issue_link(s, token="t1")
    other = GrantTarget("other", PROJ, "chat-write")
    assert s.redeem_link("t1", other, now=T0).reason.value == "target_mismatch"
    # expired
    s = GrantStore()
    _issue_link(s, token="t2", ttl=10.0)
    assert s.redeem_link("t2", TARGET, now=T0 + 999).reason.value == "expired"
    # revoked
    s = GrantStore()
    g = _issue_link(s, token="t3")
    s.revoke(g.id)
    assert s.redeem_link("t3", TARGET, now=T0).reason.value == "revoked"
    # unknown token
    s = GrantStore()
    _issue_link(s, token="t4")
    assert s.redeem_link("nope", TARGET, now=T0).reason.value == "absent"
    # empty token
    assert GrantStore().redeem_link("", TARGET, now=T0).reason.value == "absent"


def test_redeem_store_unavailable_denies_no_burn():
    class _Bad(GrantStore):
        def _sync(self):
            raise StoreUnavailable("read failed")

    s = _Bad()
    d = s.redeem_link("x", TARGET, now=T0)
    assert not d.allowed and d.reason.value == "store_unavailable"


def test_redeem_emits_metrics():
    events = []
    s = GrantStore(metrics=lambda e, r: events.append((e, r)))
    _issue_link(s, token="m1")
    s.redeem_link("m1", TARGET, now=T0)         # consume
    s.redeem_link("m1", TARGET, now=T0)         # burned → deny(absent)
    assert ("consume", None) in events and ("deny", "absent") in events


def test_serialization_byte_identity_when_absent():
    base = {"id": "x", "deployment_id": "d", "project_id": "p", "capability": "c",
            "uses_remaining": 1, "expires_at": 9.0, "issued_by": "o", "issued_at": 0.0, "revoked": False}
    out = _grant_to_dict(_grant_from_dict(base))
    assert "link_token" not in out and out == base
    # present roundtrips
    withtok = _grant_to_dict(_grant_from_dict({**base, "link_token": "T"}))
    assert withtok["link_token"] == "T"


# ----------------------------------------------------------------- route: /kickoff/enter


def test_enter_opens_a_session_without_api_key(tmp_path):
    store = GrantStore()
    _issue_link(store, token="tok-open")
    c = TestClient(_app(tmp_path, store, _Clock()))
    # a human browser: NO x-api-key header, just a loopback Host
    r = c.get("/kickoff/enter?t=tok-open", headers={"host": "localhost"})
    assert r.status_code == 200 and "kickoff_chat" in r.cookies
    # the minted session works for a turn (per-turn revalidation, no re-consume)
    turn = c.post("/concierge/chat/message", data={"message": "hi"},
                  headers={"origin": ORIGIN, "host": "localhost"})
    assert turn.status_code != 501


def test_enter_link_is_one_time(tmp_path):
    store = GrantStore()
    _issue_link(store, token="tok-once")
    c = TestClient(_app(tmp_path, store, _Clock()))
    assert c.get("/kickoff/enter?t=tok-once", headers={"host": "localhost"}).status_code == 200
    r2 = c.get("/kickoff/enter?t=tok-once", headers={"host": "localhost"})
    assert r2.status_code == 403 and "invalid, expired, or already used" in r2.text


def test_enter_generic_failures_are_indistinguishable(tmp_path):
    store = GrantStore()
    _issue_link(store, token="real")
    c = TestClient(_app(tmp_path, store, _Clock()))
    bad_token = c.get("/kickoff/enter?t=WRONG", headers={"host": "localhost"})
    wrong_host = c.get("/kickoff/enter?t=real", headers={"host": "evil.example"})
    assert bad_token.status_code == wrong_host.status_code == 403
    assert bad_token.text == wrong_host.text          # one body for every failure (no oracle)


def test_enter_absent_on_non_grant_build(tmp_path):
    # cloud build with no grant store → the human door route is not registered at all
    c = TestClient(_app(tmp_path, GrantStore(), _Clock(), grant_capable=False))
    assert c.get("/kickoff/enter?t=x", headers={"host": "localhost"}).status_code == 404


# ----------------------------------------------------------------- CLI: issue --with-link


def test_cli_issue_with_link_prints_url():
    from typer.testing import CliRunner

    from startd8.cli_cloud_grant import cloud_grant_app

    runner = CliRunner()
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = f"{d}/grants.json"
        r = runner.invoke(cloud_grant_app, [
            "issue", "--deployment", DEP, "--project", PROJ, "--issued-by", "op",
            "--with-link", "--serve-url", "https://app.example/", "--store", store,
            "--audit", f"{d}/audit.jsonl",
        ])
        assert r.exit_code == 0, r.output
        assert "https://app.example/kickoff/enter?t=" in r.output
        assert "one-time" in r.output.lower()


def test_cli_with_link_requires_serve_url():
    from typer.testing import CliRunner

    from startd8.cli_cloud_grant import cloud_grant_app

    r = CliRunner().invoke(cloud_grant_app, [
        "issue", "--deployment", DEP, "--project", PROJ, "--issued-by", "op", "--with-link",
    ])
    assert r.exit_code == 2 and "--serve-url" in r.output
