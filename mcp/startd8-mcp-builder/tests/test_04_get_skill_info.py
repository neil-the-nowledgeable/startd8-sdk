"""Phase 2.2: `startd8_get_skill_info` tool tests.

Covers:
- T2.2.1 Get skill info by exact name
- T2.2.2 Get skill info by directory name
- T2.2.3 Get skill info by partial name (fuzzy match)
- T2.2.4 Handle non-existent skill gracefully
- T2.2.5 Return full SKILL.md content
- T2.2.6 Format in Markdown correctly
- T2.2.7 Format in JSON correctly
- T2.2.8 Handle very large SKILL.md files (truncation)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import startd8_mcp
from startd8_mcp import GetSkillInput, ResponseFormat


@pytest.mark.asyncio
async def test_get_skill_by_exact_name_markdown(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
) -> None:
    """T2.2.1/T2.2.5/T2.2.6 - Exact name, Markdown wrapper + body content."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    result = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="skill-test-1", response_format=ResponseFormat.MARKDOWN)
    )

    # Wrapper header
    assert result.startswith("# Skill: skill-test-1")
    assert "**Description:** First test skill" in result
    assert "**Location:** `" in result

    # Embedded SKILL.md content from fixture
    assert "# Body for skill-test-1" in result


@pytest.mark.asyncio
async def test_get_skill_by_directory_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T2.2.2 - Resolve a skill by directory name when frontmatter name differs."""

    base = tmp_path / "skills-root"
    skill_dir = base / "dir-alias"
    skill_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: pretty-skill-name
description: Skill whose directory name differs from its declared name
metadata:
  version: "1.0.0"
---
# Directory name test
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(base))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    result = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="dir-alias", response_format=ResponseFormat.MARKDOWN)
    )

    # We expect the frontmatter name to be used in the wrapper
    assert result.startswith("# Skill: pretty-skill-name")
    assert "**Location:** `" in result and "dir-alias" in result
    assert "# Directory name test" in result


@pytest.mark.asyncio
async def test_fuzzy_skill_matching(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
) -> None:
    """T2.2.3 - Partial name (substring) should resolve to a skill.

    We choose a substring that uniquely matches skill-test-2.
    """

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    result = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="test-2", response_format=ResponseFormat.MARKDOWN)
    )

    assert result.startswith("# Skill: skill-test-2")


@pytest.mark.asyncio
async def test_skill_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T2.2.4 - Non-existent skill yields helpful error listing available skills."""

    empty_dir = tmp_path / "no-skills"
    empty_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(empty_dir))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    result = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="does-not-exist", response_format=ResponseFormat.MARKDOWN)
    )

    assert "Error: Skill 'does-not-exist' not found." in result
    assert "Available skills:" in result


@pytest.mark.asyncio
async def test_get_skill_info_json_format(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
) -> None:
    """T2.2.7 - JSON format returns structured metadata + instructions."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    raw = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="skill-test-1", response_format=ResponseFormat.JSON)
    )

    data = json.loads(raw)
    assert data["name"] == "skill-test-1"
    assert "First test skill" in data["description"]
    assert isinstance(data["metadata"], dict)
    assert isinstance(data["directory"], str)
    assert "# Body for skill-test-1" in data["instructions"]


@pytest.mark.asyncio
async def test_large_skill_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    """T2.2.8 - Very large SKILL.md content is truncated at CHARACTER_LIMIT."""

    # Fake skill metadata
    fake_skill = {
        "name": "huge-skill",
        "description": "huge skill for truncation test",
        "metadata": {},
        "directory": "/fake/huge-skill",
        "file_path": "/fake/huge-skill/SKILL.md",
    }

    # Patch helper functions and character limit
    monkeypatch.setattr(startd8_mcp, "_find_skill_by_name", lambda name: fake_skill)
    monkeypatch.setattr(startd8_mcp, "_load_skill_instructions", lambda skill: "X" * 5000)
    monkeypatch.setattr(startd8_mcp, "CHARACTER_LIMIT", 1000)

    result = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="huge-skill", response_format=ResponseFormat.MARKDOWN)
    )

    # We should see the truncation warning appended
    assert "⚠️ Response truncated at 1000 characters." in result

