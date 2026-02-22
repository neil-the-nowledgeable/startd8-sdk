"""
Anthropic Claude agent implementation.
"""

import asyncio
import logging
import time
from typing import Optional, Tuple

from ..models import TokenUsage, GenerateResult
from ..utils.retry import RetryConfig, RetryError, with_retry
from .base import BaseAgent
from .pool import TimeoutConfig, get_client_pool

logger = logging.getLogger(__name__)

# Optional Anthropic import
try:
    from anthropic import Anthropic, AsyncAnthropic
    from anthropic import APIConnectionError as AnthropicAPIConnectionError
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    Anthropic = None
    AsyncAnthropic = None
    AnthropicAPIConnectionError = None
    _ANTHROPIC_AVAILABLE = False


class ClaudeAgent(BaseAgent):
    """Anthropic Claude agent with async support, optional retry, configurable timeouts, and connection pooling"""

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
        model: str = "claude-sonnet-4-20250514",  # Claude Sonnet 4 - best balance of capability and cost
        api_key: Optional[str] = None,
        max_tokens: int = 32768,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
        use_connection_pool: bool = False,
        system_prompt: Optional[str] = None,
        enable_prompt_caching: bool = False,
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
            use_connection_pool: If True, share HTTP clients with other agents using the same
                config. Reduces connection overhead for multi-agent workloads. Default: False.
            system_prompt: Optional system prompt for stronger instruction-following.
                Sent as the separate ``system`` parameter in the Anthropic API.
                Can be overridden per-call via ``agenerate(prompt, system_prompt=...)``.
            enable_prompt_caching: If True, add cache_control blocks to system prompts
                for Anthropic prompt caching (90% input cost reduction on cache hits).
        """
        super().__init__(name, model, cost_tracker, budget_manager)

        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install startd8[anthropic] or pip install anthropic"
            )

        # Configure timeout
        self.timeout_config = timeout_config or self.DEFAULT_TIMEOUT_CONFIG
        self._use_connection_pool = use_connection_pool
        self._owns_clients = not use_connection_pool

        # Get or create clients
        if use_connection_pool:
            pool = get_client_pool()
            self.client, self.async_client = pool.get_anthropic_clients(
                api_key=api_key,
                timeout_config=self.timeout_config
            )
        else:
            httpx_timeout = self.timeout_config.to_httpx_timeout()
            # Disable Anthropic SDK-level retries so startd8 retry policy remains
            # the single source of truth for fail-fast behavior.
            self.client = Anthropic(
                api_key=api_key,
                timeout=httpx_timeout,
                max_retries=0,
            )
            self.async_client = AsyncAnthropic(
                api_key=api_key,
                timeout=httpx_timeout,
                max_retries=0,
            )

        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.enable_prompt_caching = enable_prompt_caching

        # Configure retry behavior
        if retry_config is not None:
            self.retry_config = retry_config
        elif enable_retry:
            self.retry_config = self.DEFAULT_RETRY_CONFIG
        else:
            self.retry_config = None

        # Ensure Anthropic-specific connection errors are retryable.
        # AnthropicAPIConnectionError inherits from anthropic.APIError, NOT
        # Python's ConnectionError, so the default retryable_exceptions tuple
        # (ConnectionError, TimeoutError, OSError) misses it.
        if self.retry_config is not None and AnthropicAPIConnectionError is not None:
            if AnthropicAPIConnectionError not in self.retry_config.retryable_exceptions:
                from dataclasses import replace as _dc_replace
                self.retry_config = _dc_replace(
                    self.retry_config,
                    retryable_exceptions=self.retry_config.retryable_exceptions + (AnthropicAPIConnectionError,),
                )

        self._cleanup_registered = False
        if self._owns_clients:
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

        Uses the persistent sync loop (from BaseAgent) when available so
        that httpx connections are closed on the same loop that created
        them, avoiding ``RuntimeError: Event loop is closed``.
        """
        if hasattr(self, 'async_client') and self.async_client:
            try:
                client = None
                if hasattr(self.async_client, '_client'):
                    client = self.async_client._client
                elif hasattr(self.async_client, 'client'):
                    client = self.async_client.client

                if client and hasattr(client, 'aclose'):
                    # Prefer the persistent sync loop — it created the
                    # connections so closing on it avoids cross-loop errors.
                    loop = getattr(self, '_sync_loop', None)
                    if loop is not None and not loop.is_closed():
                        try:
                            loop.run_until_complete(client.aclose())
                        except RuntimeError:
                            pass
                    else:
                        # Fallback: try whatever loop is available
                        try:
                            loop = asyncio.get_running_loop()
                            if not loop.is_closed():
                                try:
                                    asyncio.create_task(client.aclose())
                                except RuntimeError:
                                    pass
                        except RuntimeError:
                            try:
                                loop = asyncio.get_event_loop()
                                if not loop.is_closed():
                                    try:
                                        loop.run_until_complete(client.aclose())
                                    except RuntimeError:
                                        pass
                            except RuntimeError:
                                pass
            except Exception as e:
                logger.debug(
                    f"Error during {self.__class__.__name__} cleanup (ignored): {e}",
                    exc_info=False,
                    extra={"agent_name": self.name, "error_type": type(e).__name__}
                )
                pass
        # Close the persistent event loop last (after async clients)
        super().cleanup()

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

    async def _make_api_call(self, prompt: str, system_prompt: Optional[str] = None):
        """
        Make the raw API call to Anthropic.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.

        Args:
            prompt: The user prompt text
            system_prompt: Optional system prompt. If provided, sent as the
                ``system`` parameter to the Anthropic API.
        """
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }
        if system_prompt is not None:
            if self.enable_prompt_caching:
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                kwargs["system"] = system_prompt
        return await self.async_client.messages.create(**kwargs)

    async def agenerate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerateResult:
        """
        Generate response using Claude async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text to send
            system_prompt: Optional per-call system prompt override. When provided,
                takes precedence over the instance-level ``self.system_prompt``.
                If neither is set, no system parameter is sent.

        Returns:
            GenerateResult(text, time_ms, token_usage)

        Raises:
            AgentError: For DNS/connection errors that can't be retried
            APIError: For API errors
            RetryError: If all retry attempts are exhausted (when retry enabled)
        """
        # Resolve system prompt: call-level overrides instance-level
        effective_system_prompt = system_prompt if system_prompt is not None else self.system_prompt

        start_time = time.time()

        try:
            # Use retry wrapper if configured
            if self.retry_config is not None:
                make_call = with_retry(self.retry_config)(self._make_api_call)
                response = await make_call(prompt, system_prompt=effective_system_prompt)
            else:
                response = await self._make_api_call(prompt, system_prompt=effective_system_prompt)

        except RetryError as e:
            # All retry attempts exhausted
            from ..exceptions import APIError

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
            from ..exceptions import APIError, AgentError

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

        # Extract stop_reason to detect truncation
        # Anthropic uses: "end_turn" (natural), "max_tokens" (truncated), "stop_sequence"
        stop_reason = getattr(response, 'stop_reason', None)

        _raw_creation = getattr(response.usage, 'cache_creation_input_tokens', None)
        _raw_read = getattr(response.usage, 'cache_read_input_tokens', None)
        cache_creation = _raw_creation if isinstance(_raw_creation, int) else None
        cache_read = _raw_read if isinstance(_raw_read, int) else None

        token_usage = TokenUsage(
            input=response.usage.input_tokens,
            output=response.usage.output_tokens,
            total=response.usage.input_tokens + response.usage.output_tokens,
            model_name=self.model,
            finish_reason=stop_reason,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        )

        if cache_read and cache_read > 0:
            logger.info(
                "Prompt cache hit: %d tokens read from cache (%s)",
                cache_read, self.name,
            )
        elif cache_creation and cache_creation > 0:
            logger.debug(
                "Prompt cache created: %d tokens written (%s)",
                cache_creation, self.name,
            )

        # Log warning if response was truncated
        if token_usage.was_truncated:
            logger.warning(
                f"Response from {self.name} was truncated (stop_reason={stop_reason}). "
                f"Output tokens: {token_usage.output}. Consider increasing max_tokens (currently {self.max_tokens}).",
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "stop_reason": stop_reason,
                    "output_tokens": token_usage.output,
                    "max_tokens": self.max_tokens,
                }
            )

        return GenerateResult(response_text, response_time_ms, token_usage)
