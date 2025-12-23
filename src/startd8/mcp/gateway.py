"""
MCP Gateway - Centralized MCP communication layer.

This module provides the MCPGateway class which manages all communication
with the MCP server, including connection pooling, rate limiting, and
circuit breaking.
"""

import asyncio
import os
import time
import hashlib
import hmac
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from .types import (
    MCPGatewayConfig,
    SkillExecutionResult,
    CircuitBreakerConfig,
    RateLimiterConfig,
    CacheConfig,
)
from .circuit_breaker import CircuitBreaker, CircuitState
from .rate_limiter import TokenBucketRateLimiter
from .cache import ResponseCache
from .registry import SkillRegistry, SkillMetadata
from ..logging_config import get_logger
from ..models import TokenUsage

# Conditional imports
try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None
    _ANTHROPIC_AVAILABLE = False

# Optional: Prometheus metrics exporter
try:
    from prometheus_client import start_http_server
    _PROM_AVAILABLE = True
except ImportError:
    start_http_server = None
    _PROM_AVAILABLE = False

# Optional: OpenTelemetry traces exporter
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _OTEL_AVAILABLE = True
except ImportError:
    trace = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    OTLPSpanExporter = None
    _OTEL_AVAILABLE = False

logger = get_logger(__name__)


class GatewayError(RuntimeError):
    """Base exception for MCP Gateway failures."""


class GatewayCircuitOpenError(GatewayError):
    """Raised when the global or per-skill circuit breaker is open."""


class GatewayRateLimitExceededError(GatewayError):
    """Raised when rate limiting blocks execution."""


