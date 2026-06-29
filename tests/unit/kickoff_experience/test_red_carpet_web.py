"""Red Carpet Treatment — the web stage-rail (OQ-4: surfaced on /concierge/chat, not a new route).

A read-only `/red-carpet.json` endpoint backs a "Build progress" stage rail on the chat page; the
served chat can be the stage-aware Red Carpet conductor via `make_chat_factory(red_carpet=True)`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402


def _client(tmp_path: Path, *, chat: bool = True) -> TestClient:
    from startd8.kickoff_experience.proposals import ProposalBuffer

    class _Fake:
        def __init__(self) -> None:
            self.buffer = ProposalBuffer()

    factory = (lambda: _Fake()) if chat else None
    return TestClient(build_kickoff_app(tmp_path, chat_factory=factory),
                      headers={"host": "127.0.0.1:8000"})


def test_red_carpet_json_endpoint(tmp_path: Path) -> None:
    r = _client(tmp_path).get("/red-carpet.json")
    assert r.status_code == 200
    body = r.json()
    assert body["next_stage"] == "data_model" and body["cascade_offerable"] is False
    assert [s["key"] for s in body["stages"]] == ["data_model", "manifests", "value_inputs", "content", "run"]
    assert r.headers["X-Frame-Options"] == "DENY"          # same frame-deny posture as Concierge


def test_chat_page_renders_the_stage_rail(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/concierge/chat").text
    assert "id='rail'" in html                              # the rail container
    assert "/red-carpet.json" in html                       # fetched by the page
    assert "Build progress" in html                         # the rail heading
    assert "refreshRail()" in html                          # refreshed on load + after each turn


def test_red_carpet_json_available_without_chat(tmp_path: Path) -> None:
    # The stage map is $0/read-only and works even with the chat panel disabled.
    r = _client(tmp_path, chat=False).get("/red-carpet.json")
    assert r.status_code == 200 and "stages" in r.json()


def test_make_chat_factory_red_carpet_builds_staged_chat(tmp_path: Path) -> None:
    class _StubAgent:
        def supports_tool_use(self) -> bool:
            return True

    import startd8.kickoff_experience.serve as serve_mod

    # resolve_agent_spec is imported inside make_chat_factory; patch it to return our stub.
    import startd8.utils.agent_resolution as ar
    orig = ar.resolve_agent_spec
    ar.resolve_agent_spec = lambda _spec: _StubAgent()
    try:
        factory = serve_mod.make_chat_factory(tmp_path, "stub:model", red_carpet=True)
        assert factory is not None
        chat = factory()
        assert chat.red_carpet is True                      # the stage-aware conductor chat
        assert "red_carpet_state" in set(chat.session.registry._tools)
    finally:
        ar.resolve_agent_spec = orig
