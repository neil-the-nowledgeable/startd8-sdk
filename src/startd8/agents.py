"""
Agent implementations for different LLM providers
"""

import os
import time
import asyncio
import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple

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
    from .job_queue import AgentRegistry as _AgentRegistry
    return _AgentRegistry(*args, **kwargs)

# Optional dependencies - import with clear error messages
try:
    from anthropic import Anthropic, AsyncAnthropic
    from anthropic import APIConnectionError as AnthropicAPIConnectionError
except ImportError:
    Anthropic = None
    AsyncAnthropic = None
    AnthropicAPIConnectionError = None
    _ANTHROPIC_AVAILABLE = False
else:
    _ANTHROPIC_AVAILABLE = True

try:
    from openai import OpenAI, AsyncOpenAI
    from openai import APIConnectionError as OpenAIAPIConnectionError
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    OpenAIAPIConnectionError = None
    _OPENAI_AVAILABLE = False
else:
    _OPENAI_AVAILABLE = True


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

try:
    from google import genai
    from google.genai import types as genai_types
    _GEMINI_AVAILABLE = True
    _GEMINI_IMPORT_ERROR = None
except ImportError as e:
    genai = None
    genai_types = None
    _GEMINI_AVAILABLE = False
    _GEMINI_IMPORT_ERROR = str(e)

from .models import TokenUsage, AgentResponse, ResponseMetadata
from .utils.retry import RetryConfig, RetryError, with_retry


@dataclass
class TimeoutConfig:
    """
    Timeout configuration for agent HTTP requests.

    All timeouts are in seconds. Uses httpx.Timeout under the hood.

    Attributes:
        connect: Timeout for establishing a connection. Default: 10.0
        read: Timeout for reading response data. Default: 120.0
        write: Timeout for sending request data. Default: 30.0
        pool: Timeout for acquiring a connection from the pool. Default: 10.0

    Example:
        ```python
        from startd8.agents import ClaudeAgent, TimeoutConfig

        # Quick timeouts for fast-fail behavior
        fast_timeout = TimeoutConfig(connect=5.0, read=30.0)
        agent = ClaudeAgent(name="claude", timeout_config=fast_timeout)

        # Long timeouts for complex requests
        slow_timeout = TimeoutConfig(read=300.0)
        agent = ClaudeAgent(name="claude", timeout_config=slow_timeout)
        ```
    """

    connect: float = 10.0
    read: float = 120.0
    write: float = 30.0
    pool: float = 10.0

    def __post_init__(self):
        if self.connect < 0:
            raise ValueError("connect timeout must be non-negative")
        if self.read < 0:
            raise ValueError("read timeout must be non-negative")
        if self.write < 0:
            raise ValueError("write timeout must be non-negative")
        if self.pool < 0:
            raise ValueError("pool timeout must be non-negative")

    def to_httpx_timeout(self):
        """
        Convert to httpx.Timeout object.

        Returns:
            httpx.Timeout configured with these settings
        """
        import httpx
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool,
        )

