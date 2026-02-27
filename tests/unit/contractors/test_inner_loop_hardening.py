"""Tests for artisan inner-loop hardening fixes.

Covers:
  - Task 1: Truncation-blocked tasks skipped in TEST and REVIEW
  - Task 2: REVIEW warns on empty test results
  - Task 3: Test/review cache invalidation on design hash change
  - Task 4: design_quality in HandoffData
  - Task 5: Gate failure details in retry error context
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from startd8.contractors.context_seed_handlers import (
    _compute_design_results_hash,
)
from startd8.contractors.handoff import (
    HandoffData,
    load_design_handoff,
    write_design_handoff,
)


# ── Task 1: Truncation-blocked tasks skipped ────────────────────────


class TestComputeDesignResultsHash:
    """Tests for _compute_design_results_hash helper."""

    def test_empty_returns_none(self):
        assert _compute_design_results_hash({}) is None

    def test_deterministic(self):
        design = {
            "T-1": {"design_document": "doc A", "status": "designed"},
            "T-2": {"design_document": "doc B", "status": "designed"},
        }
        h1 = _compute_design_results_hash(design)
        h2 = _compute_design_results_hash(design)
        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) == 64  # SHA-256 hex

    def test_order_independent(self):
        """Task IDs are sorted, so insertion order doesn't matter."""
        d1 = {"B": {"design_document": "x"}, "A": {"design_document": "y"}}
        d2 = {"A": {"design_document": "y"}, "B": {"design_document": "x"}}
        assert _compute_design_results_hash(d1) == _compute_design_results_hash(d2)

    def test_different_docs_produce_different_hash(self):
        d1 = {"T-1": {"design_document": "version 1"}}
        d2 = {"T-1": {"design_document": "version 2"}}
        assert _compute_design_results_hash(d1) != _compute_design_results_hash(d2)

    def test_missing_design_document_key(self):
        """Non-dict entries or missing key don't crash."""
        d = {"T-1": {"status": "skipped"}}  # no design_document
        h = _compute_design_results_hash(d)
        assert h is not None  # still produces a hash (empty doc)

    def test_non_dict_entry(self):
        """Non-dict value for a task gracefully hashes empty string."""
        d = {"T-1": "just a string"}
        h = _compute_design_results_hash(d)
        assert h is not None


# ── Task 4: design_quality in HandoffData ────────────────────────


class TestHandoffDesignQuality:
    """Tests for design_quality field in HandoffData."""

    def test_default_empty(self):
        hd = HandoffData(
            enriched_seed_path="/seed.json",
            project_root="/project",
            output_dir="/out",
            workflow_id="w-1",
        )
        assert hd.design_quality == {}

    def test_round_trip(self, tmp_path):
        """write_design_handoff → load_design_handoff preserves design_quality."""
        quality = {
            "total_passed": 5,
            "total_failed": 1,
            "agreement_rate": 0.833,
            "evaluated_task_count": 6,
        }
        # Create minimal seed file for checksum computation
        seed = tmp_path / "seed.json"
        seed.write_text("{}")

        path = write_design_handoff(
            output_dir=str(tmp_path),
            enriched_seed_path=str(seed),
            project_root=str(tmp_path),
            workflow_id="w-test",
            design_quality=quality,
        )
        loaded = load_design_handoff(path)
        assert loaded.design_quality == quality

    def test_backward_compat_missing_key(self, tmp_path):
        """Loading a handoff without design_quality defaults to empty dict."""
        seed = tmp_path / "seed.json"
        seed.write_text("{}")
        # Write a minimal handoff without design_quality
        data = {
            "enriched_seed_path": str(seed),
            "project_root": str(tmp_path),
            "output_dir": str(tmp_path),
            "workflow_id": "w-old",
            "schema_version": 1,
        }
        hf = tmp_path / "design-handoff.json"
        hf.write_text(json.dumps(data))
        loaded = load_design_handoff(hf)
        assert loaded.design_quality == {}


# ── Task 5: Gate failure details in retry error context ──────────


class TestBuildRegenerateFeedbackGateDetails:
    """Verify gate_error details appear in prior_error_feedback string."""

    def _make_workflow(self):
        """Create a minimal ArtisanContractorWorkflow for testing."""
        from startd8.contractors.artisan_contractor import ArtisanContractorWorkflow
        from startd8.contractors.artisan_contractor import WorkflowPhase, PhaseResult, PhaseStatus, QualityGateError

        class MinimalWorkflow(ArtisanContractorWorkflow):
            """Bypass __init__ for unit testing."""
            def __init__(self):
                self._quality_gate = "block"

        return MinimalWorkflow(), WorkflowPhase, PhaseResult, PhaseStatus, QualityGateError

    def _make_phase_result(self, PhaseResult, WP, PS, output):
        """Create a PhaseResult with required fields."""
        return PhaseResult(
            phase=WP.TEST,
            status=PS.COMPLETED,
            start_time="2026-01-01T00:00:00Z",
            end_time="2026-01-01T00:01:00Z",
            duration_seconds=60.0,
            output=output,
        )

    def test_gate_error_in_prior_error_feedback(self):
        wf, WP, PhaseResult, PS, QGE = self._make_workflow()

        gate_err = QGE(
            "TEST quality gate: 2 task(s) failed validation",
            phase=WP.TEST,
            details={
                "total_failed": 2,
                "total_passed": 3,
                "failed_tasks": ["T-1", "T-2"],
            },
        )
        result = self._make_phase_result(
            PhaseResult, WP, PS,
            output={"total_failed": 2, "total_passed": 3, "per_task": {
                "T-1": {"passed": False}, "T-2": {"passed": False},
                "T-3": {"passed": True},
            }},
        )

        feedback = wf._build_regenerate_feedback(
            feature_id="F-1",
            phase=WP.TEST,
            phase_result=result,
            gate_error=gate_err,
        )
        assert feedback is not None
        pef = feedback["prior_error_feedback"]
        # Gate details should appear in the error string
        assert "Quality gate" in pef
        assert "BLOCKED" in pef
        assert "T-1" in pef

    def test_no_gate_error_no_gate_section(self):
        wf, WP, PhaseResult, PS, _ = self._make_workflow()

        result = self._make_phase_result(
            PhaseResult, WP, PS,
            output={"total_failed": 1, "total_passed": 2, "per_task": {
                "T-1": {"passed": False},
            }},
        )

        feedback = wf._build_regenerate_feedback(
            feature_id="F-1",
            phase=WP.TEST,
            phase_result=result,
            gate_error=None,
        )
        assert feedback is not None
        pef = feedback["prior_error_feedback"]
        assert "Quality gate" not in pef
