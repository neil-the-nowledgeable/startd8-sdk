"""M5 serve-mode tests — security-first (FR-SRV-4/5/6). Uses Starlette TestClient + real sockets.

The security model is the load-bearing 80%, so these assert the guards directly: loopback bind,
token (constant-time, gate-all), Host/Origin fail-closed, uniform errors, upgrade-reject, cost caps,
replay nonce, and the cross-process lock.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

pytest.importorskip("starlette")
from starlette.testclient import TestClient  # noqa: E402

from startd8.agents.base import BaseAgent  # noqa: E402
from startd8.consultation.models import (  # noqa: E402
    ConsultationSession,
    Turn,
    TurnRole,
    TurnStatus,
)
from startd8.consultation.store import ConsultationStore  # noqa: E402
from startd8.consultation import serve as srv  # noqa: E402

PORT = 8765
ORIGIN = f"http://127.0.0.1:{PORT}"
TOKEN = "test-token-abc123"


class FakeAgent(BaseAgent):
    def __init__(self, name, model):
        super().__init__(name, model)

    async def agenerate(self, prompt, **kwargs):  # pragma: no cover
        return SimpleNamespace(text="x", time_ms=1, token_usage=None)

    async def acreate_response(self, prompt_id, prompt, images=None, **kwargs):
        return SimpleNamespace(response=f"ans:{self.model}",
                               token_usage=SimpleNamespace(input=5, output=2), response_time_ms=9)


def _seed(tmp_path):
    store = ConsultationStore(base_dir=tmp_path / ".startd8")
    s = ConsultationSession(id="sess1", prompt="p", roster=["m1", "m2"])
    s.turns_by_model = {
        "m1": [Turn(role=TurnRole.user, text="p"), Turn(role=TurnRole.assistant, text="a1", status=TurnStatus.ok)],
        "m2": [Turn(role=TurnRole.user, text="p"), Turn(role=TurnRole.assistant, text="a2", status=TurnStatus.ok)],
    }
    store.create_session_dir(s.id)
    store.save(s)
    return store


def _state(tmp_path, **over):
    store = _seed(tmp_path)
    kw = dict(session_id="sess1", store=store, roster={"m1": FakeAgent("m1", "m1"), "m2": FakeAgent("m2", "m2")},
              token=TOKEN, origin=ORIGIN, port=PORT)
    kw.update(over)
    return srv.ServeState(**kw)


def _client(state):
    return TestClient(srv.build_app(state), base_url=ORIGIN)


# ── loopback socket (FR-SRV-4a / R2-F5) ───────────────────────────────────────
class TestLoopbackSocket:
    def test_accepts_loopback_and_asserts_bound_addr(self):
        s = srv.open_loopback_socket("127.0.0.1", 0)
        try:
            host, port = s.getsockname()[:2]
            assert host == "127.0.0.1" and port > 0
            # SO_REUSEADDR must NOT be set (R2-F5)
            assert s.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        finally:
            s.close()

    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "8.8.8.8"])
    def test_refuses_non_loopback(self, host):
        with pytest.raises(ValueError):
            srv.open_loopback_socket(host, 0)


# ── token gating (FR-SRV-4b/d) ────────────────────────────────────────────────
class TestTokenGate:
    def test_index_requires_token(self, tmp_path):
        c = _client(_state(tmp_path))
        assert c.get("/").status_code == 401
        assert c.get("/?t=wrong").status_code == 401
        ok = c.get(f"/?t={TOKEN}")
        assert ok.status_code == 200 and "session-data" in ok.text

    def test_session_route_token_gated_no_leak(self, tmp_path):
        c = _client(_state(tmp_path))
        bad = c.get("/session")  # no token
        assert bad.status_code == 401 and bad.text == ""  # uniform + no session content
        good = c.get("/session", headers={"X-Consult-Token": TOKEN})
        assert good.status_code == 200 and good.json()["id"] == "sess1"


# ── Host / Origin (FR-SRV-4c) ─────────────────────────────────────────────────
class TestHostOrigin:
    def test_foreign_host_rejected(self, tmp_path):
        c = _client(_state(tmp_path))
        r = c.get(f"/?t={TOKEN}", headers={"Host": "evil.com"})
        assert r.status_code == 403

    def test_post_requires_matching_origin_fail_closed(self, tmp_path):
        st = _state(tmp_path)
        c = _client(st)
        n = st.mint_nonce()
        body = {"prompt": "q2", "target": "m1", "nonce": n}
        # missing Origin → 403 (fail-closed)
        assert c.post("/reply", json=body, headers={"X-Consult-Token": TOKEN}).status_code == 403
        # foreign Origin → 403
        assert c.post("/reply", json=dict(body, nonce=st.mint_nonce()),
                      headers={"X-Consult-Token": TOKEN, "Origin": "http://evil.com"}).status_code == 403


# ── upgrade reject (FR-SRV-4g) + headers (4e/b) ───────────────────────────────
class TestUpgradeAndHeaders:
    def test_upgrade_rejected(self, tmp_path):
        c = _client(_state(tmp_path))
        r = c.get(f"/?t={TOKEN}", headers={"Upgrade": "websocket"})
        assert r.status_code == 400

    def test_security_headers_present(self, tmp_path):
        c = _client(_state(tmp_path))
        r = c.get(f"/?t={TOKEN}")
        csp = r.headers.get("content-security-policy", "")
        assert "script-src 'nonce-" in csp and "connect-src 'self'" in csp
        assert r.headers.get("referrer-policy") == "no-referrer"


# ── executor + replay + caps (FR-SRV-3/5/6) ───────────────────────────────────
class TestReplyExecutor:
    def _post(self, c, st, prompt="q2", target="m1", nonce=None):
        return c.post("/reply", json={"prompt": prompt, "target": target, "nonce": nonce or st.mint_nonce()},
                      headers={"X-Consult-Token": TOKEN, "Origin": ORIGIN})

    def test_reply_runs_follow_up_and_persists(self, tmp_path):
        st = _state(tmp_path)
        c = _client(st)
        r = self._post(c, st, target="m1")
        assert r.status_code == 200
        js = r.json()
        assert len(js["session"]["turns_by_model"]["m1"]) == 4  # user,asst,user,asst
        assert len(js["session"]["turns_by_model"]["m2"]) == 2  # untouched
        assert "next_nonce" in js
        # persisted to disk
        assert len(st.store.load("sess1").turns_by_model["m1"]) == 4

    def test_replayed_nonce_rejected(self, tmp_path):
        st = _state(tmp_path)
        c = _client(st)
        n = st.mint_nonce()
        assert self._post(c, st, nonce=n).status_code == 200
        assert self._post(c, st, nonce=n).status_code == 409  # single-use (replay defense)

    def test_turn_cap(self, tmp_path):
        st = _state(tmp_path, max_turns=1)
        c = _client(st)
        assert self._post(c, st).status_code == 200
        assert self._post(c, st).status_code == 429  # cap reached

    def test_spend_ceiling(self, tmp_path):
        st = _state(tmp_path, max_calls=1)  # 'all' = 2 calls > ceiling
        c = _client(st)
        assert self._post(c, st, target="all").status_code == 402


# ── cross-process lock (FR-SRV-6) ─────────────────────────────────────────────
class TestCrossProcessLock:
    def test_second_serve_refused(self, tmp_path):
        store = _seed(tmp_path)
        srv.acquire_serve_lock(store, "sess1")
        with pytest.raises(srv.SessionAlreadyServed):
            srv.acquire_serve_lock(store, "sess1")

    def test_stale_dead_pid_lock_is_reclaimed(self, tmp_path):
        store = _seed(tmp_path)
        marker = store.session_dir("sess1") / ".serve.lock"
        marker.write_text("999999")  # a PID that is not alive
        # self-heals rather than blocking forever
        got = srv.acquire_serve_lock(store, "sess1")
        assert got == marker and marker.read_text().strip() == str(__import__("os").getpid())
