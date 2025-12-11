"""
Circuit breaker implementation for MCP Gateway.

Provides resilience by preventing cascading failures when skills are unavailable.
"""

import asyncio
import time
from typing import Optional

from ..common import CircuitState
from .types import CircuitBreakerConfig
from ..logging_config import get_logger

logger = get_logger(__name__)


class CircuitBreaker:
    """
    Circuit breaker implementation for individual skills.
    
    Implements the circuit breaker pattern to prevent cascading failures:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Requests fail fast without calling the service
    - HALF_OPEN: Limited requests allowed to test recovery
    
    Example:
        >>> config = CircuitBreakerConfig(failure_threshold=5)
        >>> breaker = CircuitBreaker("skill-react-game-enhancer", config)
        >>> 
        >>> try:
        ...     await breaker.check()
        ...     # Execute request
        ...     await breaker.record_success()
        ... except RuntimeError:
        ...     await breaker.record_failure()
    """
    
    def __init__(self, skill_id: str, config: CircuitBreakerConfig):
        """
        Initialize circuit breaker.
        
        Args:
            skill_id: Identifier for the skill this breaker protects
            config: Circuit breaker configuration
        """
        self.skill_id = skill_id
        self.config = config
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_requests = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    async def check(self) -> None:
        """
        Check if request should proceed.
        
        Raises:
            RuntimeError: If circuit is open and request should be blocked
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return
            
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    logger.info(f"Circuit {self.skill_id} transitioning to HALF_OPEN")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                else:
                    elapsed = time.time() - (self._last_failure_time or 0)
                    remaining = self.config.recovery_timeout_seconds - elapsed
                    raise RuntimeError(
                        f"Circuit breaker OPEN for skill '{self.skill_id}'. "
                        f"Will retry in {remaining:.1f}s"
                    )
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_requests >= self.config.half_open_max_requests:
                    raise RuntimeError(
                        f"Circuit breaker HALF_OPEN limit reached for '{self.skill_id}'"
                    )
                self._half_open_requests += 1
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.recovery_timeout_seconds
    
    async def record_success(self) -> None:
        """Record successful request."""
        async with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit {self.skill_id} CLOSED after successful request")
                self._state = CircuitState.CLOSED
                self._half_open_requests = 0
    
    async def record_failure(self) -> None:
        """Record failed request."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit {self.skill_id} OPEN after half-open failure")
                self._state = CircuitState.OPEN
                self._half_open_requests = 0
            elif self._failure_count >= self.config.failure_threshold:
                logger.warning(
                    f"Circuit {self.skill_id} OPEN after {self._failure_count} failures"
                )
                self._state = CircuitState.OPEN
    
    def reset(self) -> None:
        """
        Manually reset the circuit breaker to closed state.
        
        Use with caution - primarily for administrative purposes.
        """
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_requests = 0
        logger.info(f"Circuit {self.skill_id} manually reset")
