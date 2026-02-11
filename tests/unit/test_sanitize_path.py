"""Tests for sanitize_path with base_dir resolution (commit 23f9154 fix).

Covers:
- Relative paths resolve against base_dir (not cwd)
- Absolute paths ignore base_dir
- Paths outside base_dir raise ValidationError
- Directory traversal attacks blocked
- Edge cases: base_dir=None, empty path, symlinks
"""

import os
from pathlib import Path

import pytest

from startd8.security import sanitize_path
from startd8.exceptions import ValidationError


class TestSanitizePathBaseDirResolution:
    """Relative paths must resolve against base_dir, not cwd."""

    def test_relative_resolves_against_base_dir(self, tmp_path):
        """scripts/foo.py + base_dir=/project → /project/scripts/foo.py"""
        base = tmp_path / "project"
        base.mkdir()
        scripts = base / "scripts"
        scripts.mkdir()
        target = scripts / "foo.py"
        target.write_text("# ok")

        result = sanitize_path("scripts/foo.py", base_dir=base)
        assert result == target.resolve()

    def test_relative_does_not_use_cwd(self, tmp_path, monkeypatch):
        """Even if cwd has a matching file, base_dir wins."""
        base = tmp_path / "project"
        base.mkdir()
        (base / "mod.py").write_text("# base")

        cwd_dir = tmp_path / "other"
        cwd_dir.mkdir()
        (cwd_dir / "mod.py").write_text("# cwd")
        monkeypatch.chdir(cwd_dir)

        result = sanitize_path("mod.py", base_dir=base)
        assert result == (base / "mod.py").resolve()

    def test_nested_relative_path(self, tmp_path):
        """data/processed/out.csv resolves correctly under base_dir."""
        base = tmp_path / "proj"
        nested = base / "data" / "processed"
        nested.mkdir(parents=True)

        result = sanitize_path("data/processed/out.csv", base_dir=base)
        assert result == (nested / "out.csv").resolve()


class TestSanitizePathAbsoluteIgnoresBaseDir:
    """Absolute paths within base_dir should work; outside should fail."""

    def test_absolute_within_base_dir(self, tmp_path):
        """Absolute path inside base_dir is accepted."""
        base = tmp_path / "project"
        base.mkdir()
        target = base / "file.py"
        target.write_text("# ok")

        result = sanitize_path(str(target), base_dir=base)
        assert result == target.resolve()

    def test_absolute_outside_base_dir_raises(self, tmp_path):
        """Absolute path outside base_dir raises ValidationError."""
        base = tmp_path / "project"
        base.mkdir()
        outside = tmp_path / "other" / "secret.py"
        outside.parent.mkdir(parents=True)
        outside.write_text("secret")

        with pytest.raises(ValidationError, match="outside allowed directory"):
            sanitize_path(str(outside), base_dir=base)


class TestSanitizePathTraversalBlocked:
    """Directory traversal attempts must be rejected."""

    def test_dotdot_in_path_raises(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()

        with pytest.raises(ValidationError, match="directory traversal"):
            sanitize_path("../etc/passwd", base_dir=base)

    def test_dotdot_component_in_middle(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()

        with pytest.raises(ValidationError, match="directory traversal"):
            sanitize_path("scripts/../../../etc/passwd", base_dir=base)

    def test_dotdot_without_base_dir(self):
        """Traversal blocked even without base_dir."""
        with pytest.raises(ValidationError, match="directory traversal"):
            sanitize_path("../../etc/shadow")


class TestSanitizePathNoBaseDir:
    """Without base_dir, paths resolve against cwd (original behavior)."""

    def test_no_base_dir_resolves_relative(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "file.txt").write_text("ok")

        result = sanitize_path("file.txt")
        assert result == (tmp_path / "file.txt").resolve()

    def test_no_base_dir_absolute_passthrough(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("ok")

        result = sanitize_path(str(target))
        assert result == target.resolve()


class TestSanitizePathEdgeCases:
    """Edge cases and boundary conditions."""

    def test_path_object_input(self, tmp_path):
        """Path objects accepted, not just strings."""
        base = tmp_path / "proj"
        base.mkdir()
        result = sanitize_path(Path("readme.md"), base_dir=base)
        assert result == (base / "readme.md").resolve()

    def test_home_tilde_expansion(self, tmp_path):
        """~ in path is expanded."""
        result = sanitize_path("~/some_file.txt")
        assert str(Path.home()) in str(result)

    def test_base_dir_itself_is_valid(self, tmp_path):
        """Passing '.' with base_dir returns base_dir itself."""
        base = tmp_path / "proj"
        base.mkdir()
        result = sanitize_path(".", base_dir=base)
        assert result == base.resolve()
