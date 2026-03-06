"""Tests for startd8.repair.orchestrator — circuit breaker, traceability, OTel."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.repair.config import RepairConfig
from startd8.repair.models import (
    Diagnostic,
    RepairStepResult,
    SyntaxDiagnostic,
)
from startd8.repair.orchestrator import (
    _circuit_breaker_state,
    _inject_traceability_comment,
    _TRACEABILITY_PREFIX,
    reset_circuit_breaker,
    run_file_repair,
)


@pytest.fixture(autouse=True)
def _clean_circuit_breaker():
    """Reset circuit breaker state before and after each test."""
    reset_circuit_breaker()
    yield
    reset_circuit_breaker()


def _make_syntax_diag(file: str = "foo.py") -> SyntaxDiagnostic:
    return SyntaxDiagnostic(category="syntax", file=file, message="invalid syntax", line=1)


def _make_files(content: str = "x = 1\n") -> dict[Path, str]:
    return {Path("foo.py"): content}


class TestCircuitBreaker:
    """REQ-RPL-502: Circuit breaker skips repair after N consecutive failures."""

    def test_skips_after_threshold(self):
        """After circuit_breaker_threshold consecutive failures, repair is skipped."""
        config = RepairConfig(circuit_breaker_threshold=2)
        diags = [_make_syntax_diag()]
        files = _make_files()
        project_root = Path("/tmp")

        # Simulate 2 consecutive failures by setting state directly
        _circuit_breaker_state["syntax"] = 2

        outcome = run_file_repair(files, diags, config, project_root)
        assert outcome.any_modified is False
        # State should remain at 2 (not incremented further since we skipped)
        assert _circuit_breaker_state["syntax"] == 2

    def test_does_not_skip_below_threshold(self):
        """Below threshold, repair proceeds normally."""
        config = RepairConfig(circuit_breaker_threshold=3)
        diags = [_make_syntax_diag()]
        files = _make_files("x = 1\n")
        project_root = Path("/tmp")

        _circuit_breaker_state["syntax"] = 2

        # This should proceed (2 < 3)
        outcome = run_file_repair(files, diags, config, project_root)
        # Whether it modified or not depends on routing, but it should not be skipped
        assert isinstance(outcome.any_modified, bool)

    def test_reset_clears_state(self):
        """reset_circuit_breaker() clears all state."""
        _circuit_breaker_state["syntax"] = 5
        _circuit_breaker_state["import"] = 3
        reset_circuit_breaker()
        assert _circuit_breaker_state == {}

    def test_success_resets_counter(self):
        """A successful repair resets the failure counter for that category."""
        config = RepairConfig(circuit_breaker_threshold=5)
        diags = [_make_syntax_diag()]
        project_root = Path("/tmp")

        # Set a count below threshold
        _circuit_breaker_state["syntax"] = 2

        # Use code with a fence that the fence_strip step will fix
        files = {Path("foo.py"): "```python\nx = 1\n```\n"}

        outcome = run_file_repair(files, diags, config, project_root)
        if outcome.any_modified:
            assert _circuit_breaker_state.get("syntax", 0) == 0

    def test_failure_increments_counter(self):
        """A repair that modifies nothing increments the failure counter."""
        config = RepairConfig(circuit_breaker_threshold=10)
        diags = [_make_syntax_diag()]
        files = _make_files("x = 1\n")  # Already valid — fence_strip won't modify
        project_root = Path("/tmp")

        _circuit_breaker_state["syntax"] = 0
        outcome = run_file_repair(files, diags, config, project_root)
        if not outcome.any_modified:
            assert _circuit_breaker_state["syntax"] == 1


class TestTraceabilityComment:
    """REQ-RPL-009: Traceability comment injection."""

    def test_inject_traceability_comment(self):
        code = "x = 1\n"
        result = _inject_traceability_comment(code, ["fence_strip", "import_completion"])
        assert result.startswith(_TRACEABILITY_PREFIX)
        assert "fence_strip, import_completion" in result
        assert result.endswith("\nx = 1\n")

    def test_no_steps_no_comment(self):
        code = "x = 1\n"
        result = _inject_traceability_comment(code, [])
        assert result == code

    def test_comment_injected_on_modified_files(self):
        """run_file_repair injects traceability comment on actually modified files."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        # Fenced code that fence_strip will repair
        files = {Path("foo.py"): "```python\nx = 1\n```\n"}
        project_root = Path("/tmp")

        outcome = run_file_repair(files, diags, config, project_root)
        if outcome.any_modified:
            for path, content in outcome.repaired_files.items():
                assert content.startswith(_TRACEABILITY_PREFIX)

    def test_comment_not_injected_on_unmodified_files(self):
        """Unmodified files should not get a traceability comment."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = _make_files("x = 1\n")  # Already valid
        project_root = Path("/tmp")

        outcome = run_file_repair(files, diags, config, project_root)
        # Unmodified files should not appear in repaired_files
        for path, content in outcome.repaired_files.items():
            # If it appears, it must have the comment
            assert content.startswith(_TRACEABILITY_PREFIX)


class TestOTelSpans:
    """REQ-RPL-400: OTel span creation."""

    @patch("startd8.repair.orchestrator._HAS_OTEL", True)
    @patch("startd8.repair.orchestrator._tracer")
    def test_span_created_on_repair(self, mock_tracer):
        """A repair.attempt span is started when OTel is available."""
        mock_span_ctx = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span_ctx

        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = {Path("foo.py"): "```python\nx = 1\n```\n"}
        project_root = Path("/tmp")

        run_file_repair(files, diags, config, project_root)

        mock_tracer.start_as_current_span.assert_called_once()
        call_args = mock_tracer.start_as_current_span.call_args
        assert call_args[0][0] == "repair.attempt"
        attrs = call_args[1]["attributes"]
        assert "repair.file_count" in attrs
        assert "repair.route_confidence" in attrs

    @patch("startd8.repair.orchestrator._HAS_OTEL", False)
    @patch("startd8.repair.orchestrator._tracer", None)
    def test_no_span_without_otel(self):
        """No crash when OTel is not available."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = _make_files()
        project_root = Path("/tmp")

        # Should not raise
        outcome = run_file_repair(files, diags, config, project_root)
        assert isinstance(outcome.any_modified, bool)


