"""
Unit tests for MCP Gateway module.

Run with: pytest tests/test_mcp_gateway.py -v

Tests cover:
- Gateway initialization and configuration
- Input validation
- Cache behavior
- Rate limiting
- Circuit breaker integration
- Audit logging
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from dataclasses import asdict

# Import the classes to test
pytest_plugins = ("pytest_asyncio",)

from startd8.mcp import (
    MCPGateway,
    MCPGatewayConfig,
    SkillExecutionResult,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    TokenBucketRateLimiter,
    RateLimiterConfig,
    ResponseCache,
    CacheConfig,
    AuthConfig,
    RequestSigningConfig,
    ObservabilityConfig,
    SkillRegistry,
    SkillMetadata,
    GatewayError,
    GatewayCircuitOpenError,
    GatewayRateLimitExceededError,
)
from startd8.models import TokenUsage


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def default_config():
    """Create default gateway configuration."""
    return MCPGatewayConfig()


@pytest.fixture
def custom_config():
    """Create custom gateway configuration for testing."""
    return MCPGatewayConfig(
        max_connections=5,
        connection_timeout_seconds=10.0,
        model="claude-sonnet-4-20250514",
        default_max_tokens=4096,
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout_seconds=15.0,
            half_open_max_requests=2
        ),
        rate_limiter=RateLimiterConfig(
            requests_per_second=5.0,
            burst_size=10,
            per_skill_limits={"skill-test": 2.0}
        ),
        cache=CacheConfig(
            enabled=True,
            ttl_seconds=60,
            max_entries=100
        ),
        audit_enabled=True,
        audit_log_responses=False
    )


@pytest.fixture
def mock_skill_result():
    """Create a mock skill execution result."""
    return SkillExecutionResult(
        content="Test response content",
        metrics={"skill_time_ms": 100},
        skill_id="skill-test",
        execution_time_ms=150,
        token_usage=TokenUsage(input=100, output=200, total=300),
        cache_hit=False
    )


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response."""
    mock_response = Mock()
    mock_response.content = [Mock(text="Test response\n---\nGenerated content")]
    mock_response.usage = Mock()
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 200
    return mock_response


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

class TestMCPGatewayConfig:
    """Tests for MCPGatewayConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = MCPGatewayConfig()
        
        assert config.max_connections == 10
        assert config.connection_timeout_seconds == 30.0
        assert config.model == "claude-sonnet-4-20250514"
        assert config.default_max_tokens == 8192
        assert config.audit_enabled is True
        assert config.audit_log_responses is False
    
    def test_custom_values(self, custom_config):
        """Test custom configuration values."""
        assert custom_config.max_connections == 5
        assert custom_config.connection_timeout_seconds == 10.0
        assert custom_config.default_max_tokens == 4096
        assert custom_config.circuit_breaker.failure_threshold == 3
        assert custom_config.rate_limiter.requests_per_second == 5.0
        assert custom_config.cache.ttl_seconds == 60
    
    def test_invalid_max_connections(self):
        """Test that invalid max_connections raises ValueError."""
        with pytest.raises(ValueError, match="max_connections must be >= 1"):
            MCPGatewayConfig(max_connections=0)
    
    def test_invalid_timeout(self):
        """Test that invalid timeout raises ValueError."""
        with pytest.raises(ValueError, match="connection_timeout_seconds must be > 0"):
            MCPGatewayConfig(connection_timeout_seconds=0)
    
    def test_invalid_max_tokens(self):
        """Test that invalid max_tokens raises ValueError."""
        with pytest.raises(ValueError, match="default_max_tokens must be >= 1"):
            MCPGatewayConfig(default_max_tokens=0)


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        
        assert config.failure_threshold == 5
        assert config.recovery_timeout_seconds == 30.0
        assert config.half_open_max_requests == 3
    
    def test_invalid_failure_threshold(self):
        """Test that invalid failure_threshold raises ValueError."""
        with pytest.raises(ValueError, match="failure_threshold must be >= 1"):
            CircuitBreakerConfig(failure_threshold=0)
    
    def test_invalid_recovery_timeout(self):
        """Test that invalid recovery_timeout raises ValueError."""
        with pytest.raises(ValueError, match="recovery_timeout_seconds must be > 0"):
            CircuitBreakerConfig(recovery_timeout_seconds=0)
    
    def test_invalid_half_open_requests(self):
        """Test that invalid half_open_max_requests raises ValueError."""
        with pytest.raises(ValueError, match="half_open_max_requests must be >= 1"):
            CircuitBreakerConfig(half_open_max_requests=0)


class TestRateLimiterConfig:
    """Tests for RateLimiterConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = RateLimiterConfig()
        
        assert config.requests_per_second == 10.0
        assert config.burst_size == 20
        assert config.per_skill_limits == {}
    
    def test_invalid_requests_per_second(self):
        """Test that invalid requests_per_second raises ValueError."""
        with pytest.raises(ValueError, match="requests_per_second must be > 0"):
            RateLimiterConfig(requests_per_second=0)
    
    def test_invalid_burst_size(self):
        """Test that invalid burst_size raises ValueError."""
        with pytest.raises(ValueError, match="burst_size must be >= 1"):
            RateLimiterConfig(burst_size=0)
    
    def test_invalid_per_skill_limit(self):
        """Test that invalid per_skill_limits raises ValueError."""
        with pytest.raises(ValueError, match="per_skill_limits"):
            RateLimiterConfig(per_skill_limits={"skill-test": 0})


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = CacheConfig()
        
        assert config.enabled is True
        assert config.ttl_seconds == 300
        assert config.max_entries == 1000
        assert config.max_entry_size_bytes == 1_000_000
    
    def test_invalid_ttl(self):
        """Test that invalid ttl raises ValueError."""
        with pytest.raises(ValueError, match="ttl_seconds must be >= 0"):
            CacheConfig(ttl_seconds=-1)
    
    def test_invalid_max_entries(self):
        """Test that invalid max_entries raises ValueError."""
        with pytest.raises(ValueError, match="max_entries must be >= 1"):
            CacheConfig(max_entries=0)


