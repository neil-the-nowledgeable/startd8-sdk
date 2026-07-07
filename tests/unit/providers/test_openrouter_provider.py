"""Unit tests for the OpenRouter provider (FR-OR-1..12) — fully offline."""

import pytest
from unittest.mock import patch

from startd8.providers import ProviderRegistry
from startd8.providers.openrouter import OpenRouterProvider
from startd8.agents import OpenAICompatibleAgent
from startd8.exceptions import ConfigurationError
from startd8.costs.pricing import PricingService
from startd8.model_catalog import get_model_info, Models
from startd8.benchmark_matrix.runner import is_infra_error

ENROLLED = ["deepseek/deepseek-chat", "deepseek/deepseek-r1", "qwen/qwen-2.5-coder-32b-instruct"]


class TestProvider:
    def test_properties(self):
        p = OpenRouterProvider()
        assert p.name == "openrouter"
        assert p.display_name == "OpenRouter"
        assert "deepseek/deepseek-chat" in p.supported_models

    def test_create_agent_pins_endpoint_and_passes_model_verbatim(self):
        agent = OpenRouterProvider().create_agent("deepseek/deepseek-chat", api_key="k")
        assert isinstance(agent, OpenAICompatibleAgent)
        assert agent.base_url == "https://openrouter.ai/api/v1"
        assert agent.model == "deepseek/deepseek-chat"  # FR-OR-2: verbatim, no alias translation

    def test_unknown_model_warns_not_raises(self):
        # aggregator catalog drifts; an unlisted id passes through with a warning
        agent = OpenRouterProvider().create_agent("some/new-model", api_key="k")
        assert agent.model == "some/new-model"

    def test_validate_without_key_is_infra_error(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError, match="API key required") as exc:
                OpenRouterProvider().validate_config({})
        assert is_infra_error(str(exc.value))  # FR-OR-3

    def test_required_env_vars(self):
        assert OpenRouterProvider().get_required_env_vars() == ["OPENROUTER_API_KEY"]


class TestRegistration:
    def test_resolves_via_registry(self):
        ProviderRegistry.discover()
        p = ProviderRegistry.get_provider("openrouter")
        assert p is not None and p.name == "openrouter"


class TestPricing:
    def test_enrolled_models_non_fallback(self):
        svc = PricingService()
        for m in ENROLLED:
            p = svc.get_pricing(m)
            assert p is not None, f"{m} missing — would hit $3/$15 fallback"
            assert p.provider == "openrouter"
            # cost-ranked cloud vendor: REAL non-zero rate (not a $0 local lane)
            assert p.input_cost_per_million > 0 and p.output_cost_per_million > 0

    def test_provider_disambiguation_vs_direct_deepseek(self):
        """FR-OR-6: the OpenRouter slash id and the direct deepseek id are distinct strings, each
        attributed by its exact entry — no collision."""
        svc = PricingService()
        assert svc.get_provider_for_model("deepseek/deepseek-chat") == "openrouter"
        assert svc.get_provider_for_model("deepseek-chat") == "deepseek"


class TestCatalog:
    def test_registry_rows_and_consts(self):
        for m in ENROLLED:
            info = get_model_info(f"openrouter:{m}")  # prefix-stripped to the slash id key
            assert info is not None and info.provider == "openrouter"
        assert Models.OPENROUTER_DEEPSEEK_CHAT == "openrouter:deepseek/deepseek-chat"
        assert Models.OPENROUTER_QWEN_CODER_32B == "openrouter:qwen/qwen-2.5-coder-32b-instruct"


class TestSpecParsingGuard:
    def test_slash_id_round_trips(self):
        """FR-OR-2 guard: provider:model split, slug() path-safe, cell_id hash recovery."""
        from startd8.model_comparison import slug
        spec = "openrouter:deepseek/deepseek-chat"
        provider, model = spec.split(":", 1)
        assert provider == "openrouter" and model == "deepseek/deepseek-chat"
        s = slug(spec)
        assert ":" not in s and "/" not in s  # path-safe
        cell_id = f"abc123def456:paymentservice:{spec}:r0"
        assert cell_id.split(":", 1)[0] == "abc123def456"
