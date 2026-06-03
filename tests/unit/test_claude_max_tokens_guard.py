"""M-G — non-streaming max_tokens ceiling guard (landmine L12).

49152 tripped Anthropic's ">10-min streaming required" guard and 500'd; 32768 (the default) is safe.
The guard clamps anything above the verified-safe ceiling so no caller can re-trigger that class —
with zero effect on calls at or below it.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from startd8.agents.claude import NONSTREAMING_MAX_TOKENS_CEILING


def _agent(max_tokens):
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        from startd8.agents import ClaudeAgent

        agent = ClaudeAgent(name="t", model="claude-opus-4-8", max_tokens=max_tokens)
    resp = MagicMock()
    resp.content = [MagicMock(text="ok")]
    resp.usage = MagicMock(input_tokens=1, output_tokens=1)
    resp.usage.cache_creation_input_tokens = None
    resp.usage.cache_read_input_tokens = None
    resp.stop_reason = "end_turn"
    agent.async_client = MagicMock()
    agent.async_client.messages.create = AsyncMock(return_value=resp)
    return agent


def test_ceiling_is_the_verified_safe_value():
    assert NONSTREAMING_MAX_TOKENS_CEILING == 32768


@pytest.mark.asyncio
async def test_oversized_max_tokens_is_clamped():
    agent = _agent(49152)  # the value that 500'd
    await agent.agenerate("hi")
    sent = agent.async_client.messages.create.call_args.kwargs["max_tokens"]
    assert sent == NONSTREAMING_MAX_TOKENS_CEILING  # clamped, not 49152


@pytest.mark.asyncio
async def test_safe_max_tokens_passes_through_unchanged():
    agent = _agent(8192)
    await agent.agenerate("hi")
    assert agent.async_client.messages.create.call_args.kwargs["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_default_32768_is_not_clamped():
    agent = _agent(32768)  # the SDK/code-gen default — must remain unchanged
    await agent.agenerate("hi")
    assert agent.async_client.messages.create.call_args.kwargs["max_tokens"] == 32768


@pytest.mark.asyncio
async def test_per_call_override_is_also_guarded():
    agent = _agent(8192)
    await agent.agenerate("hi", max_tokens=64000)
    assert agent.async_client.messages.create.call_args.kwargs["max_tokens"] == NONSTREAMING_MAX_TOKENS_CEILING
