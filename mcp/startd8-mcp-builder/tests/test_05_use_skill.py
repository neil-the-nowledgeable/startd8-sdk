"""Phase 2.3: `startd8_use_skill` tool tests.

Covers:
- T2.3.1 Generate with valid skill and API key (unit, mocked Anthropic)
- T2.3.2 Handle missing API key gracefully
- T2.3.3 Handle missing Anthropic SDK gracefully
- T2.3.4 Remove YAML frontmatter from instructions
- T2.3.5 Use correct Claude model
- T2.3.6 Respect max_tokens parameter
- T2.3.7 Format response with metadata
- T2.3.8 Handle API errors (rate limit, invalid key)
- T2.3.9 Handle skill not found

Integration tests that hit the real Anthropic API are expected to live
in a higher-level integration suite and are not covered here.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import os
import pytest

import startd8_mcp
from startd8_mcp import UseSkillInput, ResponseFormat


@pytest.mark.asyncio
async def test_use_skill_success_mocked_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
    mock_anthropic_api,
) -> None:
    """T2.3.1/T2.3.5/T2.3.6/T2.3.7 - Successful generation with mocked Anthropic.

    Verifies that:
    - The tool finds the skill
    - The Anthropic client is called with the correct model and max_tokens
    - The response is formatted with metadata header and token info
    """

    # Isolate discovery to temp skills directory
    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # Ensure character limit is large enough not to truncate here
    monkeypatch.setattr(startd8_mcp, "CHARACTER_LIMIT", 10_000)

    input_data = UseSkillInput(
        skill_name="skill-test-1",
        prompt="Test prompt",
        model="claude-test-model",
        max_tokens=1234,
    )

    result = await startd8_mcp.startd8_use_skill(input_data)

    # Response formatting
    assert result.startswith("# Response from skill-test-1")
    assert "**Model:** claude-test-model" in result
    assert "**Tokens:" in result
    assert "fake-response" in result  # from mock Anthropic fixture

    # Inspect the last_request captured by mock_anthropic_api
    last_request: dict[str, Any] = mock_anthropic_api["last_request"]
    assert last_request["model"] == "claude-test-model"
    assert last_request["max_tokens"] == 1234
    assert last_request["messages"][0]["content"] == "Test prompt"


@pytest.mark.asyncio
async def test_missing_api_key(monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path) -> None:
    """T2.3.2 - Missing ANTHROPIC_API_KEY returns a helpful error string."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # Ensure API key is not set
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    input_data = UseSkillInput(skill_name="skill-test-1", prompt="Hello")
    result = await startd8_mcp.startd8_use_skill(input_data)

    assert "Error: ANTHROPIC_API_KEY environment variable not set" in result


@pytest.mark.asyncio
async def test_missing_anthropic_sdk(monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path) -> None:
    """T2.3.3 - When Anthropic SDK is not importable, a clear error is returned."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    # Force ImportError specifically for anthropic
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any):  # type: ignore[override]
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    input_data = UseSkillInput(skill_name="skill-test-1", prompt="Hello")
    result = await startd8_mcp.startd8_use_skill(input_data)

    assert "Error: Anthropic Python SDK not installed" in result


@pytest.mark.asyncio
async def test_yaml_frontmatter_removed_from_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_anthropic_api,
) -> None:
    """T2.3.4 - YAML frontmatter is stripped before being used as system prompt."""

    # Create a skill with YAML frontmatter followed by instructions
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "frontmatter-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: frontmatter-skill
description: Skill with YAML frontmatter
---
# Real Instructions

These should be used as the system prompt.
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(skills_root))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    input_data = UseSkillInput(skill_name="frontmatter-skill", prompt="Hi")
    await startd8_mcp.startd8_use_skill(input_data)

    last_request: dict[str, Any] = mock_anthropic_api["last_request"]
    system_prompt: str = last_request["system"]

    # Ensure YAML delimiters are gone and only the body remains
    assert "---" not in system_prompt
    assert "Real Instructions" in system_prompt


@pytest.mark.asyncio
async def test_api_error_handling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T2.3.8 - API errors are caught and turned into actionable messages."""

    # Minimal skill setup
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "error-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# Error Skill", encoding="utf-8")

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(skills_root))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _ErrorMessages:
        def create(self, **_: Any):
            raise RuntimeError("rate limit exceeded")

    class _ErrorClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            """Fake client constructor ignoring args."""

            self.messages = _ErrorMessages()

    class _ErrorModule:
        Anthropic = _ErrorClient

    # Ensure importing anthropic gives our error-raising client
    import sys

    monkeypatch.setitem(sys.modules, "anthropic", _ErrorModule())

    input_data = UseSkillInput(skill_name="error-skill", prompt="Hi")
    result = await startd8_mcp.startd8_use_skill(input_data)

    assert "Error calling Claude API: rate limit exceeded" in result
    assert "Make sure your ANTHROPIC_API_KEY is valid" in result


@pytest.mark.asyncio
async def test_skill_not_found_returns_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T2.3.9 - Non-existent skill name returns a clear error message."""

    empty_dir = tmp_path / "no-skills"
    empty_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(empty_dir))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    input_data = UseSkillInput(skill_name="missing-skill", prompt="Hi")
    result = await startd8_mcp.startd8_use_skill(input_data)

    assert "Error: Skill 'missing-skill' not found" in result


@pytest.mark.asyncio
async def test_use_skill_success_json_mode(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
    mock_anthropic_api,
) -> None:
    """Test successful generation in JSON mode with full metrics."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])
    monkeypatch.setattr(startd8_mcp, "CHARACTER_LIMIT", 10_000)

    input_data = UseSkillInput(
        skill_name="skill-test-1",
        prompt="Test prompt",
        model="claude-test-model",
        max_tokens=1234,
        response_format=ResponseFormat.JSON,
    )

    result = await startd8_mcp.startd8_use_skill(input_data)

    # Parse JSON response
    data = json.loads(result)

    # Assert on structure
    assert data["skill_name"] == "skill-test-1"
    assert data["model"] == "claude-test-model"
    assert data["prompt"] == "Test prompt"
    assert data["output"] == "fake-response"
    assert data["response_format"] == "json"
    
    # Assert on usage metrics
    assert data["usage"]["input_tokens"] == 10
    assert data["usage"]["output_tokens"] == 20
    assert data["usage"]["total_tokens"] == 30
    
    # Assert on timing
    assert data["timing"]["latency_ms"] >= 0
    assert "started_at" in data["timing"]
    assert "completed_at" in data["timing"]
    
    # Assert on SDK info
    assert data["sdk"]["provider"] == "anthropic"
    assert data["error"] is None


@pytest.mark.asyncio
async def test_use_skill_success_markdown_mode_includes_metrics(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
    mock_anthropic_api,
) -> None:
    """Test Markdown mode includes metrics in header."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])
    monkeypatch.setattr(startd8_mcp, "CHARACTER_LIMIT", 10_000)

    input_data = UseSkillInput(
        skill_name="skill-test-1",
        prompt="Test prompt",
        model="claude-test-model",
        max_tokens=1234,
        response_format=ResponseFormat.MARKDOWN,
    )

    result = await startd8_mcp.startd8_use_skill(input_data)

    # Assert on markdown structure
    assert result.startswith("# Response from skill-test-1")
    assert "**Model:** claude-test-model" in result
    assert "**Tokens:** 10 in, 20 out (total 30)" in result
    assert "**Latency:** " in result
    assert "ms" in result
    assert "fake-response" in result
    assert "---" in result

