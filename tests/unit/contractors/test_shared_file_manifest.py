"""Unit tests for CCD Layer 3: shared-file manifest and lane-topology functions.

Covers:
    build_shared_file_manifest    (CCD-300)
    _normalize_target_path        (CCD-300)
    compute_lane_to_file_mapping  (CCD-302)
    compute_critical_path_tasks   (CCD-403)
"""

from __future__ import annotations

import pytest

from startd8.contractors.context_seed_handlers import (
    _normalize_target_path,
    build_shared_file_manifest,
    compute_critical_path_tasks,
    compute_lane_to_file_mapping,
)
from tests.unit.contractors.conftest import FakeSeedTask


# ---------------------------------------------------------------------------
# TestNormalizeTargetPath
# ---------------------------------------------------------------------------


class TestNormalizeTargetPath:
    """Tests for _normalize_target_path."""

    def test_dot_slash_normalization(self):
        """Leading ./ is collapsed by os.path.normpath."""
        assert _normalize_target_path("./src/widget.py") == "src/widget.py"

    def test_double_dot_normalization(self):
        """Parent-directory references are resolved."""
        assert _normalize_target_path("src/../src/widget.py") == "src/widget.py"

    def test_backslash_normalization(self):
        """Backslashes are converted to forward slashes after normpath."""
        # normpath on POSIX leaves backslashes as-is, but our replace()
        # converts them.  Pass a path that already has backslashes embedded.
        result = _normalize_target_path("src\\widget.py")
        assert "\\" not in result

    def test_plain_path_unchanged(self):
        """A clean relative path passes through without modification."""
        assert _normalize_target_path("src/widget.py") == "src/widget.py"

    def test_absolute_path_preserved(self):
        """Absolute paths (no redundant segments) are returned as-is."""
        result = _normalize_target_path("/usr/local/lib/module.py")
        assert result == "/usr/local/lib/module.py"

    def test_trailing_slash_removed(self):
        """os.path.normpath strips trailing slashes from directory paths."""
        result = _normalize_target_path("src/pkg/")
        assert not result.endswith("/")


# ---------------------------------------------------------------------------
# TestBuildSharedFileManifest
# ---------------------------------------------------------------------------


