# Skill Agent Core Design

**Version:** 1.1.0  
**Status:** ✅ Implemented (Phase 1 Complete)  
**Parent Document:** [INDEX_SKILL_INTEGRATION_PLANS_v4.md](../INDEX_SKILL_INTEGRATION_PLANS_v4.md)  
**Dependencies:** `BaseAgent`, `TokenUsage`, `AgentResponse`  
**Implementation:** `src/startd8/skills/` module

---

## 1. Overview

This document provides the complete design specification for the `SkillAgent` class, which enables the startd8 SDK to execute Claude Skills via the Model Context Protocol (MCP). The SkillAgent extends the existing `BaseAgent` class, ensuring backward compatibility while adding skill-specific capabilities.

### Design Goals

1. **Seamless Integration**: Drop-in replacement for any `BaseAgent` subclass
2. **Observability First**: Built-in metrics, logging, and tracing
3. **Cost Awareness**: Integrated cost tracking and budget enforcement
4. **Failure Resilience**: Graceful degradation when MCP is unavailable
5. **Testability**: Easy to mock and test in isolation

---

## 2. Class Diagram

```
                    ┌──────────────────────────────┐
                    │         BaseAgent            │
                    │         (Abstract)           │
                    ├──────────────────────────────┤
                    │ + name: str                  │
                    │ + model: str                 │
                    │ + cost_tracker: CostTracker  │
                    │ + budget_manager: BudgetMgr  │
                    ├──────────────────────────────┤
                    │ + generate(prompt)           │
                    │ + agenerate(prompt)          │
                    │ + create_response(...)       │
                    └──────────────┬───────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│   ClaudeAgent    │   │    GPT4Agent     │   │   SkillAgent     │
│                  │   │                  │   │     (NEW)        │
├──────────────────┤   ├──────────────────┤   ├──────────────────┤
│ + client         │   │ + client         │   │ + skill_id       │
│ + async_client   │   │ + async_client   │   │ + mcp_gateway    │
│ + max_tokens     │   │ + max_tokens     │   │ + max_tokens     │
├──────────────────┤   ├──────────────────┤   │ + circuit_state  │
│ + agenerate()    │   │ + agenerate()    │   ├──────────────────┤
└──────────────────┘   └──────────────────┘   │ + agenerate()    │
                                              │ + is_healthy()   │
                                              │ + get_agent_info │
                                              └──────────────────┘
```

---

## 3. Complete Implementation

### 3.1 Core SkillAgent Class

