"""Web agentic panel — chat page, message turn, propose→confirm→apply over HTTP."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction  # noqa: E402
from startd8.kickoff_experience.telemetry import (  # noqa: E402
    EV_CHAT_REFUSED,
    EV_CHAT_TURN,
    record_events,
)
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402


@dataclass
class _Result:
    text: str
    stop_reason: str = "completed"
    turns: int = 1
    total_tokens: int = 5
    total_cost_usd: float = 0.001


class _FakeChat:
    """A fake agentic chat: each turn 'proposes' a friction entry into a real ProposalBuffer."""

    def __init__(self) -> None:
        self.buffer = ProposalBuffer()
        self._n = 0

    async def ask(self, message: str) -> _Result:
        self._n += 1
        self.buffer.add(ProposedAction(
            "friction", {"friction": "grammar gap", "what_happened": "needs reformat",
                         "implication": "F-4 path"}, id=f"p{self._n}"))
        return _Result(text=f"echo: {message}")

    def banner(self) -> str:
        return "BANNER"

    def cost_line(self, result: _Result) -> str:
        return f"cost={result.total_cost_usd}"


def _client(tmp_path: Path, *, enabled: bool = True) -> TestClient:
    factory = (lambda: _FakeChat()) if enabled else None
    return TestClient(build_kickoff_app(tmp_path, chat_factory=factory),
                      headers={"host": "127.0.0.1:8000"})


def _csrf(client: TestClient) -> str:
    """Load the chat page (sets the httponly kickoff_chat + kickoff_csrf cookies on the client) and
    return the rendered CSRF write token. The chat session id rides the cookie automatically."""
    html = client.get("/concierge/chat").text
    return re.search(r"const CSRF=['\"]([^'\"]+)['\"]", html).group(1)


# --- enablement --------------------------------------------------------------------------------

def test_panel_disabled_without_agent(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=False)
    r = client.get("/concierge/chat")
    assert r.status_code == 200
    assert "not enabled" in r.text.lower()


def test_panel_page_renders_when_enabled(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/concierge/chat")
    assert r.status_code == 200
    assert "const CSRF=" in r.text and "/concierge/chat/message" in r.text
    assert r.headers["X-Frame-Options"] == "DENY"


def test_chat_session_cookie_is_separate_from_csrf(tmp_path: Path) -> None:
    # FR-WM2-5a: two distinct httponly+strict cookies; the chat sid is NOT the csrf token.
    client = _client(tmp_path)
    r = client.get("/concierge/chat")
    setc = r.headers.get_list("set-cookie")
    chat_c = next(c for c in setc if c.startswith("kickoff_chat="))
    csrf_c = next(c for c in setc if c.startswith("kickoff_csrf="))
    for c in (chat_c, csrf_c):
        assert "HttpOnly" in c and "SameSite=strict" in c.replace("Strict", "strict")
    chat_val = chat_c.split(";")[0].split("=", 1)[1]
    csrf_val = csrf_c.split(";")[0].split("=", 1)[1]
    rendered_csrf = re.search(r"const CSRF=['\"]([^'\"]+)['\"]", r.text).group(1)
    assert chat_val and csrf_val and chat_val != csrf_val      # distinct secrets
    assert rendered_csrf == csrf_val and rendered_csrf != chat_val  # the chat sid is never in the page


def test_concierge_links_to_chat(tmp_path: Path) -> None:
    assert "/concierge/chat" in _client(tmp_path).get("/concierge").text


# --- a turn proposes; confirm applies ----------------------------------------------------------

def test_message_turn_returns_text_and_proposals(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _csrf(client)   # loads the page → kickoff_chat cookie is now on the client
    r = client.post("/concierge/chat/message", data={"message": "what's missing?"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "echo: what's missing?"
    assert len(body["proposals"]) == 1 and body["proposals"][0]["kind"] == "friction"
    # FR-WM2-9 / R3-F7: cost is a stable structured block, not a bare string.
    cost = body["cost"]
    assert isinstance(cost, dict)
    assert set(cost) == {"turns", "tokens", "usd", "stop_reason", "line"}
    assert cost["stop_reason"] == "completed" and isinstance(cost["tokens"], int)


def test_confirm_applies_proposal_and_pops(tmp_path: Path) -> None:
    client = _client(tmp_path)
    csrf = _csrf(client)
    pid = client.post("/concierge/chat/message",
                      data={"message": "x"}).json()["proposals"][0]["id"]
    r = client.post("/concierge/chat/confirm", data={"proposal_id": pid, "csrf": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["code"] == "ok"
    assert (tmp_path / "concierge-friction.jsonl").exists()        # applied
    # popped → no longer pending
    assert client.post("/concierge/chat/pending").json()["proposals"] == []


def test_discard_removes_without_applying(tmp_path: Path) -> None:
    client = _client(tmp_path)
    csrf = _csrf(client)
    pid = client.post("/concierge/chat/message",
                      data={"message": "x"}).json()["proposals"][0]["id"]
    client.post("/concierge/chat/discard", data={"proposal_id": pid, "csrf": csrf})
    assert not (tmp_path / "concierge-friction.jsonl").exists()    # never applied
    assert client.post("/concierge/chat/pending").json()["proposals"] == []


def test_chat_disabled_in_preview_mode(tmp_path: Path) -> None:
    # FR-WM2-8a: a read/preview serve must never spend LLM tokens on chat.
    client = TestClient(
        build_kickoff_app(tmp_path, chat_factory=lambda: _FakeChat(), mode="preview"),
        headers={"host": "127.0.0.1:8000"})
    page = client.get("/concierge/chat")
    assert page.status_code == 200 and "preview" in page.text.lower()
    assert "const CSRF=" not in page.text       # panel disabled → no live chat session issued
    # the spend path refuses before invoking the provider, even with no session cookie
    r = client.post("/concierge/chat/message", data={"message": "x"})
    assert r.status_code == 403 and r.json()["code"] == "preview_only"


# --- hardening (FR-WM2-5a) ---------------------------------------------------------------------

def test_message_rejects_unknown_session(tmp_path: Path) -> None:
    # A fresh client never loaded the chat page → no kickoff_chat cookie → typed chat_session_expired.
    client = _client(tmp_path)
    r = client.post("/concierge/chat/message", data={"message": "x"})
    assert r.status_code == 403 and r.json()["code"] == "chat_session_expired"


def test_csrf_alone_cannot_drive_chat(tmp_path: Path) -> None:
    # Having the CSRF token but not the kickoff_chat cookie must fail (the two are decoupled).
    client = _client(tmp_path)
    csrf = _csrf(client)
    client.cookies.delete("kickoff_chat")          # keep kickoff_csrf, drop the session cookie
    r = client.post("/concierge/chat/message", data={"message": "x"})
    assert r.status_code == 403 and r.json()["code"] == "chat_session_expired"
    # confirm too: csrf passes the write gate but there is no chat session
    r2 = client.post("/concierge/chat/confirm", data={"proposal_id": "p1", "csrf": csrf})
    assert r2.status_code == 403 and r2.json()["code"] == "chat_session_expired"


def test_confirm_rejects_non_loopback_host(tmp_path: Path) -> None:
    client = TestClient(build_kickoff_app(tmp_path, chat_factory=lambda: _FakeChat()),
                        headers={"host": "evil.example.com"})
    _csrf(client)
    # message itself is host-checked:
    assert client.post("/concierge/chat/message",
                       data={"message": "x"}).json()["code"] == "forbidden_host"


def test_confirm_unknown_proposal_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    csrf = _csrf(client)
    r = client.post("/concierge/chat/confirm", data={"proposal_id": "nope", "csrf": csrf})
    assert r.status_code == 404 and r.json()["code"] == "no_such_proposal"


# --- Phase 2: new-conversation reset (R4-F6) + OTel nesting (R3-S8) -----------------------------

def test_chat_reset_clears_history_and_reissues(tmp_path: Path) -> None:
    client = _client(tmp_path)
    csrf = _csrf(client)
    old_sid = client.cookies.get("kickoff_chat")
    client.post("/concierge/chat/message", data={"message": "x"})
    assert client.post("/concierge/chat/pending").json()["proposals"]        # something pending
    with record_events() as events:
        r = client.post("/concierge/chat/reset", data={"csrf": csrf})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert all(e.name != EV_CHAT_TURN for e in events)                       # no provider call
    new_sid = client.cookies.get("kickoff_chat")
    assert new_sid and new_sid != old_sid                                    # fresh session minted
    assert client.post("/concierge/chat/pending").json()["proposals"] == []  # clean thread


def test_chat_reset_requires_csrf(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _csrf(client)
    r = client.post("/concierge/chat/reset", data={"csrf": "bogus"})
    assert r.status_code == 403 and r.json()["code"] == "session_expired"


def test_chat_turn_nested_in_kickoff_span(tmp_path: Path, monkeypatch) -> None:
    # R3-S8: chat_turn is emitted INSIDE the kickoff span (so it + the agentic child spans attach to
    # one trace), not after the span closes.
    import contextlib

    from startd8.kickoff_experience import telemetry as tel

    active = {"in": False}
    emitted_inside: list = []

    @contextlib.contextmanager
    def _fake_span(name, **kw):
        active["in"] = True
        try:
            yield object()
        finally:
            active["in"] = False

    orig_emit = tel.emit

    def _rec_emit(name, **kw):
        if name == tel.EV_CHAT_TURN:
            emitted_inside.append(active["in"])
        return orig_emit(name, **kw)

    monkeypatch.setattr(tel, "kickoff_span", _fake_span)
    monkeypatch.setattr(tel, "emit", _rec_emit)
    client = _client(tmp_path)
    _csrf(client)
    client.post("/concierge/chat/message", data={"message": "x"})
    assert emitted_inside == [True]


# --- chat_message hardening (FR-WM2-5b / 5c / 8b / 8c / 14a) ------------------------------------

def test_message_too_long_rejected_before_provider(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _csrf(client)
    r = client.post("/concierge/chat/message", data={"message": "x" * 5000})
    assert r.status_code == 400 and r.json()["code"] == "message_too_long"   # FR-WM2-5b


def test_stop_reason_maps_to_typed_code(tmp_path: Path) -> None:
    class _BudgetChat(_FakeChat):
        async def ask(self, message: str) -> _Result:
            await super().ask(message)                       # populate the proposal buffer
            return _Result(text="partial", stop_reason="budget")

    client = TestClient(build_kickoff_app(tmp_path, chat_factory=lambda: _BudgetChat()),
                        headers={"host": "127.0.0.1:8000"})
    _csrf(client)
    r = client.post("/concierge/chat/message", data={"message": "x"})
    assert r.status_code == 200                              # FR-WM2-8b — never 500
    assert r.json()["ok"] is False and r.json()["code"] == "chat_budget_exceeded"
    assert r.json()["text"] == "partial"


def test_provider_error_degrades_without_500_or_leak(tmp_path: Path) -> None:
    class _BoomChat(_FakeChat):
        async def ask(self, message: str) -> _Result:
            raise RuntimeError("sk-ant-secret boom from provider")

    client = TestClient(build_kickoff_app(tmp_path, chat_factory=lambda: _BoomChat()),
                        headers={"host": "127.0.0.1:8000"})
    _csrf(client)
    r = client.post("/concierge/chat/message", data={"message": "x"})
    assert r.status_code == 200 and r.json()["code"] == "chat_error"   # FR-WM2-8c
    assert "sk-ant" not in r.text and "boom" not in r.text             # sanitized, no leak
    assert client.get("/").status_code == 200                          # home page unaffected


def test_chat_turn_event_emitted_without_message_text(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _csrf(client)
    with record_events() as events:
        client.post("/concierge/chat/message", data={"message": "secret question"})
    turns = [e for e in events if e.name == EV_CHAT_TURN]
    assert len(turns) == 1                                              # FR-WM2-14a
    attrs = turns[0].attributes
    assert attrs["stop_reason"] == "completed" and "tokens" in attrs
    assert "secret question" not in str(attrs)                         # privacy: no message text


def test_chat_budget_config_shared_and_applied(tmp_path: Path) -> None:
    # FR-WM2-9a / FR-WM2-15: both chat constructors default to one shared budget envelope.
    from startd8.kickoff_experience.chat import (
        kickoff_chat_session_config,
        new_agentic_kickoff_chat,
        new_kickoff_chat,
    )

    cfg = kickoff_chat_session_config()
    assert cfg.max_cost_usd is not None and cfg.max_total_tokens is not None and cfg.max_turns >= 1

    class _StubAgent:  # AgenticSession construction only stores the agent/registry/config
        def supports_tool_use(self) -> bool:
            return True

    web = new_agentic_kickoff_chat(_StubAgent(), tmp_path)
    cli = new_kickoff_chat(_StubAgent(), tmp_path)
    assert web.session.config.max_cost_usd == cfg.max_cost_usd
    assert cli.session.config.max_cost_usd == cfg.max_cost_usd
    assert web.session.config.max_tool_calls_per_turn == cfg.max_tool_calls_per_turn


def test_chat_idle_expiry_wipes_history(tmp_path: Path) -> None:
    # FR-WM2-5d: past the idle TTL the session is gone (chat_session_expired) and its history wiped.
    from types import SimpleNamespace

    class _ChatWithHistory(_FakeChat):
        def __init__(self) -> None:
            super().__init__()
            self.session = SimpleNamespace(messages=[{"role": "user", "content": "secret"}])

    chat = _ChatWithHistory()
    t = [1000.0]
    app = build_kickoff_app(tmp_path, chat_factory=lambda: chat, clock=lambda: t[0])
    client = TestClient(app, headers={"host": "127.0.0.1:8000"})
    client.get("/concierge/chat")                       # session created at t=1000
    assert client.post("/concierge/chat/message", data={"message": "x"}).json()["ok"] is True
    t[0] += 3600.0                                       # advance well past the 30-min idle TTL
    r = client.post("/concierge/chat/message", data={"message": "x"})
    assert r.status_code == 403 and r.json()["code"] == "chat_session_expired"
    assert chat.session.messages == []                  # history destroyed, RAM-only


@pytest.mark.asyncio
async def test_concurrent_message_returns_chat_busy(tmp_path: Path) -> None:
    release = asyncio.Event()

    class _SlowChat(_FakeChat):
        async def ask(self, message: str) -> _Result:
            await release.wait()                  # hold the per-session lock until the test releases
            return await super().ask(message)

    app = build_kickoff_app(tmp_path, chat_factory=lambda: _SlowChat())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000",
                                 headers={"host": "127.0.0.1:8000"}) as ac:
        await ac.get("/concierge/chat")           # sets the kickoff_chat cookie on the client
        first = asyncio.create_task(ac.post("/concierge/chat/message", data={"message": "a"}))
        await asyncio.sleep(0.05)                 # let `first` enter and acquire the session lock
        second = await ac.post("/concierge/chat/message", data={"message": "b"})
        assert second.status_code == 429 and second.json()["code"] == "chat_busy"   # FR-WM2-5c
        release.set()
        r1 = await first
        assert r1.status_code == 200 and r1.json()["ok"] is True
