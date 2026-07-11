# Phase 3 & 4: Medium Priority & Optimization - Detailed Design

**Duration**: 4 Weeks (Weeks 5-8)  
**Total Effort**: 65 hours  
**Prerequisites**: Phase 1 & 2 Complete

---

## Phase 3: Medium Priority Improvements (Weeks 5-6)

### P3.1 Health Check System

**File**: `src/startd8/health_check.py`  
**Effort**: 8 hours

```python
# src/startd8/health_check.py
"""
Health Check System for application monitoring.
"""

import asyncio
import logging
import psutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a single component"""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SystemHealth:
    """Overall system health"""
    status: HealthStatus
    components: List[ComponentHealth]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = ""
    uptime_seconds: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                    "details": c.details
                }
                for c in self.components
            ]
        }


class HealthChecker:
    """
    System health checker with component monitoring.
    
    Example:
        checker = HealthChecker()
        checker.register("database", check_database)
        checker.register("api", check_api)
        
        health = await checker.check_all()
        print(health.status)
    """
    
    def __init__(self, version: str = "1.0.0"):
        self._checks: Dict[str, Callable[[], Awaitable[ComponentHealth]]] = {}
        self._version = version
        self._start_time = time.time()
    
    def register(
        self,
        name: str,
        check: Callable[[], Awaitable[ComponentHealth]]
    ):
        """Register a health check"""
        self._checks[name] = check
    
    async def check_component(self, name: str) -> ComponentHealth:
        """Run a single component check"""
        if name not in self._checks:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                message="Check not registered"
            )
        
        start = time.time()
        try:
            result = await self._checks[name]()
            result.latency_ms = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=int((time.time() - start) * 1000)
            )
    
    async def check_all(self, timeout: float = 30.0) -> SystemHealth:
        """Run all health checks"""
        components = []
        
        # Run checks concurrently with timeout
        tasks = [
            asyncio.wait_for(self.check_component(name), timeout=timeout)
            for name in self._checks
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for name, result in zip(self._checks.keys(), results):
            if isinstance(result, Exception):
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(result)
                ))
            else:
                components.append(result)
        
        # Add system metrics
        components.append(self._check_system_resources())
        
        # Determine overall status
        statuses = [c.status for c in components]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY
        
        return SystemHealth(
            status=overall,
            components=components,
            version=self._version,
            uptime_seconds=time.time() - self._start_time
        )
    
    def _check_system_resources(self) -> ComponentHealth:
        """Check system resource usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            details = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / (1024**3)
            }
            
            # Determine status based on thresholds
            if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
                status = HealthStatus.UNHEALTHY
                message = "Critical resource usage"
            elif cpu_percent > 70 or memory.percent > 70 or disk.percent > 80:
                status = HealthStatus.DEGRADED
                message = "Elevated resource usage"
            else:
                status = HealthStatus.HEALTHY
                message = "Resources OK"
            
            return ComponentHealth(
                name="system_resources",
                status=status,
                message=message,
                details=details
            )
        except Exception as e:
            return ComponentHealth(
                name="system_resources",
                status=HealthStatus.UNKNOWN,
                message=str(e)
            )


# Built-in health checks

async def check_anthropic_api() -> ComponentHealth:
    """Check Anthropic API connectivity"""
    from .secure_key_manager import get_secure_key_manager
    
    key_manager = get_secure_key_manager()
    api_key = key_manager.get_key("ANTHROPIC_API_KEY")
    
    if not api_key:
        return ComponentHealth(
            name="anthropic_api",
            status=HealthStatus.UNHEALTHY,
            message="API key not configured"
        )
    
    # Note: In production, make a lightweight API call to verify
    return ComponentHealth(
        name="anthropic_api",
        status=HealthStatus.HEALTHY,
        message="API key configured",
        details={"key_configured": True}
    )


async def check_openai_api() -> ComponentHealth:
    """Check OpenAI API connectivity"""
    from .secure_key_manager import get_secure_key_manager
    
    key_manager = get_secure_key_manager()
    api_key = key_manager.get_key("OPENAI_API_KEY")
    
    if not api_key:
        return ComponentHealth(
            name="openai_api",
            status=HealthStatus.UNHEALTHY,
            message="API key not configured"
        )
    
    return ComponentHealth(
        name="openai_api",
        status=HealthStatus.HEALTHY,
        message="API key configured",
        details={"key_configured": True}
    )


async def check_storage() -> ComponentHealth:
    """Check storage accessibility"""
    from pathlib import Path
    import tempfile
    
    storage_dir = Path.home() / ".startd8"
    
    try:
        # Check directory exists and is writable
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to write a test file
        test_file = storage_dir / ".health_check"
        test_file.write_text("test")
        test_file.unlink()
        
        return ComponentHealth(
            name="storage",
            status=HealthStatus.HEALTHY,
            message="Storage accessible",
            details={"path": str(storage_dir)}
        )
    except Exception as e:
        return ComponentHealth(
            name="storage",
            status=HealthStatus.UNHEALTHY,
            message=f"Storage error: {e}"
        )


def create_default_health_checker() -> HealthChecker:
    """Create health checker with default checks"""
    checker = HealthChecker()
    checker.register("anthropic_api", check_anthropic_api)
    checker.register("openai_api", check_openai_api)
    checker.register("storage", check_storage)
    return checker


# Global instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create global health checker"""
    global _health_checker
    if _health_checker is None:
        _health_checker = create_default_health_checker()
    return _health_checker
```

