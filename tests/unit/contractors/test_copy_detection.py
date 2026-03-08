"""Tests for copy_detection module.

Requirements: REQ-MP-1000, REQ-MP-1001, REQ-MP-1002, REQ-MP-1003.
"""

import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from startd8.contractors.copy_detection import (
    CopyModifySource,
    CopySource,
    compress_reference,
    detect_copy_and_modify,
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


# ---------------------------------------------------------------------------
# detect_copy_and_modify tests (REQ-MP-1003)
# ---------------------------------------------------------------------------

class TestDetectCopyAndModify:

    def test_detect_copy_and_modify(self):
        """Both duplication + modification signals -> CopyModifySource."""
        feat = _FakeFeature(
            description="Create an identical copy of the parser with changes for v2.",
            dependencies=["feat-1"],
        )
        result = detect_copy_and_modify(feat)
        assert result is not None
        assert isinstance(result, CopyModifySource)
        assert result.predecessor_id == "feat-1"

    def test_detect_adapted_copy(self):
        """'exact copy' + 'adapted for' -> CopyModifySource."""
        feat = _FakeFeature(
            description="An exact copy adapted for the new API.",
            dependencies=["feat-1"],
        )
        result = detect_copy_and_modify(feat)
        assert result is not None
        assert result.predecessor_id == "feat-1"

    def test_detect_modified_to(self):
        """'mirror of' + 'modified to' -> CopyModifySource."""
        feat = _FakeFeature(
            description="A mirror of the auth module modified to use JWT.",
            dependencies=["feat-1"],
        )
        result = detect_copy_and_modify(feat)
        assert result is not None
        assert result.predecessor_id == "feat-1"

    def test_reject_pure_copy(self):
        """Only duplication signals (no modification) -> None."""
        feat = _FakeFeature(
            description="This is an identical copy of the module.",
            dependencies=["feat-1"],
        )
        result = detect_copy_and_modify(feat)
        assert result is None

    def test_reject_no_duplication_signal(self):
        """Only modification signals (no duplication) -> None."""
        feat = _FakeFeature(
            description="Implement the module with changes for v2.",
            dependencies=["feat-1"],
        )
        result = detect_copy_and_modify(feat)
        assert result is None

    def test_reject_no_dependencies(self):
        """Both signals but no dependencies -> None."""
        feat = _FakeFeature(
            description="An exact copy with changes.",
            dependencies=[],
        )
        result = detect_copy_and_modify(feat)
        assert result is None

    def test_reject_multiple_dependencies(self):
        """Both signals but 2 dependencies -> None."""
        feat = _FakeFeature(
            description="An exact copy with changes.",
            dependencies=["feat-1", "feat-3"],
        )
        result = detect_copy_and_modify(feat)
        assert result is None

    def test_reject_explicit_copy_source_task_id(self):
        """If copy_source_task_id is set, it's a pure file copy, not copy_and_modify."""
        feat = _FakeFeature(
            description="An exact copy with changes.",
            dependencies=["feat-1"],
            copy_source_task_id="feat-1",
        )
        result = detect_copy_and_modify(feat)
        assert result is None

    def test_infer_source_file_from_predecessor(self):
        """Source file inferred from predecessor's single target."""
        feat = _FakeFeature(
            description="An identical copy adapted for new config.",
            dependencies=["feat-1"],
        )
        predecessor = _FakePredecessor(target_files=["src/parser.py"])
        result = detect_copy_and_modify(feat, predecessor=predecessor)
        assert result is not None
        assert result.source_file == "src/parser.py"

    def test_no_infer_multiple_targets(self):
        """Multiple predecessor targets -> empty source_file."""
        feat = _FakeFeature(
            description="An identical copy adapted for new config.",
            dependencies=["feat-1"],
        )
        predecessor = _FakePredecessor(
            target_files=["src/a.py", "src/b.py"]
        )
        result = detect_copy_and_modify(feat, predecessor=predecessor)
        assert result is not None
        assert result.source_file == ""


# ---------------------------------------------------------------------------
# compress_reference tests (REQ-MP-1003)
# ---------------------------------------------------------------------------

class TestCompressReference:

    def test_short_code_unchanged(self):
        """Code within budget is returned as-is."""
        code = "x = 1\ny = 2\n"
        result = compress_reference(code, token_budget=100)
        assert result == code

    def test_strip_comments(self):
        """Comments are stripped when code exceeds budget."""
        # Build code that exceeds ~20 token budget (80 chars) with comments
        code = (
            "# This is a long comment that takes up space\n"
            "x = 1\n"
            "# Another long comment here\n"
            "y = 2\n"
        )
        result = compress_reference(code, token_budget=10)
        assert "# This is a long comment" not in result

    def test_strip_docstrings(self):
        """Docstrings are stripped when code exceeds budget."""
        code = (
            'def foo():\n'
            '    """This is a docstring that should be removed."""\n'
            '    return 42\n'
        )
        result = compress_reference(code, token_budget=15)
        assert "docstring that should be removed" not in result

    def test_truncation_marker(self):
        """Very large code gets truncated with a marker."""
        code = "x = 1\n" * 500  # ~3000 chars
        result = compress_reference(code, token_budget=10)  # 40 char budget
        assert "[TRUNCATED" in result

    def test_unparseable_code_survives(self):
        """Unparseable code doesn't crash — falls through gracefully."""
        code = "def foo(:\n" * 50  # Invalid syntax, repeated
        result = compress_reference(code, token_budget=10)
        # Should not raise — returns something truncated
        assert isinstance(result, str)