class AuditLogger:
    """
    Audit logger for skill executions.
    
    Provides immutable audit trail for compliance and forensics.
    """
    
    def __init__(self, enabled: bool = True, log_responses: bool = False):
        """
        Initialize audit logger.
        
        Args:
            enabled: Whether audit logging is enabled
            log_responses: Whether to log full response content (privacy-sensitive)
        """
        self.enabled = enabled
        self.log_responses = log_responses
        self._logger = get_logger("startd8.audit")
    
    def log_request(
        self,
        skill_id: str,
        prompt: str,
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> None:
        """Log skill execution request."""
        if not self.enabled:
            return
        
        self._logger.info(
            "SKILL_REQUEST",
            extra={
                'audit_type': 'skill_request',
                'skill_id': skill_id,
                'prompt_length': len(prompt),
                'prompt_hash': hashlib.sha256(prompt.encode()).hexdigest()[:16],
                'tenant_id': tenant_id,
                'request_id': request_id,
                'timestamp': time.time()
            }
        )
    
    def log_response(
        self,
        skill_id: str,
        result: Optional[SkillExecutionResult],
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """Log skill execution response."""
        if not self.enabled:
            return
        
        extra = {
            'audit_type': 'skill_response',
            'skill_id': skill_id,
            'execution_time_ms': result.execution_time_ms if result else 0,
            'token_input': result.token_usage.input if result else 0,
            'token_output': result.token_usage.output if result else 0,
            'cache_hit': result.cache_hit if result else False,
            'tenant_id': tenant_id,
            'request_id': request_id,
            'timestamp': time.time(),
            'success': error is None,
            'error': error
        }
        
        if self.log_responses and result:
            extra['response_length'] = len(result.content)
            extra['response_hash'] = hashlib.sha256(
                result.content.encode()
            ).hexdigest()[:16]
        
        self._logger.info("SKILL_RESPONSE", extra=extra)


class MCPGateway:
    """
    Central gateway for MCP communication.
    
    Provides:
    - Connection pooling
    - Rate limiting (global and per-skill)
    - Circuit breaking (per-skill)
    - Response caching
    - Audit logging
    - Skill registry
    
    Example:
        >>> config = MCPGatewayConfig()
        >>> gateway = MCPGateway(config)
        >>> await gateway.initialize()
        >>> 
        >>> result = await gateway.execute_skill(
        ...     skill_id="skill-react-game-enhancer",
        ...     prompt="Add a notification system"
        ... )
        >>> print(result.content)
        >>> 
        >>> await gateway.shutdown()
    """
    
    def __init__(self, config: Optional[MCPGatewayConfig] = None):
        """
        Initialize MCP Gateway.
        
        Args:
            config: Gateway configuration. Uses defaults if not provided.
        """
        self.config = config or MCPGatewayConfig()
        
        # Core components
        self._client: Optional[AsyncAnthropic] = None
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._rate_limiters: Dict[str, TokenBucketRateLimiter] = {}
        
        # Sub-components
        self.cache = ResponseCache(self.config.cache)
        self.registry = SkillRegistry()
        self.audit = AuditLogger(
            enabled=self.config.audit_enabled,
            log_responses=self.config.audit_log_responses
        )
        self._connection_semaphore = asyncio.Semaphore(self.config.max_connections)
        
        # Global rate limiter
        self._global_rate_limiter = TokenBucketRateLimiter(
            rate=self.config.rate_limiter.requests_per_second,
            burst_size=self.config.rate_limiter.burst_size
        )
        # Global circuit breaker (two-tier support)
        self._global_circuit = CircuitBreaker(
            skill_id="mcp-global",
            config=self.config.circuit_breaker,
        )
        
        # State
        self._initialized = False
        self._lock = asyncio.Lock()
        self._metrics_started = False
        self._tracer = None
        
        logger.info("MCPGateway created", extra={
            'max_connections': self.config.max_connections,
            'model': self.config.model,
            'cache_enabled': self.config.cache.enabled,
            'audit_enabled': self.config.audit_enabled,
        })
    
    async def initialize(self) -> None:
        """
        Initialize the gateway.
        
        Creates connection pool and discovers available skills.
        Must be called before using the gateway.
        """
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return

            # Validate security prerequisites first for clearer error messages,
            # even when optional SDKs are not installed.
            self._ensure_auth_ready()
            self._ensure_signing_ready()

            # Validate Anthropic auth configuration.
            if not os.getenv("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Required for skill execution via MCP."
                )

            # Allow tests to patch AsyncAnthropic even if the import isn't installed.
            if AsyncAnthropic is None:
                raise RuntimeError(
                    "Anthropic SDK not installed. Install with: pip install anthropic"
                )

            await self._init_observability()
            
            # Create client
            self._client = AsyncAnthropic()
            
            # Discover skills
            await self._discover_skills()
            
            self._initialized = True
            logger.info("MCPGateway initialized")
    
    async def shutdown(self) -> None:
        """
        Shutdown the gateway gracefully.
        
        Closes connections and flushes caches.
        """
        async with self._lock:
            self._initialized = False
            self._client = None
            await self.cache.invalidate()
            logger.info("MCPGateway shutdown complete")
    
    @asynccontextmanager
    async def session(self):
        """
        Context manager for gateway session.
        
        Ensures proper initialization and cleanup.
        
        Example:
            >>> async with gateway.session():
            ...     result = await gateway.execute_skill(...)
        """
        await self.initialize()
        try:
            yield self
        finally:
            await self.shutdown()
    
    async def _discover_skills(self) -> None:
        """Discover available skills from MCP server."""
        # For now, register known skills
        # In production, this would query the MCP server via list_skills tool
        known_skills = [
            SkillMetadata(
                skill_id="skill-react-game-enhancer",
                name="React/TypeScript Game Enhancer",
                description="Enhances React games with new features",
                version="1.0.0",
                capabilities=["messaging", "HUD", "power-ups", "mobile"],
                tags=["game", "react", "typescript"]
            ),
            SkillMetadata(
                skill_id="skill-html_game_dev",
                name="HTML5 Game Designer Pro",
                description="Creates HTML5 Canvas games",
                version="3.0.0",
                capabilities=["canvas", "ECS", "physics", "animation"],
                tags=["game", "html5", "canvas"]
            ),
            SkillMetadata(
                skill_id="skill-code-reviewer",
                name="Code Reviewer",
                description="Reviews code for quality and security",
                version="1.0.0",
                capabilities=["quality", "security", "best-practices"],
                tags=["review", "quality"]
            )
        ]
        
        for skill in known_skills:
            await self.registry.register(skill)
        
        logger.info(f"Discovered {len(known_skills)} skills")
    
    def _get_circuit_breaker(self, skill_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for skill."""
        if skill_id not in self._circuit_breakers:
            self._circuit_breakers[skill_id] = CircuitBreaker(
                skill_id=skill_id,
                config=self.config.circuit_breaker
            )
        return self._circuit_breakers[skill_id]
    
    def _get_rate_limiter(self, skill_id: str) -> TokenBucketRateLimiter:
        """Get or create rate limiter for skill."""
        if skill_id not in self._rate_limiters:
            # Use per-skill limit if configured, otherwise default
            rate = self.config.rate_limiter.per_skill_limits.get(
                skill_id,
                self.config.rate_limiter.requests_per_second
            )
            self._rate_limiters[skill_id] = TokenBucketRateLimiter(
                rate=rate,
                burst_size=self.config.rate_limiter.burst_size
            )
        return self._rate_limiters[skill_id]
    
    async def execute_skill(
        self,
        skill_id: str,
        prompt: str,
        max_tokens: Optional[int] = None,
        timeout_ms: Optional[int] = None,
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None,
        use_cache: bool = True
    ) -> SkillExecutionResult:
        """
        Execute a skill through the gateway.
        
        This method handles:
        1. Cache lookup
        2. Rate limiting (global and per-skill)
        3. Circuit breaker check
        4. MCP execution
        5. Response caching
        6. Audit logging
        
        Args:
            skill_id: The skill to execute
            prompt: The task/prompt for the skill
            max_tokens: Maximum output tokens (default from config)
            timeout_ms: Request timeout in milliseconds
            tenant_id: Optional tenant identifier for multi-tenancy
            request_id: Optional request ID for tracing
            use_cache: Whether to use response cache
            
        Returns:
            SkillExecutionResult with content and metrics
            
        Raises:
            ValueError: If input validation fails
            RuntimeError: If execution fails or is blocked
        """
        # Input validation
        if not skill_id or not isinstance(skill_id, str):
            raise ValueError("skill_id must be a non-empty string")
        if len(skill_id) > 256:
            raise ValueError("skill_id exceeds maximum length (256)")
        
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")
        if len(prompt) > 1_000_000:  # 1MB limit
            raise ValueError("prompt exceeds maximum length (1MB)")
        
        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens < 1 or max_tokens > 1_000_000:
                raise ValueError("max_tokens must be between 1 and 1,000,000")
        
        if timeout_ms is not None:
            if not isinstance(timeout_ms, int) or timeout_ms < 1 or timeout_ms > 300_000:
                raise ValueError("timeout_ms must be between 1 and 300,000ms")
        
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        max_tokens = max_tokens or self.config.default_max_tokens
        timeout_ms = timeout_ms or int(self.config.connection_timeout_seconds * 1000)
        
        # Log request
        self.audit.log_request(
            skill_id=skill_id,
            prompt=prompt,
            tenant_id=tenant_id,
            request_id=request_id
        )
        
        try:
            # Step 1: Check cache
            if use_cache:
                cached = await self.cache.get(skill_id, prompt, tenant_id=tenant_id)
                if cached:
                    cached.cache_hit = True
                    self.audit.log_response(
                        skill_id=skill_id,
                        result=cached,
                        tenant_id=tenant_id,
                        request_id=request_id
                    )
                    return cached
            
            # Step 2: Rate limiting
            await self._global_rate_limiter.acquire()
            await self._get_rate_limiter(skill_id).acquire()
            
            # Step 3: Circuit breakers (global + per-skill)
            await self._global_circuit.check()
            circuit = self._get_circuit_breaker(skill_id)
            await circuit.check()
            
            # Step 4: Execute skill (with connection pooling semaphore)
            async with self._connection_semaphore:
                result = await self._execute_mcp_skill(
                    skill_id=skill_id,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    timeout_ms=timeout_ms
                )
            
            # Step 5: Record success
            await self._global_circuit.record_success()
            await circuit.record_success()
            
            # Step 6: Cache response
            if use_cache:
                await self.cache.set(skill_id, prompt, result, tenant_id=tenant_id)
            
            # Step 7: Log response
            self.audit.log_response(
                skill_id=skill_id,
                result=result,
                tenant_id=tenant_id,
                request_id=request_id
            )
            
            return result
            
        except Exception as e:
            # Record failure
            await self._global_circuit.record_failure()
            circuit = self._get_circuit_breaker(skill_id)
            await circuit.record_failure()
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Log error
            self.audit.log_response(
                skill_id=skill_id,
                result=None,
                tenant_id=tenant_id,
                request_id=request_id,
                error=str(e)
            )
            
            logger.error(
                f"Skill execution failed: {e}",
                extra={
                    'skill_id': skill_id,
                    'execution_time_ms': execution_time_ms,
                    'tenant_id': tenant_id
                },
                exc_info=True
            )
            
            message = f"Failed to execute skill '{skill_id}': {e}"

            if "Circuit breaker" in message:
                raise GatewayCircuitOpenError(message) from e
            if "Rate limit exceeded" in message:
                raise GatewayRateLimitExceededError(message) from e

            raise GatewayError(message) from e

    # --- Security / signing scaffolding ---
    def _ensure_auth_ready(self) -> None:
        """Ensure required auth material is present based on config."""
        auth = self.config.auth
        if auth.require_api_key:
            header = auth.api_key_header or "X-API-Key"
            if not os.getenv("MCP_GATEWAY_API_KEY"):
                raise RuntimeError(
                    f"MCP_GATEWAY_API_KEY not set but {header} required (require_api_key=True)"
                )
        if auth.enable_jwt:
            if not os.getenv("MCP_JWT_SECRET"):
                raise RuntimeError("MCP_JWT_SECRET not set but JWT auth enabled")
        if auth.enable_mtls:
            if not auth.mtls_ca_bundle:
                raise RuntimeError("mtls_ca_bundle must be set when mTLS is enabled")

    def _ensure_signing_ready(self) -> None:
        """Ensure request signing secret is available when enabled."""
        signing = self.config.signing
        if signing.enabled:
            if not os.getenv(signing.secret_env_var):
                raise RuntimeError(
                    f"{signing.secret_env_var} not set but signing is enabled"
                )

    def _sign_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Create HMAC signature for payload when signing is enabled.

        Returns signature string or None if signing is disabled.
        """
        signing = self.config.signing
        if not signing.enabled:
            return None
        secret = os.getenv(signing.secret_env_var)
        if not secret:
            raise RuntimeError(
                f"{signing.secret_env_var} not set but signing is enabled"
            )

        # Deterministic ordering for signing
        serialized = "|".join(
            f"{k}={payload.get(k)}" for k in sorted(payload.keys())
        ).encode("utf-8")
        digest = hmac.new(
            secret.encode("utf-8"),
            serialized,
            hashlib.sha256
        ).hexdigest()
        timestamp = str(int(time.time()))
        # Format: timestamp:signature
        return f"{timestamp}:{digest}"

    # --- Observability scaffolding ---
    async def _init_observability(self) -> None:
        """Initialize metrics and tracing exporters (best-effort, non-fatal)."""
        obs = self.config.observability

        # Metrics (Prometheus)
        if obs.enable_metrics and _PROM_AVAILABLE and not self._metrics_started:
            try:
                start_http_server(obs.metrics_port)
                self._metrics_started = True
                logger.info(
                    "Metrics exporter started",
                    extra={"metrics_path": obs.metrics_path, "metrics_port": obs.metrics_port},
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to start metrics exporter", extra={"error": str(exc)})
        elif obs.enable_metrics and not _PROM_AVAILABLE:
            logger.debug("prometheus_client not installed; metrics exporter not started")

        # Traces (OTLP)
        if obs.enable_traces and _OTEL_AVAILABLE and self._tracer is None:
            try:
                resource = Resource.create(
                    {
                        "service.name": "mcp-gateway",
                        "service.version": os.getenv("VERSION", "1.0.0"),
                        "deployment.environment": os.getenv("ENV", "development"),
                    }
                )
                provider = TracerProvider(resource=resource)
                exporter = OTLPSpanExporter(endpoint=obs.otlp_endpoint)
                processor = BatchSpanProcessor(exporter)
                provider.add_span_processor(processor)
                trace.set_tracer_provider(provider)
                self._tracer = trace.get_tracer(__name__)
                logger.info(
                    "Tracing initialized",
                    extra={
                        "otlp_endpoint": obs.otlp_endpoint,
                        "otlp_protocol": obs.otlp_protocol,
                    },
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to initialize tracing", extra={"error": str(exc)})
        elif obs.enable_traces and not _OTEL_AVAILABLE:
            logger.debug("opentelemetry not installed; tracing not initialized")
    
    async def _execute_mcp_skill(
        self,
        skill_id: str,
        prompt: str,
        max_tokens: int,
        timeout_ms: int
    ) -> SkillExecutionResult:
        """Execute skill via MCP protocol."""
        start_time = time.time()
        
        if not self._client:
            raise RuntimeError("Gateway not initialized")
        
        # Define MCP tool
        tools = [
            {
                "name": "startd8_use_skill",
                "description": "Execute a Claude Skill via startd8 MCP",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "skill_id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "max_tokens": {"type": "integer", "default": 8192}
                    },
                    "required": ["skill_id", "prompt"]
                }
            }
        ]
        
        messages = [
            {
                "role": "user",
                "content": f"Execute the {skill_id} skill with this task:\n\n{prompt}"
            }
        ]
        
        # Call Claude with timeout
        response = await asyncio.wait_for(
            self._client.messages.create(
                model=self.config.model,
                max_tokens=max_tokens,
                tools=tools,
                messages=messages
            ),
            timeout=timeout_ms / 1000
        )
        
        # Extract response
        content = ""
        for block in response.content:
            if hasattr(block, 'text'):
                content = block.text
                break
        
        if not content:
            raise ValueError("No text content found in Claude response")
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Parse metrics from response
        metrics = self._parse_skill_metrics(content)
        
        return SkillExecutionResult(
            content=content,
            metrics=metrics,
            skill_id=skill_id,
            execution_time_ms=execution_time_ms,
            token_usage=TokenUsage(
                input=response.usage.input_tokens,
                output=response.usage.output_tokens,
                total=response.usage.input_tokens + response.usage.output_tokens,
                model_name=self.config.model,
            ),
            cache_hit=False
        )
    
    def _parse_skill_metrics(self, response: str) -> Dict[str, Any]:
        """Parse metrics from skill response."""
        metrics = {}
        
        for line in response.split('\n'):
            if '**Time:**' in line:
                try:
                    time_str = line.split('**Time:**')[1].strip().rstrip('ms')
                    metrics['skill_time_ms'] = int(time_str)
                except (IndexError, ValueError):
                    pass
            elif '**Tokens:**' in line:
                try:
                    tokens_str = line.split('**Tokens:**')[1].strip()
                    in_out = tokens_str.split(',')
                    metrics['skill_input_tokens'] = int(in_out[0].split()[0])
                    metrics['skill_output_tokens'] = int(in_out[1].split()[0])
                except (IndexError, ValueError):
                    pass
        
        return metrics
    
    async def list_skills(self) -> List[Dict[str, Any]]:
        """List all available skills with metadata."""
        skills = await self.registry.list_all()
        return [
            {
                'skill_id': s.skill_id,
                'name': s.name,
                'description': s.description,
                'version': s.version,
                'capabilities': s.capabilities,
                'tags': s.tags
            }
            for s in skills
        ]
    
    async def get_skill_info(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a skill."""
        skill = await self.registry.get(skill_id)
        if not skill:
            return None
        
        circuit = self._get_circuit_breaker(skill_id)
        
        return {
            'skill_id': skill.skill_id,
            'name': skill.name,
            'description': skill.description,
            'version': skill.version,
            'capabilities': skill.capabilities,
            'tags': skill.tags,
            'circuit_state': circuit.state.value,
            'healthy': circuit.state != CircuitState.OPEN
        }
    
    def get_circuit_state(self, skill_id: str) -> str:
        """Get circuit breaker state for a skill."""
        return self._get_circuit_breaker(skill_id).state.value
    
    def get_stats(self) -> Dict[str, Any]:
        """Get gateway statistics."""
        return {
            'initialized': self._initialized,
            'skills_registered': len(self._circuit_breakers),
            'circuit_states': {
                skill_id: cb.state.value
                for skill_id, cb in self._circuit_breakers.items()
            },
            'global_circuit_state': self._global_circuit.state.value,
            'cache_config': {
                'enabled': self.config.cache.enabled,
                'ttl_seconds': self.config.cache.ttl_seconds,
                'max_entries': self.config.cache.max_entries
            },
            'cache_stats': self.cache.get_stats(),
            'rate_limiter_stats': {
                'global': self._global_rate_limiter.get_stats(),
                'per_skill': {
                    skill: limiter.get_stats()
                    for skill, limiter in self._rate_limiters.items()
                },
            },
        }
