"""Phase 2.1: `startd8_list_skills` tool tests.

Covers:
- T2.1.1 List skills in Markdown format (default)
- T2.1.2 List skills in JSON format
- T2.1.3 List with include_details=True
- T2.1.4 List with include_details=False
- T2.1.5 Handle empty skill directories
- T2.1.6 Character limit truncation
- T2.1.7 Helpful message when no skills found
"""

from __future__ import annotations

import json
from typing import List, Dict, Any

import pytest

import startd8_mcp
from startd8_mcp import ListSkillsInput, ResponseFormat


@pytest.mark.asyncio
async def test_list_skills_markdown_default(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory,
) -> None:
    """T2.1.1 - List skills in Markdown format (default params)."""

    # Isolate discovery to the temporary skills directory
    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    result = await startd8_mcp.startd8_list_skills(ListSkillsInput())

    # Basic structure checks
    assert "# Available Claude Skills" in result
    assert "Found" in result and "skill(s)" in result

    # All three valid skills from the fixture should appear
    assert "skill-test-1" in result
    assert "skill-test-2" in result
    assert "skill-test-3" in result
    # Malformed skill-test-4 should not appear
    assert "skill-test-4" not in result


@pytest.mark.asyncio
async def test_list_skills_json_format(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory,
) -> None:
    """T2.1.2 - List skills in JSON format."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    result = await startd8_mcp.startd8_list_skills(
        ListSkillsInput(response_format=ResponseFormat.JSON, include_details=True)
    )

    data = json.loads(result)
    assert isinstance(data, dict)
    assert data["total"] == 3

    skills: List[Dict[str, Any]] = data["skills"]
    names = sorted(s["name"] for s in skills)
    assert names == ["skill-test-1", "skill-test-2", "skill-test-3"]

    # Ensure metadata and file paths are present
    for s in skills:
        assert "description" in s
        assert "metadata" in s
        assert "directory" in s
        assert "file_path" in s


@pytest.mark.asyncio
async def test_list_skills_include_details_markdown(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory,
) -> None:
    """T2.1.3/T2.1.4 - Verify include_details flag affects Markdown output."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # With details
    detailed = await startd8_mcp.startd8_list_skills(
        ListSkillsInput(response_format=ResponseFormat.MARKDOWN, include_details=True)
    )
    assert "**Description:**" in detailed
    assert "**Metadata:**" in detailed
    assert "**Location:**" in detailed

    # Without details
    concise = await startd8_mcp.startd8_list_skills(
        ListSkillsInput(response_format=ResponseFormat.MARKDOWN, include_details=False)
    )
    # We expect simple bullet lines for each skill instead of detailed sections
    assert "**Description:**" not in concise
    assert "**Metadata:**" not in concise
    assert "**Location:**" not in concise
    assert "- First test skill" in concise


@pytest.mark.asyncio
async def test_list_skills_empty_directories(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """T2.1.5/T2.1.7 - Handle empty skill directories with helpful message."""

    # Point discovery to an empty directory
    empty_dir = tmp_path / "empty-skills"
    empty_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(empty_dir))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    result = await startd8_mcp.startd8_list_skills(ListSkillsInput())

    assert "No Claude Skills found." in result
    # Ensure guidance on where to place skills is included
    assert "~/.startd8/skills/" in result
    assert "STARTD8_SKILL_PATH" in result


@pytest.mark.asyncio
async def test_character_limit_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    """T2.1.6 - When output exceeds CHARACTER_LIMIT, result is truncated.

    We mock `_find_skills` to return many fake skills and temporarily
    lower the CHARACTER_LIMIT so that truncation behavior is exercised
    without needing a huge fixture on disk.
    """

    # Build a large list of fake skills
    fake_skills = [
        {
            "name": f"skill-{i}",
            "description": "x" * 200,
            "metadata": {},
            "directory": f"/fake/skill-{i}",
            "file_path": f"/fake/skill-{i}/SKILL.md",
        }
        for i in range(50)
    ]

    async def _call_list(params: ListSkillsInput) -> str:
        # Helper to call the real function with our patches
        return await startd8_mcp.startd8_list_skills(params)

    # Patch _find_skills and set a small character limit
    monkeypatch.setattr(startd8_mcp, "_find_skills", lambda: fake_skills)
    monkeypatch.setattr(startd8_mcp, "CHARACTER_LIMIT", 1000)

    result = await _call_list(ListSkillsInput(response_format=ResponseFormat.MARKDOWN))

    # Confirm truncation notice is present
    assert "⚠️ Response truncated." in result