class TestAuthConfig:
    """Tests for AuthConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = AuthConfig()
        
        assert config.require_api_key is False
        assert config.api_key_header == "X-API-Key"
        assert config.enable_jwt is False
        assert config.enable_mtls is False
    
    def test_invalid_clock_skew(self):
        """Test that invalid clock_skew raises ValueError."""
        with pytest.raises(ValueError, match="jwt_clock_skew_seconds must be >= 0"):
            AuthConfig(jwt_clock_skew_seconds=-1)


class TestObservabilityConfig:
    """Tests for ObservabilityConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ObservabilityConfig()
        
        assert config.enable_metrics is True
        assert config.metrics_port == 9090
        assert config.enable_traces is True
        assert config.otlp_protocol == "grpc"
    
    def test_invalid_metrics_port(self):
        """Test that invalid metrics_port raises ValueError."""
        with pytest.raises(ValueError, match="metrics_port must be between"):
            ObservabilityConfig(metrics_port=0)
    
    def test_invalid_otlp_protocol(self):
        """Test that invalid otlp_protocol raises ValueError."""
        with pytest.raises(ValueError, match="otlp_protocol must be"):
            ObservabilityConfig(otlp_protocol="invalid")


# =============================================================================
# GATEWAY INITIALIZATION TESTS
# =============================================================================

class TestMCPGatewayInit:
    """Tests for MCPGateway initialization."""
    
    def test_gateway_creation_with_defaults(self):
        """Test gateway creates with default config."""
        gateway = MCPGateway()
        
        assert gateway.config is not None
        assert gateway._initialized is False
        assert gateway.cache is not None
        assert gateway.registry is not None
        assert gateway.audit is not None
    
    def test_gateway_creation_with_custom_config(self, custom_config):
        """Test gateway creates with custom config."""
        gateway = MCPGateway(custom_config)
        
        assert gateway.config.max_connections == 5
        assert gateway.config.circuit_breaker.failure_threshold == 3
    
    @pytest.mark.asyncio
    async def test_initialize_missing_api_key_raises(self):
        """Test that initialization without API key raises RuntimeError."""
        gateway = MCPGateway()
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                await gateway.initialize()
    
    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful gateway initialization."""
        gateway = MCPGateway()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.mcp.gateway.AsyncAnthropic'):
                await gateway.initialize()
                assert gateway._initialized is True
                assert gateway._client is not None
    
    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        """Test that multiple initialize calls are idempotent."""
        gateway = MCPGateway()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.mcp.gateway.AsyncAnthropic'):
                await gateway.initialize()
                await gateway.initialize()  # Should not raise
                assert gateway._initialized is True
    
    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test gateway shutdown."""
        gateway = MCPGateway()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.mcp.gateway.AsyncAnthropic'):
                await gateway.initialize()
                await gateway.shutdown()
                assert gateway._initialized is False
                assert gateway._client is None
    
    @pytest.mark.asyncio
    async def test_session_context_manager(self):
        """Test session context manager."""
        gateway = MCPGateway()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.mcp.gateway.AsyncAnthropic'):
                async with gateway.session():
                    assert gateway._initialized is True
                assert gateway._initialized is False


