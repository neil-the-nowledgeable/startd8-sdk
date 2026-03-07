"""Tests for REQ-RPL-402: Manifest attribution and per-file repair frequency."""

import json
from pathlib import Path

import pytest

from startd8.repair.config import RepairConfig
from startd8.repair.models import SyntaxDiagnostic
from startd8.repair.orchestrator import (
    _OTEL_DESCRIPTORS,
    _update_repair_frequency,
    get_repair_frequency,
    reset_circuit_breaker,
    run_file_repair,
)


@pytest.fixture(autouse=True)
def _clean_circuit_breaker():
    reset_circuit_breaker()
    yield
    reset_circuit_breaker()


def _make_syntax_diag(file: str = "foo.py") -> SyntaxDiagnostic:
    return SyntaxDiagnostic(category="syntax", file=file, message="invalid syntax", line=1)


class TestOTelDescriptors:
    """REQ-RPL-402: _OTEL_DESCRIPTORS declares repair metrics and spans."""

    def test_descriptors_has_metrics(self):
        assert "metrics" in _OTEL_DESCRIPTORS
        assert len(_OTEL_DESCRIPTORS["metrics"]) == 5

    def test_descriptors_has_spans(self):
        assert "spans" in _OTEL_DESCRIPTORS
        assert len(_OTEL_DESCRIPTORS["spans"]) == 1

    def test_metric_names_match_instruments(self):
        expected = {
            "repair_attempts_total": "counter",
            "repair_success_total": "counter",
            "repair_steps_applied": "counter",
            "repair_wall_clock_ms": "histogram",
            "repair_cost_avoided_usd": "counter",
        }
        for m in _OTEL_DESCRIPTORS["metrics"]:
            assert m["name"] in expected, f"Unexpected metric: {m['name']}"
            assert m["instrument"] == expected[m["name"]]

    def test_span_pattern_is_repair_attempt(self):
        span = _OTEL_DESCRIPTORS["spans"][0]
        assert span["name_pattern"] == "repair.attempt"
        assert "repair.feature_name" in span["attributes"]
        assert "repair.file_count" in span["attributes"]
        assert "repair.route_confidence" in span["attributes"]
        assert "repair.success" in span["attributes"]

    def test_span_declares_step_events(self):
        span = _OTEL_DESCRIPTORS["spans"][0]
        assert "repair.step.{step_name}" in span["events"]

    def test_all_metrics_have_required_fields(self):
        required = {"name", "instrument", "unit", "description", "meter"}
        for m in _OTEL_DESCRIPTORS["metrics"]:
            missing = required - set(m.keys())
            assert not missing, f"Metric {m['name']} missing fields: {missing}"


class TestRepairFrequency:
    """REQ-RPL-402: Per-file repair frequency tracking."""

    def test_update_creates_frequency_file(self, tmp_path):
        repaired = {Path("src/foo.py"): "x = 1\n"}
        _update_repair_frequency(repaired, tmp_path)

        freq_path = tmp_path / ".startd8" / "repair" / "repair_frequency.json"
        assert freq_path.exists()

        data = json.loads(freq_path.read_text())
        assert "src/foo.py" in data
        assert data["src/foo.py"]["repair_count"] == 1
        assert "last_repair_epoch" in data["src/foo.py"]
        assert "first_repair_epoch" in data["src/foo.py"]

    def test_update_increments_count(self, tmp_path):
        repaired = {Path("src/foo.py"): "x = 1\n"}
        _update_repair_frequency(repaired, tmp_path)
        _update_repair_frequency(repaired, tmp_path)
        _update_repair_frequency(repaired, tmp_path)

        data = get_repair_frequency(tmp_path)
        assert data["src/foo.py"]["repair_count"] == 3

    def test_multiple_files_tracked(self, tmp_path):
        repaired = {
            Path("src/a.py"): "a = 1\n",
            Path("src/b.py"): "b = 2\n",
        }
        _update_repair_frequency(repaired, tmp_path)

        data = get_repair_frequency(tmp_path)
        assert "src/a.py" in data
        assert "src/b.py" in data

    def test_get_returns_empty_when_no_file(self, tmp_path):
        data = get_repair_frequency(tmp_path)
        assert data == {}

    def test_first_repair_epoch_preserved(self, tmp_path):
        repaired = {Path("src/foo.py"): "x = 1\n"}
        _update_repair_frequency(repaired, tmp_path)

        data1 = get_repair_frequency(tmp_path)
        first = data1["src/foo.py"]["first_repair_epoch"]

        _update_repair_frequency(repaired, tmp_path)

        data2 = get_repair_frequency(tmp_path)
        assert data2["src/foo.py"]["first_repair_epoch"] == first
        assert data2["src/foo.py"]["repair_count"] == 2

    def test_frequency_updated_on_successful_repair(self, tmp_path):
        """run_file_repair updates frequency for modified files."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = {Path("foo.py"): "```python\nx = 1\n```\n"}

        outcome = run_file_repair(files, diags, config, tmp_path)
        if outcome.any_modified:
            data = get_repair_frequency(tmp_path)
            assert len(data) > 0

    def test_frequency_not_updated_on_no_modification(self, tmp_path):
        """run_file_repair does not update frequency when nothing changed."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = {Path("foo.py"): "x = 1\n"}

        run_file_repair(files, diags, config, tmp_path)
        data = get_repair_frequency(tmp_path)
        assert data == {}


class TestCollectorRegistration:
    """REQ-RPL-402: Repair orchestrator registered in collector."""

    def test_repair_orchestrator_in_instrumented_modules(self):
        from startd8.observability.collector import _INSTRUMENTED_MODULES

        module_paths = [m[0] for m in _INSTRUMENTED_MODULES]
        assert "startd8.repair.orchestrator" in module_paths

    def test_collector_loads_repair_descriptors(self):
        from startd8.observability.collector import _load_descriptors

        desc = _load_descriptors(
            "startd8.repair.orchestrator",
            "src/startd8/repair/orchestrator.py",
        )
        assert "metrics" in desc
        assert "spans" in desc
        assert len(desc["metrics"]) == 5
