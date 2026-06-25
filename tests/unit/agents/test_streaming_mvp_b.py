"""Streaming MVP-B: robust tool-call delta accumulation (FR-S3) + ToolCallDelta/ReasoningDelta
events + the FR-S4 usage-fallback budget guard. All faked-chunk / mock, $0."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from startd8.agents.claude import ClaudeAgent
from startd8.agents.openai import GPT4Agent
from startd8.agents.mock import MockAgent
from startd8.agents.agentic import AgenticSession, SessionConfig, ToolRegistry
from startd8.agents.base import BaseAgent
from startd8.models import (
    AgenticTurn, ReasoningDelta, TextDelta, ToolCallDelta, ToolCallRequest, TokenUsage, TurnComplete,
)


# --------------------------------------------------------------- OpenAI accumulator (FR-S3 cases)
def _oa_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)], usage=usage)


def _tcd(index, id=None, name=None, args=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))


async def _run_openai_stream(chunks):
    agent = GPT4Agent(model="gpt-5.5-pro", api_key="x")

    class _Stream:
        def __aiter__(self):
            async def _gen():
                for c in chunks:
                    yield c
            return _gen()

    async def fake_create(**kwargs):
        return _Stream()

    agent.async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    return [ev async for ev in agent.agenerate_tools_stream("hi", tools=[{"type": "function", "function": {"name": "x"}}])]


@pytest.mark.asyncio
async def test_fr_s3_a_nonmonotonic_indices():
    """Index is the key, not arrival order — interleaved indices 0/1 reassemble correctly."""
    events = await _run_openai_stream([
        _oa_chunk(tool_calls=[_tcd(0, id="c0", name="alpha", args='{"a":')]),
        _oa_chunk(tool_calls=[_tcd(1, id="c1", name="beta", args='{"b":')]),
        _oa_chunk(tool_calls=[_tcd(0, args=' 1}')]),   # back to index 0
        _oa_chunk(tool_calls=[_tcd(1, args=' 2}')]),
        _oa_chunk(finish_reason="tool_calls"),
    ])
    turn = [e for e in events if isinstance(e, TurnComplete)][-1].turn
    assert turn.tool_calls == [
        ToolCallRequest("c0", "alpha", {"a": 1}),
        ToolCallRequest("c1", "beta", {"b": 2}),
    ]


@pytest.mark.asyncio
async def test_fr_s3_c_zero_arg_call_not_dropped():
    """id+name but no argument deltas → {} and the call is NOT dropped."""
    events = await _run_openai_stream([
        _oa_chunk(tool_calls=[_tcd(0, id="c0", name="noargs")]),
        _oa_chunk(finish_reason="tool_calls"),
    ])
    turn = [e for e in events if isinstance(e, TurnComplete)][-1].turn
    assert turn.tool_calls == [ToolCallRequest("c0", "noargs", {})]


@pytest.mark.asyncio
async def test_fr_s3_d_valid_only_after_last_fragment():
    """Arguments parse only at the end, never mid-accumulation (no partial-JSON parse)."""
    events = await _run_openai_stream([
        _oa_chunk(tool_calls=[_tcd(0, id="c0", name="x", args='{"deep":')]),
        _oa_chunk(tool_calls=[_tcd(0, args=' {"k": [1,')]),
        _oa_chunk(tool_calls=[_tcd(0, args=' 2]}}')]),
        _oa_chunk(finish_reason="tool_calls"),
    ])
    turn = [e for e in events if isinstance(e, TurnComplete)][-1].turn
    assert turn.tool_calls == [ToolCallRequest("c0", "x", {"deep": {"k": [1, 2]}})]


@pytest.mark.asyncio
async def test_fr_s3_e_truncated_midcall_preserves_id_name():
    """Stream ends mid-tool-call → args {} but id+name preserved so the loop can still thread/dispatch."""
    events = await _run_openai_stream([
        _oa_chunk(tool_calls=[_tcd(0, id="c0", name="x", args='{"partial":')]),  # never completed
    ])
    turn = [e for e in events if isinstance(e, TurnComplete)][-1].turn
    assert turn.tool_calls == [ToolCallRequest("c0", "x", {})]


@pytest.mark.asyncio
async def test_openai_emits_tool_call_deltas():
    """MVP-B: argument fragments surface as ToolCallDelta as they stream."""
    events = await _run_openai_stream([
        _oa_chunk(tool_calls=[_tcd(0, id="c0", name="x", args='{"a":')]),
        _oa_chunk(tool_calls=[_tcd(0, args=' 1}')]),
        _oa_chunk(finish_reason="tool_calls"),
    ])
    deltas = [e for e in events if isinstance(e, ToolCallDelta)]
    assert [d.partial_args for d in deltas] == ['{"a":', ' 1}']
    assert deltas[0].id == "c0" and deltas[0].name == "x"


# --------------------------------------------------------------- Claude tool/reasoning deltas
@pytest.mark.asyncio
async def test_claude_emits_tool_call_and_reasoning_deltas():
    agent = ClaudeAgent(model="claude-sonnet-4-6", api_key="x")
    final = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id="t1", name="survey", input={"p": "."})],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=5, output_tokens=3,
                              cache_creation_input_tokens=None, cache_read_input_tokens=None),
    )

    events_in = [
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="thinking_delta", thinking="hmm ")),
        SimpleNamespace(type="content_block_start",
                        content_block=SimpleNamespace(type="tool_use", id="t1", name="survey")),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", partial_json='{"p":')),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", partial_json=' "."}')),
    ]

    class _Stream:
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False
        def __aiter__(self):
            async def _gen():
                for ev in events_in:
                    yield ev
            return _gen()
        async def get_final_message(self): return final

    agent.async_client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: _Stream()))
    events = [ev async for ev in agent.agenerate_tools_stream("hi", tools=[{"name": "survey", "input_schema": {}}])]

    assert any(isinstance(e, ReasoningDelta) and e.text == "hmm " for e in events)
    tcds = [e for e in events if isinstance(e, ToolCallDelta)]
    assert [d.partial_args for d in tcds] == ['{"p":', ' "."}']
    assert all(d.id == "t1" and d.name == "survey" for d in tcds)
    # final turn still assembled correctly from get_final_message
    turn = [e for e in events if isinstance(e, TurnComplete)][-1].turn
    assert turn.tool_calls == [ToolCallRequest("t1", "survey", {"p": "."})]


# --------------------------------------------------------------- FR-S4 budget-bypass guard
@pytest.mark.asyncio
async def test_fr_s4_missing_usage_does_not_bypass_budget():
    """A turn with no token_usage still advances the budget via an estimate (else the loop overspends)."""

    class _NoUsageAgent(BaseAgent):
        def __init__(self): super().__init__(name="nu", model="nu"); self.calls = 0
        def supports_tool_use(self): return True
        def supports_streaming(self): return True
        async def agenerate(self, prompt, **kwargs):
            from startd8.models import GenerateResult
            return GenerateResult("x", 0, None)
        async def agenerate_tools_stream(self, messages, tools, **kwargs):
            self.calls += 1
            # a long answer but NO usage object on the turn
            yield TextDelta("word " * 40)
            yield TurnComplete(AgenticTurn("word " * 40, [], None, "end_turn", 0))

    from startd8.models import RunComplete
    agent = _NoUsageAgent()
    session = AgenticSession(agent, ToolRegistry([]), config=SessionConfig(max_total_tokens=10))
    events = [ev async for ev in session.stream("go")]  # streaming path (agent is streaming-only)
    result = [e for e in events if isinstance(e, RunComplete)][-1].result
    # without the guard, total_tokens would stay 0 and the loop would never stop on budget
    assert session.total_tokens > 0
    assert result.ok  # one final-text turn completes normally; estimate just advanced the counter


# --------------------------------------------------------------- session forwards the new events
@pytest.mark.asyncio
async def test_session_stream_forwards_new_event_types():
    """The loop forwards ToolCallDelta/ReasoningDelta through stream() unchanged (no special-casing)."""

    class _DeltaAgent(BaseAgent):
        def __init__(self): super().__init__(name="d", model="d")
        def supports_tool_use(self): return True
        def supports_streaming(self): return True
        async def agenerate(self, prompt, **kwargs):
            from startd8.models import GenerateResult
            return GenerateResult("x", 0, None)
        async def agenerate_tools_stream(self, messages, tools, **kwargs):
            yield ReasoningDelta("thinking")
            yield TextDelta("answer")
            yield TurnComplete(AgenticTurn("answer", [], TokenUsage(input=1, output=1, total=2, model_name="d"),
                                           "end_turn", 0))

    events = [ev async for ev in AgenticSession(_DeltaAgent(), ToolRegistry([])).stream("go")]
    assert any(isinstance(e, ReasoningDelta) for e in events)
    assert any(isinstance(e, TextDelta) for e in events)
