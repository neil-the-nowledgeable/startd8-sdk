"""Tests for startd8.contractors.gate_contracts — GateEmitter.

Covers:
  - Factory methods: from_review_result, from_checkpoint_result, from_preflight_report
  - Emit method: publishes QUALITY_GATE_RESULT events to EventBus
  - Fallback dict shape when contextcore is not installed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from unittest.mock import patch

import pytest

from startd8.contractors.gate_contracts import GateEmitter
from startd8.events.types import EventType


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_event_bus():
    """Patch the EventBus so emitted events can be inspected."""
    with patch("startd8.contractors.gate_contracts.EventBus") as mock:
        yield mock


# ── Helpers: mock objects matching real shapes ────────────────────────


@dataclass
class _MockCheckpointResult:
    """Mimics CheckpointResult from contractors.checkpoint."""

    name: str = "Syntax Check"
    message: str = "All files valid"
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


@dataclass
class _MockCheckResult:
    """Mimics CheckResult from artisan_phases.preflight."""

    name: str = "dep:requests"
    message: str = "Package not found"


@dataclass
class _MockPreFlightReport:
    """Mimics PreFlightReport from artisan_phases.preflight."""

    _passed: bool = True
    failed_checks: List[_MockCheckResult] = field(default_factory=list)
    _warnings: List[_MockCheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self._passed

    @property
    def warnings(self) -> list:
        return self._warnings


# ── from_review_result ────────────────────────────────────────────────


class TestFromReviewResult:
    def test_passing_review(self, mock_event_bus):
        review = {
            "passed": True,
            "score": 95,
            "verdict": "PASS",
            "issues": [],
            "suggestions": ["Consider adding docstring"],
            "strengths": ["Clean code"],
        }
        result = GateEmitter.from_review_result("task-auth", review, "wf-1")

        # In fallback mode (no contextcore), result is a dict
        if isinstance(result, dict):
            assert result["result"] == "pass"
            assert result["severity"] == "info"
            assert result["blocking"] is False
            assert result["gate_id"] == "artisan.review.task-auth"
            assert result["phase"] == "REVIEW_CALIBRATE"
            assert "95" in result["reason"]
            assert result["next_action"] == "proceed"
            # One suggestion → one evidence item
            assert result["evidence"] is not None
            assert len(result["evidence"]) == 1
            assert result["evidence"][0]["type"] == "suggestion"

    def test_failing_review(self, mock_event_bus):
        review = {
            "passed": False,
            "score": 35,
            "verdict": "FAIL",
            "issues": ["Missing error handling", "No input validation"],
            "suggestions": [],
            "strengths": [],
        }
        result = GateEmitter.from_review_result("task-db", review, "wf-2")

        if isinstance(result, dict):
            assert result["result"] == "fail"
            assert result["severity"] == "error"
            assert result["blocking"] is True
            assert result["next_action"] == "revise"
            assert len(result["evidence"]) == 2
            assert result["evidence"][0]["type"] == "issue"

    def test_empty_issues_produces_null_evidence(self, mock_event_bus):
        review = {
            "passed": True,
            "score": 100,
            "verdict": "PASS",
            "issues": [],
            "suggestions": [],
            "strengths": ["Perfect"],
        }
        result = GateEmitter.from_review_result("task-x", review, "wf-3")

        if isinstance(result, dict):
            assert result["evidence"] is None

    def test_missing_keys_use_defaults(self, mock_event_bus):
        """Minimal review dict with missing optional keys."""
        review = {"passed": False, "score": 0}
        result = GateEmitter.from_review_result("task-min", review, "wf-4")

        if isinstance(result, dict):
            assert result["result"] == "fail"
            assert result["task_id"] == "task-min"


# ── from_checkpoint_result ────────────────────────────────────────────


class TestFromCheckpointResult:
    def test_passing_checkpoint(self, mock_event_bus):
        cr = _MockCheckpointResult(
            name="Syntax Check", message="3 files valid", errors=[], warnings=[]
        )
        result = GateEmitter.from_checkpoint_result(cr, "wf-1")

        if isinstance(result, dict):
            assert result["result"] == "pass"
            assert result["severity"] == "info"
            assert result["gate_id"] == "artisan.checkpoint.Syntax Check"
            assert result["phase"] == "FINALIZE_VERIFY"
            assert result["next_action"] == "resume"
            assert result["evidence"] is None

    def test_failing_checkpoint(self, mock_event_bus):
        cr = _MockCheckpointResult(
            name="Import Check",
            message="2 import errors",
            errors=["ModuleNotFoundError: foo", "ImportError: bar"],
            warnings=["Unused import: baz"],
        )
        result = GateEmitter.from_checkpoint_result(cr, "wf-2")

        if isinstance(result, dict):
            assert result["result"] == "fail"
            assert result["severity"] == "critical"
            assert result["blocking"] is True
            assert result["next_action"] == "halt"
            # 2 errors + 1 warning = 3 evidence items
            assert len(result["evidence"]) == 3
            assert result["evidence"][0]["type"] == "error"
            assert result["evidence"][2]["type"] == "warning"


# ── from_preflight_report ─────────────────────────────────────────────


class TestFromPreflightReport:
    def test_passing_preflight(self, mock_event_bus):
        report = _MockPreFlightReport(_passed=True)
        result = GateEmitter.from_preflight_report(report, "wf-1")

        if isinstance(result, dict):
            assert result["result"] == "pass"
            assert "passed" in result["reason"].lower()
            assert result["evidence"] is None

    def test_failing_preflight(self, mock_event_bus):
        failed = [_MockCheckResult(name="dep:requests", message="Not installed")]
        warned = [_MockCheckResult(name="env:TIMEOUT", message="Not set")]
        report = _MockPreFlightReport(
            _passed=False, failed_checks=failed, _warnings=warned
        )
        result = GateEmitter.from_preflight_report(report, "wf-2")

        if isinstance(result, dict):
            assert result["result"] == "fail"
            assert result["severity"] == "critical"
            assert result["blocking"] is True
            # 1 failure + 1 warning = 2 evidence items
            assert len(result["evidence"]) == 2
            assert result["evidence"][0]["type"] == "preflight_failure"
            assert result["evidence"][1]["type"] == "preflight_warning"
            assert "dep:requests" in result["evidence"][0]["ref"]


# ── emit ──────────────────────────────────────────────────────────────


class TestEmit:
    def test_emit_publishes_to_event_bus(self, mock_event_bus):
        review = {"passed": True, "score": 90, "verdict": "PASS", "issues": [], "suggestions": []}
        gate = GateEmitter.from_review_result("task-1", review, "wf-1")
        GateEmitter.emit(gate)

        mock_event_bus.emit.assert_called_once()
        event = mock_event_bus.emit.call_args[0][0]
        assert event.type == EventType.QUALITY_GATE_RESULT
        assert event.data["gate_id"] == "artisan.review.task-1"

    def test_emit_handles_dict(self, mock_event_bus):
        gate_dict = {
            "schema_version": "v1",
            "gate_id": "custom.gate",
            "result": "pass",
        }
        GateEmitter.emit(gate_dict)

        mock_event_bus.emit.assert_called_once()
        event = mock_event_bus.emit.call_args[0][0]
        assert event.data["gate_id"] == "custom.gate"


# ── Fallback when contextcore not available ───────────────────────────


class TestFallback:
    def test_fallback_returns_dict_when_contextcore_unavailable(self, mock_event_bus):
        """Even without contextcore, all factory methods return valid dicts."""
        with patch("startd8.contractors.gate_contracts.CONTEXTCORE_AVAILABLE", False):
            review = {"passed": True, "score": 80, "verdict": "PASS", "issues": [], "suggestions": []}
            result = GateEmitter.from_review_result("t1", review, "wf-1")
            assert isinstance(result, dict)
            assert result["schema_version"] == "v1"

            cr = _MockCheckpointResult()
            result = GateEmitter.from_checkpoint_result(cr, "wf-1")
            assert isinstance(result, dict)
            assert result["schema_version"] == "v1"

            report = _MockPreFlightReport()
            result = GateEmitter.from_preflight_report(report, "wf-1")
            assert isinstance(result, dict)
            assert result["schema_version"] == "v1"
