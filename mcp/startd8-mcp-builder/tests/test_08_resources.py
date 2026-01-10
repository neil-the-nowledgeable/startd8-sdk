"""Phase 3.2: MCP Resource Tests.

Covers:
- T3.2.1 `skill://{name}` resource registered (function exists)
- T3.2.2 Resource returns skill content
- T3.2.3 Resource handles missing skills gracefully
- T3.2.4 Resource URI behavior (basic)
"""

from __future__ import annotations

from pathlib import Path

import pytest

import startd8_mcp


@pytest.mark.asyncio
async def test_skill_resource_returns_instructions(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
) -> None:
    """T3.2.2 - `skill://{name}` resource returns SKILL.md content."""

    # Ensure we can discover the test skills
    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    assert hasattr(startd8_mcp, "get_skill_resource"), "Resource function must exist"

    content = await startd8_mcp.get_skill_resource("skill-test-1")

    # We should get the body of SKILL.md, not the wrapper used by tools
    assert "# Body for skill-test-1" in content
    assert not content.startswith("# Skill: ")


@pytest.mark.asyncio
async def test_missing_skill_resource(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T3.2.3 - Missing skill name returns an error string, not an exception."""

    empty_dir = tmp_path / "no-skills"
    empty_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(empty_dir))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    msg = await startd8_mcp.get_skill_resource("does-not-exist")
    assert "Error: Skill 'does-not-exist' not found" in msg


def test_resource_docstring_mentions_uri_template() -> None:
    """T3.2.4 - Resource docstring documents the URI template format."""

    doc = (startd8_mcp.get_skill_resource.__doc__ or "").lower()
    assert "skill://" in doc
    assert "uri" in doc or "resource" in doc

