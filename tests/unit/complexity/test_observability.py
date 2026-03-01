"""Tests for complexity observability — logging and OTel metrics."""

import logging

import pytest

from startd8.complexity import ComplexityTier, log_tier_distribution
from startd8.complexity.classifier import classify_tier
from startd8.complexity.models import TaskComplexitySignals


class TestClassifyTierLogging:
    def test_logs_classification_at_info(self, caplog):
        signals = TaskComplexitySignals(blast_radius=10)
        with caplog.at_level(logging.INFO, logger="startd8.complexity.classifier"):
            tier, reason = classify_tier(signals)
        assert tier is ComplexityTier.COMPLEX
        assert any("tier=complex" in r.message for r in caplog.records)

    def test_logs_moderate_default(self, caplog):
        signals = TaskComplexitySignals()
        with caplog.at_level(logging.INFO, logger="startd8.complexity.classifier"):
            classify_tier(signals)
        assert any("tier=moderate" in r.message for r in caplog.records)

    def test_logs_simple(self, caplog):
        signals = TaskComplexitySignals(
            manifest_coverage="full",
            blast_radius=0,
            edit_mode="create",
            caller_count=0,
            estimated_loc=50,
            target_file_count=1,
        )
        with caplog.at_level(logging.INFO, logger="startd8.complexity.classifier"):
            classify_tier(signals)
        assert any("tier=simple" in r.message for r in caplog.records)


class TestLogTierDistribution:
    def test_returns_counts(self):
        tiers = [
            ComplexityTier.SIMPLE,
            ComplexityTier.MODERATE,
            ComplexityTier.MODERATE,
            ComplexityTier.COMPLEX,
        ]
        counts = log_tier_distribution(tiers)
        assert counts == {"simple": 1, "moderate": 2, "complex": 1}

    def test_empty_list(self):
        counts = log_tier_distribution([])
        assert counts == {}

    def test_logs_summary(self, caplog):
        tiers = [ComplexityTier.MODERATE, ComplexityTier.COMPLEX]
        with caplog.at_level(logging.INFO, logger="startd8.complexity.classifier"):
            log_tier_distribution(tiers)
        assert any("Tier distribution" in r.message for r in caplog.records)
