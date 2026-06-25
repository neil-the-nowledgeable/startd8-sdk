"""TUI agentic chat (FR-10): opt-in gate, multi-turn memory, sync bridge, empty-tools guard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from startd8.agents.mock import MockAgent
from startd8.models import GenerateResult
from startd8.tui.agentic_chat import (
    agentic_mode_enabled,
    cost_suffix,
    make_chat_session,
    reply,
)


def _bare_agent():
    from startd8.agents.base import BaseAgent

    class _Bare(BaseAgent):
        async def agenerate(self, prompt, **kwargs):
            return GenerateResult("x", 0, None)

    return _Bare(name="bare", model="bare")


# --- FR-10 opt-in + capability gate --------------------------------------------------------------
def test_mode_disabled_by_default(monkeypatch):
    monkeypatch.delenv("STARTD8_TUI_AGENTIC", raising=False)
    assert agentic_mode_enabled(MockAgent(model="mock-model")) is False


def test_mode_requires_both_flag_and_capability(monkeypatch):
    monkeypatch.setenv("STARTD8_TUI_AGENTIC", "1")
    assert agentic_mode_enabled(MockAgent(model="mock-model")) is True  # capable + opted in
    assert agentic_mode_enabled(_bare_agent()) is False  # opted in but NOT tool-capable
    monkeypatch.setenv("STARTD8_TUI_AGENTIC", "0")
    assert agentic_mode_enabled(MockAgent(model="mock-model")) is False  # capable but opted out


# --- FR-10 multi-turn memory: history persists across reply() calls -------------------------------
def test_chat_session_remembers_prior_turns():
    agent = MockAgent(model="mock-model")  # no script -> each turn returns a terminal final-text turn
    session = make_chat_session(agent, system_prompt="be brief")

    r1 = reply(session, "first question")
    r2 = reply(session, "second question")

    assert r1.ok and r2.ok
    # the session transcript accumulated both exchanges (user+assistant x2)
    roles = [m["role"] for m in session.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    # the model SAW the prior history on the second call (stateless REPL never did)
    second_call_messages = agent.tool_calls_received[1]
    assert any(m.get("content") == "first question" for m in second_call_messages)


def test_cost_suffix_format():
    agent = MockAgent(model="mock-model")
    session = make_chat_session(agent)
    r = reply(session, "hi")
    s = cost_suffix(r)
    assert "tokens:" in s and "cost≈$" in s and "turn" in s


# --- empty-tools guard: a tool-less session must not send tools=[] to the provider ---------------
@pytest.mark.asyncio
async def test_openai_omits_empty_tools(monkeypatch):
    from startd8.agents.openai import GPT4Agent

    agent = GPT4Agent(model="gpt-5.5-pro", api_key="test-key-not-used")
    seen = {}

    class _Completions:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=None), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2,
                                      prompt_tokens_details=None),
            )

    agent.async_client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    turn = await agent.agenerate_tools("hi", tools=[])
    assert turn.text == "ok"
    assert "tools" not in seen  # empty tool set must be omitted (OpenAI rejects tools=[])


@pytest.mark.asyncio
async def test_claude_omits_empty_tools(monkeypatch):
    from startd8.agents.claude import ClaudeAgent

    agent = ClaudeAgent(model="claude-sonnet-4-6", api_key="test-key-not-used")
    seen = {}

    async def fake_call(prompt=None, messages=None, tools=None, **kwargs):
        seen["tools"] = tools
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                                  cache_creation_input_tokens=None, cache_read_input_tokens=None),
        )

    monkeypatch.setattr(agent, "_make_api_call", fake_call)
    turn = await agent.agenerate_tools("hi", tools=[])
    assert turn.text == "ok"
    assert seen["tools"] is None  # empty tool set -> None, so _make_api_call omits the kwarg