```python
# File: src/startd8/skills/agent.py
# Module structure:
#   src/startd8/skills/
#   ├── __init__.py      # Exports public API
#   ├── agent.py         # SkillAgent, SkillAgentConfig, CircuitState
#   └── factories.py     # Factory functions

"""
Skill-Based Agents for MCP Integration

This module extends the base agent system with skill execution capabilities
via the Model Context Protocol (MCP).
"""

import os
import time
import asyncio
import logging
from abc import ABC
from enum import Enum
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field

from .models import TokenUsage, AgentResponse
from .logging_config import get_logger

# Conditional imports
try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None
    _ANTHROPIC_AVAILABLE = False

try:
    from .costs import CostTracker, BudgetManager
    _COSTS_AVAILABLE = True
except ImportError:
    CostTracker = None
    BudgetManager = None
    _COSTS_AVAILABLE = False

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class SkillMetrics:
    """Metrics collected from skill execution."""
    execution_time_ms: int
    input_tokens: int
    output_tokens: int
    skill_reported_time_ms: Optional[int] = None
    cache_hit: bool = False
    circuit_state: CircuitState = CircuitState.CLOSED


@dataclass
class SkillAgentConfig:
    """Configuration for skill-based agents.
    
    This dataclass provides a clean way to configure SkillAgent instances
    and can be serialized/deserialized for storage and transmission.
    
    Attributes:
        skill_id: Unique identifier for the skill (e.g., 'skill-react-game-enhancer')
        name: Human-readable name for the agent
        description: What the skill does and when to use it
        model: The LLM model used for skill execution
        max_tokens: Maximum output tokens for skill responses
        timeout_ms: Request timeout in milliseconds
        cost_tracking_enabled: Whether to track costs for this agent
        tags: Tags for categorizing and filtering skills
        version: Semantic version of the skill
        capabilities: List of capabilities the skill provides
    
    Example:
        >>> config = SkillAgentConfig(
        ...     skill_id="skill-react-game-enhancer",
        ...     name="React Game Enhancer",
        ...     description="Enhances React games with new features",
        ...     tags=["game", "react", "typescript"],
        ...     capabilities=["Add messaging systems", "Create HUD overlays"]
        ... )
        >>> agent = SkillAgent.from_config(config)
    """
    skill_id: str
    name: str
    description: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8192
    timeout_ms: int = 30000
    cost_tracking_enabled: bool = False
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to dictionary."""
        return {
            'skill_id': self.skill_id,
            'name': self.name,
            'description': self.description,
            'model': self.model,
            'max_tokens': self.max_tokens,
            'timeout_ms': self.timeout_ms,
            'cost_tracking_enabled': self.cost_tracking_enabled,
            'tags': self.tags,
            'version': self.version,
            'capabilities': self.capabilities
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SkillAgentConfig':
        """Deserialize config from dictionary."""
        return cls(**data)


class SkillAgent(BaseAgent):
    """
    Agent that executes Claude Skills via MCP.
    
    This agent bridges the startd8 SDK with Claude Skills by calling
    the startd8 MCP server's skill execution tools. It provides:
    
    - Skill execution via MCP protocol
    - Automatic metric collection (time, tokens, cost)
    - Circuit breaker for resilience
    - Cost tracking and budget enforcement
    - Structured logging for observability
    
    The SkillAgent is fully compatible with the existing iterative workflow
    system and can be used as either a developer or reviewer agent.
    
    Attributes:
        skill_id: The unique identifier of the skill to execute
        mcp_gateway: Optional MCP gateway for connection pooling
        max_tokens: Maximum output tokens
        timeout_ms: Request timeout in milliseconds
        _circuit_state: Current circuit breaker state
        _failure_count: Consecutive failure count
        _last_failure_time: Timestamp of last failure
    
    Example:
        >>> # Simple usage
        >>> agent = SkillAgent(skill_id="skill-react-game-enhancer")
        >>> response = await agent.agenerate("Add a notification system")
        
        >>> # With cost tracking
        >>> from startd8.costs import CostTracker
        >>> tracker = CostTracker()
        >>> agent = SkillAgent(
        ...     skill_id="skill-react-game-enhancer",
        ...     name="Game Enhancer",
        ...     cost_tracker=tracker
        ... )
        
        >>> # In iterative workflow
        >>> from startd8.iterative_workflow import IterativeDevWorkflow
        >>> dev_agent = SkillAgent(skill_id="skill-react-game-enhancer")
        >>> reviewer = SkillAgent(skill_id="skill-code-reviewer")
        >>> workflow = IterativeDevWorkflow(dev_agent, reviewer)
        >>> result = workflow.run("Add messaging system")
    """
    
    # Circuit breaker configuration
    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT_SECONDS = 30
    HALF_OPEN_MAX_REQUESTS = 3
    
    def __init__(
        self,
        skill_id: str,
        name: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 8192,
        timeout_ms: int = 30000,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        mcp_gateway: Optional[Any] = None,  # MCPGateway type hint
        mcp_enabled: bool = True
    ):
        """
        Initialize skill agent.
        
        Args:
            skill_id: ID of the skill to execute (e.g., "skill-react-game-enhancer")
            name: Display name for the agent (defaults to skill_id)
            model: Model to use for skill execution
            max_tokens: Maximum output tokens
            timeout_ms: Request timeout in milliseconds
            cost_tracker: Optional cost tracker for recording usage
            budget_manager: Optional budget manager for enforcing limits
            mcp_gateway: Optional shared MCP gateway for connection pooling
            mcp_enabled: Whether to use MCP for skill execution (default: True)
        
        Raises:
            ValueError: If skill_id is empty or invalid
            RuntimeError: If MCP is enabled but not available
        """
        if not skill_id or not isinstance(skill_id, str):
            raise ValueError(f"Invalid skill_id: {skill_id}. Must be a non-empty string.")
        
        if not skill_id.startswith("skill-"):
            logger.warning(
                f"skill_id '{skill_id}' does not follow convention 'skill-*'. "
                "Consider using standard naming."
            )
        
        super().__init__(
            name=name or skill_id,
            model=model,
            cost_tracker=cost_tracker,
            budget_manager=budget_manager
        )
        
        self.skill_id = skill_id
        self.max_tokens = max_tokens
        self.timeout_ms = timeout_ms
        self.mcp_gateway = mcp_gateway
        self.mcp_enabled = mcp_enabled
        
        # Circuit breaker state
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_requests = 0
        
        # Validate MCP availability
        if self.mcp_enabled:
            self._validate_mcp_availability()
        
        logger.info(
            f"SkillAgent initialized",
            extra={
                'skill_id': self.skill_id,
                'name': self.name,
                'model': self.model,
                'mcp_enabled': self.mcp_enabled
            }
        )
    
    @classmethod
    def from_config(
        cls,
        config: SkillAgentConfig,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        mcp_gateway: Optional[Any] = None
    ) -> 'SkillAgent':
        """
        Create SkillAgent from configuration object.
        
        Args:
            config: SkillAgentConfig with agent settings
            cost_tracker: Optional cost tracker
            budget_manager: Optional budget manager
            mcp_gateway: Optional MCP gateway
            
        Returns:
            Configured SkillAgent instance
        """
        return cls(
            skill_id=config.skill_id,
            name=config.name,
            model=config.model,
            max_tokens=config.max_tokens,
            timeout_ms=config.timeout_ms,
            cost_tracker=cost_tracker if config.cost_tracking_enabled else None,
            budget_manager=budget_manager,
            mcp_gateway=mcp_gateway
        )
    
    def _validate_mcp_availability(self) -> None:
        """
        Validate that MCP is properly configured.
        
        Checks:
        1. ANTHROPIC_API_KEY environment variable is set
        2. Anthropic SDK is available
        
        Raises:
            RuntimeError: If MCP is not available or not configured
        """
        if not _ANTHROPIC_AVAILABLE:
            raise RuntimeError(
                "Anthropic SDK not installed. "
                "Install with: pip install anthropic"
            )
        
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Required for skill execution via MCP."
            )
        
        logger.debug(f"MCP validation passed for skill: {self.skill_id}")
    
    def _check_circuit_breaker(self) -> None:
        """
        Check circuit breaker state and determine if request should proceed.
        
        Raises:
            RuntimeError: If circuit is open and request should be blocked
        """
        if self._circuit_state == CircuitState.CLOSED:
            return
        
        if self._circuit_state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.RECOVERY_TIMEOUT_SECONDS:
                    logger.info(
                        f"Circuit breaker transitioning to HALF_OPEN for {self.skill_id}"
                    )
                    self._circuit_state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                else:
                    raise RuntimeError(
                        f"Circuit breaker OPEN for skill '{self.skill_id}'. "
                        f"Will retry in {self.RECOVERY_TIMEOUT_SECONDS - elapsed:.1f}s"
                    )
        
        if self._circuit_state == CircuitState.HALF_OPEN:
            if self._half_open_requests >= self.HALF_OPEN_MAX_REQUESTS:
                raise RuntimeError(
                    f"Circuit breaker HALF_OPEN limit reached for skill '{self.skill_id}'"
                )
            self._half_open_requests += 1
    
    def _record_success(self) -> None:
        """Record successful execution and update circuit breaker."""
        self._failure_count = 0
        
        if self._circuit_state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit breaker CLOSED for {self.skill_id} after successful request")
            self._circuit_state = CircuitState.CLOSED
            self._half_open_requests = 0
    
    def _record_failure(self, error: Exception) -> None:
        """Record failed execution and update circuit breaker."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._circuit_state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit breaker OPEN for {self.skill_id} after half-open failure")
            self._circuit_state = CircuitState.OPEN
            self._half_open_requests = 0
        elif self._failure_count >= self.FAILURE_THRESHOLD:
            logger.warning(
                f"Circuit breaker OPEN for {self.skill_id} after {self._failure_count} failures"
            )
            self._circuit_state = CircuitState.OPEN
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Execute skill via MCP and return response with metrics.
        
        This method handles:
        1. Circuit breaker check
        2. MCP skill execution
        3. Response parsing
        4. Metric collection
        5. Error handling with proper logging
        
        Args:
            prompt: The prompt/task for the skill
            
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
            
        Raises:
            RuntimeError: If skill execution fails or circuit is open
            ValueError: If response format is invalid
        """
        start_time = time.time()
        
        # Check circuit breaker
        try:
            self._check_circuit_breaker()
        except RuntimeError as e:
            logger.warning(f"Request blocked by circuit breaker: {e}")
            raise
        
        try:
            # Execute skill via MCP
            if self.mcp_gateway:
                # Use shared gateway (preferred for production)
                response, tokens = await self._call_via_gateway(prompt)
            else:
                # Direct MCP call (for simple usage)
                response, tokens = await self._call_mcp_skill(prompt)
            
            # Parse response
            response_text, skill_metrics = self._parse_skill_response(response)
            
            # Calculate metrics
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Build token usage
            token_usage = TokenUsage(
                input=tokens.get("input", 0),
                output=tokens.get("output", 0),
                total=tokens.get("input", 0) + tokens.get("output", 0)
            )
            
            # Record success
            self._record_success()
            
            # Log successful execution
            logger.info(
                f"Skill {self.skill_id} executed successfully",
                extra={
                    'skill_id': self.skill_id,
                    'agent_name': self.name,
                    'time_ms': response_time_ms,
                    'input_tokens': tokens.get("input", 0),
                    'output_tokens': tokens.get("output", 0),
                    'circuit_state': self._circuit_state.value
                }
            )
            
            return response_text, response_time_ms, token_usage
            
        except Exception as e:
            # Record failure
            self._record_failure(e)
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            logger.error(
                f"Skill execution failed: {e}",
                extra={
                    'skill_id': self.skill_id,
                    'agent_name': self.name,
                    'time_ms': response_time_ms,
                    'circuit_state': self._circuit_state.value,
                    'failure_count': self._failure_count
                },
                exc_info=True
            )
            
            raise RuntimeError(
                f"Failed to execute skill '{self.skill_id}': {str(e)}"
            ) from e
    
    async def _call_via_gateway(self, prompt: str) -> Tuple[str, Dict[str, int]]:
        """
        Execute skill via shared MCP gateway.
        
        This method is preferred for production as it provides:
        - Connection pooling
        - Centralized rate limiting
        - Better observability
        
        Args:
            prompt: The skill prompt/task
            
        Returns:
            Tuple of (response_text, token_metrics)
        """
        result = await self.mcp_gateway.execute_skill(
            skill_id=self.skill_id,
            prompt=prompt,
            max_tokens=self.max_tokens,
            timeout_ms=self.timeout_ms
        )
        
        return result.content, {
            "input": result.token_usage.input,
            "output": result.token_usage.output
        }
    
    async def _call_mcp_skill(self, prompt: str) -> Tuple[str, Dict[str, int]]:
        """
        Call startd8 MCP skill execution tool directly.
        
        This method creates a new Anthropic client for each call.
        For production, use mcp_gateway for connection pooling.
        
        Args:
            prompt: The skill prompt/task
            
        Returns:
            Tuple of (response_text, token_metrics)
        """
        client = AsyncAnthropic()
        
        # Define the MCP tool for skill execution
        tools = [
            {
                "name": "startd8_use_skill",
                "description": (
                    "Execute a Claude Skill via startd8 MCP. "
                    "The skill will generate specialized responses with metrics."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "skill_id": {
                            "type": "string",
                            "description": "The ID of the skill to execute"
                        },
                        "prompt": {
                            "type": "string",
                            "description": "The task/prompt for the skill"
                        },
                        "max_tokens": {
                            "type": "integer",
                            "description": "Maximum output tokens",
                            "default": 8192
                        }
                    },
                    "required": ["skill_id", "prompt"]
                }
            }
        ]
        
        # Build message requesting skill execution
        messages = [
            {
                "role": "user",
                "content": (
                    f"Execute the {self.skill_id} skill with this task:\n\n{prompt}"
                )
            }
        ]
        
        # Call Claude with tool use
        response = await asyncio.wait_for(
            client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                tools=tools,
                messages=messages
            ),
            timeout=self.timeout_ms / 1000  # Convert to seconds
        )
        
        # Extract skill response from tool use
        skill_response = self._extract_tool_response(response)
        
        # Extract token metrics
        tokens = {
            "input": response.usage.input_tokens,
            "output": response.usage.output_tokens
        }
        
        return skill_response, tokens
    
    def _extract_tool_response(self, response: Any) -> str:
        """
        Extract skill response from Claude's tool use response.
        
        Args:
            response: Claude API response with tool use
            
        Returns:
            The skill response text
            
        Raises:
            ValueError: If response format is invalid
        """
        if not response.content:
            raise ValueError("Empty response from Claude")
        
        # Find the text content in the response
        for block in response.content:
            if hasattr(block, 'text'):
                return block.text
        
        raise ValueError(
            "No text content found in Claude response. "
            "Ensure MCP tool was invoked correctly."
        )
    
    def _parse_skill_response(
        self,
        response: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Parse skill response to extract code/content and metrics.
        
        Skill responses typically include:
        - Execution metrics (time, tokens)
        - Generated code/content
        - Quality score/feedback
        
        Expected format:
            # Skill Response
            **Skill:** React/TypeScript Game Enhancer
            **Time:** 1234ms
            **Tokens:** 156 in, 2847 out
            ---
            [Generated content]
        
        Args:
            response: The skill response text
            
        Returns:
            Tuple of (extracted_content, metrics_dict)
        """
        metrics: Dict[str, Any] = {}
        content_lines: List[str] = []
        in_content = False
        
        for line in response.split('\n'):
            # Extract metrics
            if '**Time:**' in line:
                try:
                    time_str = line.split('**Time:**')[1].strip().rstrip('ms')
                    metrics['time_ms'] = int(time_str)
                except (IndexError, ValueError):
                    pass
            
            elif '**Tokens:**' in line:
                try:
                    tokens_str = line.split('**Tokens:**')[1].strip()
                    # Format: "156 in, 2847 out"
                    in_out = tokens_str.split(',')
                    metrics['input'] = int(in_out[0].split()[0])
                    metrics['output'] = int(in_out[1].split()[0])
                except (IndexError, ValueError):
                    pass
            
            # Find where content starts (after the --- separator)
            elif line.strip() == '---':
                in_content = True
                continue
            
            # Collect content after separator
            if in_content:
                content_lines.append(line)
        
        # If no separator found, return entire response as content
        if not in_content:
            content = response
        else:
            content = '\n'.join(content_lines).strip()
        
        return content, metrics
    
    def _calculate_cost(self, tokens: Dict[str, int]) -> float:
        """
        Calculate estimated cost of skill execution.
        
        Uses Claude pricing:
        - Input: ~$3 per 1M tokens
        - Output: ~$15 per 1M tokens
        
        Args:
            tokens: Dict with 'input' and 'output' token counts
            
        Returns:
            Estimated cost in dollars
        """
        input_tokens = tokens.get("input", 0)
        output_tokens = tokens.get("output", 0)
        
        # Claude Sonnet 4 pricing (approximate)
        input_cost = (input_tokens / 1_000_000) * 3
        output_cost = (output_tokens / 1_000_000) * 15
        
        return input_cost + output_cost
    
    def get_agent_info(self) -> Dict[str, Any]:
        """
        Get metadata about this skill agent.
        
        Returns:
            Dictionary with agent information for introspection
        """
        return {
            'type': 'SkillAgent',
            'skill_id': self.skill_id,
            'name': self.name,
            'model': self.model,
            'max_tokens': self.max_tokens,
            'timeout_ms': self.timeout_ms,
            'mcp_enabled': self.mcp_enabled,
            'circuit_state': self._circuit_state.value,
            'failure_count': self._failure_count,
            'cost_tracking_enabled': self.cost_tracker is not None,
            'budget_managed': self.budget_manager is not None
        }
    
    def is_healthy(self) -> bool:
        """
        Check if the agent is healthy and ready to accept requests.
        
        Used for Kubernetes readiness probes and load balancer health checks.
        
        Returns:
            True if agent is ready to accept requests
        """
        return self._circuit_state != CircuitState.OPEN
    
    def reset_circuit_breaker(self) -> None:
        """
        Manually reset the circuit breaker to closed state.
        
        Use with caution - primarily for administrative purposes.
        """
        logger.info(f"Circuit breaker manually reset for {self.skill_id}")
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_requests = 0
    
    @property
    def agent_name(self) -> str:
        """Alias for name property for compatibility with BaseAgent."""
        return self.name


# ============================================================================
# SKILL AGENT FACTORY FUNCTIONS
# ============================================================================

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
```

