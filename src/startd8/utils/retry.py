"""
Retry utilities with exponential backoff for transient failure handling.

Provides decorators and utilities for retrying operations that may fail
due to transient issues like network timeouts, rate limits, or temporary
service unavailability.

Example:
    ```python
    from startd8.utils.retry import with_retry, RetryConfig

    # Default retry behavior
    @with_retry()
    async def call_api():
        return await client.request()

    # Custom configuration
    config = RetryConfig(
        max_attempts=5,
        base_delay=2.0,
        retryable_status_codes=(429, 503),
    )

    @with_retry(config)
    async def call_rate_limited_api():
        return await client.request()
    ```
"""

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    Awaitable,
)

logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar('T')


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of attempts (including initial). Default: 3
        base_delay: Base delay in seconds before first retry. Default: 1.0
        max_delay: Maximum delay between retries. Default: 60.0
        exponential_base: Base for exponential backoff. Default: 2.0
        jitter: Whether to add random jitter to delays. Default: True
        jitter_factor: Maximum jitter as fraction of delay. Default: 0.1
        retryable_exceptions: Tuple of exception types to retry on.
        retryable_status_codes: HTTP status codes that should trigger retry.
        on_retry: Optional callback called before each retry.

    Example:
        ```python
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            retryable_exceptions=(ConnectionError, TimeoutError),
            retryable_status_codes=(429, 500, 502, 503, 504),
        )
        ```
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.1
    retryable_exceptions: Tuple[Type[Exception], ...] = field(
        default_factory=lambda: (
            ConnectionError,
            TimeoutError,
            OSError,
        )
    )
    retryable_status_codes: Tuple[int, ...] = field(
        default_factory=lambda: (429, 500, 502, 503, 504)
    )
    on_retry: Optional[Callable[[int, Exception, float], None]] = None

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay < 0:
            raise ValueError("base_delay must be non-negative")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")


