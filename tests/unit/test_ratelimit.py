"""
Tests for rate limiting module.
"""

import asyncio
import pytest
import time

from startd8.ratelimit import (
    RateLimitConfig,
    BackpressureStrategy,
    ProviderLimits,
    get_provider_limits,
    get_default_config,
    list_providers,
    RateLimiter,
    RateLimiterStats,
    TokenBucket,
    RateLimitExceededError,
    get_rate_limiter,
    get_rate_limiter_sync,
    clear_rate_limiters,
    list_rate_limiters,
)


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass"""

    def test_default_config(self):
        config = RateLimitConfig()
        assert config.requests_per_minute == 50
        assert config.tokens_per_minute == 100_000
        assert config.burst_multiplier == 1.5
        assert config.backpressure_strategy == BackpressureStrategy.QUEUE
        assert config.max_queue_size == 100
        assert config.max_wait_seconds == 60.0
        assert config.enabled is True

    def test_custom_config(self):
        config = RateLimitConfig(
            requests_per_minute=100,
            tokens_per_minute=200_000,
            burst_multiplier=2.0,
            backpressure_strategy=BackpressureStrategy.REJECT,
            max_queue_size=50,
            max_wait_seconds=30.0,
            enabled=False,
        )
        assert config.requests_per_minute == 100
        assert config.tokens_per_minute == 200_000
        assert config.burst_multiplier == 2.0
        assert config.backpressure_strategy == BackpressureStrategy.REJECT
        assert config.max_queue_size == 50
        assert config.max_wait_seconds == 30.0
        assert config.enabled is False

    def test_invalid_requests_per_minute(self):
        with pytest.raises(ValueError, match="requests_per_minute must be at least 1"):
            RateLimitConfig(requests_per_minute=0)

    def test_invalid_tokens_per_minute(self):
        with pytest.raises(ValueError, match="tokens_per_minute must be at least 1"):
            RateLimitConfig(tokens_per_minute=0)

    def test_invalid_burst_multiplier(self):
        with pytest.raises(ValueError, match="burst_multiplier must be at least 1.0"):
            RateLimitConfig(burst_multiplier=0.5)

    def test_invalid_max_queue_size(self):
        with pytest.raises(ValueError, match="max_queue_size must be non-negative"):
            RateLimitConfig(max_queue_size=-1)

    def test_invalid_max_wait_seconds(self):
        with pytest.raises(ValueError, match="max_wait_seconds must be non-negative"):
            RateLimitConfig(max_wait_seconds=-1.0)

    def test_computed_properties(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            tokens_per_minute=60_000,
            burst_multiplier=2.0,
        )
        assert config.requests_per_second == 1.0
        assert config.tokens_per_second == 1000.0
        assert config.burst_requests == 2  # 60 * 2.0 / 60
        assert config.burst_tokens == 2000  # 60000 * 2.0 / 60


class TestBackpressureStrategy:
    """Tests for BackpressureStrategy enum"""

    def test_strategy_values(self):
        assert BackpressureStrategy.QUEUE.value == "queue"
        assert BackpressureStrategy.REJECT.value == "reject"
        assert BackpressureStrategy.ADAPTIVE.value == "adaptive"

    def test_strategy_string_enum(self):
        # BackpressureStrategy is a str enum
        assert isinstance(BackpressureStrategy.QUEUE, str)
        assert BackpressureStrategy.QUEUE == "queue"


class TestProviderLimits:
    """Tests for ProviderLimits and provider defaults"""

    def test_get_anthropic_limits(self):
        limits = get_provider_limits("anthropic")
        assert limits is not None
        assert limits.provider == "anthropic"
        assert limits.requests_per_minute == 50
        assert limits.tokens_per_minute == 40_000

    def test_get_openai_limits(self):
        limits = get_provider_limits("openai")
        assert limits is not None
        assert limits.provider == "openai"
        assert limits.requests_per_minute == 500
        assert limits.tokens_per_minute == 200_000

    def test_get_gemini_limits(self):
        limits = get_provider_limits("gemini")
        assert limits is not None
        assert limits.provider == "gemini"
        assert limits.requests_per_minute == 60
        assert limits.tokens_per_minute == 60_000

    def test_get_ollama_limits(self):
        limits = get_provider_limits("ollama")
        assert limits is not None
        assert limits.provider == "ollama"
        assert limits.requests_per_minute == 1000

    def test_get_mock_limits(self):
        limits = get_provider_limits("mock")
        assert limits is not None
        assert limits.provider == "mock"
        assert limits.requests_per_minute == 10_000

    def test_get_unknown_provider_limits(self):
        limits = get_provider_limits("unknown_provider")
        assert limits is None

    def test_case_insensitive_lookup(self):
        limits = get_provider_limits("ANTHROPIC")
        assert limits is not None
        assert limits.provider == "anthropic"

    def test_list_providers(self):
        providers = list_providers()
        assert "anthropic" in providers
        assert "openai" in providers
        assert "gemini" in providers
        assert "ollama" in providers
        assert "mock" in providers


class TestGetDefaultConfig:
    """Tests for get_default_config function"""

    def test_default_config_without_provider(self):
        config = get_default_config()
        assert config.requests_per_minute == 50
        assert config.tokens_per_minute == 100_000

    def test_default_config_with_anthropic(self):
        config = get_default_config("anthropic")
        assert config.requests_per_minute == 50
        assert config.tokens_per_minute == 40_000

    def test_default_config_with_openai(self):
        config = get_default_config("openai")
        assert config.requests_per_minute == 500
        assert config.tokens_per_minute == 200_000

    def test_default_config_with_unknown_provider(self):
        config = get_default_config("unknown")
        # Falls back to generic defaults
        assert config.requests_per_minute == 50
        assert config.tokens_per_minute == 100_000


class TestTokenBucket:
    """Tests for TokenBucket class"""

    def test_initial_state(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        assert bucket.capacity == 10.0
        assert bucket.refill_rate == 1.0
        assert bucket.available() == 10.0

    def test_try_acquire_success(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        assert bucket.try_acquire(5.0) is True
        # Use approximate comparison due to time-based refill between calls
        assert 4.9 <= bucket.available() <= 5.1

    def test_try_acquire_insufficient(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        bucket.try_acquire(8.0)
        assert bucket.try_acquire(5.0) is False
        # Use approximate comparison due to time-based refill
        assert 1.9 <= bucket.available() <= 2.1

    def test_try_acquire_exact_amount(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        assert bucket.try_acquire(10.0) is True
        # Use approximate comparison due to time-based refill
        assert bucket.available() < 0.1

    def test_refill_over_time(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=100.0)  # Fast refill
        bucket.try_acquire(10.0)
        # Use approximate comparison due to time-based refill
        assert bucket.available() < 0.1

        # Wait for refill
        time.sleep(0.05)  # 50ms = 5 tokens at 100/s
        available = bucket.available()
        assert available >= 4.0  # Allow some timing tolerance
        assert available <= 6.0

    def test_refill_caps_at_capacity(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=100.0)
        bucket.try_acquire(5.0)

        # Wait long enough to refill beyond capacity
        time.sleep(0.2)
        assert bucket.available() == 10.0  # Capped at capacity

    def test_time_until_available(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=10.0)  # 10 tokens/sec
        bucket.try_acquire(10.0)

        # Need 5 tokens, at 10/sec = 0.5 seconds
        wait_time = bucket.time_until_available(5.0)
        assert 0.4 <= wait_time <= 0.6

    def test_time_until_available_already_available(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        wait_time = bucket.time_until_available(5.0)
        assert wait_time == 0.0

    def test_reset(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        bucket.try_acquire(10.0)
        # Use approximate comparison due to time-based refill
        assert bucket.available() < 0.1

        bucket.reset()
        assert bucket.available() == 10.0


class TestRateLimiter:
    """Tests for RateLimiter class"""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clear rate limiters after each test"""
        yield
        clear_rate_limiters()

    def test_init_with_default_config(self):
        limiter = RateLimiter()
        assert limiter.name == "default"
        assert limiter.config.requests_per_minute == 50

    def test_init_with_custom_config(self):
        config = RateLimitConfig(requests_per_minute=100)
        limiter = RateLimiter(config=config, name="custom")
        assert limiter.name == "custom"
        assert limiter.config.requests_per_minute == 100

    def test_stats_initial_state(self):
        limiter = RateLimiter()
        stats = limiter.stats
        assert stats.requests_made == 0
        assert stats.requests_queued == 0
        assert stats.requests_rejected == 0
        assert stats.tokens_consumed == 0

    @pytest.mark.asyncio
    async def test_acquire_success(self):
        config = RateLimitConfig(requests_per_minute=600)  # 10/sec
        limiter = RateLimiter(config=config, name="test")

        async with limiter.acquire(estimated_tokens=100):
            pass

        assert limiter.stats.requests_made == 1
        assert limiter.stats.tokens_consumed == 100

    @pytest.mark.asyncio
    async def test_acquire_multiple(self):
        config = RateLimitConfig(requests_per_minute=6000, tokens_per_minute=600_000)
        limiter = RateLimiter(config=config, name="test")

        for i in range(5):
            async with limiter.acquire(estimated_tokens=100):
                pass

        assert limiter.stats.requests_made == 5
        assert limiter.stats.tokens_consumed == 500

    @pytest.mark.asyncio
    async def test_acquire_disabled(self):
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(config=config, name="test")

        async with limiter.acquire(estimated_tokens=100):
            pass

        # No tracking when disabled
        assert limiter.stats.requests_made == 0

    @pytest.mark.asyncio
    async def test_acquire_with_queue_strategy(self):
        # Very slow refill to force queueing
        config = RateLimitConfig(
            requests_per_minute=60,  # 1/sec
            tokens_per_minute=6000,  # 100/sec
            burst_multiplier=1.0,  # No burst
            backpressure_strategy=BackpressureStrategy.QUEUE,
            max_wait_seconds=5.0,
        )
        limiter = RateLimiter(config=config, name="test")

        # Exhaust initial capacity
        async with limiter.acquire(estimated_tokens=1):
            pass

        # Next request should queue
        start = time.monotonic()
        async with limiter.acquire(estimated_tokens=1):
            pass
        elapsed = time.monotonic() - start

        # Should have waited for capacity
        assert elapsed >= 0.5  # At least half the refill time
        assert limiter.stats.requests_queued >= 1

    @pytest.mark.asyncio
    async def test_acquire_with_reject_strategy(self):
        config = RateLimitConfig(
            requests_per_minute=60,  # 1/sec
            burst_multiplier=1.0,  # No burst
            backpressure_strategy=BackpressureStrategy.REJECT,
        )
        limiter = RateLimiter(config=config, name="test")

        # Exhaust initial capacity
        async with limiter.acquire(estimated_tokens=1):
            pass

        # Next request should be rejected
        with pytest.raises(RateLimitExceededError) as exc_info:
            async with limiter.acquire(estimated_tokens=1):
                pass

        assert exc_info.value.limiter_name == "test"
        assert exc_info.value.wait_time > 0
        assert limiter.stats.requests_rejected == 1

    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        config = RateLimitConfig(
            requests_per_minute=60,  # 1/sec
            burst_multiplier=1.0,
            backpressure_strategy=BackpressureStrategy.QUEUE,
            max_wait_seconds=0.1,  # Very short timeout
        )
        limiter = RateLimiter(config=config, name="test")

        # Exhaust initial capacity
        async with limiter.acquire(estimated_tokens=1):
            pass

        # Next request should timeout
        with pytest.raises(asyncio.TimeoutError):
            async with limiter.acquire(estimated_tokens=1):
                pass

    def test_reset_stats(self):
        limiter = RateLimiter(name="test")
        limiter._stats.requests_made = 10
        limiter._stats.tokens_consumed = 1000

        limiter.reset_stats()

        assert limiter.stats.requests_made == 0
        assert limiter.stats.tokens_consumed == 0

    def test_reset_buckets(self):
        config = RateLimitConfig(requests_per_minute=60)
        limiter = RateLimiter(config=config, name="test")

        # Consume some capacity
        limiter.request_bucket.try_acquire(5)
        limiter.token_bucket.try_acquire(500)

        limiter.reset_buckets()

        assert limiter.request_bucket.available() == limiter.config.burst_requests
        assert limiter.token_bucket.available() == limiter.config.burst_tokens