class TestMCPGatewayAuthValidation:
    """Tests for gateway authentication validation."""
    
    @pytest.mark.asyncio
    async def test_api_key_required_but_missing(self):
        """Test that missing gateway API key raises when required."""
        config = MCPGatewayConfig(
            auth=AuthConfig(require_api_key=True)
        )
        gateway = MCPGateway(config)
        
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}, clear=True):
            with pytest.raises(RuntimeError, match="MCP_GATEWAY_API_KEY"):
                await gateway.initialize()
    
    @pytest.mark.asyncio
    async def test_api_key_required_and_present(self):
        """Test that gateway initializes when API key is present."""
        config = MCPGatewayConfig(
            auth=AuthConfig(require_api_key=True)
        )
        gateway = MCPGateway(config)
        
        with patch.dict('os.environ', {
            'ANTHROPIC_API_KEY': 'test-key',
            'MCP_GATEWAY_API_KEY': 'gateway-key'
        }):
            with patch('startd8.mcp.gateway.AsyncAnthropic'):
                await gateway.initialize()
                assert gateway._initialized is True
    
    @pytest.mark.asyncio
    async def test_jwt_enabled_but_secret_missing(self):
        """Test that missing JWT secret raises when JWT enabled."""
        config = MCPGatewayConfig(
            auth=AuthConfig(enable_jwt=True)
        )
        gateway = MCPGateway(config)
        
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}, clear=True):
            with pytest.raises(RuntimeError, match="MCP_JWT_SECRET"):
                await gateway.initialize()
    
    @pytest.mark.asyncio
    async def test_mtls_enabled_but_ca_missing(self):
        """Test that missing CA bundle raises when mTLS enabled."""
        config = MCPGatewayConfig(
            auth=AuthConfig(enable_mtls=True, mtls_ca_bundle=None)
        )
        gateway = MCPGateway(config)
        
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}, clear=True):
            with pytest.raises(RuntimeError, match="mtls_ca_bundle"):
                await gateway.initialize()


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================