---

### P3.2 Standardized Error Messages

**File**: `src/startd8/error_messages.py`  
**Effort**: 4 hours

```python
# src/startd8/error_messages.py
"""
Standardized Error Messages for consistent user experience.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any


class ErrorCategory(Enum):
    """Categories of errors"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    API = "api"
    NETWORK = "network"
    FILE = "file"
    CONFIGURATION = "configuration"
    RATE_LIMIT = "rate_limit"
    INTERNAL = "internal"


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class StandardError:
    """Standardized error representation"""
    code: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    user_message: str
    details: Dict[str, Any] = None
    recovery_hint: str = ""
    documentation_url: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "user_message": self.user_message,
            "details": self.details or {},
            "recovery_hint": self.recovery_hint,
            "documentation_url": self.documentation_url
        }


class ErrorFactory:
    """
    Factory for creating standardized error messages.
    
    Example:
        error = ErrorFactory.api_key_missing("anthropic")
        print(error.user_message)
    """
    
    # API Key Errors
    @staticmethod
    def api_key_missing(provider: str) -> StandardError:
        return StandardError(
            code="ERR_API_KEY_MISSING",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            message=f"API key not found for {provider}",
            user_message=f"No API key configured for {provider}. Please add your API key.",
            details={"provider": provider},
            recovery_hint=f"Go to Settings → API Keys → Add {provider} key",
            documentation_url="https://docs.startd8.io/api-keys"
        )
    
    @staticmethod
    def api_key_invalid(provider: str) -> StandardError:
        return StandardError(
            code="ERR_API_KEY_INVALID",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            message=f"Invalid API key for {provider}",
            user_message=f"Your {provider} API key appears to be invalid. Please verify it.",
            details={"provider": provider},
            recovery_hint="Check that you copied the entire key without extra spaces"
        )
    
    # Rate Limit Errors
    @staticmethod
    def rate_limit_exceeded(provider: str, retry_after: int = 60) -> StandardError:
        return StandardError(
            code="ERR_RATE_LIMIT",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.MEDIUM,
            message=f"Rate limit exceeded for {provider}",
            user_message=f"Too many requests to {provider}. Please wait {retry_after} seconds.",
            details={"provider": provider, "retry_after": retry_after},
            recovery_hint=f"Wait {retry_after} seconds before trying again"
        )
    
    @staticmethod
    def budget_exceeded(provider: str, budget: float, spent: float) -> StandardError:
        return StandardError(
            code="ERR_BUDGET_EXCEEDED",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.HIGH,
            message=f"Budget exceeded for {provider}",
            user_message=f"You've exceeded your budget limit (${budget:.2f}). Spent: ${spent:.2f}",
            details={"provider": provider, "budget": budget, "spent": spent},
            recovery_hint="Increase your budget limit or wait for the next billing cycle"
        )
    
    # Validation Errors
    @staticmethod
    def validation_failed(field: str, reason: str, value: Any = None) -> StandardError:
        return StandardError(
            code="ERR_VALIDATION",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            message=f"Validation failed for {field}: {reason}",
            user_message=f"Invalid {field}: {reason}",
            details={"field": field, "reason": reason},
            recovery_hint="Check the input and try again"
        )
    
    @staticmethod
    def prompt_too_long(length: int, max_length: int) -> StandardError:
        return StandardError(
            code="ERR_PROMPT_TOO_LONG",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            message=f"Prompt exceeds maximum length ({length} > {max_length})",
            user_message=f"Your prompt is too long ({length:,} characters). Maximum is {max_length:,}.",
            details={"length": length, "max_length": max_length},
            recovery_hint="Shorten your prompt or split it into multiple requests"
        )
    
    @staticmethod
    def injection_detected(pattern: str) -> StandardError:
        return StandardError(
            code="ERR_INJECTION_DETECTED",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.CRITICAL,
            message=f"Potential injection attempt detected",
            user_message="Your input contains patterns that aren't allowed for security reasons.",
            details={"pattern_type": pattern},
            recovery_hint="Remove any instruction-like text from your prompt"
        )
    
    # File Errors
    @staticmethod
    def file_not_found(path: str) -> StandardError:
        return StandardError(
            code="ERR_FILE_NOT_FOUND",
            category=ErrorCategory.FILE,
            severity=ErrorSeverity.MEDIUM,
            message=f"File not found: {path}",
            user_message=f"The file '{path}' could not be found.",
            details={"path": path},
            recovery_hint="Check the file path and make sure the file exists"
        )
    
    @staticmethod
    def file_permission_denied(path: str, operation: str) -> StandardError:
        return StandardError(
            code="ERR_FILE_PERMISSION",
            category=ErrorCategory.FILE,
            severity=ErrorSeverity.MEDIUM,
            message=f"Permission denied for {operation} on {path}",
            user_message=f"You don't have permission to {operation} '{path}'.",
            details={"path": path, "operation": operation},
            recovery_hint="Check file permissions or choose a different location"
        )
    
    @staticmethod
    def path_traversal_blocked(path: str) -> StandardError:
        return StandardError(
            code="ERR_PATH_TRAVERSAL",
            category=ErrorCategory.FILE,
            severity=ErrorSeverity.CRITICAL,
            message=f"Path traversal attempt blocked: {path}",
            user_message="Access to this file path is not allowed.",
            details={"path": path},
            recovery_hint="Use a path within your allowed directories"
        )
    
    # API Errors
    @staticmethod
    def api_error(provider: str, status_code: int, message: str) -> StandardError:
        return StandardError(
            code="ERR_API_ERROR",
            category=ErrorCategory.API,
            severity=ErrorSeverity.MEDIUM,
            message=f"{provider} API error ({status_code}): {message}",
            user_message=f"The {provider} API returned an error. Please try again.",
            details={"provider": provider, "status_code": status_code, "api_message": message},
            recovery_hint="Wait a moment and try again"
        )
    
    @staticmethod
    def api_timeout(provider: str, timeout: float) -> StandardError:
        return StandardError(
            code="ERR_API_TIMEOUT",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            message=f"{provider} API request timed out after {timeout}s",
            user_message=f"The request to {provider} took too long. Please try again.",
            details={"provider": provider, "timeout": timeout},
            recovery_hint="Check your internet connection and try again"
        )
    
    @staticmethod
    def circuit_breaker_open(provider: str) -> StandardError:
        return StandardError(
            code="ERR_CIRCUIT_OPEN",
            category=ErrorCategory.API,
            severity=ErrorSeverity.HIGH,
            message=f"Circuit breaker open for {provider}",
            user_message=f"The {provider} service is currently unavailable due to repeated errors.",
            details={"provider": provider},
            recovery_hint="The system will automatically retry in a few minutes"
        )
    
    # Network Errors
    @staticmethod
    def network_error(message: str) -> StandardError:
        return StandardError(
            code="ERR_NETWORK",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            message=f"Network error: {message}",
            user_message="A network error occurred. Please check your connection.",
            details={"error": message},
            recovery_hint="Check your internet connection and try again"
        )
    
    # Configuration Errors
    @staticmethod
    def config_invalid(key: str, reason: str) -> StandardError:
        return StandardError(
            code="ERR_CONFIG_INVALID",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.MEDIUM,
            message=f"Invalid configuration for {key}: {reason}",
            user_message=f"Configuration error: {reason}",
            details={"key": key, "reason": reason},
            recovery_hint="Check your configuration settings"
        )
    
    # Internal Errors
    @staticmethod
    def internal_error(message: str, error_id: str = None) -> StandardError:
        return StandardError(
            code="ERR_INTERNAL",
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.HIGH,
            message=f"Internal error: {message}",
            user_message="An unexpected error occurred. Please try again or contact support.",
            details={"error_id": error_id} if error_id else {},
            recovery_hint="If this persists, please report the issue"
        )


# Exception classes using StandardError

class StartdError(Exception):
    """Base exception with StandardError support"""
    
    def __init__(self, standard_error: StandardError):
        self.error = standard_error
        super().__init__(standard_error.message)
    
    @property
    def user_message(self) -> str:
        return self.error.user_message
    
    @property
    def code(self) -> str:
        return self.error.code


class APIKeyError(StartdError):
    """API key related errors"""
    pass


class RateLimitError(StartdError):
    """Rate limit errors"""
    pass


class ValidationError(StartdError):
    """Validation errors"""
    pass


class FileOperationError(StartdError):
    """File operation errors"""
    pass


class APIError(StartdError):
    """API errors"""
    pass
```

