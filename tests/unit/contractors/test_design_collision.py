"""Unit tests for CCD Layer 5 — design_collision module (REQ-CCD-500-503).

Covers:
  - extract_entities()
  - _check_mode_conflicts()
  - _check_entity_collisions()
  - check_lane_collisions()
  - LaneCollisionResult.to_dict()
  - _format_collision_context()
"""
from __future__ import annotations

import pytest

from startd8.contractors.design_collision import (
    CollisionSeverity,
    DesignCollision,
    LaneCollisionResult,
    _check_entity_collisions,
    _check_mode_conflicts,
    _format_collision_context,
    check_lane_collisions,
    extract_entities,
)

# Pull in FakeSeedTask from the shared conftest so we get the real attribute
# surface (task_id + target_files) required by check_lane_collisions().
from tests.unit.contractors.conftest import FakeSeedTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_result(lane_index: int = 0) -> LaneCollisionResult:
    """Return a blank LaneCollisionResult for mutation in check helpers."""
    return LaneCollisionResult(
        lane_index=lane_index,
        task_ids=[],
        shared_files=[],
    )


# ---------------------------------------------------------------------------
# extract_entities
# ---------------------------------------------------------------------------


class TestExtractEntities:
    """extract_entities extracts classes, functions, and imports via regex."""

    def test_empty_text(self):
        """Empty string returns empty sets for all entity types."""
        result = extract_entities("")
        assert result == {"classes": set(), "functions": set(), "imports": set()}

    def test_none_like_falsy(self):
        """None-equivalent (empty string) returns empty sets."""
        result = extract_entities("")
        assert not result["classes"]
        assert not result["functions"]
        assert not result["imports"]

    def test_class_extraction(self):
        """PascalCase class names are extracted."""
        text = "class MyWidget:\n    pass\nclass AnotherClass:\n    pass"
        result = extract_entities(text)
        assert "MyWidget" in result["classes"]
        assert "AnotherClass" in result["classes"]
        assert not result["functions"]

    def test_function_extraction(self):
        """Snake-case def names are extracted."""
        text = "def compute_lanes(tasks):\n    pass\ndef _helper(x):\n    pass"
        result = extract_entities(text)
        assert "compute_lanes" in result["functions"]
        assert "_helper" in result["functions"]
        assert not result["classes"]

    def test_import_extraction(self):
        """from/import statements are extracted."""
        text = (
            "from startd8.logging_config import get_logger\n"
            "import os\n"
            "from typing import Any\n"
        )
        result = extract_entities(text)
        assert "startd8.logging_config" in result["imports"]
        assert "os" in result["imports"]
        assert "typing" in result["imports"]

    def test_mixed_content(self):
        """Class, function, and import all extracted from same document."""
        text = (
            "import sys\n"
            "class Processor:\n"
            "    def run(self):\n"
            "        pass\n"
            "def standalone_fn(x):\n"
            "    pass\n"
        )
        result = extract_entities(text)
        assert "Processor" in result["classes"]
        assert "run" in result["functions"]
        assert "standalone_fn" in result["functions"]
        assert "sys" in result["imports"]

    def test_lowercase_class_not_extracted(self):
        """Class names that start with lowercase are NOT extracted (pattern requires PascalCase)."""
        text = "class lowerCase:\n    pass"
        result = extract_entities(text)
        assert not result["classes"]

    def test_returns_sets(self):
        """Return values for each entity type are sets, not lists."""
        result = extract_entities("class Foo:\n    pass")
        assert isinstance(result["classes"], set)
        assert isinstance(result["functions"], set)
        assert isinstance(result["imports"], set)


# ---------------------------------------------------------------------------
# _check_mode_conflicts
# ---------------------------------------------------------------------------


