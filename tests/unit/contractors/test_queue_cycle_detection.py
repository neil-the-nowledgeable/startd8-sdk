"""Tests for FeatureQueue: deadlock warning, copy-source resolution, and seed loading."""

import json
import logging
from pathlib import Path

import pytest

from startd8.contractors.queue import FeatureQueue, FeatureStatus


class TestGetNextFeatureDeadlockWarning:
    """Tests for deadlock detection in get_next_feature."""

    def test_no_warning_when_feature_available(self, caplog):
        q = FeatureQueue(project_root=Path("/tmp/test"))
        q.add_feature("A", "A", "d", dependencies=[])

        with caplog.at_level(logging.WARNING, logger="startd8.contractors.queue"):
            result = q.get_next_feature()

        assert result is not None
        assert not any("deadlock" in r.message.lower() for r in caplog.records)

    def test_no_warning_when_all_complete(self, caplog):
        q = FeatureQueue(project_root=Path("/tmp/test"))
        q.add_feature("A", "A", "d", dependencies=[])
        q.add_feature("B", "B", "d", dependencies=["A"])
        q.features["A"].status = FeatureStatus.COMPLETE
        q.features["B"].status = FeatureStatus.COMPLETE

        with caplog.at_level(logging.WARNING, logger="startd8.contractors.queue"):
            result = q.get_next_feature()

        assert result is None
        assert not any("deadlock" in r.message.lower() for r in caplog.records)


class TestCopySourceTaskIdResolution:
    """Tests for plan-level ID → task ID resolution in add_features_from_seed."""

    def _make_seed(self, tmp_path, tasks):
        seed = {"version": "1.0", "tasks": tasks}
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed))
        return seed_path

    def test_resolves_plan_id_to_task_id(self, tmp_path):
        """copy_source_task_id F-001a resolves to PI-001 (run-039 fix)."""
        seed_path = self._make_seed(tmp_path, [
            {
                "task_id": "PI-001",
                "title": "Logger — emailservice",
                "config": {
                    "task_description": "Logger impl",
                    "context": {
                        "feature_id": "F-001a",
                        "target_files": ["src/emailservice/logger.py"],
                    },
                },
            },
            {
                "task_id": "PI-002",
                "title": "Logger — recommendationservice",
                "depends_on": ["PI-001"],
                "config": {
                    "task_description": "Identical copy",
                    "context": {
                        "feature_id": "F-001b",
                        "target_files": ["src/recommendationservice/logger.py"],
                        "copy_source_task_id": "F-001a",
                        "copy_source_file": "src/emailservice/logger.py",
                    },
                },
            },
        ])

        q = FeatureQueue(project_root=tmp_path)
        q.add_features_from_seed(seed_path)

        pi002 = q.get_feature("PI-002")
        assert pi002 is not None
        # Should be resolved to PI-001, not F-001a
        assert pi002.copy_source_task_id == "PI-001"
        assert pi002.copy_source_file == "src/emailservice/logger.py"

    def test_passthrough_when_already_task_id(self, tmp_path):
        """copy_source_task_id that already matches a task_id passes through."""
        seed_path = self._make_seed(tmp_path, [
            {
                "task_id": "PI-001",
                "title": "A",
                "config": {"task_description": "d", "context": {"target_files": []}},
            },
            {
                "task_id": "PI-002",
                "title": "B",
                "depends_on": ["PI-001"],
                "config": {
                    "task_description": "d",
                    "context": {
                        "target_files": [],
                        "copy_source_task_id": "PI-001",
                    },
                },
            },
        ])

        q = FeatureQueue(project_root=tmp_path)
        q.add_features_from_seed(seed_path)

        pi002 = q.get_feature("PI-002")
        assert pi002.copy_source_task_id == "PI-001"

    def test_unknown_plan_id_passes_through(self, tmp_path):
        """Unresolvable copy_source_task_id is kept as-is (best effort)."""
        seed_path = self._make_seed(tmp_path, [
            {
                "task_id": "PI-001",
                "title": "A",
                "config": {
                    "task_description": "d",
                    "context": {
                        "target_files": [],
                        "copy_source_task_id": "UNKNOWN-999",
                    },
                },
            },
        ])

        q = FeatureQueue(project_root=tmp_path)
        q.add_features_from_seed(seed_path)

        pi001 = q.get_feature("PI-001")
        assert pi001.copy_source_task_id == "UNKNOWN-999"
