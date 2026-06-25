"""OTel spans for the agentic loop (FR-18) — asserted via an in-memory span exporter (no API spend).

These run with the OTel SDK active (do NOT set OTEL_SDK_DISABLED for this module)."""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from startd8.agents.mock import MockAgent
from startd8.agents.agentic import AgenticSession, SessionConfig, ToolRegistry, ToolSpec
from startd8.agents.base import BaseAgent
from startd8.models import AgenticTurn, GenerateResult, TokenUsage


@pytest.fixture
def spans(monkeypatch):
    """Attach an in-memory exporter to the active tracer provider; yields a getter for spans by name."""
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    def by_name(name):
        return [s for s in exporter.get_finished_spans() if s.name == name]

    return by_name


def _echo_tool(log):
    def handler(args):
        log.append(args)
        return "echo: " + str(args)

    return ToolSpec("echo", "echo args", {"type": "object"}, handler, effect_class="read")


@pytest.mark.asyncio
async def test_session_turn_and_tool_spans_emitted(spans):
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"tool_calls": [("c1", "echo", {"x": 1})]},
            {"text": "done", "tool_calls": []},
        ],
    )
    session = AgenticSession(agent, ToolRegistry([_echo_tool([])]))
    result = await session.send("go")
    assert result.ok

    # session span: one, stamped with the final outcome
    sess = spans("agentic.session")
    assert len(sess) == 1
    attrs = sess[0].attributes
    assert attrs["agentic.stop_reason"] == "completed"
    assert attrs["agentic.turns"] == 2
    assert attrs["agentic.model"] == "mock-model"
    assert "agentic.total_tokens" in attrs

    # turn spans: two (tool turn + final turn)
    assert len(spans("agentic.turn")) == 2

    # one tool_call span, tagged with the tool + success
    tool_spans = spans("agentic.tool_call")
    assert len(tool_spans) == 1
    assert tool_spans[0].attributes["agentic.tool"] == "echo"
    assert tool_spans[0].attributes["agentic.tool_ok"] is True


@pytest.mark.asyncio
async def test_session_span_records_budget_stop(spans):
    agent = MockAgent(
        model="mock-model",
        tool_turns=[{"tool_calls": [("c%d" % i, "echo", {"i": i})]} for i in range(6)],
    )
    session = AgenticSession(agent, ToolRegistry([_echo_tool([])]),
                             config=SessionConfig(max_total_tokens=3))
    result = await session.send("loop")
    assert result.stop_reason == "budget"
    assert spans("agentic.session")[0].attributes["agentic.stop_reason"] == "budget"


@pytest.mark.asyncio
async def test_compaction_span_emitted_on_overflow(spans):
    class _OverflowOnce(BaseAgent):
        def __init__(self):
            super().__init__(name="of", model="of-model")
            self.calls = 0

        def supports_tool_use(self):
            return True

        async def agenerate(self, prompt, **kwargs):
            return GenerateResult("SUMMARY", 0, None)

        async def agenerate_tools(self, messages, tools, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("prompt is too long")
            return AgenticTurn("ok", [], TokenUsage(input=1, output=1, total=2, model_name="of-model"),
                               "end_turn", 0)

    session = AgenticSession(_OverflowOnce(), ToolRegistry([]),
                             config=SessionConfig(compact_keep_recent=2))
    session.messages = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    result = await session.send("q")
    assert result.ok
    assert len(spans("agentic.compaction")) == 1
    assert spans("agentic.compaction")[0].attributes["agentic.compaction_attempt"] == 1