---

### P3.3 Batch Request Handler

**File**: `src/startd8/batch_handler.py`  
**Effort**: 8 hours

```python
# src/startd8/batch_handler.py
"""
Batch Request Handler for efficient multi-prompt processing.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable, Awaitable, TypeVar
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BatchStatus(Enum):
    """Status of a batch operation"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


@dataclass
class BatchItem:
    """Single item in a batch"""
    id: str
    input: Any
    output: Any = None
    error: str = None
    status: BatchStatus = BatchStatus.PENDING
    started_at: datetime = None
    completed_at: datetime = None
    latency_ms: int = 0


@dataclass
class BatchResult:
    """Result of a batch operation"""
    batch_id: str
    status: BatchStatus
    items: List[BatchItem]
    total_items: int
    successful: int
    failed: int
    total_latency_ms: int
    started_at: datetime
    completed_at: datetime = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "total_items": self.total_items,
            "successful": self.successful,
            "failed": self.failed,
            "total_latency_ms": self.total_latency_ms,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "items": [
                {
                    "id": item.id,
                    "status": item.status.value,
                    "error": item.error,
                    "latency_ms": item.latency_ms
                }
                for item in self.items
            ]
        }


class BatchHandler:
    """
    Handle batch processing of requests.
    
    Features:
    - Concurrent execution with limits
    - Progress tracking
    - Error handling per item
    - Retry failed items
    
    Example:
        handler = BatchHandler(concurrency=5)
        
        prompts = ["prompt1", "prompt2", "prompt3"]
        result = await handler.execute(
            prompts,
            process_func=agent.agenerate
        )
    """
    
    def __init__(
        self,
        concurrency: int = 5,
        retry_failed: bool = True,
        max_retries: int = 2
    ):
        self.concurrency = concurrency
        self.retry_failed = retry_failed
        self.max_retries = max_retries
    
    async def execute(
        self,
        items: List[Any],
        process_func: Callable[[Any], Awaitable[Any]],
        on_progress: Callable[[int, int, BatchItem], None] = None,
        item_id_func: Callable[[Any, int], str] = None
    ) -> BatchResult:
        """
        Execute batch processing.
        
        Args:
            items: List of items to process
            process_func: Async function to process each item
            on_progress: Optional callback for progress updates
            item_id_func: Optional function to generate item IDs
            
        Returns:
            BatchResult with all items
        """
        import uuid
        import time
        
        batch_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(timezone.utc)
        
        # Create batch items
        batch_items = []
        for i, item in enumerate(items):
            item_id = item_id_func(item, i) if item_id_func else f"item_{i}"
            batch_items.append(BatchItem(id=item_id, input=item))
        
        # Semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.concurrency)
        
        async def process_item(batch_item: BatchItem, attempt: int = 1):
            """Process a single item with semaphore"""
            async with semaphore:
                batch_item.started_at = datetime.now(timezone.utc)
                batch_item.status = BatchStatus.RUNNING
                
                start_time = time.time()
                try:
                    result = await process_func(batch_item.input)
                    batch_item.output = result
                    batch_item.status = BatchStatus.COMPLETED
                except Exception as e:
                    batch_item.error = str(e)
                    batch_item.status = BatchStatus.FAILED
                    logger.warning(f"Batch item {batch_item.id} failed: {e}")
                finally:
                    batch_item.completed_at = datetime.now(timezone.utc)
                    batch_item.latency_ms = int((time.time() - start_time) * 1000)
                
                return batch_item
        
        # Process all items
        completed = 0
        tasks = [process_item(item) for item in batch_items]
        
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1
            
            if on_progress:
                on_progress(completed, len(batch_items), result)
        
        # Retry failed items if enabled
        if self.retry_failed:
            failed_items = [item for item in batch_items if item.status == BatchStatus.FAILED]
            
            for retry in range(self.max_retries):
                if not failed_items:
                    break
                
                logger.info(f"Retrying {len(failed_items)} failed items (attempt {retry + 2})")
                
                retry_tasks = [process_item(item, retry + 2) for item in failed_items]
                await asyncio.gather(*retry_tasks)
                
                failed_items = [item for item in failed_items if item.status == BatchStatus.FAILED]
        
        # Calculate results
        successful = sum(1 for item in batch_items if item.status == BatchStatus.COMPLETED)
        failed = sum(1 for item in batch_items if item.status == BatchStatus.FAILED)
        total_latency = sum(item.latency_ms for item in batch_items)
        
        # Determine overall status
        if failed == 0:
            status = BatchStatus.COMPLETED
        elif successful == 0:
            status = BatchStatus.FAILED
        else:
            status = BatchStatus.PARTIALLY_COMPLETED
        
        return BatchResult(
            batch_id=batch_id,
            status=status,
            items=batch_items,
            total_items=len(batch_items),
            successful=successful,
            failed=failed,
            total_latency_ms=total_latency,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc)
        )
    
    async def execute_with_agents(
        self,
        prompts: List[str],
        agents: List[Any],
        on_progress: Callable = None
    ) -> Dict[str, BatchResult]:
        """
        Execute prompts across multiple agents.
        
        Args:
            prompts: List of prompts
            agents: List of agent instances
            on_progress: Progress callback
            
        Returns:
            Dict mapping agent name to BatchResult
        """
        results = {}
        
        for agent in agents:
            logger.info(f"Processing batch with {agent.name}")
            
            async def process(prompt):
                return await agent.agenerate(prompt)
            
            result = await self.execute(
                prompts,
                process_func=process,
                on_progress=on_progress
            )
            
            results[agent.name] = result
        
        return results
```

