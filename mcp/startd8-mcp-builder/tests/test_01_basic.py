"""Phase 1: Basic Functionality Tests for Startd8 MCP server.

Covers:
- T1.1.1 Python syntax validation (py_compile)
- T1.1.2 Import resolution
- T1.1.3 FastMCP server initialization
- T1.1.4 Pydantic models validate correctly
- T1.1.5 YAML parser (PyYAML) works
"""

from __future__ import annotations

import importlib
import py_compile
from pathlib import Path

import yaml
from pydantic import ValidationError

import startd8_mcp
from mcp.server.fastmcp import FastMCP
from startd8_mcp import (
    ListSkillsInput,
    GetSkillInput,
    UseSkillInput,
    CompareAgentsInput,
)


BASE_DIR = Path(__file__).resolve().parents[1]


def test_syntax_validation() -> None:
    """T1.1.1 - Verify Python syntax is valid via py_compile."""

    for rel_path in ("startd8_mcp.py", "test_server.py"):
        file_path = BASE_DIR / rel_path
        # doraise=True will raise a SyntaxError on invalid syntax
        py_compile.compile(str(file_path), doraise=True)


def test_imports() -> None:
    """T1.1.2 - Verify core modules import without errors."""

    module = importlib.import_module("startd8_mcp")
    assert module is startd8_mcp


def test_server_initialization() -> None:
    """T1.1.3 - Verify FastMCP server instance is created."""

    assert hasattr(startd8_mcp, "mcp"), "Module should define a global 'mcp' instance"
    mcp_instance = startd8_mcp.mcp
    assert isinstance(mcp_instance, FastMCP)


def test_pydantic_models_validate() -> None:
    """T1.1.4 - Ensure core Pydantic models accept valid inputs."""

    # ListSkillsInput: all defaults
    ListSkillsInput()

    # GetSkillInput: minimal valid
    GetSkillInput(skill_name="example-skill")

    # UseSkillInput: minimal valid
    UseSkillInput(skill_name="example-skill", prompt="Test prompt")

    # CompareAgentsInput: minimal valid
    CompareAgentsInput(prompt="Test prompt", agents=["agent-a", "agent-b"])


def test_pydantic_models_reject_invalid() -> None:
    """T1.1.4 (negative) - Ensure obvious invalid inputs are rejected."""

    # Empty skill name should fail for GetSkillInput
    try:
        GetSkillInput(skill_name=" ")
    except ValidationError:
        pass
    else:
        raise AssertionError("Empty skill_name should raise ValidationError")

    # Too few agents should fail for CompareAgentsInput
    try:
        CompareAgentsInput(prompt="hi", agents=["only-one"])
    except ValidationError:
        pass
    else:
        raise AssertionError("CompareAgentsInput with <2 agents should raise ValidationError")


def test_yaml_parser_works() -> None:
    """T1.1.5 - Basic sanity check that PyYAML frontmatter parsing works."""

    content = """---
name: test-skill
description: Test skill for YAML parsing
metadata:
  version: "1.0.0"
  author: Test User
  tags:
    - test
    - sample
---
# Body content is ignored for this test
"""

    # Simulate how frontmatter is extracted in startd8_mcp._parse_skill_file
    parts = content.split("---", 2)
    assert len(parts) >= 3

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "test-skill"
    assert frontmatter["metadata"]["version"] == "1.0.0"
