"""Tests for security metrics wiring — Phase 0."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from startd8.security_prime.kaizen import (
    _default_metrics,
    load_security_metrics,
    update_security_metrics,
)


class TestUpdateSecurityMetrics:
    def test_creates_file_on_first_write(self, tmp_path):
        update_security_metrics(
            str(tmp_path),
            injection_blocked=1,
            credential_blocked=0,
            aggregate_score=0.85,
            files_checked=5,
            files_skipped=2,
            violation_files=["a.py"],
        )
        metrics_path = tmp_path / "kaizen-metrics.json"
        assert metrics_path.exists()
        data = json.loads(metrics_path.read_text())
        sec = data["security"]
        assert sec["injection_blocked"] == 1
        assert sec["aggregate_score"] == 0.85
        assert sec["consecutive_injection_runs"] == 1
        assert sec["last_injection_files"] == ["a.py"]

    def test_consecutive_runs_increment(self, tmp_path):
        # First run with injection
        update_security_metrics(str(tmp_path), injection_blocked=1)
        # Second run with injection
        update_security_metrics(str(tmp_path), injection_blocked=2)
        data = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert data["security"]["consecutive_injection_runs"] == 2

    def test_consecutive_runs_reset_on_clean(self, tmp_path):
        update_security_metrics(str(tmp_path), injection_blocked=1)
        update_security_metrics(str(tmp_path), injection_blocked=0)
        data = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert data["security"]["consecutive_injection_runs"] == 0

    def test_preserves_non_security_keys(self, tmp_path):
        # Pre-existing data
        metrics_path = tmp_path / "kaizen-metrics.json"
        metrics_path.write_text(json.dumps({"query_security": {"mean_score": 0.9}}))

        update_security_metrics(str(tmp_path), injection_blocked=0)
        data = json.loads(metrics_path.read_text())
        assert "query_security" in data
        assert "security" in data


class TestLoadSecurityMetrics:
    def test_missing_file(self, tmp_path):
        result = load_security_metrics(str(tmp_path))
        assert result == _default_metrics()

    def test_valid_file(self, tmp_path):
        metrics_path = tmp_path / "kaizen-metrics.json"
        metrics_path.write_text(json.dumps({
            "security": {
                "injection_blocked": 3,
                "consecutive_injection_runs": 2,
            },
        }))
        result = load_security_metrics(str(tmp_path))
        assert result["injection_blocked"] == 3
        assert result["consecutive_injection_runs"] == 2
