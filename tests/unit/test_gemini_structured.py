"""GeminiAgent.agenerate_structured — controlled-generation structured output.

Unblocks gemini as a structured pipeline role / generated-app DEFAULT_AGENT_SPEC.
No live API: the client's generate_content is mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

pytest.importorskip("google.genai")

from startd8.agents.gemini import GeminiAgent  # noqa: E402
from startd8.models import StructuredResult  # noqa: E402


class _Sentiment(BaseModel):
    label: str
    score: float


def _agent() -> GeminiAgent:
    agent = GeminiAgent(name="g", model="gemini-2.5-flash", api_key="test-key")
    agent.client = MagicMock()
    return agent


def _resp(text: str, in_tok: int = 10, out_tok: int = 5) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.usage_metadata = MagicMock(
        prompt_token_count=in_tok,
        candidates_token_count=out_tok,
        total_token_count=in_tok + out_tok,
    )
    return r


@pytest.mark.asyncio
async def test_structured_validates_and_returns():
    agent = _agent()
    agent.client.models.generate_content.return_value = _resp('{"label": "pos", "score": 0.9}')
    result = await agent.agenerate_structured("rate it", _Sentiment)
    assert isinstance(result, StructuredResult)
    value, raw = result
    assert isinstance(value, _Sentiment)
    assert value.label == "pos" and value.score == 0.9
    assert raw.token_usage.input == 10 and raw.token_usage.output == 5
    # response_schema + JSON mime were requested
    cfg = agent.client.models.generate_content.call_args.kwargs["config"]
    assert getattr(cfg, "response_mime_type", None) == "application/json"
    assert getattr(cfg, "response_schema", None) is _Sentiment


@pytest.mark.asyncio
async def test_structured_retries_once_then_succeeds():
    agent = _agent()
    agent.client.models.generate_content.side_effect = [
        _resp('{"label": "pos"}'),                 # missing `score` → ValidationError
        _resp('{"label": "pos", "score": 0.9}'),   # corrected
    ]
    value, _ = await agent.agenerate_structured("rate it", _Sentiment)
    assert value.score == 0.9
    assert agent.client.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_structured_raises_after_retry_exhausted():
    agent = _agent()
    agent.client.models.generate_content.return_value = _resp('{"label": "pos"}')  # always invalid
    with pytest.raises(Exception):  # ValidationError surfaced for non-destructive upstream handling
        await agent.agenerate_structured("rate it", _Sentiment)
    assert agent.client.models.generate_content.call_count == 2  # one retry


@pytest.mark.asyncio
async def test_structured_no_retry_when_disabled():
    agent = _agent()
    agent.client.models.generate_content.return_value = _resp('{"label": "pos"}')
    with pytest.raises(Exception):
        await agent.agenerate_structured("rate it", _Sentiment, retry_on_validation=False)
    assert agent.client.models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_structured_rejects_non_pydantic_schema():
    agent = _agent()
    with pytest.raises(TypeError):
        await agent.agenerate_structured("x", dict)


def test_sync_generate_structured_wrapper():
    agent = _agent()
    agent.client.models.generate_content.return_value = _resp('{"label": "neg", "score": 0.1}')
    value, raw = agent.generate_structured("rate it", _Sentiment)
    assert value.label == "neg"
