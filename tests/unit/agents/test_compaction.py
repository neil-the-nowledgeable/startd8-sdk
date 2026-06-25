"""Compaction + context-overflow (FR-3/FR-4).

The centerpiece is the tool_use<->tool_result pairing invariant (OQ-6): compaction must never orphan
a call from its result. Tested directly on both provider dialects, plus the FR-3 detector and an
end-to-end loop that recovers from an overflow on the first call.
"""

from __future__ import annotations

import pytest

from startd8.agents.compaction import (
    compact,
    find_clean_cut,
    is_context_window_error,
    pairing_is_valid,
)
from startd8.agents.agentic import AgenticSession, SessionConfig, ToolRegistry
from startd8.agents.base import BaseAgent
from startd8.models import AgenticTurn, GenerateResult, TokenUsage, ToolCallRequest


# --- FR-3 detection -------------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "Error: This model's maximum context length is 200000 tokens",
    "openai.BadRequestError: context_length_exceeded",
    "anthropic: prompt is too long: 250000 tokens > 200000",
    "request exceeds the maximum context window",
])
def test_detector_recognizes_overflow(msg):
    assert is_context_window_error(RuntimeError(msg)) is True


def test_detector_ignores_unrelated_errors():
    assert is_context_window_error(ValueError("invalid api key")) is False
    assert is_context_window_error(TimeoutError("timed out")) is False


def test_detector_follows_wrapping_chain():
    inner = RuntimeError("prompt is too long")
    outer = RuntimeError("API call failed")
    outer.__cause__ = inner
    assert is_context_window_error(outer) is True


# --- pairing invariant (anthropic dialect) --------------------------------------------------------
def _anthropic_transcript():
    return [
        {"role": "user", "content": "do A"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ra"}]},
        {"role": "user", "content": "do B"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "y", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "rb"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
    ]


def test_pairing_valid_and_orphan_detection_anthropic():
    msgs = _anthropic_transcript()
    assert pairing_is_valid(msgs, "anthropic") is True
    # an orphaned result (its tool_use removed) must be detected
    orphaned = msgs[2:]  # starts with a tool_result whose tool_use (t1) was dropped
    assert pairing_is_valid(orphaned, "anthropic") is False


def test_clean_cut_never_orphans_anthropic():
    msgs = _anthropic_transcript()
    # naive "keep last 2" would start the tail at a tool_result (index 5) -> orphan; the clean cut
    # must move earlier so t2's tool_use is kept with its result.
    cut = find_clean_cut(msgs, "anthropic", keep_recent=2)
    tail = msgs[cut:]
    assert pairing_is_valid(tail, "anthropic") is True


@pytest.mark.asyncio
async def test_compact_preserves_pairing_anthropic():
    msgs = _anthropic_transcript()

    async def summarizer(_text: str) -> str:
        return "earlier: did A and B"

    out = await compact(msgs, "anthropic", summarizer, keep_recent=2)
    assert len(out) < len(msgs)
    assert out[0]["role"] == "user" and "summarized" in out[0]["content"]
    assert pairing_is_valid(out, "anthropic") is True  # the invariant holds post-compaction


# --- pairing invariant (openai dialect) -----------------------------------------------------------
def test_clean_cut_never_orphans_openai():
    msgs = [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "x", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "ra"},
        {"role": "assistant", "content": "ok"},
    ]
    cut = find_clean_cut(msgs, "openai", keep_recent=1)  # naive tail would be the lone tool msg? no
    assert pairing_is_valid(msgs[cut:], "openai") is True


# --- end-to-end: the loop recovers from an overflow on the first call -----------------------------
class _OverflowThenAnswerAgent(BaseAgent):
    """Raises a context-overflow on the first tool call, succeeds after compaction."""

    def __init__(self):
        super().__init__(name="of", model="of-model")
        self.calls = 0
        self.compacted_history_seen = None

    def supports_tool_use(self) -> bool:
        return True

    async def agenerate(self, prompt, **kwargs):  # used by _summarize
        return GenerateResult("SUMMARY", 0, None)

    async def agenerate_tools(self, messages, tools, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("prompt is too long: exceeds the maximum context length")
        # second call: compaction already ran; record what the model now sees
        self.compacted_history_seen = list(messages)
        return AgenticTurn(
            "recovered", [], TokenUsage(input=1, output=1, total=2, model_name="of-model"), "end_turn", 0
        )


@pytest.mark.asyncio
async def test_loop_recovers_from_overflow_via_compaction():
    agent = _OverflowThenAnswerAgent()
    session = AgenticSession(agent, ToolRegistry([]), config=SessionConfig(compact_keep_recent=2))
    # seed a long-ish history so there is something to compact
    session.messages = [{"role": "user", "content": f"msg {i}"} for i in range(8)]

    result = await session.send("final question")
    assert result.ok and result.text == "recovered"
    assert agent.calls == 2  # overflowed, compacted, retried
    # the retried call saw a compacted (shorter) transcript starting with the summary
    assert any("summarized" in m.get("content", "") for m in agent.compacted_history_seen)


@pytest.mark.asyncio
async def test_loop_gives_up_when_cannot_compact_further():
    """A persistent overflow with nothing left to compact ends as context_overflow, not a crash."""

    class _AlwaysOverflow(BaseAgent):
        def __init__(self):
            super().__init__(name="ao", model="ao")

        def supports_tool_use(self):
            return True

        async def agenerate(self, prompt, **kwargs):
            return GenerateResult("S", 0, None)

        async def agenerate_tools(self, messages, tools, **kwargs):
            raise RuntimeError("prompt is too long")

    session = AgenticSession(_AlwaysOverflow(), ToolRegistry([]),
                             config=SessionConfig(compact_keep_recent=2, max_compactions=2))
    session.messages = [{"role": "user", "content": f"m{i}"} for i in range(6)]
    result = await session.send("go")
    assert result.stop_reason == "context_overflow"  # graceful terminal, no exception escaped