# Import cost tracking (optional dependency within the same package)
try:
    from .costs import CostTracker, BudgetManager, get_cost_context
    from .costs.budget import BudgetExceededError
    from .costs.pricing import PricingService
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
    
    @property
    def agent_name(self) -> str:
        """
        Alias for name property for compatibility.

        Some code expects agent.agent_name instead of agent.name.
        This property provides backward compatibility.
        """
        return self.name
    
    def cleanup(self):
        """
        Cleanup resources synchronously.
        
        This should be called before the event loop closes to ensure
        async clients are properly closed.
        """
        # Base implementation - subclasses should override if they have async clients
        pass
    
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
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Async generate a response to a prompt.
        
        This is the primary method that subclasses must implement.
        
        Args:
            prompt: The prompt text
            
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
        """
        pass
    
    def generate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Synchronous wrapper for backward compatibility.
        
        Runs the async method in an event loop.
        
        Args:
            prompt: The prompt text
            
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.agenerate(prompt))

        # Running inside an existing event loop (e.g. Jupyter/FastAPI).
        # Bridge by running the coroutine in a new thread + event loop.
        import concurrent.futures
        import contextvars

        ctx = contextvars.copy_context()

        def _runner() -> Tuple[str, int, TokenUsage]:
            return asyncio.run(self.agenerate(prompt))

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
    ) -> Tuple[str, int, TokenUsage]:
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
            Tuple of (response_text, response_time_ms, token_usage)
            
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
        response_text, response_time_ms, token_usage = await self.agenerate(prompt)
        
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
                tags=effective_tags,
                project=effective_project,
                prompt_id=prompt_id,
                response_id=response_id,
                pipeline_id=pipeline_id,
                job_id=job_id,
                metadata=metadata or {}
            )
            # COST_RECORDED event is emitted automatically by record_cost()
        
        return response_text, response_time_ms, token_usage
    
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
        
        return AgentResponse(
            id=response_id,
            prompt_id=prompt_id,
            agent_name=self.name,
            model=self.model,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            metadata=metadata or {}
        )
    
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
                # No running loop, safe to use asyncio.run directly
                response_text, response_time_ms, token_usage = asyncio.run(
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

                def _runner() -> Tuple[str, int, TokenUsage]:
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
        
        return AgentResponse(
            id=response_id,
            prompt_id=prompt_id,
            agent_name=self.name,
            model=self.model,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            metadata=metadata or {}
        )


class ClaudeAgent(BaseAgent):
    """Anthropic Claude agent with async support, optional retry, and configurable timeouts"""

    # Default retry configuration for Claude API calls
    DEFAULT_RETRY_CONFIG = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=60.0,
        retryable_status_codes=(429, 500, 502, 503, 504, 529),  # 529 = Anthropic overloaded
    )

    # Default timeout configuration
    DEFAULT_TIMEOUT_CONFIG = TimeoutConfig()

    def __init__(
        self,
        name: str = "claude",
        model: str = "claude-3-opus-20240229",  # Most stable, widely available model
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
        """
        Initialize Claude agent

        Args:
            name: Agent identifier
            model: Claude model to use
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            max_tokens: Maximum tokens to generate
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
            retry_config: Optional retry configuration. If None and enable_retry=True,
                uses DEFAULT_RETRY_CONFIG. If None and enable_retry=False, no retries.
            enable_retry: Enable retry with default config. Ignored if retry_config is provided.
            timeout_config: Optional timeout configuration. If None, uses DEFAULT_TIMEOUT_CONFIG.
        """
        super().__init__(name, model, cost_tracker, budget_manager)

        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install startd8[anthropic] or pip install anthropic"
            )

        # Configure timeout
        self.timeout_config = timeout_config or self.DEFAULT_TIMEOUT_CONFIG
        httpx_timeout = self.timeout_config.to_httpx_timeout()

        self.client = Anthropic(api_key=api_key, timeout=httpx_timeout)
        self.async_client = AsyncAnthropic(api_key=api_key, timeout=httpx_timeout)
        self.max_tokens = max_tokens

        # Configure retry behavior
        if retry_config is not None:
            self.retry_config = retry_config
        elif enable_retry:
            self.retry_config = self.DEFAULT_RETRY_CONFIG
        else:
            self.retry_config = None

        self._cleanup_registered = False
        self._register_cleanup()
    
    def _register_cleanup(self):
        """Register cleanup handler to run on exit"""
        if not self._cleanup_registered:
            import atexit
            atexit.register(self.cleanup)
            self._cleanup_registered = True
    
    def cleanup(self):
        """
        Cleanup async client resources.
        
        Handles cleanup gracefully even if event loop is closed.
        """
        if hasattr(self, 'async_client') and self.async_client:
            try:
                # Check if we can access the underlying httpx client
                client = None
                if hasattr(self.async_client, '_client'):
                    client = self.async_client._client
                elif hasattr(self.async_client, 'client'):
                    client = self.async_client.client
                
                if client and hasattr(client, 'aclose'):
                    # Try to close if event loop is available
                    try:
                        loop = asyncio.get_running_loop()
                        if not loop.is_closed():
                            # Schedule cleanup task
                            try:
                                asyncio.create_task(client.aclose())
                            except RuntimeError:
                                # Event loop closing, can't schedule tasks
                                pass
                    except RuntimeError:
                        # No running loop - event loop may be closed
                        # Try to get event loop, but handle closed case
                        try:
                            loop = asyncio.get_event_loop()
                            if not loop.is_closed():
                                try:
                                    loop.run_until_complete(client.aclose())
                                except RuntimeError:
                                    # Event loop is closing/closed
                                    pass
                        except RuntimeError:
                            # Event loop is closed or doesn't exist
                            # httpx will cleanup on Python exit
                            pass
            except Exception as e:
                # Ignore all cleanup errors - event loop may be closed
                # Log at debug level for troubleshooting
                logger.debug(
                    f"Error during {self.__class__.__name__} cleanup (ignored): {e}",
                    exc_info=False,
                    extra={"agent_name": self.name, "error_type": type(e).__name__}
                )
                pass
    
    async def acleanup(self):
        """
        Async cleanup - properly closes async client.
        
        Should be called before event loop closes.
        """
        if hasattr(self, 'async_client') and self.async_client:
            try:
                # Close the underlying httpx client if it exists
                client = None
                if hasattr(self.async_client, '_client'):
                    client = self.async_client._client
                elif hasattr(self.async_client, 'client'):
                    client = self.async_client.client
                
                if client and hasattr(client, 'aclose'):
                    try:
                        await client.aclose()
                    except RuntimeError as e:
                        # Event loop is closed - this is expected during shutdown
                        if 'Event loop is closed' not in str(e):
                            # Re-raise if it's a different RuntimeError
                            raise
            except RuntimeError as e:
                # Event loop is closed - this is expected during shutdown
                if 'Event loop is closed' not in str(e):
                    raise
            except Exception as e:
                # Ignore other cleanup errors
                # Log at debug level for troubleshooting
                logger.debug(
                    f"Error during {self.__class__.__name__} cleanup (ignored): {e}",
                    exc_info=False,
                    extra={"agent_name": self.name, "error_type": type(e).__name__}
                )
                pass
    
    async def _make_api_call(self, prompt: str):
        """
        Make the raw API call to Anthropic.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.
        """
        return await self.async_client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Generate response using Claude async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text to send

        Returns:
            Tuple of (response_text, response_time_ms, token_usage)

        Raises:
            AgentError: For DNS/connection errors that can't be retried
            APIError: For API errors
            RetryError: If all retry attempts are exhausted (when retry enabled)
        """
        start_time = time.time()

        try:
            # Use retry wrapper if configured
            if self.retry_config is not None:
                make_call = with_retry(self.retry_config)(self._make_api_call)
                response = await make_call(prompt)
            else:
                response = await self._make_api_call(prompt)

        except RetryError as e:
            # All retry attempts exhausted
            from .logging_config import get_logger
            from .exceptions import APIError

            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            logger.error(
                f"All retry attempts exhausted for {self.name}: {e.last_exception}",
                exc_info=False,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "retry_attempts": e.attempts,
                    "total_retry_time": e.total_time,
                }
            )

            raise APIError(
                f"API call failed after {e.attempts} attempts: {e.last_exception}",
                provider=self.name,
                original_error=e.last_exception,
            ) from e

        except (AnthropicAPIConnectionError, ConnectionError, OSError) as e:
            # Specific connection/network errors (only reached if retry not enabled
            # or if it's a non-retryable connection error like DNS failure)
            from .logging_config import get_logger
            from .exceptions import APIError, AgentError

            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            error_msg = str(e)

            # Check for DNS/connection errors specifically
            if AnthropicAPIConnectionError and isinstance(e, AnthropicAPIConnectionError):
                # Check for DNS resolution failures in error message or underlying exception
                underlying_error = getattr(e, 'cause', None) or getattr(e, '__cause__', None)
                underlying_msg = str(underlying_error) if underlying_error else ""
                combined_msg = f"{error_msg} {underlying_msg}".lower()

                if any(term in combined_msg for term in ["nodename nor servname", "getaddrinfo", "not known", "name or service not known", "name resolution"]):
                    dns_error_msg = (
                        f"DNS resolution failed for Anthropic API endpoint. "
                        f"The endpoint may be unreachable or there may be network connectivity issues. "
                        f"Please check your network connection and API configuration for agent '{self.name}'."
                    )
                    logger.error(
                        f"DNS resolution failed for {self.name}: {e}",
                        exc_info=True,
                        extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                    )
                    raise AgentError(
                        dns_error_msg,
                        agent_name=self.name,
                        original_error=e
                    ) from e

            # Log and wrap all connection/network errors as APIError
            logger.error(
                f"API call failed for {self.name}: {e}",
                exc_info=True,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "error_type": type(e).__name__,
                    "operation": "agenerate"
                }
            )

            raise APIError(
                f"API call failed: {str(e)}",
                provider=self.name,
                original_error=e
            ) from e

        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)

        response_text = response.content[0].text

        token_usage = TokenUsage(
            input=response.usage.input_tokens,
            output=response.usage.output_tokens,
            total=response.usage.input_tokens + response.usage.output_tokens,
            model_name=self.model,
        )

        return response_text, response_time_ms, token_usage


