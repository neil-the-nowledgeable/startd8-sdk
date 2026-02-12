"""
Unit tests for TaskErrorStore.

Validates error persistence, listing, clearing, and convenience wrappers.
All tests use tmp_path — no real project directories are touched.
"""

import json
from pathlib import Path

import pytest

from startd8.storage.error_store import TaskError, TaskErrorStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> TaskErrorStore:
    """Create a TaskErrorStore rooted at a temporary directory."""
    return TaskErrorStore(project_root=tmp_path)


# ---------------------------------------------------------------------------
# TaskError dataclass
# ---------------------------------------------------------------------------


class TestTaskError:
    def test_to_dict_includes_all_fields(self):
        err = TaskError(
            workflow_id="wf-1",
            source="implement",
            error_type="PhaseExecutionError",
            error_message="LLM returned empty output",
            context={"task_id": "PI-001"},
        )
        d = err.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["source"] == "implement"
        assert d["error_type"] == "PhaseExecutionError"
        assert d["error_message"] == "LLM returned empty output"
        assert d["context"]["task_id"] == "PI-001"
        assert "timestamp" in d

    def test_to_dict_strips_none_traceback(self):
        err = TaskError(
            workflow_id="wf-1",
            source="plan",
            error_type="E",
            error_message="msg",
        )
        d = err.to_dict()
        assert "traceback" not in d

    def test_to_dict_includes_traceback_when_set(self):
        err = TaskError(
            workflow_id="wf-1",
            source="plan",
            error_type="E",
            error_message="msg",
            traceback="Traceback (most recent call last):\n  ...",
        )
        d = err.to_dict()
        assert "traceback" in d
        assert "Traceback" in d["traceback"]


# ---------------------------------------------------------------------------
# record_error
# ---------------------------------------------------------------------------


class TestRecordError:
    def test_creates_json_file(self, store: TaskErrorStore, tmp_path: Path):
        path = store.record_error(
            workflow_id="wf-1",
            source="implement",
            error_message="Something went wrong",
        )
        assert path.exists()
        assert path.suffix == ".json"
        data = json.loads(path.read_text())
        assert data["workflow_id"] == "wf-1"
        assert data["source"] == "implement"
        assert data["error_message"] == "Something went wrong"

    def test_creates_under_workflow_subdirectory(
        self, store: TaskErrorStore, tmp_path: Path
    ):
        path = store.record_error(
            workflow_id="artisan-PI-001",
            source="plan",
            error_message="oops",
        )
        assert "artisan-PI-001" in str(path.parent.name)

    def test_appends_to_jsonl(self, store: TaskErrorStore, tmp_path: Path):
        store.record_error(
            workflow_id="wf-1", source="a", error_message="first"
        )
        store.record_error(
            workflow_id="wf-1", source="b", error_message="second"
        )
        lines = store.jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["error_message"] == "first"
        assert json.loads(lines[1])["error_message"] == "second"

    def test_exception_extracts_type_and_traceback(
        self, store: TaskErrorStore
    ):
        try:
            raise ValueError("bad value")
        except ValueError as exc:
            path = store.record_error(
                workflow_id="wf-2",
                source="test",
                error_message="caught",
                exception=exc,
            )

        data = json.loads(path.read_text())
        assert data["error_type"] == "ValueError"
        assert "traceback" in data
        assert "bad value" in data["traceback"]

    def test_handles_filename_collision(self, store: TaskErrorStore):
        """Two errors recorded in the same second should not overwrite."""
        p1 = store.record_error(
            workflow_id="wf-1", source="plan", error_message="first"
        )
        p2 = store.record_error(
            workflow_id="wf-1", source="plan", error_message="second"
        )
        assert p1 != p2
        assert p1.exists()
        assert p2.exists()


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


class TestRecordPhaseError:
    def test_includes_phase_and_cost(self, store: TaskErrorStore):
        path = store.record_phase_error(
            workflow_id="wf-1",
            phase="implement",
            error_message="timeout",
            cost=0.42,
            duration_seconds=12.5,
        )
        data = json.loads(path.read_text())
        assert data["context"]["phase"] == "implement"
        assert data["context"]["cost"] == 0.42
        assert data["context"]["duration_seconds"] == 12.5
        assert data["error_type"] == "PhaseExecutionError"


