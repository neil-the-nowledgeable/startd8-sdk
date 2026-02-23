"""
Unit tests for CCD Layer 1: Lane-Aware Design Ordering.

Tests cover:
    - compute_lanes() called once before the design loop with the full task list
    - _lane_assignments dict populated from compute_lanes() output
    - Wave-sort within each lane (wave_index ascending, None sorts last)
    - Tiebreak by task_id when wave_index values are equal
    - Lane-sequential iteration order (lane 0 tasks before lane 1 tasks, etc.)
    - Graceful fallback to flat iteration when compute_lanes() raises
    - Lane assignments produced from the same input are identical (DESIGN == IMPLEMENT)
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

import startd8.contractors.artisan_contractor as _artisan_mod
from startd8.contractors.artisan_contractor import compute_lanes
from startd8.contractors.context_seed_handlers import (
    build_shared_file_manifest,
    compute_lane_to_file_mapping,
    _normalize_target_path,
)

# Import shared FakeSeedTask from conftest
from tests.unit.contractors.conftest import FakeSeedTask


# ============================================================================
# Helpers
# ============================================================================


def _make_context(tasks: list[FakeSeedTask]) -> dict[str, Any]:
    """Build a minimal DesignPhaseHandler-compatible context from a task list."""
    return {
        "tasks": tasks,
        "task_index": {t.task_id: t for t in tasks},
        "enriched_seed_path": "/dev/null",
        "plan_title": "test plan",
        "plan_goals": [],
        "domain_summary": {},
        "preflight_summary": {},
        "total_estimated_loc": 0,
        "design_results": {},
        "generation_results": {},
        "test_results": {},
        "review_results": {},
        "scaffold": {},
    }


def _run_lane_ordering(tasks: list[FakeSeedTask]) -> tuple[
    Optional[list[list[FakeSeedTask]]],
    dict[str, int],
    list[tuple[int, FakeSeedTask, int]],
]:
    """Run the CCD-100/CCD-101/CCD-102 lane ordering logic in isolation.

    Mirrors the three-step sequence from DesignPhaseHandler.execute():
      1. compute_lanes() to get lane groups
      2. Wave-sort tasks within each lane
      3. Build _iteration_order as (global_idx, task, lane_idx) tuples

    Returns:
        (design_lanes, lane_assignments, iteration_order)
    """
    design_lanes: Optional[list[list[FakeSeedTask]]] = None
    lane_assignments: dict[str, int] = {}

    try:
        # Call via module reference so that patching
        # startd8.contractors.artisan_contractor.compute_lanes intercepts this.
        design_lanes = _artisan_mod.compute_lanes(tasks)
        for lane_idx, lane_tasks in enumerate(design_lanes):
            for lt in lane_tasks:
                lane_assignments[lt.task_id] = lane_idx
    except Exception:
        design_lanes = None

    # CCD-101: Wave-sort within each lane
    if design_lanes is not None:
        for li, lane in enumerate(design_lanes):
            design_lanes[li] = sorted(
                lane,
                key=lambda t: (
                    t.wave_index if t.wave_index is not None else float("inf"),
                    t.task_id,
                ),
            )

    # CCD-102: Build iteration order
    if design_lanes is not None:
        iteration_order: list[tuple[int, FakeSeedTask, int]] = []
        global_idx = 0
        for li, lane in enumerate(design_lanes):
            for task in lane:
                global_idx += 1
                iteration_order.append((global_idx, task, li))
    else:
        iteration_order = [(i, t, 0) for i, t in enumerate(tasks, start=1)]

    return design_lanes, lane_assignments, iteration_order


# ============================================================================
# TEST: compute_lanes() called before design loop
# ============================================================================


class TestComputeLanesCalledBeforeDesignLoop:
    """Verify compute_lanes() is invoked exactly once with the full task list."""

    def test_called_once_with_full_task_list(self):
        """compute_lanes is called once and receives all tasks."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"]),
            FakeSeedTask(task_id="T-3", target_files=["c.py"]),
        ]

        call_args_recorder: list[list] = []

        original_compute_lanes = compute_lanes

        def recording_compute_lanes(task_list):
            call_args_recorder.append(list(task_list))
            return original_compute_lanes(task_list)

        with patch(
            "startd8.contractors.artisan_contractor.compute_lanes",
            side_effect=recording_compute_lanes,
        ):
            _run_lane_ordering(tasks)

        assert len(call_args_recorder) == 1, (
            "compute_lanes should be called exactly once before the design loop"
        )
        assert [t.task_id for t in call_args_recorder[0]] == ["T-1", "T-2", "T-3"]

    def test_called_with_empty_list(self):
        """compute_lanes is called even when task list is empty."""
        call_count = [0]

        original_compute_lanes = compute_lanes

        def counting_compute_lanes(task_list):
            call_count[0] += 1
            return original_compute_lanes(task_list)

        with patch(
            "startd8.contractors.artisan_contractor.compute_lanes",
            side_effect=counting_compute_lanes,
        ):
            _run_lane_ordering([])

        assert call_count[0] == 1

    def test_not_called_multiple_times_for_n_tasks(self):
        """compute_lanes is NOT called once per task — only once total."""
        tasks = [FakeSeedTask(task_id=f"T-{i}", target_files=[f"f{i}.py"]) for i in range(5)]
        call_count = [0]

        original_compute_lanes = compute_lanes

        def counting_compute_lanes(task_list):
            call_count[0] += 1
            return original_compute_lanes(task_list)

        with patch(
            "startd8.contractors.artisan_contractor.compute_lanes",
            side_effect=counting_compute_lanes,
        ):
            _run_lane_ordering(tasks)

        assert call_count[0] == 1, (
            f"Expected 1 call to compute_lanes, got {call_count[0]}"
        )


