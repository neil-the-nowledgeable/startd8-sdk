"""Unit tests for forensic LLM call logging (OT-712, OT-713).

Covers:
  - Schema conformance per call_type (7 tests)
  - Null-field presence (3 tests)
  - Degradation condition evaluation (13 tests)
  - OTel exemplar extraction (3 tests)
  - WARNING-level filtering (3 tests)
  - Exception safety (2 tests)
  - Input validation (4 tests)
  - Contract state construction from BoundaryResult (3 tests)
  - Size truncation / OT-716 (2 tests)
  - ContextVar accessors (2 tests)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.forensic_log import (
    _SENTINEL,
    _build_contract_state,
    _extract_exemplars,
    _validate_inputs,
    emit_forensic_log,
    get_boundary_result,
    is_degraded,
    set_boundary_result,
    _boundary_result_var,
    _MAX_TARGET_FILES,
    _MAX_DEGRADATION_REASONS,
)
from startd8.otel_conventions import (
    FORENSIC_LOG_SCHEMA_VERSION,
    VALID_CALL_TYPES,
    DegradationReasons,
    EventNames,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeBoundaryResult:
    """Minimal BoundaryResult stub for testing."""

    passed: bool = True
    blocking_failures: list[str] = field(default_factory=list)
    propagation_status: str = "validated"
    chain_statuses: dict[str, str] | None = None
    boundary_severity_max: str | None = None
    quality_violations: list[str] | None = None


def _minimal_call() -> dict[str, Any]:
    return {
        "prompt_length": 100,
        "model_spec": "mock:mock-model",
        "tokens_input": 50,
        "tokens_output": 25,
        "cost_usd": 0.001,
    }


def _minimal_task() -> dict[str, Any]:
    return {
        "task_id": "T1",
        "title": "Test Task",
        "domain": "python",
        "phase": "design",
    }


def _minimal_ctx_prop() -> dict[str, Any]:
    return {
        "domain_defaulted": False,
        "design_calibration_present": True,
        "depth_tier": "standard",
        "design_doc_present": True,
        "design_doc_line_count": 100,
    }


# ---------------------------------------------------------------------------
# Schema conformance tests (one per call_type)
# ---------------------------------------------------------------------------


class TestSchemaConformance:
    """Verify emit_forensic_log produces a log with correct schema fields."""

    @pytest.mark.parametrize("call_type", sorted(VALID_CALL_TYPES))
    def test_schema_fields_present_for_each_call_type(self, call_type):
        """Each call_type should produce a log entry with all schema sections."""
        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type=call_type,
                call=_minimal_call(),
                task=_minimal_task(),
                context_propagation=_minimal_ctx_prop(),
                boundary_result_override=None,
            )

        assert captured.get("event") == EventNames.LLM_CALL
        assert captured.get("schema_version") == FORENSIC_LOG_SCHEMA_VERSION
        assert captured.get("call_type") == call_type
        assert "call" in captured
        assert "task" in captured
        assert "context_propagation" in captured
        assert "contract_state" in captured
        assert "provenance" in captured
        assert "exemplars" in captured
        assert "degraded" in captured
        assert "degradation_reasons" in captured


# ---------------------------------------------------------------------------
# Null-field presence tests (OT-709)
# ---------------------------------------------------------------------------


class TestNullFieldPresence:
    """Verify that null fields are explicitly present, never omitted."""

    def test_all_call_fields_present_when_empty(self):
        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type="design.generate",
                call={},
                task={},
                context_propagation={},
                boundary_result_override=None,
            )

        call_section = captured["call"]
        assert "prompt_length" in call_section
        assert "max_tokens" in call_section
        assert "model_spec" in call_section
        assert "response_time_ms" in call_section
        assert call_section["prompt_length"] is None

    def test_task_fields_present_when_empty(self):
        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type="design.generate",
                call=_minimal_call(),
                task={},
                context_propagation=_minimal_ctx_prop(),
                boundary_result_override=None,
            )

        task_section = captured["task"]
        assert "task_id" in task_section
        assert "title" in task_section
        assert "domain" in task_section
        assert "feature_id" in task_section
        assert "phase" in task_section
        assert task_section["task_id"] is None

    def test_provenance_section_present_when_none(self):
        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type="design.generate",
                call=_minimal_call(),
                task=_minimal_task(),
                context_propagation=_minimal_ctx_prop(),
                provenance=None,
                boundary_result_override=None,
            )

        prov = captured["provenance"]
        assert "workflow_id" in prov
        assert "iteration" in prov
        assert prov["workflow_id"] is None


# ---------------------------------------------------------------------------
# Degradation condition tests (OT-711)
# ---------------------------------------------------------------------------


class TestIsDegraded:
    """Test each of the 12 degradation conditions plus the all-healthy case."""

    def test_all_healthy_returns_false(self):
        degraded, reasons = is_degraded(
            "design.generate",
            _minimal_ctx_prop(),
            FakeBoundaryResult(passed=True),
        )
        assert degraded is False
        assert reasons == []

    def test_condition_1_domain_defaulted(self):
        ctx = {**_minimal_ctx_prop(), "domain_defaulted": True}
        degraded, reasons = is_degraded("design.generate", ctx, None)
        assert degraded is True
        assert DegradationReasons.DOMAIN_DEFAULTED in reasons

    def test_condition_2_design_doc_missing_at_implement(self):
        ctx = {**_minimal_ctx_prop(), "design_doc_present": False}
        degraded, reasons = is_degraded("implement.chunk", ctx, None)
        assert DegradationReasons.DESIGN_DOC_MISSING in reasons

    def test_condition_2_design_doc_missing_not_at_design(self):
        """Condition 2 should NOT fire at design phase."""
        ctx = {**_minimal_ctx_prop(), "design_doc_present": False}
        degraded, reasons = is_degraded("design.generate", ctx, None)
        assert DegradationReasons.DESIGN_DOC_MISSING not in reasons

    def test_condition_3_design_calibration_missing_at_design(self):
        ctx = {**_minimal_ctx_prop(), "design_calibration_present": False}
        degraded, reasons = is_degraded("design.generate", ctx, None)
        assert DegradationReasons.DESIGN_CALIBRATION_MISSING in reasons

    def test_condition_4_prompt_constraints_empty_at_implement(self):
        ctx = {**_minimal_ctx_prop(), "prompt_constraints_count": 0}
        degraded, reasons = is_degraded("implement.chunk", ctx, None)
        assert DegradationReasons.PROMPT_CONSTRAINTS_EMPTY in reasons

    def test_condition_5_parameter_sources_missing_at_review(self):
        ctx = {**_minimal_ctx_prop(), "parameter_sources_present": False}
        degraded, reasons = is_degraded("review.evaluate", ctx, None)
        assert DegradationReasons.PARAMETER_SOURCES_MISSING in reasons

    def test_condition_6_file_inventory_missing_at_test(self):
        ctx = {**_minimal_ctx_prop(), "existing_file_inventory_present": False}
        degraded, reasons = is_degraded("test.generate", ctx, None)
        assert DegradationReasons.FILE_INVENTORY_MISSING in reasons

    def test_condition_7_depth_tier_null(self):
        ctx = {**_minimal_ctx_prop(), "depth_tier": None}
        degraded, reasons = is_degraded("design.generate", ctx, None)
        assert DegradationReasons.DEPTH_TIER_NULL in reasons

    def test_condition_8_design_doc_empty(self):
        ctx = {
            **_minimal_ctx_prop(),
            "design_doc_present": True,
            "design_doc_line_count": 0,
        }
        degraded, reasons = is_degraded("implement.chunk", ctx, None)
        assert DegradationReasons.DESIGN_DOC_EMPTY in reasons

    def test_condition_9_entry_gate_failed(self):
        br = FakeBoundaryResult(passed=False)
        degraded, reasons = is_degraded("design.generate", _minimal_ctx_prop(), br)
        assert DegradationReasons.ENTRY_GATE_FAILED in reasons

    def test_condition_10_boundary_severity_warning(self):
        br = FakeBoundaryResult(boundary_severity_max="WARNING")
        degraded, reasons = is_degraded("design.generate", _minimal_ctx_prop(), br)
        assert DegradationReasons.BOUNDARY_SEVERITY_HIGH in reasons

    def test_condition_11_chain_degraded(self):
        br = FakeBoundaryResult(chain_statuses={"seed_to_impl": "DEGRADED"})
        degraded, reasons = is_degraded("design.generate", _minimal_ctx_prop(), br)
        assert any(r.startswith(DegradationReasons.CHAIN_DEGRADED) for r in reasons)

    def test_condition_12_quality_violations_present(self):
        br = FakeBoundaryResult(quality_violations=["missing_field"])
        degraded, reasons = is_degraded("design.generate", _minimal_ctx_prop(), br)
        assert DegradationReasons.QUALITY_VIOLATIONS_PRESENT in reasons


# ---------------------------------------------------------------------------
# OTel exemplar extraction tests (OT-708)
# ---------------------------------------------------------------------------


class TestExemplars:
    """Verify OTel exemplar extraction."""

    def test_exemplars_none_when_otel_unavailable(self):
        with patch("startd8.contractors.forensic_log._HAS_OTEL", False):
            trace_id, span_id = _extract_exemplars()
        assert trace_id is None
        assert span_id is None

    def test_exemplars_none_when_span_invalid(self):
        with patch("startd8.contractors.forensic_log._HAS_OTEL", True):
            mock_span = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.is_valid = False
            mock_span.get_span_context.return_value = mock_ctx
            with patch("startd8.contractors.forensic_log._trace") as mock_trace:
                mock_trace.get_current_span.return_value = mock_span
                trace_id, span_id = _extract_exemplars()
        assert trace_id is None
        assert span_id is None

    def test_exemplars_extracted_when_span_valid(self):
        with patch("startd8.contractors.forensic_log._HAS_OTEL", True):
            mock_span = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.is_valid = True
            mock_ctx.trace_id = 0x1234ABCD
            mock_ctx.span_id = 0x5678EF
            mock_span.get_span_context.return_value = mock_ctx
            with patch("startd8.contractors.forensic_log._trace") as mock_trace:
                mock_trace.get_current_span.return_value = mock_span
                trace_id, span_id = _extract_exemplars()
        assert trace_id is not None
        assert span_id is not None
        assert len(trace_id) == 32
        assert len(span_id) == 16


# ---------------------------------------------------------------------------
# WARNING-level filtering tests (OT-711)
# ---------------------------------------------------------------------------


class TestWarningFiltering:
    """Verify WARNING-level filtering behavior."""

    def test_warning_level_skips_healthy_call(self):
        """When forensic_log_level=WARNING and context is healthy, no log."""
        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type="design.generate",
                call=_minimal_call(),
                task=_minimal_task(),
                context_propagation=_minimal_ctx_prop(),
                forensic_log_level="WARNING",
                boundary_result_override=FakeBoundaryResult(passed=True),
            )

            mock_logger.log.assert_not_called()

    def test_warning_level_emits_for_degraded_call(self):
        """When forensic_log_level=WARNING and context is degraded, emit."""
        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type="design.generate",
                call=_minimal_call(),
                task=_minimal_task(),
                context_propagation={**_minimal_ctx_prop(), "domain_defaulted": True},
                forensic_log_level="WARNING",
                boundary_result_override=None,
            )

        assert captured.get("degraded") is True

    def test_info_level_always_emits(self):
        """When forensic_log_level=INFO, always emit regardless of degradation."""
        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type="design.generate",
                call=_minimal_call(),
                task=_minimal_task(),
                context_propagation=_minimal_ctx_prop(),
                forensic_log_level="INFO",
                boundary_result_override=FakeBoundaryResult(passed=True),
            )

        assert captured.get("degraded") is False


# ---------------------------------------------------------------------------
# Exception safety tests (OT-712 AC-8)
# ---------------------------------------------------------------------------


class TestExceptionSafety:
    """Verify emit_forensic_log never raises exceptions."""

    def test_internal_error_does_not_raise(self):
        """Even with a broken logger, emit_forensic_log should not raise."""
        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_gl.side_effect = RuntimeError("logger exploded")
            # This should NOT raise
            emit_forensic_log(
                call_type="design.generate",
                call=_minimal_call(),
                task=_minimal_task(),
                context_propagation=_minimal_ctx_prop(),
                boundary_result_override=None,
            )

    def test_validation_error_recorded_as_span_event(self):
        """Invalid call_type should record span event, not crash."""
        with patch("startd8.contractors.forensic_log._HAS_OTEL", True):
            mock_span = MagicMock()
            with patch("startd8.contractors.forensic_log._trace") as mock_trace:
                mock_trace.get_current_span.return_value = mock_span
                # Invalid call_type
                emit_forensic_log(
                    call_type="invalid.type",
                    call=_minimal_call(),
                    task=_minimal_task(),
                    context_propagation=_minimal_ctx_prop(),
                    boundary_result_override=None,
                )
                # Should have recorded the error as a span event
                mock_span.add_event.assert_called_once()
                event_name = mock_span.add_event.call_args[0][0]
                assert event_name == EventNames.FORENSIC_LOG_ERROR


# ---------------------------------------------------------------------------
# Input validation tests (OT-712 AC-11)
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Verify input validation for call_type, numerics, and strings."""

    def test_invalid_call_type_raises(self):
        with pytest.raises(ValueError, match="Invalid call_type"):
            _validate_inputs("invalid.type", _minimal_call(), _minimal_task())

    def test_negative_tokens_raises(self):
        call = {**_minimal_call(), "tokens_input": -1}
        with pytest.raises(ValueError, match="non-negative"):
            _validate_inputs("design.generate", call, _minimal_task())

    def test_negative_cost_raises(self):
        call = {**_minimal_call(), "cost_usd": -0.5}
        with pytest.raises(ValueError, match="non-negative"):
            _validate_inputs("design.generate", call, _minimal_task())

    def test_empty_task_id_raises(self):
        task = {**_minimal_task(), "task_id": ""}
        with pytest.raises(ValueError, match="non-empty"):
            _validate_inputs("design.generate", _minimal_call(), task)

    def test_none_values_always_valid(self):
        """None is always a valid value for any field (R1-F2)."""
        call = {"prompt_length": None, "tokens_input": None, "cost_usd": None}
        task = {"task_id": None, "title": None, "domain": None}
        _validate_inputs("design.generate", call, task)  # should not raise


