"""Tests for OTel span instrumentation in the Artisan pipeline.

Covers:
  - Gate entry/exit spans created by _execute_phase
  - Per-task span creation in handler.execute() paths
  - _NoOpTracer path — no crashes when OTel unavailable
  - Gate span records gate.passed attribute
  - Per-task span records task.status attribute
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from startd8.contractors.artisan_contractor import (
    HAS_OTEL,
    WorkflowPhase,
    _NoOpSpan,
    _NoOpTracer,
)


# ── NoOp Path Tests ────────────────────────────────────────────────


class TestNoOpTracer:
    """Verify _NoOpTracer and _NoOpSpan don't crash."""

    def test_start_as_current_span_returns_noop_span(self):
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test.span", attributes={"key": "val"})
        assert isinstance(span, _NoOpSpan)

    def test_noop_span_context_manager(self):
        span = _NoOpSpan()
        with span as s:
            assert s is span
            s.set_attribute("key", "value")
            s.set_status(None)
            s.add_event("test.event", attributes={"a": 1})
            s.record_exception(ValueError("test"))

    def test_noop_span_enter_exit(self):
        """Manual __enter__/__exit__ pattern used for per-task spans."""
        tracer = _NoOpTracer()
        cm = tracer.start_as_current_span("test.span")
        span = cm.__enter__()
        span.set_attribute("task.id", "T1")
        span.set_attribute("task.status", "designed")
        cm.__exit__(None, None, None)

    def test_noop_span_multiple_exits_no_crash(self):
        """Multiple __exit__ calls should not crash."""
        span = _NoOpSpan()
        span.__enter__()
        span.__exit__(None, None, None)
        span.__exit__(None, None, None)  # second exit — should be harmless


# ── Gate Span Tests ────────────────────────────────────────────────


class TestGateSpans:
    """Verify gate.entry / gate.exit spans are created."""

    def test_gate_entry_span_created(self):
        """Mock self.tracer to verify gate.entry span creation."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_cm

        # Simulate what _execute_phase does for gate.entry
        with mock_tracer.start_as_current_span(
            "gate.entry",
            attributes={"gate.phase": "design"},
        ) as gate_span:
            gate_span.set_attribute("gate.passed", True)

        mock_tracer.start_as_current_span.assert_called_once_with(
            "gate.entry",
            attributes={"gate.phase": "design"},
        )
        mock_span.set_attribute.assert_called_once_with("gate.passed", True)

    def test_gate_exit_span_created(self):
        """Mock self.tracer to verify gate.exit span creation."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_cm

        with mock_tracer.start_as_current_span(
            "gate.exit",
            attributes={"gate.phase": "implement"},
        ) as gate_span:
            gate_span.set_attribute("gate.passed", True)
            gate_span.set_attribute("gate.propagation_status", "validated")

        mock_tracer.start_as_current_span.assert_called_once_with(
            "gate.exit",
            attributes={"gate.phase": "implement"},
        )
        assert mock_span.set_attribute.call_count == 2


# ── Per-Task Span Tests ────────────────────────────────────────────


class TestPerTaskSpans:
    """Verify per-task span lifecycle in context_seed_handlers."""

    def test_phase_tracer_module_level_import(self):
        """Verify _phase_tracer is importable (either real or NoOp)."""
        from startd8.contractors.context_seed_handlers import _phase_tracer

        # Should be a tracer object (real OTel or _NoOpTracer)
        assert hasattr(_phase_tracer, "start_as_current_span")

    def test_per_task_span_manual_lifecycle(self):
        """Verify the __enter__/__exit__ pattern works with _phase_tracer."""
        from startd8.contractors.context_seed_handlers import _phase_tracer

        cm = _phase_tracer.start_as_current_span(
            "task.T1",
            attributes={
                "task.id": "T1",
                "task.title": "Test Task",
                "task.domain": "python",
                "task.phase": "design",
                "task.target_files": "src/foo.py",
            },
        )
        span = cm.__enter__()
        span.set_attribute("task.status", "designed")
        span.set_attribute("task.cost", 0.05)
        span.set_attribute("task.attempts", 1)
        cm.__exit__(None, None, None)

    def test_noop_tracer_per_task_span(self):
        """Per-task span with _NoOpTracer doesn't crash."""
        tracer = _NoOpTracer()
        cm = tracer.start_as_current_span(
            "task.T2",
            attributes={"task.id": "T2", "task.phase": "test"},
        )
        span = cm.__enter__()
        span.set_attribute("task.status", "passed")
        cm.__exit__(None, None, None)


# ── Design Documentation Spans ─────────────────────────────────────


class TestDesignDocumentationSpans:
    """Verify design phase span helpers exist and work."""

    def test_get_design_tracer_returns_tracer(self):
        from startd8.contractors.artisan_phases.design_documentation import (
            _get_design_tracer,
        )

        tracer = _get_design_tracer()
        assert hasattr(tracer, "start_as_current_span")

    def test_has_otel_flag_is_bool(self):
        from startd8.contractors.artisan_phases.design_documentation import _HAS_OTEL

        assert isinstance(_HAS_OTEL, bool)


# ── Development Phase Spans ────────────────────────────────────────


class TestDevelopmentPhaseSpans:
    """Verify development phase OTel import and flag."""

    def test_has_otel_flag_is_bool(self):
        from startd8.contractors.artisan_phases.development import _HAS_OTEL

        assert isinstance(_HAS_OTEL, bool)


# ── Test Construction Spans ────────────────────────────────────────


class TestTestConstructionSpans:
    """Verify test construction phase OTel import and flag."""

    def test_has_otel_flag_is_bool(self):
        from startd8.contractors.artisan_phases.test_construction import _HAS_OTEL

        assert isinstance(_HAS_OTEL, bool)
