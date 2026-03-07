"""Tests for copy_detection module (Phase 0: Identical-Copy File Duplication).

Requirements: REQ-MP-1000, REQ-MP-1001, REQ-MP-1002.
"""

import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from startd8.contractors.copy_detection import (
    CopySource,
    detect_copy_task,
    validate_copy_path,
)


# ---------------------------------------------------------------------------
# Lightweight stub — avoids importing the full FeatureSpec for unit tests.
# ---------------------------------------------------------------------------

@dataclass
class _FakeFeature:
    id: str = "feat-2"
    name: str = "Copy Feature"
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    copy_source_task_id: Optional[str] = None
    copy_source_file: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class _FakePredecessor:
    id: str = "feat-1"
    target_files: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# detect_copy_task tests
# ---------------------------------------------------------------------------

class TestDetectCopyTask:

    def test_detect_identical_copy(self):
        """Description with 'identical copy' + 1 dependency -> CopySource."""
        feat = _FakeFeature(
            description="This is an identical copy of the auth module.",
            dependencies=["feat-1"],
        )
        result = detect_copy_task(feat)
        assert result is not None
        assert isinstance(result, CopySource)
        assert result.predecessor_id == "feat-1"

    def test_detect_exact_copy(self):
        """Description with 'exact copy' + 1 dependency -> CopySource."""
        feat = _FakeFeature(
            description="Create an exact copy of the config parser.",
            dependencies=["feat-1"],
        )
        result = detect_copy_task(feat)
        assert result is not None
        assert result.predecessor_id == "feat-1"

    def test_reject_modified_copy(self):
        """'identical copy' + 'with changes' -> None (modification signal)."""
        feat = _FakeFeature(
            description="Create an identical copy of the parser with changes for v2.",
            dependencies=["feat-1"],
        )
        result = detect_copy_task(feat)
        assert result is None

    def test_reject_adapted_copy(self):
        """'exact copy' + 'adapted for' -> None."""
        feat = _FakeFeature(
            description="An exact copy adapted for the new API.",
            dependencies=["feat-1"],
        )
        result = detect_copy_task(feat)
        assert result is None

    def test_reject_no_dependency(self):
        """'identical copy' but no dependencies -> None."""
        feat = _FakeFeature(
            description="This is an identical copy of the module.",
            dependencies=[],
        )
        result = detect_copy_task(feat)
        assert result is None

    def test_reject_multiple_dependencies(self):
        """'identical copy' but 2 dependencies -> None."""
        feat = _FakeFeature(
            description="This is an identical copy of the module.",
            dependencies=["feat-1", "feat-3"],
        )
        result = detect_copy_task(feat)
        assert result is None

    def test_reject_no_signal(self):
        """Normal description without copy signals -> None."""
        feat = _FakeFeature(
            description="Implement the authentication module with OAuth2.",
            dependencies=["feat-1"],
        )
        result = detect_copy_task(feat)
        assert result is None

    def test_explicit_copy_source_task_id(self):
        """When copy_source_task_id is set, trust it regardless of description."""
        feat = _FakeFeature(
            description="Some unrelated description.",
            dependencies=[],
            copy_source_task_id="feat-1",
            copy_source_file="src/auth.py",
        )
        result = detect_copy_task(feat)
        assert result is not None
        assert result.predecessor_id == "feat-1"
        assert result.source_file == "src/auth.py"

    def test_fallback_inference_single_target(self):
        """copy_source_file not set, predecessor has 1 target -> inferred."""
        feat = _FakeFeature(
            description="This is an identical copy of the parser.",
            dependencies=["feat-1"],
            copy_source_file=None,
        )
        predecessor = _FakePredecessor(target_files=["src/parser.py"])
        result = detect_copy_task(feat, predecessor=predecessor)
        assert result is not None
        assert result.source_file == "src/parser.py"

    def test_fallback_inference_multiple_targets(self):
        """Predecessor has multiple targets -> source_file stays empty."""
        feat = _FakeFeature(
            description="This is an identical copy of the parser.",
            dependencies=["feat-1"],
            copy_source_file=None,
        )
        predecessor = _FakePredecessor(
            target_files=["src/parser.py", "src/lexer.py"]
        )
        result = detect_copy_task(feat, predecessor=predecessor)
        assert result is not None
        # Cannot infer — source_file falls back to empty string.
        assert result.source_file == ""

    def test_fallback_inference_with_explicit_id(self):
        """copy_source_task_id set, no copy_source_file, predecessor has 1 target."""
        feat = _FakeFeature(
            copy_source_task_id="feat-1",
            copy_source_file=None,
        )
        predecessor = _FakePredecessor(target_files=["src/utils.py"])
        result = detect_copy_task(feat, predecessor=predecessor)
        assert result is not None
        assert result.predecessor_id == "feat-1"
        assert result.source_file == "src/utils.py"


# ---------------------------------------------------------------------------
# validate_copy_path tests
# ---------------------------------------------------------------------------

class TestValidateCopyPath:

    def test_valid_relative_path(self, tmp_path):
        """Normal relative path -> resolved Path returned."""
        result = validate_copy_path("src/module.py", str(tmp_path))
        expected = (tmp_path / "src" / "module.py").resolve()
        assert result == expected

    def test_path_traversal_blocked(self, tmp_path):
        """../../etc/passwd -> ValueError."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_copy_path("../../etc/passwd", str(tmp_path))

    def test_path_prefix_collision(self, tmp_path):
        """/workspace2/file.py with root /workspace -> ValueError."""
        # Create two sibling directories to test prefix collision.
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # An absolute path outside the workspace but sharing a prefix.
        outside = str(tmp_path / "workspace2" / "file.py")
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_copy_path(outside, str(workspace))

    def test_nested_valid_path(self, tmp_path):
        """Deeply nested relative path within workspace is valid."""
        result = validate_copy_path("a/b/c/d.py", str(tmp_path))
        expected = (tmp_path / "a" / "b" / "c" / "d.py").resolve()
        assert result == expected
