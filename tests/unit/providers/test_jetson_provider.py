"""Unit tests for the Jetson edge-cluster provider.

Covers FR-J3/J3a/J11/J12 + the CRP R1 cases: registry resolution, opt-in guard
(R1-S1/FR-J12), env-overridable base_url (R1-S2), alias→served-id translation,
sentinel key (FR-J11), real non-fallback pricing keyed on the served id
(R1-S6/FR-J9b), provider mapping, contamination labels, and offline-landability
(R1-S8 — no network needed).
"""

import pytest
from unittest.mock import patch

from startd8.providers import ProviderRegistry
from startd8.providers.jetson import JetsonProvider, ALLOW_ENV
from startd8.agents import OpenAICompatibleAgent
from startd8.exceptions import ConfigurationError
from startd8.costs.pricing import PricingService

OPT_IN = {ALLOW_ENV: "1"}


class TestJetsonProviderBasics:
    def test_provider_properties(self):
        p = JetsonProvider()
        assert p.name == "jetson"
        assert p.display_name == "Jetson Edge Cluster"
        assert "mistral-7b-base" in p.supported_models

    def test_alias_translation(self):
        p = JetsonProvider()
        assert p.served_id("mistral-7b-base") == "mistralai/Mistral-7B-v0.3"
        assert p.served_id("iter-002") == "iter_002"
        # unknown alias passes through verbatim
        assert p.served_id("something-else") == "something-else"

    def test_contamination_labels(self):
        p = JetsonProvider()
        assert p.contamination_label("mistral-7b-base") == "clean"
        assert p.contamination_label("iter-002") == "in-domain-finetune"


class TestJetsonOptInGuard:
    def test_create_agent_refused_without_opt_in(self):
        """FR-J12/R1-S1: SDK must not silently dial the LAN box."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError, match="opt-in"):
                JetsonProvider().create_agent("mistral-7b-base")

    def test_validate_config_refused_without_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError, match="opt-in"):
                JetsonProvider().validate_config({})

    def test_validate_config_ok_with_opt_in(self):
        with patch.dict("os.environ", OPT_IN, clear=True):
            assert JetsonProvider().validate_config({}) is True


class TestJetsonAgentConstruction:
    def test_create_agent_pins_default_endpoint_and_served_id(self):
        with patch.dict("os.environ", OPT_IN, clear=True):
            agent = JetsonProvider().create_agent("mistral-7b-base")
        assert isinstance(agent, OpenAICompatibleAgent)
        assert agent.base_url == "http://192.168.7.57:8000/v1"
        assert agent.model == "mistralai/Mistral-7B-v0.3"  # served id, not the alias

    def test_base_url_env_override(self):
        """R1-S2: JETSON_BASE_URL overrides the default; default restored when unset."""
        with patch.dict("os.environ", {**OPT_IN, "JETSON_BASE_URL": "http://astro:8000/v1"}, clear=True):
            agent = JetsonProvider().create_agent("mistral-7b-base")
            assert agent.base_url == "http://astro:8000/v1"
        with patch.dict("os.environ", OPT_IN, clear=True):
            assert JetsonProvider().base_url == "http://192.168.7.57:8000/v1"

    def test_sentinel_key_applied(self):
        """FR-J11: a LAN IP (not localhost) needs a non-empty key; sentinel is supplied."""
        with patch.dict("os.environ", OPT_IN, clear=True):
            agent = JetsonProvider().create_agent("mistral-7b-base")
        # key is held on the OpenAI client; the LAN IP is not nulled like localhost would be
        assert agent.client.api_key == "local-no-auth"


class TestJetsonRegistration:
    def test_resolves_via_registry(self):
        """FR-J3/dual-registration: registry yields the provider (entry-point or builtin)."""
        ProviderRegistry.discover()
        provider = ProviderRegistry.get_provider("jetson")
        assert provider is not None
        assert provider.name == "jetson"


class TestJetsonPricing:
    def test_pricing_keyed_both_call_sites_non_fallback(self):
        """R1-S6/FR-J9b: BOTH ids that resolve_pricing receives must be present — the served id
        (runtime tracker) AND the alias (pre-run estimate, stripped from the spec) — or the dry-run
        warns NO-PRICING / the runtime hits the $3/$15 fallback. The dry-run surfaced exactly this."""
        svc = PricingService()
        for key in ("mistralai/Mistral-7B-v0.3", "iter_002", "mistral-7b-base", "iter-002"):
            pricing = svc.get_pricing(key)  # None ⇒ would hit fallback
            assert pricing is not None, f"{key} missing — would fire $3/$15 fallback / NO-PRICING warn"
            assert pricing.provider == "jetson"
            # marginal on-prem ≈ $0; crucially NOT the 3.0/15.0 fallback
            assert pricing.input_cost_per_million == 0.0
            assert pricing.output_cost_per_million == 0.0

    def test_provider_for_served_id(self):
        assert PricingService().get_provider_for_model("mistralai/Mistral-7B-v0.3") == "jetson"

    def test_offline_pricing_resolution(self):
        """R1-S8: pricing/agent wiring resolves with no network — the SDK side is offline-landable."""
        with patch.dict("os.environ", OPT_IN, clear=True):
            agent = JetsonProvider().create_agent("mistral-7b-base")
        pricing = PricingService().get_pricing(agent.model)
        assert pricing is not None and pricing.input_cost_per_million == 0.0
