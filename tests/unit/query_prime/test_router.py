"""Tests for query_prime.router — tier-to-model routing and escalation."""

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.query_prime.router import (
    QueryRouterConfig,
    get_agent_spec_for_tier,
    get_escalation_tier,
)


class TestGetAgentSpecForTier:
    def test_simple_uses_t3(self):
        spec = get_agent_spec_for_tier(ComplexityTier.SIMPLE)
        assert "haiku" in spec

    def test_moderate_uses_t2(self):
        spec = get_agent_spec_for_tier(ComplexityTier.MODERATE)
        assert "sonnet" in spec

    def test_complex_uses_t1(self):
        spec = get_agent_spec_for_tier(ComplexityTier.COMPLEX)
        assert "opus" in spec

    def test_trivial_falls_to_t3(self):
        spec = get_agent_spec_for_tier(ComplexityTier.TRIVIAL)
        assert "haiku" in spec

    def test_custom_config(self):
        config = QueryRouterConfig(t3_agent_spec="mock:mock-model")
        spec = get_agent_spec_for_tier(ComplexityTier.SIMPLE, config)
        assert spec == "mock:mock-model"


class TestGetEscalationTier:
    def test_simple_escalates_to_moderate(self):
        assert get_escalation_tier(ComplexityTier.SIMPLE) == ComplexityTier.MODERATE

    def test_moderate_escalates_to_complex(self):
        assert get_escalation_tier(ComplexityTier.MODERATE) == ComplexityTier.COMPLEX

    def test_complex_cannot_escalate(self):
        assert get_escalation_tier(ComplexityTier.COMPLEX) is None

    def test_trivial_escalates_to_simple(self):
        assert get_escalation_tier(ComplexityTier.TRIVIAL) == ComplexityTier.SIMPLE