class RetryError(Exception):
    """
    Raised when all retry attempts have been exhausted.

    Attributes:
        attempts: Number of attempts made
        last_exception: The last exception that caused failure
        total_time: Total time spent on all attempts
    """

    def __init__(
        self,
        message: str,
        attempts: int,
        last_exception: Exception,
        total_time: float,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception
        self.total_time = total_time


def _calculate_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """
    Calculate delay before next retry using exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * (exponential_base ^ attempt)
    delay = config.base_delay * (config.exponential_base ** attempt)

    # Cap at max_delay
    delay = min(delay, config.max_delay)

    # Add jitter if enabled
    if config.jitter:
        jitter_range = delay * config.jitter_factor
        delay += random.uniform(-jitter_range, jitter_range)
        # Ensure delay doesn't go negative
        delay = max(0.0, delay)

    return delay


def _is_retryable_exception(
    exception: Exception,
    config: RetryConfig,
) -> bool:
    """
    Check if an exception should trigger a retry.

    Args:
        exception: The exception to check
        config: Retry configuration

    Returns:
        True if the exception is retryable
    """
    # Check if it's a direct instance of retryable exceptions
    if isinstance(exception, config.retryable_exceptions):
        return True

    # Check for HTTP status codes in common exception patterns
    status_code = _extract_status_code(exception)
    if status_code and status_code in config.retryable_status_codes:
        return True

    return False


def _extract_status_code(exception: Exception) -> Optional[int]:
    """
    Extract HTTP status code from various exception types.

    Handles common patterns from httpx, requests, and SDK exceptions.

    Args:
        exception: The exception to extract status code from

    Returns:
        Status code if found, None otherwise
    """
    # Direct status_code attribute (common in HTTP libraries)
    if hasattr(exception, 'status_code'):
        return getattr(exception, 'status_code')

    # httpx response attribute
    if hasattr(exception, 'response'):
        response = getattr(exception, 'response')
        if response and hasattr(response, 'status_code'):
            return getattr(response, 'status_code')

    # Check in exception args or message for common patterns
    exc_str = str(exception)
    for code in (429, 500, 502, 503, 504):
        if str(code) in exc_str:
            # Be careful - only return if it looks like a status code
            if f'status {code}' in exc_str.lower() or f'error {code}' in exc_str.lower():
                return code

    return None


def _extract_retry_after(exception: Exception) -> Optional[float]:
    """
    Extract Retry-After header value from exception if present.

    Args:
        exception: The exception to check

    Returns:
        Retry-After value in seconds, or None if not found
    """
    # Check direct retry_after attribute
    if hasattr(exception, 'retry_after'):
        retry_after = getattr(exception, 'retry_after')
        if retry_after is not None:
            return float(retry_after)

    # Check response headers
    if hasattr(exception, 'response'):
        response = getattr(exception, 'response')
        if response and hasattr(response, 'headers'):
            headers = getattr(response, 'headers')
            retry_after = headers.get('Retry-After') or headers.get('retry-after')
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass

    return None


def with_retry(
    config: Optional[RetryConfig] = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator for retrying async functions with exponential backoff.

    Retries the decorated function when it raises retryable exceptions
    or returns responses with retryable status codes.

    Args:
        config: Retry configuration. Uses defaults if not provided.

    Returns:
        Decorator function

    Example:
        ```python
        @with_retry()
        async def fetch_data():
            async with httpx.AsyncClient() as client:
                return await client.get("https://api.example.com/data")

        @with_retry(RetryConfig(max_attempts=5, base_delay=2.0))
        async def call_flaky_api():
            return await flaky_client.request()
        ```

    Raises:
        RetryError: When all retry attempts are exhausted
    """
    effective_config = config or RetryConfig()

    def decorator(
        func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            start_time = time.monotonic()
            last_exception: Optional[Exception] = None

            for attempt in range(effective_config.max_attempts):
                try:
                    return await func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if we should retry
                    if not _is_retryable_exception(e, effective_config):
                        logger.debug(
                            f"Non-retryable exception in {func.__name__}: {type(e).__name__}",
                            extra={
                                "function": func.__name__,
                                "exception_type": type(e).__name__,
                                "attempt": attempt + 1,
                            }
                        )
                        raise

                    # Check if we have attempts remaining
                    if attempt >= effective_config.max_attempts - 1:
                        break

                    # Calculate delay
                    delay = _calculate_delay(attempt, effective_config)

                    # Check for Retry-After header
                    retry_after = _extract_retry_after(e)
                    if retry_after is not None:
                        delay = max(delay, retry_after)
                        # Cap at max_delay
                        delay = min(delay, effective_config.max_delay)

                    logger.warning(
                        f"Retry {attempt + 1}/{effective_config.max_attempts} for "
                        f"{func.__name__} after {type(e).__name__}: {e}. "
                        f"Waiting {delay:.2f}s",
                        extra={
                            "function": func.__name__,
                            "exception_type": type(e).__name__,
                            "attempt": attempt + 1,
                            "max_attempts": effective_config.max_attempts,
                            "delay_seconds": delay,
                        }
                    )

                    # Call on_retry callback if provided
                    if effective_config.on_retry:
                        try:
                            effective_config.on_retry(attempt + 1, e, delay)
                        except Exception as callback_err:
                            logger.debug(
                                f"on_retry callback failed: {callback_err}",
                                exc_info=True
                            )

                    # Wait before retry
                    await asyncio.sleep(delay)

            # All attempts exhausted
            total_time = time.monotonic() - start_time
            error_msg = (
                f"All {effective_config.max_attempts} retry attempts exhausted "
                f"for {func.__name__} after {total_time:.2f}s"
            )
            logger.error(
                error_msg,
                extra={
                    "function": func.__name__,
                    "total_attempts": effective_config.max_attempts,
                    "total_time_seconds": total_time,
                    "last_exception_type": type(last_exception).__name__ if last_exception else None,
                }
            )

            raise RetryError(
                error_msg,
                attempts=effective_config.max_attempts,
                last_exception=last_exception,
                total_time=total_time,
            ) from last_exception

        return wrapper
    return decorator


def with_retry_sync(
    config: Optional[RetryConfig] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying synchronous functions with exponential backoff.

    Same behavior as with_retry but for sync functions.

    Args:
        config: Retry configuration. Uses defaults if not provided.

    Returns:
        Decorator function

    Example:
        ```python
        @with_retry_sync()
        def fetch_data():
            return requests.get("https://api.example.com/data")
        ```
    """
    effective_config = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            start_time = time.monotonic()
            last_exception: Optional[Exception] = None

            for attempt in range(effective_config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    if not _is_retryable_exception(e, effective_config):
                        raise

                    if attempt >= effective_config.max_attempts - 1:
                        break

                    delay = _calculate_delay(attempt, effective_config)

                    retry_after = _extract_retry_after(e)
                    if retry_after is not None:
                        delay = max(delay, min(retry_after, effective_config.max_delay))

                    logger.warning(
                        f"Retry {attempt + 1}/{effective_config.max_attempts} for "
                        f"{func.__name__} after {type(e).__name__}. Waiting {delay:.2f}s",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "delay_seconds": delay,
                        }
                    )

                    if effective_config.on_retry:
                        try:
                            effective_config.on_retry(attempt + 1, e, delay)
                        except Exception:
                            pass

                    time.sleep(delay)

            total_time = time.monotonic() - start_time
            raise RetryError(
                f"All {effective_config.max_attempts} retry attempts exhausted "
                f"for {func.__name__} after {total_time:.2f}s",
                attempts=effective_config.max_attempts,
                last_exception=last_exception,
                total_time=total_time,
            ) from last_exception

        return wrapper
    return decorator


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> T:
    """
    Execute an async function with retry logic.

    Functional alternative to the decorator pattern.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        config: Retry configuration
        **kwargs: Keyword arguments for func

    Returns:
        Result of func

    Example:
        ```python
        result = await retry_async(
            client.request,
            "GET",
            "/api/data",
            config=RetryConfig(max_attempts=5)
        )
        ```
    """
    wrapped = with_retry(config)(func)
    return await wrapped(*args, **kwargs)


def retry_sync(
    func: Callable[..., T],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> T:
    """
    Execute a sync function with retry logic.

    Functional alternative to the decorator pattern.

    Args:
        func: Function to execute
        *args: Positional arguments for func
        config: Retry configuration
        **kwargs: Keyword arguments for func

    Returns:
        Result of func
    """
    wrapped = with_retry_sync(config)(func)
    return wrapped(*args, **kwargs)