class GPT4Agent(BaseAgent):
    """OpenAI GPT-4 agent with async support, optional retry, and configurable timeouts"""

    # Default retry configuration for OpenAI API calls
    DEFAULT_RETRY_CONFIG = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=60.0,
        retryable_status_codes=(429, 500, 502, 503, 504),
    )

    # Default timeout configuration
    DEFAULT_TIMEOUT_CONFIG = TimeoutConfig()

    def __init__(
        self,
        name: str = "gpt4",
        model: str = "gpt-4-turbo-preview",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
        """
        Initialize GPT-4 agent

        Args:
            name: Agent identifier
            model: GPT model to use
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            max_tokens: Maximum tokens to generate
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
            retry_config: Optional retry configuration. If None and enable_retry=True,
                uses DEFAULT_RETRY_CONFIG. If None and enable_retry=False, no retries.
            enable_retry: Enable retry with default config. Ignored if retry_config is provided.
            timeout_config: Optional timeout configuration. If None, uses DEFAULT_TIMEOUT_CONFIG.
        """
        super().__init__(name, model, cost_tracker, budget_manager)

        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install startd8[openai] or pip install openai"
            )

        # Configure timeout
        self.timeout_config = timeout_config or self.DEFAULT_TIMEOUT_CONFIG
        httpx_timeout = self.timeout_config.to_httpx_timeout()

        self.client = OpenAI(api_key=api_key, timeout=httpx_timeout)
        self.async_client = AsyncOpenAI(api_key=api_key, timeout=httpx_timeout)
        self.max_tokens = max_tokens

        # Configure retry behavior
        if retry_config is not None:
            self.retry_config = retry_config
        elif enable_retry:
            self.retry_config = self.DEFAULT_RETRY_CONFIG
        else:
            self.retry_config = None

    async def _make_api_call(self, prompt: str):
        """
        Make the raw API call to OpenAI.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.
        """
        return await self.async_client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Generate response using GPT-4 async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text to send

        Returns:
            Tuple of (response_text, response_time_ms, token_usage)

        Raises:
            AgentError: For model errors or DNS/connection errors that can't be retried
            APIError: For API errors
            RetryError: If all retry attempts are exhausted (when retry enabled)
        """
        start_time = time.time()

        try:
            # Use retry wrapper if configured
            if self.retry_config is not None:
                make_call = with_retry(self.retry_config)(self._make_api_call)
                response = await make_call(prompt)
            else:
                response = await self._make_api_call(prompt)

        except RetryError as e:
            # All retry attempts exhausted
            from .logging_config import get_logger
            from .exceptions import APIError

            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            logger.error(
                f"All retry attempts exhausted for {self.name}: {e.last_exception}",
                exc_info=False,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "retry_attempts": e.attempts,
                    "total_retry_time": e.total_time,
                }
            )

            raise APIError(
                f"API call failed after {e.attempts} attempts: {e.last_exception}",
                provider=self.name,
                original_error=e.last_exception,
            ) from e

        except Exception as e:
            from .logging_config import get_logger
            from .exceptions import APIError, AgentError

            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            error_msg = str(e)
            error_msg_lower = error_msg.lower()

            # Check for completion model error (404 - not a chat model)
            # Only raise this error if we're confident it's actually a completion model issue
            # Check both the error message AND verify the model is actually a completion model
            is_completion = is_completion_model(self.model)
            if "404" in error_msg and is_completion and (
                "not a chat model" in error_msg_lower or
                "v1/completions" in error_msg_lower or
                "chat/completions endpoint" in error_msg_lower
            ):
                completion_error_msg = (
                    f"Model '{self.model}' is a completion model, not a chat model. "
                    f"Completion models (like text-davinci-003, gpt-3.5-turbo-instruct) "
                    f"use the /v1/completions endpoint, which is not supported by this agent. "
                    f"Please use a chat model (like gpt-4, gpt-3.5-turbo, gpt-4-turbo) instead."
                )
                logger.error(
                    f"Completion model used with chat endpoint for {self.name}: {completion_error_msg} (Original: {e})",
                    extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                )
                raise AgentError(
                    completion_error_msg,
                    agent_name=self.name,
                    original_error=e
                ) from e

            # Check for model not found errors (404 but not a completion model)
            if "404" in error_msg and not is_completion and (
                "model" in error_msg_lower or "not found" in error_msg_lower
            ):
                model_error_msg = (
                    f"Model '{self.model}' not found or not available. "
                    f"Please verify the model name is correct and that you have access to it. "
                    f"Common chat models include: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o"
                )
                logger.error(
                    f"Model not found error for {self.name}: {model_error_msg} (Original: {e})",
                    extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                )
                raise AgentError(
                    model_error_msg,
                    agent_name=self.name,
                    original_error=e
                ) from e

            # Check for DNS/connection errors specifically
            if OpenAIAPIConnectionError and isinstance(e, OpenAIAPIConnectionError):
                # Check for DNS resolution failures in error message or underlying exception
                underlying_error = getattr(e, 'cause', None) or getattr(e, '__cause__', None)
                underlying_msg = str(underlying_error) if underlying_error else ""
                combined_msg = f"{error_msg} {underlying_msg}".lower()

                if any(term in combined_msg for term in ["nodename nor servname", "getaddrinfo", "not known", "name or service not known", "name resolution"]):
                    dns_error_msg = (
                        f"DNS resolution failed for OpenAI API endpoint. "
                        f"The endpoint may be unreachable or there may be network connectivity issues. "
                        f"Please check your network connection and API configuration for agent '{self.name}'."
                    )
                    logger.error(
                        f"DNS resolution failed for {self.name}: {e}",
                        exc_info=True,
                        extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                    )
                    raise AgentError(
                        dns_error_msg,
                        agent_name=self.name,
                        original_error=e
                    ) from e

            # Log and wrap all other errors as APIError
            logger.error(
                f"API call failed for {self.name}: {e}",
                exc_info=True,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "error_type": type(e).__name__,
                    "operation": "agenerate"
                }
            )

            raise APIError(
                f"API call failed: {str(e)}",
                provider=self.name,
                original_error=e
            ) from e

        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)

        response_text = response.choices[0].message.content

        token_usage = TokenUsage(
            input=response.usage.prompt_tokens,
            output=response.usage.completion_tokens,
            total=response.usage.total_tokens,
            model_name=self.model,
        )

        return response_text, response_time_ms, token_usage


class GeminiAgent(BaseAgent):
    """Google Gemini agent with async support, optional retry, and configurable timeouts"""

    # Default retry configuration for Gemini API calls
    DEFAULT_RETRY_CONFIG = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=60.0,
        retryable_status_codes=(429, 500, 502, 503, 504),
    )

    # Default timeout configuration
    DEFAULT_TIMEOUT_CONFIG = TimeoutConfig()

    def __init__(
        self,
        name: str = "gemini",
        model: str = "gemini-1.5-flash",  # Updated default - gemini-pro is deprecated
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
        """
        Initialize Gemini agent

        Args:
            name: Agent identifier
            model: Gemini model to use (e.g., 'gemini-pro', 'gemini-1.5-pro')
            api_key: Google API key (uses GOOGLE_API_KEY env var if not provided)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 2.0)
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
            retry_config: Optional retry configuration. If None and enable_retry=True,
                uses DEFAULT_RETRY_CONFIG. If None and enable_retry=False, no retries.
            enable_retry: Enable retry with default config. Ignored if retry_config is provided.
            timeout_config: Optional timeout configuration. If None, uses DEFAULT_TIMEOUT_CONFIG.
                Note: Gemini client uses httpx internally; timeout is applied via httpx_client.

        Raises:
            ImportError: If google-genai package is not installed
            ValueError: If API key is not provided and not in environment
        """
        super().__init__(name, model, cost_tracker, budget_manager)
        
        if not _GEMINI_AVAILABLE:
            import sys
            python_exe = sys.executable
            
            # Detect installation method
            is_pipx = False
            is_user_install = False
            
            # Check if running from pipx
            if 'pipx' in python_exe or '.local/pipx' in python_exe:
                is_pipx = True
            # Check if installed in user site-packages
            elif hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix:
                # Virtual environment
                is_user_install = False
            elif os.path.exists(os.path.expanduser('~/.local/bin/startd8')):
                # Likely user install
                is_user_install = True
            
            # Build helpful error message
            if is_pipx:
                error_msg = (
                    "google-genai package not installed.\n\n"
                    "[Installation Help]\n"
                    "You're running startd8 from pipx. To install google-genai:\n\n"
                    "  pipx inject startd8 google-genai\n\n"
                    "Or reinstall startd8 with Gemini support:\n"
                    "  pipx install --force 'startd8[gemini]'\n\n"
                    f"Python executable: {python_exe}"
                )
            elif is_user_install:
                error_msg = (
                    "google-genai package not installed.\n\n"
                    "[Installation Help]\n"
                    "Install using:\n\n"
                    f"  {python_exe} -m pip install --user google-genai\n\n"
                    "Or install startd8 with Gemini support:\n"
                    f"  {python_exe} -m pip install --user 'startd8[gemini]'\n\n"
                    f"Python executable: {python_exe}"
                )
            else:
                error_msg = (
                    "google-genai package not installed.\n\n"
                    "[Installation Help]\n"
                    "Install using:\n\n"
                    f"  {python_exe} -m pip install google-genai\n\n"
                    "Or install startd8 with Gemini support:\n"
                    f"  {python_exe} -m pip install 'startd8[gemini]'\n\n"
                    f"Python executable: {python_exe}\n"
                    f"Import error: {_GEMINI_IMPORT_ERROR or 'Module not found'}"
                )
            
            raise ImportError(error_msg)
        
        # Get API key from parameter or environment
        if api_key is None:
            api_key = os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            raise ValueError(
                "Google API key required. "
                "Set GOOGLE_API_KEY environment variable or pass api_key parameter."
            )
        
        # Configure timeout
        self.timeout_config = timeout_config or self.DEFAULT_TIMEOUT_CONFIG

        # Create the client with API key and timeout
        # New google.genai uses Client-based API with httpx under the hood
        import httpx
        httpx_client = httpx.Client(timeout=self.timeout_config.to_httpx_timeout())
        self.client = genai.Client(api_key=api_key, http_client=httpx_client)
        self.model_name = self.model

        self.max_tokens = max_tokens
        self.temperature = temperature

        # Configure retry behavior
        if retry_config is not None:
            self.retry_config = retry_config
        elif enable_retry:
            self.retry_config = self.DEFAULT_RETRY_CONFIG
        else:
            self.retry_config = None

    async def _make_api_call(self, prompt: str):
        """
        Make the raw API call to Gemini.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.
        """
        # google.genai Client API - run in executor for async compatibility
        # Create generation config
        generation_config = genai_types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=generation_config
            )
        )

    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Generate response using Gemini async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text

        Returns:
            Tuple of (response_text, response_time_ms, token_usage)

        Raises:
            RuntimeError: If Gemini API call fails
            APIError: For API errors
            RetryError: If all retry attempts are exhausted (when retry enabled)
        """
        start_time = time.time()

        try:
            # Use retry wrapper if configured
            if self.retry_config is not None:
                make_call = with_retry(self.retry_config)(self._make_api_call)
                response = await make_call(prompt)
            else:
                response = await self._make_api_call(prompt)

        except RetryError as e:
            # All retry attempts exhausted
            from .logging_config import get_logger
            from .exceptions import APIError

            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            logger.error(
                f"All retry attempts exhausted for {self.name}: {e.last_exception}",
                exc_info=False,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "retry_attempts": e.attempts,
                    "total_retry_time": e.total_time,
                }
            )

            raise APIError(
                f"API call failed after {e.attempts} attempts: {e.last_exception}",
                provider=self.name,
                original_error=e.last_exception,
            ) from e

        except (ConnectionError, OSError) as e:
            # Specific connection/network errors
            from .logging_config import get_logger
            from .exceptions import APIError
            
            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            logger.error(
                f"Connection error for {self.name}: {e}",
                exc_info=True,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "error_type": type(e).__name__,
                    "operation": "agenerate"
                }
            )
            
            raise APIError(
                f"API connection failed: {str(e)}",
                provider=self.name,
                original_error=e
            ) from e
        except Exception as e:
            # Other API errors - check for specific error types
            from .logging_config import get_logger
            from .exceptions import APIError, AgentError
            
            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            error_msg = str(e)
            error_msg_lower = error_msg.lower()
            
            # Check for deprecated model errors
            if "not found" in error_msg_lower and ("v1beta" in error_msg_lower or "404" in error_msg_lower):
                deprecated_models = {
                    "gemini-pro": "gemini-1.5-flash",
                    "gemini-pro-vision": "gemini-1.5-flash",
                }
                
                if self.model in deprecated_models:
                    suggested_model = deprecated_models[self.model]
                    model_error_msg = (
                        f"Model '{self.model}' is deprecated or not found. "
                        f"Please update your configuration to use '{suggested_model}' instead. "
                        f"The model '{self.model}' was deprecated by Google and is no longer available."
                    )
                    logger.error(
                        f"Deprecated model error for {self.name}: {e}",
                        exc_info=True,
                        extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                    )
                    raise AgentError(
                        model_error_msg,
                        agent_name=self.name,
                        original_error=e
                    ) from e
                else:
                    # Generic model not found error
                    model_error_msg = (
                        f"Model '{self.model}' not found or not supported. "
                        f"Please verify the model name is correct. "
                        f"Available models include: gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash-exp"
                    )
                    logger.error(
                        f"Model not found error for {self.name}: {e}",
                        exc_info=True,
                        extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                    )
                    raise AgentError(
                        model_error_msg,
                        agent_name=self.name,
                        original_error=e
                    ) from e
            
            # Check for DNS/connection errors (Google API uses similar error patterns)
            # Google's API errors may wrap httpx/httpcore errors
            underlying_error = getattr(e, 'cause', None) or getattr(e, '__cause__', None)
            underlying_msg = str(underlying_error).lower() if underlying_error else ""
            combined_msg = f"{error_msg_lower} {underlying_msg}"
            
            if any(term in combined_msg for term in ["nodename nor servname", "getaddrinfo", "not known", "name or service not known", "name resolution", "connection", "network"]):
                dns_error_msg = (
                    f"DNS resolution or network connection failed for Google Gemini API endpoint. "
                    f"The endpoint may be unreachable or there may be network connectivity issues. "
                    f"Please check your network connection and API configuration for agent '{self.name}'."
                )
                logger.error(
                    f"DNS/connection error for {self.name}: {e}",
                    exc_info=True,
                    extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                )
                raise AgentError(
                    dns_error_msg,
                    agent_name=self.name,
                    original_error=e
                ) from e
            
                logger.error(
                    f"API call failed for {self.name}: {e}",
                    exc_info=True,
                    extra={
                        "agent_name": self.name,
                        "model": self.model,
                        "response_time_ms": response_time_ms,
                        "error_type": type(e).__name__,
                        "operation": "agenerate"
                    }
                )
                
                raise APIError(
                    f"API call failed: {str(e)}",
                    provider=self.name,
                    original_error=e
                ) from e
        
        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)
        
        # Extract response text
        # New google.genai API structure
        if not hasattr(response, 'text') or not response.text:
            finish_reason = getattr(response, 'finish_reason', 'unknown')
            raise RuntimeError(
                f"Gemini returned empty response. "
                f"Finish reason: {finish_reason}"
            )
        
        response_text = response.text
        
        # New google.genai API provides usage_metadata directly
        try:
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                input_tokens = getattr(usage, 'prompt_token_count', 0)
                output_tokens = getattr(usage, 'candidates_token_count', 0)
                total_tokens = getattr(usage, 'total_token_count', input_tokens + output_tokens)
            else:
                # Fallback: estimate tokens if usage_metadata not available
                input_tokens = max(1, int(len(prompt.split()) / 1.3))
                output_tokens = max(1, int(len(response_text.split()) / 1.3))
                total_tokens = input_tokens + output_tokens
        except (AttributeError, KeyError, TypeError) as e:
            # Expected errors when token usage metadata is missing or malformed
            # ~1.3 tokens per word as rough estimate
            input_tokens = max(1, int(len(prompt.split()) / 1.3))
            output_tokens = max(1, int(len(response_text.split()) / 1.3))
            total_tokens = input_tokens + output_tokens
            logger.debug(
                f"Token usage metadata unavailable, using estimate: {e}",
                exc_info=False,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "error_type": type(e).__name__,
                    "operation": "extract_token_usage"
                }
            )
        except Exception as e:
            # Unexpected errors during token counting
            # ~1.3 tokens per word as rough estimate
            input_tokens = max(1, int(len(prompt.split()) / 1.3))
            output_tokens = max(1, int(len(response_text.split()) / 1.3))
            total_tokens = input_tokens + output_tokens
            logger.warning(
                f"Failed to extract token usage, using estimate: {e}",
                exc_info=True,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "error_type": type(e).__name__,
                    "operation": "extract_token_usage"
                }
            )
        
        token_usage = TokenUsage(
            input=int(input_tokens),
            output=int(output_tokens),
            total=int(total_tokens),
            model_name=self.model,
        )
        
        return response_text, response_time_ms, token_usage


