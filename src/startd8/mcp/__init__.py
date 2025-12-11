"""
MCP Gateway Module - Centralized MCP communication layer.

This module provides infrastructure for production deployment:
- Connection pooling and management
- Rate limiting (global and per-skill)
- Response caching
- Circuit breaking
- Skill discovery
"""

from .gateway import MCPGateway
from .types import (
    SkillExecutionResult,
    MCPGatewayConfig,
    CircuitBreakerConfig,
    RateLimiterConfig,
    CacheConfig,
    AuthConfig,
    RequestSigningConfig,
    ObservabilityConfig,
)
from .circuit_breaker import CircuitBreaker, CircuitState
from .rate_limiter import TokenBucketRateLimiter
from .cache import ResponseCache
from .registry import SkillRegistry, SkillMetadata
from .gateway import GatewayError, GatewayCircuitOpenError, GatewayRateLimitExceededError

__all__ = [
    "MCPGateway",
    "MCPGatewayConfig",
    "SkillExecutionResult",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "TokenBucketRateLimiter",
    "RateLimiterConfig",
    "ResponseCache",
    "CacheConfig",
    "AuthConfig",
    "RequestSigningConfig",
    "ObservabilityConfig",
    "SkillRegistry",
    "SkillMetadata",
    "GatewayError",
    "GatewayCircuitOpenError",
    "GatewayRateLimitExceededError",
]