---

## 4. Unit Tests

```python
# File: tests/unit/test_skill_agent.py

"""
Unit tests for SkillAgent class.

Run with: pytest tests/unit/test_skill_agent.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import asdict

# Import the classes to test
from src.startd8.agents import (
    SkillAgent,
    SkillAgentConfig,
    CircuitState,
    create_game_enhancer_agent,
    create_html5_game_designer_agent,
    create_code_reviewer_agent
)


class TestSkillAgentConfig:
    """Tests for SkillAgentConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = SkillAgentConfig(
            skill_id="test-skill",
            name="Test Skill"
        )
        
        assert config.skill_id == "test-skill"
        assert config.name == "Test Skill"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 8192
        assert config.timeout_ms == 30000
        assert config.cost_tracking_enabled is False
        assert config.tags == []
        assert config.version == "1.0.0"
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = SkillAgentConfig(
            skill_id="test-skill",
            name="Test Skill",
            tags=["test", "unit"]
        )
        
        data = config.to_dict()
        
        assert data['skill_id'] == "test-skill"
        assert data['tags'] == ["test", "unit"]
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            'skill_id': 'test-skill',
            'name': 'Test Skill',
            'model': 'claude-3-opus',
            'max_tokens': 4096
        }
        
        config = SkillAgentConfig.from_dict(data)
        
        assert config.skill_id == "test-skill"
        assert config.max_tokens == 4096


class TestSkillAgentInit:
    """Tests for SkillAgent initialization."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_valid_skill_id(self):
        """Test initialization with valid skill_id."""
        agent = SkillAgent(skill_id="skill-test")
        
        assert agent.skill_id == "skill-test"
        assert agent.name == "skill-test"
        assert agent._circuit_state == CircuitState.CLOSED
    
    def test_invalid_skill_id_empty(self):
        """Test that empty skill_id raises ValueError."""
        with pytest.raises(ValueError, match="Invalid skill_id"):
            SkillAgent(skill_id="")
    
    def test_invalid_skill_id_none(self):
        """Test that None skill_id raises ValueError."""
        with pytest.raises(ValueError, match="Invalid skill_id"):
            SkillAgent(skill_id=None)
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_custom_name(self):
        """Test custom name for agent."""
        agent = SkillAgent(
            skill_id="skill-test",
            name="My Custom Agent"
        )
        
        assert agent.name == "My Custom Agent"
        assert agent.skill_id == "skill-test"
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_from_config(self):
        """Test creating agent from config."""
        config = SkillAgentConfig(
            skill_id="skill-test",
            name="Config Agent",
            max_tokens=4096
        )
        
        agent = SkillAgent.from_config(config)
        
        assert agent.skill_id == "skill-test"
        assert agent.name == "Config Agent"
        assert agent.max_tokens == 4096


class TestSkillAgentParsing:
    """Tests for response parsing."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_parse_skill_response_with_metrics(self):
        """Test parsing skill response with metrics."""
        agent = SkillAgent(skill_id="skill-test")
        
        response = """# Skill Response
**Skill:** Test Skill
**Time:** 1234ms
**Tokens:** 156 in, 2847 out

---

## Generated Code
```typescript
export const Component = () => {
  return <div>Hello</div>;
};
```"""
        
        content, metrics = agent._parse_skill_response(response)
        
        assert "Generated Code" in content
        assert metrics['time_ms'] == 1234
        assert metrics['input'] == 156
        assert metrics['output'] == 2847
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_parse_skill_response_no_separator(self):
        """Test parsing response without --- separator."""
        agent = SkillAgent(skill_id="skill-test")
        
        response = "Just plain content without any formatting"
        
        content, metrics = agent._parse_skill_response(response)
        
        assert content == response
        assert metrics == {}
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_calculate_cost(self):
        """Test cost calculation."""
        agent = SkillAgent(skill_id="skill-test")
        
        tokens = {"input": 1000, "output": 1000}
        cost = agent._calculate_cost(tokens)
        
        # Input cost: (1000 / 1M) * 3 = 0.003
        # Output cost: (1000 / 1M) * 15 = 0.015
        # Total: ~0.018
        assert cost > 0
        assert 0.01 < cost < 0.05


class TestSkillAgentCircuitBreaker:
    """Tests for circuit breaker functionality."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_initial_state_closed(self):
        """Test circuit starts in closed state."""
        agent = SkillAgent(skill_id="skill-test")
        
        assert agent._circuit_state == CircuitState.CLOSED
        assert agent.is_healthy() is True
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Simulate failures
        for i in range(SkillAgent.FAILURE_THRESHOLD):
            agent._record_failure(Exception("test"))
        
        assert agent._circuit_state == CircuitState.OPEN
        assert agent.is_healthy() is False
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_success_resets_failure_count(self):
        """Test successful request resets failure count."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Add some failures
        agent._record_failure(Exception("test"))
        agent._record_failure(Exception("test"))
        assert agent._failure_count == 2
        
        # Success resets
        agent._record_success()
        assert agent._failure_count == 0
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_manual_reset(self):
        """Test manual circuit breaker reset."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Open circuit
        for i in range(SkillAgent.FAILURE_THRESHOLD):
            agent._record_failure(Exception("test"))
        
        assert agent._circuit_state == CircuitState.OPEN
        
        # Manual reset
        agent.reset_circuit_breaker()
        
        assert agent._circuit_state == CircuitState.CLOSED
        assert agent._failure_count == 0


class TestSkillAgentInfo:
    """Tests for agent info and metadata."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_get_agent_info(self):
        """Test getting agent info."""
        agent = SkillAgent(
            skill_id="skill-test",
            name="Test Agent",
            max_tokens=4096
        )
        
        info = agent.get_agent_info()
        
        assert info['type'] == 'SkillAgent'
        assert info['skill_id'] == 'skill-test'
        assert info['name'] == 'Test Agent'
        assert info['max_tokens'] == 4096
        assert info['circuit_state'] == 'closed'
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_agent_name_property(self):
        """Test agent_name property alias."""
        agent = SkillAgent(skill_id="skill-test", name="My Agent")
        
        assert agent.agent_name == "My Agent"


class TestSkillAgentFactories:
    """Tests for factory functions."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_create_game_enhancer_agent(self):
        """Test game enhancer factory function."""
        agent = create_game_enhancer_agent()
        
        assert agent.skill_id == "skill-react-game-enhancer"
        assert "game" in agent.name.lower() or "react" in agent.name.lower()
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_create_html5_game_designer_agent(self):
        """Test HTML5 game designer factory function."""
        agent = create_html5_game_designer_agent()
        
        assert agent.skill_id == "skill-html_game_dev"
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_create_code_reviewer_agent(self):
        """Test code reviewer factory function."""
        agent = create_code_reviewer_agent()
        
        assert agent.skill_id == "skill-code-reviewer"
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_factory_with_custom_name(self):
        """Test factory with custom name."""
        agent = create_game_enhancer_agent(name="Custom Name")
        
        assert agent.name == "Custom Name"
        assert agent.skill_id == "skill-react-game-enhancer"


class TestSkillAgentAsync:
    """Tests for async functionality."""
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    async def test_agenerate_circuit_open(self):
        """Test that agenerate raises when circuit is open."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Open circuit
        for i in range(SkillAgent.FAILURE_THRESHOLD):
            agent._record_failure(Exception("test"))
        
        with pytest.raises(RuntimeError, match="Circuit breaker OPEN"):
            await agent.agenerate("test prompt")
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('src.startd8.agents.AsyncAnthropic')
    async def test_agenerate_success(self, mock_anthropic):
        """Test successful skill execution."""
        # Setup mock
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        
        mock_response = Mock()
        mock_response.content = [Mock(text="Test response\n---\nContent")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        
        agent = SkillAgent(skill_id="skill-test")
        
        response, time_ms, tokens = await agent.agenerate("test prompt")
        
        assert "Content" in response
        assert tokens.input == 100
        assert tokens.output == 200
```

