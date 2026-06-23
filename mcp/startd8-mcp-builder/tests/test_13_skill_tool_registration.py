"""Phase 1.13: Per-skill convenience tool registration (regression).

Covers the FastMCP signature-compatibility regression where every per-skill
tool (`startd8_skill_<name>`) silently failed to register because the
registration closure used a bind parameter named ``_lookup``. Current ``mcp``
SDK versions reject any tool parameter whose name starts with ``_`` by raising
``InvalidSignature``, so ``_register_concrete_skill_tools`` returned 0 while
``startd8_list_skills`` still advertised those (non-existent) tool names.

These tests assert the convenience tools actually register against the live
FastMCP instance, guarding against this whole class of breakage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import startd8_mcp


def _registered_tool_names() -> set[str]:
    return {t.name for t in startd8_mcp.mcp._tool_manager.list_tools()}


@pytest.fixture(autouse=True)
def _reset_skill_tool_state(monkeypatch: pytest.MonkeyPatch):
    """Isolate global registration state and the FastMCP registry per test."""
    # Reset the module-level dedupe set so re-registration is observable.
    monkeypatch.setattr(startd8_mcp, "_CONCRETE_SKILL_TOOL_NAMES", set())
    # Snapshot the tool manager's registry and restore it afterwards so we do
    # not leak per-skill tools into other tests sharing the singleton `mcp`.
    tm = startd8_mcp.mcp._tool_manager
    original = dict(tm._tools)
    try:
        yield
    finally:
        tm._tools = original


def test_skill_tools_register_for_every_skill(
    monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path
) -> None:
    """T1.13.1 - One convenience tool registers per discovered skill."""
    monkeypatch.setenv("STARTD8_SKILL_PATH", "")
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [test_skills_directory])
    monkeypatch.setattr(startd8_mcp, "MCP_REGISTER_SKILL_TOOLS", True)
    monkeypatch.setattr(startd8_mcp, "MCP_MAX_SKILL_TOOLS", 100)

    skills = startd8_mcp._find_skills()
    assert skills, "fixture should yield at least one discoverable skill"

    added = startd8_mcp._register_concrete_skill_tools(skills)

    # Regression: this was 0 because FastMCP rejected the `_lookup` bind param.
    assert added == len(skills), f"expected {len(skills)} skill tools, registered {added}"

    names = _registered_tool_names()
    skill_tool_names = {n for n in names if n.startswith("startd8_skill_")}
    assert len(skill_tool_names) == len(skills)


def test_skill_tool_signature_has_no_underscore_param(
    monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path
) -> None:
    """T1.13.2 - Registered skill tools expose only the public `params` arg.

    FastMCP raises InvalidSignature for any parameter starting with '_', so a
    successfully registered tool must not carry a bind parameter like `_lookup`.
    """
    monkeypatch.setenv("STARTD8_SKILL_PATH", "")
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [test_skills_directory])
    monkeypatch.setattr(startd8_mcp, "MCP_REGISTER_SKILL_TOOLS", True)

    skills = startd8_mcp._find_skills()
    added = startd8_mcp._register_concrete_skill_tools(skills)
    assert added > 0

    tools = {t.name: t for t in startd8_mcp.mcp._tool_manager.list_tools()}
    skill_tools = {n: t for n, t in tools.items() if n.startswith("startd8_skill_")}
    assert skill_tools, "no per-skill tools were registered"

    for name, tool in skill_tools.items():
        schema = tool.parameters  # FastMCP-generated JSON schema
        props = schema.get("properties", {})
        # The wrapper exposes a single `params` object; no leaked bind params.
        assert set(props.keys()) == {"params"}, f"{name} exposed unexpected args: {props.keys()}"
        assert not any(k.startswith("_") for k in props), f"{name} has an underscore param"


def test_registration_disabled_flag_registers_nothing(
    monkeypatch: pytest.MonkeyPatch, test_skills_directory: Path
) -> None:
    """T1.13.3 - Honors STARTD8_MCP_REGISTER_SKILL_TOOLS=off."""
    monkeypatch.setenv("STARTD8_SKILL_PATH", "")
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [test_skills_directory])
    monkeypatch.setattr(startd8_mcp, "MCP_REGISTER_SKILL_TOOLS", False)

    skills = startd8_mcp._find_skills()
    added = startd8_mcp._register_concrete_skill_tools(skills)
    assert added == 0
    assert not any(n.startswith("startd8_skill_") for n in _registered_tool_names())
