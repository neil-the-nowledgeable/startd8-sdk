"""Tests for the local Ollama contestant lane (FR-LO-1..11) — fully offline."""

import pytest
from types import SimpleNamespace

from startd8.benchmark_matrix import local_lane as ll
from startd8.benchmark_matrix import jetson_lane as jl
from startd8.costs.pricing import PricingService
from startd8.model_catalog import get_model_info, Models

LOCAL_MODELS = ["qwen2.5-coder:14b", "qwen2.5-coder:7b", "codellama:latest"]


class MockAgent:
    def __init__(self, text="def f():\n    return 42\n"):
        self._text = text
        self.last_system_prompt = None
        self.last_system_fingerprint = None

    async def agenerate(self, prompt, system_prompt=None, temperature=None):
        self.last_system_prompt = system_prompt
        self.last_system_fingerprint = "fp_ollama"  # Ollama's echo — NOT a served_adapter=
        return SimpleNamespace(text=self._text)


class TestRunLocalCell:
    @pytest.mark.asyncio
    async def test_clean_cell_scored_with_provenance(self):
        agent = MockAgent()
        rec = await ll.run_local_cell(agent, model="qwen2.5-coder:14b", prompt="build paymentservice")
        assert rec.scored is True                       # no firewall verdict — always scored
        assert rec.cost_lane == "local"
        assert rec.contestant_kind == "local-pretraining-caveat"
        assert rec.model == "qwen2.5-coder:14b"
        assert rec.text.startswith("def f")
        assert rec.sampling == jl.DEFAULT_SAMPLING      # recorded (FR-LO-11)

    @pytest.mark.asyncio
    async def test_neutral_prompt_sent(self):
        """FR-J6 fairness: the lane sends the shared corpus-token-free neutral prompt."""
        agent = MockAgent()
        rec = await ll.run_local_cell(agent, model="codellama:latest", prompt="x")
        assert rec.system_prompt_sent == ll.NEUTRAL_SYSTEM_PROMPT == jl.NEUTRAL_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_to_dict_and_scored_cells(self):
        agent = MockAgent()
        rec = await ll.run_local_cell(agent, model="qwen2.5-coder:7b", prompt="x")
        d = rec.to_dict()
        assert d["cost_lane"] == "local" and d["model"] == "qwen2.5-coder:7b"
        assert ll.scored_cells([rec]) == [rec]


class TestLocalPricing:
    def test_pricing_non_fallback_zero(self):
        """FR-LO-5: each enrolled model has a real $0 entry, not the $3/$15 fallback."""
        svc = PricingService()
        for m in LOCAL_MODELS:
            p = svc.get_pricing(m)
            assert p is not None, f"{m} missing — would hit $3/$15 fallback"
            assert p.provider == "ollama"
            assert p.input_cost_per_million == 0.0 and p.output_cost_per_million == 0.0

    def test_provider_for_model_maps_ollama(self):
        """FR-LO-6: PROVIDER_PATTERNS attributes these ids to ollama."""
        svc = PricingService()
        assert svc.get_provider_for_model("qwen2.5-coder:14b") == "ollama"
        assert svc.get_provider_for_model("codellama:latest") == "ollama"


class TestLocalCatalog:
    def test_registry_rows_present(self):
        # get_model_info strips the provider prefix on the first colon, so query with the full
        # provider-prefixed spec (the realistic call) — a bare Ollama tag like "qwen2.5-coder:14b"
        # would be mis-parsed to "14b" (a pre-existing catalog quirk, not this lane's concern).
        for m in LOCAL_MODELS:
            info = get_model_info(f"ollama:{m}")
            assert info is not None and info.provider == "ollama"
            assert "code" in info.capabilities

    def test_models_constants(self):
        assert Models.OLLAMA_QWEN_CODER_14B == "ollama:qwen2.5-coder:14b"
        assert Models.OLLAMA_CODELLAMA == "ollama:codellama:latest"


class TestSpecParsingGuard:
    def test_inner_colon_model_id_round_trips(self):
        """FR-LO-3: ollama:qwen2.5-coder:14b splits provider/model and slugs filesystem-safe."""
        from startd8.model_comparison import slug
        spec = "ollama:qwen2.5-coder:14b"
        provider, model = spec.split(":", 1)
        assert provider == "ollama" and model == "qwen2.5-coder:14b"
        s = slug(spec)
        assert ":" not in s and "/" not in s            # path-safe
        # cell_id recovers the spec-hash via split(":",1)[0]; the model's inner colon is harmless
        cell_id = f"abc123def456:paymentservice:{spec}:r0"
        assert cell_id.split(":", 1)[0] == "abc123def456"
