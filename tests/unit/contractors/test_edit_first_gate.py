"""Tests for the Edit-First Enforcement gate (REQ-EFE-020–023)."""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

from startd8.contractors.edit_first_gate import (
    EditFirstGateResult,
    EditFirstResult,
    _DEFAULT_EDIT_MIN_PCT,
    build_edit_retry_prompt,
    emit_rejection_telemetry,
    resolve_threshold,
    validate_task_size_regression,
)


# ── resolve_threshold tests ──────────────────────────────────────────


class TestResolveThreshold:
    """Tests for resolve_threshold()."""

    def test_resolve_threshold_with_feature_flag(self):
        """REQ-EFE-021: uses per-artifact thresholds from output_contracts."""
        output_contracts = {
            "source_code": {"edit_min_pct": 85},
            "config_file": {"edit_min_pct": 90},
        }
        schema_features = {"edit_first_enforcement": True}

        result = resolve_threshold(
            artifact_types=["source_code"],
            output_contracts=output_contracts,
            schema_features=schema_features,
        )
        assert result == 85.0

    def test_resolve_threshold_without_feature_flag(self):
        """Defaults to 80% with warning when schema_features lacks the flag."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = resolve_threshold(
                artifact_types=["source_code"],
                output_contracts={"source_code": {"edit_min_pct": 90}},
                schema_features={},
            )
            assert result == float(_DEFAULT_EDIT_MIN_PCT)
            assert len(w) == 1
            assert "edit_first_enforcement" in str(w[0].message)

    def test_resolve_threshold_multi_artifact_takes_max(self):
        """Multi-artifact tasks use max() — strictest threshold wins."""
        output_contracts = {
            "source_code": {"edit_min_pct": 75},
            "test_file": {"edit_min_pct": 90},
            "config_file": {"edit_min_pct": 80},
        }
        schema_features = {"edit_first_enforcement": True}

        result = resolve_threshold(
            artifact_types=["source_code", "test_file", "config_file"],
            output_contracts=output_contracts,
            schema_features=schema_features,
        )
        assert result == 90.0

    def test_resolve_threshold_no_contracts_for_types(self):
        """Falls back to default when feature flag present but no per-type thresholds."""
        schema_features = {"edit_first_enforcement": True}
        result = resolve_threshold(
            artifact_types=["unknown_type"],
            output_contracts={},
            schema_features=schema_features,
        )
        assert result == float(_DEFAULT_EDIT_MIN_PCT)

    def test_resolve_threshold_none_inputs(self):
        """Handles None inputs gracefully."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = resolve_threshold(
                artifact_types=[],
                output_contracts=None,
                schema_features=None,
            )
            assert result == float(_DEFAULT_EDIT_MIN_PCT)


# ── validate_task_size_regression tests ──────────────────────────────


class TestValidateTaskSizeRegression:
    """Tests for validate_task_size_regression()."""

    def test_new_file_always_passes(self):
        """New files (no existing counterpart) always pass."""
        result = validate_task_size_regression(
            task_id="T-001",
            generated_files={"new_module.py": "class Foo:\n    pass\n"},
            existing_contents={},  # no existing file
            threshold=85.0,
        )
        assert not result.any_rejected
        assert len(result.file_results) == 1
        assert result.file_results[0].action == "new_file"
        assert result.file_results[0].passed is True

    def test_edit_above_threshold_passes(self):
        """Output at 90% of original with 80% threshold passes."""
        original = "x" * 1000
        edited = "x" * 900  # 90% of original
        result = validate_task_size_regression(
            task_id="T-002",
            generated_files={"module.py": edited},
            existing_contents={"module.py": original},
            threshold=80.0,
        )
        assert not result.any_rejected
        assert result.file_results[0].passed is True
        assert result.file_results[0].action == "passed"
        assert result.file_results[0].ratio == pytest.approx(90.0)

    def test_edit_below_threshold_rejects(self):
        """Output at 50% of original with 85% threshold is rejected."""
        original = "x" * 1000
        rewritten = "y" * 500  # 50% of original
        result = validate_task_size_regression(
            task_id="T-003",
            generated_files={"module.py": rewritten},
            existing_contents={"module.py": original},
            threshold=85.0,
        )
        assert result.any_rejected
        assert result.retry_needed
        assert result.file_results[0].passed is False
        assert result.file_results[0].action == "rejected"
        assert result.file_results[0].ratio == pytest.approx(50.0)

    def test_force_rewrite_overrides(self):
        """force_rewrite=True overrides rejection with action="force_overridden"."""
        original = "x" * 1000
        rewritten = "y" * 100  # 10% — would normally reject
        result = validate_task_size_regression(
            task_id="T-004",
            generated_files={"module.py": rewritten},
            existing_contents={"module.py": original},
            threshold=85.0,
            force_rewrite=True,
        )
        assert not result.any_rejected
        assert result.file_results[0].passed is True
        assert result.file_results[0].action == "force_overridden"

    def test_char_count_not_line_count(self):
        """Gate uses len() (character count) not splitlines() (line count).

        A file with many short lines should produce a different ratio than
        a file with few long lines, even if line count is the same.
        """
        # Same number of lines (10), but very different character counts
        original = "\n".join(["a" * 100] * 10)  # 10 lines, ~1000 chars
        # 10 lines of 10 chars = ~100 chars (10% of original)
        generated = "\n".join(["a" * 10] * 10)

        result = validate_task_size_regression(
            task_id="T-005",
            generated_files={"module.py": generated},
            existing_contents={"module.py": original},
            threshold=80.0,
        )
        # Character ratio ~10%, well below 80% threshold — should reject
        assert result.any_rejected
        assert result.file_results[0].passed is False
        # Verify it's using character count, not line count
        assert result.file_results[0].input_chars == len(original)
        assert result.file_results[0].output_chars == len(generated)

    def test_empty_existing_file_passes(self):
        """Empty existing file treated as new — ratio is 100%."""
        result = validate_task_size_regression(
            task_id="T-006",
            generated_files={"module.py": "new content"},
            existing_contents={"module.py": ""},
            threshold=85.0,
        )
        assert not result.any_rejected
        assert result.file_results[0].ratio == 100.0


