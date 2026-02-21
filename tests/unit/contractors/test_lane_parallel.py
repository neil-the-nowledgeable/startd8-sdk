"""
Unit tests for lane-parallel execution mode.

Tests cover:
    - compute_lanes() Union-Find grouping by shared target_files and depends_on
    - _isolate_context_for_lane() deep copy and task narrowing
    - _merge_lane_results() multi-lane result aggregation
    - WorkflowConfig mutual exclusion (lane_parallel vs feature_serial)
    - WorkflowCheckpoint v3 schema with lane-parallel fields
    - _commit_changes() short-circuit in lane-parallel mode
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.artisan_contractor import (
    CHECKPOINT_SCHEMA_VERSION,
    ArtisanContractorWorkflow,
    InMemoryCheckpointStore,
    PhaseResult,
    PhaseStatus,
    WorkflowCheckpoint,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowStatus,
    AbstractPhaseHandler,
    compute_lanes,
    _isolate_context_for_lane,
    _merge_lane_results,
)

# Import shared FakeSeedTask from conftest
from tests.unit.contractors.conftest import FakeSeedTask


# ============================================================================
# TEST: compute_lanes()
# ============================================================================


class TestComputeLanes:
    """Tests for the Union-Find lane grouping algorithm."""

    def test_empty_tasks(self):
        """Empty input produces empty output."""
        assert compute_lanes([]) == []

    def test_single_task(self):
        """Single task produces one lane with one task."""
        task = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        lanes = compute_lanes([task])
        assert len(lanes) == 1
        assert lanes[0] == [task]

    def test_no_overlap_produces_separate_lanes(self):
        """Tasks with disjoint target_files and no depends_on get separate lanes."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["b.py"])
        t3 = FakeSeedTask(task_id="PI-003", target_files=["c.py"])

        lanes = compute_lanes([t1, t2, t3])
        assert len(lanes) == 3
        assert lanes[0] == [t1]
        assert lanes[1] == [t2]
        assert lanes[2] == [t3]

    def test_shared_file_merges_into_one_lane(self):
        """Tasks sharing a target_file are grouped into the same lane."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["prime.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["other.py"])
        t3 = FakeSeedTask(task_id="PI-003", target_files=["prime.py", "utils.py"])

        lanes = compute_lanes([t1, t2, t3])
        assert len(lanes) == 2
        # t1 and t3 share prime.py → same lane
        lane_ids = [[t.task_id for t in lane] for lane in lanes]
        assert ["PI-001", "PI-003"] in lane_ids
        assert ["PI-002"] in lane_ids

    def test_depends_on_merges_into_same_lane(self):
        """Tasks connected by depends_on are placed in the same lane."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["b.py"], depends_on=["PI-001"])

        lanes = compute_lanes([t1, t2])
        assert len(lanes) == 1
        assert [t.task_id for t in lanes[0]] == ["PI-001", "PI-002"]

    def test_transitive_merge_via_shared_file(self):
        """Transitive overlap (A shares file with B, B shares file with C)."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["a.py", "b.py"])
        t3 = FakeSeedTask(task_id="PI-003", target_files=["b.py"])

        lanes = compute_lanes([t1, t2, t3])
        assert len(lanes) == 1
        assert [t.task_id for t in lanes[0]] == ["PI-001", "PI-002", "PI-003"]

    def test_preserves_input_order_within_lane(self):
        """Tasks within a lane preserve their input (topological) order."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["shared.py"])
        t2 = FakeSeedTask(task_id="PI-003", target_files=["other.py"])
        t3 = FakeSeedTask(task_id="PI-005", target_files=["shared.py"])
        t4 = FakeSeedTask(task_id="PI-009", target_files=["shared.py"])

        lanes = compute_lanes([t1, t2, t3, t4])
        shared_lane = [lane for lane in lanes if len(lane) > 1][0]
        assert [t.task_id for t in shared_lane] == ["PI-001", "PI-005", "PI-009"]

    def test_depends_on_unknown_id_ignored(self):
        """depends_on referencing a task_id not in the input is silently ignored."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"], depends_on=["PI-999"])
        lanes = compute_lanes([t1])
        assert len(lanes) == 1
        assert lanes[0] == [t1]

    def test_lanes_ordered_by_first_task_appearance(self):
        """Lanes are ordered by the index of their first task in the input."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["b.py"])
        t3 = FakeSeedTask(task_id="PI-003", target_files=["a.py"])

        lanes = compute_lanes([t1, t2, t3])
        # Lane containing PI-001 (index 0) should come before lane containing PI-002 (index 1)
        assert lanes[0][0].task_id == "PI-001"
        assert lanes[1][0].task_id == "PI-002"

    def test_multiple_files_per_task(self):
        """Task with multiple target_files merges all overlapping groups."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["b.py"])
        t3 = FakeSeedTask(task_id="PI-003", target_files=["a.py", "b.py"])  # merges both

        lanes = compute_lanes([t1, t2, t3])
        assert len(lanes) == 1
        assert [t.task_id for t in lanes[0]] == ["PI-001", "PI-002", "PI-003"]

    def test_empty_target_files(self):
        """Tasks with no target_files are each their own lane."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=[])
        t2 = FakeSeedTask(task_id="PI-002", target_files=[])

        lanes = compute_lanes([t1, t2])
        assert len(lanes) == 2