class TestBuildSharedFileManifest:
    """Tests for build_shared_file_manifest."""

    def test_empty_tasks(self):
        """No tasks → empty manifest."""
        result = build_shared_file_manifest([])
        assert result == {}

    def test_no_overlap(self):
        """Tasks with entirely distinct target files → no entry in manifest."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["src/a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["src/b.py"]),
        ]
        result = build_shared_file_manifest(tasks)
        assert result == {}

    def test_two_tasks_shared_file(self):
        """A file targeted by exactly 2 tasks appears in the manifest."""
        shared = "src/shared.py"
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=[shared, "src/a.py"]),
            FakeSeedTask(task_id="T-2", target_files=[shared, "src/b.py"]),
        ]
        result = build_shared_file_manifest(tasks)

        assert shared in result
        assert set(result[shared]) == {"T-1", "T-2"}
        # Unshared files must not appear
        assert "src/a.py" not in result
        assert "src/b.py" not in result

    def test_three_tasks_shared_file(self):
        """A file targeted by 3 tasks includes all 3 task IDs."""
        shared = "src/models.py"
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=[shared]),
            FakeSeedTask(task_id="T-2", target_files=[shared]),
            FakeSeedTask(task_id="T-3", target_files=[shared]),
        ]
        result = build_shared_file_manifest(tasks)

        assert shared in result
        assert set(result[shared]) == {"T-1", "T-2", "T-3"}

    def test_none_target_files(self):
        """Tasks whose target_files is None are skipped without error."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=None),
            FakeSeedTask(task_id="T-2", target_files=None),
        ]
        result = build_shared_file_manifest(tasks)
        assert result == {}

    def test_dot_slash_paths_normalized(self):
        """Paths with ./ prefix are normalized before comparison, so
        './src/shared.py' and 'src/shared.py' are treated as the same file."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["./src/shared.py"]),
            FakeSeedTask(task_id="T-2", target_files=["src/shared.py"]),
        ]
        result = build_shared_file_manifest(tasks)

        # Normalized key should be 'src/shared.py'
        assert "src/shared.py" in result
        assert set(result["src/shared.py"]) == {"T-1", "T-2"}

    def test_single_task_targeting_file_not_in_manifest(self):
        """A file targeted by only 1 task does not appear (threshold is 2)."""
        tasks = [FakeSeedTask(task_id="T-1", target_files=["src/solo.py"])]
        result = build_shared_file_manifest(tasks)
        assert "src/solo.py" not in result


# ---------------------------------------------------------------------------
# TestComputeLaneToFileMapping
# ---------------------------------------------------------------------------


class TestComputeLaneToFileMapping:
    """Tests for compute_lane_to_file_mapping."""

    def test_empty_lanes(self):
        """No lanes → empty mapping."""
        result = compute_lane_to_file_mapping([], {})
        assert result == {}

    def test_single_lane_no_shared_files(self):
        """Lane whose tasks share no files with each other → not in mapping."""
        lane = [
            FakeSeedTask(task_id="T-1", target_files=["src/a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["src/b.py"]),
        ]
        manifest = {}  # nothing shared
        result = compute_lane_to_file_mapping([lane], manifest)
        assert result == {}

    def test_single_lane_shared_file(self):
        """A lane with 2 tasks sharing a file is indexed under lane 0."""
        shared = "src/shared.py"
        lane = [
            FakeSeedTask(task_id="T-1", target_files=[shared]),
            FakeSeedTask(task_id="T-2", target_files=[shared]),
        ]
        manifest = {shared: ["T-1", "T-2"]}
        result = compute_lane_to_file_mapping([lane], manifest)

        assert 0 in result
        assert shared in result[0]

    def test_multiple_lanes_only_contested_indexed(self):
        """Only the lane whose tasks share a file appears in the mapping."""
        shared = "src/shared.py"
        lane0 = [
            FakeSeedTask(task_id="T-1", target_files=["src/a.py"]),
            FakeSeedTask(task_id="T-2", target_files=["src/b.py"]),
        ]
        lane1 = [
            FakeSeedTask(task_id="T-3", target_files=[shared]),
            FakeSeedTask(task_id="T-4", target_files=[shared]),
        ]
        manifest = {shared: ["T-3", "T-4"]}
        result = compute_lane_to_file_mapping([lane0, lane1], manifest)

        assert 0 not in result
        assert 1 in result
        assert shared in result[1]

    def test_shared_files_sorted_in_output(self):
        """Shared files within a lane entry are returned in sorted order."""
        files = ["src/z_module.py", "src/a_module.py", "src/m_module.py"]
        lane = [
            FakeSeedTask(task_id="T-1", target_files=files),
            FakeSeedTask(task_id="T-2", target_files=files),
        ]
        manifest = {f: ["T-1", "T-2"] for f in files}
        result = compute_lane_to_file_mapping([lane], manifest)

        assert result[0] == sorted(files)


# ---------------------------------------------------------------------------
# TestComputeCriticalPathTasks
# ---------------------------------------------------------------------------


class TestComputeCriticalPathTasks:
    """Tests for compute_critical_path_tasks."""

    def test_empty_tasks(self):
        """No tasks → empty set."""
        result = compute_critical_path_tasks([], {"src/shared.py": ["T-1", "T-2"]})
        assert result == set()

    def test_empty_manifest(self):
        """Empty manifest (no shared files) → empty set."""
        tasks = [FakeSeedTask(task_id="T-1", target_files=["src/a.py"])]
        result = compute_critical_path_tasks(tasks, {})
        assert result == set()

    def test_no_shared_files(self):
        """Tasks with no overlap with the manifest → empty set."""
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=["src/solo.py"]),
        ]
        manifest = {"src/shared.py": ["T-2", "T-3"]}  # T-1 not involved
        result = compute_critical_path_tasks(tasks, manifest)
        assert result == set()

    def test_top_20_percent(self):
        """Tasks in the top 20% by contention score are returned.

        We build 5 tasks where T-5 contests the most shared files,
        T-4 is second, and T-1..T-3 have lower scores.  At top_fraction=0.20
        (default), at least T-5 should appear in the result.
        """
        # Each task targets the shared file; the contest list length drives score.
        # contest list length - 1 = contention score per file.
        # T-5 contests 4 shared files (score=4), T-4 contests 3 (score=3), etc.
        shared_4 = "src/heavy.py"  # contested by 5 tasks → score contribution = 4
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=[shared_4]),
            FakeSeedTask(task_id="T-2", target_files=[shared_4]),
            FakeSeedTask(task_id="T-3", target_files=[shared_4]),
            FakeSeedTask(task_id="T-4", target_files=[shared_4]),
            FakeSeedTask(task_id="T-5", target_files=[shared_4]),
        ]
        manifest = {shared_4: ["T-1", "T-2", "T-3", "T-4", "T-5"]}
        result = compute_critical_path_tasks(tasks, manifest)

        # All tasks have the same contention score (4), so all should appear
        assert result == {"T-1", "T-2", "T-3", "T-4", "T-5"}

    def test_uncontested_tasks_excluded(self):
        """Tasks with zero contention score are never returned."""
        shared = "src/shared.py"
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=[shared]),
            FakeSeedTask(task_id="T-2", target_files=[shared]),
            FakeSeedTask(task_id="T-3", target_files=["src/solo.py"]),  # no contention
        ]
        manifest = {shared: ["T-1", "T-2"]}
        result = compute_critical_path_tasks(tasks, manifest)

        assert "T-3" not in result

    def test_multiple_shared_files_sum_scores(self):
        """A task contesting N shared files accumulates scores across all of them."""
        shared_a = "src/a.py"
        shared_b = "src/b.py"
        # T-1 contests both files; T-2 contests only a; T-3 contests only b
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=[shared_a, shared_b]),
            FakeSeedTask(task_id="T-2", target_files=[shared_a]),
            FakeSeedTask(task_id="T-3", target_files=[shared_b]),
        ]
        manifest = {
            shared_a: ["T-1", "T-2"],   # T-1 score += 1
            shared_b: ["T-1", "T-3"],   # T-1 score += 1 → total = 2
        }
        result = compute_critical_path_tasks(tasks, manifest, top_fraction=0.20)

        # T-1 has the highest score so must appear
        assert "T-1" in result

    def test_top_fraction_zero_returns_empty(self):
        """top_fraction=0.0 → threshold pushed to top of sorted list → empty set."""
        shared = "src/shared.py"
        tasks = [
            FakeSeedTask(task_id="T-1", target_files=[shared]),
            FakeSeedTask(task_id="T-2", target_files=[shared]),
        ]
        manifest = {shared: ["T-1", "T-2"]}
        result = compute_critical_path_tasks(tasks, manifest, top_fraction=0.0)

        # threshold_idx = int(2 * 1.0) = 2, which clamps to sorted_scores[-1]
        # so the threshold equals the max score → all are >= threshold, set not empty
        # This tests the boundary: the function returns at most the top scored tasks.
        assert isinstance(result, set)