class TestCheckModeConflicts:
    """_check_mode_conflicts detects create/update design-mode conflicts."""

    def test_double_create_is_conflicting(self):
        """Two tasks both creating the same file → CONFLICTING collision."""
        result = _empty_result()
        _check_mode_conflicts(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            design_mode_summary={"T-1": "create", "T-2": "create"},
            result=result,
        )

        assert len(result.collisions) == 1
        col = result.collisions[0]
        assert col.conflict_type == "mode_double_create"
        assert col.severity == CollisionSeverity.CONFLICTING
        assert col.file_path == "src/widget.py"
        assert {col.task_a, col.task_b} == {"T-1", "T-2"}

    def test_create_plus_update_is_warning(self):
        """One creator + one updater for same file → WARNING collision."""
        result = _empty_result()
        _check_mode_conflicts(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            design_mode_summary={"T-1": "create", "T-2": "update"},
            result=result,
        )

        assert len(result.collisions) == 1
        col = result.collisions[0]
        assert col.conflict_type == "mode_conflict"
        assert col.severity == CollisionSeverity.WARNING

    def test_double_update_no_collision(self):
        """Two tasks both updating the same file → no collision record."""
        result = _empty_result()
        _check_mode_conflicts(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            design_mode_summary={"T-1": "update", "T-2": "update"},
            result=result,
        )

        assert result.collisions == []

    def test_no_modes_no_collision(self):
        """Tasks absent from design_mode_summary produce no collision."""
        result = _empty_result()
        _check_mode_conflicts(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            design_mode_summary={},
            result=result,
        )

        assert result.collisions == []

    def test_three_creators_generates_three_pairs(self):
        """Three creators → three pairwise CONFLICTING collisions (C(3,2)=3)."""
        result = _empty_result()
        _check_mode_conflicts(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2", "T-3"],
            design_mode_summary={"T-1": "create", "T-2": "create", "T-3": "create"},
            result=result,
        )

        double_create = [
            c for c in result.collisions if c.conflict_type == "mode_double_create"
        ]
        assert len(double_create) == 3

    def test_create_plus_two_updaters(self):
        """One creator + two updaters → two WARNING collisions (one per updater)."""
        result = _empty_result()
        _check_mode_conflicts(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2", "T-3"],
            design_mode_summary={"T-1": "create", "T-2": "update", "T-3": "update"},
            result=result,
        )

        mode_conflicts = [
            c for c in result.collisions if c.conflict_type == "mode_conflict"
        ]
        assert len(mode_conflicts) == 2
        for col in mode_conflicts:
            assert col.severity == CollisionSeverity.WARNING


# ---------------------------------------------------------------------------
# _check_entity_collisions
# ---------------------------------------------------------------------------


class TestCheckEntityCollisions:
    """_check_entity_collisions detects duplicate class/function names."""

    def test_duplicate_class_is_warning(self):
        """Two tasks defining the same class name → WARNING duplicate_class."""
        result = _empty_result()
        task_entities = {
            "T-1": {"classes": {"Processor"}, "functions": set(), "imports": set()},
            "T-2": {"classes": {"Processor"}, "functions": set(), "imports": set()},
        }
        _check_entity_collisions(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            task_entities=task_entities,
            result=result,
        )

        assert len(result.collisions) == 1
        col = result.collisions[0]
        assert col.conflict_type == "duplicate_class"
        assert col.severity == CollisionSeverity.WARNING
        assert "Processor" in col.detail

    def test_duplicate_function_is_warning(self):
        """Two tasks defining the same function name → WARNING duplicate_function."""
        result = _empty_result()
        task_entities = {
            "T-1": {"classes": set(), "functions": {"run_task"}, "imports": set()},
            "T-2": {"classes": set(), "functions": {"run_task"}, "imports": set()},
        }
        _check_entity_collisions(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            task_entities=task_entities,
            result=result,
        )

        assert len(result.collisions) == 1
        assert result.collisions[0].conflict_type == "duplicate_function"

    def test_no_overlap_no_collision(self):
        """Non-overlapping entity sets produce no collision."""
        result = _empty_result()
        task_entities = {
            "T-1": {"classes": {"Alpha"}, "functions": {"do_alpha"}, "imports": set()},
            "T-2": {"classes": {"Beta"}, "functions": {"do_beta"}, "imports": set()},
        }
        _check_entity_collisions(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            task_entities=task_entities,
            result=result,
        )

        assert result.collisions == []

    def test_import_overlap_not_flagged(self):
        """Shared imports do NOT produce entity collisions (imports excluded)."""
        result = _empty_result()
        task_entities = {
            "T-1": {"classes": set(), "functions": set(), "imports": {"os"}},
            "T-2": {"classes": set(), "functions": set(), "imports": {"os"}},
        }
        _check_entity_collisions(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            task_entities=task_entities,
            result=result,
        )

        assert result.collisions == []

    def test_multiple_duplicate_classes(self):
        """Multiple overlapping class names produce one collision per pair."""
        result = _empty_result()
        task_entities = {
            "T-1": {
                "classes": {"Alpha", "Beta"},
                "functions": set(),
                "imports": set(),
            },
            "T-2": {
                "classes": {"Alpha", "Beta"},
                "functions": set(),
                "imports": set(),
            },
        }
        _check_entity_collisions(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            task_entities=task_entities,
            result=result,
        )

        # One collision record per overlapping entity type (classes, functions)
        class_collisions = [
            c for c in result.collisions if c.conflict_type == "duplicate_class"
        ]
        # Exactly one collision for the "classes" entity type (both names bundled)
        assert len(class_collisions) == 1

    def test_missing_task_entities_treated_as_empty(self):
        """Task absent from task_entities dict is treated as having no entities."""
        result = _empty_result()
        task_entities = {
            "T-1": {"classes": {"Processor"}, "functions": set(), "imports": set()},
            # T-2 intentionally absent
        }
        _check_entity_collisions(
            fpath="src/widget.py",
            task_ids=["T-1", "T-2"],
            task_entities=task_entities,
            result=result,
        )

        # No overlap when one side is empty
        assert result.collisions == []