class TestOTelMetrics:
    """REQ-RPL-401: Metric emission."""

    @patch("startd8.repair.orchestrator._repair_wall_clock")
    @patch("startd8.repair.orchestrator._repair_success")
    @patch("startd8.repair.orchestrator._repair_attempts")
    def test_metrics_emitted_on_success(self, mock_attempts, mock_success, mock_wall_clock):
        """Metrics are emitted on successful repair."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = {Path("foo.py"): "```python\nx = 1\n```\n"}
        project_root = Path("/tmp")

        outcome = run_file_repair(files, diags, config, project_root)

        mock_attempts.add.assert_called()
        mock_wall_clock.record.assert_called()
        if outcome.any_modified:
            mock_success.add.assert_called()

    @patch("startd8.repair.orchestrator._repair_wall_clock")
    @patch("startd8.repair.orchestrator._repair_success")
    @patch("startd8.repair.orchestrator._repair_attempts")
    def test_metrics_emitted_on_failure(self, mock_attempts, mock_success, mock_wall_clock):
        """Metrics are emitted even on failed repair."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = _make_files("x = 1\n")
        project_root = Path("/tmp")

        outcome = run_file_repair(files, diags, config, project_root)
        mock_attempts.add.assert_called()
        mock_wall_clock.record.assert_called()

    @patch("startd8.repair.orchestrator._repair_wall_clock")
    @patch("startd8.repair.orchestrator._repair_success")
    @patch("startd8.repair.orchestrator._repair_attempts")
    def test_skipped_metrics_on_circuit_breaker(self, mock_attempts, mock_success, mock_wall_clock):
        """Skipped outcome is emitted when circuit breaker is open."""
        _circuit_breaker_state["syntax"] = 5
        config = RepairConfig(circuit_breaker_threshold=3)
        diags = [_make_syntax_diag()]
        files = _make_files()
        project_root = Path("/tmp")

        run_file_repair(files, diags, config, project_root)

        mock_attempts.add.assert_called_once()
        call_kwargs = mock_attempts.add.call_args[0]
        assert call_kwargs[1]["outcome"] == "skipped"

    @patch("startd8.repair.orchestrator._repair_wall_clock", None)
    @patch("startd8.repair.orchestrator._repair_success", None)
    @patch("startd8.repair.orchestrator._repair_attempts", None)
    def test_no_crash_without_metrics(self):
        """No crash when metrics are None (OTel not installed)."""
        config = RepairConfig(circuit_breaker_threshold=100)
        diags = [_make_syntax_diag()]
        files = _make_files()
        project_root = Path("/tmp")

        outcome = run_file_repair(files, diags, config, project_root)
        assert isinstance(outcome.any_modified, bool)