class TestMCPGatewayInputValidation:
    """Tests for gateway input validation."""
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_empty_skill_id_raises(self, mock_anthropic):
        """Test that empty skill_id raises ValueError."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        with pytest.raises(ValueError, match="skill_id must be a non-empty string"):
            await gateway.execute_skill(skill_id="", prompt="test")
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_none_skill_id_raises(self, mock_anthropic):
        """Test that None skill_id raises ValueError."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        with pytest.raises(ValueError, match="skill_id must be a non-empty string"):
            await gateway.execute_skill(skill_id=None, prompt="test")
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_skill_id_too_long_raises(self, mock_anthropic):
        """Test that skill_id > 256 chars raises ValueError."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        long_skill_id = "a" * 257
        with pytest.raises(ValueError, match="skill_id exceeds maximum length"):
            await gateway.execute_skill(skill_id=long_skill_id, prompt="test")
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_empty_prompt_raises(self, mock_anthropic):
        """Test that empty prompt raises ValueError."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        with pytest.raises(ValueError, match="prompt must be a non-empty string"):
            await gateway.execute_skill(skill_id="skill-test", prompt="")
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_prompt_too_large_raises(self, mock_anthropic):
        """Test that prompt > 1MB raises ValueError."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        large_prompt = "a" * (1_000_001)
        with pytest.raises(ValueError, match="prompt exceeds maximum length"):
            await gateway.execute_skill(skill_id="skill-test", prompt=large_prompt)
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_invalid_max_tokens_raises(self, mock_anthropic):
        """Test that invalid max_tokens raises ValueError."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        with pytest.raises(ValueError, match="max_tokens must be between"):
            await gateway.execute_skill(
                skill_id="skill-test",
                prompt="test",
                max_tokens=0
            )
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_invalid_timeout_raises(self, mock_anthropic):
        """Test that invalid timeout raises ValueError."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        with pytest.raises(ValueError, match="timeout_ms must be between"):
            await gateway.execute_skill(
                skill_id="skill-test",
                prompt="test",
                timeout_ms=0
            )


# =============================================================================
# CACHE TESTS
# =============================================================================

class TestResponseCache:
    """Tests for ResponseCache behavior."""
    
    @pytest.fixture
    def cache(self):
        """Create a test cache."""
        config = CacheConfig(enabled=True, ttl_seconds=60, max_entries=10)
        return ResponseCache(config)
    
    @pytest.fixture
    def disabled_cache(self):
        """Create a disabled cache."""
        config = CacheConfig(enabled=False)
        return ResponseCache(config)
    
    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, cache, mock_skill_result):
        """Test setting and getting cached values."""
        await cache.set("skill-test", "test prompt", mock_skill_result)
        
        result = await cache.get("skill-test", "test prompt")
        
        assert result is not None
        assert result.content == mock_skill_result.content
    
    @pytest.mark.asyncio
    async def test_cache_miss_different_prompt(self, cache, mock_skill_result):
        """Test that different prompts cause cache miss."""
        await cache.set("skill-test", "prompt 1", mock_skill_result)
        
        result = await cache.get("skill-test", "prompt 2")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_miss_different_skill(self, cache, mock_skill_result):
        """Test that different skills cause cache miss."""
        await cache.set("skill-test-1", "test prompt", mock_skill_result)
        
        result = await cache.get("skill-test-2", "test prompt")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, mock_skill_result):
        """Test that expired entries return None."""
        config = CacheConfig(enabled=True, ttl_seconds=0, max_entries=10)
        cache = ResponseCache(config)
        
        await cache.set("skill-test", "test prompt", mock_skill_result)
        
        # Wait for TTL to expire
        await asyncio.sleep(0.1)
        
        result = await cache.get("skill-test", "test prompt")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_disabled_returns_none(self, disabled_cache, mock_skill_result):
        """Test that disabled cache always returns None."""
        await disabled_cache.set("skill-test", "test prompt", mock_skill_result)
        
        result = await disabled_cache.get("skill-test", "test prompt")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self, mock_skill_result):
        """Test LRU eviction when cache is full."""
        config = CacheConfig(enabled=True, ttl_seconds=60, max_entries=3)
        cache = ResponseCache(config)
        
        # Fill cache
        await cache.set("skill-1", "prompt", mock_skill_result)
        await cache.set("skill-2", "prompt", mock_skill_result)
        await cache.set("skill-3", "prompt", mock_skill_result)
        
        # Access skill-1 to make it recently used
        await cache.get("skill-1", "prompt")
        
        # Add new entry, should evict skill-2 (least recently used)
        await cache.set("skill-4", "prompt", mock_skill_result)
        
        # skill-1 should still be there (recently accessed)
        assert await cache.get("skill-1", "prompt") is not None
        # skill-2 should be evicted
        assert await cache.get("skill-2", "prompt") is None
        # skill-4 should be there (just added)
        assert await cache.get("skill-4", "prompt") is not None
    
    @pytest.mark.asyncio
    async def test_cache_tenant_isolation(self, mock_skill_result):
        """Test tenant-isolated cache keys."""
        config = CacheConfig(enabled=True, ttl_seconds=60, isolate_by_tenant=True)
        cache = ResponseCache(config)
        
        await cache.set("skill-test", "prompt", mock_skill_result, tenant_id="tenant-1")
        
        # Same prompt, different tenant should miss
        result = await cache.get("skill-test", "prompt", tenant_id="tenant-2")
        assert result is None
        
        # Same tenant should hit
        result = await cache.get("skill-test", "prompt", tenant_id="tenant-1")
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_cache_invalidate_all(self, cache, mock_skill_result):
        """Test invalidating all cache entries."""
        await cache.set("skill-1", "prompt", mock_skill_result)
        await cache.set("skill-2", "prompt", mock_skill_result)
        
        count = await cache.invalidate()
        
        assert count == 2
        assert await cache.get("skill-1", "prompt") is None
        assert await cache.get("skill-2", "prompt") is None
    
    @pytest.mark.asyncio
    async def test_cache_invalidate_by_skill(self, cache, mock_skill_result):
        """Test invalidating entries for specific skill."""
        await cache.set("skill-1", "prompt", mock_skill_result)
        await cache.set("skill-2", "prompt", mock_skill_result)
        
        count = await cache.invalidate("skill-1")
        
        assert count == 1
        assert await cache.get("skill-1", "prompt") is None
        assert await cache.get("skill-2", "prompt") is not None
    
    def test_cache_stats(self, cache):
        """Test cache statistics."""
        stats = cache.get_stats()
        
        assert 'size' in stats
        assert 'max_entries' in stats
        assert 'enabled' in stats


# =============================================================================
# RATE LIMITER TESTS
# =============================================================================

class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""
    
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        """Test acquiring tokens within limit succeeds."""
        limiter = TokenBucketRateLimiter(rate=10.0, burst_size=20)
        
        # Should succeed without waiting
        await limiter.acquire(1)
        
        assert limiter.get_available_tokens() < 20
    
    @pytest.mark.asyncio
    async def test_acquire_burst(self):
        """Test burst acquisition up to burst_size."""
        limiter = TokenBucketRateLimiter(rate=10.0, burst_size=5)
        
        # Should be able to acquire burst_size tokens immediately
        for _ in range(5):
            await limiter.acquire(1)
        
        assert limiter.get_available_tokens() < 1
    
    @pytest.mark.asyncio
    async def test_acquire_refill(self):
        """Test token refill over time."""
        limiter = TokenBucketRateLimiter(rate=100.0, burst_size=5)
        
        # Drain tokens
        for _ in range(5):
            await limiter.acquire(1)
        
        # Wait for refill
        await asyncio.sleep(0.1)
        
        # Should have refilled some tokens
        assert limiter.get_available_tokens() > 0
    
    @pytest.mark.asyncio
    async def test_acquire_excessive_wait_raises(self):
        """Test that excessive wait requirement raises RuntimeError."""
        limiter = TokenBucketRateLimiter(rate=0.01, burst_size=1)
        
        # Drain the bucket
        await limiter.acquire(1)
        
        # Next acquire would need to wait > 10s
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await limiter.acquire(1)


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Tests for CircuitBreaker."""
    
    @pytest.fixture
    def breaker(self):
        """Create a test circuit breaker."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout_seconds=0.1,
            half_open_max_requests=2
        )
        return CircuitBreaker("skill-test", config)
    
    def test_initial_state_closed(self, breaker):
        """Test circuit starts in closed state."""
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_check_closed_passes(self, breaker):
        """Test that check passes when circuit is closed."""
        await breaker.check()  # Should not raise
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, breaker):
        """Test circuit opens after failure_threshold failures."""
        for _ in range(3):
            await breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_blocks_when_open(self, breaker):
        """Test that open circuit blocks requests."""
        # Open the circuit
        for _ in range(3):
            await breaker.record_failure()
        
        with pytest.raises(RuntimeError, match="Circuit breaker OPEN"):
            await breaker.check()
    
    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self, breaker):
        """Test circuit transitions to half-open after timeout."""
        # Open the circuit
        for _ in range(3):
            await breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Check should transition to half-open
        await breaker.check()
        
        assert breaker.state == CircuitState.HALF_OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_closes_on_half_open_success(self, breaker):
        """Test circuit closes after successful half-open request."""
        # Open the circuit
        for _ in range(3):
            await breaker.record_failure()
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Transition to half-open
        await breaker.check()
        
        # Record success
        await breaker.record_success()
        
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_opens_on_half_open_failure(self, breaker):
        """Test circuit opens after half-open failure."""
        # Open the circuit
        for _ in range(3):
            await breaker.record_failure()
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Transition to half-open
        await breaker.check()
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Record failure
        await breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self, breaker):
        """Test that success resets failure count."""
        # Add some failures (but not enough to open)
        await breaker.record_failure()
        await breaker.record_failure()
        
        # Record success
        await breaker.record_success()
        
        # Should be able to fail 3 more times before opening
        for _ in range(2):
            await breaker.record_failure()
        
        assert breaker.state == CircuitState.CLOSED
    
    def test_manual_reset(self, breaker):
        """Test manual circuit reset."""
        # Open the circuit synchronously by manipulating state
        breaker._state = CircuitState.OPEN
        breaker._failure_count = 5
        
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0


# =============================================================================
# SKILL REGISTRY TESTS
# =============================================================================

class TestSkillRegistry:
    """Tests for SkillRegistry."""
    
    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        return SkillRegistry()
    
    @pytest.fixture
    def skill_metadata(self):
        """Create test skill metadata."""
        return SkillMetadata(
            skill_id="skill-test",
            name="Test Skill",
            description="A test skill",
            version="1.0.0",
            capabilities=["test"],
            tags=["test"]
        )
    
    @pytest.mark.asyncio
    async def test_register_skill(self, registry, skill_metadata):
        """Test registering a skill."""
        await registry.register(skill_metadata)
        
        result = await registry.get("skill-test")
        assert result is not None
        assert result.name == "Test Skill"
    
    @pytest.mark.asyncio
    async def test_get_unregistered_skill(self, registry):
        """Test getting unregistered skill returns None."""
        result = await registry.get("skill-nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_list_all_skills(self, registry, skill_metadata):
        """Test listing all registered skills."""
        await registry.register(skill_metadata)
        
        skills = await registry.list_all()
        
        assert len(skills) == 1
        assert skills[0].skill_id == "skill-test"
    
    @pytest.mark.asyncio
    async def test_is_registered(self, registry, skill_metadata):
        """Test checking if skill is registered."""
        assert await registry.is_registered("skill-test") is False
        
        await registry.register(skill_metadata)
        
        assert await registry.is_registered("skill-test") is True
    
    def test_registry_stats(self, registry):
        """Test registry statistics."""
        stats = registry.get_stats()
        
        assert 'total_skills' in stats
        assert stats['total_skills'] == 0


# =============================================================================
# GATEWAY EXECUTION TESTS
# =============================================================================

class TestMCPGatewayExecution:
    """Tests for gateway skill execution."""
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_successful_execution(self, mock_anthropic_class, mock_anthropic_response):
        """Test successful skill execution."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
        
        gateway = MCPGateway()
        await gateway.initialize()
        
        result = await gateway.execute_skill(
            skill_id="skill-test",
            prompt="Test prompt"
        )
        
        assert result is not None
        assert result.skill_id == "skill-test"
        assert result.token_usage.input == 100
        assert result.token_usage.output == 200
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_execution_with_cache_hit(self, mock_anthropic_class, mock_anthropic_response):
        """Test that cache hit returns cached result."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
        
        gateway = MCPGateway()
        await gateway.initialize()
        
        # First call - cache miss
        result1 = await gateway.execute_skill(
            skill_id="skill-test",
            prompt="Test prompt"
        )
        
        # Second call - should be cache hit
        result2 = await gateway.execute_skill(
            skill_id="skill-test",
            prompt="Test prompt"
        )
        
        assert result2.cache_hit is True
        # API should only be called once
        assert mock_client.messages.create.call_count == 1
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_execution_cache_disabled(self, mock_anthropic_class, mock_anthropic_response):
        """Test execution with cache disabled."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
        
        config = MCPGatewayConfig(cache=CacheConfig(enabled=False))
        gateway = MCPGateway(config)
        await gateway.initialize()
        
        # First call
        await gateway.execute_skill(skill_id="skill-test", prompt="Test prompt")
        
        # Second call - should also call API (no caching)
        await gateway.execute_skill(skill_id="skill-test", prompt="Test prompt")
        
        assert mock_client.messages.create.call_count == 2
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_execution_use_cache_false(self, mock_anthropic_class, mock_anthropic_response):
        """Test execution with use_cache=False bypasses cache."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
        
        gateway = MCPGateway()
        await gateway.initialize()
        
        # First call with caching
        await gateway.execute_skill(skill_id="skill-test", prompt="Test prompt")
        
        # Second call with use_cache=False
        result = await gateway.execute_skill(
            skill_id="skill-test",
            prompt="Test prompt",
            use_cache=False
        )
        
        assert result.cache_hit is False
        assert mock_client.messages.create.call_count == 2
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_execution_records_circuit_failure(self, mock_anthropic_class):
        """Test that execution failures are recorded by circuit breaker."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))
        
        config = MCPGatewayConfig(
            circuit_breaker=CircuitBreakerConfig(failure_threshold=2)
        )
        gateway = MCPGateway(config)
        await gateway.initialize()
        
        # First failure
        with pytest.raises(RuntimeError):
            await gateway.execute_skill(skill_id="skill-test", prompt="Test")
        
        # Second failure - should open circuit
        with pytest.raises(RuntimeError):
            await gateway.execute_skill(skill_id="skill-test", prompt="Test")
        
        # Circuit should now be open
        assert gateway.get_circuit_state("skill-test") == "open"


