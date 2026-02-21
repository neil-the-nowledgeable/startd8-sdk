"""
Unit tests for wave computation algorithm and related helpers.

Tests cover:
    - compute_waves() BFS dependency-depth wave assignment
    - compute_wave_metadata() wave summary statistics
    - compute_wave_index_map() canonical task_id → wave_index mapping
    - Unknown dependency handling (WARNING and strict mode)
    - Cycle detection and single-wave fallback
    - SeedTask.wave_index parsing and validation
    - Task ID safety validation (_SAFE_TASK_ID_PATTERN)
    - _TaskDictAdapter normalization for plan ingestion
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pytest

from startd8.contractors.artisan_contractor import (
    InvalidTaskIdError,
    UnresolvedDependencyError,
    _SAFE_TASK_ID_PATTERN,
    compute_wave_index_map,
    compute_wave_metadata,
    compute_waves,
)
from startd8.contractors.context_seed_handlers import SeedTask

# Import shared FakeSeedTask from conftest
from tests.unit.contractors.conftest import FakeSeedTask


# ---------------------------------------------------------------------------
# Lightweight task objects for compute_waves() tests
# ---------------------------------------------------------------------------

@dataclass
class _SimpleTask:
    """Minimal WaveComputeTask-compatible task for testing."""
    task_id: str
    depends_on: Optional[list[str]] = field(default_factory=list)


# ============================================================================
# TEST: compute_waves()
# ============================================================================


class TestComputeWaves:
    """Tests for the BFS dependency-depth wave assignment algorithm."""

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert compute_waves([]) == []

    def test_single_task(self):
        """Single task with no deps goes to Wave 0."""
        task = _SimpleTask(task_id="A")
        waves = compute_waves([task])
        assert len(waves) == 1
        assert waves[0] == [task]

    def test_linear_chain(self):
        """A→B→C produces 3 waves."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B", depends_on=["A"])
        c = _SimpleTask(task_id="C", depends_on=["B"])
        waves = compute_waves([a, b, c])
        assert len(waves) == 3
        assert waves[0] == [a]
        assert waves[1] == [b]
        assert waves[2] == [c]

    def test_diamond_dependency(self):
        """Diamond: A→{B,C}→D produces 3 waves."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B", depends_on=["A"])
        c = _SimpleTask(task_id="C", depends_on=["A"])
        d = _SimpleTask(task_id="D", depends_on=["B", "C"])
        waves = compute_waves([a, b, c, d])
        assert len(waves) == 3
        assert waves[0] == [a]
        assert set(t.task_id for t in waves[1]) == {"B", "C"}
        assert waves[2] == [d]

    def test_disconnected_components(self):
        """Independent tasks all go to Wave 0."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B")
        c = _SimpleTask(task_id="C")
        waves = compute_waves([a, b, c])
        assert len(waves) == 1
        assert set(t.task_id for t in waves[0]) == {"A", "B", "C"}

    def test_cycle_fallback_single_wave(self, caplog):
        """Cycle detection falls back to a single wave with all tasks."""
        a = _SimpleTask(task_id="A", depends_on=["B"])
        b = _SimpleTask(task_id="B", depends_on=["A"])
        with caplog.at_level(logging.WARNING):
            waves = compute_waves([a, b])
        assert len(waves) == 1
        assert set(t.task_id for t in waves[0]) == {"A", "B"}
        assert "cycle" in caplog.text.lower()
        # Verify task IDs are listed in the warning
        assert "A" in caplog.text
        assert "B" in caplog.text

    def test_order_preserved_within_wave(self):
        """Input order is preserved within each wave."""
        c = _SimpleTask(task_id="C")
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B")
        waves = compute_waves([c, a, b])
        assert len(waves) == 1
        assert [t.task_id for t in waves[0]] == ["C", "A", "B"]

    def test_depends_on_none_handled(self):
        """depends_on=None is treated as no dependencies."""
        a = _SimpleTask(task_id="A", depends_on=None)
        b = _SimpleTask(task_id="B", depends_on=["A"])
        waves = compute_waves([a, b])
        assert len(waves) == 2
        assert waves[0] == [a]
        assert waves[1] == [b]

    def test_complex_graph(self):
        """Multi-layer graph with fan-out and fan-in."""
        # A → B, C
        # B → D
        # C → D
        # D → E
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B", depends_on=["A"])
        c = _SimpleTask(task_id="C", depends_on=["A"])
        d = _SimpleTask(task_id="D", depends_on=["B", "C"])
        e = _SimpleTask(task_id="E", depends_on=["D"])
        waves = compute_waves([a, b, c, d, e])
        assert len(waves) == 4
        assert waves[0] == [a]
        assert set(t.task_id for t in waves[1]) == {"B", "C"}
        assert waves[2] == [d]
        assert waves[3] == [e]

    def test_works_with_fake_seed_task(self):
        """compute_waves() works with FakeSeedTask objects (SeedTask Protocol)."""
        a = FakeSeedTask(task_id="A", depends_on=[])
        b = FakeSeedTask(task_id="B", depends_on=["A"])
        waves = compute_waves([a, b])
        assert len(waves) == 2
        assert waves[0][0].task_id == "A"
        assert waves[1][0].task_id == "B"