---

### P3.4 Prompt Response Cache

**File**: `src/startd8/prompt_cache.py`  
**Effort**: 6 hours

```python
# src/startd8/prompt_cache.py
"""
Prompt Response Cache for avoiding duplicate API calls.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from .bounded_cache import BoundedLRUCache, get_cache

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    """Cached prompt response"""
    prompt_hash: str
    model: str
    response: str
    tokens_used: int
    cached_at: datetime
    hit_count: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_hash": self.prompt_hash,
            "model": self.model,
            "response": self.response,
            "tokens_used": self.tokens_used,
            "cached_at": self.cached_at.isoformat(),
            "hit_count": self.hit_count
        }


class PromptCache:
    """
    Cache for prompt responses to avoid duplicate API calls.
    
    Features:
    - Content-based hashing
    - Model-specific caching
    - Configurable TTL
    - Persistent storage option
    
    Example:
        cache = PromptCache()
        
        # Check cache before API call
        cached = cache.get(prompt, model="claude-3-sonnet")
        if cached:
            return cached.response
        
        # Make API call
        response = await agent.agenerate(prompt)
        
        # Cache response
        cache.set(prompt, model="claude-3-sonnet", response=response, tokens=1234)
    """
    
    def __init__(
        self,
        max_items: int = 500,
        default_ttl: int = 3600,  # 1 hour
        persistent_path: Path = None
    ):
        self._cache = get_cache(
            "prompt_cache",
            max_items=max_items,
            default_ttl=default_ttl
        )
        self._persistent_path = persistent_path
        
        # Load persistent cache if configured
        if persistent_path:
            self._load_persistent()
    
    @staticmethod
    def _hash_prompt(prompt: str, model: str) -> str:
        """Generate hash for prompt+model combination"""
        content = f"{model}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def get(self, prompt: str, model: str) -> Optional[CachedResponse]:
        """
        Get cached response for prompt.
        
        Args:
            prompt: The prompt text
            model: Model name
            
        Returns:
            CachedResponse if found, None otherwise
        """
        cache_key = self._hash_prompt(prompt, model)
        cached = self._cache.get(f"response:{cache_key}")
        
        if cached:
            # Update hit count
            cached.hit_count += 1
            self._cache.set(f"response:{cache_key}", cached)
            logger.debug(f"Cache hit for prompt hash {cache_key}")
            return cached
        
        return None
    
    def set(
        self,
        prompt: str,
        model: str,
        response: str,
        tokens: int = 0,
        ttl: int = None
    ):
        """
        Cache a prompt response.
        
        Args:
            prompt: The prompt text
            model: Model name
            response: Response text
            tokens: Tokens used
            ttl: Optional TTL override
        """
        cache_key = self._hash_prompt(prompt, model)
        
        cached = CachedResponse(
            prompt_hash=cache_key,
            model=model,
            response=response,
            tokens_used=tokens,
            cached_at=datetime.now(timezone.utc)
        )
        
        self._cache.set(f"response:{cache_key}", cached, ttl=ttl)
        logger.debug(f"Cached response for prompt hash {cache_key}")
        
        # Persist if configured
        if self._persistent_path:
            self._save_persistent()
    
    def invalidate(self, prompt: str, model: str):
        """Invalidate cached response"""
        cache_key = self._hash_prompt(prompt, model)
        self._cache.delete(f"response:{cache_key}")
    
    def clear(self):
        """Clear all cached responses"""
        self._cache.clear()
        
        if self._persistent_path and self._persistent_path.exists():
            self._persistent_path.unlink()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self._cache.stats()
    
    def _load_persistent(self):
        """Load cache from persistent storage"""
        if not self._persistent_path or not self._persistent_path.exists():
            return
        
        try:
            with open(self._persistent_path) as f:
                data = json.load(f)
            
            for item in data.get("items", []):
                cached = CachedResponse(
                    prompt_hash=item["prompt_hash"],
                    model=item["model"],
                    response=item["response"],
                    tokens_used=item["tokens_used"],
                    cached_at=datetime.fromisoformat(item["cached_at"]),
                    hit_count=item.get("hit_count", 0)
                )
                self._cache.set(f"response:{cached.prompt_hash}", cached)
            
            logger.info(f"Loaded {len(data.get('items', []))} items from persistent cache")
        except Exception as e:
            logger.warning(f"Failed to load persistent cache: {e}")
    
    def _save_persistent(self):
        """Save cache to persistent storage"""
        if not self._persistent_path:
            return
        
        try:
            # Get all cached items (simplified - would need iteration in real impl)
            items = []
            # Note: This is a simplified version - real impl would iterate cache
            
            self._persistent_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persistent_path, 'w') as f:
                json.dump({"items": items}, f)
        except Exception as e:
            logger.warning(f"Failed to save persistent cache: {e}")


# Global instance
_prompt_cache: Optional[PromptCache] = None


def get_prompt_cache() -> PromptCache:
    """Get or create global prompt cache"""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = PromptCache()
    return _prompt_cache
```

