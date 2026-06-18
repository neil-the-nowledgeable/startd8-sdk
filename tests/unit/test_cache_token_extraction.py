"""Cross-vendor cached-token extraction (cost-accuracy fix).

OpenAI/Gemini/DeepSeek fold cached prompt tokens INTO their prompt-token count (unlike Anthropic,
which reports them separately). The agents must extract the cached subset AND subtract it from the
`input` they record, so the cost model (input @ full rate, cache_read @ 0.1x) doesn't double-charge.
These tests cover the extraction helper and the subtraction/pricing arithmetic without a live API.
"""
from __future__ import annotations

from types import SimpleNamespace

from startd8.agents.openai import _cached_input_tokens


def test_openai_dialect_prompt_tokens_details():
    usage = SimpleNamespace(prompt_tokens=1000,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=600))
    assert _cached_input_tokens(usage) == 600


def test_deepseek_dialect_prompt_cache_hit_tokens():
    usage = SimpleNamespace(prompt_tokens=1000, prompt_cache_hit_tokens=400)
    assert _cached_input_tokens(usage) == 400


def test_no_cache_fields_returns_zero():
    assert _cached_input_tokens(SimpleNamespace(prompt_tokens=1000)) == 0
    # details present but no cached_tokens
    assert _cached_input_tokens(SimpleNamespace(prompt_tokens_details=SimpleNamespace())) == 0
    # malformed value degrades to 0
    assert _cached_input_tokens(SimpleNamespace(prompt_cache_hit_tokens="oops")) == 0


def test_subtraction_avoids_double_counting_in_pricing():
    """input must be NON-cached; cache_read priced at 0.1x. The correct (subtracted) split must cost
    LESS than charging all prompt tokens at full input rate, and must not exceed it."""
    from startd8.costs.pricing import PricingService

    pricing = PricingService()
    model = "gpt-5.5"  # any priced OpenAI-family model
    if pricing.get_pricing(model) is None:
        import pytest
        pytest.skip("model not in pricing table")

    prompt, cached, output = 1000, 600, 200
    # Correct: input = non-cached (400), cache_read = 600 @ 0.1x
    correct = pricing.calculate_cost_breakdown(
        model, input_tokens=prompt - cached, output_tokens=output,
        cache_read_input_tokens=cached)
    # Naive double-count bug: input = full 1000 AND cache_read = 600
    naive = pricing.calculate_cost_breakdown(
        model, input_tokens=prompt, output_tokens=output,
        cache_read_input_tokens=cached)
    # Full-price-everything (no cache awareness at all)
    full = pricing.calculate_cost_breakdown(model, input_tokens=prompt, output_tokens=output)

    # calculate_cost_breakdown returns (input_side_cost, output_cost)
    correct_total = sum(correct)
    naive_total = sum(naive)
    full_total = sum(full)

    assert correct_total < full_total          # caching saves money
    assert correct_total < naive_total          # the bug would over-charge
    # the over-charge equals pricing the cached tokens twice (full input + 0.1x cache)
    assert naive_total > correct_total