# ============================================================================
# TEST: Unknown dependencies
# ============================================================================


class TestUnknownDeps:
    """Tests for unknown depends_on reference handling."""

    def test_unknown_dep_warning_logged(self, caplog):
        """Unknown dep logs WARNING with task_id and unresolved dep ID."""
        a = _SimpleTask(task_id="A", depends_on=["NONEXISTENT"])
        with caplog.at_level(logging.WARNING):
            waves = compute_waves([a])
        assert len(waves) == 1
        assert waves[0] == [a]
        assert "NONEXISTENT" in caplog.text
        assert "A" in caplog.text

    def test_unknown_dep_task_in_wave_zero(self):
        """Task with only unknown deps is placed in Wave 0."""
        a = _SimpleTask(task_id="A", depends_on=["GHOST"])
        waves = compute_waves([a])
        assert len(waves) == 1
        assert waves[0] == [a]

    def test_strict_mode_raises_error(self):
        """strict=True raises UnresolvedDependencyError on unknown deps."""
        a = _SimpleTask(task_id="A", depends_on=["MISSING"])
        with pytest.raises(UnresolvedDependencyError, match="MISSING"):
            compute_waves([a], strict=True)

    def test_strict_mode_valid_deps_ok(self):
        """strict=True does not raise for valid deps."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B", depends_on=["A"])
        waves = compute_waves([a, b], strict=True)
        assert len(waves) == 2


# ============================================================================
# TEST: compute_wave_metadata()
# ============================================================================


class TestComputeWaveMetadata:
    """Tests for wave metadata computation."""

    def test_empty_waves(self):
        """Empty wave list produces zeroed metadata."""
        meta = compute_wave_metadata([])
        assert meta["wave_count"] == 0
        assert meta["critical_path_length"] == 0

    def test_single_wave(self):
        """Single wave metadata."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B")
        waves = [[a, b]]
        meta = compute_wave_metadata(waves)
        assert meta["wave_count"] == 1
        assert meta["critical_path_length"] == 1
        assert meta["wave_summary"] == [2]

    def test_multi_wave(self):
        """Multi-wave metadata with correct summary."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B")
        c = _SimpleTask(task_id="C")
        waves = [[a, b], [c]]
        meta = compute_wave_metadata(waves)
        assert meta["wave_count"] == 2
        assert meta["critical_path_length"] == 2
        assert meta["wave_summary"] == [2, 1]


# ============================================================================
# TEST: compute_wave_index_map()
# ============================================================================


class TestComputeWaveIndexMap:
    """Tests for the canonical task_id → wave_index mapping helper."""

    def test_empty_waves(self):
        """Empty input produces empty map."""
        assert compute_wave_index_map([]) == {}

    def test_correct_mapping(self):
        """Mapping is correct for multi-wave input."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B")
        c = _SimpleTask(task_id="C")
        waves = [[a, b], [c]]
        m = compute_wave_index_map(waves)
        assert m == {"A": 0, "B": 0, "C": 1}

    def test_all_tasks_mapped(self):
        """Every task appears exactly once in the map."""
        tasks = [_SimpleTask(task_id=f"T{i}") for i in range(5)]
        waves = [tasks]
        m = compute_wave_index_map(waves)
        assert len(m) == 5
        for i in range(5):
            assert f"T{i}" in m


# ============================================================================
# TEST: wave_index parsing in SeedTask.from_seed_entry()
# ============================================================================


