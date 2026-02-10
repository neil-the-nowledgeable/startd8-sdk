"""
Connection pooling and timeout configuration for agents.

This module provides shared infrastructure for HTTP client management:
- TimeoutConfig: Configurable timeout settings
- ClientPool: Thread-safe connection pool for reusing HTTP clients
"""

import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

# Optional dependencies - import with availability flags
try:
    from anthropic import Anthropic, AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    Anthropic = None
    AsyncAnthropic = None
    _ANTHROPIC_AVAILABLE = False

try:
    from openai import OpenAI, AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    _OPENAI_AVAILABLE = False

try:
    from google import genai
    _GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    _GEMINI_AVAILABLE = False


@dataclass
class TimeoutConfig:
    """
    Timeout configuration for agent HTTP requests.

    All timeouts are in seconds. Uses httpx.Timeout under the hood.

    Attributes:
        connect: Timeout for establishing a connection. Default: 10.0
        read: Timeout for reading response data. Default: 300.0
        write: Timeout for sending request data. Default: 30.0
        pool: Timeout for acquiring a connection from the pool. Default: 10.0

    Example:
        ```python
        from startd8.agents import ClaudeAgent, TimeoutConfig

        # Quick timeouts for fast-fail behavior
        fast_timeout = TimeoutConfig(connect=5.0, read=30.0)
        agent = ClaudeAgent(name="claude", timeout_config=fast_timeout)

        # Long timeouts for very complex requests
        slow_timeout = TimeoutConfig(read=600.0)
        agent = ClaudeAgent(name="claude", timeout_config=slow_timeout)
        ```
    """

    connect: float = 10.0
    read: float = 300.0
    write: float = 30.0
    pool: float = 10.0

    def __post_init__(self):
        if self.connect < 0:
            raise ValueError("connect timeout must be non-negative")
        if self.read < 0:
            raise ValueError("read timeout must be non-negative")
        if self.write < 0:
            raise ValueError("write timeout must be non-negative")
        if self.pool < 0:
            raise ValueError("pool timeout must be non-negative")

    def to_httpx_timeout(self):
        """
        Convert to httpx.Timeout object.

        Returns:
            httpx.Timeout configured with these settings
        """
        import httpx
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool,
        )

    def __hash__(self):
        """Make TimeoutConfig hashable for use as dict key"""
        return hash((self.connect, self.read, self.write, self.pool))

    def __eq__(self, other):
        if not isinstance(other, TimeoutConfig):
            return False
        return (self.connect, self.read, self.write, self.pool) == (
            other.connect, other.read, other.write, other.pool
        )


