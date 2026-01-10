"""Phase 1.2: Skill Discovery Tests.

Covers:
- T1.2.1 Discover skills in default directories
- T1.2.2 Discover skills via STARTD8_SKILL_PATH env var
- T1.2.3 Handle missing skill directories gracefully
- T1.2.4 Parse YAML frontmatter correctly
- T1.2.5 Handle malformed SKILL.md files
- T1.2.6 Fallback to directory name when YAML missing
- T1.2.7 Skip directories without SKILL.md
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import startd8_mcp
# test_skills_directory fixture is imported via conftest.py


def _skill_names(skills):
    return sorted(s["name"] for s in skills)


def test_default_directory_discovery(monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path) -> None:
    """T1.2.1 - Discover skills from (patched) default directories.

    We patch DEFAULT_SKILL_PATHS to only include the temporary
    test_skills_directory so that the test is deterministic and does not
    depend on the real user environment.
    """

    monkeypatch.setenv("STARTD8_SKILL_PATH", "")
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [test_skills_directory])

    skills = startd8_mcp._find_skills()
    names = _skill_names(skills)

    # skill-test-4 has malformed YAML and should be skipped by _parse_skill_file
    assert "skill-test-1" in names
    assert "skill-test-2" in names
    assert "skill-test-3" in names  # fallback name from directory
    assert "skill-test-4" not in names


def test_env_var_skill_path(monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path) -> None:
    """T1.2.2 - Discover skills via STARTD8_SKILL_PATH env var.

    Here we clear DEFAULT_SKILL_PATHS so that only the env var controls
    discovery.
    """

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    skills = startd8_mcp._find_skills()
    names = _skill_names(skills)

    assert set(names) == {"skill-test-1", "skill-test-2", "skill-test-3"}


def test_missing_skill_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T1.2.3 - Handle missing skill directories gracefully.

    Point both the env var and DEFAULT_SKILL_PATHS at paths that do not
    exist and verify that discovery returns an empty list rather than
    raising.
    """

    missing1 = tmp_path / "missing1"
    missing2 = tmp_path / "missing2"

    monkeypatch.setenv("STARTD8_SKILL_PATH", f"{missing1}:{missing2}")
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [missing1, missing2])

    skills = startd8_mcp._find_skills()
    assert skills == []


def test_yaml_parsing_valid_frontmatter(test_skills_directory: Path) -> None:
    """T1.2.4 - Parse YAML frontmatter correctly for valid SKILL.md files."""

    skill_file = test_skills_directory / "skill-test-1" / "SKILL.md"
    meta = startd8_mcp._parse_skill_file(skill_file)

    assert meta is not None
    assert meta["name"] == "skill-test-1"
    assert "First test skill" in meta["description"]
    assert meta["metadata"]["version"] == "1.0.0"


def test_malformed_skill_file_handled_gracefully(test_skills_directory: Path) -> None:
    """T1.2.5 - Malformed SKILL.md frontmatter should not crash discovery.

    _parse_skill_file returns None on error, which _find_skills is
    expected to treat as "skip this file".
    """

    malformed_file = test_skills_directory / "skill-test-4" / "SKILL.md"
    meta = startd8_mcp._parse_skill_file(malformed_file)
    assert meta is None


def test_fallback_to_directory_name_when_yaml_missing(test_skills_directory: Path) -> None:
    """T1.2.6 - When YAML is missing, fall back to directory name."""

    skill_file = test_skills_directory / "skill-test-3" / "SKILL.md"
    meta = startd8_mcp._parse_skill_file(skill_file)

    assert meta is not None
    assert meta["name"] == "skill-test-3"
    assert meta["description"] == "Claude Skill"  # default description


def test_directories_without_skill_file_are_skipped(monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path) -> None:
    """T1.2.7 - Directories without SKILL.md are skipped by discovery."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    skills = startd8_mcp._find_skills()

    # Ensure that the directory "no-skill-file" did not produce a skill
    names = _skill_names(skills)
    assert "no-skill-file" not in names