---

### P3.5 SSL/TLS Configuration

**File**: `src/startd8/ssl_config.py`  
**Effort**: 4 hours

```python
# src/startd8/ssl_config.py
"""
SSL/TLS Configuration for secure connections.
"""

import ssl
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class SSLConfig:
    """
    SSL/TLS configuration with security best practices.
    
    Features:
    - TLS 1.2+ enforcement
    - Certificate verification
    - Custom CA support
    """
    
    # Minimum TLS version
    MIN_TLS_VERSION = ssl.TLSVersion.TLSv1_2
    
    @classmethod
    def create_ssl_context(
        cls,
        verify: bool = True,
        ca_bundle: str = None
    ) -> ssl.SSLContext:
        """
        Create secure SSL context.
        
        Args:
            verify: Whether to verify certificates
            ca_bundle: Optional custom CA bundle path
            
        Returns:
            Configured SSLContext
        """
        # Block attempts to disable SSL verification
        if not verify:
            if os.getenv("STARTD8_ALLOW_INSECURE"):
                logger.warning("SSL verification disabled - NOT RECOMMENDED")
            else:
                raise SecurityError(
                    "SSL verification cannot be disabled. "
                    "Set STARTD8_ALLOW_INSECURE=1 to override (not recommended)."
                )
        
        # Create context with secure defaults
        context = ssl.create_default_context()
        
        # Set minimum TLS version
        context.minimum_version = cls.MIN_TLS_VERSION
        
        # Disable insecure protocols and ciphers
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        
        # Set cipher suite (secure ciphers only)
        context.set_ciphers(
            'ECDHE+AESGCM:DHE+AESGCM:ECDHE+CHACHA20:DHE+CHACHA20'
        )
        
        # Load custom CA if provided
        if ca_bundle:
            context.load_verify_locations(ca_bundle)
        
        # Require certificate verification
        if verify:
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
        else:
            context.verify_mode = ssl.CERT_NONE
            context.check_hostname = False
        
        return context
    
    @classmethod
    def get_httpx_ssl_context(cls) -> ssl.SSLContext:
        """Get SSL context configured for httpx"""
        return cls.create_ssl_context(verify=True)


class SecurityError(Exception):
    """Security-related error"""
    pass


def validate_ssl_connection(host: str, port: int = 443) -> dict:
    """
    Validate SSL connection to a host.
    
    Args:
        host: Hostname to check
        port: Port number
        
    Returns:
        Dict with connection info
    """
    import socket
    
    context = SSLConfig.create_ssl_context()
    
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                
                return {
                    "valid": True,
                    "version": ssock.version(),
                    "cipher": ssock.cipher(),
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                    "expires": cert.get("notAfter"),
                }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }
```

