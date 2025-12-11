"""
Factory functions for creating pre-configured SkillAgent instances.

These factory functions provide convenient ways to create SkillAgent instances
for common use cases with sensible defaults.

Example:
    >>> from startd8.skills import create_game_enhancer_agent
    >>> agent = create_game_enhancer_agent(cost_tracking=True)
    >>> response = await agent.agenerate("Add achievement system")
"""

from typing import Optional

from .agent import SkillAgent, SkillAgentConfig

# Import cost tracking (optional)
try:
    from ..costs import CostTracker
    _COSTS_AVAILABLE = True
except ImportError:
    CostTracker = None
    _COSTS_AVAILABLE = False


def create_game_enhancer_agent(
    name: str = "React Game Enhancer",
    cost_tracking: bool = False,
    model: str = "claude-sonnet-4-20250514"
) -> SkillAgent:
    """
    Factory function to create a game enhancer skill agent.
    
    The React Game Enhancer skill is optimized for:
    - Adding game features (messaging, HUD, power-ups)
    - Mobile optimization
    - Accessibility compliance (WCAG 2.1 AA)
    - TypeScript/React best practices
    
    Args:
        name: Display name for the agent
        cost_tracking: Whether to enable cost tracking
        model: Model to use for execution
        
    Returns:
        Configured SkillAgent for game enhancement
        
    Example:
        >>> agent = create_game_enhancer_agent(cost_tracking=True)
        >>> response = await agent.agenerate("Add achievement system")
    """
    config = SkillAgentConfig(
        skill_id="skill-react-game-enhancer",
        name=name,
        description="Expert at enhancing React/TypeScript games with new features, systems, and components",
        model=model,
        tags=['game', 'react', 'typescript', 'enhancement'],
        version="1.0.0",
        capabilities=[
            "Add messaging systems",
            "Create HUD overlays",
            "Implement power-up systems",
            "Build leaderboards",
            "Add accessibility features",
            "Mobile optimization"
        ]
    )
    
    cost_tracker = None
    if cost_tracking and _COSTS_AVAILABLE:
        cost_tracker = CostTracker()
    
    return SkillAgent.from_config(config, cost_tracker=cost_tracker)


def create_html5_game_designer_agent(
    name: str = "HTML5 Game Designer",
    cost_tracking: bool = False,
    model: str = "claude-sonnet-4-20250514"
) -> SkillAgent:
    """
    Factory function to create an HTML5 game designer skill agent.
    
    The HTML5 Game Designer skill is optimized for:
    - Creating complete games from scratch
    - Canvas-based game development
    - Entity-Component System (ECS) architecture
    - Physics simulation
    - Performance optimization
    
    Args:
        name: Display name for the agent
        cost_tracking: Whether to enable cost tracking
        model: Model to use for execution
        
    Returns:
        Configured SkillAgent for HTML5 game creation
        
    Example:
        >>> agent = create_html5_game_designer_agent()
        >>> response = await agent.agenerate("Create a snake game with smooth animations")
    """
    config = SkillAgentConfig(
        skill_id="skill-html_game_dev",
        name=name,
        description="Creates production-ready HTML5 games using Canvas and ECS",
        model=model,
        tags=['game', 'html5', 'canvas', 'creation'],
        version="3.0.0",
        capabilities=[
            "Canvas-based game development",
            "Entity-Component System (ECS)",
            "Physics simulation",
            "Performance optimization",
            "Game polish and effects"
        ]
    )
    
    cost_tracker = None
    if cost_tracking and _COSTS_AVAILABLE:
        cost_tracker = CostTracker()
    
    return SkillAgent.from_config(config, cost_tracker=cost_tracker)


def create_code_reviewer_agent(
    name: str = "Code Reviewer",
    cost_tracking: bool = False,
    model: str = "claude-sonnet-4-20250514"
) -> SkillAgent:
    """
    Factory function to create a code review skill agent.
    
    The Code Reviewer skill is optimized for:
    - Code quality analysis
    - Best practices enforcement
    - Security vulnerability detection
    - Performance recommendations
    
    Args:
        name: Display name for the agent
        cost_tracking: Whether to enable cost tracking
        model: Model to use for execution
        
    Returns:
        Configured SkillAgent for code review
        
    Example:
        >>> reviewer = create_code_reviewer_agent()
        >>> feedback = await reviewer.agenerate(
        ...     "Review this code for security issues:\\n\\n" + code
        ... )
    """
    config = SkillAgentConfig(
        skill_id="skill-code-reviewer",
        name=name,
        description="Expert code reviewer that identifies issues and suggests improvements",
        model=model,
        tags=['code-review', 'quality', 'security'],
        version="1.0.0",
        capabilities=[
            "Code quality analysis",
            "Best practices enforcement",
            "Security vulnerability detection",
            "Performance recommendations",
            "Accessibility compliance checking"
        ]
    )
    
    cost_tracker = None
    if cost_tracking and _COSTS_AVAILABLE:
        cost_tracker = CostTracker()
    
    return SkillAgent.from_config(config, cost_tracker=cost_tracker)