# ============================================================================
# TEST: _lane_assignments populated
# ============================================================================


class TestLaneAssignmentsStoredInContext:
    """Verify the _lane_assignments dict is correctly built from compute_lanes output."""

    def test_all_tasks_assigned(self):
        """Every task in the input receives a lane assignment."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"]),
            FakeSeedTask(task_id="T-3", target_files=["a.py"]),  # same file as T-1
        ]
        _, lane_assignments, _ = _run_lane_ordering(tasks)

        assert set(lane_assignments.keys()) == {"T-1", "T-2", "T-3"}

    def test_shared_file_tasks_get_same_lane_index(self):
        """Tasks sharing a target_file are assigned the same lane index."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["shared.py"]),
            FakeSeedTask(task_id="T-2", target_files=["other.py"]),
            FakeSeedTask(task_id="T-3", target_files=["shared.py"]),
        ]
        _, lane_assignments, _ = _run_lane_ordering(tasks)

        assert lane_assignments["T-1"] == lane_assignments["T-3"], (
            "T-1 and T-3 share shared.py — must be in the same lane"
        )
        assert lane_assignments["T-2"] != lane_assignments["T-1"], (
            "T-2 targets a different file — must be in a different lane"
        )

    def test_independent_tasks_get_distinct_lane_indices(self):
        """Tasks with disjoint target_files each get a unique lane index."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"]),
            FakeSeedTask(task_id="T-3", target_files=["c.py"]),
        ]
        _, lane_assignments, _ = _run_lane_ordering(tasks)

        indices = list(lane_assignments.values())
        assert len(set(indices)) == 3, "Three independent tasks should get 3 distinct lane indices"

    def test_lane_indices_are_integers(self):
        """Lane assignments are non-negative integers."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"]),
        ]
        _, lane_assignments, _ = _run_lane_ordering(tasks)

        for task_id, lane_idx in lane_assignments.items():
            assert isinstance(lane_idx, int), f"{task_id} lane_index is not int: {lane_idx!r}"
            assert lane_idx >= 0, f"{task_id} lane_index is negative: {lane_idx}"

    def test_empty_task_list_produces_empty_assignments(self):
        """Empty task list yields empty lane_assignments."""
        _, lane_assignments, _ = _run_lane_ordering([])
        assert lane_assignments == {}


# ============================================================================
# TEST: Wave-sort within lane
# ============================================================================


