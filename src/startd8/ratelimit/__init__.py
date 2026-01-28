"""
Rate limiting for StartD8 SDK.

This module provides rate limiting capabilities for managing API call rates
across different LLM providers. It uses a token bucket algorithm with
dual buckets for both request count and token count limits.

Main components:
- RateLimiter: Async rate limiter with dual token buckets
- RateLimitConfig: Configuration for rate limiting behavior
- TokenBucket: Token bucket implementation
- BackpressureStrategy: Strategy enum for handling limit exceeded

Example:
    ```python
    from startd8.ratelimit import (
        RateLimiter,
        RateLimitConfig,
        BackpressureStrategy,
        get_rate_limiter,
    )

    # Create a custom rate limiter
    config = RateLimitConfig(
        requests_per_minute=100,
        tokens_per_minute=200_000,
        backpressure_strategy=BackpressureStrategy.QUEUE,
    )
    limiter = RateLimiter(config, name="my-api")

    # Use context manager
    async with limiter.acquire(estimated_tokens=1000):
        response = await client.generate(prompt)

    # Use decorator
    @limiter.limit(estimated_tokens=500)
    async def rate_limited_call():
        return await client.generate(prompt)

    # Use global registry
    limiter = get_rate_limiter("anthropic", provider="anthropic")
    ```
"""

from .config import (
    BackpressureStrategy,
    RateLimitConfig,
    ProviderLimits,
    get_provider_limits,
    get_default_config,
    list_providers,
)
from .rate_limiter import (
    RateLimiter,
    RateLimiterStats,
    TokenBucket,
    RateLimitExceededError,
    get_rate_limiter,
    get_rate_limiter_sync,
    clear_rate_limiters,
    list_rate_limiters,
)

__all__ = [
    # Config
    "BackpressureStrategy",
    "RateLimitConfig",
    "ProviderLimits",
    "get_provider_limits",
    "get_default_config",
    "list_providers",
    # Rate limiter
    "RateLimiter",
    "RateLimiterStats",
    "TokenBucket",
    "RateLimitExceededError",
    # Global registry
    "get_rate_limiter",
    "get_rate_limiter_sync",
    "clear_rate_limiters",
    "list_rate_limiters",
]
