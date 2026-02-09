"""
Tests for OTel cost metrics (Phase 2A/2B).

Covers:
- Counter increments with correct attributes
- No-op guard when OTel unavailable
- CostMetrics lazy initialization
"""

from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class FakeCostRecord:
    """Minimal CostRecord-like object for testing."""
    model: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    project: Optional[str] = "test-project"
    total_cost: float = 0.05
    input_tokens: int = 1000
    output_tokens: int = 500


class TestCostMetrics:
    """Tests for CostMetrics class."""

    def test_no_op_when_otel_unavailable(self):
        """CostMetrics.record() is a no-op when OTel is not available."""
        from startd8.costs.otel_metrics import CostMetrics

        cm = CostMetrics()
        # Force OTel unavailable
        with patch("startd8.costs.otel_metrics._OTEL_AVAILABLE", False):
            cm._initialized = False
            cm.record(FakeCostRecord())
            # Should not raise, and counters should be None
            assert cm._cost_total is None

    def test_lazy_initialization(self):
        """CostMetrics instruments are created on first record() call."""
        from startd8.costs.otel_metrics import CostMetrics

        cm = CostMetrics()
        assert cm._initialized is False

        # Mock OTel metrics
        mock_meter = MagicMock()
        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        mock_meter.create_counter.return_value = mock_counter
        mock_meter.create_histogram.return_value = mock_histogram

        with patch("startd8.costs.otel_metrics._OTEL_AVAILABLE", True), \
             patch("startd8.costs.otel_metrics._otel_metrics") as mock_otel:
            mock_otel.get_meter.return_value = mock_meter
            cm._initialized = False  # Reset for clean test

            cm.record(FakeCostRecord())

            assert cm._initialized is True
            # Counter should have been called
            mock_counter.add.assert_called()

    def test_record_correct_attributes(self):
        """CostMetrics.record() passes correct attributes to OTel."""
        from startd8.costs.otel_metrics import CostMetrics

        cm = CostMetrics()
        mock_meter = MagicMock()

        mock_cost_counter = MagicMock()
        mock_input_counter = MagicMock()
        mock_output_counter = MagicMock()
        mock_histogram = MagicMock()

        counter_calls = []
        def make_counter(name, **kwargs):
            c = MagicMock()
            counter_calls.append((name, c))
            if "input_tokens" in name:
                return mock_input_counter
            elif "output_tokens" in name:
                return mock_output_counter
            return mock_cost_counter

        mock_meter.create_counter.side_effect = make_counter
        mock_meter.create_histogram.return_value = mock_histogram

        with patch("startd8.costs.otel_metrics._OTEL_AVAILABLE", True), \
             patch("startd8.costs.otel_metrics._otel_metrics") as mock_otel:
            mock_otel.get_meter.return_value = mock_meter

            record = FakeCostRecord(
                model="gpt-4o",
                provider="openai",
                project="my-project",
                total_cost=0.10,
                input_tokens=2000,
                output_tokens=1000,
            )
            cm.record(record)

            # Verify cost counter
            mock_cost_counter.add.assert_called_once_with(
                0.10,
                attributes={
                    "model": "gpt-4o",
                    "provider": "openai",
                    "project": "my-project",
                },
            )
            # Verify token counters
            mock_input_counter.add.assert_called_once_with(
                2000,
                attributes={
                    "model": "gpt-4o",
                    "provider": "openai",
                    "project": "my-project",
                },
            )
            mock_output_counter.add.assert_called_once_with(
                1000,
                attributes={
                    "model": "gpt-4o",
                    "provider": "openai",
                    "project": "my-project",
                },
            )
            # Verify histogram
            mock_histogram.record.assert_called_once_with(
                0.10,
                attributes={
                    "model": "gpt-4o",
                    "provider": "openai",
                    "project": "my-project",
                },
            )

    def test_record_without_project(self):
        """CostMetrics.record() omits project attribute when None."""
        from startd8.costs.otel_metrics import CostMetrics

        cm = CostMetrics()
        mock_meter = MagicMock()
        mock_counter = MagicMock()
        mock_meter.create_counter.return_value = mock_counter
        mock_meter.create_histogram.return_value = MagicMock()

        with patch("startd8.costs.otel_metrics._OTEL_AVAILABLE", True), \
             patch("startd8.costs.otel_metrics._otel_metrics") as mock_otel:
            mock_otel.get_meter.return_value = mock_meter

            record = FakeCostRecord(project=None)
            cm.record(record)

            call_attrs = mock_counter.add.call_args[1]["attributes"]
            assert "project" not in call_attrs