class TestWaveSortWithinLane:
    """Verify tasks are sorted by wave_index ascending within each lane."""

    def test_wave_indices_sorted_ascending(self):
        """Tasks with wave_index [2, 0, 1] are reordered to [0, 1, 2]."""
        tasks = [
            FakeSeedTask(task_id="T-A", target_files=["shared.py"], wave_index=2),
            FakeSeedTask(task_id="T-B", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-C", target_files=["shared.py"], wave_index=1),
        ]
        # All share shared.py → one lane
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        assert len(design_lanes) == 1
        ordered_ids = [t.task_id for t in design_lanes[0]]
        assert ordered_ids == ["T-B", "T-C", "T-A"], (
            f"Expected wave-sorted order [T-B, T-C, T-A], got {ordered_ids}"
        )

    def test_already_sorted_wave_unchanged(self):
        """Tasks already in wave order [0, 1, 2] remain in the same order."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-2", target_files=["shared.py"], wave_index=1),
            FakeSeedTask(task_id="T-3", target_files=["shared.py"], wave_index=2),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        ordered_ids = [t.task_id for t in design_lanes[0]]
        assert ordered_ids == ["T-1", "T-2", "T-3"]

    def test_wave_sort_independent_per_lane(self):
        """Wave-sort is applied independently within each lane."""
        # Lane A: T-A1 (wave=1) and T-A0 (wave=0) share file_a.py
        # Lane B: T-B2 (wave=2) and T-B0 (wave=0) share file_b.py
        tasks = [
            FakeSeedTask(task_id="T-A1", target_files=["file_a.py"], wave_index=1),
            FakeSeedTask(task_id="T-A0", target_files=["file_a.py"], wave_index=0),
            FakeSeedTask(task_id="T-B2", target_files=["file_b.py"], wave_index=2),
            FakeSeedTask(task_id="T-B0", target_files=["file_b.py"], wave_index=0),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        assert len(design_lanes) == 2

        lane_a = next(
            lane for lane in design_lanes if any(t.task_id.startswith("T-A") for t in lane)
        )
        lane_b = next(
            lane for lane in design_lanes if any(t.task_id.startswith("T-B") for t in lane)
        )

        assert [t.task_id for t in lane_a] == ["T-A0", "T-A1"]
        assert [t.task_id for t in lane_b] == ["T-B0", "T-B2"]


# ============================================================================
# TEST: None wave_index sorts last
# ============================================================================


class TestWaveSortNoneWaveAtEnd:
    """Verify tasks with wave_index=None sort after all numbered waves."""

    def test_none_wave_sorts_after_numbered(self):
        """Tasks with None wave_index appear after tasks with integer wave_index."""
        tasks = [
            FakeSeedTask(task_id="T-none", target_files=["shared.py"], wave_index=None),
            FakeSeedTask(task_id="T-0", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-1", target_files=["shared.py"], wave_index=1),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        assert len(design_lanes) == 1
        ordered_ids = [t.task_id for t in design_lanes[0]]
        assert ordered_ids[-1] == "T-none", (
            f"Expected T-none last; got order {ordered_ids}"
        )
        assert ordered_ids[0] == "T-0"
        assert ordered_ids[1] == "T-1"

    def test_multiple_none_waves_at_end(self):
        """Multiple tasks with None wave_index all appear at the end."""
        tasks = [
            FakeSeedTask(task_id="T-none-2", target_files=["shared.py"], wave_index=None),
            FakeSeedTask(task_id="T-0", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-none-1", target_files=["shared.py"], wave_index=None),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        ordered = design_lanes[0]
        # First task must have wave_index=0
        assert ordered[0].wave_index == 0
        # All None-wave tasks must be at the end
        for t in ordered[1:]:
            assert t.wave_index is None

    def test_all_none_waves_preserves_task_id_sort(self):
        """When all tasks have None wave_index, secondary sort by task_id applies."""
        tasks = [
            FakeSeedTask(task_id="T-Z", target_files=["shared.py"], wave_index=None),
            FakeSeedTask(task_id="T-A", target_files=["shared.py"], wave_index=None),
            FakeSeedTask(task_id="T-M", target_files=["shared.py"], wave_index=None),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        ordered_ids = [t.task_id for t in design_lanes[0]]
        assert ordered_ids == ["T-A", "T-M", "T-Z"]


# ============================================================================
# TEST: Tiebreak by task_id
# ============================================================================


class TestWaveSortTiebreakByTaskId:
    """Verify that equal wave_index values are tiebroken by task_id (lexicographic)."""

    def test_same_wave_sorted_by_task_id(self):
        """Tasks with the same wave_index are sorted lexicographically by task_id."""
        tasks = [
            FakeSeedTask(task_id="T-C", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-A", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-B", target_files=["shared.py"], wave_index=0),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        ordered_ids = [t.task_id for t in design_lanes[0]]
        assert ordered_ids == ["T-A", "T-B", "T-C"]

    def test_tiebreak_within_mixed_waves(self):
        """Tiebreak applies only within the same wave, not across waves."""
        tasks = [
            FakeSeedTask(task_id="T-C0", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-A0", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-B1", target_files=["shared.py"], wave_index=1),
            FakeSeedTask(task_id="T-A1", target_files=["shared.py"], wave_index=1),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        ordered_ids = [t.task_id for t in design_lanes[0]]
        # Wave 0: A0, C0 (alphabetical); Wave 1: A1, B1 (alphabetical)
        assert ordered_ids == ["T-A0", "T-C0", "T-A1", "T-B1"]

    def test_single_task_per_wave_no_tiebreak_needed(self):
        """A single task per wave produces straightforward wave ordering."""
        tasks = [
            FakeSeedTask(task_id="T-X", target_files=["shared.py"], wave_index=1),
            FakeSeedTask(task_id="T-Y", target_files=["shared.py"], wave_index=0),
        ]
        design_lanes, _, _ = _run_lane_ordering(tasks)

        assert design_lanes is not None
        ordered_ids = [t.task_id for t in design_lanes[0]]
        assert ordered_ids == ["T-Y", "T-X"]


# ============================================================================
# TEST: Lane-sequential iteration order
# ============================================================================


class TestLaneSequentialIterationOrder:
    """Verify the _iteration_order processes all tasks lane-by-lane."""

    def test_five_tasks_two_lanes_iteration_order(self):
        """5 tasks in 2 lanes: all lane-0 tasks precede all lane-1 tasks."""
        # Lane 0: T-1, T-3, T-5 share file_x.py
        # Lane 1: T-2, T-4 share file_y.py
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["file_x.py"], wave_index=0),
            FakeSeedTask(task_id="T-2", target_files=["file_y.py"], wave_index=0),
            FakeSeedTask(task_id="T-3", target_files=["file_x.py"], wave_index=1),
            FakeSeedTask(task_id="T-4", target_files=["file_y.py"], wave_index=1),
            FakeSeedTask(task_id="T-5", target_files=["file_x.py"], wave_index=2),
        ]
        design_lanes, lane_assignments, iteration_order = _run_lane_ordering(tasks)

        assert design_lanes is not None
        assert len(design_lanes) == 2

        # All 5 tasks appear in iteration_order
        processed_ids = [task.task_id for _, task, _ in iteration_order]
        assert set(processed_ids) == {"T-1", "T-2", "T-3", "T-4", "T-5"}

        # Lane indices in iteration_order must be non-decreasing (lane-sequential)
        lane_indices = [li for _, _, li in iteration_order]
        assert lane_indices == sorted(lane_indices), (
            f"Lane indices in iteration_order not monotonically non-decreasing: {lane_indices}"
        )

    def test_global_indices_start_at_one_and_are_sequential(self):
        """Global indices in iteration_order start at 1 and increment by 1."""
        tasks = [
            FakeSeedTask(task_id="T-A", target_files=["a.py"], wave_index=0),
            FakeSeedTask(task_id="T-B", target_files=["b.py"], wave_index=0),
            FakeSeedTask(task_id="T-C", target_files=["a.py"], wave_index=1),
        ]
        _, _, iteration_order = _run_lane_ordering(tasks)

        global_indices = [idx for idx, _, _ in iteration_order]
        assert global_indices[0] == 1
        assert global_indices == list(range(1, len(tasks) + 1))

    def test_single_lane_all_tasks_in_order(self):
        """With one lane, iteration_order matches the wave-sorted lane order."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["shared.py"], wave_index=2),
            FakeSeedTask(task_id="T-2", target_files=["shared.py"], wave_index=0),
            FakeSeedTask(task_id="T-3", target_files=["shared.py"], wave_index=1),
        ]
        design_lanes, _, iteration_order = _run_lane_ordering(tasks)

        processed_ids = [task.task_id for _, task, _ in iteration_order]
        # After wave-sort: T-2(0), T-3(1), T-1(2)
        assert processed_ids == ["T-2", "T-3", "T-1"]

    def test_lane_boundary_resets_at_each_new_lane(self):
        """Each new lane in iteration_order is preceded by all tasks from the previous lane."""
        tasks = [
            FakeSeedTask(task_id="T-L0a", target_files=["lane0.py"], wave_index=0),
            FakeSeedTask(task_id="T-L0b", target_files=["lane0.py"], wave_index=1),
            FakeSeedTask(task_id="T-L1a", target_files=["lane1.py"], wave_index=0),
            FakeSeedTask(task_id="T-L1b", target_files=["lane1.py"], wave_index=1),
        ]
        design_lanes, _, iteration_order = _run_lane_ordering(tasks)

        assert design_lanes is not None
        assert len(design_lanes) == 2

        # Group iteration_order by lane
        lane0_tasks = [t.task_id for _, t, li in iteration_order if li == 0]
        lane1_tasks = [t.task_id for _, t, li in iteration_order if li == 1]

        # Verify all lane 0 tasks appear before any lane 1 tasks in the order
        lane0_positions = [i for i, (_, t, li) in enumerate(iteration_order) if li == 0]
        lane1_positions = [i for i, (_, t, li) in enumerate(iteration_order) if li == 1]

        assert max(lane0_positions) < min(lane1_positions), (
            "All lane 0 tasks must precede all lane 1 tasks in iteration_order"
        )


