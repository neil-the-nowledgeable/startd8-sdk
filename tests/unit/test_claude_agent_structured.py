"""
M-A — ClaudeAgent structured (tool-use) output + ValidationError retry.

Covers FR-MA-1's SDK prerequisite: a sibling structured-output path that leaves the 3-field
``GenerateResult`` arity untouched (the 77-unpack-site constraint), forces a tool call, validates
against a Pydantic schema, and retries exactly once on a ``ValidationError`` feeding the error back.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel


class Metric(BaseModel):
    """A single extracted metric (name + integer count)."""

    name: str
    count: int


def _tool_response(tool_input, *, stop_reason="tool_use"):
    """Build a mock Anthropic response carrying a single tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input
    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(input_tokens=11, output_tokens=7)
    response.usage.cache_creation_input_tokens = None
    response.usage.cache_read_input_tokens = None
    response.stop_reason = stop_reason
    return response


def _make_agent():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        from startd8.agents import ClaudeAgent

        agent = ClaudeAgent(name="test", model="claude-3-opus-20240229")
    agent.async_client = MagicMock()
    return agent


@pytest.mark.asyncio
async def test_structured_valid_first_attempt():
    """A valid tool call returns a validated model + a raw GenerateResult; one API call."""
    agent = _make_agent()
    agent.async_client.messages.create = AsyncMock(
        return_value=_tool_response({"name": "signups", "count": 42})
    )

    value, raw = await agent.agenerate_structured("extract", Metric)

    assert isinstance(value, Metric)
    assert value.name == "signups" and value.count == 42
    # raw is a 3-tuple GenerateResult — unchanged contract
    text, time_ms, usage = raw
    assert usage.input == 11 and usage.output == 7
    assert "signups" in text  # text is the validated model's JSON
    agent.async_client.messages.create.assert_called_once()
    # the forced tool call carried tools + tool_choice
    _, kwargs = agent.async_client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": "Metric"}
    assert kwargs["tools"][0]["name"] == "Metric"


@pytest.mark.asyncio
async def test_structured_retries_once_on_validation_error():
    """An invalid first response triggers exactly one retry, then succeeds."""
    agent = _make_agent()
    agent.async_client.messages.create = AsyncMock(
        side_effect=[
            _tool_response({"name": "signups", "count": "not-an-int"}),  # ValidationError
            _tool_response({"name": "signups", "count": 42}),  # corrected
        ]
    )

    value, raw = await agent.agenerate_structured("extract", Metric)

    assert value.count == 42
    assert agent.async_client.messages.create.call_count == 2
    # the retry prompt fed the validation error back
    second_call_prompt = agent.async_client.messages.create.call_args_list[1].kwargs["messages"][0]["content"]
    assert "failed schema validation" in second_call_prompt


@pytest.mark.asyncio
async def test_structured_raises_after_one_retry_exhausted():
    """Two invalid responses → raise (caller decides how to fail non-destructively); no 3rd call."""
    from pydantic import ValidationError

    agent = _make_agent()
    agent.async_client.messages.create = AsyncMock(
        return_value=_tool_response({"name": "x", "count": "nope"})
    )

    with pytest.raises(ValidationError):
        await agent.agenerate_structured("extract", Metric)
    assert agent.async_client.messages.create.call_count == 2  # initial + one retry only


@pytest.mark.asyncio
async def test_no_retry_when_disabled():
    """retry_on_validation=False makes exactly one attempt."""
    from pydantic import ValidationError

    agent = _make_agent()
    agent.async_client.messages.create = AsyncMock(
        return_value=_tool_response({"name": "x", "count": "nope"})
    )

    with pytest.raises(ValidationError):
        await agent.agenerate_structured("extract", Metric, retry_on_validation=False)
    agent.async_client.messages.create.assert_called_once()


def test_generate_result_arity_unchanged():
    """Regression guard: GenerateResult stays a 3-tuple; StructuredResult is a 2-tuple sibling."""
    from startd8.models import GenerateResult, StructuredResult

    gr = GenerateResult("text", 5, None)
    a, b, c = gr  # must still unpack as 3
    assert (a, b, c) == ("text", 5, None)
    assert len(gr) == 3

    sr = StructuredResult(Metric(name="x", count=1), gr)
    value, raw = sr  # 2-tuple
    assert isinstance(value, Metric) and raw is gr


@pytest.mark.asyncio
async def test_unsupported_provider_raises_not_implemented():
    """A provider without tool-use support reports NotImplementedError, not a silent pass."""
    from startd8.agents.mock import MockAgent

    agent = MockAgent(name="m", model="mock-model")
    with pytest.raises(NotImplementedError):
        await agent.agenerate_structured("extract", Metric)


@pytest.mark.asyncio
async def test_rejects_non_pydantic_schema():
    agent = _make_agent()
    with pytest.raises(TypeError):
        await agent.agenerate_structured("extract", dict)
