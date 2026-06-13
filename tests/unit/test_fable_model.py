"""Claude Fable 5 catalog and provider wiring."""

from startd8.model_catalog import Models, get_model_info, is_known_model
from startd8.providers.anthropic import AnthropicProvider, normalize_anthropic_model_id
from startd8.providers.registry import ProviderRegistry
from startd8.costs.pricing import PricingService


def test_fable_in_model_catalog():
    assert Models.CLAUDE_FABLE_LATEST == "anthropic:claude-fable-5"
    info = get_model_info("claude-fable-5")
    assert info is not None
    assert info.tier == "flagship"
    assert is_known_model("anthropic:claude-fable-5")


def test_fable_in_anthropic_hardcoded_models():
    assert "claude-fable-5" in AnthropicProvider.HARDCODED_MODELS
    info = AnthropicProvider().get_model_info("claude-fable-5")
    assert info is not None
    assert info["max_output_tokens"] == 128000


def test_fable_model_alias_normalization():
    assert normalize_anthropic_model_id("fable-5") == "claude-fable-5"
    assert normalize_anthropic_model_id("claude-fable") == "claude-fable-5"
    assert normalize_anthropic_model_id("claude-fable-5") == "claude-fable-5"


def test_fable_pricing():
    pricing = PricingService()
    record = pricing.get_pricing("claude-fable-5")
    assert record is not None
    assert record.input_cost_per_million == 10.0
    assert record.output_cost_per_million == 50.0


def test_find_provider_for_fable_by_prefix():
    ProviderRegistry.discover()
    provider = ProviderRegistry.find_provider_for_model("claude-fable-5")
    assert provider is not None
    assert provider.name == "anthropic"