class TestRateLimiterDecorator:
    """Tests for RateLimiter.limit() decorator"""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        clear_rate_limiters()

    @pytest.mark.asyncio
    async def test_limit_decorator_success(self):
        config = RateLimitConfig(requests_per_minute=6000)
        limiter = RateLimiter(config=config, name="test")

        call_count = 0

        @limiter.limit(estimated_tokens=100)
        async def my_api_call():
            nonlocal call_count
            call_count += 1
            return "result"

        result = await my_api_call()

        assert result == "result"
        assert call_count == 1
        assert limiter.stats.requests_made == 1
        assert limiter.stats.tokens_consumed == 100

    @pytest.mark.asyncio
    async def test_limit_decorator_multiple_calls(self):
        config = RateLimitConfig(requests_per_minute=6000, tokens_per_minute=600_000)
        limiter = RateLimiter(config=config, name="test")

        @limiter.limit(estimated_tokens=50)
        async def my_api_call(value: int):
            return value * 2

        results = []
        for i in range(5):
            result = await my_api_call(i)
            results.append(result)

        assert results == [0, 2, 4, 6, 8]
        assert limiter.stats.requests_made == 5
        assert limiter.stats.tokens_consumed == 250

    @pytest.mark.asyncio
    async def test_limit_decorator_preserves_function_metadata(self):
        config = RateLimitConfig()
        limiter = RateLimiter(config=config, name="test")

        @limiter.limit(estimated_tokens=100)
        async def documented_function():
            """This is the docstring."""
            return "result"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is the docstring."