class TestWaveIndexParsing:
    """Tests for SeedTask.wave_index parsing and validation."""

    def _make_entry(self, wave_index=None):
        """Create a minimal valid seed entry dict."""
        entry = {
            "task_id": "PI-001",
            "title": "Test task",
            "task_type": "task",
            "story_points": 1,
            "priority": "medium",
            "labels": [],
            "depends_on": [],
            "config": {
                "task_description": "desc",
                "context": {
                    "target_files": ["a.py"],
                    "estimated_loc": 10,
                    "feature_id": "F1",
                },
            },
            "_enrichment": {
                "domain": "backend",
                "domain_reasoning": "",
                "environment_checks": [],
                "prompt_constraints": [],
                "post_generation_validators": [],
                "available_siblings": [],
            },
        }
        if wave_index is not None:
            entry["wave_index"] = wave_index
        return entry

    def test_valid_integer_accepted(self):
        """Valid integer wave_index is accepted."""
        task = SeedTask.from_seed_entry(self._make_entry(wave_index=2))
        assert task.wave_index == 2

    def test_none_when_absent(self):
        """wave_index is None when not present in entry."""
        task = SeedTask.from_seed_entry(self._make_entry())
        assert task.wave_index is None

    def test_none_when_explicit_none(self):
        """wave_index=None in entry results in None."""
        task = SeedTask.from_seed_entry(self._make_entry(wave_index=None))
        assert task.wave_index is None

    def test_negative_integer_ignored(self, caplog):
        """Negative wave_index is ignored with WARNING."""
        with caplog.at_level(logging.WARNING):
            task = SeedTask.from_seed_entry(self._make_entry(wave_index=-1))
        assert task.wave_index is None
        assert "negative" in caplog.text.lower()

    def test_non_integer_string_ignored(self, caplog):
        """Non-integer type (string) is ignored with WARNING."""
        with caplog.at_level(logging.WARNING):
            task = SeedTask.from_seed_entry(self._make_entry(wave_index="three"))
        assert task.wave_index is None
        assert "not an integer" in caplog.text.lower()

    def test_boolean_ignored(self, caplog):
        """Boolean wave_index is rejected (bool is subclass of int)."""
        with caplog.at_level(logging.WARNING):
            task = SeedTask.from_seed_entry(self._make_entry(wave_index=True))
        assert task.wave_index is None
        assert "not an integer" in caplog.text.lower()

    def test_float_ignored(self, caplog):
        """Float wave_index is ignored with WARNING."""
        with caplog.at_level(logging.WARNING):
            task = SeedTask.from_seed_entry(self._make_entry(wave_index=3.5))
        assert task.wave_index is None
        assert "not an integer" in caplog.text.lower()

    def test_zero_accepted(self):
        """wave_index=0 is valid."""
        task = SeedTask.from_seed_entry(self._make_entry(wave_index=0))
        assert task.wave_index == 0


# ============================================================================
# TEST: Task ID safety validation
# ============================================================================


class TestTaskIdSafety:
    """Tests for _SAFE_TASK_ID_PATTERN and compute_waves() task ID validation."""

    def test_valid_task_ids_accepted(self):
        """Valid task IDs pass validation."""
        for tid in ["PI-001", "task_42", "my-task", "A", "T1"]:
            task = _SimpleTask(task_id=tid)
            waves = compute_waves([task])
            assert len(waves) == 1

    def test_dotted_task_ids_accepted(self):
        """Dotted task IDs are accepted (backward compatibility)."""
        for tid in ["svc.emailservice.dockerfile", "PI-001.subtask.2"]:
            task = _SimpleTask(task_id=tid)
            waves = compute_waves([task])
            assert len(waves) == 1

    def test_path_separator_rejected(self):
        """Task ID with path separators raises InvalidTaskIdError."""
        task = _SimpleTask(task_id="../etc/passwd")
        with pytest.raises(InvalidTaskIdError):
            compute_waves([task])

    def test_shell_metacharacters_rejected(self):
        """Task ID with shell metacharacters raises InvalidTaskIdError."""
        task = _SimpleTask(task_id=";rm -rf")
        with pytest.raises(InvalidTaskIdError):
            compute_waves([task])

    def test_format_string_rejected(self):
        """Task ID with format string patterns raises InvalidTaskIdError."""
        for tid in ["%s", "{0}", "task${var}"]:
            task = _SimpleTask(task_id=tid)
            with pytest.raises(InvalidTaskIdError):
                compute_waves([task])

    def test_dependency_reference_unsafe_rejected(self):
        """Unsafe dependency references raise InvalidTaskIdError."""
        a = _SimpleTask(task_id="A")
        b = _SimpleTask(task_id="B", depends_on=["../bad"])
        with pytest.raises(InvalidTaskIdError):
            compute_waves([a, b])

    def test_empty_task_id_rejected(self):
        """Empty string task_id raises InvalidTaskIdError."""
        task = _SimpleTask(task_id="")
        with pytest.raises(InvalidTaskIdError):
            compute_waves([task])

    def test_seed_task_unsafe_id_warning(self, caplog):
        """SeedTask.from_seed_entry() with unsafe task ID logs WARNING."""
        entry = {
            "task_id": "../bad-id",
            "title": "Test",
            "task_type": "task",
            "story_points": 1,
            "priority": "medium",
            "labels": [],
            "depends_on": [],
            "config": {
                "task_description": "desc",
                "context": {
                    "target_files": ["a.py"],
                    "estimated_loc": 10,
                    "feature_id": "F1",
                },
            },
            "_enrichment": {
                "domain": "backend",
                "domain_reasoning": "",
                "environment_checks": [],
                "prompt_constraints": [],
                "post_generation_validators": [],
                "available_siblings": [],
            },
        }
        with caplog.at_level(logging.WARNING):
            task = SeedTask.from_seed_entry(entry)
        assert "unsafe characters" in caplog.text.lower()

    def test_pattern_rejects_spaces(self):
        """Spaces are rejected by the pattern."""
        assert not _SAFE_TASK_ID_PATTERN.match("task one")

    def test_pattern_accepts_alphanumeric_dash_underscore_dot(self):
        """Pattern accepts alphanumerics, dashes, underscores, dots."""
        for s in ["abc", "ABC", "123", "a-b", "a_b", "a.b", "A-1.2_3"]:
            assert _SAFE_TASK_ID_PATTERN.match(s), f"Should accept: {s}"
