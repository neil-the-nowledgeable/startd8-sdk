"""Tests for the Micro Prime → shared ComplexityTier bridge."""

from __future__ import annotations

import pytest

from startd8.complexity import ComplexityTier
from startd8.micro_prime.classifier import (
    _to_shared_tier,
    classify_element_shared,
)
from startd8.micro_prime.models import TierClassification


class TestToSharedTier:
    def test_trivial(self):
        assert _to_shared_tier(TierClassification.TRIVIAL) is ComplexityTier.TRIVIAL

    def test_simple(self):
        assert _to_shared_tier(TierClassification.SIMPLE) is ComplexityTier.SIMPLE

    def test_moderate(self):
        assert _to_shared_tier(TierClassification.MODERATE) is ComplexityTier.MODERATE

    def test_complex(self):
        assert _to_shared_tier(TierClassification.COMPLEX) is ComplexityTier.COMPLEX


class TestClassifyElementShared:
    def test_property_returns_shared_simple(
        self, property_element, sample_file_spec, empty_contracts,
    ):
        tier, reason = classify_element_shared(
            property_element, sample_file_spec, empty_contracts,
        )
        assert tier is ComplexityTier.SIMPLE
        assert isinstance(reason, str)

    def test_simple_function_returns_shared_tier(
        self, simple_function_element, sample_file_spec, empty_contracts,
    ):
        tier, reason = classify_element_shared(
            simple_function_element, sample_file_spec, empty_contracts,
        )
        assert isinstance(tier, ComplexityTier)
        assert tier in (ComplexityTier.SIMPLE, ComplexityTier.MODERATE)

    def test_complex_function_returns_shared_complex(
        self, complex_function_element, sample_file_spec, empty_contracts,
    ):
        tier, reason = classify_element_shared(
            complex_function_element, sample_file_spec, empty_contracts,
        )
        assert tier is ComplexityTier.COMPLEX

    def test_constant_returns_shared_simple(
        self, constant_element, sample_file_spec, empty_contracts,
    ):
        tier, reason = classify_element_shared(
            constant_element, sample_file_spec, empty_contracts,
        )
        assert tier is ComplexityTier.SIMPLE
