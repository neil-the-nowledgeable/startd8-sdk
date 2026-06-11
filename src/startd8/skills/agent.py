"""
SkillAgent - Agent that executes Claude Skills via MCP

This module contains the core SkillAgent class which bridges the startd8 SDK
with Claude Skills through the Model Context Protocol (MCP).

Design Document: design/SKILL_AGENT_CORE_DESIGN.md

.. note::
   **Skill execution mechanism (fixed 2026-06-11).** :meth:`SkillAgent._call_mcp_skill` and the
   gateway's ``_execute_mcp_skill`` now load the skill's ``SKILL.md`` via :func:`resolve_skill_md`
   (``~/.claude/skills/<id>/SKILL.md``) and inject it as the model's **system prompt**, so the
   skill's actual instructions steer the response. The old behavior — a phantom ``startd8_use_skill``
   tool that was never executed and never loaded skill content, sending only ``"Execute the
   {skill_id} skill ..."`` — has been removed (it produced generic base-model output falsely
   attributed to the skill; the Presentation Polish OQ-8 spike caught it). **Caveat:** when the
   skill isn't installed on disk, :func:`resolve_skill_md` returns ``None`` and the call runs without
   skill instructions (a warning is logged) — so output is only skill-driven when the skill is
   present. ``_discover_skills`` still registers metadata stubs (it does not enumerate disk skills).
"""

import os
import time
import asyncio
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field

from ..agents import BaseAgent
from ..models import TokenUsage, GenerateResult
from ..logging_config import get_logger

# Conditional imports
try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None
    _ANTHROPIC_AVAILABLE = False

try:
    from ..costs import CostTracker, BudgetManager
    _COSTS_AVAILABLE = True
except ImportError:
    CostTracker = None
    BudgetManager = None
    _COSTS_AVAILABLE = False

logger = get_logger(__name__)


def resolve_skill_md(skill_id: str) -> Optional[str]:
    """Find and read a Claude Code skill's ``SKILL.md`` from disk; return its content or ``None``.

    Looks under ``~/.claude/skills/<id>/SKILL.md`` (trying the id both as-is and with a leading
    ``skill-`` stripped, since on-disk dirs are often un-prefixed, e.g. ``frontend-design``), then
    best-effort under ``~/.claude/plugins/**/skills/<id>/SKILL.md``. This is the real mechanism that
    lets the SDK actually *use* a skill: its instructions are injected as the model's system prompt.
    Returns ``None`` (caller degrades gracefully) when the skill isn't installed.
    """
    names = [skill_id]
    if skill_id.startswith("skill-"):
        names.append(skill_id[len("skill-") :])
    home = Path.home() / ".claude"
    candidates = [home / "skills" / n / "SKILL.md" for n in names]
    plugins = home / "plugins"
    if plugins.is_dir():
        for n in names:
            candidates.extend(plugins.glob(f"**/skills/{n}/SKILL.md"))
    for path in candidates:
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable file → try the next candidate
            continue
    return None


class CircuitState(str, Enum):
    """Circuit breaker states for resilience pattern.
    
    States:
        CLOSED: Normal operation, requests flow through
        OPEN: Failing fast, requests are rejected immediately
        HALF_OPEN: Testing recovery, limited requests allowed
    """
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class SkillMetrics:
    """Metrics collected from skill execution.
    
    Attributes:
        execution_time_ms: Time to execute the skill in milliseconds
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
        skill_reported_time_ms: Time reported by the skill itself (if available)
        cache_hit: Whether the response was served from cache
        circuit_state: Circuit breaker state at time of execution
    """
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
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 32768
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
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
        timeout_ms: int = 30000,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        mcp_gateway: Optional[Any] = None,  # MCPGateway type hint (Phase 2)
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
            mcp_gateway: Optional shared MCP gateway for connection pooling (Phase 2)
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
            "SkillAgent initialized",
            extra={
                'skill_id': self.skill_id,
                'agent_name': self.name,
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
        2. Anthropic SDK availability is validated at call time (lazy)
        
        Raises:
            RuntimeError: If MCP is not available or not configured
        """
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
    
    async def agenerate(self, prompt: str) -> GenerateResult:
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
            GenerateResult(text, time_ms, token_usage)
            
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
                # Use shared gateway (preferred for production - Phase 2)
                response, tokens = await self._call_via_gateway(prompt)
            else:
                # Direct MCP call (Phase 1)
                response, tokens = await self._call_mcp_skill(prompt)
            
            # Parse response
            response_text, skill_metrics = self._parse_skill_response(response)
            
            # Calculate metrics
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Build token usage
            token_usage = TokenUsage(
                input=tokens.get("input", 0),
                output=tokens.get("output", 0),
                total=tokens.get("input", 0) + tokens.get("output", 0),
                model_name=self.model,
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
            
            return GenerateResult(response_text, response_time_ms, token_usage)

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
        Execute skill via shared MCP gateway (Phase 2).
        
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
        Call startd8 MCP skill execution tool directly (Phase 1).
        
        This method creates a new Anthropic client for each call.
        For production, use mcp_gateway for connection pooling (Phase 2).
        
        Args:
            prompt: The skill prompt/task
            
        Returns:
            Tuple of (response_text, token_metrics)
        """
        if AsyncAnthropic is None:
            raise RuntimeError(
                "Anthropic SDK not installed. Install with: pip install anthropic"
            )
        client = AsyncAnthropic()
        
        # Load the skill's instructions and inject them as the SYSTEM PROMPT — the real mechanism
        # for *using* a skill. (The old path declared a phantom `startd8_use_skill` tool that was
        # never executed and never loaded SKILL.md, so output was generic base-model text falsely
        # attributed to the skill. Fixed: resolve_skill_md() reads ~/.claude/skills/<id>/SKILL.md.)
        skill_md = resolve_skill_md(self.skill_id)
        create_kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if skill_md:
            create_kwargs["system"] = skill_md
        else:
            logger.warning(
                "SkillAgent: no SKILL.md found for '%s' under ~/.claude/skills — running WITHOUT "
                "skill instructions; output will be generic, not skill-driven.",
                self.skill_id,
            )

        response = await asyncio.wait_for(
            client.messages.create(**create_kwargs),
            timeout=self.timeout_ms / 1000,  # Convert to seconds
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
    
    # Note: agent_name property is inherited from BaseAgent, no need to override
