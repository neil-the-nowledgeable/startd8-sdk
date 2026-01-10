"""Phase 2.4: Input Validation Tests (Pydantic models).

These tests focus directly on the Pydantic models defined in
`startd8_mcp` rather than on the MCP tools, to keep validation
behavior fast and deterministic.

Covers:
- T2.4.1 Reject empty skill names
- T2.4.2 Reject empty prompts
- T2.4.3 Enforce min/max length constraints
- T2.4.4 Enforce min/max value constraints (tokens)
- T2.4.5 Strip whitespace from string inputs
- T2.4.6 Validate enum values (ResponseFormat)
- T2.4.7 Reject extra fields (Pydantic strict mode)
- T2.4.8 Validate list constraints (min_items, max_items)
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from startd8_mcp import (
    ListSkillsInput,
    GetSkillInput,
    UseSkillInput,
    CompareAgentsInput,
    ResponseFormat,
)


def _expect_validation_error(model, **kwargs: Any) -> None:
    """Helper that asserts constructing a model raises ValidationError."""

    with pytest.raises(ValidationError):
        model(**kwargs)


def test_empty_skill_name_rejected() -> None:
    """T2.4.1 - Empty skill names should be rejected."""

    _expect_validation_error(GetSkillInput, skill_name="")
    _expect_validation_error(GetSkillInput, skill_name="   ")

    _expect_validation_error(UseSkillInput, skill_name="")
    _expect_validation_error(UseSkillInput, skill_name="   ")


def test_empty_prompt_rejected() -> None:
    """T2.4.2 - Empty prompts should be rejected for tools that require them."""

    _expect_validation_error(UseSkillInput, skill_name="x", prompt="")
    _expect_validation_error(UseSkillInput, skill_name="x", prompt="   ")

    _expect_validation_error(CompareAgentsInput, prompt="", agents=["a", "b"])  # type: ignore[arg-type]


def test_length_constraints_enforced() -> None:
    """T2.4.3 - Enforce min/max length on string fields."""

    # min_length=1 enforced by previous tests; here we test max_length
    long_name = "x" * 201
    _expect_validation_error(GetSkillInput, skill_name=long_name)

    long_prompt = "x" * 50_001
    _expect_validation_error(UseSkillInput, skill_name="ok", prompt=long_prompt)


def test_token_constraints() -> None:
    """T2.4.4 - max_tokens must be within the configured bounds."""

    # Valid boundary values
    UseSkillInput(skill_name="ok", prompt="hi", max_tokens=1)
    UseSkillInput(skill_name="ok", prompt="hi", max_tokens=200_000)

    # Out-of-range values
    _expect_validation_error(UseSkillInput, skill_name="ok", prompt="hi", max_tokens=0)
    _expect_validation_error(UseSkillInput, skill_name="ok", prompt="hi", max_tokens=200_001)


def test_whitespace_stripping() -> None:
    """T2.4.5 - Leading/trailing whitespace is stripped from strings."""

    model = GetSkillInput(skill_name="  skill-name  ")
    assert model.skill_name == "skill-name"

    use_model = UseSkillInput(skill_name="  skill  ", prompt="  hello  ")
    assert use_model.skill_name == "skill"
    assert use_model.prompt == "hello"


def test_response_format_enum_validation() -> None:
    """T2.4.6 - ResponseFormat must be a valid enum value."""

    # Enum accepts either the enum member or its string value
    ListSkillsInput(response_format=ResponseFormat.MARKDOWN)
    ListSkillsInput(response_format="json")

    # Invalid value should fail
    _expect_validation_error(ListSkillsInput, response_format="invalid-format")


def test_extra_fields_rejected() -> None:
    """T2.4.7 - Models are configured with extra='forbid'."""

    _expect_validation_error(ListSkillsInput, response_format="markdown", unknown_field=True)
    _expect_validation_error(GetSkillInput, skill_name="x", extra_field="y")
    _expect_validation_error(UseSkillInput, skill_name="x", prompt="hi", foo="bar")


def test_list_constraints_for_agents() -> None:
    """T2.4.8 - Validate min_items and max_items constraints for agents list."""

    # Too few agents
    _expect_validation_error(CompareAgentsInput, prompt="hi", agents=["only-one"])

    # Too many agents (>5)
    _expect_validation_error(
        CompareAgentsInput,
        prompt="hi",
        agents=["a", "b", "c", "d", "e", "f"],
    )

    # Boundary cases (2..5) should succeed
    CompareAgentsInput(prompt="ok", agents=["a", "b"])
    CompareAgentsInput(prompt="ok", agents=["a", "b", "c", "d", "e"])


def test_use_skill_response_format_validation() -> None:
    """Test response_format field on UseSkillInput model."""

    # Valid enum values should succeed
    UseSkillInput(skill_name="ok", prompt="hi", response_format=ResponseFormat.MARKDOWN)
    UseSkillInput(skill_name="ok", prompt="hi", response_format=ResponseFormat.JSON)
    
    # String values should also work due to enum coercion
    UseSkillInput(skill_name="ok", prompt="hi", response_format="markdown")
    UseSkillInput(skill_name="ok", prompt="hi", response_format="json")

    # Invalid format should fail
    _expect_validation_error(
        UseSkillInput,
        skill_name="ok",
        prompt="hi",
        response_format="invalid-format"
    )


def test_use_skill_response_format_default() -> None:
    """Test that response_format defaults to markdown."""

    model = UseSkillInput(skill_name="ok", prompt="hi")
    assert model.response_format == ResponseFormat.MARKDOWN