# =============================================================================
# GATEWAY INFO TESTS
# =============================================================================

class TestMCPGatewayInfo:
    """Tests for gateway info and statistics."""
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_list_skills(self, mock_anthropic):
        """Test listing available skills."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        skills = await gateway.list_skills()
        
        # Should have discovered default skills
        assert len(skills) > 0
        assert all('skill_id' in s for s in skills)
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_get_skill_info(self, mock_anthropic):
        """Test getting skill info."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        # Get info for a discovered skill
        skills = await gateway.list_skills()
        if skills:
            info = await gateway.get_skill_info(skills[0]['skill_id'])
            
            assert info is not None
            assert 'skill_id' in info
            assert 'circuit_state' in info
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('startd8.mcp.gateway.AsyncAnthropic')
    async def test_get_skill_info_not_found(self, mock_anthropic):
        """Test getting info for non-existent skill."""
        gateway = MCPGateway()
        await gateway.initialize()
        
        info = await gateway.get_skill_info("skill-nonexistent")
        
        assert info is None
    
    def test_get_circuit_state(self):
        """Test getting circuit state for skill."""
        gateway = MCPGateway()
        
        state = gateway.get_circuit_state("skill-test")
        
        assert state == "closed"
    
    def test_get_stats(self):
        """Test getting gateway statistics."""
        gateway = MCPGateway()
        
        stats = gateway.get_stats()
        
        assert 'initialized' in stats
        assert 'skills_registered' in stats
        assert 'circuit_states' in stats
        assert 'cache_config' in stats
        assert 'cache_stats' in stats
        assert 'rate_limiter_stats' in stats
        assert 'global_circuit_state' in stats


