"""
OpenAI agent implementations.

This module provides:
- GPT4Agent: OpenAI GPT-4 agent
- OpenAICompatibleAgent: Agent for OpenAI-compatible APIs (Ollama, Together AI, Groq, etc.)
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional, Tuple

from ..models import TokenUsage, GenerateResult, AgenticTurn, ToolCallRequest
from .model_timing import record_model_time_ms  # FR-SPEED-1: accumulate pure model API time
from ..utils.retry import RetryConfig, RetryError, with_retry
from .base import BaseAgent, is_completion_model, requires_max_completion_tokens
from .pool import TimeoutConfig, get_client_pool

logger = logging.getLogger(__name__)


def _cached_input_tokens(usage) -> int:
    """Cache-read (cached prompt) tokens from an OpenAI-style ``usage`` object, across dialects:
    OpenAI/most compat servers expose ``usage.prompt_tokens_details.cached_tokens``; DeepSeek exposes
    ``usage.prompt_cache_hit_tokens``. Returns 0 when absent.

    IMPORTANT: unlike Anthropic (which reports cache tokens SEPARATELY from input), these vendors fold
    cached tokens INTO ``prompt_tokens``. Callers MUST subtract this from the ``input`` they pass to
    ``TokenUsage`` so the cost model (which prices ``input`` at full rate and ``cache_read`` at 0.1x)
    does not double-charge the cached tokens. See costs/pricing.py:543."""
    def _num(v):
        # Require a genuine number — guards against MagicMock (whose __int__ returns 1) and other
        # odd usage objects yielding a phantom cache count.
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    details = getattr(usage, "prompt_tokens_details", None)
    cached = _num(getattr(details, "cached_tokens", None)) if details is not None else None
    if cached is None:
        cached = _num(getattr(usage, "prompt_cache_hit_tokens", None))  # DeepSeek dialect
    return max(0, int(cached)) if cached is not None else 0


def _build_chat_kwargs(
    model: str,
    messages: list,
    token_limit: int,
    temperature: Optional[float],
    stop: Optional[list],
    *,
    enforce_next_gen: bool,
) -> dict:
    """Build chat-completions kwargs, adapting token/temperature params per model family.

    The gpt-5 family and o-series reject ``max_tokens`` (require ``max_completion_tokens``)
    and only accept the default temperature. ``enforce_next_gen`` gates that behavior so it
    is applied only against the real OpenAI endpoint — an OpenAI-*compatible* server may use a
    model name in those families while still expecting the classic ``max_tokens`` dialect.
    """
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if enforce_next_gen and requires_max_completion_tokens(model):
        kwargs["max_completion_tokens"] = token_limit
        if temperature is not None:
            logger.debug(
                "Dropping temperature override for %s (only the default temperature is supported)",
                model,
            )
    else:
        kwargs["max_tokens"] = token_limit
        if temperature is not None:
            kwargs["temperature"] = temperature
    if stop is not None:
        kwargs["stop"] = stop
    return kwargs

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
        model: str = "gpt-5.5-pro",  # GPT-5.5 Pro - most capable (flagship default)
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

        # Ensure OpenAI-specific connection errors are retryable.
        # OpenAIAPIConnectionError inherits from openai.APIError, NOT
        # Python's ConnectionError, so the default retryable_exceptions tuple
        # misses it.
        if self.retry_config is not None and OpenAIAPIConnectionError is not None:
            if OpenAIAPIConnectionError not in self.retry_config.retryable_exceptions:
                from dataclasses import replace as _dc_replace
                self.retry_config = _dc_replace(
                    self.retry_config,
                    retryable_exceptions=self.retry_config.retryable_exceptions + (OpenAIAPIConnectionError,),
                )

    async def _make_api_call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list] = None,
    ):
        """
        Make the raw API call to OpenAI.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.

        Args:
            prompt: The user prompt text
            system_prompt: Optional system prompt. If provided, prepended as a
                ``{"role": "system", ...}`` message.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
            temperature: Optional sampling temperature override. When provided,
                passed to the API call. If None, the API default is used.
            stop: Optional list of stop sequences. When provided, the API will
                stop generating when any of these sequences is encountered.
        """
        messages = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        # GPT4Agent always targets the real OpenAI endpoint → enforce next-gen params.
        kwargs = _build_chat_kwargs(
            self.model, messages, token_limit, temperature, stop, enforce_next_gen=True
        )
        return await self.async_client.chat.completions.create(**kwargs)

    async def agenerate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list] = None,
    ) -> GenerateResult:
        """
        Generate response using GPT-4 async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text to send
            system_prompt: Optional per-call system prompt override. When provided,
                takes precedence over the instance-level ``self.system_prompt``.
                If neither is set, no system message is sent.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
                This is thread-safe — it avoids mutating the shared agent.
            temperature: Optional sampling temperature override. When provided,
                passed to the API call. If None, the API default is used.
            stop: Optional list of stop sequences. When provided, the API will
                stop generating when any of these sequences is encountered.

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
                response = await make_call(
                    prompt, system_prompt=effective_system_prompt,
                    max_tokens=max_tokens, temperature=temperature,
                    stop=stop,
                )
            else:
                response = await self._make_api_call(
                    prompt, system_prompt=effective_system_prompt,
                    max_tokens=max_tokens, temperature=temperature,
                    stop=stop,
                )

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

        _cached = _cached_input_tokens(response.usage)
        token_usage = TokenUsage(
            input=max(0, response.usage.prompt_tokens - _cached),  # non-cached (pricing expects this)
            output=response.usage.completion_tokens,
            total=response.usage.total_tokens,
            model_name=self.model,
            finish_reason=finish_reason,
            cache_read_input_tokens=_cached or None,
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

        record_model_time_ms(response_time_ms)
        return GenerateResult(response_text, response_time_ms, token_usage)

    def supports_tool_use(self) -> bool:
        """GPT4Agent implements the FR-0 tool-use primitive (:meth:`agenerate_tools`)."""
        return True

    async def agenerate_tools(
        self,
        messages: "list[dict] | str",
        tools: list,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AgenticTurn:
        """One agentic turn (FR-0): present OpenAI-format *tools*, return text + all tool calls.

        Accepts a **canonical message list** (so the loop can thread prior assistant ``tool_calls``
        and ``tool`` result messages back; a bare ``str`` is wrapped). For OpenAI the system prompt
        rides *inside* the message list, so it is prepended when not already present. Tool calls
        arrive on ``message.tool_calls`` with ``function.arguments`` as a **JSON string**, parsed into
        the provider-neutral :class:`ToolCallRequest` ``arguments`` dict. ``_make_api_call`` does not
        accept ``tools``, so the request is built via ``_build_chat_kwargs``. Retry/usage extraction
        mirror :meth:`agenerate`.
        """
        effective_system_prompt = (
            system_prompt if system_prompt is not None else self.system_prompt
        )
        msgs = self._normalize_messages(messages)
        if effective_system_prompt is not None and not any(
            m.get("role") == "system" for m in msgs
        ):
            msgs = [{"role": "system", "content": effective_system_prompt}] + msgs

        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        kwargs = _build_chat_kwargs(
            self.model, msgs, token_limit, temperature, None, enforce_next_gen=True
        )
        if tools:  # empty tool set => omit the kwarg (OpenAI rejects tools=[])
            kwargs["tools"] = tools

        async def _create():
            return await self.async_client.chat.completions.create(**kwargs)

        start_time = time.time()
        try:
            if self.retry_config is not None:
                response = await with_retry(self.retry_config)(_create)()
            else:
                response = await _create()
        except RetryError as e:  # mirror agenerate: wrap exhausted transport retries
            from ..exceptions import APIError

            raise APIError(
                f"API call failed after {e.attempts} attempts: {e.last_exception}",
                provider=self.name,
                original_error=e.last_exception,
            ) from e

        response_time_ms = int((time.time() - start_time) * 1000)
        choice = response.choices[0]
        message = choice.message
        finish_reason = getattr(choice, "finish_reason", None)

        tool_calls: list[ToolCallRequest] = []
        for tc in (getattr(message, "tool_calls", None) or []):
            fn = getattr(tc, "function", None)
            raw_args = getattr(fn, "arguments", None)
            try:
                if isinstance(raw_args, str):
                    args = json.loads(raw_args) if raw_args.strip() else {}
                else:
                    args = dict(raw_args or {})
            except (json.JSONDecodeError, TypeError, ValueError):
                args = {}  # malformed tool args degrade to empty, never crash the turn
            tool_calls.append(
                ToolCallRequest(
                    id=getattr(tc, "id", "") or "",
                    name=getattr(fn, "name", "") or "",
                    arguments=args,
                )
            )

        usage = getattr(response, "usage", None)
        token_usage = None
        if usage is not None:
            _cached = _cached_input_tokens(usage)
            token_usage = TokenUsage(
                input=max(0, usage.prompt_tokens - _cached),
                output=usage.completion_tokens,
                total=usage.total_tokens,
                model_name=self.model,
                finish_reason=finish_reason,
                cache_read_input_tokens=_cached or None,
            )
        record_model_time_ms(response_time_ms)
        return AgenticTurn(
            text=getattr(message, "content", None) or "",
            tool_calls=tool_calls,
            token_usage=token_usage,
            finish_reason=finish_reason,
            time_ms=response_time_ms,
        )

    def supports_streaming(self) -> bool:
        """GPT4Agent implements per-token streaming (FR-S2, MVP-A)."""
        return True

    async def agenerate_tools_stream(
        self,
        messages: "list[dict] | str",
        tools: list,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        """Stream a tool-use turn (FR-S2). Yields :class:`TextDelta` per content fragment, then a
        terminal :class:`TurnComplete`. OpenAI has no final-message helper, so tool calls are assembled
        **by index** across chunks (basic accumulation — the FR-S3 edge-case hardening is MVP-B). Usage
        arrives in the final chunk via ``stream_options.include_usage``."""
        from ..models import TextDelta, ToolCallDelta, TurnComplete

        effective_system_prompt = (
            system_prompt if system_prompt is not None else self.system_prompt
        )
        msgs = self._normalize_messages(messages)
        if effective_system_prompt is not None and not any(m.get("role") == "system" for m in msgs):
            msgs = [{"role": "system", "content": effective_system_prompt}] + msgs

        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        kwargs = _build_chat_kwargs(self.model, msgs, token_limit, temperature, None, enforce_next_gen=True)
        if tools:
            kwargs["tools"] = tools
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}

        start_time = time.time()
        text_parts: list[str] = []
        tc_acc: dict[int, dict] = {}
        finish_reason = None
        usage_obj = None

        stream = await self.async_client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                usage_obj = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if content:
                text_parts.append(content)
                yield TextDelta(content)
            for tcd in (getattr(delta, "tool_calls", None) or []):
                slot = tc_acc.setdefault(getattr(tcd, "index", 0), {"id": "", "name": "", "args": ""})
                if getattr(tcd, "id", None):
                    slot["id"] = tcd.id
                fn = getattr(tcd, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] = fn.name
                    frag = getattr(fn, "arguments", None)
                    if frag:
                        slot["args"] += frag
                        # MVP-B: surface the argument fragment as it streams (capability-gated event).
                        yield ToolCallDelta(slot["id"], slot["name"], frag)

        tool_calls: list[ToolCallRequest] = []
        for idx in sorted(tc_acc):
            slot = tc_acc[idx]
            try:
                args = json.loads(slot["args"]) if slot["args"].strip() else {}
            except (json.JSONDecodeError, ValueError, TypeError):
                args = {}
            tool_calls.append(ToolCallRequest(id=slot["id"], name=slot["name"], arguments=args))

        token_usage = None
        if usage_obj is not None:
            _cached = _cached_input_tokens(usage_obj)
            token_usage = TokenUsage(
                input=max(0, usage_obj.prompt_tokens - _cached),
                output=usage_obj.completion_tokens,
                total=usage_obj.total_tokens,
                model_name=self.model,
                finish_reason=finish_reason,
                cache_read_input_tokens=_cached or None,
            )
        record_model_time_ms(int((time.time() - start_time) * 1000))
        yield TurnComplete(
            AgenticTurn(
                text="".join(text_parts),
                tool_calls=tool_calls,
                token_usage=token_usage,
                finish_reason=finish_reason,
                time_ms=int((time.time() - start_time) * 1000),
            )
        )


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

        # Some local APIs (Ollama, llama.cpp, LM Studio) don't require an API key, but the
        # installed `openai` client REJECTS api_key=None ("api_key must be set"), so a no-key
        # localhost endpoint must still receive a non-empty SENTINEL the server ignores. (The
        # old code set None here, which made create_agent raise for the ollama provider /
        # openai-compatible@localhost — broke the local micro-prime tier + any local-LLM lane.)
        if not actual_api_key and base_url:
            if 'localhost' in base_url or '127.0.0.1' in base_url:
                actual_api_key = "not-needed"

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

        # Firewall provenance capture (FR-J5a/J6): the most recent response's applied-adapter echo
        # and the exact system prompt sent. Read by the Jetson on-prem lane runner (same process)
        # to enforce the contamination firewall. None until the first agenerate() call.
        self.last_system_fingerprint: Optional[str] = None
        self.last_system_prompt: Optional[str] = None

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

        # Ensure OpenAI-specific connection errors are retryable.
        if self.retry_config is not None and OpenAIAPIConnectionError is not None:
            if OpenAIAPIConnectionError not in self.retry_config.retryable_exceptions:
                from dataclasses import replace as _dc_replace
                self.retry_config = _dc_replace(
                    self.retry_config,
                    retryable_exceptions=self.retry_config.retryable_exceptions + (OpenAIAPIConnectionError,),
                )

    def _is_openai_endpoint(self) -> bool:
        """True when this compatible agent points at the real OpenAI API.

        Next-gen param enforcement (max_completion_tokens / fixed temperature) is an OpenAI-API
        fact, so it must NOT be applied to third-party OpenAI-compatible servers (vLLM, Ollama,
        NIM) even if their model names happen to start with gpt-5/o-series prefixes.
        """
        return not self.base_url or "api.openai.com" in self.base_url

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

    async def _make_api_call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list] = None,
    ):
        """
        Make the raw API call to the OpenAI-compatible endpoint.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.

        Args:
            prompt: The user prompt text
            system_prompt: Optional system prompt. If provided, prepended as a
                ``{"role": "system", ...}`` message.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
            temperature: Optional sampling temperature override. When provided,
                passed to the API call. If None, the API default is used.
            stop: Optional list of stop sequences. When provided, the API will
                stop generating when any of these sequences is encountered.
        """
        messages = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        # Only enforce next-gen params against the real OpenAI endpoint (M3).
        kwargs = _build_chat_kwargs(
            self.model, messages, token_limit, temperature, stop,
            enforce_next_gen=self._is_openai_endpoint(),
        )
        return await self.async_client.chat.completions.create(**kwargs)

    async def agenerate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list] = None,
    ) -> GenerateResult:
        """
        Generate response using OpenAI-compatible API (async).

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text
            system_prompt: Optional per-call system prompt override. When provided,
                takes precedence over the instance-level ``self.system_prompt``.
                If neither is set, no system message is sent.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
                This is thread-safe — it avoids mutating the shared agent.
            temperature: Optional sampling temperature override. When provided,
                passed to the API call. If None, the API default is used.
            stop: Optional list of stop sequences. When provided, the API will
                stop generating when any of these sequences is encountered.

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
                response = await make_call(
                    prompt, system_prompt=effective_system_prompt,
                    max_tokens=max_tokens, temperature=temperature,
                    stop=stop,
                )
            else:
                response = await self._make_api_call(
                    prompt, system_prompt=effective_system_prompt,
                    max_tokens=max_tokens, temperature=temperature,
                    stop=stop,
                )

            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            # FR-J5a/J6 firewall capture: the server's applied-adapter echo + the prompt we sent.
            self.last_system_fingerprint = getattr(response, "system_fingerprint", None)
            self.last_system_prompt = effective_system_prompt

            response_text = response.choices[0].message.content

            # Extract finish_reason to detect truncation
            # OpenAI-compatible APIs use: "stop" (natural), "length" (truncated)
            finish_reason = getattr(response.choices[0], 'finish_reason', None)

            # Some APIs may not return usage info
            if hasattr(response, 'usage') and response.usage:
                _cached = _cached_input_tokens(response.usage)
                _prompt = response.usage.prompt_tokens or 0
                token_usage = TokenUsage(
                    input=max(0, _prompt - _cached),  # non-cached (DeepSeek/compat fold cache into prompt_tokens)
                    output=response.usage.completion_tokens or 0,
                    total=response.usage.total_tokens or 0,
                    model_name=self.model,
                    finish_reason=finish_reason,
                    cache_read_input_tokens=_cached or None,
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

            record_model_time_ms(response_time_ms)
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