---

## Phase 4: Performance Optimization (Weeks 7-8)

### P4.1 Response Streaming

**File**: `src/startd8/streaming.py`  
**Effort**: 10 hours

```python
# src/startd8/streaming.py
"""
Response Streaming for real-time output.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A chunk of streamed response"""
    content: str
    index: int
    is_final: bool = False
    metadata: dict = None


@dataclass
class StreamResult:
    """Final result of a streamed response"""
    full_content: str
    total_chunks: int
    total_tokens: int
    time_to_first_chunk_ms: int
    total_time_ms: int


class ResponseStreamer:
    """
    Handle streaming responses from LLM APIs.
    
    Example:
        streamer = ResponseStreamer()
        
        async for chunk in streamer.stream(agent, prompt):
            print(chunk.content, end="", flush=True)
        
        result = streamer.get_result()
        print(f"\\nTotal tokens: {result.total_tokens}")
    """
    
    def __init__(self):
        self._chunks: list = []
        self._start_time: float = 0
        self._first_chunk_time: float = 0
        self._total_tokens: int = 0
    
    async def stream_claude(
        self,
        client,
        model: str,
        prompt: str,
        max_tokens: int = 4096
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream response from Claude API.
        
        Args:
            client: AsyncAnthropic client
            model: Model name
            prompt: Prompt text
            max_tokens: Maximum tokens
            
        Yields:
            StreamChunk for each piece of content
        """
        import time
        
        self._start_time = time.time()
        self._chunks = []
        index = 0
        
        async with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                if index == 0:
                    self._first_chunk_time = time.time()
                
                chunk = StreamChunk(
                    content=text,
                    index=index,
                    is_final=False
                )
                self._chunks.append(chunk)
                index += 1
                
                yield chunk
            
            # Get final message for token counts
            message = await stream.get_final_message()
            self._total_tokens = message.usage.input_tokens + message.usage.output_tokens
        
        # Yield final chunk
        yield StreamChunk(
            content="",
            index=index,
            is_final=True,
            metadata={"total_tokens": self._total_tokens}
        )
    
    async def stream_openai(
        self,
        client,
        model: str,
        prompt: str,
        max_tokens: int = 4096
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream response from OpenAI API.
        
        Args:
            client: AsyncOpenAI client
            model: Model name
            prompt: Prompt text
            max_tokens: Maximum tokens
            
        Yields:
            StreamChunk for each piece of content
        """
        import time
        
        self._start_time = time.time()
        self._chunks = []
        index = 0
        
        stream = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )
        
        async for chunk in stream:
            if index == 0:
                self._first_chunk_time = time.time()
            
            content = chunk.choices[0].delta.content or ""
            
            stream_chunk = StreamChunk(
                content=content,
                index=index,
                is_final=chunk.choices[0].finish_reason is not None
            )
            self._chunks.append(stream_chunk)
            index += 1
            
            yield stream_chunk
    
    def get_result(self) -> StreamResult:
        """Get final streaming result"""
        import time
        
        full_content = "".join(c.content for c in self._chunks)
        end_time = time.time()
        
        return StreamResult(
            full_content=full_content,
            total_chunks=len(self._chunks),
            total_tokens=self._total_tokens,
            time_to_first_chunk_ms=int((self._first_chunk_time - self._start_time) * 1000),
            total_time_ms=int((end_time - self._start_time) * 1000)
        )


async def stream_to_callback(
    streamer: ResponseStreamer,
    provider: str,
    client: Any,
    model: str,
    prompt: str,
    on_chunk: Callable[[str], None],
    on_complete: Callable[[StreamResult], None] = None
):
    """
    Stream response to callbacks.
    
    Args:
        streamer: ResponseStreamer instance
        provider: "anthropic" or "openai"
        client: API client
        model: Model name
        prompt: Prompt text
        on_chunk: Callback for each chunk
        on_complete: Callback when complete
    """
    if provider == "anthropic":
        stream = streamer.stream_claude(client, model, prompt)
    elif provider == "openai":
        stream = streamer.stream_openai(client, model, prompt)
    else:
        raise ValueError(f"Unknown provider: {provider}")
    
    async for chunk in stream:
        if chunk.content:
            on_chunk(chunk.content)
    
    if on_complete:
        result = streamer.get_result()
        on_complete(result)
```

