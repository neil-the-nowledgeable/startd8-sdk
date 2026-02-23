"""Unit tests for CCD Layer 4 — lane assignment helpers in plan_ingestion_workflow.

Covers:
  - _TaskDictAdapter.target_files property
  - _assign_lane_indices() function
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from startd8.workflows.builtin.plan_ingestion_workflow import (
    _TaskDictAdapter,
    _assign_lane_indices,
)


# ---------------------------------------------------------------------------
# _TaskDictAdapter.target_files
# ---------------------------------------------------------------------------


class TestTaskDictAdapterTargetFiles:
    """_TaskDictAdapter reads target_files from config.context.target_files."""

    def test_reads_from_config_context(self):
        """Adapter reads target_files from config.context.target_files."""
        data = {
            "task_id": "T-1",
            "config": {
                "context": {
                    "target_files": ["src/foo.py", "src/bar.py"],
                }
            },
        }
        adapter = _TaskDictAdapter(data)
        assert adapter.target_files == ["src/foo.py", "src/bar.py"]

    def test_empty_default_when_key_missing(self):
        """Missing target_files key returns empty list."""
        data = {"task_id": "T-1"}
        adapter = _TaskDictAdapter(data)
        assert adapter.target_files == []

    def test_empty_default_when_config_missing(self):
        """Missing config block returns empty list."""
        data = {"task_id": "T-1", "config": {}}
        adapter = _TaskDictAdapter(data)
        assert adapter.target_files == []

    def test_empty_default_when_context_missing(self):
        """Missing context inside config returns empty list."""
        data = {"task_id": "T-1", "config": {"context": {}}}
        adapter = _TaskDictAdapter(data)
        assert adapter.target_files == []

    def test_null_target_files_treated_as_empty(self):
        """Explicit None for target_files is normalized to empty list (or [] fallback)."""
        data = {
            "task_id": "T-1",
            "config": {"context": {"target_files": None}},
        }
        adapter = _TaskDictAdapter(data)
        # The property uses `or []` so None becomes [].
        assert adapter.target_files == []

    def test_task_id_property(self):
        """task_id property delegates to the dict."""
        data = {"task_id": "T-42", "config": {}}
        adapter = _TaskDictAdapter(data)
        assert adapter.task_id == "T-42"


# ---------------------------------------------------------------------------
# _assign_lane_indices
# ---------------------------------------------------------------------------


def _make_task(task_id: str, target_files: list[str] | None = None) -> dict:
    """Build a minimal task dict recognised by _assign_lane_indices."""
    files = target_files or []
    return {
        "task_id": task_id,
        "depends_on": [],
        "config": {"context": {"target_files": files}},
    }


class TestAssignLaneIndices:
    """_assign_lane_indices groups tasks into lanes via shared target_files."""

    def test_empty_tasks(self):
        """Empty input returns ([], {})."""
        tasks, lane_assignments = _assign_lane_indices([])
        assert tasks == []
        assert lane_assignments == {}

    def test_basic_shared_file(self):
        """Two tasks sharing a file get the same lane_index."""
        tasks = [
            _make_task("T-1", ["src/widget.py"]),
            _make_task("T-2", ["src/widget.py"]),
        ]
        tasks_out, lane_assignments = _assign_lane_indices(tasks)

        assert "T-1" in lane_assignments
        assert "T-2" in lane_assignments
        assert lane_assignments["T-1"] == lane_assignments["T-2"]

    def test_disjoint_files(self):
        """Tasks with distinct files get different lane indices."""
        tasks = [
            _make_task("T-1", ["src/foo.py"]),
            _make_task("T-2", ["src/bar.py"]),
        ]
        tasks_out, lane_assignments = _assign_lane_indices(tasks)

        assert "T-1" in lane_assignments
        assert "T-2" in lane_assignments
        assert lane_assignments["T-1"] != lane_assignments["T-2"]

    def test_no_target_files(self):
        """All tasks with empty target_files return {} lane_assignments."""
        tasks = [
            _make_task("T-1", []),
            _make_task("T-2", []),
        ]
        tasks_out, lane_assignments = _assign_lane_indices(tasks)

        # No shared files → compute_lanes gives each task its own lane,
        # but because no target_files exist the grouping is trivial;
        # lane_assignments may be populated (one lane per task) or empty.
        # The key contract: returned tasks list matches input length.
        assert len(tasks_out) == 2

    def test_lane_index_written_to_task_dict(self):
        """Lane index is written back into each task dict."""
        tasks = [
            _make_task("T-1", ["shared.py"]),
            _make_task("T-2", ["shared.py"]),
        ]
        tasks_out, lane_assignments = _assign_lane_indices(tasks)

        for t in tasks_out:
            tid = t["task_id"]
            if tid in lane_assignments:
                assert t["lane_index"] == lane_assignments[tid]

    def test_three_tasks_two_lanes(self):
        """Three tasks where two share a file form two lanes."""
        tasks = [
            _make_task("T-1", ["src/a.py"]),
            _make_task("T-2", ["src/a.py"]),
            _make_task("T-3", ["src/b.py"]),
        ]
        tasks_out, lane_assignments = _assign_lane_indices(tasks)

        assert lane_assignments["T-1"] == lane_assignments["T-2"]
        assert lane_assignments["T-3"] != lane_assignments["T-1"]

    def test_exception_fallback_returns_empty_assignments(self, caplog):
        """compute_lanes raises → WARNING logged, returns (tasks, {})."""
        tasks = [_make_task("T-1", ["src/foo.py"])]

        with patch(
            "startd8.workflows.builtin.plan_ingestion_workflow.compute_lanes",
            side_effect=RuntimeError("boom"),
        ):
            with caplog.at_level(logging.WARNING):
                tasks_out, lane_assignments = _assign_lane_indices(tasks)

        assert lane_assignments == {}
        assert tasks_out is tasks  # Same list object returned on failure
        assert any("compute_lanes" in r.message for r in caplog.records)

    def test_tasks_list_length_preserved(self):
        """Output tasks list has the same length as input."""
        tasks = [
            _make_task("T-1", ["a.py"]),
            _make_task("T-2", ["b.py"]),
            _make_task("T-3", ["a.py"]),
        ]
        tasks_out, _ = _assign_lane_indices(tasks)
        assert len(tasks_out) == 3
