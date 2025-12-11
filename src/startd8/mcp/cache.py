"""
Response cache for MCP Gateway.

Provides LRU cache with TTL-based expiration for skill responses.
"""

import asyncio
import time
import hashlib
import json
from collections import OrderedDict
from typing import Optional, Dict, Tuple

from .types import CacheConfig, SkillExecutionResult
from ..logging_config import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """
    LRU cache for skill responses.
    
    Caches responses based on (skill_id, prompt_hash) key.
    Uses TTL-based expiration and LRU eviction.
    
    Example:
        >>> config = CacheConfig(ttl_seconds=300, max_entries=1000)
        >>> cache = ResponseCache(config)
        >>> 
        >>> # Store result
        >>> await cache.set("skill-react-game-enhancer", "Add notifications", result)
        >>> 
        >>> # Retrieve cached result
        >>> cached = await cache.get("skill-react-game-enhancer", "Add notifications")
    """
    
    def __init__(self, config: CacheConfig):
        """
        Initialize response cache.
        
        Args:
            config: Cache configuration
        """
        self.config = config
        self._cache: OrderedDict[str, Tuple[float, SkillExecutionResult]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._lock_timeouts = 0

    async def _acquire_lock(self, timeout: float = 1.0) -> bool:
        """
        Acquire the cache lock with a timeout to prevent indefinite blocking.
        Returns True if acquired, False otherwise.
        """
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning("Cache lock acquisition timed out; returning miss")
            self._lock_timeouts += 1
            return False
    
    def _hash_prompt(self, prompt: str) -> str:
        """Create hash of prompt for cache key."""
        # Use full hash to minimize collision risk
        return hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    
    def _make_key(self, skill_id: str, prompt: str, tenant_id: Optional[str] = None) -> str:
        """Create cache key from skill_id, prompt, and optional tenant."""
        prompt_hash = self._hash_prompt(prompt)
        if self.config.isolate_by_tenant and tenant_id:
            # Basic validation to prevent delimiter injection in keys
            if not isinstance(tenant_id, str):
                raise ValueError("tenant_id must be a string")
            if len(tenant_id) > 256:
                raise ValueError("tenant_id exceeds maximum length (256)")
            if ':' in tenant_id or '/' in tenant_id:
                raise ValueError("tenant_id cannot contain ':' or '/'")
            return f"{skill_id}:{tenant_id}:{prompt_hash}"
        return f"{skill_id}:{prompt_hash}"
    
    async def get(
        self,
        skill_id: str,
        prompt: str,
        tenant_id: Optional[str] = None
    ) -> Optional[SkillExecutionResult]:
        """
        Get cached response if available and not expired.
        
        Args:
            skill_id: The skill identifier
            prompt: The prompt text
            
        Returns:
            Cached result or None if not found/expired
        """
        if not self.config.enabled:
            return None
        
        lock_acquired = await self._acquire_lock()
        if not lock_acquired:
            return None
        try:
            key = self._make_key(skill_id, prompt, tenant_id=tenant_id)
            
            if key not in self._cache:
                return None
            
            timestamp, result = self._cache[key]
            
            # Check TTL
            if time.time() - timestamp > self.config.ttl_seconds:
                del self._cache[key]
                return None
            
            # Update access order (LRU)
            self._cache.move_to_end(key)
            
            logger.debug(f"Cache hit for {skill_id}")
            return result
        finally:
            if lock_acquired:
                self._lock.release()
    
    async def set(
        self,
        skill_id: str,
        prompt: str,
        result: SkillExecutionResult,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Cache a skill execution result.
        
        Args:
            skill_id: The skill identifier
            prompt: The prompt text
            result: The execution result to cache
        """
        if not self.config.enabled:
            return
        
        # Check entry size before acquiring lock
        result_json = json.dumps(result.to_dict())
        if len(result_json) > self.config.max_entry_size_bytes:
            logger.debug(f"Skipping cache for {skill_id}: response too large")
            return
        
        lock_acquired = await self._acquire_lock()
        if not lock_acquired:
            return
        try:
            key = self._make_key(skill_id, prompt, tenant_id=tenant_id)
            
            # If key exists, just update (no eviction needed)
            if key in self._cache:
                self._cache[key] = (time.time(), result)
                self._cache.move_to_end(key)
                return
            
            # Evict if at capacity (only for new entries)
            while len(self._cache) >= self.config.max_entries:
                oldest_key, _ = self._cache.popitem(last=False)
                logger.debug(f"Evicted cache entry {oldest_key}")
            
            # Now safe to add new entry
            self._cache[key] = (time.time(), result)
        finally:
            if lock_acquired:
                self._lock.release()
    
    async def invalidate(self, skill_id: Optional[str] = None) -> int:
        """
        Invalidate cache entries.
        
        Args:
            skill_id: If provided, only invalidate entries for this skill.
                     If None, invalidate all entries.
                     
        Returns:
            Number of entries invalidated
        """
        lock_acquired = await self._acquire_lock()
        if not lock_acquired:
            return 0
        try:
            if skill_id is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            
            keys_to_remove = [
                k for k in list(self._cache.keys())
                if k.startswith(f"{skill_id}:")
            ]
            
            for key in keys_to_remove:
                self._cache.pop(key, None)
            
            return len(keys_to_remove)
        finally:
            if lock_acquired:
                self._lock.release()
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            'size': len(self._cache),
            'max_entries': self.config.max_entries,
            'enabled': self.config.enabled,
            'lock_timeouts': self._lock_timeouts,
        }
