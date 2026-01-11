# SDK Architecture Enhancement Plan

**Version:** 1.0.0
**Date:** 2026-01-11
**Status:** Draft
**Author:** agent:claude-code

## Executive Summary

Analysis of the startd8 SDK reveals opportunities to improve modularity, performance, and robustness. This plan proposes incremental enhancements that maintain backward compatibility while addressing architectural concerns.

---

## Current State Analysis

### Strengths
- Well-defined provider protocol (`AgentProvider`)
- Thread-safe `ProviderRegistry` with entry point discovery
- Comprehensive event system with persistence support
- Good exception hierarchy in `exceptions.py`
- Async-first design with sync wrappers

### Areas for Improvement

| Category | Issue | Impact |
|----------|-------|--------|
| Modularity | `agents.py` is 1550+ lines | Hard to maintain, test |
| Modularity | Cost tracking embedded in `BaseAgent` | Tight coupling |
| Performance | Synchronous storage operations | Blocks async pipelines |
| Performance | Thread pool per sync-async bridge | Resource waste |
| Robustness | No retry/circuit breaker in agents | Fragile to transient failures |
| Robustness | Complex cleanup code in agents | Error-prone |

---

## Phase 1: Modularity Improvements

### 1.1 Split `agents.py` into Per-Provider Modules

**Current:**
```
src/startd8/agents.py (1550+ lines, all agents)
```

**Proposed:**
```
src/startd8/agents/
├── __init__.py          # Re-exports for backward compat
├── base.py              # BaseAgent class
├── claude.py            # ClaudeAgent
├── openai.py            # GPT4Agent, OpenAICompatibleAgent
├── gemini.py            # GeminiAgent
├── mock.py              # MockAgent
└── mixins.py            # Shared mixins (cleanup, cost tracking)
```

**Benefits:**
- Each agent can be maintained independently
- Easier to add new agents
- Clearer ownership of provider-specific code

**Migration:**
```python
# Old (still works)
from startd8.agents import ClaudeAgent

# New (also works)
from startd8.agents.claude import ClaudeAgent
```

### 1.2 Extract Cost Tracking Mixin

**Current:** Cost tracking logic embedded in `BaseAgent._run_with_cost_tracking()` (100+ lines)

**Proposed:**
```python
# src/startd8/agents/mixins.py
class CostTrackingMixin:
    """Mixin providing cost tracking capabilities"""

    cost_tracker: Optional['CostTracker']
    budget_manager: Optional['BudgetManager']

    async def _with_cost_tracking(
        self,
        coro: Coroutine,
        prompt_id: str,
        response_id: str,
        **context
    ) -> Any:
        """Execute coroutine with cost tracking wrapper"""
        # Pre-call budget check
        if self.budget_manager:
            self._check_budget(prompt_id, context)

        result = await coro

        # Post-call recording
        if self.cost_tracker:
            self._record_cost(result, prompt_id, response_id, context)

        return result
```

**Benefits:**
- Agents without cost tracking don't pay complexity cost
- Cost logic can evolve independently
- Easier to test cost tracking in isolation

### 1.3 Separate Sync/Async Bridge

**Current:** Each agent duplicates sync-to-async bridging code

**Proposed:**
```python
# src/startd8/utils/async_bridge.py
def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run async coroutine from sync context, handling nested loops"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Running inside existing loop - use thread bridge
    return _thread_bridge(coro)

def _thread_bridge(coro: Coroutine[Any, Any, T]) -> T:
    """Bridge async to sync via thread pool"""
    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(ctx.run, lambda: asyncio.run(coro)).result()
```

**Benefits:**
- Single implementation to maintain
- Consistent behavior across all agents
- Easier to optimize (e.g., reuse thread pool)

---

## Phase 2: Performance Improvements

### 2.1 Async Storage Backend

**Current:** `FileSystemStorage` uses synchronous file I/O

**Proposed:**
```python
# src/startd8/storage/async_backend.py
class AsyncFileSystemStorage(StorageBackend):
    """Async file system storage using aiofiles"""

    async def save_prompt_async(self, prompt: Prompt) -> None:
        async with aiofiles.open(path, 'w') as f:
            await f.write(prompt.model_dump_json())

    async def load_prompt_async(self, prompt_id: str) -> Optional[Prompt]:
        async with aiofiles.open(path, 'r') as f:
            data = await f.read()
            return Prompt.model_validate_json(data)
```

**Benefits:**
- Non-blocking I/O in async pipelines
- Better throughput for concurrent operations
- Optional - sync backend remains default

### 2.2 Connection Pooling for Agents

**Current:** Each agent creates its own HTTP client

**Proposed:**
```python
# src/startd8/agents/base.py
class BaseAgent:
    # Class-level connection pool
    _http_pool: ClassVar[Optional[httpx.AsyncClient]] = None
    _pool_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_http_pool(cls) -> httpx.AsyncClient:
        with cls._pool_lock:
            if cls._http_pool is None:
                cls._http_pool = httpx.AsyncClient(
                    limits=httpx.Limits(max_connections=100),
                    timeout=httpx.Timeout(60.0)
                )
            return cls._http_pool
```

**Benefits:**
- Reduced connection overhead
- Better resource utilization
- Configurable limits

### 2.3 Lazy Provider Loading

**Current:** `_register_builtin_providers()` imports all providers

**Proposed:**
```python
# src/startd8/providers/registry.py
class ProviderRegistry:
    _lazy_providers: Dict[str, str] = {
        'anthropic': 'startd8.providers.anthropic:AnthropicProvider',
        'openai': 'startd8.providers.openai:OpenAIProvider',
        # ...
    }

    @classmethod
    def get_provider(cls, name: str) -> Optional[AgentProvider]:
        name = name.lower()

        # Check already loaded
        if name in cls._providers:
            return cls._providers[name]

        # Lazy load if registered
        if name in cls._lazy_providers:
            cls._load_provider(name, cls._lazy_providers[name])
            return cls._providers.get(name)

        return None
```

