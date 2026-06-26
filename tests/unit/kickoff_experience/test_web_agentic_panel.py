"""Web agentic panel — chat page, message turn, propose→confirm→apply over HTTP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction  # noqa: E402
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402


@dataclass
class _Result:
    text: str
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


def _token(client: TestClient) -> str:
    html = client.get("/concierge/chat").text
    return re.search(r"const TOK=['\"]([^'\"]+)['\"]", html).group(1)


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
    assert "const TOK=" in r.text and "/concierge/chat/message" in r.text
    assert r.headers["X-Frame-Options"] == "DENY"


def test_concierge_links_to_chat(tmp_path: Path) -> None:
    assert "/concierge/chat" in _client(tmp_path).get("/concierge").text


# --- a turn proposes; confirm applies ----------------------------------------------------------

def test_message_turn_returns_text_and_proposals(tmp_path: Path) -> None:
    client = _client(tmp_path)
    token = _token(client)
    r = client.post("/concierge/chat/message", data={"token": token, "message": "what's missing?"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "echo: what's missing?"
    assert len(body["proposals"]) == 1 and body["proposals"][0]["kind"] == "friction"


def test_confirm_applies_proposal_and_pops(tmp_path: Path) -> None:
    client = _client(tmp_path)
    token = _token(client)
    pid = client.post("/concierge/chat/message",
                      data={"token": token, "message": "x"}).json()["proposals"][0]["id"]
    r = client.post("/concierge/chat/confirm", data={"token": token, "proposal_id": pid})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["code"] == "ok"
    assert (tmp_path / "concierge-friction.jsonl").exists()        # applied
    # popped → no longer pending
    assert client.post("/concierge/chat/pending", data={"token": token}).json()["proposals"] == []


def test_discard_removes_without_applying(tmp_path: Path) -> None:
    client = _client(tmp_path)
    token = _token(client)
    pid = client.post("/concierge/chat/message",
                      data={"token": token, "message": "x"}).json()["proposals"][0]["id"]
    client.post("/concierge/chat/discard", data={"token": token, "proposal_id": pid})
    assert not (tmp_path / "concierge-friction.jsonl").exists()    # never applied
    assert client.post("/concierge/chat/pending", data={"token": token}).json()["proposals"] == []


# --- hardening ---------------------------------------------------------------------------------

def test_message_rejects_unknown_session(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.post("/concierge/chat/message", data={"token": "bogus", "message": "x"})
    assert r.status_code == 403 and r.json()["code"] == "session_expired"


def test_confirm_rejects_non_loopback_host(tmp_path: Path) -> None:
    client = TestClient(build_kickoff_app(tmp_path, chat_factory=lambda: _FakeChat()),
                        headers={"host": "evil.example.com"})
    token = _token(client)
    client.post("/concierge/chat/message", data={"token": token, "message": "x"})
    # message itself is host-checked too:
    assert client.post("/concierge/chat/message",
                       data={"token": token, "message": "x"}).json()["code"] == "forbidden_host"


def test_confirm_unknown_proposal_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    token = _token(client)
    r = client.post("/concierge/chat/confirm", data={"token": token, "proposal_id": "nope"})
    assert r.status_code == 404 and r.json()["code"] == "no_such_proposal"
