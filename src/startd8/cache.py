"""
Caching utilities for startd8 SDK

Provides simple in-memory caching for frequently accessed data.
"""

from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
from functools import wraps
import threading


class CacheEntry:
    """A single cache entry with expiration"""
    
    def __init__(self, value: Any, ttl_seconds: Optional[int] = None):
        """
        Initialize cache entry
        
        Args:
            value: Cached value
            ttl_seconds: Time to live in seconds (None = no expiration)
        """
        self.value = value
        self.created_at = datetime.now(timezone.utc)
        self.ttl_seconds = ttl_seconds
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        if self.ttl_seconds is None:
            return False
        return datetime.now(timezone.utc) - self.created_at > timedelta(seconds=self.ttl_seconds)


class SimpleCache:
    """
    Thread-safe simple in-memory cache
    
    Provides basic caching with TTL support.
    """
    
    def __init__(self, default_ttl: Optional[int] = 300):
        """
        Initialize cache
        
        Args:
            default_ttl: Default time to live in seconds (default: 5 minutes)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            if entry.is_expired():
                del self._cache[key]
                return None
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        with self._lock:
            self._cache[key] = CacheEntry(value, ttl or self.default_ttl)
    
    def delete(self, key: str) -> None:
        """Delete key from cache"""
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self) -> int:
        """
        Remove expired entries
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)
    
    def size(self) -> int:
        """Get number of cache entries"""
        with self._lock:
            return len(self._cache)


# Global cache instance
_default_cache = SimpleCache()


def cached(key_prefix: str = "", ttl: Optional[int] = None):
    """
    Decorator to cache function results
    
    Args:
        key_prefix: Prefix for cache keys
        ttl: Time to live in seconds
    
    Example:
        @cached(key_prefix="prompt", ttl=300)
        def get_prompt(prompt_id: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Try to get from cache
            cached_value = _default_cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = func(*args, **kwargs)
            _default_cache.set(cache_key, result, ttl=ttl)
            return result
        
        return wrapper
    return decorator