# ── emit_rejection_telemetry tests ───────────────────────────────────


class TestEmitRejectionTelemetry:
    """Tests for emit_rejection_telemetry()."""

    def test_emit_telemetry_attributes(self):
        """Verify add_event is called with correct event name and attributes."""
        mock_span = MagicMock()
        gate_result = EditFirstGateResult(
            task_id="T-007",
            file_results=[
                EditFirstResult(
                    file_path="src/module.py",
                    input_chars=1000,
                    output_chars=400,
                    ratio=40.0,
                    threshold=85.0,
                    artifact_type="source_code",
                    passed=False,
                    action="rejected",
                ),
            ],
            any_rejected=True,
        )

        emit_rejection_telemetry(gate_result, mock_span)

        mock_span.add_event.assert_called_once()
        call_args = mock_span.add_event.call_args
        assert call_args[0][0] == "edit_first.size_regression"
        attrs = call_args[1]["attributes"]
        assert attrs["task.id"] == "T-007"
        assert attrs["file.path"] == "src/module.py"
        assert attrs["edit_first.input_chars"] == 1000
        assert attrs["edit_first.output_chars"] == 400
        assert attrs["edit_first.ratio_pct"] == 40.0
        assert attrs["edit_first.threshold_pct"] == 85.0
        assert attrs["edit_first.artifact_type"] == "source_code"
        assert attrs["edit_first.action"] == "rejected"

    def test_emit_telemetry_skips_passed_files(self):
        """Only rejected files emit telemetry events."""
        mock_span = MagicMock()
        gate_result = EditFirstGateResult(
            task_id="T-008",
            file_results=[
                EditFirstResult(
                    file_path="src/module.py",
                    input_chars=1000,
                    output_chars=950,
                    ratio=95.0,
                    threshold=85.0,
                    artifact_type="source_code",
                    passed=True,
                    action="passed",
                ),
            ],
        )

        emit_rejection_telemetry(gate_result, mock_span)
        mock_span.add_event.assert_not_called()

    def test_emit_telemetry_none_span(self):
        """None span is handled gracefully (no-op)."""
        gate_result = EditFirstGateResult(task_id="T-009", any_rejected=True)
        # Should not raise
        emit_rejection_telemetry(gate_result, None)


# ── build_edit_retry_prompt tests ────────────────────────────────────


class TestBuildEditRetryPrompt:
    """Tests for build_edit_retry_prompt()."""

    def test_build_retry_prompt_content(self):
        """Prompt includes original content, threshold, and ratio."""
        prompt = build_edit_retry_prompt(
            original_content="def hello():\n    print('hello')\n",
            design_doc="Add goodbye function",
            task_description="Add a goodbye() function to module.py",
            ratio=45.0,
            threshold=85.0,
        )
        # Must include the original content
        assert "def hello():" in prompt
        assert "print('hello')" in prompt
        # Must include the ratio and threshold
        assert "45.0%" in prompt
        assert "85.0%" in prompt
        # Must include task description
        assert "Add a goodbye() function" in prompt
        # Must include design doc
        assert "Add goodbye function" in prompt
        # Must instruct to EDIT not rewrite
        assert "EDIT" in prompt
        assert "not rewrite" in prompt
