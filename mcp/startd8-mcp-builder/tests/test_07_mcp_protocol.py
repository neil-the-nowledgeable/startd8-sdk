"""Phase 3.1: MCP Tool Registration / Protocol Shape Tests.

These tests validate that the expected tools are defined with the
correct names, async signatures, and Pydantic-based input schemas, in
line with the FastMCP patterns from the Python guide.

Covers (adapted to in-process inspection):
- T3.1.1 All 4 tools present in the server module
- T3.1.2 Tool names correct (`startd8_*`)
- T3.1.3 Tool annotations present and docstrings comprehensive
- T3.1.4 Tool descriptions/docstrings are non-trivial
- T3.1.5 Input schemas properly defined via Pydantic models
- T3.1.6 Tools are async coroutines suitable for MCP protocol
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

import startd8_mcp
from startd8_mcp import (
    ListSkillsInput,
    GetSkillInput,
    UseSkillInput,
    CompareAgentsInput,
)


EXPECTED_TOOL_NAMES = [
    "startd8_list_skills",
    "startd8_get_skill_info",
    "startd8_use_skill",
    "startd8_compare_agents",
]


def test_all_expected_tools_present() -> None:
    """T3.1.1/T3.1.2 - Verify the four expected tools exist and are callables."""

    for name in EXPECTED_TOOL_NAMES:
        assert hasattr(startd8_mcp, name), f"Missing tool function: {name}"
        func = getattr(startd8_mcp, name)
        assert callable(func), f"{name} should be callable"
        assert name.startswith("startd8_"), "Tool names should use startd8_ prefix"


def test_tools_are_async_coroutines() -> None:
    """T3.1.6 - All tools must be async coroutine functions for MCP usage."""

    for name in EXPECTED_TOOL_NAMES:
        func = getattr(startd8_mcp, name)
        assert inspect.iscoroutinefunction(func), f"{name} must be async def"


def test_tool_signatures_use_pydantic_models() -> None:
    """T3.1.5 - Ensure the main parameter type hints are Pydantic models."""

    expected_param_types = {
        "startd8_list_skills": ListSkillsInput,
        "startd8_get_skill_info": GetSkillInput,
        "startd8_use_skill": UseSkillInput,
        "startd8_compare_agents": CompareAgentsInput,
    }

    for name, expected_type in expected_param_types.items():
        func = getattr(startd8_mcp, name)
        sig = inspect.signature(func)

        # Each tool should take exactly one explicit parameter (the Pydantic model)
        params = list(sig.parameters.values())
        assert len(params) == 1, f"{name} should take exactly one parameter (Pydantic model)"

        # Validate the parameter type annotation via get_type_hints
        hints = get_type_hints(func)
        assert "params" in hints, f"{name} should annotate its 'params' argument"
        assert (
            hints["params"] is expected_type
        ), f"{name} 'params' annotation should be {expected_type.__name__}"

        # Return type should be annotated as str
        assert hints.get("return") is str, f"{name} should annotate return type as str"


def test_tool_docstrings_are_comprehensive() -> None:
    """T3.1.3/T3.1.4 - Docstrings exist and contain usage + error handling sections.

    Rather than asserting exact wording, we check for key structural
    elements such as examples and error handling notes to ensure tools
    are well-documented for LLM usage.
    """

    for name in EXPECTED_TOOL_NAMES:
        func = getattr(startd8_mcp, name)
        doc = inspect.getdoc(func) or ""

        # Non-trivial length
        assert len(doc) > 200, f"Docstring for {name} should be reasonably detailed"

        # Heuristic checks for structure
        assert "Args:" in doc or "Parameters" in doc, f"{name} docstring should describe arguments"
        assert "Returns:" in doc, f"{name} docstring should describe return type"
        assert "Examples" in doc or "Use when" in doc, f"{name} should include usage guidance"
        assert "Error Handling" in doc or "Error:" in doc, f"{name} should document error behavior"

