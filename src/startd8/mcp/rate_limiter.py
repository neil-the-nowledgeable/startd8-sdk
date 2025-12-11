"""
Token bucket rate limiter for MCP Gateway.

Provides rate limiting to prevent API quota exhaustion.
"""

import asyncio
import time
from typing import Dict, Any

from .types import RateLimiterConfig


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter implementation.
    
    Allows burst traffic up to bucket size, then limits to
    sustained rate of tokens per second.
    
    Example:
        >>> limiter = TokenBucketRateLimiter(rate=10.0, burst_size=20)
        >>> await limiter.acquire()  # Consume 1 token
        >>> await limiter.acquire(tokens=5)  # Consume 5 tokens
    """
    
    def __init__(self, rate: float, burst_size: int):
        """
        Initialize token bucket rate limiter.
        
        Args:
            rate: Tokens per second (sustained rate)
            burst_size: Maximum tokens in bucket (burst capacity)
        """
        self.rate = rate  # tokens per second
        self.burst_size = burst_size
        
        self._tokens = float(burst_size)
        self._last_update = time.time()
        self._lock = asyncio.Lock()
        self._wait_events = 0
        self._total_wait_seconds = 0.0
    
    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            
        Raises:
            RuntimeError: If request would exceed limits (wait time > 10s)
        """
        async with self._lock:
            self._refill()
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            
            # Calculate wait time
            needed = tokens - self._tokens
            wait_time = needed / self.rate
            
            if wait_time > 10:  # Max 10 second wait
                raise RuntimeError(
                    f"Rate limit exceeded. Would need to wait {wait_time:.1f}s"
                )
            
            try:
                await asyncio.sleep(wait_time)
                self._refill()
                self._tokens -= tokens
                self._wait_events += 1
                self._total_wait_seconds += wait_time
            except asyncio.CancelledError:
                # Restore tokens on cancellation to maintain consistency
                self._tokens += tokens
                raise

    def get_stats(self) -> Dict[str, Any]:
        """
        Return basic rate limiter stats (approximate, not thread-safe).
        
        For accurate stats under concurrent access, use the async path that
        acquires the lock before reading shared state.
        """
        # Best-effort stats (may be slightly stale)
        self._refill()
        avg_wait = (
            self._total_wait_seconds / self._wait_events
            if self._wait_events > 0 else 0.0
        )
        return {
            "available_tokens": self._tokens,  # May be stale
            "wait_events": self._wait_events,  # May have race condition
            "total_wait_seconds": round(self._total_wait_seconds, 4),
            "avg_wait_seconds": round(avg_wait, 4),
            "rate": self.rate,
            "burst_size": self.burst_size,
        }
    
    async def get_stats_async(self) -> Dict[str, Any]:
        """
        Return rate limiter stats with locking for thread-safety.
        
        Prefer this in concurrent contexts to avoid race conditions.
        """
        async with self._lock:
            self._refill()
            avg_wait = (
                self._total_wait_seconds / self._wait_events
                if self._wait_events > 0 else 0.0
            )
            return {
                "available_tokens": self._tokens,
                "wait_events": self._wait_events,
                "total_wait_seconds": round(self._total_wait_seconds, 4),
                "avg_wait_seconds": round(avg_wait, 4),
                "rate": self.rate,
                "burst_size": self.burst_size,
            }
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(
            self.burst_size,
            self._tokens + elapsed * self.rate
        )
        self._last_update = now
    
    def get_available_tokens(self) -> float:
        """
        Get current number of available tokens (without consuming).
        
        Returns:
            Number of tokens currently available
        """
        self._refill()
        return self._tokens
