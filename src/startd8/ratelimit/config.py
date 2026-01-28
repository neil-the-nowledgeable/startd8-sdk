"""
Rate limiting configuration for StartD8 SDK.

Provides configuration classes for rate limiting behavior, including
per-provider defaults and backpressure strategies.

Example:
    ```python
    from startd8.ratelimit import RateLimitConfig, BackpressureStrategy

    # Custom configuration
    config = RateLimitConfig(
        requests_per_minute=100,
        tokens_per_minute=100_000,
        backpressure_strategy=BackpressureStrategy.QUEUE,
    )

    # Get provider defaults
    from startd8.ratelimit.config import get_provider_limits
    limits = get_provider_limits("anthropic")
    ```
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BackpressureStrategy(str, Enum):
    """
    Strategy for handling requests when rate limits are reached.

    Attributes:
        QUEUE: Queue requests and wait for capacity (default)
        REJECT: Immediately reject requests when at limit
        ADAPTIVE: Dynamically adjust based on server responses
    """
    QUEUE = "queue"
    REJECT = "reject"
    ADAPTIVE = "adaptive"


@dataclass
class RateLimitConfig:
    """
    Configuration for rate limiting behavior.

    Controls how the rate limiter handles request and token limits,
    including backpressure strategy and queue behavior.

    Attributes:
        requests_per_minute: Maximum requests per minute. Default: 50
        tokens_per_minute: Maximum tokens per minute. Default: 100,000
        burst_multiplier: Multiplier for burst capacity. Default: 1.5
        backpressure_strategy: How to handle limit exceeded. Default: QUEUE
        max_queue_size: Maximum pending requests in queue. Default: 100
        max_wait_seconds: Maximum time to wait for capacity. Default: 60.0
        enabled: Whether rate limiting is enabled. Default: True

    Example:
        ```python
        config = RateLimitConfig(
            requests_per_minute=100,
            tokens_per_minute=200_000,
            backpressure_strategy=BackpressureStrategy.REJECT,
        )
        ```

    Raises:
        ValueError: If configuration values are invalid
    """

    requests_per_minute: int = 50
    tokens_per_minute: int = 100_000
    burst_multiplier: float = 1.5
    backpressure_strategy: BackpressureStrategy = BackpressureStrategy.QUEUE
    max_queue_size: int = 100
    max_wait_seconds: float = 60.0
    enabled: bool = True

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.requests_per_minute < 1:
            raise ValueError("requests_per_minute must be at least 1")
        if self.tokens_per_minute < 1:
            raise ValueError("tokens_per_minute must be at least 1")
        if self.burst_multiplier < 1.0:
            raise ValueError("burst_multiplier must be at least 1.0")
        if self.max_queue_size < 0:
            raise ValueError("max_queue_size must be non-negative")
        if self.max_wait_seconds < 0:
            raise ValueError("max_wait_seconds must be non-negative")

    @property
    def requests_per_second(self) -> float:
        """Calculate requests per second from RPM."""
        return self.requests_per_minute / 60.0

    @property
    def tokens_per_second(self) -> float:
        """Calculate tokens per second from TPM."""
        return self.tokens_per_minute / 60.0

    @property
    def burst_requests(self) -> int:
        """Maximum burst requests allowed."""
        return int(self.requests_per_minute * self.burst_multiplier / 60.0)

    @property
    def burst_tokens(self) -> int:
        """Maximum burst tokens allowed."""
        return int(self.tokens_per_minute * self.burst_multiplier / 60.0)


@dataclass
class ProviderLimits:
    """
    Default rate limits for a specific provider.

    Contains the standard limits published by each provider.
    These are conservative defaults and may vary based on your API tier.

    Attributes:
        provider: Provider name
        requests_per_minute: Default RPM for this provider
        tokens_per_minute: Default TPM for this provider
        notes: Additional notes about the limits
    """

    provider: str
    requests_per_minute: int
    tokens_per_minute: int
    notes: str = ""


# Default limits per provider
# These are conservative defaults based on typical API tiers
_PROVIDER_DEFAULTS: dict[str, ProviderLimits] = {
    "anthropic": ProviderLimits(
        provider="anthropic",
        requests_per_minute=50,
        tokens_per_minute=40_000,
        notes="Tier 1 defaults. Higher tiers have increased limits.",
    ),
    "openai": ProviderLimits(
        provider="openai",
        requests_per_minute=500,
        tokens_per_minute=200_000,
        notes="Pay-as-you-go defaults. Rate limits vary by model.",
    ),
    "gemini": ProviderLimits(
        provider="gemini",
        requests_per_minute=60,
        tokens_per_minute=60_000,
        notes="Free tier defaults. Paid tiers have higher limits.",
    ),
    "ollama": ProviderLimits(
        provider="ollama",
        requests_per_minute=1000,
        tokens_per_minute=1_000_000,
        notes="Local deployment - limits depend on hardware.",
    ),
    "mock": ProviderLimits(
        provider="mock",
        requests_per_minute=10_000,
        tokens_per_minute=10_000_000,
        notes="Mock provider for testing - high limits.",
    ),
}


def get_provider_limits(provider: str) -> Optional[ProviderLimits]:
    """
    Get default rate limits for a provider.

    Args:
        provider: Provider name (anthropic, openai, gemini, ollama, mock)

    Returns:
        ProviderLimits for the provider, or None if unknown

    Example:
        ```python
        limits = get_provider_limits("anthropic")
        if limits:
            print(f"Anthropic default RPM: {limits.requests_per_minute}")
        ```
    """
    return _PROVIDER_DEFAULTS.get(provider.lower())


def get_default_config(provider: Optional[str] = None) -> RateLimitConfig:
    """
    Get a default RateLimitConfig, optionally based on a provider.

    If a provider is specified and has known limits, those limits
    are used. Otherwise, conservative defaults are applied.

    Args:
        provider: Optional provider name to base defaults on

    Returns:
        RateLimitConfig with appropriate defaults

    Example:
        ```python
        # Generic defaults
        config = get_default_config()

        # Provider-specific defaults
        anthropic_config = get_default_config("anthropic")
        ```
    """
    if provider:
        limits = get_provider_limits(provider)
        if limits:
            return RateLimitConfig(
                requests_per_minute=limits.requests_per_minute,
                tokens_per_minute=limits.tokens_per_minute,
            )

    # Fall back to conservative defaults
    return RateLimitConfig()


def list_providers() -> list[str]:
    """
    List all providers with known default limits.

    Returns:
        List of provider names
    """
    return list(_PROVIDER_DEFAULTS.keys())