---

## 5. Integration Examples

### 5.1 Basic Usage

```python
# examples/skill_agent_basic.py

"""Basic SkillAgent usage example."""

import asyncio
from src.startd8.agents import SkillAgent, create_game_enhancer_agent


async def basic_example():
    """Demonstrate basic SkillAgent usage."""
    
    print("=" * 60)
    print("Basic SkillAgent Example")
    print("=" * 60)
    
    # Method 1: Direct instantiation
    agent = SkillAgent(
        skill_id="skill-react-game-enhancer",
        name="My Game Agent"
    )
    
    # Method 2: Factory function
    agent = create_game_enhancer_agent()
    
    print(f"\nAgent: {agent.name}")
    print(f"Skill ID: {agent.skill_id}")
    print(f"Model: {agent.model}")
    
    # Execute skill
    prompt = "Add a simple notification component"
    print(f"\nPrompt: {prompt}")
    
    response, time_ms, tokens = await agent.agenerate(prompt)
    
    print(f"\nResults:")
    print(f"  Time: {time_ms}ms")
    print(f"  Tokens: {tokens.input} in, {tokens.output} out")
    print(f"  Response preview: {response[:200]}...")


if __name__ == "__main__":
    asyncio.run(basic_example())
```

### 5.2 With Cost Tracking

