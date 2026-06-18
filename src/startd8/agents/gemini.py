"""
Google Gemini agent implementation.
"""

import asyncio
import logging
import os
import time
from typing import Any, Optional, Tuple

from ..models import TokenUsage, GenerateResult, StructuredResult
from .model_timing import record_model_time_ms  # FR-SPEED-1: accumulate pure model API time
from ..utils.retry import RetryConfig, RetryError, with_retry
from .base import BaseAgent
from .pool import TimeoutConfig, get_client_pool

logger = logging.getLogger(__name__)

# Optional Gemini import
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


class GeminiAgent(BaseAgent):
    """Google Gemini agent with async support, optional retry, configurable timeouts, and connection pooling"""

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
        model: str = "gemini-2.5-pro",  # Gemini 2.5 Pro - most capable stable (flagship default)
        api_key: Optional[str] = None,
        max_tokens: int = 32768,
        temperature: float = 0.7,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
        use_connection_pool: bool = False,
        safety_settings: Optional[list] = None,
        system_prompt: Optional[str] = None,
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
            use_connection_pool: If True, share HTTP clients with other agents using the same
                config. Reduces connection overhead for multi-agent workloads. Default: False.
            safety_settings: Optional list of safety setting dicts or SafetySetting objects
                to pass to Gemini's GenerateContentConfig.  Each entry should have
                ``category`` (e.g. "HARM_CATEGORY_DANGEROUS_CONTENT") and ``threshold``
                (e.g. "BLOCK_NONE").  When None, Gemini applies its default filters.
            system_prompt: Optional system prompt. Sent as ``system_instruction`` in
                Gemini's GenerateContentConfig. Can be overridden per-call via
                ``agenerate(prompt, system_prompt=...)``.

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
        self._use_connection_pool = use_connection_pool
        self._owns_clients = not use_connection_pool

        # Get or create client
        if use_connection_pool:
            pool = get_client_pool()
            self.client = pool.get_gemini_client(
                api_key=api_key,
                timeout_config=self.timeout_config
            )
        else:
            # Create the client with API key
            # Note: google-genai 1.x doesn't support custom http_client in Client()
            # Timeout is handled internally by the library
            self.client = genai.Client(api_key=api_key)

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

        self.safety_settings = safety_settings
        self.system_prompt = system_prompt

    async def _make_api_call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Make the raw API call to Gemini.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.

        Args:
            prompt: The user prompt text
            system_prompt: Optional system prompt. If provided, sent as
                ``system_instruction`` in the GenerateContentConfig.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
        """
        # google.genai Client API - run in executor for async compatibility
        # Create generation config
        config_kwargs = {
            "temperature": self.temperature,
            "max_output_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        if self.safety_settings:
            config_kwargs["safety_settings"] = self.safety_settings
        if system_prompt is not None:
            config_kwargs["system_instruction"] = system_prompt
        generation_config = genai_types.GenerateContentConfig(**config_kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=generation_config
            )
        )

    async def agenerate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> GenerateResult:
        """
        Generate response using Gemini async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text
            system_prompt: Optional per-call system prompt override. When provided,
                takes precedence over the instance-level ``self.system_prompt``.
                If neither is set, no system instruction is sent.
            max_tokens: Optional per-call max_tokens override. When provided,
                takes precedence over the instance-level ``self.max_tokens``.
                This is thread-safe — it avoids mutating the shared agent.

        Returns:
            GenerateResult(text, time_ms, token_usage)

        Raises:
            GeminiSafetyFilterError: If Gemini's content safety filter blocks the response
            RuntimeError: If Gemini API call fails for other reasons
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
                )
            else:
                response = await self._make_api_call(
                    prompt, system_prompt=effective_system_prompt, max_tokens=max_tokens,
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

        except (ConnectionError, OSError) as e:
            # Specific connection/network errors
            from ..logging_config import get_logger
            from ..exceptions import APIError

            local_logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            local_logger.error(
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
            from ..logging_config import get_logger
            from ..exceptions import APIError, AgentError

            local_logger = get_logger(__name__)
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
                    local_logger.error(
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
                    local_logger.error(
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
                local_logger.error(
                    f"DNS/connection error for {self.name}: {e}",
                    exc_info=True,
                    extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
                )
                raise AgentError(
                    dns_error_msg,
                    agent_name=self.name,
                    original_error=e
                ) from e

            # Generic API error fallback
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

        # Extract finish_reason to detect truncation
        # Gemini uses: "STOP" (natural), "MAX_TOKENS" (truncated), "SAFETY", etc.
        # Note: In google.genai, finish_reason may be on response or candidates[0]
        finish_reason = None
        if hasattr(response, 'candidates') and response.candidates:
            finish_reason = getattr(response.candidates[0], 'finish_reason', None)
        if not finish_reason:
            finish_reason = getattr(response, 'finish_reason', None)
        # Convert enum to string if needed
        if finish_reason and hasattr(finish_reason, 'name'):
            finish_reason = finish_reason.name

        # Extract response text
        # New google.genai API structure
        if not hasattr(response, 'text') or not response.text:
            # Distinguish SAFETY from other empty-response causes
            if finish_reason and finish_reason.upper() == "SAFETY":
                from ..exceptions import GeminiSafetyFilterError

                # Extract safety ratings for diagnostics
                safety_ratings = []
                if hasattr(response, 'candidates') and response.candidates:
                    raw = getattr(response.candidates[0], 'safety_ratings', None)
                    if raw:
                        safety_ratings = [
                            {
                                "category": getattr(r, 'category', None),
                                "probability": getattr(r, 'probability', None),
                                "blocked": getattr(r, 'blocked', None),
                            }
                            for r in raw
                        ]

                # Estimate prompt tokens for the diagnostic message
                prompt_tokens_est = max(1, int(len(prompt.split()) / 1.3))

                # Log the prompt that triggered the filter for investigation
                logger.warning(
                    "Gemini SAFETY filter triggered — logging prompt diagnostics",
                    extra={
                        "agent_name": self.name,
                        "model": self.model,
                        "prompt_tokens_est": prompt_tokens_est,
                        "prompt_chars": len(prompt),
                        "safety_ratings": safety_ratings,
                        "operation": "agenerate",
                    },
                )
                # Debug-level: first 2000 chars of the prompt for root-cause analysis
                logger.debug(
                    "SAFETY-blocked prompt sample (first 2000 chars): %s",
                    prompt[:2000],
                    extra={
                        "agent_name": self.name,
                        "model": self.model,
                        "operation": "agenerate_safety_diagnostics",
                    },
                )

                raise GeminiSafetyFilterError(
                    f"Gemini safety filter blocked response for prompt "
                    f"(~{prompt_tokens_est} tokens, {len(prompt)} chars). "
                    f"Safety ratings: {safety_ratings}. "
                    f"Try reducing context size or adjusting safety_settings.",
                    prompt_tokens=prompt_tokens_est,
                    safety_ratings=safety_ratings,
                )

            raise RuntimeError(
                f"Gemini returned empty response. "
                f"Finish reason: {finish_reason or 'unknown'}"
            )

        response_text = response.text

        # New google.genai API provides usage_metadata directly
        cached_tokens = 0  # Gemini implicit/explicit context cache (subset of prompt_token_count)
        try:
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                input_tokens = getattr(usage, 'prompt_token_count', 0)
                output_tokens = getattr(usage, 'candidates_token_count', 0)
                total_tokens = getattr(usage, 'total_token_count', input_tokens + output_tokens)
                cached_tokens = getattr(usage, 'cached_content_token_count', 0) or 0
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

        # Normalize Gemini's finish_reason for truncation detection
        # Gemini uses "MAX_TOKENS", we standardize to "max_tokens"
        normalized_finish_reason = finish_reason
        if finish_reason and finish_reason.upper() == "MAX_TOKENS":
            normalized_finish_reason = "max_tokens"

        token_usage = TokenUsage(
            input=max(0, int(input_tokens) - int(cached_tokens)),  # non-cached (cached is a subset)
            output=int(output_tokens),
            total=int(total_tokens),
            model_name=self.model,
            finish_reason=normalized_finish_reason,
            cache_read_input_tokens=int(cached_tokens) or None,
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

    async def _make_structured_api_call(
        self,
        prompt: str,
        output_schema: Any,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        """Raw structured call: Gemini controlled generation (JSON + response_schema).

        Sets ``response_mime_type="application/json"`` + ``response_schema`` (the
        Pydantic class) so the model returns a schema-shaped JSON object. Separated
        from ``_make_api_call`` so retry logic can wrap it without changing the
        plain-generate signature.
        """
        config_kwargs = {
            "temperature": self.temperature,
            "max_output_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "response_mime_type": "application/json",
            "response_schema": output_schema,
        }
        if self.safety_settings:
            config_kwargs["safety_settings"] = self.safety_settings
        if system_prompt is not None:
            config_kwargs["system_instruction"] = system_prompt
        generation_config = genai_types.GenerateContentConfig(**config_kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=generation_config,
            ),
        )

    async def agenerate_structured(
        self,
        prompt: str,
        output_schema: Any,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,  # accepted for parity; Gemini uses self.temperature
        retry_on_validation: bool = True,
    ) -> StructuredResult:
        """Structured output via Gemini controlled generation (``response_schema``).

        Mirrors :meth:`ClaudeAgent.agenerate_structured`: forces JSON matching
        *output_schema*, validates with Pydantic, and retries **once** on a
        ``ValidationError`` (feeding the error back) — a semantic retry distinct
        from the transport retry in ``utils.retry``. Returns
        ``StructuredResult(value, raw)`` so the 3-tuple ``GenerateResult`` contract
        is untouched. This is what makes ``gemini:`` usable as the app's
        ``DEFAULT_AGENT_SPEC`` / a structured pipeline role.

        Raises:
            TypeError: if *output_schema* is not a Pydantic ``BaseModel`` subclass.
            ValidationError / ValueError: if still invalid after the one retry.
            APIError: for transport failures (as in :meth:`agenerate`).
        """
        from pydantic import ValidationError

        from ..exceptions import APIError

        if not (isinstance(output_schema, type) and hasattr(output_schema, "model_json_schema")):
            raise TypeError("output_schema must be a Pydantic BaseModel subclass")

        effective_system_prompt = (
            system_prompt if system_prompt is not None else self.system_prompt
        )

        async def _call(p: str):
            try:
                if self.retry_config is not None:
                    make_call = with_retry(self.retry_config)(self._make_structured_api_call)
                    return await make_call(
                        p, output_schema, system_prompt=effective_system_prompt,
                        max_tokens=max_tokens,
                    )
                return await self._make_structured_api_call(
                    p, output_schema, system_prompt=effective_system_prompt,
                    max_tokens=max_tokens,
                )
            except RetryError as exc:
                raise APIError(
                    f"API call failed after {exc.attempts} attempts: {exc.last_exception}",
                    provider=self.name, original_error=exc.last_exception,
                ) from exc

        start_time = time.time()
        attempts = 2 if retry_on_validation else 1
        current_prompt = prompt
        last_error: Optional[Exception] = None

        for attempt in range(attempts):
            response = await _call(current_prompt)
            text = getattr(response, "text", None)
            try:
                if not text:
                    raise ValueError("model returned no JSON text")
                value = output_schema.model_validate_json(text)
            except (ValidationError, ValueError) as e:
                last_error = e
                logger.warning(
                    "Structured output failed for %s (attempt %d/%d): %s",
                    self.name, attempt + 1, attempts, e,
                )
                current_prompt = (
                    f"{prompt}\n\nYour previous response did not satisfy the required JSON "
                    f"schema (error: {e}). Respond again with ONLY a JSON object that validates "
                    f"against the schema."
                )
                continue

            response_time_ms = int((time.time() - start_time) * 1000)
            token_usage = None
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                _in = getattr(usage, "prompt_token_count", 0) or 0
                _out = getattr(usage, "candidates_token_count", 0) or 0
                _cached = getattr(usage, "cached_content_token_count", 0) or 0
                token_usage = TokenUsage(
                    input=max(0, int(_in) - int(_cached)),  # non-cached (cached is a subset)
                    output=int(_out),
                    total=int(getattr(usage, "total_token_count", _in + _out) or (_in + _out)),
                    model_name=self.model,
                    cache_read_input_tokens=int(_cached) or None,
                )
            record_model_time_ms(response_time_ms)
            raw = GenerateResult(value.model_dump_json(), response_time_ms, token_usage)
            return StructuredResult(value, raw)

        if last_error is not None:
            raise last_error
        raise RuntimeError("structured generation produced no result")  # unreachable