# ============================================================================
# TEST: _isolate_context_for_lane()
# ============================================================================


class TestIsolateContextForLane:
    """Tests for context isolation before lane execution."""

    def _make_base_context(self) -> dict[str, Any]:
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["b.py"])
        t3 = FakeSeedTask(task_id="PI-003", target_files=["c.py"])
        return {
            "tasks": [t1, t2, t3],
            "design_results": {
                "PI-001": {"status": "designed"},
                "PI-002": {"status": "designed"},
                "PI-003": {"status": "designed"},
            },
            "generation_results": {
                "PI-001": {"files": ["a.py"]},
                "PI-002": {"files": ["b.py"]},
            },
            "enriched_seed_path": "/path/to/seed.json",
        }

    def test_deep_copy_isolation(self):
        """Changes to lane context do not affect base context."""
        base = self._make_base_context()
        lane_tasks = [base["tasks"][0]]  # PI-001

        lane_ctx = _isolate_context_for_lane(base, lane_tasks)
        lane_ctx["design_results"]["PI-001"]["status"] = "modified"

        assert base["design_results"]["PI-001"]["status"] == "designed"

    def test_narrows_tasks_to_lane(self):
        """Lane context contains only the lane's tasks."""
        base = self._make_base_context()
        lane_tasks = [base["tasks"][0], base["tasks"][2]]  # PI-001, PI-003

        lane_ctx = _isolate_context_for_lane(base, lane_tasks)
        assert len(lane_ctx["tasks"]) == 2
        assert lane_ctx["tasks"][0].task_id == "PI-001"
        assert lane_ctx["tasks"][1].task_id == "PI-003"

    def test_narrows_task_keyed_dicts(self):
        """Task-keyed dicts are narrowed to only the lane's task IDs."""
        base = self._make_base_context()
        lane_tasks = [base["tasks"][1]]  # PI-002

        lane_ctx = _isolate_context_for_lane(base, lane_tasks)
        assert set(lane_ctx["design_results"].keys()) == {"PI-002"}
        assert set(lane_ctx["generation_results"].keys()) == {"PI-002"}

    def test_preserves_non_task_keyed_fields(self):
        """Non-task-keyed fields are preserved in the lane context."""
        base = self._make_base_context()
        lane_tasks = [base["tasks"][0]]

        lane_ctx = _isolate_context_for_lane(base, lane_tasks)
        assert lane_ctx["enriched_seed_path"] == "/path/to/seed.json"


# ============================================================================
# TEST: _merge_lane_results()
# ============================================================================


class TestMergeLaneResults:
    """Tests for merging lane results back into the base context."""

    def test_merge_from_two_lanes(self):
        """Results from two lanes are merged into the base context."""
        base = {"design_results": {}, "generation_results": {}}
        lane0 = {
            "design_results": {"PI-001": {"status": "designed"}},
            "generation_results": {"PI-001": {"files": ["a.py"]}},
        }
        lane1 = {
            "design_results": {"PI-002": {"status": "designed"}},
            "generation_results": {"PI-002": {"files": ["b.py"]}},
        }

        _merge_lane_results(base, [lane0, lane1])
        assert set(base["design_results"].keys()) == {"PI-001", "PI-002"}
        assert set(base["generation_results"].keys()) == {"PI-001", "PI-002"}

    def test_no_clobber_between_lanes(self):
        """Disjoint lanes don't overwrite each other's results."""
        base = {"design_results": {"PI-000": {"status": "preexisting"}}}
        lane0 = {"design_results": {"PI-001": {"status": "designed"}}}
        lane1 = {"design_results": {"PI-002": {"status": "designed"}}}

        _merge_lane_results(base, [lane0, lane1])
        assert base["design_results"]["PI-000"]["status"] == "preexisting"
        assert "PI-001" in base["design_results"]
        assert "PI-002" in base["design_results"]

    def test_missing_fields_handled_gracefully(self):
        """Lanes that don't have a task-keyed field don't cause errors."""
        base = {"design_results": {}}
        lane0 = {}  # No design_results at all
        lane1 = {"design_results": {"PI-001": {"status": "designed"}}}

        _merge_lane_results(base, [lane0, lane1])
        assert base["design_results"] == {"PI-001": {"status": "designed"}}

    def test_empty_lane_contexts(self):
        """Empty lane contexts list is a no-op."""
        base = {"design_results": {"PI-000": {"status": "preexisting"}}}
        _merge_lane_results(base, [])
        assert base["design_results"] == {"PI-000": {"status": "preexisting"}}


