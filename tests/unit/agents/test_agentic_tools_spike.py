"""Increment-0 spike (FR-0): prove ClaudeAgent.agenerate_tools parses a tool-use turn.

This is the load-bearing assumption the whole agentic-loop design stands on — that the existing
`agenerate_structured` mechanism generalizes into a multi-tool, unforced primitive returning an
`AgenticTurn`. We monkeypatch `_make_api_call` to return a fake Anthropic-shaped response so the
parse is exercised with **no live API cost**.

See docs/design/agentic-loop/AGENTIC_LOOP_{REQUIREMENTS,PLAN}.md.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from startd8.agents.claude import ClaudeAgent
from startd8.models import AgenticTurn, ToolCallRequest


def _fake_response(*, text: str, tool_uses: list[dict], stop_reason: str):
    """Build a SimpleNamespace shaped like an Anthropic Messages response."""
    content = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    for tu in tool_uses:
        content.append(
            SimpleNamespace(type="tool_use", id=tu["id"], name=tu["name"], input=tu["input"])
        )
    usage = SimpleNamespace(
        input_tokens=120,
        output_tokens=45,
        cache_creation_input_tokens=30,
        cache_read_input_tokens=90,
    )
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


def _agent() -> ClaudeAgent:
    # API key only needs to be present for construction; we never make a real call.
    return ClaudeAgent(model="claude-sonnet-4-6", api_key="test-key-not-used")


@pytest.mark.asyncio
async def test_agenerate_tools_parses_multiple_tool_calls(monkeypatch):
    agent = _agent()
    assert agent.supports_tool_use() is True

    async def fake_call(prompt, **kwargs):
        # Two tools presented, no tool_choice forcing => kwargs must NOT contain tool_choice.
        assert "tool_choice" not in kwargs
        assert kwargs.get("tools") is not None
        return _fake_response(
            text="Let me look that up.",
            tool_uses=[
                {"id": "tu_1", "name": "survey", "input": {"project_root": "."}},
                {"id": "tu_2", "name": "assess", "input": {"project_root": ".", "deep": True}},
            ],
            stop_reason="tool_use",
        )

    monkeypatch.setattr(agent, "_make_api_call", fake_call)

    tools = [
        {"name": "survey", "description": "survey a project", "input_schema": {"type": "object"}},
        {"name": "assess", "description": "assess readiness", "input_schema": {"type": "object"}},
    ]
    turn = await agent.agenerate_tools("How ready is this project?", tools=tools)

    assert isinstance(turn, AgenticTurn)
    assert turn.text == "Let me look that up."
    assert turn.finish_reason == "tool_use"
    assert len(turn.tool_calls) == 2
    assert all(isinstance(tc, ToolCallRequest) for tc in turn.tool_calls)
    assert turn.tool_calls[0] == ToolCallRequest("tu_1", "survey", {"project_root": "."})
    assert turn.tool_calls[1].name == "assess"
    assert turn.tool_calls[1].arguments == {"project_root": ".", "deep": True}
    # cache-token telemetry flows through (FR-7 reuse)
    assert turn.token_usage is not None
    assert turn.token_usage.cache_read_input_tokens == 90
    assert turn.token_usage.cache_creation_input_tokens == 30


@pytest.mark.asyncio
async def test_agenerate_tools_final_text_no_tools(monkeypatch):
    """When the model answers directly, tool_calls is empty and finish_reason is the natural stop."""
    agent = _agent()

    async def fake_call(prompt, **kwargs):
        return _fake_response(text="The project is ready.", tool_uses=[], stop_reason="end_turn")

    monkeypatch.setattr(agent, "_make_api_call", fake_call)

    turn = await agent.agenerate_tools("status?", tools=[{"name": "noop", "input_schema": {}}])
    assert turn.text == "The project is ready."
    assert turn.tool_calls == []
    assert turn.finish_reason == "end_turn"


def _fake_openai_response(*, content, tool_calls: list[dict], finish_reason: str):
    """Build a SimpleNamespace shaped like an OpenAI chat-completions response.

    Key difference vs Anthropic: tool args arrive as a JSON **string** on function.arguments.
    """
    tcs = [
        SimpleNamespace(
            id=tc["id"],
            type="function",
            function=SimpleNamespace(name=tc["name"], arguments=tc["arguments"]),
        )
        for tc in tool_calls
    ]
    message = SimpleNamespace(content=content, tool_calls=tcs or None)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=200,
        completion_tokens=50,
        total_tokens=250,
        prompt_tokens_details=SimpleNamespace(cached_tokens=80),
    )
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.mark.asyncio
async def test_openai_agenerate_tools_parses_json_string_args(monkeypatch):
    """OpenAI adapter must json.loads the function.arguments string into a dict, and subtract
    folded cached tokens from input (OpenAI folds cache into prompt_tokens, unlike Anthropic)."""
    from startd8.agents.openai import GPT4Agent

    agent = GPT4Agent(model="gpt-5.5-pro", api_key="test-key-not-used")
    assert agent.supports_tool_use() is True

    fake = _fake_openai_response(
        content=None,
        tool_calls=[
            {"id": "call_1", "name": "survey", "arguments": '{"project_root": ".", "deep": true}'},
            {"id": "call_2", "name": "assess", "arguments": "not-valid-json"},  # must degrade to {}
        ],
        finish_reason="tool_calls",
    )

    class _Completions:
        async def create(self, **kwargs):
            assert "tool_choice" not in kwargs  # unforced
            assert kwargs.get("tools") is not None
            return fake

    agent.async_client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    tools = [{"type": "function", "function": {"name": "survey", "parameters": {"type": "object"}}}]
    turn = await agent.agenerate_tools("ready?", tools=tools)

    assert isinstance(turn, AgenticTurn)
    assert turn.text == ""  # content None -> ""
    assert turn.finish_reason == "tool_calls"
    assert len(turn.tool_calls) == 2
    assert turn.tool_calls[0] == ToolCallRequest("call_1", "survey", {"project_root": ".", "deep": True})
    assert turn.tool_calls[1].arguments == {}  # malformed JSON degraded, did not crash
    # OpenAI folds cached into prompt_tokens -> input must be net of cache (200 - 80)
    assert turn.token_usage.input == 120
    assert turn.token_usage.cache_read_input_tokens == 80


@pytest.mark.asyncio
async def test_base_agent_optin_default_is_unsupported():
    """The opt-in flag keeps the 10 existing providers untouched: default False + NotImplementedError."""
    from startd8.agents.base import BaseAgent

    # MockAgent (or any agent not implementing the primitive) must report unsupported.
    from startd8.agents.mock import MockAgent

    mock = MockAgent(model="mock-model")
    assert mock.supports_tool_use() is False
    with pytest.raises(NotImplementedError):
        await mock.agenerate_tools("hi", tools=[])
