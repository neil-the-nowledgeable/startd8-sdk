"""MCP agent surface (FR-11): generic client → canonical registry → loop, with FR-19 default-deny.

Uses a FakeToolClient (the ToolClient protocol) so the whole surface is tested with no server and no
fastmcp dependency.
"""

from __future__ import annotations

import pytest

from startd8.agents.mock import MockAgent
from startd8.mcp.client import (
    McpToolInfo,
    ToolClient,
    build_registry_from_mcp,
    new_mcp_agent_session,
)


class FakeToolClient:
    """In-memory ToolClient: a read tool and an effectful tool; records what got executed."""

    def __init__(self):
        self.executed: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[McpToolInfo]:
        return [
            McpToolInfo("get_status", "read status", {"type": "object"}, read_only=True),
            McpToolInfo("delete_repo", "danger", {"type": "object"}, read_only=False, destructive=True),
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.executed.append((name, arguments))
        return f"{name} -> ok"


def test_fake_client_satisfies_protocol():
    assert isinstance(FakeToolClient(), ToolClient)  # runtime_checkable Protocol


def test_effect_class_derivation():
    assert McpToolInfo("a", "", {}, read_only=True).effect_class == "read"
    assert McpToolInfo("a", "", {}, read_only=False).effect_class == "write"
    assert McpToolInfo("a", "", {}, read_only=False, destructive=True).effect_class == "destructive"
    # destructive wins even if read_only is somehow set
    assert McpToolInfo("a", "", {}, read_only=True, destructive=True).effect_class == "destructive"


@pytest.mark.asyncio
async def test_registry_snapshot_maps_all_tools():
    reg = await build_registry_from_mcp(FakeToolClient())
    assert reg.names() == {"get_status", "delete_repo"}
    assert reg.allow_effect_classes == {"read"}  # default-deny posture


@pytest.mark.asyncio
async def test_read_tool_executes_through_the_loop():
    client = FakeToolClient()
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"tool_calls": [("c1", "get_status", {"verbose": True})]},
            {"text": "status looks good", "tool_calls": []},
        ],
    )
    session = await new_mcp_agent_session(agent, client)
    result = await session.send("what's the status?")

    assert result.ok and "status looks good" in result.text
    assert client.executed == [("get_status", {"verbose": True})]  # the MCP tool really ran
    assert any("get_status -> ok" in m.get("content", "") for m in result.messages if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_effectful_mcp_tool_denied_by_default():
    """FR-19 / FR-11: a destructive MCP tool is NOT executed under the default read-only policy."""
    client = FakeToolClient()
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"tool_calls": [("c1", "delete_repo", {"name": "prod"})]},
            {"text": "I can't do that.", "tool_calls": []},
        ],
    )
    session = await new_mcp_agent_session(agent, client)  # allow_effect_classes defaults to ("read",)
    result = await session.send("delete the prod repo")

    assert result.stop_reason == "completed"
    assert client.executed == []  # the destructive tool NEVER ran
    assert any("not permitted by policy" in m.get("content", "") for m in result.messages if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_effectful_tool_runs_only_with_explicit_allowlist():
    """The escape hatch is explicit: widening the allow-list (an approval decision) lets it run."""
    client = FakeToolClient()
    agent = MockAgent(
        model="mock-model",
        tool_turns=[
            {"tool_calls": [("c1", "delete_repo", {"name": "scratch"})]},
            {"text": "done", "tool_calls": []},
        ],
    )
    session = await new_mcp_agent_session(agent, client, allow_effect_classes=("read", "destructive"))
    result = await session.send("delete scratch")
    assert result.ok
    assert client.executed == [("delete_repo", {"name": "scratch"})]
