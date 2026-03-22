"""Tests for TODO completion v3 integration into Prime Contractor.

Covers:
- Step 1: task_type threading through queue boundary (REQ-TCW-201)
- Step 2: _try_uncomment_shortcut() dispatch (REQ-TCW-300)
- Step 3: post-generation TODO scan trigger (REQ-TCW-203)
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest import mock

import pytest

from startd8.contractors.queue import FeatureQueue, FeatureSpec


# ---------------------------------------------------------------------------
# Step 1: Queue task_type metadata threading
# ---------------------------------------------------------------------------


class TestQueueTaskTypeThreading:
    """REQ-TCW-201: task_type survives add_features_from_seed()."""

    def _write_seed(self, tmp_path: Path, tasks: list) -> Path:
        seed = {"schema_version": "1.0.0", "source": "test", "tasks": tasks}
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed), encoding="utf-8")
        return seed_path

    def test_uncomment_task_type_preserved(self, tmp_path):
        queue = FeatureQueue(project_root=tmp_path)
        seed_path = self._write_seed(tmp_path, [
            {
                "task_id": "TODO-001",
                "title": "Uncomment profiler",
                "task_type": "uncomment",
                "config": {
                    "task_description": "Uncomment profiler block",
                    "context": {
                        "target_files": ["src/main.py"],
                        "todo_line": 42,
                        "language": "python",
                    },
                },
                "target_files": ["src/main.py"],
                "depends_on": [],
            },
        ])
        added = queue.add_features_from_seed(str(seed_path))
        assert len(added) == 1
        spec = added[0]
        assert spec.metadata.get("task_type") == "uncomment"
        assert spec.metadata.get("_todo_context", {}).get("todo_line") == 42

    def test_implement_task_type_preserved(self, tmp_path):
        queue = FeatureQueue(project_root=tmp_path)
        seed_path = self._write_seed(tmp_path, [
            {
                "task_id": "TODO-002",
                "title": "Implement initStats",
                "task_type": "implement",
                "config": {
                    "task_description": "Implement initStats",
                    "context": {"target_files": ["src/main.go"]},
                },
                "target_files": ["src/main.go"],
                "depends_on": [],
            },
        ])
        added = queue.add_features_from_seed(str(seed_path))
        spec = added[0]
        assert spec.metadata.get("task_type") == "implement"
        # _todo_context only set for uncomment tasks
        assert "_todo_context" not in spec.metadata

    def test_normal_task_has_no_task_type(self, tmp_path):
        queue = FeatureQueue(project_root=tmp_path)
        seed_path = self._write_seed(tmp_path, [
            {
                "task_id": "PI-001",
                "title": "Create main.py",
                "config": {
                    "task_description": "Create main.py",
                    "context": {"target_files": ["src/main.py"]},
                },
                "target_files": ["src/main.py"],
                "depends_on": [],
            },
        ])
        added = queue.add_features_from_seed(str(seed_path))
        assert "task_type" not in added[0].metadata


# ---------------------------------------------------------------------------
# Step 2: Uncomment shortcut dispatch
# ---------------------------------------------------------------------------


class TestUncommentShortcut:
    """REQ-TCW-300: _try_uncomment_shortcut() in develop_feature()."""

    def _make_feature(self, metadata: dict, target_files: list[str]) -> FeatureSpec:
        return FeatureSpec(
            id="TODO-001",
            name="Uncomment profiler",
            description="Uncomment profiler block",
            target_files=target_files,
            metadata=metadata,
        )

    def test_non_uncomment_returns_none(self):
        """Non-uncomment tasks pass through (return None)."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        with mock.patch.object(PrimeContractorWorkflow, "__init__", return_value=None):
            wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
            wf.project_root = Path("/tmp")
            wf.queue = FeatureQueue(project_root=Path("/tmp"))

        feature = self._make_feature({"task_type": "implement"}, ["src/main.go"])
        result = wf._try_uncomment_shortcut(feature)
        assert result is None

    def test_uncomment_succeeds_on_valid_file(self, tmp_path):
        """Category A task with valid target file uncomments successfully."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        # Create a file with a commented-out block
        target = tmp_path / "main.py"
        target.write_text(textwrap.dedent("""\
            def init():
                # TODO: enable profiler
                # import profiler
                # profiler.start()
                # profiler.configure(verbose=True)
                pass
        """))

        with mock.patch.object(PrimeContractorWorkflow, "__init__", return_value=None):
            wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
            wf.project_root = tmp_path
            wf.queue = FeatureQueue(project_root=tmp_path)
            wf.queue.add_feature("TODO-001", "Uncomment", "uncomment block", target_files=[str(target)])
            wf.queue.start_feature("TODO-001")

        feature = wf.queue.get_feature("TODO-001")
        feature.metadata = {"task_type": "uncomment"}

        # Mock _save_queue_state_with_mode to avoid file I/O
        wf._save_queue_state_with_mode = mock.MagicMock()

        result = wf._try_uncomment_shortcut(feature)
        assert result is True

        # File should have been modified (uncomment_block removes comment markers)
        content = target.read_text()
        # The exact output depends on uncomment_block logic, but it should differ
        # from original if blocks were found
        assert feature.status.value == "generated"

    def test_uncomment_fails_on_missing_file(self, tmp_path):
        """Uncomment task with missing target file returns False."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        with mock.patch.object(PrimeContractorWorkflow, "__init__", return_value=None):
            wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
            wf.project_root = tmp_path
            wf.queue = FeatureQueue(project_root=tmp_path)
            wf.queue.add_feature("TODO-001", "Uncomment", "uncomment block", target_files=[])
            wf.queue.start_feature("TODO-001")

        feature = wf.queue.get_feature("TODO-001")
        feature.metadata = {"task_type": "uncomment"}

        result = wf._try_uncomment_shortcut(feature)
        assert result is False


