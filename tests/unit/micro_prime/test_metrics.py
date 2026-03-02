"""Tests for the Micro Prime Metrics module (REQ-MP-600–603)."""

from __future__ import annotations

import pytest

from startd8.micro_prime.metrics import (
    MetricsCollector,
    generate_cost_report,
    generate_experiment_result,
)
from startd8.micro_prime.models import (
    ElementResult,
    EscalationReason,
    EscalationResult,
    FileResult,
    MicroPrimeConfig,
    SeedResult,
    TierClassification,
)


@pytest.fixture
def sample_seed_result():
    """Create a sample SeedResult for testing."""
    return SeedResult(
        file_results=[
            FileResult(
                file_path="src/a.py",
                element_results=[
                    ElementResult(
                        element_name="__init__",
                        file_path="src/a.py",
                        tier=TierClassification.TRIVIAL,
                        success=True,
                        template_used=True,
                    ),
                    ElementResult(
                        element_name="get_name",
                        file_path="src/a.py",
                        tier=TierClassification.SIMPLE,
                        success=True,
                        input_tokens=100,
                        output_tokens=50,
                    ),
                    ElementResult(
                        element_name="process",
                        file_path="src/a.py",
                        tier=TierClassification.MODERATE,
                        success=False,
                        escalation=EscalationResult(
                            reason=EscalationReason.TIER_TOO_HIGH,
                            detail="Too complex",
                        ),
                    ),
                ],
            ),
        ],
    )


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_record_and_retrieve(self):
        collector = MetricsCollector()
        result = ElementResult(
            element_name="foo",
            file_path="src/foo.py",
            tier=TierClassification.SIMPLE,
            success=True,
            generation_time_ms=100.0,
            input_tokens=50,
            output_tokens=30,
        )
        collector.record(result)
        assert len(collector.metrics) == 1
        assert collector.metrics[0].element_name == "foo"
        assert collector.metrics[0].generation_time_ms == 100.0

    def test_record_forwards_classification_reason(self):
        """R3-S1: classification_reason flows from ElementResult to metrics."""
        collector = MetricsCollector()
        result = ElementResult(
            element_name="foo",
            file_path="src/foo.py",
            tier=TierClassification.SIMPLE,
            classification_reason="2 params; simple return (str)",
            success=True,
        )
        collector.record(result)
        assert collector.metrics[0].classification_reason == "2 params; simple return (str)"

    def test_record_with_escalation(self):
        collector = MetricsCollector()
        result = ElementResult(
            element_name="bar",
            file_path="src/bar.py",
            tier=TierClassification.MODERATE,
            success=False,
            escalation=EscalationResult(
                reason=EscalationReason.AST_FAILURE,
                detail="Could not parse",
            ),
        )
        collector.record(result)
        assert collector.metrics[0].escalation_reason == "ast_failure"

    def test_clear(self):
        collector = MetricsCollector()
        result = ElementResult(
            element_name="baz",
            file_path="src/baz.py",
            tier=TierClassification.TRIVIAL,
            success=True,
        )
        collector.record(result)
        assert len(collector.metrics) == 1
        collector.clear()
        assert len(collector.metrics) == 0

    def test_metrics_returns_copy(self):
        collector = MetricsCollector()
        result = ElementResult(
            element_name="x",
            file_path="src/x.py",
            tier=TierClassification.SIMPLE,
            success=True,
        )
        collector.record(result)
        metrics = collector.metrics
        metrics.clear()
        assert len(collector.metrics) == 1  # Original not affected


class TestGenerateCostReport:
    """Tests for generate_cost_report() (REQ-MP-602)."""

    def test_basic_cost_report(self, sample_seed_result):
        config = MicroPrimeConfig()
        report = generate_cost_report(sample_seed_result, config)
        assert report.total_elements == 3
        assert report.trivial_count == 1
        assert report.simple_count == 1
        assert report.moderate_count == 1
        assert report.local_success_count == 2
        assert report.escalated_count == 1
        assert report.template_count == 1
        assert report.total_input_tokens == 100
        assert report.total_output_tokens == 50

    def test_success_rate(self, sample_seed_result):
        config = MicroPrimeConfig()
        report = generate_cost_report(sample_seed_result, config)
        assert abs(report.success_rate - 2.0 / 3.0) < 0.01

    def test_empty_seed_result(self):
        config = MicroPrimeConfig()
        report = generate_cost_report(SeedResult(), config)
        assert report.total_elements == 0
        assert report.success_rate == 0.0


class TestGenerateExperimentResult:
    """Tests for generate_experiment_result() (REQ-MP-603)."""

    def test_schema_version(self, sample_seed_result):
        config = MicroPrimeConfig()
        result = generate_experiment_result(
            sample_seed_result, config, "test-run-001",
        )
        assert result["schema_version"] == "1.0.0"
        assert result["run_id"] == "test-run-001"

    def test_includes_config(self, sample_seed_result):
        config = MicroPrimeConfig(model="custom-coder")
        result = generate_experiment_result(
            sample_seed_result, config, "test-run-002",
        )
        assert result["config"]["model"] == "custom-coder"

    def test_includes_summary(self, sample_seed_result):
        config = MicroPrimeConfig()
        result = generate_experiment_result(
            sample_seed_result, config, "test-run-003",
        )
        assert "total_elements" in result["summary"]
        assert result["summary"]["total_elements"] == 3

    def test_includes_timestamp(self, sample_seed_result):
        config = MicroPrimeConfig()
        result = generate_experiment_result(
            sample_seed_result, config, "test-run-004",
        )
        assert "timestamp" in result

    def test_includes_element_metrics(self, sample_seed_result):
        config = MicroPrimeConfig()
        collector = MetricsCollector()
        collector.record(ElementResult(
            element_name="test",
            file_path="src/t.py",
            tier=TierClassification.SIMPLE,
            success=True,
        ))
        result = generate_experiment_result(
            sample_seed_result, config, "test-run-005",
            collector=collector,
        )
        assert len(result["elements"]) == 1
        assert result["elements"][0]["element_name"] == "test"
