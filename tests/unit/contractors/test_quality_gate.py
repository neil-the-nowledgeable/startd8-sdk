"""Tests for the quality gate feature (Fix 2).

Validates _check_quality_gate() behavior in skip/warn/block modes
for TEST and REVIEW phases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    PhaseResult,
    PhaseStatus,
    QualityGateError,
    WorkflowConfig,
    WorkflowPhase,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_phase_result(
    phase: WorkflowPhase,
    output: Optional[dict[str, Any]] = None,
    status: PhaseStatus = PhaseStatus.COMPLETED,
) -> PhaseResult:
    """Build a minimal PhaseResult for testing."""
    return PhaseResult(
        phase=phase,
        status=status,
        output=output or {},
        cost=0.0,
        duration_seconds=1.0,
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T00:00:01Z",
    )


def _make_workflow(quality_gate: str = "warn") -> ArtisanContractorWorkflow:
    """Build a minimal ArtisanContractorWorkflow for gate testing."""
    config = WorkflowConfig(dry_run=True)
    return ArtisanContractorWorkflow(config=config, quality_gate=quality_gate)


# ============================================================================
# Block mode
# ============================================================================


class TestQualityGateBlock:
    """Block mode raises QualityGateError on failures."""

    def test_design_phase_failures_raise(self):
        wf = _make_workflow("block")
        pr = _make_phase_result(
            WorkflowPhase.DESIGN,
            output={
                "total_failed": 2,
                "total_passed": 1,
                "agreement_rate": 1 / 3,
                "per_task": {
                    "T-1": {"passed": True, "status": "designed"},
                    "T-2": {"passed": False, "status": "designed", "reason": "DUAL_REJECTION"},
                    "T-3": {"passed": False, "status": "design_failed", "reason": "DESIGN_FAILED"},
                },
            },
        )
        with pytest.raises(QualityGateError) as exc_info:
            wf._check_quality_gate(WorkflowPhase.DESIGN, pr)

        assert exc_info.value.phase == WorkflowPhase.DESIGN
        assert exc_info.value.details["total_failed"] == 2
        assert "T-2" in exc_info.value.details["failed_designs"]
        assert exc_info.value.details["agreement_rate"] == pytest.approx(1 / 3)

    def test_test_phase_failures_raise(self):
        wf = _make_workflow("block")
        pr = _make_phase_result(
            WorkflowPhase.TEST,
            output={
                "total_failed": 3,
                "total_passed": 2,
                "per_task": {
                    "T-1": {"passed": True},
                    "T-2": {"passed": False, "failures": ["import_check"]},
                    "T-3": {"passed": False, "failures": ["syntax_check"]},
                    "T-4": {"passed": False, "failures": ["lint_check"]},
                    "T-5": {"passed": True},
                },
            },
        )
        with pytest.raises(QualityGateError) as exc_info:
            wf._check_quality_gate(WorkflowPhase.TEST, pr)

        assert exc_info.value.phase == WorkflowPhase.TEST
        assert exc_info.value.details["total_failed"] == 3
        assert "T-2" in exc_info.value.details["failed_tasks"]

    def test_review_phase_failures_raise(self):
        wf = _make_workflow("block")
        pr = _make_phase_result(
            WorkflowPhase.REVIEW,
            output={
                "total_failed": 1,
                "total_passed": 4,
                "per_task": {
                    "T-1": {"passed": True, "score": 85, "verdict": "PASS"},
                    "T-2": {"passed": False, "score": 22, "verdict": "FAIL"},
                },
            },
        )
        with pytest.raises(QualityGateError) as exc_info:
            wf._check_quality_gate(WorkflowPhase.REVIEW, pr)

        assert exc_info.value.phase == WorkflowPhase.REVIEW
        assert exc_info.value.details["failed_reviews"] == {"T-2": 22}

    def test_zero_failures_pass(self):
        wf = _make_workflow("block")
        pr = _make_phase_result(
            WorkflowPhase.TEST,
            output={"total_failed": 0, "total_passed": 5},
        )
        # Should not raise
        wf._check_quality_gate(WorkflowPhase.TEST, pr)


# ============================================================================
# Warn mode
# ============================================================================


class TestQualityGateWarn:
    """Warn mode logs but does not raise."""

    def test_design_phase_failures_log_warning(self, caplog):
        wf = _make_workflow("warn")
        pr = _make_phase_result(
            WorkflowPhase.DESIGN,
            output={
                "total_failed": 1,
                "total_passed": 2,
                "agreement_rate": 2 / 3,
                "per_task": {
                    "T-1": {"passed": True},
                    "T-2": {"passed": False, "reason": "DUAL_REJECTION"},
                    "T-3": {"passed": True},
                },
            },
        )
        with caplog.at_level(logging.WARNING):
            wf._check_quality_gate(WorkflowPhase.DESIGN, pr)

        assert "QUALITY GATE WARNING" in caplog.text
        assert "DESIGN quality gate: 1 task(s) failed design quality" in caplog.text

    def test_test_phase_failures_log_warning(self, caplog):
        wf = _make_workflow("warn")
        pr = _make_phase_result(
            WorkflowPhase.TEST,
            output={
                "total_failed": 2,
                "total_passed": 3,
                "per_task": {
                    "T-1": {"passed": False},
                    "T-2": {"passed": False},
                },
            },
        )
        with caplog.at_level(logging.WARNING):
            wf._check_quality_gate(WorkflowPhase.TEST, pr)

        assert "QUALITY GATE WARNING" in caplog.text
        assert "2 task(s) failed validation" in caplog.text

    def test_review_phase_failures_log_warning(self, caplog):
        wf = _make_workflow("warn")
        pr = _make_phase_result(
            WorkflowPhase.REVIEW,
            output={
                "total_failed": 1,
                "total_passed": 4,
                "per_task": {
                    "T-1": {"passed": False, "score": 22},
                },
            },
        )
        with caplog.at_level(logging.WARNING):
            wf._check_quality_gate(WorkflowPhase.REVIEW, pr)

        assert "QUALITY GATE WARNING" in caplog.text
        assert "1 task(s) failed review" in caplog.text

    def test_zero_failures_no_warning(self, caplog):
        wf = _make_workflow("warn")
        pr = _make_phase_result(
            WorkflowPhase.TEST,
            output={"total_failed": 0, "total_passed": 5},
        )
        with caplog.at_level(logging.WARNING):
            wf._check_quality_gate(WorkflowPhase.TEST, pr)

        assert "QUALITY GATE" not in caplog.text

    def test_records_traceable_gate_outcome(self):
        wf = _make_workflow("warn")
        wf._active_workflow_context = {}
        pr = _make_phase_result(
            WorkflowPhase.DESIGN,
            output={
                "total_failed": 1,
                "total_passed": 0,
                "agreement_rate": 0.0,
                "per_task": {"T-1": {"passed": False, "reason": "DESIGN_FAILED"}},
            },
        )
        wf._check_quality_gate(WorkflowPhase.DESIGN, pr)

        assert len(wf._quality_gate_outcomes) == 1
        outcome = wf._quality_gate_outcomes[0]
        assert outcome["gate_id"] == "artisan.design.quality"
        assert outcome["contract_signal_id"] == "design_quality.total_failed"
        assert outcome["policy_mode"] == "warn"
        assert outcome["threshold"]["metric"] == "total_failed"
        assert outcome["observed_value"] == 1
        assert outcome["decision"] == "warn"
        assert outcome["violated"] is True
        summary = wf._active_workflow_context["quality_gate_summary"]
        assert summary["violation_count"] == 1
        assert len(wf._active_workflow_context["quality_gate_outcomes"]) == 1


# ============================================================================
# Skip mode
# ============================================================================


class TestQualityGateSkip:
    """Skip mode does nothing regardless of failures."""

    def test_design_phase_failures_ignored(self):
        wf = _make_workflow("skip")
        pr = _make_phase_result(
            WorkflowPhase.DESIGN,
            output={"total_failed": 4, "total_passed": 0},
        )
        wf._check_quality_gate(WorkflowPhase.DESIGN, pr)

    def test_test_phase_failures_ignored(self):
        wf = _make_workflow("skip")
        pr = _make_phase_result(
            WorkflowPhase.TEST,
            output={"total_failed": 5, "total_passed": 0},
        )
        # Should not raise
        wf._check_quality_gate(WorkflowPhase.TEST, pr)

    def test_review_phase_failures_ignored(self):
        wf = _make_workflow("skip")
        pr = _make_phase_result(
            WorkflowPhase.REVIEW,
            output={"total_failed": 5, "total_passed": 0},
        )
        # Should not raise
        wf._check_quality_gate(WorkflowPhase.REVIEW, pr)


# ============================================================================
# Edge cases
# ============================================================================


class TestQualityGateEdgeCases:
    """Edge cases: empty output, non-dict output, non-gate phases."""

    def test_none_output_no_crash(self):
        wf = _make_workflow("block")
        pr = _make_phase_result(WorkflowPhase.TEST, output=None)
        # Should not raise (no output to inspect)
        wf._check_quality_gate(WorkflowPhase.TEST, pr)

    def test_non_test_review_phase_ignored(self):
        wf = _make_workflow("block")
        pr = _make_phase_result(
            WorkflowPhase.IMPLEMENT,
            output={"total_failed": 99},
        )
        # Should not raise (IMPLEMENT is not a gate phase)
        wf._check_quality_gate(WorkflowPhase.IMPLEMENT, pr)

    def test_missing_per_task_key(self):
        """Block mode with failures but no per_task detail."""
        wf = _make_workflow("block")
        pr = _make_phase_result(
            WorkflowPhase.TEST,
            output={"total_failed": 1, "total_passed": 4},
        )
        with pytest.raises(QualityGateError) as exc_info:
            wf._check_quality_gate(WorkflowPhase.TEST, pr)

        assert exc_info.value.details["failed_tasks"] == []

    def test_constructor_uses_env_quality_gate_mode(self):
        with patch.dict("os.environ", {"STARTD8_QUALITY_GATE_MODE": "block"}):
            wf = ArtisanContractorWorkflow(config=WorkflowConfig(dry_run=True))
        assert wf._quality_gate == "block"