class TestGatewayTypedErrors:
    """Tests for typed gateway exceptions."""

    @pytest.mark.asyncio
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    async def test_rate_limit_error_raises_typed(self):
        """Gateway translates rate-limit runtime error to typed exception."""
        gateway = MCPGateway()
        await gateway.initialize()

        async def fail_acquire(*_, **__):
            raise RuntimeError("Rate limit exceeded. Would need to wait 1.0s")

        gateway._global_rate_limiter.acquire = fail_acquire  # type: ignore

        with pytest.raises(GatewayRateLimitExceededError):
            await gateway.execute_skill("skill-react-game-enhancer", "prompt")

        await gateway.shutdown()


class TestRateLimiterAndCacheStats:
    """Tests for rate limiter metrics and cache lock timeout tracking."""

    @pytest.mark.asyncio
    async def test_rate_limiter_wait_stats_increment(self, monkeypatch):
        """Wait events and total wait seconds are recorded."""
        limiter = TokenBucketRateLimiter(rate=1.0, burst_size=1)

        await limiter.acquire()  # consume burst

        # Patch sleep to avoid real delay
        monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))

        await limiter.acquire()  # triggers wait
        stats = limiter.get_stats()

        assert stats["wait_events"] >= 1
        assert stats["total_wait_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_cache_lock_timeouts_reported(self):
        """Cache lock timeouts surface in stats and gateway get_stats."""
        gateway = MCPGateway()
        cache = gateway.cache

        # Hold the lock to force timeout in _acquire_lock
        await cache._lock.acquire()
        try:
            result = await cache.get("skill-x", "prompt")
            assert result is None
        finally:
            cache._lock.release()

        stats = cache.get_stats()
        assert stats["lock_timeouts"] >= 1

        gw_stats = gateway.get_stats()
        assert gw_stats["cache_stats"]["lock_timeouts"] >= 1


# =============================================================================
# SKILL EXECUTION RESULT TESTS
# =============================================================================

class TestSkillExecutionResult:
    """Tests for SkillExecutionResult dataclass."""
    
    def test_creation(self, mock_skill_result):
        """Test creating a skill execution result."""
        assert mock_skill_result.content == "Test response content"
        assert mock_skill_result.skill_id == "skill-test"
        assert mock_skill_result.execution_time_ms == 150
        assert mock_skill_result.cache_hit is False
    
    def test_to_dict(self, mock_skill_result):
        """Test converting result to dictionary."""
        data = mock_skill_result.to_dict()
        
        assert data['content'] == "Test response content"
        assert data['skill_id'] == "skill-test"
        assert data['token_usage']['input'] == 100
        assert data['token_usage']['output'] == 200
        assert data['cache_hit'] is False
