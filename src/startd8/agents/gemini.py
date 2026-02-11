"""
Google Gemini agent implementation.
"""

import asyncio
import logging
import os
import time
from typing import Optional, Tuple

from ..models import TokenUsage, GenerateResult
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
        model: str = "gemini-2.0-flash",  # Gemini 2.0 Flash - latest stable model
        api_key: Optional[str] = None,
        max_tokens: int = 16384,
        temperature: float = 0.7,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_retry: bool = False,
        timeout_config: Optional[TimeoutConfig] = None,
        use_connection_pool: bool = False,
        safety_settings: Optional[list] = None,
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

    async def _make_api_call(self, prompt: str):
        """
        Make the raw API call to Gemini.

        This is separated from agenerate to allow retry logic to wrap it.
        Raises the raw API exceptions for retry handling.
        """
        # google.genai Client API - run in executor for async compatibility
        # Create generation config
        config_kwargs = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        if self.safety_settings:
            config_kwargs["safety_settings"] = self.safety_settings
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

    async def agenerate(self, prompt: str) -> GenerateResult:
        """
        Generate response using Gemini async API.

        If retry_config is set, transient failures (rate limits, server errors)
        will be automatically retried with exponential backoff.

        Args:
            prompt: The prompt text

        Returns:
            GenerateResult(text, time_ms, token_usage)

        Raises:
            GeminiSafetyFilterError: If Gemini's content safety filter blocks the response
            RuntimeError: If Gemini API call fails for other reasons
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

        # Normalize Gemini's finish_reason for truncation detection
        # Gemini uses "MAX_TOKENS", we standardize to "max_tokens"
        normalized_finish_reason = finish_reason
        if finish_reason and finish_reason.upper() == "MAX_TOKENS":
            normalized_finish_reason = "max_tokens"

        token_usage = TokenUsage(
            input=int(input_tokens),
            output=int(output_tokens),
            total=int(total_tokens),
            model_name=self.model,
            finish_reason=normalized_finish_reason,
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