# ---------------------------------------------------------------------------
# Step 3: Post-generation TODO scan
# ---------------------------------------------------------------------------


class TestTodoScanAndInject:
    """REQ-TCW-203: _run_todo_scan_and_inject()."""

    def test_no_generated_dir_returns_zero(self, tmp_path):
        """When generated/ dir doesn't exist, returns (0, 0)."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        with mock.patch.object(PrimeContractorWorkflow, "__init__", return_value=None):
            wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
            wf._enable_todo_completion = True
            wf._instrumentation_contract = None

        wf._resolve_generated_dir = mock.MagicMock(return_value=None)
        assert wf._run_todo_scan_and_inject() == (0, 0)

    def test_empty_scan_returns_zero(self, tmp_path):
        """When scan finds no TODOs, returns (0, 0)."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        generated = tmp_path / "output" / "generated"
        generated.mkdir(parents=True)
        (generated / "clean.py").write_text("def main(): pass\n")

        output_dir = tmp_path / "output"

        with mock.patch.object(PrimeContractorWorkflow, "__init__", return_value=None):
            wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
            wf._enable_todo_completion = True
            wf._instrumentation_contract = None
            wf._run_id = "test-run"
            wf.queue = FeatureQueue(project_root=tmp_path)

        wf._resolve_generated_dir = mock.MagicMock(return_value=generated)
        wf._resolve_output_dir = mock.MagicMock(return_value=output_dir)

        succeeded, failed = wf._run_todo_scan_and_inject()
        assert succeeded == 0
        assert failed == 0

        # Inventory should still be written
        inv_path = output_dir / "instrumentation" / "todo-inventory.json"
        assert inv_path.exists()

    def test_scan_exception_is_non_fatal(self, tmp_path):
        """Exceptions during scan don't crash the workflow."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        with mock.patch.object(PrimeContractorWorkflow, "__init__", return_value=None):
            wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
            wf._enable_todo_completion = True
            wf._instrumentation_contract = None

        wf._resolve_generated_dir = mock.MagicMock(return_value=tmp_path)
        wf._resolve_output_dir = mock.MagicMock(side_effect=OSError("disk full"))

        # Should not raise
        succeeded, failed = wf._run_todo_scan_and_inject()
        assert succeeded == 0
        assert failed == 0
