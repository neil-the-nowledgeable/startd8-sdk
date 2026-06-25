"""Increment 1 — end-to-end AgenticSession loop tests, driven by the MockAgent tool-use double.

Each scenario scripts the model's turns (FR-0a) and asserts the loop's behavior: tool dispatch,
the FR-9 unknown-tool reject, FR-19 effect-class default-deny, FR-16 result redaction, and the
FR-15 safety bounds (max_turns, repeated-call breaker, budget).
"""

from __future__ import annotations

import pytest

from startd8.agents.mock import MockAgent
from startd8.agents.agentic import (
    AgenticSession,
    SessionConfig,
    ToolRegistry,
    ToolSpec,
    UnsupportedToolUseError,
    apply_result_policy,
)


def _survey_tool(calls_log: list) -> ToolSpec:
    def handler(args: dict) -> str:
        calls_log.append(args)
        return f"survey ran on {args.get('project_root', '?')}"

    return ToolSpec(
        name="survey", description="survey a project",
        parameters={"type": "object", "properties": {"project_root": {"type": "string"}}},
        handler=handler, effect_class="read",
    )


@pytest.mark.asyncio
async def test_loop_runs_tool_then_completes():
    invoked: list = []
    registry = ToolRegistry([_survey_tool(invoked)])
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"text": "let me check", "tool_calls": [("c1", "survey", {"project_root": "."})]},
            {"text": "The project is ready.", "tool_calls": []},
        ],
    )
    session = AgenticSession(agent, registry, system_prompt="be helpful")
    result = await session.send("how ready is it?")

    assert result.ok and result.stop_reason == "completed"
    assert result.text == "The project is ready."
    assert result.turns == 2
    assert invoked == [{"project_root": "."}]  # the handler actually ran
    # a tool-result message landed back in the transcript (OpenAI dialect for MockAgent)
    assert any(m.get("role") == "tool" and "survey ran on ." in m.get("content", "") for m in result.messages)


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected_not_executed():
    invoked: list = []
    registry = ToolRegistry([_survey_tool(invoked)])
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"tool_calls": [("c1", "ghost_tool", {"x": 1})]},  # not registered
            {"text": "done anyway", "tool_calls": []},
        ],
    )
    result = await AgenticSession(agent, registry).send("go")
    assert result.stop_reason == "completed"
    assert invoked == []  # real tool never ran
    assert any("unknown tool 'ghost_tool'" in m.get("content", "") for m in result.messages if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_effect_class_default_deny():
    """FR-19: a write tool is denied unless its class is allow-listed; handler must not run."""
    ran: list = []

    def deleter(args: dict) -> str:
        ran.append(args)
        return "deleted!"

    write_tool = ToolSpec("delete_all", "danger", {"type": "object"}, deleter, effect_class="write")
    registry = ToolRegistry([write_tool])  # default allow = {"read"} only
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"tool_calls": [("c1", "delete_all", {})]},
            {"text": "ok", "tool_calls": []},
        ],
    )
    result = await AgenticSession(agent, registry).send("clean up")
    assert ran == []  # the write handler was NEVER invoked
    assert any("not permitted by policy" in m.get("content", "") for m in result.messages if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_max_turns_bound():
    """Distinct args each turn (so the repeated-call breaker doesn't fire first) > max_turns."""
    registry = ToolRegistry([_survey_tool([])])
    agent = MockAgent(
        model="mock-model",
        tool_turns=[{"tool_calls": [("c%d" % i, "survey", {"project_root": str(i)})]} for i in range(10)],
    )
    result = await AgenticSession(agent, registry, config=SessionConfig(max_turns=3)).send("loop")
    assert result.stop_reason == "max_turns"
    assert result.turns == 3


@pytest.mark.asyncio
async def test_repeated_call_breaker():
    """Same (name, args) beyond the limit halts the loop (guards the {}-degraded doom loop)."""
    registry = ToolRegistry([_survey_tool([])])
    agent = MockAgent(
        model="mock-model",
        tool_turns=[{"tool_calls": [("c", "survey", {"project_root": "."})]} for _ in range(10)],
    )
    result = await AgenticSession(agent, registry, config=SessionConfig(repeated_call_limit=2)).send("spin")
    assert result.stop_reason == "repeated_calls"


@pytest.mark.asyncio
async def test_token_budget_stops_before_next_call():
    """FR-15: per-session token ceiling checked before each model re-entry."""
    registry = ToolRegistry([_survey_tool([])])
    # each scripted turn reports total=2 tokens (mock shorthand); distinct args avoid the breaker
    agent = MockAgent(
        model="mock-model",
        tool_turns=[{"tool_calls": [("c%d" % i, "survey", {"project_root": str(i)})]} for i in range(10)],
    )
    result = await AgenticSession(agent, registry, config=SessionConfig(max_total_tokens=3)).send("go")
    assert result.stop_reason == "budget"
    # turn1 spends 2 (<3, continues); before turn2... still 2<3 runs; after turn2 total=4>=3 → stop before turn3
    assert result.total_tokens >= 3


@pytest.mark.asyncio
async def test_unsupported_agent_rejected():
    from startd8.agents.base import BaseAgent
    from startd8.models import GenerateResult

    class _Bare(BaseAgent):
        async def agenerate(self, prompt, **kwargs):
            return GenerateResult("x", 0, None)

    with pytest.raises(UnsupportedToolUseError):
        AgenticSession(_Bare(name="bare", model="bare"), ToolRegistry([]))


def test_result_policy_redacts_and_caps():
    """FR-16: secrets redacted, oversize content truncated."""
    clean, trunc = apply_result_policy("key=sk-ABCDEFGH12345678 rest")
    assert "sk-ABCDEFGH" not in clean and "[REDACTED]" in clean and trunc is False
    big, trunc2 = apply_result_policy("x" * 100, max_bytes=20)
    assert trunc2 is True and "…[truncated]" in big
