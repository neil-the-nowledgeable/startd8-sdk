"""
Unit tests for feature-serial execution and checkpoint schema v2.

Tests cover:
    - WorkflowCheckpoint v2 schema with feature-serial fields
    - Backward compatibility loading of v1 checkpoints
    - FeaturePartialResult fitness summary
    - _execute_feature() inner loop logic
    - _execute_feature_serial_mode() orchestration
"""

import json
from types import SimpleNamespace
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.artisan_contractor import (
    CHECKPOINT_SCHEMA_VERSION,
    ArtisanContractorWorkflow,
    FeaturePartialResult,
    InnerPhaseResult,
    JsonFileCheckpointStore,
    InMemoryCheckpointStore,
    PhaseResult,
    PhaseStatus,
    WorkflowCheckpoint,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowStatus,
    AbstractPhaseHandler,
    CostBudgetExceededError,
)
from startd8.contractors.context_seed_handlers import _ensure_context_loaded


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def tmp_checkpoint_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for checkpoint files."""
    return tmp_path / "checkpoints"


@pytest.fixture
def v1_checkpoint_data() -> dict:
    """Return a v1 checkpoint (without feature-serial fields)."""
    return {
        "workflow_id": "test-workflow-v1",
        "last_completed_phase": "design",
        "phase_results": [
            {
                "phase": "plan",
                "status": "completed",
                "start_time": "2026-01-01T00:00:00+00:00",
                "end_time": "2026-01-01T00:01:00+00:00",
                "duration_seconds": 60.0,
                "cost": 0.01,
                "output": {"tasks": 5},
                "error_message": None,
                "retry_count": 0,
                "metadata": {},
            }
        ],
        "cumulative_cost": 0.01,
        "timestamp": "2026-01-01T00:01:00+00:00",
        "status": "in_progress",
        "metadata": {},
        "context_snapshot": {"plan_title": "Test Plan"},
    }


@pytest.fixture
def v2_checkpoint_data() -> dict:
    """Return a v2 checkpoint (with feature-serial fields)."""
    return {
        "workflow_id": "test-workflow-v2",
        "last_completed_phase": "scaffold",
        "phase_results": [],
        "cumulative_cost": 0.05,
        "timestamp": "2026-01-01T00:02:00+00:00",
        "status": "in_progress",
        "metadata": {},
        "context_snapshot": {},
        "schema_version": 2,
        "completed_features": ["feature-1", "feature-2"],
        "current_feature": "feature-3",
        "current_feature_phase": "implement",
        "feature_partial_results": {
            "feature-3": {
                "feature_id": "feature-3",
                "started_at": "2026-01-01T00:01:30+00:00",
                "failed_at": None,
                "failure_reason": None,
                "inner_phases": {
                    "design": {"status": "completed", "cost": 0.01},
                },
            }
        },
    }


class MockPhaseHandler(AbstractPhaseHandler):
    """Mock phase handler for testing."""

    def __init__(self, output: Any = None, cost: float = 0.0, should_fail: bool = False):
        self.output = output
        self.cost = cost
        self.should_fail = should_fail
        self.call_count = 0
        self.last_context = None

    def execute(
        self, phase: WorkflowPhase, context: dict[str, Any], dry_run: bool = False
    ) -> dict[str, Any]:
        self.call_count += 1
        self.last_context = dict(context)

        if self.should_fail:
            raise RuntimeError("Intentional test failure")

        return {
            "output": self.output,
            "cost": self.cost,
            "metadata": {"dry_run": dry_run},
        }


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestWorkflowCheckpointV2Schema:
    """Tests for WorkflowCheckpoint v2 schema."""

    def test_checkpoint_has_schema_version(self):
        """Verify checkpoints include schema_version field."""
        checkpoint = WorkflowCheckpoint(
            workflow_id="test",
            last_completed_phase=None,
            phase_results=[],
            cumulative_cost=0.0,
            timestamp="2026-01-01T00:00:00+00:00",
            status="in_progress",
        )
        assert checkpoint.schema_version == CHECKPOINT_SCHEMA_VERSION
        assert checkpoint.schema_version == 4

    def test_checkpoint_has_feature_serial_fields(self):
        """Verify checkpoints have feature-serial execution fields."""
        checkpoint = WorkflowCheckpoint(
            workflow_id="test",
            last_completed_phase=None,
            phase_results=[],
            cumulative_cost=0.0,
            timestamp="2026-01-01T00:00:00+00:00",
            status="in_progress",
            completed_features=["f1", "f2"],
            current_feature="f3",
            current_feature_phase="implement",
            feature_partial_results={"f3": {"inner_phases": {}}},
        )

        assert checkpoint.completed_features == ["f1", "f2"]
        assert checkpoint.current_feature == "f3"
        assert checkpoint.current_feature_phase == "implement"
        assert "f3" in checkpoint.feature_partial_results

    def test_checkpoint_defaults_for_feature_serial_fields(self):
        """Verify feature-serial fields have sensible defaults."""
        checkpoint = WorkflowCheckpoint(
            workflow_id="test",
            last_completed_phase=None,
            phase_results=[],
            cumulative_cost=0.0,
            timestamp="2026-01-01T00:00:00+00:00",
            status="in_progress",
        )

        assert checkpoint.completed_features == []
        assert checkpoint.current_feature is None
        assert checkpoint.current_feature_phase is None
        assert checkpoint.feature_partial_results == {}


class TestJsonFileCheckpointStoreBackwardCompat:
    """Tests for backward-compatible checkpoint loading."""

    def test_load_v1_checkpoint_adds_missing_fields(
        self, tmp_checkpoint_dir: Path, v1_checkpoint_data: dict
    ):
        """Loading a v1 checkpoint should add missing v2 fields."""
        tmp_checkpoint_dir.mkdir(parents=True, exist_ok=True)
        store = JsonFileCheckpointStore(str(tmp_checkpoint_dir))

        # Write v1 checkpoint directly (bypassing store.save)
        path = tmp_checkpoint_dir / "test-workflow-v1.checkpoint.json"
        path.write_text(json.dumps(v1_checkpoint_data))

        # Load and verify migration
        checkpoint = store.load("test-workflow-v1")

        assert checkpoint is not None
        assert checkpoint.schema_version == 4  # Migrated v1 → v4
        assert checkpoint.completed_features == []
        assert checkpoint.current_feature is None
        assert checkpoint.current_feature_phase is None
        assert checkpoint.feature_partial_results == {}
        # v4 wave fields added by migration
        assert checkpoint.wave_assignments == {}
        assert checkpoint.completed_waves == []
        assert checkpoint.current_wave is None
        assert checkpoint.wave_resume_count == {}

    def test_load_v2_checkpoint_preserves_fields(
        self, tmp_checkpoint_dir: Path, v2_checkpoint_data: dict
    ):
        """Loading a v2 checkpoint should preserve all fields."""
        tmp_checkpoint_dir.mkdir(parents=True, exist_ok=True)
        store = JsonFileCheckpointStore(str(tmp_checkpoint_dir))

        # Write v2 checkpoint directly
        path = tmp_checkpoint_dir / "test-workflow-v2.checkpoint.json"
        path.write_text(json.dumps(v2_checkpoint_data))

        # Load and verify
        checkpoint = store.load("test-workflow-v2")

        assert checkpoint is not None
        assert checkpoint.schema_version == 4  # Migrated v2 → v4
        assert checkpoint.completed_features == ["feature-1", "feature-2"]
        assert checkpoint.current_feature == "feature-3"
        assert checkpoint.current_feature_phase == "implement"
        assert "feature-3" in checkpoint.feature_partial_results

    def test_save_checkpoint_includes_all_v2_fields(self, tmp_checkpoint_dir: Path):
        """Saving a checkpoint should include all v2 fields."""
        tmp_checkpoint_dir.mkdir(parents=True, exist_ok=True)
        store = JsonFileCheckpointStore(str(tmp_checkpoint_dir))

        checkpoint = WorkflowCheckpoint(
            workflow_id="save-test",
            last_completed_phase="scaffold",
            phase_results=[],
            cumulative_cost=0.1,
            timestamp="2026-01-01T00:00:00+00:00",
            status="in_progress",
            completed_features=["f1"],
            current_feature="f2",
            current_feature_phase="design",
            feature_partial_results={},
        )

        store.save(checkpoint)

        # Read raw JSON to verify fields
        path = tmp_checkpoint_dir / "save-test.checkpoint.json"
        raw_data = json.loads(path.read_text())

        assert raw_data["schema_version"] == 4
        assert raw_data["completed_features"] == ["f1"]
        assert raw_data["current_feature"] == "f2"
        assert raw_data["current_feature_phase"] == "design"
        # v4 wave fields present with defaults
        assert raw_data["wave_assignments"] == {}
        assert raw_data["completed_waves"] == []
        assert raw_data["current_wave"] is None
        assert raw_data["wave_resume_count"] == {}


class TestFeaturePartialResult:
    """Tests for FeaturePartialResult helper class."""

    def test_fitness_summary_completed_phases(self):
        """fitness_summary should list completed inner phases."""
        partial = FeaturePartialResult(
            feature_id="test-feature",
            started_at="2026-01-01T00:00:00+00:00",
            inner_phases={
                "design": {"status": "completed", "cost": 0.01},
                "implement": {"status": "completed", "cost": 0.05},
                "test": {"status": "failed", "cost": 0.02},
            },
        )

        summary = partial.fitness_summary()

        assert summary["feature_id"] == "test-feature"
        assert "design" in summary["completed_phases"]
        assert "implement" in summary["completed_phases"]
        assert "test" not in summary["completed_phases"]
        assert summary["failed_phase"] == "test"
        assert summary["has_design"] is True
        assert summary["total_cost"] == pytest.approx(0.08)

    def test_fitness_summary_no_design(self):
        """fitness_summary should report has_design=False when design failed."""
        partial = FeaturePartialResult(
            feature_id="test-feature",
            started_at="2026-01-01T00:00:00+00:00",
            failure_reason="Design phase failed",
            inner_phases={
                "design": {"status": "failed", "cost": 0.01},
            },
        )

        summary = partial.fitness_summary()

        assert summary["has_design"] is False
        assert summary["failed_phase"] == "design"
        assert summary["failure_reason"] == "Design phase failed"


class TestInnerPhaseResult:
    """Tests for InnerPhaseResult data class."""

    def test_inner_phase_result_creation(self):
        """InnerPhaseResult should store phase execution details."""
        result = InnerPhaseResult(
            status="completed",
            cost=0.05,
            timestamp="2026-01-01T00:00:00+00:00",
            artifacts={"files_written": ["src/foo.py"]},
        )

        assert result.status == "completed"
        assert result.cost == 0.05
        assert result.error is None
        assert "files_written" in result.artifacts


class TestWorkflowConfigFeatureSerial:
    """Tests for feature_serial config option."""

    def test_default_is_phase_serial(self):
        """By default, workflows should use phase-serial execution."""
        config = WorkflowConfig()
        assert config.feature_serial is False

    def test_feature_serial_can_be_enabled(self):
        """feature_serial can be explicitly enabled."""
        config = WorkflowConfig(feature_serial=True)
        assert config.feature_serial is True


class TestExecuteFeatureSerialMode:
    """Tests for feature-serial execution mode orchestration."""

    def test_feature_serial_flag_routes_to_correct_mode(self):
        """Setting feature_serial=True should use feature-serial execution path."""
        config = WorkflowConfig(
            workflow_id="test-feature-serial",
            feature_serial=True,
            dry_run=True,
        )
        workflow = ArtisanContractorWorkflow(config=config)

        # Mock the mode methods to verify routing
        with patch.object(
            workflow, "_execute_feature_serial_mode", return_value=WorkflowStatus.COMPLETED
        ) as mock_feature_serial, patch.object(
            workflow, "_execute_phase_serial_mode"
        ) as mock_phase_serial:

            result = workflow.execute(context={})

            mock_feature_serial.assert_called_once()
            mock_phase_serial.assert_not_called()
            assert result.status == WorkflowStatus.COMPLETED

    def test_phase_serial_flag_routes_to_correct_mode(self):
        """Default (feature_serial=False) should use phase-serial execution path."""
        config = WorkflowConfig(
            workflow_id="test-phase-serial",
            feature_serial=False,
            dry_run=True,
        )
        workflow = ArtisanContractorWorkflow(config=config)

        # Mock the mode methods to verify routing
        with patch.object(
            workflow, "_execute_phase_serial_mode", return_value=WorkflowStatus.COMPLETED
        ) as mock_phase_serial, patch.object(
            workflow, "_execute_feature_serial_mode"
        ) as mock_feature_serial:

            result = workflow.execute(context={})

            mock_phase_serial.assert_called_once()
            mock_feature_serial.assert_not_called()
            assert result.status == WorkflowStatus.COMPLETED

    def test_feature_serial_requires_compatible_inner_handlers(self):
        """Feature-serial should fail fast with non-opted-in handlers."""
        config = WorkflowConfig(
            workflow_id="test-feature-serial-guard",
            feature_serial=True,
            dry_run=True,
        )
        workflow = ArtisanContractorWorkflow(config=config)
        with pytest.raises(ValueError, match="supports_feature_serial=True"):
            workflow.execute(context={"tasks": []})

    def test_resume_logs_feature_serial_coordinates(self, caplog):
        """Resume diagnostics should include current feature and inner phase."""
        config = WorkflowConfig(
            workflow_id="test-feature-serial-resume-log",
            feature_serial=True,
            dry_run=True,
        )
        store = InMemoryCheckpointStore()
        workflow = ArtisanContractorWorkflow(config=config, checkpoint_store=store)

        store.save(
            WorkflowCheckpoint(
                workflow_id=config.workflow_id,
                last_completed_phase="scaffold",
                phase_results=[],
                cumulative_cost=0.0,
                timestamp="2026-01-01T00:00:00+00:00",
                status="in_progress",
                completed_features=["F-001", "F-002"],
                current_feature="F-003",
                current_feature_phase="implement",
            )
        )

        with patch.object(
            workflow, "_execute_feature_serial_mode", return_value=WorkflowStatus.COMPLETED
        ):
            with caplog.at_level("INFO"):
                workflow.execute(context={}, resume_from_checkpoint=True)

        assert "feature=F-003" in caplog.text
        assert "inner_phase=implement" in caplog.text
        assert "completed_features=2" in caplog.text

    def test_feature_serial_budget_exceeded_maps_to_budget_error(self):
        """Budget exceeded in feature loop should raise CostBudgetExceededError."""
        config = WorkflowConfig(
            workflow_id="test-feature-serial-budget",
            feature_serial=True,
            dry_run=True,
            cost_budget=0.01,
        )
        workflow = ArtisanContractorWorkflow(config=config)
        cost_tracker = SimpleNamespace(cumulative_cost=0.02)
        cost_tracker.add = lambda cost: None

        # Avoid real phase execution; directly simulate budget-exceeded status.
        with patch.object(
            workflow,
            "_validate_feature_serial_handlers",
            return_value=None,
        ), patch.object(
            workflow,
            "_execute_phase",
            return_value=PhaseResult(
                phase=WorkflowPhase.PLAN,
                status=PhaseStatus.DRY_RUN,
                start_time="2026-01-01T00:00:00+00:00",
                end_time="2026-01-01T00:00:00+00:00",
                duration_seconds=0.0,
                cost=0.0,
                output={},
                retry_count=0,
                metadata={},
            ),
        ), patch.object(
            workflow,
            "_execute_feature_serial_loop",
            return_value=(WorkflowStatus.BUDGET_EXCEEDED, [], {}, "F-123", "implement"),
        ):
            with pytest.raises(CostBudgetExceededError):
                workflow._execute_feature_serial_mode(
                    context={"tasks": []},
                    phase_results=[],
                    cost_tracker=cost_tracker,
                    workflow_start=0.0,
                    start_index=0,
                    loaded_checkpoint=None,
                )


class TestPersistCheckpointFeatureSerial:
    """Tests for _persist_checkpoint with feature-serial fields."""

    def test_persist_checkpoint_includes_feature_serial_fields(self):
        """_persist_checkpoint should include feature-serial fields when provided."""
        config = WorkflowConfig(workflow_id="test-persist")
        store = InMemoryCheckpointStore()
        workflow = ArtisanContractorWorkflow(config=config, checkpoint_store=store)

        checkpoint = workflow._persist_checkpoint(
            last_completed_phase=WorkflowPhase.SCAFFOLD,
            phase_results=[],
            cumulative_cost=0.05,
            status=WorkflowStatus.IN_PROGRESS,
            completed_features=["f1", "f2"],
            current_feature="f3",
            current_feature_phase="implement",
            feature_partial_results={"f3": {"inner_phases": {}}},
        )

        assert checkpoint.completed_features == ["f1", "f2"]
        assert checkpoint.current_feature == "f3"
        assert checkpoint.current_feature_phase == "implement"
        assert "f3" in checkpoint.feature_partial_results

        # Verify it was saved
        loaded = store.load("test-persist")
        assert loaded is not None
        assert loaded.completed_features == ["f1", "f2"]


class TestExtractFailureReason:
    """Tests for _extract_failure_reason helper."""

    def test_extract_failure_from_inner_results(self):
        """Should extract failure reason from inner phase results."""
        inner_results = {
            "design": {"status": "completed", "cost": 0.01},
            "implement": {"status": "failed", "error": "Syntax error in generated code"},
        }

        reason = ArtisanContractorWorkflow._extract_failure_reason(inner_results)

        assert "implement phase failed" in reason
        assert "Syntax error" in reason

    def test_extract_failure_unknown_when_no_failed_phase(self):
        """Should return unknown if no failed phase found."""
        inner_results = {
            "design": {"status": "completed", "cost": 0.01},
        }

        reason = ArtisanContractorWorkflow._extract_failure_reason(inner_results)

        assert "Unknown" in reason

    def test_extract_terminal_phase(self):
        """Should return the inner phase where execution terminated."""
        inner_results = {
            "design": {"status": "completed", "cost": 0.01},
            "implement": {"status": "budget_exceeded", "cost": 0.02},
        }
        phase = ArtisanContractorWorkflow._extract_terminal_phase(inner_results)
        assert phase == "implement"


class TestBuildFeaturePartialResult:
    """Tests for _build_feature_partial_result helper."""

    def test_build_partial_result_includes_fitness_summary(self):
        """Partial result should include pre-computed fitness summary."""
        config = WorkflowConfig(workflow_id="test")
        workflow = ArtisanContractorWorkflow(config=config)

        inner_results = {
            "design": {"status": "completed", "cost": 0.01, "timestamp": "2026-01-01T00:00:00+00:00"},
            "implement": {"status": "failed", "cost": 0.02, "error": "Test error"},
        }

        result = workflow._build_feature_partial_result(
            feature_id="f1",
            inner_results=inner_results,
            failure_reason="Implementation failed",
        )

        assert result["feature_id"] == "f1"
        assert result["failure_reason"] == "Implementation failed"
        assert "fitness_summary" in result
        assert result["fitness_summary"]["has_design"] is True
        assert result["fitness_summary"]["failed_phase"] == "implement"


class TestFeatureTaskSelection:
    """Tests feature-serial task selection behavior in handlers."""

    def test_ensure_context_loaded_filters_to_current_feature(self):
        """Handlers should receive only current_feature_id task in feature-serial mode."""
        t1 = SimpleNamespace(task_id="F1")
        t2 = SimpleNamespace(task_id="F2")
        context = {
            "tasks": [t1, t2],
            "current_feature_id": "F2",
        }
        selected = _ensure_context_loaded(context)
        assert [t.task_id for t in selected] == ["F2"]

    def test_ensure_context_loaded_raises_on_unknown_feature(self):
        """Unknown current_feature_id should fail fast (no silent full-task execution)."""
        t1 = SimpleNamespace(task_id="F1")
        context = {
            "tasks": [t1],
            "current_feature_id": "F9",
        }
        with pytest.raises(RuntimeError, match="unknown current_feature_id"):
            _ensure_context_loaded(context)