class ClientPool:
    """
    Thread-safe connection pool for sharing HTTP clients across agent instances.

    Reduces connection overhead by reusing clients with the same configuration.
    Clients are keyed by (api_key_hash, timeout_config) to ensure agents with
    different configurations get separate clients.

    Example:
        ```python
        # Agents with same config share a client
        agent1 = ClaudeAgent(name="a1", use_connection_pool=True)
        agent2 = ClaudeAgent(name="a2", use_connection_pool=True)
        # agent1 and agent2 share the same underlying HTTP client

        # Agents with different timeouts get separate clients
        fast_agent = ClaudeAgent(
            name="fast",
            timeout_config=TimeoutConfig(read=30.0),
            use_connection_pool=True
        )
        # fast_agent has its own client due to different timeout
        ```
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sync_clients: Dict[Tuple[int, TimeoutConfig], Any] = {}
        self._async_clients: Dict[Tuple[int, TimeoutConfig], Any] = {}
        self._cleanup_registered = False

    def _get_key(self, api_key: Optional[str], timeout_config: TimeoutConfig) -> Tuple[int, TimeoutConfig]:
        """Generate cache key from api_key and timeout_config"""
        # Hash the API key for privacy (don't store raw keys)
        key_hash = hash(api_key) if api_key else 0
        return (key_hash, timeout_config)

    def get_anthropic_clients(
        self,
        api_key: Optional[str],
        timeout_config: TimeoutConfig
    ) -> Tuple[Any, Any]:
        """
        Get or create Anthropic sync and async clients.

        Args:
            api_key: Anthropic API key
            timeout_config: Timeout configuration

        Returns:
            Tuple of (sync_client, async_client)
        """
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed")

        key = self._get_key(api_key, timeout_config)
        httpx_timeout = timeout_config.to_httpx_timeout()

        with self._lock:
            if key not in self._sync_clients:
                self._sync_clients[key] = Anthropic(api_key=api_key, timeout=httpx_timeout)
                self._async_clients[key] = AsyncAnthropic(api_key=api_key, timeout=httpx_timeout)
                self._register_cleanup()

            return self._sync_clients[key], self._async_clients[key]

    def get_openai_clients(
        self,
        api_key: Optional[str],
        timeout_config: TimeoutConfig,
        base_url: Optional[str] = None
    ) -> Tuple[Any, Any]:
        """
        Get or create OpenAI sync and async clients.

        Args:
            api_key: OpenAI API key
            timeout_config: Timeout configuration
            base_url: Optional base URL for OpenAI-compatible APIs

        Returns:
            Tuple of (sync_client, async_client)
        """
        if not _OPENAI_AVAILABLE:
            raise ImportError("openai package not installed")

        # Include base_url in key for OpenAI-compatible APIs
        key_base = self._get_key(api_key, timeout_config)
        key = (key_base[0], key_base[1], base_url)
        httpx_timeout = timeout_config.to_httpx_timeout()

        with self._lock:
            if key not in self._sync_clients:
                self._sync_clients[key] = OpenAI(
                    api_key=api_key,
                    timeout=httpx_timeout,
                    base_url=base_url
                )
                self._async_clients[key] = AsyncOpenAI(
                    api_key=api_key,
                    timeout=httpx_timeout,
                    base_url=base_url
                )
                self._register_cleanup()

            return self._sync_clients[key], self._async_clients[key]

    def get_gemini_client(
        self,
        api_key: str,
        timeout_config: TimeoutConfig
    ) -> Any:
        """
        Get or create Gemini client.

        Args:
            api_key: Google API key
            timeout_config: Timeout configuration

        Returns:
            genai.Client instance

        Note:
            Gemini uses a single sync client that's wrapped with run_in_executor
            for async operations, so only one client is returned.
        """
        if not _GEMINI_AVAILABLE:
            raise ImportError("google-genai package not installed")

        key = self._get_key(api_key, timeout_config)
        httpx_timeout = timeout_config.to_httpx_timeout()

        with self._lock:
            if key not in self._sync_clients:
                # Note: google-genai 1.x doesn't support custom http_client in Client()
                self._sync_clients[key] = genai.Client(api_key=api_key)
                self._register_cleanup()

            return self._sync_clients[key]

    def _register_cleanup(self):
        """Register cleanup handler to run on exit"""
        if not self._cleanup_registered:
            import atexit
            atexit.register(self.cleanup)
            self._cleanup_registered = True

    def cleanup(self):
        """Clean up all pooled clients"""
        with self._lock:
            # Clear references - clients will be garbage collected
            self._sync_clients.clear()
            self._async_clients.clear()

    def stats(self) -> Dict[str, int]:
        """Get pool statistics"""
        with self._lock:
            return {
                "sync_clients": len(self._sync_clients),
                "async_clients": len(self._async_clients),
            }


# Global client pool instance
_client_pool: Optional[ClientPool] = None
_pool_lock = threading.Lock()


def get_client_pool() -> ClientPool:
    """
    Get the global client pool instance.

    Creates the pool on first access (lazy initialization).

    Returns:
        The global ClientPool instance
    """
    global _client_pool
    if _client_pool is None:
        with _pool_lock:
            if _client_pool is None:
                _client_pool = ClientPool()
    return _client_pool