**Benefits:**
- Faster startup (only load what's used)
- Reduced memory for unused providers
- No import errors for missing optional deps

---

## Phase 3: Robustness Improvements

### 3.1 Retry Decorator for Transient Failures

**Proposed:**
```python
# src/startd8/utils/retry.py
@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
    )
    retryable_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)

def with_retry(config: Optional[RetryConfig] = None):
    """Decorator for retrying transient failures with exponential backoff"""
    config = config or RetryConfig()

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e
                    delay = min(
                        config.base_delay * (config.exponential_base ** attempt),
                        config.max_delay
                    )
                    await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
```

**Usage in agents:**
```python
class ClaudeAgent(BaseAgent):
    @with_retry(RetryConfig(max_attempts=3))
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        # ... existing implementation
```

### 3.2 Circuit Breaker Pattern

**Proposed:**
```python
# src/startd8/utils/circuit_breaker.py
class CircuitBreaker:
    """Circuit breaker for provider resilience"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_requests: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_successes = 0

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError(f"Circuit open until {self._reset_time}")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

### 3.3 Simplified Cleanup with Context Managers

**Current:** Complex `cleanup()` and `__del__` with multiple try/except

**Proposed:**
```python
# src/startd8/agents/base.py
class BaseAgent:
    def __init__(self, ...):
        self._cleanup_stack = AsyncExitStack()

    async def __aenter__(self) -> 'BaseAgent':
        return self

    async def __aexit__(self, *args) -> None:
        await self._cleanup_stack.aclose()

# Usage
async with ClaudeAgent() as agent:
    response = await agent.agenerate("Hello")
# Automatic cleanup
```

### 3.4 Request Timeout Configuration

**Proposed:**
```python
@dataclass
class AgentConfig:
    """Configuration for agent behavior"""
    connect_timeout: float = 10.0
    read_timeout: float = 120.0
    total_timeout: float = 300.0
    retry_config: Optional[RetryConfig] = None

class BaseAgent:
    def __init__(
        self,
        name: str,
        model: str,
        config: Optional[AgentConfig] = None,
        ...
    ):
        self.config = config or AgentConfig()
```

---

## Phase 4: Architecture Diagram (Target State)

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Application Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │     CLI      │  │     TUI      │  │      Python API           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────────┐
│                         Orchestration Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   Pipeline   │  │  Benchmark   │  │      Job Queue            │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────────┐
│                           Agent Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  BaseAgent   │──│   Mixins     │  │      AgentConfig          │  │
│  │  (abstract)  │  │ - CostTrack  │  │   - Timeouts              │  │
│  └──────────────┘  │ - Retry      │  │   - Retry                 │  │
│        │           │ - Cleanup    │  │   - CircuitBreaker        │  │
│  ┌─────┴─────┐     └──────────────┘  └──────────────────────────┘  │
│  │           │                                                       │
│  ▼           ▼                                                       │
│ Claude    GPT4    Gemini    OpenAICompat    Mock                    │
└─────────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────────┐
│                          Provider Layer                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    ProviderRegistry                           │  │
│  │  - Lazy loading    - Entry point discovery                    │  │
│  │  - Model lookup    - Provider info                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Anthropic   │  │   OpenAI     │  │     Gemini / Mock        │  │
│  │  Provider    │  │   Provider   │  │     Providers            │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────────┐
│                       Cross-Cutting Concerns                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  EventBus    │  │ CostTracker  │  │      Storage              │  │
│  │  (pub/sub)   │  │ BudgetMgr    │  │  - Sync / Async           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   Logging    │  │   Retry      │  │   Circuit Breaker         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Priority

| Phase | Item | Effort | Impact | Priority | Status |
|-------|------|--------|--------|----------|--------|
| 1.1 | Split agents.py | Medium | High | **P1** | Pending |
| 1.2 | Extract cost tracking mixin | Low | Medium | P2 | Pending |
| 1.3 | Sync/async bridge util | Low | Medium | P2 | Pending |
| 2.1 | Async storage backend | Medium | Medium | P3 | Pending |
| 2.2 | Connection pooling | Low | High | **P1** | **COMPLETE** |
| 2.3 | Lazy provider loading | Low | Low | P3 | Pending |
| 3.1 | Retry decorator | Low | High | **P1** | **COMPLETE** |
| 3.2 | Circuit breaker | Medium | Medium | P2 | Pending |
| 3.3 | Context manager cleanup | Low | Medium | P2 | Pending |
| 3.4 | Timeout configuration | Low | High | **P1** | **COMPLETE** |

---

## Backward Compatibility

All changes maintain backward compatibility:

1. **Re-exports** - Old import paths continue to work via `__init__.py`
2. **Default behavior** - New features are opt-in (e.g., retry disabled by default)
3. **Deprecation warnings** - Old patterns warn but don't break
4. **Migration guide** - Document upgrade path for each change

---

## Testing Strategy

1. **Unit tests** for each new module/mixin
2. **Integration tests** for backward compatibility
3. **Performance benchmarks** before/after for Phase 2
4. **Chaos testing** for Phase 3 (inject failures)

---

## Open Questions

1. Should `EventBus` become instance-based instead of class-level?
2. Is `aiofiles` dependency acceptable for async storage?
3. Should retry config be provider-specific or global?

---

## References

- `src/startd8/agents.py` - Current agent implementations
- `src/startd8/providers/registry.py` - Provider registry
- `src/startd8/events/bus.py` - Event system
- `src/startd8/storage/backend.py` - Storage layer