---

### P4.2 Log Rotation

**File**: `src/startd8/log_rotation.py`  
**Effort**: 4 hours

```python
# src/startd8/log_rotation.py
"""
Log Rotation for managing log file sizes.
"""

import logging
import gzip
import shutil
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


class CompressedRotatingFileHandler(RotatingFileHandler):
    """
    Rotating file handler that compresses rotated logs.
    
    Extends RotatingFileHandler to gzip old log files.
    """
    
    def doRollover(self):
        """
        Do a rollover and compress the old file.
        """
        if self.stream:
            self.stream.close()
            self.stream = None
        
        if self.backupCount > 0:
            # Rotate existing backups
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename(f"{self.baseFilename}.{i}.gz")
                dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}.gz")
                if Path(sfn).exists():
                    if Path(dfn).exists():
                        Path(dfn).unlink()
                    Path(sfn).rename(dfn)
            
            # Compress current log
            dfn = self.rotation_filename(f"{self.baseFilename}.1")
            if Path(self.baseFilename).exists():
                shutil.move(self.baseFilename, dfn)
                
                # Compress
                with open(dfn, 'rb') as f_in:
                    with gzip.open(f"{dfn}.gz", 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                Path(dfn).unlink()
        
        if not self.delay:
            self.stream = self._open()


def configure_log_rotation(
    log_dir: Path,
    log_name: str = "startd8.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    compress: bool = True
) -> logging.Handler:
    """
    Configure log rotation.
    
    Args:
        log_dir: Directory for log files
        log_name: Base log file name
        max_bytes: Maximum file size before rotation
        backup_count: Number of backup files to keep
        compress: Whether to compress rotated files
        
    Returns:
        Configured logging handler
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_name
    
    if compress:
        handler = CompressedRotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count
        )
    else:
        handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count
        )
    
    # Set formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    return handler


def setup_application_logging(
    log_dir: Path = None,
    level: int = logging.INFO,
    compress: bool = True,
    console: bool = True
):
    """
    Set up complete application logging with rotation.
    
    Args:
        log_dir: Log directory (default: ~/.startd8/logs)
        level: Logging level
        compress: Compress rotated logs
        console: Also log to console
    """
    from .log_filter import SensitiveDataFilter
    
    if log_dir is None:
        log_dir = Path.home() / ".startd8" / "logs"
    
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    
    # Add sanitization filter
    root.addFilter(SensitiveDataFilter())
    
    # File handler with rotation
    file_handler = configure_log_rotation(
        log_dir=log_dir,
        compress=compress
    )
    file_handler.setLevel(level)
    root.addHandler(file_handler)
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(
            '%(levelname)s - %(message)s'
        ))
        root.addHandler(console_handler)
    
    logging.info(f"Logging configured: {log_dir}")
```

