"""
Rate limiter implementation with token bucket algorithm.

Provides async-first rate limiting with dual buckets for both
request count and token count limits.

Example:
    ```python
    from startd8.ratelimit import RateLimiter, RateLimitConfig

    # Create a rate limiter
    config = RateLimitConfig(requests_per_minute=60, tokens_per_minute=100_000)
    limiter = RateLimiter(config, name="anthropic")

    # Acquire capacity
    async with limiter.acquire(estimated_tokens=1000):
        response = await client.generate(prompt)

    # Or use the decorator
    @limiter.limit(estimated_tokens=500)
    async def my_api_call():
        return await client.generate(prompt)
    ```
"""

import asyncio
import functools
import logging
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Optional,
    TypeVar,
)

from .config import BackpressureStrategy, RateLimitConfig, get_default_config

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimitExceededError(Exception):
    """
    Raised when rate limit is exceeded and backpressure strategy is REJECT.

    Attributes:
        limiter_name: Name of the rate limiter
        wait_time: Estimated seconds until capacity available
        bucket_type: Which bucket triggered the error ('requests' or 'tokens')
    """

    def __init__(
        self,
        message: str,
        limiter_name: str = "",
        wait_time: float = 0.0,
        bucket_type: str = "requests",
    ):
        super().__init__(message)
        self.limiter_name = limiter_name
        self.wait_time = wait_time
        self.bucket_type = bucket_type


@dataclass
class RateLimiterStats:
    """
    Statistics for rate limiter usage.

    Attributes:
        requests_made: Total requests processed
        requests_queued: Total requests that had to wait
        requests_rejected: Total requests rejected (REJECT strategy)
        tokens_consumed: Total tokens consumed
        total_wait_time: Total time spent waiting for capacity
        last_request_time: Timestamp of last request
    """

    requests_made: int = 0
    requests_queued: int = 0
    requests_rejected: int = 0
    tokens_consumed: int = 0
    total_wait_time: float = 0.0
    last_request_time: float = 0.0


