"""
OpenAI agent implementations.

This module provides:
- GPT4Agent: OpenAI GPT-4 agent
- OpenAICompatibleAgent: Agent for OpenAI-compatible APIs (Ollama, Together AI, Groq, etc.)
"""

import asyncio
import logging
import os
import time
from typing import Optional, Tuple

from ..models import TokenUsage, GenerateResult
from ..utils.retry import RetryConfig, RetryError, with_retry
from .base import BaseAgent, is_completion_model
from .pool import TimeoutConfig, get_client_pool

logger = logging.getLogger(__name__)

# Optional OpenAI import
try:
    from openai import OpenAI, AsyncOpenAI
    from openai import APIConnectionError as OpenAIAPIConnectionError
    _OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    OpenAIAPIConnectionError = None
    _OPENAI_AVAILABLE = False


class GPT4Agent(BaseAgent):
    """OpenAI GPT-4 agent with async support, optional retry, configurable timeouts, and connection pooling"""

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
        model: str = "gpt-4o",  # GPT-4o - latest flagship model
        api_key: Optional[str] = None,
        max_tokens: int = 16384,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
        use_connection_pool: bool = False,
        system_prompt: Optional[str] = None,
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
            use_connection_pool: If True, share HTTP clients with other agents using the same
                config. Reduces connection overhead for multi-agent workloads. Default: False.
            system_prompt: Optional system prompt. Prepended as a ``{"role": "system", ...}``
                message to the messages list. Can be overridden per-call via
                ``agenerate(prompt, system_prompt=...)``.
        """
        super().__init__(name, model, cost_tracker, budget_manager)

        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install startd8[openai] or pip install openai"
            )

        # Configure timeout
        self.timeout_config = timeout_config or self.DEFAULT_TIMEOUT_CONFIG
        self._use_connection_pool = use_connection_pool
        self._owns_clients = not use_connection_pool

        # Get or create clients
        if use_connection_pool:
            pool = get_client_pool()
            self.client, self.async_client = pool.get_openai_clients(
                api_key=api_key,
                timeout_config=self.timeout_config
            )
        else:
            httpx_timeout = self.timeout_config.to_httpx_timeout()
            self.client = OpenAI(api_key=api_key, timeout=httpx_timeout)
            self.async_client = AsyncOpenAI(api_key=api_key, timeout=httpx_timeout)

        self.max_tokens = max_tokens
        self.system_prompt = system_prompt

        # Configure retry behavior
        if retry_config is not None:
            self.retry_config = retry_config
        elif enable_retry:
            self.retry_config = self.DEFAULT_RETRY_CONFIG
        else:
            self.retry_config = None

    async def _make_api_call(self, prompt: str, system_prompt: Optional[str] = None):
        """
        Make the raw API call to OpenAI.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.

        Args:
            prompt: The user prompt text
            system_prompt: Optional system prompt. If provided, prepended as a
                ``{"role": "system", ...}`` message.
        """
        messages = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.async_client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=messages,
        )

    async def agenerate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerateResult:
        """
        Generate response using GPT-4 async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text to send
            system_prompt: Optional per-call system prompt override. When provided,
                takes precedence over the instance-level ``self.system_prompt``.
                If neither is set, no system message is sent.

        Returns:
            GenerateResult(text, time_ms, token_usage)

        Raises:
            AgentError: For model errors or DNS/connection errors that can't be retried
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
            from ..logging_config import get_logger
            from ..exceptions import APIError

            local_logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            local_logger.error(
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
            from ..logging_config import get_logger
            from ..exceptions import APIError, AgentError

            local_logger = get_logger(__name__)
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
                local_logger.error(
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
                local_logger.error(
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
                    local_logger.error(
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
            local_logger.error(
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

        # Extract finish_reason to detect truncation
        # OpenAI uses: "stop" (natural), "length" (truncated), "content_filter", "tool_calls"
        finish_reason = getattr(response.choices[0], 'finish_reason', None)

        token_usage = TokenUsage(
            input=response.usage.prompt_tokens,
            output=response.usage.completion_tokens,
            total=response.usage.total_tokens,
            model_name=self.model,
            finish_reason=finish_reason,
        )

        # Log warning if response was truncated
        if token_usage.was_truncated:
            logger.warning(
                f"Response from {self.name} was truncated (finish_reason={finish_reason}). "
                f"Output tokens: {token_usage.output}. Consider increasing max_tokens (currently {self.max_tokens}).",
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "finish_reason": finish_reason,
                    "output_tokens": token_usage.output,
                    "max_tokens": self.max_tokens,
                }
            )

        return GenerateResult(response_text, response_time_ms, token_usage)


class OpenAICompatibleAgent(BaseAgent):
    """Agent for OpenAI-compatible APIs (Cursor, Ollama, Together AI, Groq, etc.) with async support, optional retry, configurable timeouts, and connection pooling"""

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
        max_tokens: int = 16384,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
        use_connection_pool: bool = False,
        system_prompt: Optional[str] = None,
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
            use_connection_pool: If True, share HTTP clients with other agents using the same
                config. Reduces connection overhead for multi-agent workloads. Default: False.
            system_prompt: Optional system prompt. Prepended as a ``{"role": "system", ...}``
                message to the messages list. Can be overridden per-call via
                ``agenerate(prompt, system_prompt=...)``.
        """
        super().__init__(name, model, cost_tracker, budget_manager)

        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install startd8[openai] or pip install openai"
            )

        # Get API key from env var if specified
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
        self._use_connection_pool = use_connection_pool
        self._owns_clients = not use_connection_pool

        # Get or create clients
        if use_connection_pool:
            pool = get_client_pool()
            self.client, self.async_client = pool.get_openai_clients(
                api_key=actual_api_key,
                timeout_config=self.timeout_config,
                base_url=base_url
            )
        else:
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
        self.system_prompt = system_prompt
        self.base_url = base_url
        self.api_key_env = api_key_env
        self._cleanup_registered = False

        # Only register cleanup if we own the clients
        if self._owns_clients:
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

    async def _make_api_call(self, prompt: str, system_prompt: Optional[str] = None):
        """
        Make the raw API call to the OpenAI-compatible endpoint.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.

        Args:
            prompt: The user prompt text
            system_prompt: Optional system prompt. If provided, prepended as a
                ``{"role": "system", ...}`` message.
        """
        messages = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.async_client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=messages,
        )

    async def agenerate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerateResult:
        """
        Generate response using OpenAI-compatible API (async).

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text
            system_prompt: Optional per-call system prompt override. When provided,
                takes precedence over the instance-level ``self.system_prompt``.
                If neither is set, no system message is sent.

        Returns:
            GenerateResult(text, time_ms, token_usage)

        Raises:
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

            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            response_text = response.choices[0].message.content

            # Extract finish_reason to detect truncation
            # OpenAI-compatible APIs use: "stop" (natural), "length" (truncated)
            finish_reason = getattr(response.choices[0], 'finish_reason', None)

            # Some APIs may not return usage info
            if hasattr(response, 'usage') and response.usage:
                token_usage = TokenUsage(
                    input=response.usage.prompt_tokens or 0,
                    output=response.usage.completion_tokens or 0,
                    total=response.usage.total_tokens or 0,
                    model_name=self.model,
                    finish_reason=finish_reason,
                )
            else:
                # Estimate tokens if not provided
                token_usage = TokenUsage(
                    input=len(prompt.split()),
                    output=len(response_text.split()) if response_text else 0,
                    total=len(prompt.split()) + (len(response_text.split()) if response_text else 0),
                    model_name=self.model,
                    finish_reason=finish_reason,
                )

            # Log warning if response was truncated
            if token_usage.was_truncated:
                logger.warning(
                    f"Response from {self.name} was truncated (finish_reason={finish_reason}). "
                    f"Output tokens: {token_usage.output}. Consider increasing max_tokens (currently {self.max_tokens}).",
                    extra={
                        "agent_name": self.name,
                        "model": self.model,
                        "finish_reason": finish_reason,
                        "output_tokens": token_usage.output,
                        "max_tokens": self.max_tokens,
                    }
                )

            return GenerateResult(response_text, response_time_ms, token_usage)

        except RetryError as e:
            # All retry attempts exhausted
            from ..logging_config import get_logger
            from ..exceptions import APIError

            local_logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            local_logger.error(
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
            from ..logging_config import get_logger
            from ..exceptions import APIError, AgentError

            local_logger = get_logger(__name__)
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
                local_logger.error(
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
                local_logger.error(
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
                    local_logger.error(
                        f"DNS resolution failed for {self.name} ({self.base_url}): {e}",
                        exc_info=True,
                        extra={"agent_name": self.name, "model": self.model, "base_url": self.base_url, "response_time_ms": response_time_ms}
                    )
                    raise AgentError(
                        dns_error_msg,
                        agent_name=self.name,
                        original_error=e
                    ) from e

            local_logger.error(
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