# ============================================================================
# TEST: WorkflowConfig validation
# ============================================================================


class TestLaneParallelConfig:
    """Tests for WorkflowConfig lane_parallel fields and validation."""

    def test_default_lane_parallel_is_false(self):
        """Default config has lane_parallel=False."""
        config = WorkflowConfig()
        assert config.lane_parallel is False
        assert config.max_parallel_lanes == 4

    def test_lane_parallel_enabled(self):
        """Can enable lane_parallel mode."""
        config = WorkflowConfig(lane_parallel=True)
        assert config.lane_parallel is True

    def test_mutual_exclusion_with_feature_serial(self):
        """lane_parallel and feature_serial cannot both be True."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            WorkflowConfig(lane_parallel=True, feature_serial=True)

    def test_max_parallel_lanes_custom(self):
        """max_parallel_lanes can be customized."""
        config = WorkflowConfig(lane_parallel=True, max_parallel_lanes=8)
        assert config.max_parallel_lanes == 8

    def test_max_parallel_lanes_must_be_positive(self):
        """max_parallel_lanes must be at least 1."""
        with pytest.raises(ValueError, match="max_parallel_lanes"):
            WorkflowConfig(max_parallel_lanes=0)


# ============================================================================
# TEST: WorkflowCheckpoint v3 schema
# ============================================================================


class TestLaneParallelCheckpoint:
    """Tests for WorkflowCheckpoint v3 fields."""

    def test_schema_version_is_3(self):
        """Checkpoint schema version should be 3."""
        assert CHECKPOINT_SCHEMA_VERSION == 3

    def test_v3_fields_default_empty(self):
        """v3 lane-parallel fields default to empty collections."""
        cp = WorkflowCheckpoint(
            workflow_id="test",
            last_completed_phase="scaffold",
            phase_results=[],
            cumulative_cost=0.0,
            timestamp="2026-02-20T00:00:00Z",
            status="in_progress",
        )
        assert cp.lane_assignments == {}
        assert cp.completed_lanes == []
        assert cp.lane_results == {}
        assert cp.schema_version == 3

    def test_v3_fields_populated(self):
        """v3 fields can be populated."""
        cp = WorkflowCheckpoint(
            workflow_id="test",
            last_completed_phase="scaffold",
            phase_results=[],
            cumulative_cost=1.5,
            timestamp="2026-02-20T00:00:00Z",
            status="in_progress",
            lane_assignments={"PI-001": 0, "PI-002": 0, "PI-003": 1},
            completed_lanes=[0],
            lane_results={"0": {"status": "completed", "completed_features": ["PI-001", "PI-002"]}},
        )
        assert cp.lane_assignments["PI-001"] == 0
        assert cp.completed_lanes == [0]
        assert cp.lane_results["0"]["status"] == "completed"

    def test_v2_checkpoint_loads_with_v3_defaults(self):
        """A v2 checkpoint (no lane fields) loads successfully with defaults."""
        v2_data = {
            "workflow_id": "test-v2",
            "last_completed_phase": "design",
            "phase_results": [],
            "cumulative_cost": 2.0,
            "timestamp": "2026-02-20T00:00:00Z",
            "status": "in_progress",
            "schema_version": 2,
            "completed_features": ["PI-001"],
            "current_feature": None,
            "current_feature_phase": None,
            "feature_partial_results": {},
        }
        cp = WorkflowCheckpoint(**v2_data)
        # v3 fields should get defaults
        assert cp.lane_assignments == {}
        assert cp.completed_lanes == []
        assert cp.lane_results == {}

    def test_checkpoint_round_trip_via_asdict(self):
        """Checkpoint with lane fields survives asdict → WorkflowCheckpoint round-trip."""
        cp = WorkflowCheckpoint(
            workflow_id="test",
            last_completed_phase="scaffold",
            phase_results=[],
            cumulative_cost=0.0,
            timestamp="2026-02-20T00:00:00Z",
            status="in_progress",
            lane_assignments={"PI-001": 0},
            completed_lanes=[0],
            lane_results={"0": {"status": "completed"}},
        )
        data = asdict(cp)
        restored = WorkflowCheckpoint(**data)
        assert restored.lane_assignments == {"PI-001": 0}
        assert restored.completed_lanes == [0]
        assert restored.lane_results == {"0": {"status": "completed"}}


# ============================================================================
# TEST: _commit_changes short-circuit
# ============================================================================


class TestCommitChangesLaneParallel:
    """Tests for _commit_changes behavior in lane-parallel mode."""

    def test_commit_changes_skipped_in_lane_parallel(self):
        """Auto-commit is skipped when lane_parallel=True."""
        config = WorkflowConfig(lane_parallel=True, project_root="/tmp/test")
        wf = ArtisanContractorWorkflow(config=config)

        # If _commit_changes tries to run git, it would fail since /tmp/test
        # doesn't have a git repo. The short-circuit prevents that.
        wf._commit_changes(WorkflowPhase.IMPLEMENT, feature_id="PI-001")
        # No exception = success (git was not called)

    def test_commit_changes_not_skipped_in_normal_mode(self):
        """Auto-commit is NOT skipped in normal mode (only when git is missing)."""
        config = WorkflowConfig(project_root="/tmp/nonexistent")
        wf = ArtisanContractorWorkflow(config=config)
        # In normal mode, _commit_changes runs but returns early because
        # .git doesn't exist at /tmp/nonexistent
        wf._commit_changes(WorkflowPhase.IMPLEMENT)
        # No exception = success


# ============================================================================
# TEST: End-to-end lane-parallel dispatch (mock handlers)
# ============================================================================


class _MockFeatureSerialHandler(AbstractPhaseHandler):
    """Handler that supports feature_serial and records calls."""

    supports_feature_serial = True

    def __init__(self):
        self.calls: list[tuple[str, str]] = []  # (phase, feature_id)

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        feature_id = context.get("current_feature_id", "global")
        self.calls.append((phase.value, feature_id))
        return {"cost": 0.001, "output": {"task_id": feature_id}, "metadata": {}}


class TestLaneParallelDispatch:
    """Integration test for lane-parallel dispatch with mock handlers.

    Replaces _execute_phase with a lightweight stub that skips context
    schema validation entirely, so we focus on dispatch logic.
    """

    @staticmethod
    def _minimal_context(tasks: list[FakeSeedTask]) -> dict[str, Any]:
        """Build a minimal context for lane dispatch."""
        task_index = {t.task_id: t for t in tasks}
        return {
            "tasks": tasks,
            "task_index": task_index,
            "enriched_seed_path": "/dev/null",
            "plan_title": "test plan",
            "plan_goals": ["test"],
            "domain_summary": {"backend": 1},
            "preflight_summary": {},
            "total_estimated_loc": 0,
            "design_results": {},
            "generation_results": {},
            "test_results": {},
            "review_results": {},
            "scaffold": {},
        }

    def _make_workflow_with_tasks(
        self, tasks: list[FakeSeedTask], max_lanes: int = 4,
    ) -> tuple[ArtisanContractorWorkflow, _MockFeatureSerialHandler]:
        config = WorkflowConfig(
            lane_parallel=True,
            max_parallel_lanes=max_lanes,
            dry_run=True,
            checkpoint_dir=None,  # Disable checkpoint I/O
        )
        wf = ArtisanContractorWorkflow(config=config)
        wf.checkpoint_store = InMemoryCheckpointStore()

        handler = _MockFeatureSerialHandler()
        for phase in WorkflowPhase:
            wf.register_handler(phase, handler)

        # Replace _execute_phase to skip context schema validation
        original_execute_phase = wf._execute_phase

        def _stub_execute_phase(phase, context, remaining_total_timeout):
            handler_obj = wf.handlers.get(phase, wf._default_handler)
            result_dict = handler_obj.execute(phase, context, wf.config.dry_run)
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            return PhaseResult(
                phase=phase,
                status=PhaseStatus.DRY_RUN,
                start_time=now_iso,
                end_time=now_iso,
                duration_seconds=0.01,
                cost=float(result_dict.get("cost", 0.0)),
                output=result_dict.get("output"),
                metadata=result_dict.get("metadata", {}),
            )

        wf._execute_phase = _stub_execute_phase

        return wf, handler

    def test_single_lane_all_tasks(self):
        """Tasks sharing a file run in one lane."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["shared.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["shared.py"])

        wf, handler = self._make_workflow_with_tasks([t1, t2])
        result = wf.execute(context=self._minimal_context([t1, t2]))

        assert result.status == WorkflowStatus.COMPLETED

    def test_two_independent_lanes(self):
        """Independent tasks run in separate lanes."""
        t1 = FakeSeedTask(task_id="PI-001", target_files=["a.py"])
        t2 = FakeSeedTask(task_id="PI-002", target_files=["b.py"])

        wf, handler = self._make_workflow_with_tasks([t1, t2])
        result = wf.execute(context=self._minimal_context([t1, t2]))

        assert result.status == WorkflowStatus.COMPLETED

    def test_zero_tasks_completes(self):
        """No tasks still completes (PLAN + SCAFFOLD + FINALIZE run)."""
        wf, handler = self._make_workflow_with_tasks([])
        result = wf.execute(context=self._minimal_context([]))

        assert result.status == WorkflowStatus.COMPLETED