class OpenAICompatibleAgent(BaseAgent):
    """Agent for OpenAI-compatible APIs (Cursor, Ollama, Together AI, Groq, etc.) with async support, optional retry, and configurable timeouts"""

    # Default retry configuration for OpenAI-compatible API calls
    DEFAULT_RETRY_CONFIG = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=60.0,
        retryable_status_codes=(429, 500, 502, 503, 504),
    )

    # Default timeout configuration
    DEFAULT_TIMEOUT_CONFIG = TimeoutConfig()

    def __init__(
        self,
        name: str = "custom",
        model: str = "custom-model",
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 4096,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
        """
        Initialize OpenAI-compatible agent

        Args:
            name: Agent identifier
            model: Model name to use
            api_key: API key (or use api_key_env to specify env var name)
            api_key_env: Environment variable name for API key
            base_url: Base URL for the API (e.g., 'https://api.openai.com/v1' or 'http://localhost:11434/v1' for Ollama)
            max_tokens: Maximum tokens to generate
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
            retry_config: Optional retry configuration. If None and enable_retry=True,
                uses DEFAULT_RETRY_CONFIG. If None and enable_retry=False, no retries.
            enable_retry: Enable retry with default config. Ignored if retry_config is provided.
            timeout_config: Optional timeout configuration. If None, uses DEFAULT_TIMEOUT_CONFIG.
        """
        super().__init__(name, model, cost_tracker, budget_manager)

        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install startd8[openai] or pip install openai"
            )

        # Get API key from env var if specified
        import os
        actual_api_key = api_key
        if not actual_api_key and api_key_env:
            actual_api_key = os.getenv(api_key_env)

        # Some APIs (like Ollama) don't need an API key
        # For localhost URLs, we can use None if the client supports it
        if not actual_api_key and base_url:
            # Check if this looks like a local URL (Ollama, etc.)
            if 'localhost' in base_url or '127.0.0.1' in base_url:
                # Use None instead of dummy key - OpenAI client accepts None for local APIs
                actual_api_key = None

        # Configure timeout
        self.timeout_config = timeout_config or self.DEFAULT_TIMEOUT_CONFIG
        httpx_timeout = self.timeout_config.to_httpx_timeout()

        self.client = OpenAI(
            api_key=actual_api_key,
            base_url=base_url,
            timeout=httpx_timeout
        )
        self.async_client = AsyncOpenAI(
            api_key=actual_api_key,
            base_url=base_url,
            timeout=httpx_timeout
        )
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.api_key_env = api_key_env
        self._cleanup_registered = False
        self._register_cleanup()

        # Configure retry behavior
        if retry_config is not None:
            self.retry_config = retry_config
        elif enable_retry:
            self.retry_config = self.DEFAULT_RETRY_CONFIG
        else:
            self.retry_config = None

    def _register_cleanup(self):
        """Register cleanup handler to run on exit"""
        if not self._cleanup_registered:
            import atexit
            atexit.register(self.cleanup)
            self._cleanup_registered = True
    
    def cleanup(self):
        """
        Cleanup async client resources.
        
        Handles cleanup gracefully even if event loop is closed.
        Suppresses RuntimeError when event loop is closed.
        """
        if hasattr(self, 'async_client') and self.async_client:
            try:
                # Check if we can access the underlying httpx client
                client = None
                if hasattr(self.async_client, '_client'):
                    client = self.async_client._client
                elif hasattr(self.async_client, 'client'):
                    client = self.async_client.client
                
                if client and hasattr(client, 'aclose'):
                    # Try to close if event loop is available
                    try:
                        loop = asyncio.get_running_loop()
                        if not loop.is_closed():
                            # Schedule cleanup task
                            try:
                                asyncio.create_task(client.aclose())
                            except RuntimeError:
                                # Event loop closing, can't schedule tasks
                                pass
                    except RuntimeError:
                        # No running loop - event loop may be closed
                        # Try to get event loop, but handle closed case gracefully
                        try:
                            loop = asyncio.get_event_loop()
                            if not loop.is_closed():
                                try:
                                    loop.run_until_complete(client.aclose())
                                except RuntimeError as e:
                                    # Event loop is closing/closed - suppress error
                                    if 'Event loop is closed' not in str(e):
                                        # Only suppress the specific "Event loop is closed" error
                                        pass
                        except RuntimeError:
                            # Event loop is closed or doesn't exist
                            # httpx will cleanup on Python exit - suppress error
                            pass
            except RuntimeError as e:
                # Suppress "Event loop is closed" errors during cleanup
                if 'Event loop is closed' not in str(e):
                    # Re-raise if it's a different RuntimeError
                    raise
            except Exception as e:
                # Ignore all other cleanup errors
                # Log at debug level for troubleshooting
                logger.debug(
                    f"Error during {self.__class__.__name__} cleanup (ignored): {e}",
                    exc_info=False,
                    extra={"agent_name": self.name, "error_type": type(e).__name__}
                )
                pass
    
    async def acleanup(self):
        """Async cleanup - properly closes async client"""
        if hasattr(self, 'async_client') and self.async_client:
            try:
                # Close the underlying httpx client if it exists
                if hasattr(self.async_client, '_client'):
                    client = self.async_client._client
                    if hasattr(client, 'aclose'):
                        try:
                            await client.aclose()
                        except RuntimeError as e:
                            if 'Event loop is closed' not in str(e):
                                raise
            except Exception as e:
                # Ignore cleanup errors
                # Log at debug level for troubleshooting
                logger.debug(
                    f"Error during {self.__class__.__name__} async cleanup (ignored): {e}",
                    exc_info=False,
                    extra={"agent_name": self.name, "error_type": type(e).__name__}
                )
                pass

    async def _make_api_call(self, prompt: str):
        """
        Make the raw API call to the OpenAI-compatible endpoint.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.
        """
        return await self.async_client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Generate response using OpenAI-compatible API (async).

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text

        Returns:
            Tuple of (response_text, response_time_ms, token_usage)

        Raises:
            APIError: For API errors
            RetryError: If all retry attempts are exhausted (when retry enabled)
        """
        start_time = time.time()

        try:
            # Use retry wrapper if configured
            if self.retry_config is not None:
                make_call = with_retry(self.retry_config)(self._make_api_call)
                response = await make_call(prompt)
            else:
                response = await self._make_api_call(prompt)

            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            response_text = response.choices[0].message.content

            # Some APIs may not return usage info
            if hasattr(response, 'usage') and response.usage:
                token_usage = TokenUsage(
                    input=response.usage.prompt_tokens or 0,
                    output=response.usage.completion_tokens or 0,
                    total=response.usage.total_tokens or 0,
                    model_name=self.model,
                )
            else:
                # Estimate tokens if not provided
                token_usage = TokenUsage(
                    input=len(prompt.split()),
                    output=len(response_text.split()) if response_text else 0,
                    total=len(prompt.split()) + (len(response_text.split()) if response_text else 0),
                    model_name=self.model,
                )

            return response_text, response_time_ms, token_usage

        except RetryError as e:
            # All retry attempts exhausted
            from .logging_config import get_logger
            from .exceptions import APIError

            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            logger.error(
                f"All retry attempts exhausted for {self.name}: {e.last_exception}",
                exc_info=False,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "retry_attempts": e.attempts,
                    "total_retry_time": e.total_time,
                }
            )

            raise APIError(
                f"API call failed after {e.attempts} attempts: {e.last_exception}",
                provider=self.name,
                original_error=e.last_exception,
            ) from e

        except Exception as e:
            from .logging_config import get_logger
            from .exceptions import APIError, AgentError
            
            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            error_msg = str(e)
            error_msg_lower = error_msg.lower()
            
            # Check for completion model error (404 - not a chat model)
            # Only raise this error if we're confident it's actually a completion model issue
            # Check both the error message AND verify the model is actually a completion model
            is_completion = is_completion_model(self.model)
            if "404" in error_msg and is_completion and (
                "not a chat model" in error_msg_lower or 
                "v1/completions" in error_msg_lower or
                "chat/completions endpoint" in error_msg_lower
            ):
                completion_error_msg = (
                    f"Model '{self.model}' is a completion model, not a chat model. "
                    f"Completion models (like text-davinci-003, gpt-3.5-turbo-instruct) "
                    f"use the /v1/completions endpoint, which is not supported by this agent. "
                    f"Please use a chat model (like gpt-4, gpt-3.5-turbo, gpt-4-turbo) instead."
                )
                # Log without exc_info=True to avoid printing traceback to console
                # The original error is preserved in AgentError.original_error for debugging
                logger.error(
                    f"Completion model used with chat endpoint for {self.name}: {completion_error_msg} (Original: {e})",
                    extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                )
                raise AgentError(
                    completion_error_msg,
                    agent_name=self.name,
                    original_error=e
                ) from e
            
            # Check for model not found errors (404 but not a completion model)
            if "404" in error_msg and not is_completion and (
                "model" in error_msg_lower or "not found" in error_msg_lower
            ):
                model_error_msg = (
                    f"Model '{self.model}' not found or not available. "
                    f"Please verify the model name is correct and that you have access to it. "
                    f"Common chat models include: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o"
                )
                # Log without exc_info=True to avoid printing traceback to console
                # The original error is preserved in AgentError.original_error for debugging
                logger.error(
                    f"Model not found error for {self.name}: {model_error_msg} (Original: {e})",
                    extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                )
                raise AgentError(
                    model_error_msg,
                    agent_name=self.name,
                    original_error=e
                ) from e
            
            # Check for DNS/connection errors specifically
            if OpenAIAPIConnectionError and isinstance(e, OpenAIAPIConnectionError):
                # Check for DNS resolution failures in error message or underlying exception
                underlying_error = getattr(e, 'cause', None) or getattr(e, '__cause__', None)
                underlying_msg = str(underlying_error) if underlying_error else ""
                combined_msg = f"{error_msg} {underlying_msg}".lower()
                
                if any(term in combined_msg for term in ["nodename nor servname", "getaddrinfo", "not known", "name or service not known", "name resolution"]):
                    dns_error_msg = (
                        f"DNS resolution failed for endpoint '{self.base_url}'. "
                        f"The endpoint may be unreachable, the URL may be incorrect, or the service may be deprecated. "
                        f"Please verify the base_url configuration for agent '{self.name}'."
                    )
                    logger.error(
                        f"DNS resolution failed for {self.name} ({self.base_url}): {e}",
                        exc_info=True,
                        extra={"agent_name": self.name, "model": self.model, "base_url": self.base_url, "response_time_ms": response_time_ms}
                    )
                    raise AgentError(
                        dns_error_msg,
                        agent_name=self.name,
                        original_error=e
                    ) from e
            
            logger.error(
                f"API call failed for {self.name}: {e}",
                exc_info=True,
                extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
            )
            
            # Preserve original exception context
            raise APIError(
                f"API call failed: {str(e)}",
                provider=self.name,
                original_error=e
            ) from e


class MockAgent(BaseAgent):
    """Mock agent for testing with async support"""
    
    def __init__(self, name: str = "mock", model: str = "mock-model"):
        """Initialize mock agent"""
        super().__init__(name, model)
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """Generate mock response (async)"""
        await asyncio.sleep(0.1)  # Simulate async latency
        
        response = f"Mock response to: {prompt[:50]}..."
        response_time_ms = 100
        
        token_usage = TokenUsage(
            input=len(prompt.split()),
            output=len(response.split()),
            total=len(prompt.split()) + len(response.split()),
            model_name=self.model,
        )
        
        return response, response_time_ms, token_usage


class ComposerAgent(OpenAICompatibleAgent):
    """
    Cursor Composer agent (via OpenAI-compatible API)
    
    .. deprecated:: 
        Cursor does not provide a public OpenAI-compatible API for external applications.
        This agent class is maintained for backward compatibility but may not work with
        current Cursor API endpoints. Consider using alternative providers like OpenRouter,
        Together AI, or direct Claude/GPT-4 agents instead.
    """
    
    def __init__(
        self,
        name: str = "composer",
        model: str = "composer",
        api_key: Optional[str] = None,
        api_key_env: str = "CURSOR_API_KEY",
        base_url: str = "https://api.cursor.com/v1",
        max_tokens: int = 8192
    ):
        """
        Initialize Cursor Composer agent.
        
        .. warning::
            Cursor does not provide a public OpenAI-compatible API. This agent may not work
            as expected. The default base_url has been updated to api.cursor.com, but Cursor's
            API is designed for internal use only (admin API and background agents).
        
        Args:
            name: Agent identifier (default: "composer")
            model: Model name (default: "composer")
            api_key: Cursor API key (or use api_key_env)
            api_key_env: Environment variable for API key (default: CURSOR_API_KEY)
            base_url: Cursor API base URL (default updated to api.cursor.com)
            max_tokens: Maximum tokens to generate
        """
        super().__init__(
            name=name,
            model=model,
            api_key=api_key,
            api_key_env=api_key_env,
            base_url=base_url,
            max_tokens=max_tokens
        )

