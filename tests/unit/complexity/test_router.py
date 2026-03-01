"""Tests for complexity.router — tier-based generator/agent routing."""

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.complexity.router import ComplexityRouter


class TestComplexityRouter:
    def test_select_returns_tier_specific_generator(self):
        gen_simple = object()
        gen_complex = object()
        router = ComplexityRouter(
            simple_generator=gen_simple,
            complex_generator=gen_complex,
        )
        assert router.select(ComplexityTier.SIMPLE) is gen_simple
        assert router.select(ComplexityTier.COMPLEX) is gen_complex

    def test_select_falls_back_to_moderate(self):
        gen_moderate = object()
        router = ComplexityRouter(moderate_generator=gen_moderate)
        assert router.select(ComplexityTier.TRIVIAL) is gen_moderate
        assert router.select(ComplexityTier.SIMPLE) is gen_moderate
        assert router.select(ComplexityTier.COMPLEX) is gen_moderate

    def test_select_returns_none_when_no_generators(self):
        router = ComplexityRouter()
        assert router.select(ComplexityTier.MODERATE) is None

    def test_select_agent_spec_tier_specific(self):
        router = ComplexityRouter(
            simple_agent_spec="anthropic:claude-haiku-4-5",
            complex_agent_spec="anthropic:claude-opus-4-6",
        )
        assert router.select_agent_spec(ComplexityTier.SIMPLE) == "anthropic:claude-haiku-4-5"
        assert router.select_agent_spec(ComplexityTier.COMPLEX) == "anthropic:claude-opus-4-6"

    def test_select_agent_spec_falls_back_to_moderate(self):
        router = ComplexityRouter(
            moderate_agent_spec="anthropic:claude-sonnet-4-6",
        )
        assert router.select_agent_spec(ComplexityTier.TRIVIAL) == "anthropic:claude-sonnet-4-6"
        assert router.select_agent_spec(ComplexityTier.COMPLEX) == "anthropic:claude-sonnet-4-6"

    def test_select_agent_spec_returns_none_when_not_set(self):
        router = ComplexityRouter()
        assert router.select_agent_spec(ComplexityTier.MODERATE) is None

    def test_all_tiers_selectable(self):
        """Each tier can be independently configured."""
        gens = {tier: object() for tier in ComplexityTier}
        router = ComplexityRouter(
            trivial_generator=gens[ComplexityTier.TRIVIAL],
            simple_generator=gens[ComplexityTier.SIMPLE],
            moderate_generator=gens[ComplexityTier.MODERATE],
            complex_generator=gens[ComplexityTier.COMPLEX],
        )
        for tier, expected in gens.items():
            assert router.select(tier) is expected
