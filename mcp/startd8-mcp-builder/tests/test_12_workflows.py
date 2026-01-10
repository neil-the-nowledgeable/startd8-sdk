"""Phase 7.1: Real-World Workflow Tests.

End-to-end workflows composed of multiple tools, using in-process calls
and mocked Anthropic for deterministic behavior.

Covers:
- T7.1.1 Discover → Info → Use workflow
- T7.1.2 Multiple skill usage in sequence (simplified)
- T7.1.3 Skill not found → correction workflow
- T7.1.4 API key missing → setup workflow
- T7.1.5 Complex prompt with skill
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import startd8_mcp
from startd8_mcp import (
    ListSkillsInput,
    GetSkillInput,
    UseSkillInput,
    ResponseFormat,
)


@pytest.mark.asyncio
async def test_full_skill_usage_workflow(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
    mock_anthropic_api,
) -> None:
    """T7.1.1/T7.1.5 - Discover → Info → Use with a complex prompt."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # 1. Discover skills
    skills_md = await startd8_mcp.startd8_list_skills(ListSkillsInput())
    assert "skill-test-1" in skills_md

    # 2. Get specific skill info
    info_md = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="skill-test-1", response_format=ResponseFormat.MARKDOWN)
    )
    assert "# Skill: skill-test-1" in info_md
    assert "# Body for skill-test-1" in info_md

    # 3. Use that skill with a more complex prompt
    complex_prompt = """You are testing the Startd8 MCP server.

Please summarize the key responsibilities of this test skill and then
propose three example usage scenarios, each on its own line.
"""

    response = await startd8_mcp.startd8_use_skill(
        UseSkillInput(skill_name="skill-test-1", prompt=complex_prompt)
    )

    assert response.startswith("# Response from skill-test-1")

    # Ensure our mock received the complex prompt
    last_request = mock_anthropic_api["last_request"]
    assert complex_prompt.strip() == last_request["messages"][0]["content"]


@pytest.mark.asyncio
async def test_multiple_skill_usage_sequence(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
    mock_anthropic_api,
) -> None:
    """T7.1.2 - Use two different skills in sequence.

    We reuse the same directory for simplicity but treat two names
    separately to validate sequential calls don't interfere.
    """

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # First call
    resp1 = await startd8_mcp.startd8_use_skill(
        UseSkillInput(skill_name="skill-test-1", prompt="First run")
    )
    assert "Response from skill-test-1" in resp1

    # Second call with another skill from the same fixture set
    resp2 = await startd8_mcp.startd8_use_skill(
        UseSkillInput(skill_name="skill-test-2", prompt="Second run")
    )
    assert "Response from skill-test-2" in resp2


@pytest.mark.asyncio
async def test_skill_correction_workflow(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
) -> None:
    """T7.1.3 - Skill not found leads to correction using suggestions."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # 1. Try to get non-existent skill
    wrong_name = "skill-tset-1"  # typo
    error_msg = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name=wrong_name, response_format=ResponseFormat.MARKDOWN)
    )

    assert "Error: Skill" in error_msg
    assert "Available skills:" in error_msg
    assert "skill-test-1" in error_msg  # suggestion list

    # 2. Use correct skill name
    info_md = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="skill-test-1", response_format=ResponseFormat.MARKDOWN)
    )
    assert "# Skill: skill-test-1" in info_md


@pytest.mark.asyncio
async def test_missing_api_key_setup_workflow(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
) -> None:
    """T7.1.4 - API key missing leads to clear setup instructions."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # Ensure the key is absent
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    msg = await startd8_mcp.startd8_use_skill(
        UseSkillInput(skill_name="skill-test-1", prompt="hi")
    )

    assert "Error: ANTHROPIC_API_KEY environment variable not set" in msg


@pytest.mark.asyncio
async def test_full_workflow_with_json_output(
    monkeypatch: pytest.MonkeyPatch,
    test_skills_directory: Path,
    mock_anthropic_api,
) -> None:
    """Test end-to-end workflow with JSON output for metrics."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    # 1. Discover skills
    skills_md = await startd8_mcp.startd8_list_skills(ListSkillsInput())
    assert "skill-test-1" in skills_md

    # 2. Get skill info
    info_md = await startd8_mcp.startd8_get_skill_info(
        GetSkillInput(skill_name="skill-test-1", response_format=ResponseFormat.MARKDOWN)
    )
    assert "# Skill: skill-test-1" in info_md

    # 3. Use skill in JSON mode to capture metrics
    complex_prompt = """Summarize the key responsibilities and provide three usage scenarios."""

    response_json_str = await startd8_mcp.startd8_use_skill(
        UseSkillInput(
            skill_name="skill-test-1",
            prompt=complex_prompt,
            response_format=ResponseFormat.JSON,
        )
    )

    # Parse and validate JSON structure
    data = json.loads(response_json_str)
    
    # Validate all required fields
    assert data["skill_name"] == "skill-test-1"
    assert data["prompt"] == complex_prompt
    assert data["output"] == "fake-response"
    assert data["response_format"] == "json"
    assert "usage" in data
    assert "input_tokens" in data["usage"]
    assert "output_tokens" in data["usage"]
    assert "total_tokens" in data["usage"]
    assert "timing" in data
    assert "started_at" in data["timing"]
    assert "completed_at" in data["timing"]
    assert "latency_ms" in data["timing"]
    assert data["sdk"]["provider"] == "anthropic"
    assert data["error"] is None

