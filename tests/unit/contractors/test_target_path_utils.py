"""Recovers e0c3ec33's never-created module — the FR-1 directory-target belt."""

from __future__ import annotations

import pytest

from startd8.contractors.target_path_utils import (
    any_directory_targets,
    is_directory_target,
)

pytestmark = pytest.mark.unit


def test_trailing_slash_is_directory():
    assert is_directory_target("src/") is True
    assert is_directory_target("pkg/handlers/") is True


def test_concrete_files_are_not_directories():
    for f in ["src/main.go", "app/server.py", "adservice/Ad.java"]:
        assert is_directory_target(f) is False


def test_extensionless_real_files_not_flagged():
    # the conservative contract: Dockerfile/Makefile/README are files, never refused
    for f in ["Dockerfile", "Makefile", "README"]:
        assert is_directory_target(f) is False


def test_existing_dir_flagged(tmp_path):
    d = tmp_path / "a_dir"
    d.mkdir()
    assert is_directory_target(str(d)) is True
    f = tmp_path / "a_file.py"
    f.write_text("x")
    assert is_directory_target(str(f)) is False


def test_any_directory_targets():
    assert any_directory_targets(["src/main.go", "pkg/"]) is True
    assert any_directory_targets(["src/main.go", "app/server.py"]) is False
    assert any_directory_targets([]) is False


def test_empty_and_none_safe():
    assert is_directory_target("") is False
    assert is_directory_target("   ") is False
