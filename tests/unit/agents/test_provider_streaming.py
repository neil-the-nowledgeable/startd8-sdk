"""Per-token provider streaming (FR-S2) for Claude + OpenAI, via faked chunk streams (no API spend).

Asserts: live TextDeltas arrive incrementally, and the terminal TurnComplete carries an AgenticTurn
structurally equal to what the non-streaming path produces (parity)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from startd8.agents.claude import ClaudeAgent
from startd8.agents.openai import GPT4Agent
from startd8.models import AgenticTurn, TextDelta, ToolCallRequest, TurnComplete


# ----------------------------------------------------------------- Claude (Anthropic) stream
class _FakeAnthropicStream:
    """Async context manager mimicking anthropic's messages.stream()."""

    def __init__(self, text_chunks, final_message):
        self._text_chunks = text_chunks
        self._final = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):  # pragma: no cover - replaced by __aiter__ below
        ...

    def __aiter__(self):
        async def _gen():
            for t in self._text_chunks:
                yield SimpleNamespace(type="content_block_delta",
                                      delta=SimpleNamespace(type="text_delta", text=t))
        return _gen()

    async def get_final_message(self):
        return self._final


@pytest.mark.asyncio
async def test_claude_stream_yields_deltas_then_assembled_turn(monkeypatch):
    agent = ClaudeAgent(model="claude-sonnet-4-6", api_key="x")
    assert agent.supports_streaming() is True

    final = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Hello world"),
            SimpleNamespace(type="tool_use", id="t1", name="survey", input={"p": "."}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                              cache_creation_input_tokens=None, cache_read_input_tokens=None),
    )

    def fake_stream(**kwargs):
        assert "tool_choice" not in kwargs  # unforced
        return _FakeAnthropicStream(["Hello ", "world"], final)

    agent.async_client = SimpleNamespace(messages=SimpleNamespace(stream=fake_stream))

    events = [ev async for ev in agent.agenerate_tools_stream("hi", tools=[{"name": "survey", "input_schema": {}}])]
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Hello ", "world"]  # streamed incrementally
    tc = [e for e in events if isinstance(e, TurnComplete)][-1]
    assert isinstance(tc.turn, AgenticTurn)
    assert tc.turn.text == "Hello world"
    assert tc.turn.tool_calls == [ToolCallRequest("t1", "survey", {"p": "."})]  # assembled from final
    assert tc.turn.finish_reason == "tool_use"
    assert tc.turn.token_usage.input == 10


# ----------------------------------------------------------------- OpenAI stream
def _oa_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)


def _tc_delta(index, id=None, name=None, args=None):
    fn = SimpleNamespace(name=name, arguments=args)
    return SimpleNamespace(index=index, id=id, function=fn)


@pytest.mark.asyncio
async def test_openai_stream_accumulates_text_and_tool_calls(monkeypatch):
    agent = GPT4Agent(model="gpt-5.5-pro", api_key="x")
    assert agent.supports_streaming() is True

    # chunks: text "Hi"+" there", then a tool call fragmented across chunks, then usage chunk
    chunks = [
        _oa_chunk(content="Hi"),
        _oa_chunk(content=" there"),
        _oa_chunk(tool_calls=[_tc_delta(0, id="c1", name="survey", args='{"p":')]),
        _oa_chunk(tool_calls=[_tc_delta(0, args=' "."}')]),  # arguments built up across chunks
        _oa_chunk(finish_reason="tool_calls"),
        _oa_chunk(usage=SimpleNamespace(prompt_tokens=20, completion_tokens=4, total_tokens=24,
                                        prompt_tokens_details=None)),
    ]

    class _Stream:
        def __aiter__(self):
            async def _gen():
                for c in chunks:
                    yield c
            return _gen()

    async def fake_create(**kwargs):
        assert kwargs.get("stream") is True
        assert kwargs["stream_options"] == {"include_usage": True}
        return _Stream()

    agent.async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))

    events = [ev async for ev in agent.agenerate_tools_stream("hi", tools=[{"type": "function", "function": {"name": "survey"}}])]
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Hi", " there"]
    tc = [e for e in events if isinstance(e, TurnComplete)][-1].turn
    assert tc.text == "Hi there"
    # tool-call arguments reassembled from the two fragments → valid JSON
    assert tc.tool_calls == [ToolCallRequest("c1", "survey", {"p": "."})]
    assert tc.finish_reason == "tool_calls"
    assert tc.token_usage.total == 24


@pytest.mark.asyncio
async def test_openai_stream_degrades_malformed_tool_args(monkeypatch):
    agent = GPT4Agent(model="gpt-5.5-pro", api_key="x")
    chunks = [
        _oa_chunk(tool_calls=[_tc_delta(0, id="c1", name="x", args="not json")]),
        _oa_chunk(finish_reason="tool_calls"),
    ]

    class _Stream:
        def __aiter__(self):
            async def _gen():
                for c in chunks:
                    yield c
            return _gen()

    async def fake_create(**kwargs):
        return _Stream()

    agent.async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    events = [ev async for ev in agent.agenerate_tools_stream("hi", tools=[{"type": "function", "function": {"name": "x"}}])]
    tc = [e for e in events if isinstance(e, TurnComplete)][-1].turn
    assert tc.tool_calls == [ToolCallRequest("c1", "x", {})]  # malformed → {}, id+name preserved