# ---------------------------------------------------------------------------
# check_lane_collisions (orchestrator)
# ---------------------------------------------------------------------------


class TestCheckLaneCollisions:
    """check_lane_collisions orchestrates per-file mode + entity checks."""

    def test_no_shared_files_coherent(self):
        """Lane with no shared files → COHERENT status, no collisions."""
        t1 = FakeSeedTask(task_id="T-1", target_files=["src/a.py"])
        t2 = FakeSeedTask(task_id="T-2", target_files=["src/b.py"])

        result = check_lane_collisions(
            lane_index=0,
            lane_tasks=[t1, t2],
            design_results={},
            shared_file_manifest={},
            design_mode_summary={},
        )

        assert result.status == CollisionSeverity.COHERENT
        assert result.collisions == []
        assert result.shared_files == []

    def test_detects_duplicate_class(self):
        """Shared file with duplicate class → at least one WARNING collision."""
        t1 = FakeSeedTask(task_id="T-1", target_files=["src/widget.py"])
        t2 = FakeSeedTask(task_id="T-2", target_files=["src/widget.py"])

        design_results = {
            "T-1": {"design_document": "class Processor:\n    pass"},
            "T-2": {"design_document": "class Processor:\n    pass"},
        }
        shared_file_manifest = {"src/widget.py": ["T-1", "T-2"]}

        result = check_lane_collisions(
            lane_index=0,
            lane_tasks=[t1, t2],
            design_results=design_results,
            shared_file_manifest=shared_file_manifest,
            design_mode_summary={},
        )

        assert result.status in (CollisionSeverity.WARNING, CollisionSeverity.CONFLICTING)
        assert any(c.conflict_type == "duplicate_class" for c in result.collisions)

    def test_worst_severity_wins(self):
        """A CONFLICTING collision drives the overall status to CONFLICTING."""
        t1 = FakeSeedTask(task_id="T-1", target_files=["src/widget.py"])
        t2 = FakeSeedTask(task_id="T-2", target_files=["src/widget.py"])

        design_results = {
            "T-1": {"design_document": "class Foo:\n    pass"},
            "T-2": {"design_document": "class Bar:\n    pass"},
        }
        shared_file_manifest = {"src/widget.py": ["T-1", "T-2"]}
        # Both create → CONFLICTING
        design_mode_summary = {"T-1": "create", "T-2": "create"}

        result = check_lane_collisions(
            lane_index=0,
            lane_tasks=[t1, t2],
            design_results=design_results,
            shared_file_manifest=shared_file_manifest,
            design_mode_summary=design_mode_summary,
        )

        assert result.status == CollisionSeverity.CONFLICTING

    def test_lane_index_stored_on_result(self):
        """LaneCollisionResult.lane_index matches the provided lane_index."""
        t1 = FakeSeedTask(task_id="T-1", target_files=["src/a.py"])
        result = check_lane_collisions(
            lane_index=3,
            lane_tasks=[t1],
            design_results={},
            shared_file_manifest={},
            design_mode_summary={},
        )
        assert result.lane_index == 3

    def test_task_ids_stored_on_result(self):
        """LaneCollisionResult.task_ids contains all provided task IDs."""
        t1 = FakeSeedTask(task_id="T-1", target_files=[])
        t2 = FakeSeedTask(task_id="T-2", target_files=[])
        result = check_lane_collisions(
            lane_index=0,
            lane_tasks=[t1, t2],
            design_results={},
            shared_file_manifest={},
            design_mode_summary={},
        )
        assert set(result.task_ids) == {"T-1", "T-2"}

    def test_only_lane_tasks_considered_for_shared_files(self):
        """Tasks in shared_file_manifest but NOT in lane_tasks are ignored."""
        t1 = FakeSeedTask(task_id="T-1", target_files=["src/widget.py"])
        # T-99 is in the manifest but not in lane_tasks
        shared_file_manifest = {"src/widget.py": ["T-1", "T-99"]}

        result = check_lane_collisions(
            lane_index=0,
            lane_tasks=[t1],
            design_results={},
            shared_file_manifest=shared_file_manifest,
            design_mode_summary={},
        )

        # Only one lane task involved → no pairwise check possible → COHERENT
        assert result.status == CollisionSeverity.COHERENT

    def test_warning_only_when_no_conflicting(self):
        """All WARNING collisions → overall status is WARNING (not CONFLICTING)."""
        t1 = FakeSeedTask(task_id="T-1", target_files=["src/widget.py"])
        t2 = FakeSeedTask(task_id="T-2", target_files=["src/widget.py"])

        design_results = {
            "T-1": {"design_document": "class Processor:\n    pass"},
            "T-2": {"design_document": "class Processor:\n    pass"},
        }
        shared_file_manifest = {"src/widget.py": ["T-1", "T-2"]}
        # create + update → WARNING only
        design_mode_summary = {"T-1": "create", "T-2": "update"}

        result = check_lane_collisions(
            lane_index=0,
            lane_tasks=[t1, t2],
            design_results=design_results,
            shared_file_manifest=shared_file_manifest,
            design_mode_summary=design_mode_summary,
        )

        # At minimum WARNING from mode conflict; no CONFLICTING
        assert result.status == CollisionSeverity.WARNING
        assert all(
            c.severity != CollisionSeverity.CONFLICTING for c in result.collisions
        )


