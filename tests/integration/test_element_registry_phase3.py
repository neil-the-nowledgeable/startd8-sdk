"""Phase 3 integration tests for Element Registry intelligence layer.

Tests Steps 3.1-3.4: REVIEW element scoring, cross-run Kaizen metrics,
warm-up reconciliation, and element lineage tracking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from startd8.element_registry import (
    ElementEntry,
    ElementLineage,
    ElementRegistry,
    PhaseRecord,
    ReconciliationReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry(tmp_path: Path) -> ElementRegistry:
    """Create a pre-populated element registry with phase history."""
    state = tmp_path / "state"
    state.mkdir()
    reg = ElementRegistry(state_dir=state)

    # Element with code (previously generated)
    reg.put(ElementEntry(
        element_id="function/mymod-abc123",
        kind="function",
        name="my_func",
        file_path="src/pkg/mymod.py",
        phases={},
        extra={"code": "return 42"},
    ))
    reg.set_phase_status("function/mymod-abc123", "plan_ingestion", "specified")
    reg.set_phase_status("function/mymod-abc123", "implement", "generated")

    # Element without code
    reg.put(ElementEntry(
        element_id="class/mymod-def456",
        kind="class",
        name="MyClass",
        file_path="src/pkg/mymod.py",
        phases={},
        extra={},
    ))
    reg.set_phase_status("class/mymod-def456", "plan_ingestion", "specified")

    # Element in a different file
    reg.put(ElementEntry(
        element_id="function/other-ghi789",
        kind="function",
        name="helper",
        file_path="src/pkg/other.py",
        phases={},
        extra={"code": "pass"},
    ))
    return reg


# ---------------------------------------------------------------------------
# Step 3.1: REVIEW Phase Element Scoring (ER-010)
# ---------------------------------------------------------------------------


class TestReviewElementScoring:
    """Step 3.1: ReviewPhaseHandler scores elements from review results."""

    def test_score_elements_from_review(self, registry: ElementRegistry) -> None:
        """Review items map scores to matching elements."""
        from startd8.contractors.context_seed.core import ReviewPhaseHandler

        task = mock.MagicMock()
        task.task_id = "T-001"
        task.target_files = ["src/pkg/mymod.py"]

        review_items = [
            {
                "task_id": "T-001",
                "score": 85,
                "verdict": "PASS",
                "passed": True,
                "issues": ["Minor: naming convention"],
            },
        ]

        scored = ReviewPhaseHandler._score_elements_from_review(
            review_items, [task], registry,
        )
        # Both elements in src/pkg/mymod.py should be scored
        assert scored == 2

        entry = registry.get("function/mymod-abc123")
        assert "review" in entry.phases
        records = entry.phases["review"]
        assert len(records) >= 1
        latest = records[-1]
        assert "passed:85" in latest.status
        assert latest.metadata["score"] == 85

    def test_score_elements_no_registry(self) -> None:
        """When registry is None, scoring is a no-op."""
        from startd8.contractors.context_seed.core import ReviewPhaseHandler

        # Should not crash
        scored = ReviewPhaseHandler._score_elements_from_review(
            [{"task_id": "T-1", "score": 50, "passed": False}],
            [],
            None,
        )
        assert scored == 0

    def test_score_elements_missing_task(self, registry: ElementRegistry) -> None:
        """Review items for unknown tasks are silently skipped."""
        from startd8.contractors.context_seed.core import ReviewPhaseHandler

        scored = ReviewPhaseHandler._score_elements_from_review(
            [{"task_id": "T-UNKNOWN", "score": 50, "passed": False}],
            [],  # no tasks
            registry,
        )
        assert scored == 0


# ---------------------------------------------------------------------------
# Step 3.2: Cross-Run Kaizen Metrics (ER-014)
# ---------------------------------------------------------------------------


class TestCrossRunKaizenMetrics:
    """Step 3.2: write_run_metrics + compare_runs."""

    def test_write_and_compare_runs(self, registry: ElementRegistry) -> None:
        """Write two run snapshots and compare them."""
        # Write first run
        registry.write_run_metrics("run-001")

        # Add another element
        registry.put(ElementEntry(
            element_id="function/new-xyz000",
            kind="function",
            name="new_func",
            file_path="src/pkg/new.py",
            phases={},
            extra={},
        ))

        # Write second run
        registry.write_run_metrics("run-002")

        # Compare
        comparison = registry.compare_runs("run-001", "run-002")
        assert comparison  # not empty
        assert comparison["delta"]["total"] == 1  # one element added

    def test_compare_missing_run(self, registry: ElementRegistry) -> None:
        """compare_runs returns empty dict when a run is missing."""
        registry.write_run_metrics("run-only")
        result = registry.compare_runs("run-only", "run-nonexistent")
        assert result == {}

    def test_write_run_metrics_creates_file(self, registry: ElementRegistry) -> None:
        """Run metrics file is persisted to disk."""
        registry.write_run_metrics("run-test")
        runs_dir = registry._runs_dir
        assert (runs_dir / "run-test.json").exists()


# ---------------------------------------------------------------------------
# Step 3.3: Warm Up Reconciliation (ER-015)
# ---------------------------------------------------------------------------


class TestWarmUpReconciliation:
    """Step 3.3: reconcile() compares registry vs external backup."""

    def test_reconcile_all_matched(self, registry: ElementRegistry) -> None:
        """When backup matches registry, all are matched."""
        backup = {
            "function/mymod-abc123": "hash1",
            "class/mymod-def456": "hash2",
            "function/other-ghi789": "hash3",
        }
        report = registry.reconcile(backup, "test-backup")
        assert isinstance(report, ReconciliationReport)
        assert len(report.matched) == 3
        assert len(report.missing) == 0
        assert len(report.extra) == 0
        assert report.tool == "test-backup"

    def test_reconcile_missing_elements(self, registry: ElementRegistry) -> None:
        """Elements in backup but not in registry show as missing."""
        backup = {
            "function/mymod-abc123": "hash1",
            "function/unknown-zzz000": "hash4",
        }
        report = registry.reconcile(backup, "test-backup")
        assert "function/unknown-zzz000" in report.missing

    def test_reconcile_extra_elements(self, registry: ElementRegistry) -> None:
        """Elements in registry but not in backup show as extra."""
        backup = {"function/mymod-abc123": "hash1"}
        report = registry.reconcile(backup, "test-backup")
        assert len(report.extra) == 2  # def456 and ghi789


# ---------------------------------------------------------------------------
# Step 3.4: Element Lineage (ER-018)
# ---------------------------------------------------------------------------


class TestElementLineage:
    """Step 3.4: element_lineage() returns complete history."""

    def test_element_lineage_full_history(self, registry: ElementRegistry) -> None:
        """Element with multiple phase records returns sorted history."""
        lineage = registry.element_lineage("function/mymod-abc123")
        assert lineage is not None
        assert isinstance(lineage, ElementLineage)
        assert lineage.element_id == "function/mymod-abc123"

        # Should have plan_ingestion + implement records
        assert len(lineage.history) >= 2
        assert "plan_ingestion" in lineage.current_phases
        assert "implement" in lineage.current_phases
        assert lineage.current_phases["plan_ingestion"] == "specified"
        assert lineage.current_phases["implement"] == "generated"

    def test_element_lineage_missing_element(self, registry: ElementRegistry) -> None:
        """Unknown element returns None."""
        lineage = registry.element_lineage("function/nonexistent")
        assert lineage is None

    def test_element_lineage_history_sorted(self, registry: ElementRegistry) -> None:
        """History records are sorted by timestamp ascending."""
        lineage = registry.element_lineage("function/mymod-abc123")
        assert lineage is not None
        timestamps = [r.timestamp for r in lineage.history if r.timestamp]
        assert timestamps == sorted(timestamps)

    def test_element_lineage_tracks_review_scoring(self, registry: ElementRegistry) -> None:
        """After review scoring, lineage includes the review phase."""
        registry.set_phase_status(
            "function/mymod-abc123", "review", "passed:90",
            metadata={"score": 90},
        )
        lineage = registry.element_lineage("function/mymod-abc123")
        assert "review" in lineage.current_phases
        assert lineage.current_phases["review"] == "passed:90"


# ---------------------------------------------------------------------------
# Cross-cutting: full lineage through pipeline
# ---------------------------------------------------------------------------


class TestFullPipelineLineage:
    """End-to-end: element tracked through plan → implement → review."""

    def test_full_pipeline_lineage(self, registry: ElementRegistry) -> None:
        """An element tracked through multiple phases has complete lineage."""
        eid = "function/mymod-abc123"

        # Simulate remaining phases
        registry.set_phase_status(eid, "design", "contracted:add")
        registry.set_phase_status(eid, "integrate", "merged")
        registry.set_phase_status(eid, "test", "covered")
        registry.set_phase_status(eid, "review", "passed:95")

        lineage = registry.element_lineage(eid)
        assert lineage is not None

        # Should have all phases
        phases = set(lineage.current_phases.keys())
        expected = {"plan_ingestion", "implement", "design", "integrate", "test", "review"}
        assert expected.issubset(phases)

        # Summary should reflect all phases
        summary = registry.summary()
        assert summary.total == 3
        assert "review" in summary.by_phase_status
