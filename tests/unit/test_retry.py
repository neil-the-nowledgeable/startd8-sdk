"""
Tests for retry utilities.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from startd8.utils.retry import (
    RetryConfig,
    RetryError,
    with_retry,
    with_retry_sync,
    retry_async,
    retry_sync,
    _calculate_delay,
    _is_retryable_exception,
    _extract_status_code,
    _extract_retry_after,
)


class TestRetryConfig:
    """Tests for RetryConfig dataclass"""

    def test_default_config(self):
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert ConnectionError in config.retryable_exceptions
        assert 429 in config.retryable_status_codes

    def test_custom_config(self):
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            retryable_status_codes=(429, 503),
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.retryable_status_codes == (429, 503)

    def test_invalid_max_attempts(self):
        with pytest.raises(ValueError, match="max_attempts must be at least 1"):
            RetryConfig(max_attempts=0)

    def test_invalid_base_delay(self):
        with pytest.raises(ValueError, match="base_delay must be non-negative"):
            RetryConfig(base_delay=-1.0)

    def test_invalid_max_delay(self):
        with pytest.raises(ValueError, match="max_delay must be >= base_delay"):
            RetryConfig(base_delay=10.0, max_delay=5.0)


class TestCalculateDelay:
    """Tests for delay calculation"""

    def test_exponential_backoff(self):
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)

        assert _calculate_delay(0, config) == 1.0  # 1 * 2^0 = 1
        assert _calculate_delay(1, config) == 2.0  # 1 * 2^1 = 2
        assert _calculate_delay(2, config) == 4.0  # 1 * 2^2 = 4
        assert _calculate_delay(3, config) == 8.0  # 1 * 2^3 = 8

    def test_max_delay_cap(self):
        config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=False)

        assert _calculate_delay(0, config) == 1.0
        assert _calculate_delay(1, config) == 2.0
        assert _calculate_delay(2, config) == 4.0
        assert _calculate_delay(3, config) == 5.0  # Capped at max_delay
        assert _calculate_delay(10, config) == 5.0  # Still capped

    def test_jitter_adds_variation(self):
        config = RetryConfig(base_delay=10.0, jitter=True, jitter_factor=0.1)

        delays = [_calculate_delay(0, config) for _ in range(100)]

        # Should have some variation
        assert len(set(delays)) > 1

        # All delays should be within jitter range (10 +/- 1)
        for delay in delays:
            assert 9.0 <= delay <= 11.0


class TestIsRetryableException:
    """Tests for exception classification"""

    def test_connection_error_is_retryable(self):
        config = RetryConfig()
        assert _is_retryable_exception(ConnectionError("failed"), config)

    def test_timeout_error_is_retryable(self):
        config = RetryConfig()
        assert _is_retryable_exception(TimeoutError("timeout"), config)

    def test_os_error_is_retryable(self):
        config = RetryConfig()
        assert _is_retryable_exception(OSError("network"), config)

    def test_value_error_not_retryable(self):
        config = RetryConfig()
        assert not _is_retryable_exception(ValueError("invalid"), config)

    def test_custom_retryable_exceptions(self):
        class CustomError(Exception):
            pass

        config = RetryConfig(retryable_exceptions=(CustomError,))
        assert _is_retryable_exception(CustomError("custom"), config)
        assert not _is_retryable_exception(ConnectionError("conn"), config)

    def test_exception_with_status_code(self):
        config = RetryConfig(retryable_status_codes=(429,))

        class APIError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code

        assert _is_retryable_exception(APIError(429), config)
        assert not _is_retryable_exception(APIError(400), config)


class TestExtractStatusCode:
    """Tests for status code extraction"""

    def test_direct_status_code_attribute(self):
        class Error(Exception):
            status_code = 429

        assert _extract_status_code(Error()) == 429

    def test_response_status_code(self):
        class Response:
            status_code = 503

        class Error(Exception):
            response = Response()

        assert _extract_status_code(Error()) == 503

    def test_no_status_code(self):
        assert _extract_status_code(ValueError("invalid")) is None


class TestExtractRetryAfter:
    """Tests for Retry-After extraction"""

    def test_direct_retry_after_attribute(self):
        class Error(Exception):
            retry_after = 30

        assert _extract_retry_after(Error()) == 30.0

    def test_response_headers(self):
        class Response:
            headers = {"Retry-After": "60"}

        class Error(Exception):
            response = Response()

        assert _extract_retry_after(Error()) == 60.0

    def test_no_retry_after(self):
        assert _extract_retry_after(ValueError("invalid")) is None


class TestWithRetryAsync:
    """Tests for async retry decorator"""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        call_count = 0

        @with_retry()
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        call_count = 0

        @with_retry(RetryConfig(base_delay=0.01))
        async def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary failure")
            return "success"

        result = await eventually_succeeds()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_all_attempts(self):
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01))
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("permanent failure")

        with pytest.raises(RetryError) as exc_info:
            await always_fails()

        assert call_count == 3
        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ConnectionError)

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        call_count = 0

        @with_retry(RetryConfig(base_delay=0.01))
        async def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await raises_value_error()

        assert call_count == 1  # No retry for ValueError

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        retry_calls = []

        def on_retry(attempt, exception, delay):
            retry_calls.append((attempt, type(exception).__name__, delay))

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01, on_retry=on_retry))
        async def fails_twice():
            if len(retry_calls) < 2:
                raise ConnectionError("temporary")
            return "success"

        await fails_twice()
        assert len(retry_calls) == 2
        assert retry_calls[0][0] == 1
        assert retry_calls[1][0] == 2

    @pytest.mark.asyncio
    async def test_respects_retry_after_header(self):
        call_count = 0
        start_time = None

        class RateLimitError(Exception):
            retry_after = 0.1  # 100ms

        @with_retry(RetryConfig(
            max_attempts=2,
            base_delay=0.01,
            retryable_exceptions=(RateLimitError,)
        ))
        async def rate_limited():
            nonlocal call_count, start_time
            call_count += 1
            if call_count == 1:
                start_time = time.monotonic()
                raise RateLimitError("rate limited")
            return "success"

        await rate_limited()
        elapsed = time.monotonic() - start_time

        # Should have waited at least 0.1s due to retry_after
        assert elapsed >= 0.1


class TestWithRetrySyncDecorator:
    """Tests for sync retry decorator"""

    def test_success_on_first_attempt(self):
        call_count = 0

        @with_retry_sync()
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_success_after_retry(self):
        call_count = 0

        @with_retry_sync(RetryConfig(base_delay=0.01))
        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temporary")
            return "success"

        result = eventually_succeeds()
        assert result == "success"
        assert call_count == 2

    def test_exhausts_all_attempts(self):
        call_count = 0

        @with_retry_sync(RetryConfig(max_attempts=2, base_delay=0.01))
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timeout")

        with pytest.raises(RetryError) as exc_info:
            always_fails()

        assert call_count == 2
        assert exc_info.value.attempts == 2


class TestFunctionalAPI:
    """Tests for functional retry API"""

    @pytest.mark.asyncio
    async def test_retry_async(self):
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temporary")
            return "success"

        result = await retry_async(
            flaky_func,
            config=RetryConfig(base_delay=0.01)
        )
        assert result == "success"
        assert call_count == 2

    def test_retry_sync(self):
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temporary")
            return "success"

        result = retry_sync(
            flaky_func,
            config=RetryConfig(base_delay=0.01)
        )
        assert result == "success"
        assert call_count == 2


class TestRetryError:
    """Tests for RetryError exception"""

    def test_retry_error_attributes(self):
        original = ConnectionError("original error")
        error = RetryError(
            "All attempts failed",
            attempts=3,
            last_exception=original,
            total_time=5.5,
        )

        assert error.attempts == 3
        assert error.last_exception is original
        assert error.total_time == 5.5
        assert "All attempts failed" in str(error)

    def test_retry_error_chaining(self):
        """Verify exception chaining works correctly"""
        original = ConnectionError("original")

        try:
            raise RetryError(
                "failed",
                attempts=1,
                last_exception=original,
                total_time=1.0,
            ) from original
        except RetryError as e:
            assert e.__cause__ is original
