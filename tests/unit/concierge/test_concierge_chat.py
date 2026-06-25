"""Concierge conversational front-end (FR-12/FR-13/FR-14) — read-only posture is inviolable.

Driven by the MockAgent tool-use double: scripts the model calling survey/assess and asserts the
posture holds at both enforcement layers, real read-only data flows back, and cost is disclosed.
"""

from __future__ import annotations

import pytest

from startd8.agents.mock import MockAgent
from startd8.concierge import ConciergeError, handle_concierge_read
from startd8.concierge.chat import (
    POSTURE_BANNER,
    build_concierge_registry,
    new_concierge_chat,
)


# --- FR-13 layer 2: the dispatch floor hard-rejects non-read actions -----------------------------
@pytest.mark.parametrize("action", ["instantiate-kickoff", "log-friction", "derive-contract", "bogus"])
def test_dispatch_floor_refuses_non_read_actions(tmp_path, action):
    with pytest.raises(ConciergeError) as exc:
        handle_concierge_read(action, str(tmp_path))
    assert "read-only" in str(exc.value)


def test_dispatch_floor_allows_read_actions(tmp_path):
    out = handle_concierge_read("survey", str(tmp_path))
    assert out["schema_version"] >= 1  # real survey ran


# --- FR-13 layer 1: the registry exposes exactly the two read tools ------------------------------
def test_registry_is_exactly_two_read_tools(tmp_path):
    reg = build_concierge_registry(str(tmp_path))
    assert len(reg) == 2
    assert reg.names() == {"survey", "assess"}
    assert reg.allow_effect_classes == {"read"}


# --- FR-12: the loop answers an onboarding question by calling a read tool ------------------------
@pytest.mark.asyncio
async def test_chat_answers_via_survey(tmp_path):
    # a project dir with nothing in it still surveys cleanly
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"text": "let me look", "tool_calls": [("c1", "survey", {})]},
            {"text": "Here is what I found about your project's readiness.", "tool_calls": []},
        ],
    )
    chat = new_concierge_chat(agent, str(tmp_path))
    assert "assist, not operate" in chat.banner()

    result = await chat.ask("how ready is my project?")
    assert result.ok and result.stop_reason == "completed"
    assert "readiness" in result.text
    # a real survey result (schema-versioned dict) came back as a tool message
    assert any(m.get("role") == "tool" and "schema_version" in m.get("content", "") for m in result.messages)

    # FR-14: cost is disclosed and labeled read-only
    line = chat.cost_line(result)
    assert "read-only" in line and "tokens=" in line and "cost≈$" in line


# --- FR-13 end-to-end: even if the model *tries* a write tool name, nothing writes ---------------
@pytest.mark.asyncio
async def test_model_cannot_invoke_a_write_action(tmp_path):
    # The model hallucinates an effectful tool name; it isn't registered, so the loop returns a
    # tool-error (FR-9 unknown-tool) and never reaches any write path.
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"tool_calls": [("c1", "log-friction", {"friction": "x"})]},  # not in the registry
            {"text": "I can only survey and assess — writes go through the CLI.", "tool_calls": []},
        ],
    )
    chat = new_concierge_chat(agent, str(tmp_path))
    result = await chat.ask("log this friction for me")
    assert result.stop_reason == "completed"
    assert any(
        m.get("role") == "tool" and "unknown tool 'log-friction'" in m.get("content", "")
        for m in result.messages
    )


# --- regression: existing concierge public API is intact -----------------------------------------
def test_handle_concierge_read_is_public():
    import startd8.concierge as c

    assert hasattr(c, "handle_concierge_read")
    assert "handle_concierge_read" in c.__all__
