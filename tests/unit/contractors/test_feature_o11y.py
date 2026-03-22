"""Tests for Feature O11y — progress indication for Prime Contractor."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


@dataclass
class FakeFeature:
    """Minimal FeatureSpec stand-in for testing."""

    id: str = "F-001"
    name: str = "test_feature"
    description: str = "A test feature"
    status: Any = "complete"
    target_files: List[str] = field(default_factory=lambda: ["src/foo.py"])
    generated_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _cost_usd: float = 0.0123


class TestFeatureSignalExtraction:
    """FeatureObserver._extract_signal captures correct data."""

    def test_basic_extraction(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        feature = FakeFeature()
        signal = FeatureObserver._extract_signal(feature, elapsed=1.5)
        assert signal.name == "test_feature"
        assert signal.feature_id == "F-001"
        assert signal.success is True
        assert signal.cost_usd == pytest.approx(0.0123)
        assert signal.elapsed_s == 1.5

    def test_failed_feature(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        feature = FakeFeature(status="failed")
        signal = FeatureObserver._extract_signal(feature, elapsed=2.0)
        assert signal.success is False

    def test_review_data_extracted(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        feature = FakeFeature(
            metadata={"review": {"score": 85, "verdict": "PASS"}},
        )
        signal = FeatureObserver._extract_signal(feature, elapsed=1.0)
        assert signal.review_score == 85
        assert signal.review_verdict == "PASS"

    def test_disk_quality_extracted(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        feature = FakeFeature(
            metadata={"disk_quality_score": 0.72},
        )
        signal = FeatureObserver._extract_signal(feature, elapsed=1.0)
        assert signal.disk_quality_score == pytest.approx(0.72)

    def test_gate_fired_extracted(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        feature = FakeFeature(
            metadata={"_redrafted": True},
        )
        signal = FeatureObserver._extract_signal(feature, elapsed=1.0)
        assert signal.gate_fired is True

    def test_no_metadata_graceful(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        feature = FakeFeature(metadata=None)
        signal = FeatureObserver._extract_signal(feature, elapsed=0.5)
        assert signal.review_score is None
        assert signal.disk_quality_score is None
        assert signal.gate_fired is False


class TestStatusLine:
    """T1: One-line status output per feature."""

    def test_prints_status_line(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver(total_features=3)
        feature = FakeFeature()

        buf = io.StringIO()
        with redirect_stdout(buf):
            observer.on_feature_complete(feature)

        line = buf.getvalue()
        assert "[1/3]" in line
        assert "test_feature" in line
        assert "$0.0123" in line

    def test_review_verdict_in_line(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver(total_features=2)
        feature = FakeFeature(
            metadata={"review": {"score": 72, "verdict": "FAIL"}},
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            observer.on_feature_complete(feature)

        line = buf.getvalue()
        assert "review:" in line
        assert "72" in line

    def test_cumulative_cost(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver(total_features=2)
        f1 = FakeFeature(id="F-001", _cost_usd=0.01)
        f2 = FakeFeature(id="F-002", name="second", _cost_usd=0.02)

        buf = io.StringIO()
        with redirect_stdout(buf):
            observer.on_feature_complete(f1)
            observer.on_feature_complete(f2)

        lines = buf.getvalue().strip().split("\n")
        assert len(lines) == 2
        assert "total:$0.0100" in lines[0]
        assert "total:$0.0300" in lines[1]

    def test_quiet_mode_no_output(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver(total_features=1, quiet=True)
        feature = FakeFeature()

        buf = io.StringIO()
        with redirect_stdout(buf):
            observer.on_feature_complete(feature)

        assert buf.getvalue() == ""


class TestSummary:
    """print_summary() shows aggregated metrics."""

    def test_summary_content(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver(total_features=3)
        observer.on_feature_complete(FakeFeature(id="F-1", status="complete", _cost_usd=0.01))
        observer.on_feature_complete(FakeFeature(id="F-2", status="failed", _cost_usd=0.02))
        observer.on_feature_complete(FakeFeature(id="F-3", status="complete", _cost_usd=0.03))

        buf = io.StringIO()
        with redirect_stdout(buf):
            observer.print_summary()

        text = buf.getvalue()
        assert "Feature O11y Summary" in text
        assert "2 succeeded" in text
        assert "1 failed" in text
        assert "$0.0600" in text

    def test_summary_with_reviews(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver(total_features=2)
        observer.on_feature_complete(FakeFeature(
            id="F-1", metadata={"review": {"score": 80, "verdict": "PASS"}},
        ))
        observer.on_feature_complete(FakeFeature(
            id="F-2", metadata={"review": {"score": 60, "verdict": "FAIL"}},
        ))

        buf = io.StringIO()
        with redirect_stdout(buf):
            observer.print_summary()

        text = buf.getvalue()
        assert "Avg review:" in text
        assert "70" in text  # (80+60)/2

    def test_empty_summary_no_crash(self):
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver()
        buf = io.StringIO()
        with redirect_stdout(buf):
            observer.print_summary()
        # No crash, no output for empty
        assert buf.getvalue() == ""


class TestOnFeatureStart:
    """on_feature_start tracks timing for elapsed calculation."""

    def test_start_sets_timing(self):
        import time
        from startd8.contractors.feature_o11y import FeatureObserver

        observer = FeatureObserver(total_features=1, quiet=True)
        feature = FakeFeature()

        observer.on_feature_start(feature)
        time.sleep(0.05)
        observer.on_feature_complete(feature)

        assert len(observer._signals) == 1
        assert observer._signals[0].elapsed_s >= 0.04