class TestRecordGenerationError:
    def test_includes_task_id_and_target_file(self, store: TaskErrorStore):
        path = store.record_generation_error(
            workflow_id="wf-1",
            task_id="PI-003",
            error_message="empty output",
            target_file="src/foo.py",
        )
        data = json.loads(path.read_text())
        assert data["context"]["task_id"] == "PI-003"
        assert data["context"]["target_file"] == "src/foo.py"
        assert data["error_type"] == "GenerationError"


class TestRecordWorkflowResultError:
    def test_includes_failed_steps(self, store: TaskErrorStore):
        path = store.record_workflow_result_error(
            workflow_id="wf-1",
            error_message="workflow failed",
            steps=[
                {"step_name": "step1", "error": None},
                {"step_name": "step2", "error": "boom"},
            ],
            metrics={"total_time_ms": 5000},
        )
        data = json.loads(path.read_text())
        assert data["error_type"] == "WorkflowResultError"
        assert len(data["context"]["failed_steps"]) == 1
        assert data["context"]["failed_steps"][0]["step_name"] == "step2"
        assert data["context"]["total_steps"] == 2
        assert data["context"]["metrics"]["total_time_ms"] == 5000


# ---------------------------------------------------------------------------
# list_errors
# ---------------------------------------------------------------------------


class TestListErrors:
    def test_empty_when_no_errors(self, store: TaskErrorStore):
        assert store.list_errors() == []

    def test_returns_errors_newest_first(self, store: TaskErrorStore):
        store.record_error(
            workflow_id="wf-1", source="a", error_message="old"
        )
        store.record_error(
            workflow_id="wf-1", source="b", error_message="new"
        )
        errors = store.list_errors()
        assert len(errors) == 2
        # Newest first (both have very close timestamps but "new" was second)
        assert errors[0]["error_message"] == "new"

    def test_filter_by_workflow_id(self, store: TaskErrorStore):
        store.record_error(
            workflow_id="wf-1", source="a", error_message="one"
        )
        store.record_error(
            workflow_id="wf-2", source="b", error_message="two"
        )
        errors = store.list_errors(workflow_id="wf-1")
        assert len(errors) == 1
        assert errors[0]["workflow_id"] == "wf-1"

    def test_limit(self, store: TaskErrorStore):
        for i in range(10):
            store.record_error(
                workflow_id="wf-1", source="x", error_message=f"err-{i}"
            )
        assert len(store.list_errors(limit=3)) == 3

    def test_returns_empty_for_unknown_workflow(self, store: TaskErrorStore):
        store.record_error(
            workflow_id="wf-1", source="a", error_message="exists"
        )
        assert store.list_errors(workflow_id="nonexistent") == []


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_specific_workflow(self, store: TaskErrorStore):
        store.record_error(
            workflow_id="wf-1", source="a", error_message="keep"
        )
        store.record_error(
            workflow_id="wf-2", source="b", error_message="remove"
        )
        removed = store.clear(workflow_id="wf-2")
        assert removed == 1
        assert len(store.list_errors(workflow_id="wf-1")) == 1
        assert len(store.list_errors(workflow_id="wf-2")) == 0

    def test_clear_all(self, store: TaskErrorStore):
        store.record_error(
            workflow_id="wf-1", source="a", error_message="one"
        )
        store.record_error(
            workflow_id="wf-2", source="b", error_message="two"
        )
        removed = store.clear()
        assert removed == 2
        assert store.list_errors() == []

    def test_clear_returns_zero_when_empty(self, store: TaskErrorStore):
        assert store.clear() == 0


# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------


class TestDirectoryStructure:
    def test_creates_startd8_task_errors_directory(
        self, store: TaskErrorStore, tmp_path: Path
    ):
        store.record_error(
            workflow_id="wf-1", source="test", error_message="hello"
        )
        errors_dir = tmp_path / ".startd8" / "task_errors"
        assert errors_dir.is_dir()
        assert (errors_dir / "wf-1").is_dir()

    def test_jsonl_in_errors_root(
        self, store: TaskErrorStore, tmp_path: Path
    ):
        store.record_error(
            workflow_id="wf-1", source="test", error_message="hello"
        )
        jsonl = tmp_path / ".startd8" / "task_errors" / "errors.jsonl"
        assert jsonl.exists()

    def test_custom_base_dir(self, tmp_path: Path):
        store = TaskErrorStore(project_root=tmp_path, base_dir=".custom")
        store.record_error(
            workflow_id="wf-1", source="test", error_message="hello"
        )
        assert (tmp_path / ".custom" / "task_errors" / "wf-1").is_dir()
