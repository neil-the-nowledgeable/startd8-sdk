"""
Mock agents for testing.
"""

import asyncio
from typing import Optional, Tuple, TYPE_CHECKING

from ..models import TokenUsage, GenerateResult
from .base import BaseAgent
from .openai import OpenAICompatibleAgent

if TYPE_CHECKING:
    from .pool import TimeoutConfig
    from ..utils.retry import RetryConfig


class MockAgent(BaseAgent):
    """Mock agent for testing with async support"""

    def __init__(
        self,
        name: str = "mock",
        model: str = "mock-model",
        timeout_config: Optional["TimeoutConfig"] = None,
        retry_config: Optional["RetryConfig"] = None,
        **kwargs,
    ):
        """
        Initialize mock agent.

        Args:
            name: Agent identifier
            model: Model name
            timeout_config: Optional timeout configuration (stored for inspection)
            retry_config: Optional retry configuration (stored for inspection)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(name, model)
        self.timeout_config = timeout_config
        self.retry_config = retry_config

    async def agenerate(self, prompt: str) -> GenerateResult:
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

        return GenerateResult(response, response_time_ms, token_usage)


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
