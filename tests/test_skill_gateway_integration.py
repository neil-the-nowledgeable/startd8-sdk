"""
Integration-style tests ensuring SkillAgent routes through MCPGateway.
Network calls are stubbed to avoid external dependencies.
"""

import pytest

from startd8.mcp import MCPGateway, MCPGatewayConfig, SkillExecutionResult
from startd8.skills import SkillAgent
from startd8.models import TokenUsage


@pytest.mark.asyncio
async def test_skill_agent_uses_gateway(monkeypatch):
    """SkillAgent should invoke MCPGateway.execute_skill when provided."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    cfg = MCPGatewayConfig(max_connections=2)
    gateway = MCPGateway(cfg)

    # Stub _execute_mcp_skill to avoid real MCP calls
    async def fake_exec(skill_id, prompt, max_tokens, timeout_ms):
        return SkillExecutionResult(
            content=f"response for {skill_id}",
            metrics={"mock": True},
            skill_id=skill_id,
            execution_time_ms=5,
            token_usage=TokenUsage(input=10, output=20, total=30),
            cache_hit=False,
        )

    # Monkeypatch helper on gateway (using existing private to build result)
    gateway._execute_mcp_skill = fake_exec  # type: ignore[attr-defined]
    await gateway.initialize()

    agent = SkillAgent(skill_id="skill-react-game-enhancer", mcp_gateway=gateway)

    response, time_ms, tokens = await agent.agenerate("do a thing")

    assert "response for skill-react-game-enhancer" in response
    assert isinstance(tokens, TokenUsage)
    assert tokens.input == 10
    assert tokens.output == 20

    await gateway.shutdown()


@pytest.mark.asyncio
async def test_multiple_agents_share_gateway(monkeypatch):
    """Multiple SkillAgents should share the same gateway instance."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    gateway = MCPGateway()

    async def fake_exec(skill_id, prompt, max_tokens, timeout_ms):
        return SkillExecutionResult(
            content=f"{skill_id} reply",
            metrics={},
            skill_id=skill_id,
            execution_time_ms=3,
            token_usage=TokenUsage(input=5, output=5, total=10),
            cache_hit=False,
        )

    gateway._execute_mcp_skill = fake_exec  # type: ignore[attr-defined]
    await gateway.initialize()

    dev = SkillAgent(skill_id="skill-react-game-enhancer", mcp_gateway=gateway)
    reviewer = SkillAgent(skill_id="skill-code-reviewer", mcp_gateway=gateway)

    dev_resp, _, _ = await dev.agenerate("task a")
    rev_resp, _, _ = await reviewer.agenerate("task b")

    assert "skill-react-game-enhancer" in dev_resp
    assert "skill-code-reviewer" in rev_resp

    # Ensure both agents reference the same gateway object
    assert dev.mcp_gateway is reviewer.mcp_gateway is gateway

    await gateway.shutdown()
