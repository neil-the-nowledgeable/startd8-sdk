"""Tests for Kaizen instrumentation metrics integration (REQ-TCW-402)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers to import _emit_kaizen_metrics / _update_kaizen_index from script
# ---------------------------------------------------------------------------

@pytest.fixture()
def postmortem_module():
    """Import run_prime_postmortem as a module."""
    script = Path(__file__).resolve().parents[3] / "scripts" / "run_prime_postmortem.py"
    assert script.is_file(), f"Script not found: {script}"
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_prime_postmortem", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_report(**overrides):
    """Create a minimal mock PostMortemReport."""
    report = MagicMock()
    report.timestamp = "2026-03-18T12:00:00"
    report.total_features = overrides.get("total_features", 5)
    report.successful_features = overrides.get("successful_features", 4)
    report.failed_features = overrides.get("failed_features", 1)
    report.cost_summary = None
    report.micro_prime_analysis = None
    report.pipeline_attribution = []
    report.lessons = []
    report.features = []
    report.aggregate_verdict = "PASS"
    report.aggregate_score = 0.8
    report.avg_assembly_delta = None
    return report


# ---------------------------------------------------------------------------
# Tests: _emit_kaizen_metrics reads instrumentation result
# ---------------------------------------------------------------------------

class TestKaizenInstrumentationMetrics:

    def test_metrics_include_instrumentation_when_present(self, tmp_path, postmortem_module):
        """If instrumentation-result.json exists, kaizen metrics include its fields."""
        instr_dir = tmp_path / "instrumentation"
        instr_dir.mkdir()
        (instr_dir / "instrumentation-result.json").write_text(json.dumps({
            "todo_count": 10,
            "todo_completed": 7,
            "todo_deferred": 3,
            "todo_completion_rate": 70.0,
            "instrumentation_coverage": 85.5,
        }))

        report = _make_report()
        postmortem_module._emit_kaizen_metrics(report, tmp_path, run_id="test-run")

        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert metrics["todo_count"] == 10
        assert metrics["todo_completed"] == 7
        assert metrics["todo_deferred"] == 3
        assert metrics["todo_completion_rate"] == 70.0
        assert metrics["instrumentation_coverage"] == 85.5

    def test_metrics_without_instrumentation(self, tmp_path, postmortem_module):
        """Without instrumentation-result.json, fields are absent."""
        report = _make_report()
        postmortem_module._emit_kaizen_metrics(report, tmp_path, run_id="test-run")

        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert "todo_count" not in metrics
        assert "instrumentation_coverage" not in metrics

    def test_metrics_with_malformed_json(self, tmp_path, postmortem_module):
        """Malformed instrumentation JSON is handled gracefully."""
        instr_dir = tmp_path / "instrumentation"
        instr_dir.mkdir()
        (instr_dir / "instrumentation-result.json").write_text("NOT JSON")

        report = _make_report()
        # Should not raise
        postmortem_module._emit_kaizen_metrics(report, tmp_path, run_id="test-run")

        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert "instrumentation_coverage" not in metrics

    def test_metrics_with_partial_fields(self, tmp_path, postmortem_module):
        """Partial instrumentation result uses defaults for missing fields."""
        instr_dir = tmp_path / "instrumentation"
        instr_dir.mkdir()
        (instr_dir / "instrumentation-result.json").write_text(json.dumps({
            "todo_count": 3,
        }))

        report = _make_report()
        postmortem_module._emit_kaizen_metrics(report, tmp_path, run_id="test-run")

        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert metrics["todo_count"] == 3
        assert metrics["todo_completed"] == 0
        assert metrics["instrumentation_coverage"] == 0.0


# ---------------------------------------------------------------------------
# Tests: _update_kaizen_index includes instrumentation_coverage
# ---------------------------------------------------------------------------

class TestKaizenIndexInstrumentation:

    def test_index_entry_includes_coverage(self, tmp_path, postmortem_module):
        """When kaizen-metrics.json has instrumentation_coverage, it appears in the index."""
        # Simulate run directory structure
        run_dir = tmp_path / "run-001"
        output_dir = run_dir / "plan-ingestion"
        output_dir.mkdir(parents=True)

        # Write kaizen-metrics.json with coverage
        (output_dir / "kaizen-metrics.json").write_text(json.dumps({
            "success_rate": 0.8,
            "total_features": 5,
            "kaizen_enabled": True,
            "instrumentation_coverage": 72.5,
        }))

        postmortem_module._update_kaizen_index(output_dir, keep=20, run_id="run-001")

        index = json.loads((tmp_path / "kaizen-index.json").read_text())
        assert len(index["runs"]) == 1
        assert index["runs"][0]["instrumentation_coverage"] == 72.5

    def test_index_entry_without_coverage(self, tmp_path, postmortem_module):
        """Without instrumentation_coverage, field is absent from index entry."""
        run_dir = tmp_path / "run-002"
        output_dir = run_dir / "plan-ingestion"
        output_dir.mkdir(parents=True)

        (output_dir / "kaizen-metrics.json").write_text(json.dumps({
            "success_rate": 0.9,
            "total_features": 3,
        }))

        postmortem_module._update_kaizen_index(output_dir, keep=20, run_id="run-002")

        index = json.loads((tmp_path / "kaizen-index.json").read_text())
        assert len(index["runs"]) == 1
        assert "instrumentation_coverage" not in index["runs"][0]

    def test_index_no_metrics_file(self, tmp_path, postmortem_module):
        """Without kaizen-metrics.json, entry has no metrics fields."""
        run_dir = tmp_path / "run-003"
        output_dir = run_dir / "plan-ingestion"
        output_dir.mkdir(parents=True)

        postmortem_module._update_kaizen_index(output_dir, keep=20, run_id="run-003")

        index = json.loads((tmp_path / "kaizen-index.json").read_text())
        assert len(index["runs"]) == 1
        assert "instrumentation_coverage" not in index["runs"][0]

    def test_index_idempotent_update(self, tmp_path, postmortem_module):
        """Re-running update for same run_id replaces the entry."""
        run_dir = tmp_path / "run-004"
        output_dir = run_dir / "plan-ingestion"
        output_dir.mkdir(parents=True)

        (output_dir / "kaizen-metrics.json").write_text(json.dumps({
            "success_rate": 0.5,
            "total_features": 2,
            "instrumentation_coverage": 50.0,
        }))

        postmortem_module._update_kaizen_index(output_dir, keep=20, run_id="run-004")
        postmortem_module._update_kaizen_index(output_dir, keep=20, run_id="run-004")

        index = json.loads((tmp_path / "kaizen-index.json").read_text())
        run_ids = [r["run_id"] for r in index["runs"]]
        assert run_ids.count("run-004") == 1