---

### P4.3 Performance Metrics

**File**: `src/startd8/metrics.py`  
**Effort**: 6 hours

```python
# src/startd8/metrics.py
"""
Performance Metrics Collection and Export.
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Collect and export performance metrics.
    
    Supports:
    - Counters
    - Gauges
    - Histograms
    - Prometheus export format
    
    Example:
        metrics = MetricsCollector()
        
        # Count API calls
        metrics.increment("api_calls", labels={"provider": "anthropic"})
        
        # Track latency
        with metrics.timer("api_latency", labels={"provider": "anthropic"}):
            await api_call()
        
        # Export for Prometheus
        print(metrics.prometheus_export())
    """
    
    def __init__(self):
        self._counters: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = threading.RLock()
        self._start_time = time.time()
    
    def _labels_key(self, labels: Dict[str, str]) -> str:
        """Convert labels to cache key"""
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    
    def increment(self, name: str, value: float = 1, labels: Dict[str, str] = None):
        """Increment a counter"""
        with self._lock:
            key = self._labels_key(labels or {})
            self._counters[name][key] += value
    
    def gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge value"""
        with self._lock:
            key = self._labels_key(labels or {})
            self._gauges[name][key] = value
    
    def histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Add value to histogram"""
        with self._lock:
            key = self._labels_key(labels or {})
            self._histograms[name][key].append(value)
    
    def timer(self, name: str, labels: Dict[str, str] = None):
        """Context manager for timing operations"""
        return _TimerContext(self, name, labels)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get all metrics as dictionary"""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    name: {
                        key: {
                            "count": len(values),
                            "sum": sum(values),
                            "min": min(values) if values else 0,
                            "max": max(values) if values else 0,
                            "avg": sum(values) / len(values) if values else 0
                        }
                        for key, values in label_values.items()
                    }
                    for name, label_values in self._histograms.items()
                },
                "uptime_seconds": time.time() - self._start_time
            }
    
    def prometheus_export(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []
        
        with self._lock:
            # Export counters
            for name, label_values in self._counters.items():
                lines.append(f"# TYPE {name} counter")
                for labels, value in label_values.items():
                    label_str = f"{{{labels}}}" if labels else ""
                    lines.append(f"{name}{label_str} {value}")
            
            # Export gauges
            for name, label_values in self._gauges.items():
                lines.append(f"# TYPE {name} gauge")
                for labels, value in label_values.items():
                    label_str = f"{{{labels}}}" if labels else ""
                    lines.append(f"{name}{label_str} {value}")
            
            # Export histograms
            for name, label_values in self._histograms.items():
                lines.append(f"# TYPE {name} histogram")
                for labels, values in label_values.items():
                    label_str = f"{{{labels}}}" if labels else ""
                    if values:
                        lines.append(f"{name}_count{label_str} {len(values)}")
                        lines.append(f"{name}_sum{label_str} {sum(values)}")
        
        return "\n".join(lines)
    
    def reset(self):
        """Reset all metrics"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


class _TimerContext:
    """Context manager for timing"""
    
    def __init__(self, collector: MetricsCollector, name: str, labels: Dict[str, str]):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start_time = 0
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.collector.histogram(self.name, duration * 1000, self.labels)  # ms


# Global instance
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get or create global metrics collector"""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
```

---

## Integration Summary

### New Files Created
| Phase | File | Purpose |
|-------|------|---------|
| 3 | `health_check.py` | System health monitoring |
| 3 | `error_messages.py` | Standardized errors |
| 3 | `batch_handler.py` | Batch processing |
| 3 | `prompt_cache.py` | Response caching |
| 3 | `ssl_config.py` | TLS security |
| 4 | `streaming.py` | Response streaming |
| 4 | `log_rotation.py` | Log management |
| 4 | `metrics.py` | Performance metrics |

### Testing Checklist
- [ ] Health check returns accurate status
- [ ] Error messages are user-friendly
- [ ] Batch processing handles failures gracefully
- [ ] Cache reduces duplicate API calls
- [ ] TLS 1.2+ enforced
- [ ] Streaming reduces time-to-first-token
- [ ] Logs rotate correctly
- [ ] Metrics exportable to Prometheus

---

## Final Integration

After completing all phases:

1. **Update `__init__.py`** to export new modules
2. **Update documentation** with security features
3. **Run full test suite**
4. **Performance benchmarking**
5. **Security audit**
6. **Release to production**

---

**Total Project Completion**: 160 hours over 8 weeks

**Expected Outcomes**:
- 95% Security Score
- 95% Robustness Score  
- 95% Performance Score
- Enterprise-ready deployment