```python
# examples/skill_agent_cost_tracking.py

"""SkillAgent with cost tracking example."""

import asyncio
from src.startd8.agents import SkillAgent
from src.startd8.costs import CostTracker


async def cost_tracking_example():
    """Demonstrate cost tracking with SkillAgent."""
    
    print("=" * 60)
    print("SkillAgent with Cost Tracking")
    print("=" * 60)
    
    # Create cost tracker
    tracker = CostTracker()
    
    # Create agent with tracker
    agent = SkillAgent(
        skill_id="skill-react-game-enhancer",
        name="Tracked Agent",
        cost_tracker=tracker
    )
    
    # Execute multiple requests
    prompts = [
        "Add a health bar component",
        "Add a score display",
        "Add a power-up indicator"
    ]
    
    for prompt in prompts:
        print(f"\nExecuting: {prompt[:40]}...")
        response = await agent.agenerate(prompt)
    
    # Get cost summary
    summary = tracker.get_summary()
    print(f"\n{'='*60}")
    print("Cost Summary:")
    print(f"  Total requests: {summary['total_requests']}")
    print(f"  Total tokens: {summary['total_tokens']}")
    print(f"  Total cost: ${summary['total_cost']:.4f}")


if __name__ == "__main__":
    asyncio.run(cost_tracking_example())
```

