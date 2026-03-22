"""Tests for utils.trend_math — linear_slope shared utility."""

from __future__ import annotations

import pytest

from startd8.utils.trend_math import linear_slope


class TestLinearSlope:
    """Tests for linear_slope."""

    def test_empty_returns_none(self):
        assert linear_slope([]) is None

    def test_single_value_returns_none(self):
        assert linear_slope([5.0]) is None

    def test_two_ascending_values(self):
        slope = linear_slope([1.0, 2.0])
        assert slope is not None
        assert slope == pytest.approx(1.0)

    def test_two_descending_values(self):
        slope = linear_slope([2.0, 1.0])
        assert slope is not None
        assert slope == pytest.approx(-1.0)

    def test_constant_values(self):
        slope = linear_slope([5.0, 5.0, 5.0, 5.0])
        assert slope is not None
        assert slope == pytest.approx(0.0)

    def test_linear_ascending(self):
        slope = linear_slope([0.0, 1.0, 2.0, 3.0])
        assert slope is not None
        assert slope == pytest.approx(1.0)

    def test_noisy_ascending(self):
        slope = linear_slope([0.0, 1.5, 1.0, 3.0, 2.5])
        assert slope is not None
        assert slope > 0.0

    def test_positive_slope_indicates_improvement(self):
        # Scores improving over runs
        slope = linear_slope([0.5, 0.6, 0.7, 0.8, 0.9])
        assert slope is not None
        assert slope == pytest.approx(0.1)

    def test_negative_slope_for_cost(self):
        # Cost decreasing = good
        slope = linear_slope([1.0, 0.8, 0.6, 0.4])
        assert slope is not None
        assert slope == pytest.approx(-0.2)

    def test_many_values(self):
        values = [float(i) for i in range(100)]
        slope = linear_slope(values)
        assert slope is not None
        assert slope == pytest.approx(1.0)