# ---------------------------------------------------------------------------
# LaneCollisionResult.to_dict serialization
# ---------------------------------------------------------------------------


class TestLaneCollisionResultSerialization:
    """LaneCollisionResult.to_dict produces JSON-safe output."""

    def test_to_dict_empty(self):
        """Empty (no-collision) result serializes correctly."""
        result = LaneCollisionResult(
            lane_index=0,
            task_ids=["T-1"],
            shared_files=[],
        )
        d = result.to_dict()

        assert d["lane_index"] == 0
        assert d["task_ids"] == ["T-1"]
        assert d["shared_files"] == []
        assert d["collisions"] == []
        assert d["status"] == "COHERENT"

    def test_to_dict_with_collisions(self):
        """Result with collisions serializes severity as string value."""
        collision = DesignCollision(
            file_path="src/widget.py",
            task_a="T-1",
            task_b="T-2",
            conflict_type="duplicate_class",
            severity=CollisionSeverity.WARNING,
            detail="Both define Processor",
        )
        result = LaneCollisionResult(
            lane_index=1,
            task_ids=["T-1", "T-2"],
            shared_files=["src/widget.py"],
            collisions=[collision],
            status=CollisionSeverity.WARNING,
        )
        d = result.to_dict()

        assert d["status"] == "WARNING"
        assert len(d["collisions"]) == 1
        col_d = d["collisions"][0]
        assert col_d["file_path"] == "src/widget.py"
        assert col_d["task_a"] == "T-1"
        assert col_d["task_b"] == "T-2"
        assert col_d["conflict_type"] == "duplicate_class"
        assert col_d["severity"] == "WARNING"
        assert col_d["detail"] == "Both define Processor"

    def test_to_dict_conflicting_status(self):
        """CONFLICTING status is serialized as string."""
        result = LaneCollisionResult(
            lane_index=0,
            task_ids=[],
            shared_files=[],
            status=CollisionSeverity.CONFLICTING,
        )
        assert result.to_dict()["status"] == "CONFLICTING"

    def test_to_dict_is_json_serializable(self):
        """to_dict output can be passed through json.dumps without error."""
        import json

        collision = DesignCollision(
            file_path="src/a.py",
            task_a="T-1",
            task_b="T-2",
            conflict_type="mode_double_create",
            severity=CollisionSeverity.CONFLICTING,
            detail="Both create a.py",
        )
        result = LaneCollisionResult(
            lane_index=0,
            task_ids=["T-1", "T-2"],
            shared_files=["src/a.py"],
            collisions=[collision],
            status=CollisionSeverity.CONFLICTING,
        )
        # Should not raise
        serialized = json.dumps(result.to_dict())
        assert "CONFLICTING" in serialized