# ---------------------------------------------------------------------------
# Contract state construction tests
# ---------------------------------------------------------------------------


class TestBuildContractState:
    """Test _build_contract_state with various BoundaryResult shapes."""

    def test_none_boundary_result(self):
        state = _build_contract_state(None)
        assert state["entry_gate_passed"] is None
        assert state["propagation_status"] is None
        assert state["chain_statuses"] is None
        assert state["quality_violations"] == []

    def test_passed_boundary_result(self):
        br = FakeBoundaryResult(passed=True, propagation_status="validated")
        state = _build_contract_state(br)
        assert state["entry_gate_passed"] is True
        assert state["propagation_status"] == "validated"

    def test_failed_boundary_with_violations(self):
        br = FakeBoundaryResult(
            passed=False,
            blocking_failures=["missing_design", "bad_domain"],
            chain_statuses={"a_to_b": "DEGRADED"},
        )
        state = _build_contract_state(br)
        assert state["entry_gate_passed"] is False
        assert state["quality_violations"] == ["missing_design", "bad_domain"]
        assert state["chain_statuses"] == {"a_to_b": "DEGRADED"}


# ---------------------------------------------------------------------------
# Size truncation tests (OT-716)
# ---------------------------------------------------------------------------


class TestSizeTruncation:
    """Verify list truncation for large fields."""

    def test_target_files_truncated(self):
        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            large_files = [f"file_{i}.py" for i in range(_MAX_TARGET_FILES + 10)]
            emit_forensic_log(
                call_type="implement.chunk",
                call=_minimal_call(),
                task={**_minimal_task(), "target_files": large_files},
                context_propagation=_minimal_ctx_prop(),
                boundary_result_override=None,
            )

        task_section = captured["task"]
        assert len(task_section["target_files"]) == _MAX_TARGET_FILES
        assert task_section["target_files_truncated"] is True

    def test_degradation_reasons_truncated(self):
        """Many degradation conditions should be capped."""
        # Create a boundary result with many chain degradations
        chains = {f"chain_{i}": "DEGRADED" for i in range(_MAX_DEGRADATION_REASONS + 10)}
        br = FakeBoundaryResult(chain_statuses=chains)
        ctx = {
            **_minimal_ctx_prop(),
            "domain_defaulted": True,
            "depth_tier": None,
        }

        captured = {}

        def _capture_log(level, msg, *args, extra=None, **kwargs):
            if extra and "forensic" in extra:
                captured.update(extra["forensic"])

        with patch("startd8.contractors.forensic_log.get_logger") as mock_gl:
            mock_logger = MagicMock()
            mock_logger.log = _capture_log
            mock_gl.return_value = mock_logger

            emit_forensic_log(
                call_type="design.generate",
                call=_minimal_call(),
                task=_minimal_task(),
                context_propagation=ctx,
                boundary_result_override=br,
            )

        assert len(captured["degradation_reasons"]) <= _MAX_DEGRADATION_REASONS
        assert captured["degradation_reasons_truncated"] is True


# ---------------------------------------------------------------------------
# ContextVar accessor tests
# ---------------------------------------------------------------------------


class TestContextVarAccessors:
    """Verify set_boundary_result/get_boundary_result work correctly."""

    def test_default_is_none(self):
        # Reset to ensure clean state
        token = _boundary_result_var.set(None)
        try:
            assert get_boundary_result() is None
        finally:
            _boundary_result_var.reset(token)

    def test_set_and_get(self):
        br = FakeBoundaryResult(passed=True)
        token = set_boundary_result(br)
        try:
            assert get_boundary_result() is br
        finally:
            _boundary_result_var.reset(token)

    def test_reset_restores_previous(self):
        original = get_boundary_result()
        br = FakeBoundaryResult(passed=False)
        token = set_boundary_result(br)
        assert get_boundary_result() is br
        _boundary_result_var.reset(token)
        assert get_boundary_result() is original
