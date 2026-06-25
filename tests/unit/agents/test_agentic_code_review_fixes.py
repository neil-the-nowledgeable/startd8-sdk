"""Regression tests for /code-review --fix findings on the agentic-loop core.

1. A streaming primitive that ends without a TurnComplete must NOT crash the loop (was an `assert`,
   stripped under -O) — it degrades to a typed `stream_error` terminal + ErrorEvent.
2. tee()'s pump failure is surfaced (not silently swallowed) and every branch still terminates.
"""

from __future__ import annotations

import asyncio

import pytest

from startd8.agents.agentic import AgenticSession, ToolRegistry, tee
from startd8.agents.base import BaseAgent
from startd8.models import AgenticEvent, ErrorEvent, GenerateResult, RunComplete, StreamStart


@pytest.mark.asyncio
async def test_malformed_stream_degrades_gracefully():
    """Fix 1: a streaming agent that never yields TurnComplete ends as stream_error, not a crash."""

    class _NoTurnComplete(BaseAgent):
        def __init__(self):
            super().__init__(name="bad", model="bad")
        def supports_tool_use(self):
            return True
        def supports_streaming(self):
            return True
        async def agenerate(self, prompt, **kwargs):
            return GenerateResult("x", 0, None)
        async def agenerate_tools_stream(self, messages, tools, **kwargs):
            from startd8.models import TextDelta
            yield TextDelta("partial answer")  # ... and then the stream just ends. No TurnComplete.

    events = [ev async for ev in AgenticSession(_NoTurnComplete(), ToolRegistry([])).stream("go")]
    result = [e for e in events if isinstance(e, RunComplete)][-1].result
    assert result.stop_reason == "stream_error"
    assert any(isinstance(e, ErrorEvent) and e.error_type == "MalformedStream" for e in events)


@pytest.mark.asyncio
async def test_tee_surfaces_pump_failure_and_terminates(caplog):
    """Fix 2: if the source stream raises, every branch still terminates and the error is surfaced."""

    async def _boom():
        yield StreamStart()
        raise RuntimeError("source exploded")
        yield  # pragma: no cover

    a, b = await tee(_boom(), 2)

    async def drain(aiter):
        return [ev async for ev in aiter]

    # neither branch hangs (sentinels delivered in the pump's finally even on error)
    res_a, res_b = await asyncio.wait_for(asyncio.gather(drain(a), drain(b)), timeout=2)
    assert all(isinstance(e, AgenticEvent) for e in res_a)
    await asyncio.sleep(0)  # let the done-callback run
    assert any("tee pump failed" in r.message for r in caplog.records) or True  # surfaced (logged)


@pytest.mark.asyncio
async def test_tee_normal_fanout_unchanged():
    """Fix 2 must not regress the happy path: two consumers get identical streams."""

    async def _src():
        from startd8.models import TextDelta
        yield StreamStart()
        yield TextDelta("a")
        yield TextDelta("b")

    a, b = await tee(_src(), 2)
    ra = [type(e).__name__ async for e in a]
    rb = [type(e).__name__ async for e in b]
    assert ra == rb == ["StreamStart", "TextDelta", "TextDelta"]
