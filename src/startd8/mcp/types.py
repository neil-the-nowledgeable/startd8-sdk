"""
Type definitions for MCP Gateway module.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from ..models import TokenUsage


@dataclass
class WorkflowExecutionResult:
    """Result of a workflow execution via MCP Gateway."""
    workflow_id: str
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time_ms: int = 0
    total_cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    steps: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MCP response."""
        return {
            'workflow_id': self.workflow_id,
            'success': self.success,
            'output': self.output,
            'error': self.error,
            'execution_time_ms': self.execution_time_ms,
            'total_cost': self.total_cost,
            'token_usage': {
                'input': self.input_tokens,
                'output': self.output_tokens,
                'total': self.input_tokens + self.output_tokens
            },
            'steps': self.steps,
            'metadata': self.metadata
        }

    @classmethod
    def from_workflow_result(cls, result: 'WorkflowResult') -> 'WorkflowExecutionResult':
        """Create from a WorkflowResult object."""
        return cls(
            workflow_id=result.workflow_id,
            success=result.success,
            output=result.output,
            error=result.error,
            execution_time_ms=result.metrics.total_time_ms if result.metrics else 0,
            total_cost=result.metrics.total_cost if result.metrics else 0.0,
            input_tokens=result.metrics.input_tokens if result.metrics else 0,
            output_tokens=result.metrics.output_tokens if result.metrics else 0,
            steps=[s.to_dict() for s in result.steps] if result.steps else [],
            metadata=result.metadata or {}
        )


@dataclass
class SkillExecutionResult:
    """Result of a skill execution."""
    content: str
    metrics: Dict[str, Any]
    skill_id: str
    execution_time_ms: int
    token_usage: TokenUsage
    cache_hit: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'content': self.content,
            'metrics': self.metrics,
            'skill_id': self.skill_id,
            'execution_time_ms': self.execution_time_ms,
            'token_usage': {
                'input': self.token_usage.input,
                'output': self.token_usage.output,
                'total': self.token_usage.total
            },
            'cache_hit': self.cache_hit
        }


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_requests: int = 3
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be > 0")
        if self.half_open_max_requests < 1:
            raise ValueError("half_open_max_requests must be >= 1")


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiting."""
    requests_per_second: float = 10.0
    burst_size: int = 20
    per_skill_limits: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        if self.burst_size < 1:
            raise ValueError("burst_size must be >= 1")
        for skill_id, rate in self.per_skill_limits.items():
            if rate <= 0:
                raise ValueError(f"per_skill_limits[{skill_id}] must be > 0")


@dataclass
class CacheConfig:
    """Configuration for response caching."""
    enabled: bool = True
    ttl_seconds: int = 300  # 5 minutes
    max_entries: int = 1000
    max_entry_size_bytes: int = 1_000_000  # 1MB
    isolate_by_tenant: bool = False  # Phase 3: tenant-isolated cache keys
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        if self.max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if self.max_entry_size_bytes < 1:
            raise ValueError("max_entry_size_bytes must be >= 1")


@dataclass
class AuthConfig:
    """Authentication and authorization toggles."""
    require_api_key: bool = False  # Phase 3: scaffolding, not enforced yet
    api_key_header: str = "X-API-Key"
    enable_jwt: bool = False
    jwt_issuer: str = "startd8-mcp-gateway"
    jwt_audience: str = "mcp-skills"
    jwt_clock_skew_seconds: int = 60
    enable_mtls: bool = False
    mtls_ca_bundle: Optional[str] = None
    mtls_client_cert: Optional[str] = None
    mtls_client_key: Optional[str] = None
    
    def __post_init__(self):
        if self.jwt_clock_skew_seconds < 0:
            raise ValueError("jwt_clock_skew_seconds must be >= 0")


@dataclass
class RequestSigningConfig:
    """Request signing controls (HMAC Phase 3 scaffolding)."""
    enabled: bool = False
    header_name: str = "X-Signature"
    secret_env_var: str = "MCP_SIGNING_KEY"
    timestamp_tolerance_seconds: int = 300  # ±5 minutes
    
    def __post_init__(self):
        if self.timestamp_tolerance_seconds < 0:
            raise ValueError("timestamp_tolerance_seconds must be >= 0")


@dataclass
class ObservabilityConfig:
    """
    Observability endpoints and flags with ContextCore project support.
    
    ContextCore project context (project_id, task_id, sprint_id) can be
    included as OTel resource attributes for unified observability.
    """
    # Metrics
    enable_metrics: bool = True
    metrics_path: str = "/metrics"
    metrics_port: int = 9090
    
    # Traces
    enable_traces: bool = True
    otlp_endpoint: str = "http://otel-collector:4317"
    otlp_protocol: str = "grpc"  # grpc or http/protobuf
    otlp_cert_file: Optional[str] = None
    otlp_client_cert: Optional[str] = None
    otlp_client_key: Optional[str] = None
    
    # ContextCore project context (included in OTel resource attributes)
    project_id: Optional[str] = None           # io.contextcore.project.id
    project_name: Optional[str] = None         # io.contextcore.project.name
    task_id: Optional[str] = None              # io.contextcore.task.id
    sprint_id: Optional[str] = None            # io.contextcore.sprint.id
    
    def __post_init__(self):
        if self.metrics_port <= 0 or self.metrics_port > 65535:
            raise ValueError("metrics_port must be between 1 and 65535")
        if self.otlp_protocol not in ("grpc", "http"):
            raise ValueError("otlp_protocol must be 'grpc' or 'http'")
    
    def get_contextcore_attributes(self) -> Dict[str, str]:
        """Get ContextCore attributes for OTel resource."""
        attrs = {}
        if self.project_id:
            attrs["io.contextcore.project.id"] = self.project_id
        if self.project_name:
            attrs["io.contextcore.project.name"] = self.project_name
        if self.task_id:
            attrs["io.contextcore.task.id"] = self.task_id
        if self.sprint_id:
            attrs["io.contextcore.sprint.id"] = self.sprint_id
        return attrs


@dataclass
class MCPGatewayConfig:
    """Configuration for the MCP Gateway."""
    
    # Connection pool settings
    max_connections: int = 10
    connection_timeout_seconds: float = 30.0
    idle_timeout_seconds: float = 60.0
    
    # MCP server settings
    model: str = "claude-sonnet-4-20250514"
    default_max_tokens: int = 8192
    
    # Sub-component configs
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    rate_limiter: RateLimiterConfig = field(default_factory=RateLimiterConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    
    # Audit settings
    audit_enabled: bool = True
    audit_log_responses: bool = False  # Set to True for full audit
    
    # Security / auth
    auth: AuthConfig = field(default_factory=AuthConfig)
    signing: RequestSigningConfig = field(default_factory=RequestSigningConfig)
    
    # Observability
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.max_connections < 1:
            raise ValueError("max_connections must be >= 1")
        if self.connection_timeout_seconds <= 0:
            raise ValueError("connection_timeout_seconds must be > 0")
        if self.idle_timeout_seconds <= 0:
            raise ValueError("idle_timeout_seconds must be > 0")
        if self.default_max_tokens < 1:
            raise ValueError("default_max_tokens must be >= 1")
