"""Streaming MVP-A (FR-2): AgenticSession.stream() event flow, fallback, overflow, sync-bridge, tee.

All driven by the MockAgent streaming double (FR-S0a) — zero API spend."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from startd8.agents.mock import MockAgent
from startd8.agents.agentic import (
    AgenticSession, SessionConfig, ToolRegistry, ToolSpec, stream_sync, tee,
)
from startd8.agents.base import BaseAgent
from startd8.models import (
    AgenticEvent, AgenticTurn, GenerateResult, RunComplete, StreamReset, StreamStart,
    TextDelta, ToolCallResult, ToolCallStarted, TokenUsage, TurnComplete,
)


def _echo_tool(log):
    def handler(args):
        log.append(args)
        return "echo"
    return ToolSpec("echo", "echo", {"type": "object"}, handler, effect_class="read")


async def _collect(aiter):
    return [ev async for ev in aiter]


@pytest.mark.asyncio
async def test_stream_text_then_tool_then_complete():
    """Canonical event sequence for a one-tool turn (FR-S5 acceptance)."""
    invoked = []
    agent = MockAgent(model="mock-model", streaming=True, tool_turns=[
        {"text": "let me check", "tool_calls": [("c1", "echo", {"x": 1})]},
        {"text": "all good", "tool_calls": []},
    ])
    session = AgenticSession(agent, ToolRegistry([_echo_tool(invoked)]))
    events = await _collect(session.stream("go"))

    types = [type(e).__name__ for e in events]
    assert types[0] == "StreamStart"
    # turn 1: text deltas, then the tool pair, then TurnComplete; turn 2: text, TurnComplete; RunComplete
    assert "TextDelta" in types
    assert types.index("ToolCallStarted") < types.index("ToolCallResult")
    assert isinstance(events[-1], RunComplete) and events[-1].result.ok
    # live text actually streamed as multiple deltas
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(deltas).startswith("let me check")
    assert invoked == [{"x": 1}]  # the tool really ran


@pytest.mark.asyncio
async def test_fallback_non_streaming_agent_is_uniform():
    """FR-S6: a non-streaming agent still yields the same event shape (one TextDelta + tool events)."""
    invoked = []
    agent = MockAgent(model="mock-model", streaming=False, tool_turns=[  # streaming OFF
        {"text": "checking", "tool_calls": [("c1", "echo", {})]},
        {"text": "done", "tool_calls": []},
    ])
    assert agent.supports_streaming() is False
    events = await _collect(AgenticSession(agent, ToolRegistry([_echo_tool(invoked)])).stream("go"))
    types = [type(e).__name__ for e in events]
    assert "TextDelta" in types and "ToolCallStarted" in types and "ToolCallResult" in types
    assert isinstance(events[-1], RunComplete) and events[-1].result.ok


@pytest.mark.asyncio
async def test_stream_budget_stop():
    agent = MockAgent(model="mock-model", streaming=True,
                      tool_turns=[{"tool_calls": [("c%d" % i, "echo", {"i": i})]} for i in range(6)])
    events = await _collect(AgenticSession(
        agent, ToolRegistry([_echo_tool([])]), config=SessionConfig(max_total_tokens=3)).stream("go"))
    assert isinstance(events[-1], RunComplete) and events[-1].result.stop_reason == "budget"


@pytest.mark.asyncio
async def test_stream_overflow_emits_reset_then_recovers():
    """FR-S9: overflow on the first call → StreamReset + CompactionEvent, then the retry succeeds."""

    class _OverflowOnce(BaseAgent):
        def __init__(self):
            super().__init__(name="of", model="of-model")
            self.calls = 0
        def supports_tool_use(self): return True
        def supports_streaming(self): return True
        async def agenerate(self, prompt, **kwargs): return GenerateResult("SUMMARY", 0, None)
        async def agenerate_tools_stream(self, messages, tools, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("prompt is too long")
            yield TextDelta("recovered ")
            yield TurnComplete(AgenticTurn("recovered", [], TokenUsage(input=1, output=1, total=2,
                              model_name="of-model"), "end_turn", 0))

    session = AgenticSession(_OverflowOnce(), ToolRegistry([]),
                             config=SessionConfig(compact_keep_recent=2))
    session.messages = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    events = await _collect(session.stream("q"))
    types = [type(e).__name__ for e in events]
    assert "StreamReset" in types and "CompactionEvent" in types
    assert isinstance(events[-1], RunComplete) and events[-1].result.ok


def test_stream_sync_bridge():
    """FR-S5a: a synchronous caller can drive the async stream (the TUI's entry point)."""
    agent = MockAgent(model="mock-model", streaming=True, tool_turns=[{"text": "hi there", "tool_calls": []}])
    session = AgenticSession(agent, ToolRegistry([]))
    events = list(stream_sync(session.stream("go")))  # NOTE: sync iteration, no await
    assert isinstance(events[0], StreamStart)
    assert isinstance(events[-1], RunComplete)
    assert "".join(e.text for e in events if isinstance(e, TextDelta)).strip() == "hi there"


@pytest.mark.asyncio
async def test_tee_fans_out_to_two_consumers():
    """FR-S7: two consumers each receive every event; a slow one doesn't starve the other."""
    agent = MockAgent(model="mock-model", streaming=True, tool_turns=[{"text": "one two three", "tool_calls": []}])
    session = AgenticSession(agent, ToolRegistry([]))
    a, b = await tee(session.stream("go"), 2)

    async def slow(aiter):
        out = []
        async for ev in aiter:
            await asyncio.sleep(0)  # simulate a slower consumer
            out.append(ev)
        return out

    res_a, res_b = await asyncio.gather(_collect(a), slow(b))
    assert [type(e).__name__ for e in res_a] == [type(e).__name__ for e in res_b]  # identical streams
    assert isinstance(res_a[-1], RunComplete) and isinstance(res_b[-1], RunComplete)


def test_events_share_a_typed_base():
    """FR-S1: closed union — every event is an AgenticEvent (so AsyncIterator[AgenticEvent] is real)."""
    for ev in (StreamStart(), TextDelta("x"), ToolCallStarted("i", "n"), ToolCallResult("i", "n", True),
               StreamReset("r"), TurnComplete(None), RunComplete(None)):
        assert isinstance(ev, AgenticEvent)


def test_fr_s12_no_contextcore_import_in_agentic_modules():
    """FR-S12: the loop/streaming modules import nothing from integrations.contextcore (only the
    io.contextcore.* attribute *strings* from FR-18 are allowed)."""
    root = Path(__file__).resolve().parents[3] / "src" / "startd8" / "agents"
    for name in ("agentic.py", "agentic_otel.py", "compaction.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert not re.search(r"import.*integrations\.contextcore", src), f"{name} imports contextcore"