class TestGlobalRegistry:
    """Tests for global rate limiter registry"""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clear rate limiters before and after each test"""
        clear_rate_limiters()
        yield
        clear_rate_limiters()

    def test_get_rate_limiter_creates_new(self):
        limiter = get_rate_limiter("test-limiter")
        assert limiter.name == "test-limiter"

    def test_get_rate_limiter_returns_existing(self):
        limiter1 = get_rate_limiter("test-limiter")
        limiter2 = get_rate_limiter("test-limiter")
        assert limiter1 is limiter2

    def test_get_rate_limiter_with_config(self):
        config = RateLimitConfig(requests_per_minute=100)
        limiter = get_rate_limiter("custom", config=config)
        assert limiter.config.requests_per_minute == 100

    def test_get_rate_limiter_ignores_config_for_existing(self):
        config1 = RateLimitConfig(requests_per_minute=100)
        config2 = RateLimitConfig(requests_per_minute=200)

        limiter1 = get_rate_limiter("test", config=config1)
        limiter2 = get_rate_limiter("test", config=config2)

        # Second config is ignored
        assert limiter2.config.requests_per_minute == 100
        assert limiter1 is limiter2

    def test_get_rate_limiter_with_provider(self):
        limiter = get_rate_limiter("anthropic-limiter", provider="anthropic")
        assert limiter.config.requests_per_minute == 50
        assert limiter.config.tokens_per_minute == 40_000

    def test_get_rate_limiter_sync(self):
        limiter = get_rate_limiter_sync("sync-test")
        assert limiter.name == "sync-test"

        # Same as async version
        limiter2 = get_rate_limiter("sync-test")
        assert limiter is limiter2

    def test_clear_rate_limiters(self):
        get_rate_limiter("limiter1")
        get_rate_limiter("limiter2")

        assert len(list_rate_limiters()) == 2

        clear_rate_limiters()

        assert len(list_rate_limiters()) == 0

    def test_list_rate_limiters(self):
        get_rate_limiter("limiter-a")
        get_rate_limiter("limiter-b")
        get_rate_limiter("limiter-c")

        limiters = list_rate_limiters()
        assert "limiter-a" in limiters
        assert "limiter-b" in limiters
        assert "limiter-c" in limiters


class TestRateLimitExceededError:
    """Tests for RateLimitExceededError exception"""

    def test_error_attributes(self):
        error = RateLimitExceededError(
            "Rate limit exceeded",
            limiter_name="test-limiter",
            wait_time=5.5,
            bucket_type="requests",
        )

        assert error.limiter_name == "test-limiter"
        assert error.wait_time == 5.5
        assert error.bucket_type == "requests"
        assert "Rate limit exceeded" in str(error)

    def test_error_default_values(self):
        error = RateLimitExceededError("Rate limit exceeded")
        assert error.limiter_name == ""
        assert error.wait_time == 0.0
        assert error.bucket_type == "requests"


class TestRateLimiterStats:
    """Tests for RateLimiterStats dataclass"""

    def test_default_stats(self):
        stats = RateLimiterStats()
        assert stats.requests_made == 0
        assert stats.requests_queued == 0
        assert stats.requests_rejected == 0
        assert stats.tokens_consumed == 0
        assert stats.total_wait_time == 0.0
        assert stats.last_request_time == 0.0

    def test_stats_modification(self):
        stats = RateLimiterStats()
        stats.requests_made = 10
        stats.tokens_consumed = 5000

        assert stats.requests_made == 10
        assert stats.tokens_consumed == 5000
