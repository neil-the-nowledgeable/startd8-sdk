"""Tests for security_prime.trend_analysis — Phase 5."""

from __future__ import annotations

import pytest

from startd8.security_prime.trend_analysis import (
    assess_pass_rate_trajectory,
    compute_security_posture_trend,
)


class TestComputeSecurityPostureTrend:
    def test_insufficient_data(self):
        result = compute_security_posture_trend([])
        assert result["status"] == "insufficient_data"
        assert result["runs_available"] == 0

    def test_single_run(self):
        result = compute_security_posture_trend([{"gate_pass_rate": 0.9}])
        assert result["status"] == "insufficient_data"

    def test_improving_trend(self):
        runs = [
            {"gate_pass_rate": 0.5, "mean_score": 0.5,
             "findings_by_type": {"injection": 3}},
            {"gate_pass_rate": 0.7, "mean_score": 0.7,
             "findings_by_type": {"injection": 1}},
            {"gate_pass_rate": 0.9, "mean_score": 0.9,
             "findings_by_type": {"injection": 0}},
        ]
        result = compute_security_posture_trend(runs)
        assert result["status"] == "ok"
        assert result["pass_rate_slope"] > 0
        assert result["mean_score_slope"] > 0
        assert result["injection_slope"] < 0  # Decreasing is good
        assert result["latest_pass_rate"] == 0.9

    def test_declining_trend(self):
        runs = [
            {"gate_pass_rate": 0.9, "mean_score": 0.9,
             "findings_by_type": {}},
            {"gate_pass_rate": 0.5, "mean_score": 0.5,
             "findings_by_type": {"injection": 2}},
        ]
        result = compute_security_posture_trend(runs)
        assert result["pass_rate_slope"] < 0

    def test_owasp_coverage_slope(self):
        runs = [
            {"gate_pass_rate": 0.8, "mean_score": 0.8,
             "findings_by_type": {},
             "owasp_coverage": {"coverage_percentage": 0.3}},
            {"gate_pass_rate": 0.9, "mean_score": 0.9,
             "findings_by_type": {},
             "owasp_coverage": {"coverage_percentage": 0.5}},
        ]
        result = compute_security_posture_trend(runs)
        assert result["owasp_coverage_slope"] is not None
        assert result["owasp_coverage_slope"] > 0

    def test_no_owasp_data(self):
        runs = [
            {"gate_pass_rate": 0.8, "mean_score": 0.8, "findings_by_type": {}},
            {"gate_pass_rate": 0.9, "mean_score": 0.9, "findings_by_type": {}},
        ]
        result = compute_security_posture_trend(runs)
        assert result["owasp_coverage_slope"] is None


class TestAssessPassRateTrajectory:
    def test_insufficient_data(self):
        result = assess_pass_rate_trajectory([0.9])
        assert result["trend"] == "unknown"

    def test_sustained_low(self):
        result = assess_pass_rate_trajectory([0.5, 0.6, 0.65])
        assert result["alert_level"] == "ERROR"
        assert result["trend"] == "sustained_low"
        assert result["consecutive_below_threshold"] == 3

    def test_sustained_low_needs_3_consecutive(self):
        # 2 runs below 0.80 is not enough
        result = assess_pass_rate_trajectory([0.5, 0.6])
        assert result["trend"] != "sustained_low"

    def test_sustained_low_broken_by_good_run(self):
        # Good run in the middle breaks consecutive count
        result = assess_pass_rate_trajectory([0.5, 0.6, 0.85, 0.7, 0.75])
        # Only 2 trailing below 0.80 (0.7, 0.75) — not 3+
        assert result["trend"] != "sustained_low"

    def test_declining(self):
        result = assess_pass_rate_trajectory([0.95, 0.90, 0.85, 0.80, 0.75])
        assert result["alert_level"] == "WARNING"
        assert result["trend"] == "declining"

    def test_improving(self):
        result = assess_pass_rate_trajectory([0.75, 0.80, 0.85, 0.90, 0.95])
        # Latest is 0.95 > 0.7, slope positive
        assert result["alert_level"] == "INFO"
        assert result["trend"] == "improving"
