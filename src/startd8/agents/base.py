"""
Base agent class and shared utilities.

This module provides:
- BaseAgent: Abstract base class for all LLM agents
- is_completion_model: Utility to detect completion vs chat models
- AgentRegistry: Backward compatibility shim
"""

import asyncio
import logging
import uuid
import warnings
from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple

from ..models import TokenUsage, GenerateResult, StructuredResult, AgentResponse, ResponseMetadata
from ..exceptions import TruncationWarning
from ..truncation_detection import (
    detect_truncation,
    PreFlightEstimate,
    estimate_output_size,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backward compatibility shim
# ---------------------------------------------------------------------------
# Older integrations imported AgentRegistry from `startd8.agents`, but the
# concrete implementation now lives in `startd8.job_queue`.
#
# IMPORTANT: This must be a lazy import to avoid circular imports:
# - `startd8.job_queue` imports agent classes from `startd8.agents`.
def AgentRegistry(*args, **kwargs):  # type: ignore
    from ..job_queue import AgentRegistry as _AgentRegistry
    return _AgentRegistry(*args, **kwargs)


def is_completion_model(model: str) -> bool:
    """
    Check if a model is a completion model (not a chat model).

    Completion models use the /v1/completions endpoint, while chat models
    use the /v1/chat/completions endpoint.

    Args:
        model: Model identifier

    Returns:
        True if model is a completion model, False if chat model
    """
    model_lower = model.lower()

    # Known completion models
    completion_patterns = [
        'text-davinci',  # text-davinci-003, text-davinci-002, etc.
        'gpt-3.5-turbo-instruct',  # Completion variant of turbo
        'text-curie',
        'text-babbage',
        'text-ada',
    ]

    # Check if model matches any completion pattern
    for pattern in completion_patterns:
        if pattern in model_lower:
            return True

    # Chat models typically start with these prefixes
    chat_prefixes = ['gpt-', 'o1-', 'chatgpt-', 'claude-', 'gemini-']
    for prefix in chat_prefixes:
        if model_lower.startswith(prefix):
            return False

    # If model doesn't match known patterns, assume it's a chat model
    # (most modern models are chat models)
    return False


def requires_max_completion_tokens(model: str) -> bool:
    """
    Check whether an OpenAI model rejects ``max_tokens`` and requires
    ``max_completion_tokens`` instead.

    The gpt-5 family and the o-series reasoning models (o1/o3/o4) only accept
    ``max_completion_tokens`` on the chat-completions endpoint, and only support
    the default ``temperature`` (1). Older families (gpt-4o, gpt-4.1, gpt-4-turbo,
    gpt-3.5) continue to use ``max_tokens`` and arbitrary temperatures.

    Args:
        model: Model identifier

    Returns:
        True if the model needs ``max_completion_tokens`` and a default temperature.
    """
    if not model:
        return False
    m = model.lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


# Import cost tracking (optional dependency within the same package)
try:
    from ..costs import CostTracker, BudgetManager, get_cost_context
    from ..costs.budget import BudgetExceededError
    from ..costs.pricing import PricingService
    _COSTS_AVAILABLE = True
except ImportError:
    CostTracker = None
    BudgetManager = None
    get_cost_context = None
    BudgetExceededError = None
    PricingService = None
    _COSTS_AVAILABLE = False


class BaseAgent(ABC):
    """Base class for LLM agents with sync and async support"""

    def __init__(
        self,
        name: str,
        model: str,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        """
        Initialize agent

        Args:
            name: Agent identifier
            model: Model name to use
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
        """
        self.name = name
        self.model = model
        self.cost_tracker = cost_tracker
        self.budget_manager = budget_manager
        self._sync_loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def agent_name(self) -> str:
        """
        Alias for name property for compatibility.

        Some code expects agent.agent_name instead of agent.name.
        This property provides backward compatibility.
        """
        return self.name

    def _get_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create a persistent event loop for synchronous bridge calls.

        Using a persistent loop (instead of ``asyncio.run()`` which
        creates/destroys a loop per call) prevents ``RuntimeError: Event
        loop is closed`` from httpx connections that outlive the loop
        that created them.  This is required on Python 3.12+ where
        asyncio teardown is stricter about pending transports.
        """
        if self._sync_loop is None or self._sync_loop.is_closed():
            self._sync_loop = asyncio.new_event_loop()
        return self._sync_loop

    def cleanup(self):
        """
        Cleanup resources synchronously.

        This should be called before the event loop closes to ensure
        async clients are properly closed.
        """
        # Close the persistent sync loop if we own one
        if self._sync_loop is not None and not self._sync_loop.is_closed():
            try:
                self._sync_loop.close()
            except Exception:
                pass
            self._sync_loop = None

    async def acleanup(self):
        """
        Cleanup resources asynchronously.

        Closes async clients and other async resources.
        """
        # Base implementation - subclasses should override if they have async clients
        pass

    def __del__(self):
        """
        Destructor - attempts cleanup if event loop is still available.

        Suppresses RuntimeError when event loop is closed.
        """
        try:
            # Try to cleanup if possible
            self.cleanup()
        except RuntimeError as e:
            # Suppress "Event loop is closed" errors during destruction
            if 'Event loop is closed' not in str(e):
                # Re-raise if it's a different RuntimeError
                raise
        except Exception as e:
            # Ignore other errors during destruction - event loop may be closed
            # Log at debug level for troubleshooting
            logger.debug(
                f"Error during {self.__class__.__name__} destruction (ignored): {e}",
                exc_info=False,
                extra={"agent_name": self.name, "error_type": type(e).__name__}
            )
            pass

    @abstractmethod
    async def agenerate(self, prompt: str, **kwargs) -> GenerateResult:
        """
        Async generate a response to a prompt.

        This is the primary method that subclasses must implement.

        Args:
            prompt: The prompt text
            **kwargs: Optional per-call overrides. Supported keys:
                - ``system_prompt``: Per-call system prompt override.
                - ``max_tokens``: Per-call max_tokens override (thread-safe
                  alternative to mutating the agent's instance attribute).

        Returns:
            GenerateResult(text, time_ms, token_usage).
            Backward-compatible with tuple unpacking:
            ``text, time_ms, usage = await agent.agenerate(prompt)``
        """
        pass

    async def agenerate_structured(
        self,
        prompt: str,
        output_schema: Any,
        **kwargs: Any,
    ) -> "StructuredResult":
        """
        Generate a result validated against *output_schema* via provider tool-use.

        Returns a :class:`StructuredResult` (``value, raw``) — a sibling of
        :class:`GenerateResult` that leaves the latter's 3-tuple arity untouched. Unpack as
        ``value, raw = await agent.agenerate_structured(prompt, MySchema)``.

        Args:
            prompt: The prompt text.
            output_schema: A Pydantic ``BaseModel`` subclass the result must validate against.
            **kwargs: Per-call overrides (``system_prompt``, ``max_tokens``, ``temperature``,
                ``retry_on_validation``).

        Raises:
            NotImplementedError: Providers that do not yet support structured (tool-use) output.
                A provider counts as structured-output-supported only once its smoke test passes.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support structured (tool-use) output yet"
        )

    def supports_tool_use(self) -> bool:
        """Whether this agent implements :meth:`agenerate_tools` (the agentic-loop primitive).

        Opt-in capability flag (FR-0). Default ``False`` so the 10 existing providers and downstream
        consumers are untouched until a provider's tool-use path passes its smoke test. The agentic
        loop must gate on this before calling :meth:`agenerate_tools`.
        """
        return False

    def supports_streaming(self) -> bool:
        """Whether this agent implements ``agenerate_tools_stream`` (FR-S2).

        Opt-in capability flag, default ``False``. ``AgenticSession.stream()`` gates on this: streaming
        agents drive the live path; others fall back to one text delta from :meth:`agenerate_tools`
        (FR-S6), so consumers get a uniform event stream regardless.
        """
        return False

    async def agenerate_tools(
        self,
        messages: "list[dict] | str",
        tools: list,
        **kwargs: Any,
    ) -> "AgenticTurn":
        """Generate one agentic turn: assistant text + any tool calls the model requested.

        The foundational primitive for the agentic loop (FR-0). Unlike
        :meth:`agenerate_structured` (a *single forced* tool for schema output), this presents N
        tools with no forced choice and returns **all** tool calls plus text, as an
        :class:`AgenticTurn` (a sibling type — ``GenerateResult`` cannot carry tool calls).

        Args:
            messages: The conversation as a **canonical message list** —
                ``[{"role": "user"|"assistant"|"tool", "content": ...}, ...]`` — so the loop can
                thread prior ``tool_use``/``tool_result`` blocks back (a plain string cannot encode
                that pairing; FR-0/R1-F1). A bare ``str`` is accepted as a convenience and wrapped
                into a single user message. Per-provider adapters render this to their native shape.
            tools: Tool specs (provider-native at this primitive boundary; canonical→provider
                translation is owned by the loop's ToolRegistry — FR-9).
            **kwargs: Per-call overrides (``system_prompt``, ``max_tokens``, ``temperature``).

        Raises:
            NotImplementedError: Providers that have not implemented the tool-use primitive.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement agenerate_tools (FR-0) yet"
        )

    @staticmethod
    def _normalize_messages(messages: "list[dict] | str") -> "list[dict]":
        """Convenience: wrap a bare ``str`` into ``[{"role": "user", "content": str}]``.

        FR-0 keeps ``messages`` as the canonical primary shape; this lets simple callers (and the
        existing spike tests) pass a prompt string without building a message list.
        """
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        return list(messages)

    def generate(self, prompt: str, **kwargs: Any) -> GenerateResult:
        """
        Synchronous wrapper for backward compatibility.

        Runs the async method in an event loop.  Any keyword arguments
        (e.g. ``system_prompt``) are forwarded to ``agenerate``.

        Args:
            prompt: The prompt text
            **kwargs: Additional arguments forwarded to ``agenerate``.

        Returns:
            GenerateResult(text, time_ms, token_usage).
            Backward-compatible with tuple unpacking:
            ``text, time_ms, usage = agent.generate(prompt)``
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — use a persistent loop to keep httpx
            # connections alive across calls (prevents Python >=3.12
            # "Event loop is closed" errors from asyncio.run teardown).
            loop = self._get_event_loop()
            return loop.run_until_complete(self.agenerate(prompt, **kwargs))

        # Running inside an existing event loop (e.g. Jupyter/FastAPI).
        # Bridge by running the coroutine in a new thread + event loop.
        import concurrent.futures
        import contextvars

        ctx = contextvars.copy_context()

        def _runner() -> GenerateResult:
            return asyncio.run(self.agenerate(prompt, **kwargs))

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(ctx.run, _runner)
            return future.result()

    def generate_structured(
        self, prompt: str, output_schema: Any, **kwargs: Any
    ) -> "StructuredResult":
        """Synchronous wrapper for :meth:`agenerate_structured` (mirrors :meth:`generate`).

        Lets the owned, **sync** AI-service wrapper (C-1) call the structured path without managing
        an event loop. Unpack as ``value, raw = agent.generate_structured(prompt, MySchema)``.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = self._get_event_loop()
            return loop.run_until_complete(
                self.agenerate_structured(prompt, output_schema, **kwargs)
            )

        import concurrent.futures
        import contextvars

        ctx = contextvars.copy_context()

        def _runner() -> "StructuredResult":
            return asyncio.run(self.agenerate_structured(prompt, output_schema, **kwargs))

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(ctx.run, _runner)
            return future.result()

    async def _run_with_cost_tracking(
        self,
        prompt: str,
        prompt_id: str,
        response_id: str,
        metadata: Optional['ResponseMetadata'] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None,
        pipeline_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> GenerateResult:
        """
        Execute API call with cost tracking and budget enforcement.

        This helper method orchestrates:
        1. Pre-call budget check (if budget_manager is configured)
        2. API call execution (agenerate)
        3. Post-call cost recording (if cost_tracker is configured)

        Args:
            prompt: The prompt text
            prompt_id: ID of the prompt (for cost record)
            response_id: ID of the response (unique identifier linking cost record to response)
            metadata: Optional metadata to include in cost record
            project: Optional project identifier (overrides context default)
            tags: Optional tags (merged with context tags)
            pipeline_id: Optional pipeline ID for attribution
            job_id: Optional job ID for attribution

        Returns:
            GenerateResult(text, time_ms, token_usage)

        Raises:
            BudgetExceededError: If budget check fails with block_on_exceed=True
        """
        # STEP 1: Pre-call budget check
        # Note: Budget enforcement works independently from cost tracking
        # We only need budget_manager, not cost_tracker
        if self.budget_manager and _COSTS_AVAILABLE:
            # Get context defaults (Phase 1 integration)
            context = get_cost_context() if get_cost_context else {}

            # Use explicit project or fall back to context default
            effective_project = project or context.get("project")

            # Estimate cost from pricing service
            # Use cost_tracker's pricing if available, otherwise create a new PricingService
            if self.cost_tracker:
                pricing = self.cost_tracker.pricing
            else:
                pricing = PricingService()

            estimated_cost = pricing.estimate_cost(
                model=self.model,
                prompt_chars=len(prompt),
                expected_output_chars=500  # Conservative estimate
            )

            # Check budget (may raise BudgetExceededError if block_on_exceed=True)
            if effective_project:
                self.budget_manager.check_budget(
                    model=self.model,
                    project=effective_project,
                    tags=tags or context.get("tags", []),
                    estimated_cost=estimated_cost
                )

        # STEP 2: Execute API call
        result = await self.agenerate(prompt)
        response_text, response_time_ms, token_usage = result

        # STEP 3: Post-call cost recording
        if self.cost_tracker and _COSTS_AVAILABLE:
            # Get context defaults for recording (Phase 1 integration)
            context = get_cost_context() if get_cost_context else {}

            # Use explicit project or fall back to context default
            effective_project = project or context.get("project")

            # Merge explicit tags with context tags (decision A3)
            context_tags = context.get("tags", []) if context else []
            effective_tags = list(set((tags or []) + context_tags))

            # Record actual cost with token usage
            self.cost_tracker.record_cost(
                agent_name=self.name,
                model=self.model,
                input_tokens=token_usage.input,
                output_tokens=token_usage.output,
                cache_creation_input_tokens=getattr(token_usage, "cache_creation_input_tokens", None),
                cache_read_input_tokens=getattr(token_usage, "cache_read_input_tokens", None),
                tags=effective_tags,
                project=effective_project,
                prompt_id=prompt_id,
                response_id=response_id,
                pipeline_id=pipeline_id,
                job_id=job_id,
                metadata=metadata or {}
            )
            # COST_RECORDED event is emitted automatically by record_cost()

        return result

    def _check_for_truncation(
        self,
        response: AgentResponse,
        original_prompt: str = None
    ) -> None:
        """
        Check for truncation using both API finish_reason and heuristic detection.

        Issues a TruncationWarning if truncation is detected.

        Args:
            response: The AgentResponse to check
            original_prompt: Original prompt text (for length comparison)
        """
        truncation_detected = False
        finish_reason = None
        indicators = []
        confidence = 0.0

        # Check API-level truncation via finish_reason
        if response.token_usage and response.token_usage.was_truncated:
            truncation_detected = True
            finish_reason = response.token_usage.finish_reason
            indicators.append(f"API finish_reason: {finish_reason}")
            confidence = 1.0  # API says it was truncated - definitive

        # Also run heuristic detection for additional signals
        heuristic_result = detect_truncation(
            output=response.response,
            original_input=original_prompt,
            strict_mode=False
        )

        if heuristic_result.is_truncated:
            truncation_detected = True
            indicators.extend(heuristic_result.indicators)
            # Use max confidence between API and heuristic
            confidence = max(confidence, heuristic_result.confidence)

        # Store truncation info in response metadata
        if truncation_detected:
            response.metadata['truncation_detected'] = True
            response.metadata['truncation_indicators'] = indicators
            response.metadata['truncation_confidence'] = confidence

            # Get max_tokens from the agent if available
            max_tokens = getattr(self, 'max_tokens', None)

            # Issue warning
            warning_msg = (
                f"Response from {self.name} appears truncated. "
                f"Indicators: {', '.join(indicators[:3])}{'...' if len(indicators) > 3 else ''}. "
                f"Confidence: {confidence:.0%}"
            )

            warnings.warn(
                TruncationWarning(
                    warning_msg,
                    agent_name=self.name,
                    finish_reason=finish_reason,
                    output_tokens=response.token_usage.output if response.token_usage else None,
                    max_tokens=max_tokens,
                    indicators=indicators,
                    confidence=confidence
                ),
                stacklevel=3  # Point to the caller's caller
            )

            logger.warning(
                warning_msg,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "finish_reason": finish_reason,
                    "indicators": indicators,
                    "confidence": confidence,
                    "response_id": response.id,
                }
            )

    async def acreate_response(
        self,
        prompt_id: str,
        prompt: str,
        metadata: Optional[ResponseMetadata] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None,
        pipeline_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> AgentResponse:
        """
        Async generate and create an AgentResponse object

        Integrates with cost tracking and budget enforcement if configured.

        Args:
            prompt_id: ID of the prompt
            prompt: Prompt text
            metadata: Optional metadata
            project: Optional project identifier (overrides context default)
            tags: Optional tags (merged with context tags)
            pipeline_id: Optional pipeline ID for attribution
            job_id: Optional job ID for attribution

        Returns:
            AgentResponse object

        Raises:
            BudgetExceededError: If budget check fails with block_on_exceed=True
        """
        # Generate response_id once at the start to ensure cost record and response use the same ID
        response_id = f"response-{uuid.uuid4().hex[:12]}"

        # Use cost/budget helper if either is configured.
        # Budget enforcement must work even when cost_tracker is not present.
        if _COSTS_AVAILABLE and (self.cost_tracker or self.budget_manager):
            response_text, response_time_ms, token_usage = await self._run_with_cost_tracking(
                prompt=prompt,
                prompt_id=prompt_id,
                response_id=response_id,
                metadata=metadata,
                project=project,
                tags=tags,
                pipeline_id=pipeline_id,
                job_id=job_id,
            )
        else:
            # Direct call without cost tracking
            response_text, response_time_ms, token_usage = await self.agenerate(prompt)

        response_obj = AgentResponse(
            id=response_id,
            prompt_id=prompt_id,
            agent_name=self.name,
            model=self.model,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            metadata=metadata or {}
        )

        # Check for truncation using heuristics (second layer of defense)
        self._check_for_truncation(response_obj, prompt)

        return response_obj

    def create_response(
        self,
        prompt_id: str,
        prompt: str,
        metadata: Optional[ResponseMetadata] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None,
        pipeline_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> AgentResponse:
        """
        Generate and create an AgentResponse object (sync wrapper)

        Integrates with cost tracking and budget enforcement if configured.
        Bridges sync code to async cost tracking pipeline.

        Args:
            prompt_id: ID of the prompt
            prompt: Prompt text
            metadata: Optional metadata
            project: Optional project identifier (overrides context default)
            tags: Optional tags (merged with context tags)
            pipeline_id: Optional pipeline ID for attribution
            job_id: Optional job ID for attribution

        Returns:
            AgentResponse object

        Raises:
            BudgetExceededError: If budget check fails with block_on_exceed=True
        """
        # Generate response_id once at the start to ensure cost record and response use the same ID
        response_id = f"response-{uuid.uuid4().hex[:12]}"

        # Use cost/budget helper via asyncio bridge if either is configured.
        # Budget enforcement must work even when cost_tracker is not present.
        if _COSTS_AVAILABLE and (self.cost_tracker or self.budget_manager):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # No running loop — use persistent loop (same as generate())
                loop = self._get_event_loop()
                response_text, response_time_ms, token_usage = loop.run_until_complete(
                    self._run_with_cost_tracking(
                        prompt=prompt,
                        prompt_id=prompt_id,
                        response_id=response_id,
                        metadata=metadata,
                        project=project,
                        tags=tags,
                        pipeline_id=pipeline_id,
                        job_id=job_id,
                    )
                )
            else:
                # Running inside an existing event loop (e.g. Jupyter/FastAPI).
                # Bridge by running the coroutine in a new thread + event loop.
                import concurrent.futures
                import contextvars

                ctx = contextvars.copy_context()

                def _runner() -> GenerateResult:
                    return asyncio.run(
                        self._run_with_cost_tracking(
                            prompt=prompt,
                            prompt_id=prompt_id,
                            response_id=response_id,
                            metadata=metadata,
                            project=project,
                            tags=tags,
                            pipeline_id=pipeline_id,
                            job_id=job_id,
                        )
                    )

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(ctx.run, _runner)
                    response_text, response_time_ms, token_usage = future.result()
        else:
            # Direct call without cost tracking
            response_text, response_time_ms, token_usage = self.generate(prompt)

        response_obj = AgentResponse(
            id=response_id,
            prompt_id=prompt_id,
            agent_name=self.name,
            model=self.model,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            metadata=metadata or {}
        )

        # Check for truncation using heuristics (second layer of defense)
        self._check_for_truncation(response_obj, prompt)

        return response_obj

    def _pre_flight_check(
        self,
        task_description: str,
        inputs: Optional[dict] = None,
        safe_line_limit: int = 150,
        safe_token_limit: int = 500,
    ) -> PreFlightEstimate:
        """
        Perform pre-flight size estimation BEFORE generation.

        This is the proactive truncation prevention pattern: estimate output
        size before generation and provide warnings/recommendations if the
        output is likely to exceed safe limits.

        Args:
            task_description: Natural language description of what to generate
            inputs: Additional context (target_file, required_exports, etc.)
            safe_line_limit: Maximum safe lines for output (default 150)
            safe_token_limit: Maximum safe tokens for output (default 500)

        Returns:
            PreFlightEstimate with size prediction and recommended action

        Example:
            estimate = agent._pre_flight_check(
                "Implement a REST API client with CRUD operations",
                inputs={"required_exports": ["APIClient"]}
            )

            if estimate.exceeds_limit:
                logger.warning(f"Task may be too large: {estimate.reasoning}")
                if estimate.suggested_action == "decompose":
                    # Split into smaller tasks
                    pass
        """
        return estimate_output_size(
            task_description=task_description,
            inputs=inputs,
            safe_line_limit=safe_line_limit,
            safe_token_limit=safe_token_limit,
        )

    async def agenerate_with_validation(
        self,
        prompt: str,
        task_description: Optional[str] = None,
        inputs: Optional[dict] = None,
        safe_line_limit: int = 150,
        safe_token_limit: int = 500,
        strict: bool = False,
    ) -> Tuple[str, int, TokenUsage, Optional[PreFlightEstimate]]:
        """
        Generate with pre-flight validation and post-generation truncation check.

        This method combines proactive (pre-flight) and reactive (post-generation)
        truncation prevention for comprehensive protection.

        Args:
            prompt: The prompt text
            task_description: Optional description for pre-flight estimation
                             (if None, skips pre-flight check)
            inputs: Additional context for pre-flight estimation
            safe_line_limit: Maximum safe lines for output
            safe_token_limit: Maximum safe tokens for output
            strict: If True, raise exception when limits exceeded

        Returns:
            Tuple of (response_text, response_time_ms, token_usage, pre_flight_estimate)
            pre_flight_estimate is None if task_description was not provided

        Raises:
            ValueError: If strict=True and pre-flight estimate exceeds limits

        Example:
            response, time_ms, usage, estimate = await agent.agenerate_with_validation(
                prompt="Generate the FooBar class...",
                task_description="Implement FooBar class with 5 methods",
                inputs={"required_exports": ["FooBar"]},
                strict=False,
            )

            if estimate and estimate.exceeds_limit:
                logger.warning(f"Output may be truncated: {estimate.reasoning}")
        """
        pre_flight_estimate = None

        # Step 1: Pre-flight check (if task_description provided)
        if task_description:
            pre_flight_estimate = self._pre_flight_check(
                task_description=task_description,
                inputs=inputs,
                safe_line_limit=safe_line_limit,
                safe_token_limit=safe_token_limit,
            )

            if pre_flight_estimate.exceeds_limit:
                warning_msg = (
                    f"Pre-flight check warning for {self.name}: "
                    f"{pre_flight_estimate.reasoning}. "
                    f"Suggested action: {pre_flight_estimate.suggested_action}"
                )
                logger.warning(
                    warning_msg,
                    extra={
                        "agent_name": self.name,
                        "model": self.model,
                        "estimated_lines": pre_flight_estimate.estimated_lines,
                        "safe_line_limit": safe_line_limit,
                        "suggested_action": pre_flight_estimate.suggested_action,
                    }
                )

                if strict and pre_flight_estimate.suggested_action == "reject":
                    raise ValueError(
                        f"Pre-flight check rejected task: {pre_flight_estimate.reasoning}"
                    )

        # Step 2: Generate
        response_text, response_time_ms, token_usage = await self.agenerate(prompt)

        # Step 3: Post-generation truncation check
        truncation_result = detect_truncation(
            output=response_text,
            original_input=prompt,
            strict_mode=strict,
        )

        if truncation_result.is_truncated:
            warning_msg = (
                f"Truncation detected in output from {self.name}. "
                f"Confidence: {truncation_result.confidence:.0%}. "
                f"Indicators: {', '.join(truncation_result.indicators[:3])}"
            )
            logger.warning(
                warning_msg,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "truncation_confidence": truncation_result.confidence,
                    "truncation_indicators": truncation_result.indicators,
                    "pre_flight_estimated_lines": pre_flight_estimate.estimated_lines if pre_flight_estimate else None,
                }
            )

            if strict:
                warnings.warn(
                    TruncationWarning(
                        warning_msg,
                        agent_name=self.name,
                        indicators=truncation_result.indicators,
                        confidence=truncation_result.confidence,
                    ),
                    stacklevel=2,
                )

        return response_text, response_time_ms, token_usage, pre_flight_estimate
