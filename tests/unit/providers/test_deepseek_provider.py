"""Unit tests for the DeepSeek provider (FR-12).

Covers: registry resolution (builtin path), infra-fail-compatible error on missing
key, agent base_url, real (non-fallback) pricing, and provider->model mapping.
"""

import pytest
from unittest.mock import patch

from startd8.providers import ProviderRegistry
from startd8.providers.deepseek import DeepSeekProvider
from startd8.agents import OpenAICompatibleAgent
from startd8.exceptions import ConfigurationError
from startd8.costs.pricing import PricingService
from startd8.benchmark_matrix.runner import is_infra_error


class TestDeepSeekProvider:
    def test_provider_properties(self):
        p = DeepSeekProvider()
        assert p.name == "deepseek"
        assert p.display_name == "DeepSeek"
        assert "deepseek-chat" in p.supported_models

    def test_create_agent_pins_endpoint(self):
        p = DeepSeekProvider()
        agent = p.create_agent("deepseek-chat", api_key="test-key")
        assert isinstance(agent, OpenAICompatibleAgent)
        assert agent.base_url == "https://api.deepseek.com/v1"

    def test_create_agent_default_name(self):
        agent = DeepSeekProvider().create_agent("deepseek-chat", api_key="k")
        assert agent.name == "deepseek-deepseek-chat"

    def test_validate_config_with_key(self):
        assert DeepSeekProvider().validate_config({"api_key": "k"}) is True

    def test_validate_config_without_key_is_infra_error(self):
        """Missing key must raise a message the benchmark classifies as infra_fail (FR-3)."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError, match="API key required") as exc:
                DeepSeekProvider().validate_config({})
        assert is_infra_error(str(exc.value)) is True

    def test_required_env_vars(self):
        assert DeepSeekProvider().get_required_env_vars() == ["DEEPSEEK_API_KEY"]

    def test_reasoner_capability(self):
        caps = DeepSeekProvider().get_capabilities("deepseek-reasoner")
        assert "reasoning" in caps


class TestDeepSeekRegistration:
    def test_resolves_via_registry(self):
        """FR-2: registry yields the provider (entry-point or builtin fallback)."""
        ProviderRegistry.discover()
        provider = ProviderRegistry.get_provider("deepseek")
        assert provider is not None
        assert provider.name == "deepseek"


class TestDeepSeekPricing:
    def test_pricing_present_and_real(self):
        """FR-4: a concrete entry exists (not the flagged unknown-model fallback)."""
        svc = PricingService()
        pricing = svc.get_pricing("deepseek-chat")
        assert pricing is not None
        assert pricing.provider == "deepseek"
        assert pricing.input_cost_per_million > 0
        assert pricing.output_cost_per_million > 0

    def test_provider_for_model(self):
        """FR-8."""
        assert PricingService().get_provider_for_model("deepseek-chat") == "deepseek"
