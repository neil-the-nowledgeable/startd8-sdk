"""
Skills Module - MCP-based Claude Skills Integration

This module provides skill-based agents that execute Claude Skills via the
Model Context Protocol (MCP). Skills are specialized Claude capabilities
optimized for specific tasks.

Components:
- SkillAgent: Agent that executes skills via MCP
- SkillAgentConfig: Configuration for skill agents
- CircuitState: Circuit breaker states for resilience
- Factory functions for common skills

Example:
    >>> from startd8.skills import SkillAgent, create_game_enhancer_agent
    >>> 
    >>> # Using factory function
    >>> agent = create_game_enhancer_agent()
    >>> response = await agent.agenerate("Add a notification system")
    >>> 
    >>> # Direct instantiation
    >>> agent = SkillAgent(
    ...     skill_id="skill-react-game-enhancer",
    ...     name="My Game Agent"
    ... )

See Also:
    - design/SKILL_AGENT_CORE_DESIGN.md for detailed design
"""

from .agent import (
    SkillAgent,
    SkillAgentConfig,
    CircuitState,
    SkillMetrics,
)

from .factories import (
    create_game_enhancer_agent,
    create_html5_game_designer_agent,
    create_code_reviewer_agent,
)

__all__ = [
    # Core classes
    "SkillAgent",
    "SkillAgentConfig",
    "CircuitState",
    "SkillMetrics",
    # Factory functions
    "create_game_enhancer_agent",
    "create_html5_game_designer_agent",
    "create_code_reviewer_agent",
]
