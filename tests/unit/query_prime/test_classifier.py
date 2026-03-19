"""Tests for query_prime.classifier — tier mapping, prior injection forcing."""

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.query_prime.classifier import (
    QueryRoutingConfig,
    classify_query_tier,
)
from startd8.query_prime.models import OperationType, QuerySignals


class TestClassifyQueryTier:
    """Core classification logic tests."""

    def test_health_check_is_trivial(self):
        signals = QuerySignals(table_count=1)
        result = classify_query_tier(signals, operation_type=OperationType.HEALTH_CHECK)
        assert result.tier == ComplexityTier.TRIVIAL
        assert "health_check" in result.reason

    def test_simple_single_table_select(self):
        signals = QuerySignals(table_count=1, join_count=0)
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.SIMPLE

    def test_simple_two_table_one_join(self):
        signals = QuerySignals(table_count=2, join_count=1)
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.SIMPLE

    def test_complex_many_tables(self):
        signals = QuerySignals(table_count=5)
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.COMPLEX
        assert "table_count" in result.reason

    def test_complex_dynamic_columns(self):
        signals = QuerySignals(has_dynamic_columns=True)
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.COMPLEX

    def test_complex_subquery_with_aggregate(self):
        signals = QuerySignals(has_subquery=True, has_aggregate=True)
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.COMPLEX

    def test_moderate_default(self):
        signals = QuerySignals(
            table_count=3,
            join_count=2,
            has_subquery=True,
            has_aggregate=False,
        )
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.MODERATE

    def test_transaction_prevents_simple(self):
        signals = QuerySignals(table_count=1, has_transaction=True)
        result = classify_query_tier(signals)
        # has_transaction blocks SIMPLE -> falls to MODERATE
        assert result.tier == ComplexityTier.MODERATE


class TestPriorInjectionForcing:
    """Prior injection failure forces minimum MODERATE (REQ-QP-301)."""

    def test_prior_injection_forces_moderate_from_simple(self):
        signals = QuerySignals(
            table_count=1,
            prior_injection_failure=True,
        )
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.MODERATE
        assert result.forced_minimum == ComplexityTier.MODERATE

    def test_prior_injection_does_not_downgrade_complex(self):
        signals = QuerySignals(
            table_count=5,
            prior_injection_failure=True,
        )
        result = classify_query_tier(signals)
        assert result.tier == ComplexityTier.COMPLEX

    def test_prior_injection_forces_health_check_up(self):
        signals = QuerySignals(prior_injection_failure=True)
        result = classify_query_tier(signals, operation_type=OperationType.HEALTH_CHECK)
        assert result.tier == ComplexityTier.MODERATE


class TestQueryRoutingConfig:
    """Configurable threshold tests."""

    def test_custom_table_threshold(self):
        config = QueryRoutingConfig(table_count_complex_threshold=2)
        signals = QuerySignals(table_count=3)
        result = classify_query_tier(signals, config)
        assert result.tier == ComplexityTier.COMPLEX

    def test_tuple_unpacking(self):
        signals = QuerySignals(table_count=1)
        tier, reason = classify_query_tier(signals)
        assert tier == ComplexityTier.SIMPLE
        assert isinstance(reason, str)