class TokenBucket:
    """
    Token bucket implementation for rate limiting.

    Uses the token bucket algorithm where tokens are added at a steady
    rate up to a maximum capacity (burst). Requests consume tokens
    and must wait if insufficient tokens are available.

    Attributes:
        capacity: Maximum tokens in the bucket (burst limit)
        refill_rate: Tokens added per second
        tokens: Current token count
        last_refill: Last refill timestamp
    """

    def __init__(self, capacity: float, refill_rate: float):
        """
        Initialize a token bucket.

        Args:
            capacity: Maximum tokens (burst limit)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity  # Start full
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def try_acquire(self, amount: float = 1.0) -> bool:
        """
        Try to acquire tokens without blocking.

        Args:
            amount: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False otherwise
        """
        with self._lock:
            self._refill()
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    def time_until_available(self, amount: float = 1.0) -> float:
        """
        Calculate time until requested tokens are available.

        Args:
            amount: Number of tokens needed

        Returns:
            Seconds until tokens are available (0 if available now)
        """
        with self._lock:
            self._refill()
            if self.tokens >= amount:
                return 0.0
            tokens_needed = amount - self.tokens
            return tokens_needed / self.refill_rate

    def available(self) -> float:
        """Get current available tokens."""
        with self._lock:
            self._refill()
            return self.tokens

    def reset(self) -> None:
        """Reset bucket to full capacity."""
        with self._lock:
            self.tokens = self.capacity
            self.last_refill = time.monotonic()


class RateLimiter:
    """
    Async rate limiter with dual token buckets.

    Maintains separate buckets for request count and token count,
    enforcing both limits simultaneously. Supports multiple
    backpressure strategies for handling limit exceeded scenarios.

    Attributes:
        config: Rate limit configuration
        name: Identifier for this limiter
        request_bucket: Token bucket for request rate
        token_bucket: Token bucket for token rate
        stats: Usage statistics

    Example:
        ```python
        limiter = RateLimiter(
            RateLimitConfig(requests_per_minute=60),
            name="my-api"
        )

        # Context manager usage
        async with limiter.acquire(estimated_tokens=500):
            await api_call()

        # Decorator usage
        @limiter.limit(estimated_tokens=500)
        async def rate_limited_call():
            await api_call()
        ```
    """

    def __init__(
        self,
        config: Optional[RateLimitConfig] = None,
        name: str = "default",
    ):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration. Uses defaults if not provided.
            name: Identifier for this limiter (used in logs and errors)
        """
        self.config = config or get_default_config()
        self.name = name
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[asyncio.Event] = asyncio.Queue()
        self._stats = RateLimiterStats()

        # Initialize dual buckets
        self.request_bucket = TokenBucket(
            capacity=self.config.burst_requests,
            refill_rate=self.config.requests_per_second,
        )
        self.token_bucket = TokenBucket(
            capacity=self.config.burst_tokens,
            refill_rate=self.config.tokens_per_second,
        )

    @property
    def stats(self) -> RateLimiterStats:
        """Get current statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset statistics to zero."""
        self._stats = RateLimiterStats()

    def reset_buckets(self) -> None:
        """Reset both buckets to full capacity."""
        self.request_bucket.reset()
        self.token_bucket.reset()

    @asynccontextmanager
    async def acquire(self, estimated_tokens: int = 1):
        """
        Acquire rate limit capacity as an async context manager.

        Waits for both request and token capacity to be available
        before yielding. The strategy determines behavior when limits
        are exceeded.

        Args:
            estimated_tokens: Estimated tokens for this request

        Yields:
            None when capacity is acquired

        Raises:
            RateLimitExceededError: If REJECT strategy and limits exceeded
            asyncio.TimeoutError: If wait exceeds max_wait_seconds

        Example:
            ```python
            async with limiter.acquire(estimated_tokens=1000):
                response = await client.generate(prompt)
            ```
        """
        if not self.config.enabled:
            yield
            return

        start_time = time.monotonic()
        queued = False

        try:
            # Try immediate acquisition
            if self._try_acquire_both(estimated_tokens):
                self._stats.requests_made += 1
                self._stats.tokens_consumed += estimated_tokens
                self._stats.last_request_time = time.monotonic()
                yield
                return

            # Handle based on strategy
            if self.config.backpressure_strategy == BackpressureStrategy.REJECT:
                self._stats.requests_rejected += 1
                wait_time = max(
                    self.request_bucket.time_until_available(1.0),
                    self.token_bucket.time_until_available(estimated_tokens),
                )
                raise RateLimitExceededError(
                    f"Rate limit exceeded for '{self.name}'. "
                    f"Retry in {wait_time:.2f}s",
                    limiter_name=self.name,
                    wait_time=wait_time,
                    bucket_type="requests"
                    if self.request_bucket.available() < 1
                    else "tokens",
                )

            # Queue strategy - wait for capacity
            queued = True
            self._stats.requests_queued += 1

            await self._wait_for_capacity(estimated_tokens)

            wait_time = time.monotonic() - start_time
            self._stats.total_wait_time += wait_time
            self._stats.requests_made += 1
            self._stats.tokens_consumed += estimated_tokens
            self._stats.last_request_time = time.monotonic()

            logger.debug(
                f"Rate limiter '{self.name}' acquired after {wait_time:.3f}s wait",
                extra={
                    "limiter_name": self.name,
                    "wait_time": wait_time,
                    "estimated_tokens": estimated_tokens,
                },
            )

            yield

        except asyncio.CancelledError:
            logger.debug(f"Rate limiter '{self.name}' acquire cancelled")
            raise

    def _try_acquire_both(self, tokens: int) -> bool:
        """Try to acquire from both buckets atomically."""
        # Check both buckets first
        if (
            self.request_bucket.tokens >= 1.0
            and self.token_bucket.tokens >= tokens
        ):
            # Acquire from both
            request_acquired = self.request_bucket.try_acquire(1.0)
            if request_acquired:
                token_acquired = self.token_bucket.try_acquire(tokens)
                if not token_acquired:
                    # Rollback request acquisition - this shouldn't happen
                    # but handle it gracefully
                    self.request_bucket.tokens = min(
                        self.request_bucket.capacity,
                        self.request_bucket.tokens + 1.0,
                    )
                    return False
                return True
        return False

    async def _wait_for_capacity(self, estimated_tokens: int) -> None:
        """Wait until capacity is available."""
        deadline = time.monotonic() + self.config.max_wait_seconds

        while True:
            # Check timeout
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError(
                    f"Rate limiter '{self.name}' wait exceeded "
                    f"{self.config.max_wait_seconds}s"
                )

            # Calculate wait time
            request_wait = self.request_bucket.time_until_available(1.0)
            token_wait = self.token_bucket.time_until_available(estimated_tokens)
            wait_time = max(request_wait, token_wait)

            if wait_time > 0:
                # Don't wait longer than remaining timeout
                actual_wait = min(wait_time, remaining)
                await asyncio.sleep(actual_wait)

            # Try to acquire
            if self._try_acquire_both(estimated_tokens):
                return

            # Small delay before retry to prevent busy-waiting
            await asyncio.sleep(0.01)

    def limit(
        self,
        estimated_tokens: int = 1,
    ) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
        """
        Decorator for rate-limiting async functions.

        Wraps an async function to automatically acquire rate limit
        capacity before execution.

        Args:
            estimated_tokens: Estimated tokens for each call

        Returns:
            Decorator function

        Example:
            ```python
            limiter = RateLimiter(config, name="api")

            @limiter.limit(estimated_tokens=500)
            async def call_api(prompt: str):
                return await client.generate(prompt)

            # Each call will be rate limited
            result = await call_api("Hello")
            ```
        """

        def decorator(
            func: Callable[..., Awaitable[T]]
        ) -> Callable[..., Awaitable[T]]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T:
                async with self.acquire(estimated_tokens=estimated_tokens):
                    return await func(*args, **kwargs)

            return wrapper

        return decorator


