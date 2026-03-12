"""Tests for circular dependency detection, deadlock warning, and seed loading in FeatureQueue."""

import json
import logging
from pathlib import Path

import pytest

from startd8.contractors.queue import FeatureQueue, FeatureStatus


class TestFindCycles:
    """Unit tests for _find_cycles static method."""

    def test_no_cycles(self):
        adj = {"A": ["B"], "B": ["C"], "C": []}
        cycles = FeatureQueue._find_cycles(adj)
        assert cycles == []

    def test_simple_two_node_cycle(self):
        adj = {"A": ["B"], "B": ["A"]}
        cycles = FeatureQueue._find_cycles(adj)
        assert len(cycles) >= 1
        # At least one cycle should contain both A and B
        cycle_nodes = set()
        for c in cycles:
            cycle_nodes.update(c)
        assert "A" in cycle_nodes
        assert "B" in cycle_nodes

    def test_three_node_cycle(self):
        adj = {"A": ["B"], "B": ["C"], "C": ["A"]}
        cycles = FeatureQueue._find_cycles(adj)
        assert len(cycles) >= 1

    def test_self_loop(self):
        adj = {"A": ["A"]}
        cycles = FeatureQueue._find_cycles(adj)
        assert len(cycles) >= 1

    def test_empty_graph(self):
        cycles = FeatureQueue._find_cycles({})
        assert cycles == []

    def test_disconnected_with_cycle(self):
        adj = {"A": ["B"], "B": [], "C": ["D"], "D": ["C"]}
        cycles = FeatureQueue._find_cycles(adj)
        assert len(cycles) >= 1
        cycle_nodes = set()
        for c in cycles:
            cycle_nodes.update(c)
        assert "C" in cycle_nodes
        assert "D" in cycle_nodes

    def test_diamond_no_cycle(self):
        adj = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        cycles = FeatureQueue._find_cycles(adj)
        assert cycles == []


class TestDetectAndBreakCycles:
    """Integration tests for cycle detection in add_features_from_seed."""

    def _make_queue(self) -> FeatureQueue:
        return FeatureQueue(project_root=Path("/tmp/test-project"))

    def test_breaks_simple_cycle(self):
        q = self._make_queue()
        q.add_feature("A", "Feature A", "desc", dependencies=["B"])
        q.add_feature("B", "Feature B", "desc", dependencies=["A"])
        q._detect_and_break_cycles()

        # One edge should be broken
        a_deps = q.features["A"].dependencies
        b_deps = q.features["B"].dependencies
        # At least one direction must be broken
        assert not (("A" in b_deps) and ("B" in a_deps)), \
            "Cycle should have been broken"

    def test_breaks_three_node_cycle(self):
        q = self._make_queue()
        q.add_feature("A", "A", "d", dependencies=["B"])
        q.add_feature("B", "B", "d", dependencies=["C"])
        q.add_feature("C", "C", "d", dependencies=["A"])
        q._detect_and_break_cycles()

        # Build adjacency and verify no cycles remain
        adj = {fid: list(f.dependencies) for fid, f in q.features.items()}
        remaining = FeatureQueue._find_cycles(adj)
        assert remaining == [], f"Cycles remain: {remaining}"

    def test_no_cycle_untouched(self):
        q = self._make_queue()
        q.add_feature("A", "A", "d", dependencies=[])
        q.add_feature("B", "B", "d", dependencies=["A"])
        q.add_feature("C", "C", "d", dependencies=["B"])
        q._detect_and_break_cycles()

        assert q.features["A"].dependencies == []
        assert q.features["B"].dependencies == ["A"]
        assert q.features["C"].dependencies == ["B"]

    def test_logs_warning_on_cycle(self, caplog):
        q = self._make_queue()
        q.add_feature("X", "X", "d", dependencies=["Y"])
        q.add_feature("Y", "Y", "d", dependencies=["X"])

        with caplog.at_level(logging.WARNING, logger="startd8.contractors.queue"):
            q._detect_and_break_cycles()

        assert any("Circular dependency detected" in r.message for r in caplog.records)

    def test_online_boutique_cycles_broken(self):
        """Reproduce the real-world circular deps from the online-boutique seed."""
        q = self._make_queue()
        # Simplified reproduction: PI-001 ↔ PI-003 cycle
        q.add_feature("PI-001", "Logger", "d", dependencies=["PI-003"])
        q.add_feature("PI-003", "Server", "d", dependencies=["PI-001"])
        q.add_feature("PI-004", "Client", "d", dependencies=["PI-003"])

        q._detect_and_break_cycles()

        adj = {fid: list(f.dependencies) for fid, f in q.features.items()}
        remaining = FeatureQueue._find_cycles(adj)
        assert remaining == [], f"Cycles remain: {remaining}"

        # Should be able to get a next feature now
        nxt = q.get_next_feature()
        assert nxt is not None, "Should have a runnable feature after breaking cycles"


class TestGetNextFeatureDeadlockWarning:
    """Tests for deadlock detection in get_next_feature."""

    def test_deadlock_warning_logged(self, caplog):
        q = FeatureQueue(project_root=Path("/tmp/test"))
        q.add_feature("A", "A", "d", dependencies=["B"])
        q.add_feature("B", "B", "d", dependencies=["C"])
        # C doesn't exist — B can never be satisfied

        with caplog.at_level(logging.WARNING, logger="startd8.contractors.queue"):
            result = q.get_next_feature()

        assert result is None
        assert any("deadlock" in r.message.lower() for r in caplog.records)

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