# ---------------------------------------------------------------------------
# _format_collision_context
# ---------------------------------------------------------------------------


class TestFormatCollisionContext:
    """_format_collision_context formats collision dicts as human-readable text."""

    def test_empty_collisions(self):
        """Empty list → empty string."""
        assert _format_collision_context([]) == ""

    def test_formats_collision_text(self):
        """Single collision dict is rendered with index, severity, and type."""
        collision_dict = {
            "file_path": "src/widget.py",
            "task_a": "T-1",
            "task_b": "T-2",
            "conflict_type": "duplicate_class",
            "severity": "WARNING",
            "detail": "Both define Processor in src/widget.py.",
        }
        text = _format_collision_context([collision_dict])

        assert "WARNING" in text
        assert "duplicate_class" in text
        assert "src/widget.py" in text
        assert "T-1" in text
        assert "T-2" in text
        assert "Both define Processor" in text

    def test_multiple_collisions_numbered(self):
        """Multiple collisions are numbered sequentially starting from 1."""
        c1 = {
            "file_path": "src/a.py",
            "task_a": "T-1",
            "task_b": "T-2",
            "conflict_type": "mode_double_create",
            "severity": "CONFLICTING",
            "detail": "Both create a.py",
        }
        c2 = {
            "file_path": "src/b.py",
            "task_a": "T-3",
            "task_b": "T-4",
            "conflict_type": "duplicate_function",
            "severity": "WARNING",
            "detail": "Both define run_task",
        }
        text = _format_collision_context([c1, c2])

        assert "  1." in text
        assert "  2." in text

    def test_missing_detail_field_omitted(self):
        """Collision dict without detail key does not produce 'Detail:' line."""
        collision_dict = {
            "file_path": "src/widget.py",
            "task_a": "T-1",
            "task_b": "T-2",
            "conflict_type": "duplicate_class",
            "severity": "WARNING",
            # No 'detail' key
        }
        text = _format_collision_context([collision_dict])

        # Empty detail → no detail line rendered
        assert "Detail:" not in text

    def test_uses_to_dict_output_directly(self):
        """Format function correctly processes LaneCollisionResult.to_dict() output."""
        collision = DesignCollision(
            file_path="src/widget.py",
            task_a="T-1",
            task_b="T-2",
            conflict_type="mode_conflict",
            severity=CollisionSeverity.WARNING,
            detail="create vs update ordering issue",
        )
        result = LaneCollisionResult(
            lane_index=0,
            task_ids=["T-1", "T-2"],
            shared_files=["src/widget.py"],
            collisions=[collision],
            status=CollisionSeverity.WARNING,
        )
        d = result.to_dict()
        text = _format_collision_context(d["collisions"])

        assert "mode_conflict" in text
        assert "create vs update ordering issue" in text