# =============================================================================
# Global Registry
# =============================================================================

_rate_limiters: Dict[str, RateLimiter] = {}
_registry_lock = threading.Lock()


def get_rate_limiter(
    name: str = "default",
    config: Optional[RateLimitConfig] = None,
    provider: Optional[str] = None,
) -> RateLimiter:
    """
    Get or create a rate limiter by name.

    Returns an existing limiter if one exists with the given name,
    otherwise creates a new one. If config is provided and a limiter
    already exists, the existing limiter is returned (config is ignored).

    Args:
        name: Unique identifier for the rate limiter
        config: Configuration for new limiter (ignored if exists)
        provider: Provider name for default config (ignored if config provided)

    Returns:
        RateLimiter instance

    Example:
        ```python
        # Get or create with defaults
        limiter = get_rate_limiter("my-api")

        # Get or create with custom config
        config = RateLimitConfig(requests_per_minute=100)
        limiter = get_rate_limiter("my-api", config=config)

        # Get or create with provider defaults
        limiter = get_rate_limiter("anthropic-limiter", provider="anthropic")
        ```
    """
    with _registry_lock:
        if name not in _rate_limiters:
            if config is None:
                config = get_default_config(provider)
            _rate_limiters[name] = RateLimiter(config=config, name=name)
        return _rate_limiters[name]


def get_rate_limiter_sync(
    name: str = "default",
    config: Optional[RateLimitConfig] = None,
    provider: Optional[str] = None,
) -> RateLimiter:
    """
    Synchronous version of get_rate_limiter.

    Identical to get_rate_limiter but named explicitly for sync contexts.
    The rate limiter itself still uses async acquire methods.

    Args:
        name: Unique identifier for the rate limiter
        config: Configuration for new limiter
        provider: Provider name for default config

    Returns:
        RateLimiter instance
    """
    return get_rate_limiter(name=name, config=config, provider=provider)


def clear_rate_limiters() -> None:
    """
    Clear all rate limiters from the global registry.

    Useful for testing or resetting state.

    Example:
        ```python
        # In test teardown
        clear_rate_limiters()
        ```
    """
    with _registry_lock:
        _rate_limiters.clear()


def list_rate_limiters() -> list[str]:
    """
    List all registered rate limiter names.

    Returns:
        List of rate limiter names
    """
    with _registry_lock:
        return list(_rate_limiters.keys())