---

## 6. Migration Guide

### From ClaudeAgent to SkillAgent

**Before:**
```python
from src.startd8.agents import ClaudeAgent

agent = ClaudeAgent(
    name="developer",
    model="claude-sonnet-4-20250514"
)
response = agent.generate("Write a notification component")
```

**After:**
```python
from src.startd8.agents import SkillAgent

agent = SkillAgent(
    skill_id="skill-react-game-enhancer",
    name="developer",
    model="claude-sonnet-4-20250514"
)
response = await agent.agenerate("Write a notification component")
```

### Key Differences

| Aspect | ClaudeAgent | SkillAgent |
|--------|-------------|------------|
| Primary method | `generate()` sync | `agenerate()` async |
| Execution | Direct API call | Via MCP skill |
| Resilience | None | Circuit breaker |
| Metrics | Token usage | Extended skill metrics |

---

## 7. Troubleshooting

### Common Issues

**"ANTHROPIC_API_KEY not set"**
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

**"Circuit breaker OPEN"**
```python
# Check circuit state
print(agent.get_agent_info()['circuit_state'])

# Manual reset (use carefully)
agent.reset_circuit_breaker()
```

**"No text content found"**
- Verify MCP server is running
- Check skill ID is correct
- Review Claude response format

---

## 8. Next Steps

After implementing this design:

1. **Proceed to**: [MCP_GATEWAY_ARCHITECTURE.md](./MCP_GATEWAY_ARCHITECTURE.md)
2. **Run tests**: `pytest tests/unit/test_skill_agent.py -v`
3. **Integration test**: See [WORKFLOW_INTEGRATION_DESIGN.md](./WORKFLOW_INTEGRATION_DESIGN.md)

---

**Document Status:** ✅ Implemented

**Implementation Notes:**
- Module created at `src/startd8/skills/`
- Exported from main `startd8` package
- Unit tests at `tests/test_skill_agent.py`
- Version bumped to 0.4.0 in `__init__.py`
