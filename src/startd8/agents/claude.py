"""
Anthropic Claude agent implementation.
"""

import asyncio
import logging
import re
import time
from typing import Any, Optional, Tuple

from pydantic import ValidationError

from ..models import TokenUsage, GenerateResult, StructuredResult, AgenticTurn, ToolCallRequest
from .model_timing import record_model_time_ms  # FR-SPEED-1: accumulate pure model API time
from ..utils.retry import RetryConfig, RetryError, with_retry
from .base import BaseAgent
from .pool import TimeoutConfig, get_client_pool

logger = logging.getLogger(__name__)

# Largest verified-safe non-streaming ``max_tokens`` for Anthropic (M4 landmine L12). 32768 completes
# (it is the SDK's own default, used by the tier3 code-gen path); 49152 tripped the ">10-min streaming
# required" guard and 500'd (the app's old service.py). Until ClaudeAgent gains streaming support, any
# request above this is clamped (with a warning) so no caller can re-trigger that failure class.
NONSTREAMING_MAX_TOKENS_CEILING = 32768


def _is_fable_model(model: str) -> bool:
    """Return True for Claude Fable / Mythos models (adaptive-thinking tier)."""
    m = model.lower()
    return m.startswith("claude-fable") or m.startswith("claude-mythos")


def _extract_response_text(response: Any, stop_reason: Optional[str]) -> str:
    """Extract assistant text from an Anthropic Messages response."""
    if stop_reason == "refusal":
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                return text
        return "[Model declined this request (stop_reason=refusal)]"

    if not getattr(response, "content", None):
        return ""

    first = response.content[0]
    return getattr(first, "text", "") or ""

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
        model: str = "claude-opus-4-8",  # Claude Opus 4.8 - most capable (flagship default)
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

    async def _make_api_call(
        self,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[dict] = None,
        messages: Optional[list] = None,
    ):
        """
        Make the raw API call to Anthropic.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.

        Args:
            prompt: The user prompt text
            system_prompt: Optional system prompt. If provided, sent as the
                ``system`` parameter to the Anthropic API.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
                This avoids mutating the shared agent object, which is not
                thread-safe when chunks run concurrently.
            temperature: Optional sampling temperature (0.0–1.0). When provided,
                sent as the ``temperature`` parameter to the Anthropic API.
        """
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        if effective_max_tokens > NONSTREAMING_MAX_TOKENS_CEILING:
            logger.warning(
                "max_tokens=%d exceeds the non-streaming ceiling %d — clamping (L12; "
                "ClaudeAgent has no streaming yet, and higher values trip Anthropic's "
                "'>10-min streaming required' guard). agent=%s model=%s",
                effective_max_tokens, NONSTREAMING_MAX_TOKENS_CEILING, self.name, self.model,
            )
            effective_max_tokens = NONSTREAMING_MAX_TOKENS_CEILING
        kwargs = {
            "model": self.model,
            "max_tokens": effective_max_tokens,
            # FR-0: a full canonical message list (multi-turn tool loop) takes precedence; a single
            # prompt string is the legacy single-message convenience path.
            "messages": messages if messages is not None else [
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
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools is not None:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return await self.async_client.messages.create(**kwargs)

    async def agenerate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> GenerateResult:
        """
        Generate response using Claude async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text to send
            system_prompt: Optional per-call system prompt override. When provided,
                takes precedence over the instance-level ``self.system_prompt``.
                If neither is set, no system parameter is sent.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
                This is thread-safe — it avoids mutating the shared agent.
            temperature: Optional sampling temperature (0.0–1.0).

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
                response = await make_call(
                    prompt, system_prompt=effective_system_prompt, max_tokens=max_tokens,
                    temperature=temperature,
                )
            else:
                response = await self._make_api_call(
                    prompt, system_prompt=effective_system_prompt, max_tokens=max_tokens,
                    temperature=temperature,
                )

        except RetryError as e:
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
                },
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

        except Exception as e:
            from ..exceptions import APIError, AgentError

            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            error_msg = str(e)
            error_msg_lower = error_msg.lower()

            if "404" in error_msg and (
                "not found" in error_msg_lower
                or "not available" in error_msg_lower
                or "model" in error_msg_lower
            ):
                hint = (
                    "Use the canonical API id 'claude-fable-5' (not 'fable-5'). "
                    if _is_fable_model(self.model) or "fable" in self.model.lower()
                    else ""
                )
                model_error_msg = (
                    f"Model '{self.model}' not found or not available. "
                    f"{hint}"
                    f"Verify the model id and that your Anthropic account has access."
                )
                logger.error(
                    f"Model not found for {self.name}: {model_error_msg} (Original: {e})",
                    extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms},
                )
                raise AgentError(
                    model_error_msg,
                    agent_name=self.name,
                    original_error=e,
                ) from e

            logger.error(
                f"API call failed for {self.name}: {e}",
                exc_info=True,
                extra={
                    "agent_name": self.name,
                    "model": self.model,
                    "response_time_ms": response_time_ms,
                    "error_type": type(e).__name__,
                    "operation": "agenerate",
                },
            )
            raise APIError(
                f"API call failed: {error_msg}",
                provider=self.name,
                original_error=e,
            ) from e

        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)

        # Extract stop_reason to detect truncation / refusal
        # Anthropic uses: "end_turn" (natural), "max_tokens" (truncated),
        # "stop_sequence", "refusal" (Fable safety classifiers)
        stop_reason = getattr(response, 'stop_reason', None)
        response_text = _extract_response_text(response, stop_reason)

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

        record_model_time_ms(response_time_ms)
        return GenerateResult(response_text, response_time_ms, token_usage)

    async def agenerate_structured(
        self,
        prompt: str,
        output_schema: Any,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        retry_on_validation: bool = True,
    ) -> StructuredResult:
        """
        Generate a result validated against *output_schema* via Anthropic tool-use.

        Forces a single tool call whose ``input_schema`` is *output_schema*'s JSON schema, parses
        the ``tool_use`` block, and validates it. On a Pydantic ``ValidationError`` (or a missing
        tool call) the request is retried **once**, feeding the error back into the prompt — a
        *semantic* retry, distinct from the transport retry in ``utils.retry``. Returns
        ``StructuredResult(value, raw)`` so the 3-tuple ``GenerateResult`` contract is untouched.

        Raises:
            TypeError: If *output_schema* is not a Pydantic ``BaseModel`` subclass.
            ValidationError / ValueError: If the model still returns an invalid (or absent) object
                after the one retry — the caller (e.g. the generated AI wrapper) decides how to fail
                non-destructively.
            APIError / AgentError: For transport failures (as in :meth:`agenerate`).
        """
        if not (isinstance(output_schema, type) and hasattr(output_schema, "model_json_schema")):
            raise TypeError("output_schema must be a Pydantic BaseModel subclass")

        effective_system_prompt = (
            system_prompt if system_prompt is not None else self.system_prompt
        )

        tool_name = re.sub(
            r"[^a-zA-Z0-9_-]", "_", getattr(output_schema, "__name__", "extract")
        )[:64]
        tool = {
            "name": tool_name,
            "description": (output_schema.__doc__ or f"Return a {tool_name} object.").strip(),
            "input_schema": output_schema.model_json_schema(),
        }
        tool_choice = {"type": "tool", "name": tool_name}

        async def _call(p: str):
            from ..exceptions import APIError

            try:
                if self.retry_config is not None:
                    make_call = with_retry(self.retry_config)(self._make_api_call)
                    return await make_call(
                        p, system_prompt=effective_system_prompt, max_tokens=max_tokens,
                        temperature=temperature, tools=[tool], tool_choice=tool_choice,
                    )
                return await self._make_api_call(
                    p, system_prompt=effective_system_prompt, max_tokens=max_tokens,
                    temperature=temperature, tools=[tool], tool_choice=tool_choice,
                )
            except RetryError as exc:  # all transport retries exhausted — wrap like agenerate (L3)
                raise APIError(
                    f"API call failed after {exc.attempts} attempts: {exc.last_exception}",
                    provider=self.name,
                    original_error=exc.last_exception,
                ) from exc

        start_time = time.time()
        attempts = 2 if retry_on_validation else 1
        current_prompt = prompt
        last_error: Optional[Exception] = None

        for attempt in range(attempts):
            response = await _call(current_prompt)

            tool_input = None
            for block in getattr(response, "content", None) or []:
                if getattr(block, "type", None) == "tool_use":
                    tool_input = block.input
                    break

            try:
                if tool_input is None:
                    raise ValueError("model returned no tool_use block")
                value = output_schema.model_validate(tool_input)
            except ValidationError as e:
                last_error = e
                logger.warning(
                    "Structured output failed validation for %s (attempt %d/%d): %s",
                    self.name, attempt + 1, attempts, e,
                )
                current_prompt = (
                    f"{prompt}\n\nYour previous `{tool_name}` tool call failed schema validation "
                    f"with these errors:\n{e}\n\nCall `{tool_name}` again with a corrected object "
                    f"that satisfies the schema."
                )
                continue
            except ValueError as e:
                last_error = e
                logger.warning(
                    "Structured output missing tool_use block for %s (attempt %d/%d)",
                    self.name, attempt + 1, attempts,
                )
                current_prompt = (
                    f"{prompt}\n\nYou must call the `{tool_name}` tool to return the result."
                )
                continue

            # Success — build the raw GenerateResult, mirroring agenerate's usage extraction.
            response_time_ms = int((time.time() - start_time) * 1000)
            stop_reason = getattr(response, "stop_reason", None)
            usage = getattr(response, "usage", None)
            token_usage = None
            if usage is not None:
                _raw_creation = getattr(usage, "cache_creation_input_tokens", None)
                _raw_read = getattr(usage, "cache_read_input_tokens", None)
                token_usage = TokenUsage(
                    input=usage.input_tokens,
                    output=usage.output_tokens,
                    total=usage.input_tokens + usage.output_tokens,
                    model_name=self.model,
                    finish_reason=stop_reason,
                    cache_creation_input_tokens=(
                        _raw_creation if isinstance(_raw_creation, int) else None
                    ),
                    cache_read_input_tokens=(
                        _raw_read if isinstance(_raw_read, int) else None
                    ),
                )
            record_model_time_ms(response_time_ms)
            raw = GenerateResult(value.model_dump_json(), response_time_ms, token_usage)
            return StructuredResult(value, raw)

        # Single retry exhausted — surface the last error for non-destructive handling upstream.
        if last_error is not None:
            raise last_error
        raise RuntimeError("structured generation produced no result")  # unreachable; not an assert (L1)

    def supports_tool_use(self) -> bool:
        """ClaudeAgent implements the FR-0 tool-use primitive (:meth:`agenerate_tools`)."""
        return True

    async def agenerate_tools(
        self,
        messages: "list[dict] | str",
        tools: list,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AgenticTurn:
        """One agentic turn (FR-0): present *tools* unforced, return text + all tool calls.

        Generalizes :meth:`agenerate_structured` — N tools instead of one, no ``tool_choice``
        forcing, no schema validation. Accepts a **canonical message list** (so the loop can thread
        prior ``tool_use``/``tool_result`` blocks back; a bare ``str`` is wrapped). Anthropic carries
        ``system`` out-of-band, so it is passed separately, not inside ``messages``. Parses every
        ``tool_use`` block into a :class:`ToolCallRequest` and concatenates ``text`` blocks. Transport
        retry/usage extraction mirror :meth:`agenerate`.
        """
        from ..exceptions import APIError

        msgs = self._normalize_messages(messages)
        effective_system_prompt = (
            system_prompt if system_prompt is not None else self.system_prompt
        )

        api_tools = tools or None  # empty tool set => omit the kwarg (Anthropic rejects tools=[])

        async def _call():
            try:
                if self.retry_config is not None:
                    make_call = with_retry(self.retry_config)(self._make_api_call)
                    return await make_call(
                        messages=msgs, system_prompt=effective_system_prompt, max_tokens=max_tokens,
                        temperature=temperature, tools=api_tools,
                    )
                return await self._make_api_call(
                    messages=msgs, system_prompt=effective_system_prompt, max_tokens=max_tokens,
                    temperature=temperature, tools=api_tools,
                )
            except RetryError as exc:  # mirror agenerate (L3): wrap exhausted transport retries
                raise APIError(
                    f"API call failed after {exc.attempts} attempts: {exc.last_exception}",
                    provider=self.name,
                    original_error=exc.last_exception,
                ) from exc

        start_time = time.time()
        response = await _call()
        return self._turn_from_message(response, start_time)

    def _turn_from_message(self, response: Any, start_time: float) -> AgenticTurn:
        """Parse an Anthropic Messages response (or a streamed final message) into an AgenticTurn.

        Shared by :meth:`agenerate_tools` and :meth:`agenerate_tools_stream` so the streaming and
        non-streaming paths produce a structurally-identical turn (FR-S2 parity)."""
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in getattr(response, "content", None) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=getattr(block, "id", "") or "",
                        name=getattr(block, "name", "") or "",
                        arguments=dict(getattr(block, "input", None) or {}),
                    )
                )

        response_time_ms = int((time.time() - start_time) * 1000)
        stop_reason = getattr(response, "stop_reason", None)
        usage = getattr(response, "usage", None)
        token_usage = None
        if usage is not None:
            _raw_creation = getattr(usage, "cache_creation_input_tokens", None)
            _raw_read = getattr(usage, "cache_read_input_tokens", None)
            token_usage = TokenUsage(
                input=usage.input_tokens,
                output=usage.output_tokens,
                total=usage.input_tokens + usage.output_tokens,
                model_name=self.model,
                finish_reason=stop_reason,
                cache_creation_input_tokens=(
                    _raw_creation if isinstance(_raw_creation, int) else None
                ),
                cache_read_input_tokens=(
                    _raw_read if isinstance(_raw_read, int) else None
                ),
            )
        record_model_time_ms(response_time_ms)
        return AgenticTurn(
            text="".join(text_parts),
            tool_calls=tool_calls,
            token_usage=token_usage,
            finish_reason=stop_reason,
            time_ms=response_time_ms,
        )

    def supports_streaming(self) -> bool:
        """ClaudeAgent implements per-token streaming (FR-S2, MVP-A)."""
        return True

    async def agenerate_tools_stream(
        self,
        messages: "list[dict] | str",
        tools: list,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        """Stream a tool-use turn (FR-S2). Yields :class:`TextDelta` per text fragment (and, MVP-B,
        :class:`ToolCallDelta` per streamed tool-arg fragment + :class:`ReasoningDelta` per thinking
        fragment), then a terminal :class:`TurnComplete` carrying the accumulated turn. The turn's tool
        calls are assembled from the stream's final message (Anthropic's ``get_final_message``), so it
        is structurally identical to the non-streaming path regardless of how deltas arrived."""
        from ..models import ReasoningDelta, TextDelta, ToolCallDelta, TurnComplete

        msgs = self._normalize_messages(messages)
        effective_system = system_prompt if system_prompt is not None else self.system_prompt
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        kwargs: dict = {"model": self.model, "max_tokens": effective_max_tokens, "messages": msgs}
        if effective_system is not None:
            kwargs["system"] = effective_system
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools

        start_time = time.time()
        # Track the tool_use block currently streaming (id/name arrive on content_block_start) so a
        # streamed input_json_delta can be surfaced as a ToolCallDelta with its call id/name.
        block: dict = {"id": "", "name": ""}
        async with self.async_client.messages.stream(**kwargs) as stream:
            async for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_start":
                    cb = getattr(event, "content_block", None)
                    if getattr(cb, "type", None) == "tool_use":
                        block = {"id": getattr(cb, "id", "") or "", "name": getattr(cb, "name", "") or ""}
                elif etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    dtype = getattr(delta, "type", None)
                    if dtype == "text_delta":
                        text = getattr(delta, "text", "") or ""
                        if text:
                            yield TextDelta(text)
                    elif dtype == "input_json_delta":  # MVP-B: streamed tool-call args
                        frag = getattr(delta, "partial_json", "") or ""
                        if frag:
                            yield ToolCallDelta(block["id"], block["name"], frag)
                    elif dtype == "thinking_delta":  # MVP-B: extended-thinking reasoning
                        think = getattr(delta, "thinking", "") or ""
                        if think:
                            yield ReasoningDelta(think)
            final_message = await stream.get_final_message()
        yield TurnComplete(self._turn_from_message(final_message, start_time))