# ============================================================================
# TEST: Fallback on compute_lanes exception
# ============================================================================


class TestFallbackOnComputeLanesException:
    """Verify graceful fallback to flat iteration when compute_lanes raises."""

    def test_all_tasks_processed_on_exception(self):
        """When compute_lanes raises, all tasks still appear in iteration_order."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"]),
            FakeSeedTask(task_id="T-3", target_files=["c.py"]),
        ]

        with patch(
            "startd8.contractors.artisan_contractor.compute_lanes",
            side_effect=RuntimeError("compute_lanes injection failure"),
        ):
            design_lanes, lane_assignments, iteration_order = _run_lane_ordering(tasks)

        assert design_lanes is None, "design_lanes should be None on exception"
        assert lane_assignments == {}, "lane_assignments should be empty on exception"

        processed_ids = {task.task_id for _, task, _ in iteration_order}
        assert processed_ids == {"T-1", "T-2", "T-3"}, (
            "All tasks must still be processed even when compute_lanes fails"
        )

    def test_fallback_uses_original_task_order(self):
        """Flat fallback preserves the original input order of tasks."""
        tasks = [
            FakeSeedTask(task_id="T-X", target_files=["x.py"]),
            FakeSeedTask(task_id="T-Y", target_files=["y.py"]),
            FakeSeedTask(task_id="T-Z", target_files=["z.py"]),
        ]

        with patch(
            "startd8.contractors.artisan_contractor.compute_lanes",
            side_effect=ValueError("injected error"),
        ):
            _, _, iteration_order = _run_lane_ordering(tasks)

        processed_ids = [task.task_id for _, task, _ in iteration_order]
        assert processed_ids == ["T-X", "T-Y", "T-Z"]

    def test_fallback_assigns_all_tasks_to_lane_zero(self):
        """In flat fallback mode, all tasks get lane_index 0."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"]),
        ]

        with patch(
            "startd8.contractors.artisan_contractor.compute_lanes",
            side_effect=Exception("injected"),
        ):
            _, _, iteration_order = _run_lane_ordering(tasks)

        lane_indices = [li for _, _, li in iteration_order]
        assert all(li == 0 for li in lane_indices), (
            f"All tasks should be in lane 0 during fallback, got: {lane_indices}"
        )

    def test_fallback_global_indices_start_at_one(self):
        """Flat fallback still starts global index at 1."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"]),
        ]

        with patch(
            "startd8.contractors.artisan_contractor.compute_lanes",
            side_effect=RuntimeError("injected"),
        ):
            _, _, iteration_order = _run_lane_ordering(tasks)

        global_indices = [idx for idx, _, _ in iteration_order]
        # Flat fallback uses enumerate(tasks, start=1) → indices are [1, 2]
        assert global_indices[0] == 1
        assert global_indices == list(range(1, len(tasks) + 1))


# ============================================================================
# TEST: Design lanes match implement lanes
# ============================================================================


class TestDesignLanesMatchImplementLanes:
    """Verify compute_lanes() produces identical results for DESIGN and IMPLEMENT phases."""

    def test_same_task_list_produces_identical_lanes(self):
        """Calling compute_lanes() twice on the same input produces the same lane structure."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["shared.py"]),
            FakeSeedTask(task_id="T-2", target_files=["other.py"]),
            FakeSeedTask(task_id="T-3", target_files=["shared.py"]),
        ]

        design_lanes = compute_lanes(tasks)
        implement_lanes = compute_lanes(tasks)

        design_structure = [[t.task_id for t in lane] for lane in design_lanes]
        implement_structure = [[t.task_id for t in lane] for lane in implement_lanes]

        assert design_structure == implement_structure, (
            "Lane structure must be identical between DESIGN and IMPLEMENT phases"
        )

    def test_lane_assignments_identical_for_both_phases(self):
        """Lane assignment dicts are byte-for-byte equal for both phases."""
        tasks = [
            FakeSeedTask(task_id="T-A", target_files=["f1.py", "f2.py"]),
            FakeSeedTask(task_id="T-B", target_files=["f2.py"]),
            FakeSeedTask(task_id="T-C", target_files=["f3.py"]),
        ]

        # Simulate DESIGN phase lane assignment
        design_lanes = compute_lanes(tasks)
        design_assignments: dict[str, int] = {}
        for lane_idx, lane_tasks in enumerate(design_lanes):
            for lt in lane_tasks:
                design_assignments[lt.task_id] = lane_idx

        # Simulate IMPLEMENT phase lane assignment (same algorithm)
        implement_lanes = compute_lanes(tasks)
        implement_assignments: dict[str, int] = {}
        for lane_idx, lane_tasks in enumerate(implement_lanes):
            for lt in lane_tasks:
                implement_assignments[lt.task_id] = lane_idx

        assert design_assignments == implement_assignments

    def test_lane_count_matches_between_phases(self):
        """Number of lanes is identical for DESIGN and IMPLEMENT given same tasks."""
        tasks = [
            FakeSeedTask(task_id=f"T-{i}", target_files=[f"file_{i % 3}.py"])
            for i in range(6)
        ]

        design_lane_count = len(compute_lanes(tasks))
        implement_lane_count = len(compute_lanes(tasks))

        assert design_lane_count == implement_lane_count

    def test_depends_on_grouping_consistent_across_phases(self):
        """Tasks joined by depends_on end up in the same lane for both phases."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["b.py"], depends_on=["T-1"]),
            FakeSeedTask(task_id="T-3", target_files=["c.py"]),
        ]

        design_lanes = compute_lanes(tasks)
        implement_lanes = compute_lanes(tasks)

        # Find which lane T-1 and T-2 are in for both calls
        def _lane_of(lanes, task_id):
            for li, lane in enumerate(lanes):
                if any(t.task_id == task_id for t in lane):
                    return li
            return -1

        assert _lane_of(design_lanes, "T-1") == _lane_of(design_lanes, "T-2"), (
            "T-1 and T-2 must be in the same lane (depends_on)"
        )
        assert _lane_of(design_lanes, "T-1") == _lane_of(implement_lanes, "T-1"), (
            "Lane assignment for T-1 must match between DESIGN and IMPLEMENT"
        )
        assert _lane_of(design_lanes, "T-2") == _lane_of(implement_lanes, "T-2"), (
            "Lane assignment for T-2 must match between DESIGN and IMPLEMENT"
        )
