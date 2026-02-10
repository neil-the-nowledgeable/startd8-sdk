"""
Session tracking for monitoring active sessions and context capacity.

Provides framework-level tracking of:
- Active session count
- Context window usage per session
- Token consumption metrics
- Response times and costs
- Truncation events

Exports metrics via OpenTelemetry (preferred) or Prometheus (legacy).

OpenTelemetry Integration:
    The SessionTracker uses OpenTelemetry metrics by default, enabling
    export to any OTel-compatible backend (Prometheus, Mimir, OTLP, etc.).

    Metrics exported:
    - startd8_active_sessions: Number of active sessions (up/down counter)
    - startd8_requests_total: Total API requests (counter)
    - startd8_tokens_total: Total tokens processed (counter)
    - startd8_response_time_ms: Response time distribution (histogram)
    - startd8_context_usage_ratio: Context window usage 0-1 (observable gauge)
    - startd8_truncations_total: Truncation events (counter)
    - startd8_cost_total: Total cost in USD (counter)
"""

import time
import uuid
import threading
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Generator
from enum import Enum

logger = logging.getLogger(__name__)

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime cost.
_OTEL_DESCRIPTORS = {
    "metrics": [
        {
            "name": "startd8_active_sessions",
            "instrument": "up_down_counter",
            "unit": "sessions",
            "description": "Number of active sessions",
            "meter": "startd8",
            "labels": ["agent_name", "model", "project_id"],
        },
        {
            "name": "startd8_requests_total",
            "instrument": "counter",
            "unit": "requests",
            "description": "Total number of requests",
            "meter": "startd8",
            "labels": ["agent_name", "model", "project_id", "status"],
        },
        {
            "name": "startd8_tokens_total",
            "instrument": "counter",
            "unit": "tokens",
            "description": "Total tokens processed",
            "meter": "startd8",
            "labels": ["agent_name", "model", "project_id", "direction"],
        },
        {
            "name": "startd8_response_time_ms",
            "instrument": "histogram",
            "unit": "ms",
            "description": "Response time in milliseconds",
            "meter": "startd8",
            "labels": ["agent_name", "model", "project_id"],
        },
        {
            "name": "startd8_context_usage_ratio",
            "instrument": "observable_gauge",
            "unit": "ratio",
            "description": "Context window usage ratio (0-1)",
            "meter": "startd8",
            "labels": ["session_id", "agent_name", "model", "project_id"],
        },
        {
            "name": "startd8_truncations_total",
            "instrument": "counter",
            "unit": "events",
            "description": "Total truncation events",
            "meter": "startd8",
            "labels": ["agent_name", "model", "project_id"],
        },
        {
            "name": "startd8_cost_total",
            "instrument": "counter",
            "unit": "USD",
            "description": "Total cost in USD",
            "meter": "startd8",
            "labels": ["agent_name", "model", "project_id"],
        },
    ],
}

# Lazy-load OpenTelemetry to avoid hard dependency
_otel_metrics = None

def _get_otel_metrics():
    """Get OpenTelemetry metrics module if available."""
    global _otel_metrics
    if _otel_metrics is None:
        try:
            from opentelemetry import metrics as otel_m
            _otel_metrics = otel_m
        except ImportError:
            _otel_metrics = False  # Mark as unavailable
    return _otel_metrics if _otel_metrics else None


class SessionState(Enum):
    """Session lifecycle states"""
    ACTIVE = "active"
    IDLE = "idle"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ContextUsage:
    """Tracks context window usage for a session"""
    model: str
    context_window: int  # Total context window size
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used in context"""
        return self.input_tokens + self.output_tokens

    @property
    def capacity_used(self) -> float:
        """Percentage of context window used (0.0 - 1.0)"""
        if self.context_window == 0:
            return 0.0
        return min(1.0, self.total_tokens / self.context_window)

    @property
    def capacity_remaining(self) -> int:
        """Tokens remaining in context window"""
        return max(0, self.context_window - self.total_tokens)

    @property
    def is_near_capacity(self) -> bool:
        """True if context usage exceeds 80%"""
        return self.capacity_used >= 0.8


@dataclass
class SessionMetrics:
    """Full telemetry for a session"""
    session_id: str
    created_at: datetime
    state: SessionState = SessionState.ACTIVE

    # Context tracking
    context_usage: Optional[ContextUsage] = None

    # Request counts
    request_count: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Token totals (cumulative across all requests)
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Timing
    total_response_time_ms: int = 0
    last_activity: Optional[datetime] = None

    # Cost tracking
    total_cost: float = 0.0

    # Truncation events
    truncation_count: int = 0

    # Metadata
    agent_name: Optional[str] = None
    model: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ContextCore project metadata fields
    project_id: Optional[str] = None           # io.contextcore.project.id
    project_name: Optional[str] = None         # io.contextcore.project.name
    task_id: Optional[str] = None              # io.contextcore.task.id
    sprint_id: Optional[str] = None            # io.contextcore.sprint.id
    business_criticality: Optional[str] = None # io.contextcore.business.criticality

    @property
    def average_response_time_ms(self) -> float:
        """Average response time in milliseconds"""
        if self.request_count == 0:
            return 0.0
        return self.total_response_time_ms / self.request_count

    @property
    def success_rate(self) -> float:
        """Success rate as percentage (0.0 - 1.0)"""
        if self.request_count == 0:
            return 0.0
        return self.successful_requests / self.request_count

    @property
    def tokens_per_request(self) -> float:
        """Average tokens per request"""
        if self.request_count == 0:
            return 0.0
        return (self.total_input_tokens + self.total_output_tokens) / self.request_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "state": self.state.value,
            "context_usage": {
                "model": self.context_usage.model,
                "context_window": self.context_usage.context_window,
                "input_tokens": self.context_usage.input_tokens,
                "output_tokens": self.context_usage.output_tokens,
                "capacity_used": self.context_usage.capacity_used,
                "capacity_remaining": self.context_usage.capacity_remaining,
            } if self.context_usage else None,
            "request_count": self.request_count,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_response_time_ms": self.total_response_time_ms,
            "average_response_time_ms": self.average_response_time_ms,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "total_cost": self.total_cost,
            "truncation_count": self.truncation_count,
            "success_rate": self.success_rate,
            "agent_name": self.agent_name,
            "model": self.model,
            "tags": self.tags,
            # ContextCore project metadata
            "project_id": self.project_id,
            "project_name": self.project_name,
            "task_id": self.task_id,
            "sprint_id": self.sprint_id,
            "business_criticality": self.business_criticality,
        }


class SessionTracker:
    """
    Thread-safe session tracker with Prometheus metrics export.

    Usage:
        tracker = SessionTracker()

        # Start a session
        session_id = tracker.start_session(agent_name="claude", model="claude-sonnet-4-20250514")

        # Record activity
        tracker.record_request(session_id, input_tokens=100, output_tokens=500,
                               response_time_ms=1234, cost=0.01)

        # Check capacity
        metrics = tracker.get_session(session_id)
        print(f"Context usage: {metrics.context_usage.capacity_used:.1%}")

        # End session
        tracker.end_session(session_id)

        # Get summary
        summary = tracker.get_summary()
        print(f"Active sessions: {summary['active_sessions']}")
    """

    # Default context windows by provider (fallback if model info unavailable)
    DEFAULT_CONTEXT_WINDOWS = {
        "anthropic": 200000,
        "openai": 128000,
        "gemini": 1000000,
        "ollama": 32000,
        "mock": 100000,
    }

    def __init__(
        self,
        prometheus_port: Optional[int] = None,
        enable_otel: bool = True,
        otel_service_name: str = "startd8",
    ):
        """
        Initialize session tracker.

        Args:
            prometheus_port: Port for Prometheus metrics server (legacy, deprecated)
            enable_otel: Whether to enable OpenTelemetry metrics (default: True)
            otel_service_name: Service name for OTel metrics (default: "startd8")
        """
        self._sessions: Dict[str, SessionMetrics] = {}
        self._lock = threading.RLock()
        self._otel_enabled = False
        self._otel_service_name = otel_service_name

        # OpenTelemetry metrics (initialized lazily)
        self._otel_meter = None
        self._otel_active_sessions = None
        self._otel_requests_counter = None
        self._otel_tokens_counter = None
        self._otel_response_time = None
        self._otel_context_usage = None
        self._otel_truncations = None
        self._otel_cost_counter = None

        # Track active session counts for gauge updates
        self._active_session_counts: Dict[str, int] = {}

        # Legacy prometheus support (deprecated)
        self._prometheus_port = prometheus_port
        self._prom_active_sessions = None
        self._prom_total_requests = None
        self._prom_total_tokens = None
        self._prom_response_time = None
        self._prom_context_usage = None
        self._prom_truncations = None
        self._prom_total_cost = None

        # Initialize OTel first (preferred)
        if enable_otel:
            self._init_otel_metrics()

        # Fall back to prometheus if OTel not available and port specified
        if prometheus_port and not self._otel_enabled:
            self._init_prometheus(prometheus_port)

    def _init_otel_metrics(self) -> None:
        """Initialize OpenTelemetry metrics."""
        try:
            from opentelemetry import metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.resources import Resource

            # Get or create meter
            self._otel_meter = metrics.get_meter(
                self._otel_service_name,
                version="0.4.0",
            )

            # Create metrics using OTel SDK

            # Active sessions (using UpDownCounter for gauge-like behavior)
            self._otel_active_sessions = self._otel_meter.create_up_down_counter(
                name="startd8_active_sessions",
                description="Number of active sessions",
                unit="sessions",
            )

            # Total requests counter
            self._otel_requests_counter = self._otel_meter.create_counter(
                name="startd8_requests_total",
                description="Total number of requests",
                unit="requests",
            )

            # Total tokens counter
            self._otel_tokens_counter = self._otel_meter.create_counter(
                name="startd8_tokens_total",
                description="Total tokens processed",
                unit="tokens",
            )

            # Response time histogram
            self._otel_response_time = self._otel_meter.create_histogram(
                name="startd8_response_time_ms",
                description="Response time in milliseconds",
                unit="ms",
            )

            # Context usage gauge (using observable gauge with callback)
            # We'll update this via the callback pattern
            self._otel_context_usage = self._otel_meter.create_observable_gauge(
                name="startd8_context_usage_ratio",
                description="Context window usage ratio (0-1)",
                unit="ratio",
                callbacks=[self._observe_context_usage],
            )

            # Truncation counter
            self._otel_truncations = self._otel_meter.create_counter(
                name="startd8_truncations_total",
                description="Total truncation events",
                unit="events",
            )

            # Cost counter
            self._otel_cost_counter = self._otel_meter.create_counter(
                name="startd8_cost_total",
                description="Total cost in USD",
                unit="USD",
            )

            self._otel_enabled = True
            logger.info("OpenTelemetry metrics initialized for session tracking")

        except ImportError:
            logger.debug(
                "OpenTelemetry not installed. Install with: pip install opentelemetry-api opentelemetry-sdk"
            )
            self._otel_enabled = False
        except Exception as e:
            logger.warning(f"Failed to initialize OpenTelemetry metrics: {e}")
            self._otel_enabled = False

    def _observe_context_usage(self, options) -> Generator:
        """Callback for observable gauge - yields current context usage values."""
        otel = _get_otel_metrics()
        if not otel:
            return

        from opentelemetry.metrics import Observation

        with self._lock:
            for session in self._sessions.values():
                if session.state == SessionState.ACTIVE and session.context_usage:
                    yield Observation(
                        session.context_usage.capacity_used,
                        attributes={
                            "session_id": session.session_id,
                            "agent_name": session.agent_name or "unknown",
                            "model": session.model or "unknown",
                            "project_id": session.project_id or "",
                        }
                    )

    def _init_prometheus(self, port: int) -> None:
        """Initialize Prometheus metrics and start HTTP server (legacy/deprecated)."""
        logger.warning(
            "prometheus_client is deprecated. Migrate to OpenTelemetry: "
            "pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-prometheus"
        )
        try:
            from prometheus_client import (
                Gauge, Counter, Histogram, start_http_server,
                REGISTRY, CollectorRegistry
            )

            # Create metrics
            self._prom_active_sessions = Gauge(
                'startd8_active_sessions',
                'Number of active sessions',
                ['agent_name', 'model']
            )

            self._prom_total_requests = Counter(
                'startd8_requests_total',
                'Total number of requests',
                ['agent_name', 'model', 'status']
            )

            self._prom_total_tokens = Counter(
                'startd8_tokens_total',
                'Total tokens processed',
                ['agent_name', 'model', 'direction']  # direction: input/output
            )

            self._prom_response_time = Histogram(
                'startd8_response_time_ms',
                'Response time in milliseconds',
                ['agent_name', 'model'],
                buckets=[100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000]
            )

            self._prom_context_usage = Gauge(
                'startd8_context_usage_ratio',
                'Context window usage ratio (0-1)',
                ['session_id', 'agent_name', 'model']
            )

            self._prom_truncations = Counter(
                'startd8_truncations_total',
                'Total truncation events',
                ['agent_name', 'model']
            )

            self._prom_total_cost = Counter(
                'startd8_cost_total',
                'Total cost in USD',
                ['agent_name', 'model']
            )

            # Start metrics server
            start_http_server(port)
            logger.info(f"Prometheus metrics server started on port {port}")

        except ImportError:
            logger.warning(
                "prometheus_client not installed. Install with: pip install prometheus-client"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Prometheus metrics: {e}")

    def _get_context_window(self, model: str, agent_name: Optional[str] = None) -> int:
        """Get context window size for a model"""
        # Try to get from provider registry
        try:
            from .providers import ProviderRegistry
            ProviderRegistry.discover()

            # Determine provider from agent name or model
            provider_name = None
            if agent_name:
                if "claude" in agent_name.lower():
                    provider_name = "anthropic"
                elif "gpt" in agent_name.lower() or "openai" in agent_name.lower():
                    provider_name = "openai"
                elif "gemini" in agent_name.lower():
                    provider_name = "gemini"

            if provider_name:
                provider = ProviderRegistry.get_provider(provider_name)
                if hasattr(provider, 'MODEL_INFO') and model in provider.MODEL_INFO:
                    return provider.MODEL_INFO[model].get('context_window',
                           self.DEFAULT_CONTEXT_WINDOWS.get(provider_name, 100000))
        except Exception:
            pass

        # Fallback to defaults based on model name
        model_lower = model.lower()
        if "claude" in model_lower:
            return self.DEFAULT_CONTEXT_WINDOWS["anthropic"]
        elif "gpt" in model_lower or "o3" in model_lower or "o4" in model_lower:
            return self.DEFAULT_CONTEXT_WINDOWS["openai"]
        elif "gemini" in model_lower:
            return self.DEFAULT_CONTEXT_WINDOWS["gemini"]
        elif "llama" in model_lower or "mistral" in model_lower:
            return self.DEFAULT_CONTEXT_WINDOWS["ollama"]

        return 100000  # Safe default

    def start_session(
        self,
        agent_name: Optional[str] = None,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        # ContextCore project context parameters
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        task_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
    ) -> str:
        """
        Start a new session with optional ContextCore project context.

        Args:
            agent_name: Name of the agent
            model: Model being used
            tags: Optional tags for filtering
            metadata: Additional metadata
            session_id: Optional custom session ID (auto-generated if not provided)
            project_id: ContextCore project identifier (io.contextcore.project.id)
            project_name: Human-readable project name (io.contextcore.project.name)
            task_id: ContextCore task identifier (io.contextcore.task.id)
            sprint_id: ContextCore sprint identifier (io.contextcore.sprint.id)

        Returns:
            Session ID
        """
        if session_id is None:
            session_id = f"session-{uuid.uuid4().hex[:12]}"

        context_window = self._get_context_window(model or "", agent_name)

        with self._lock:
            metrics = SessionMetrics(
                session_id=session_id,
                created_at=datetime.now(timezone.utc),
                state=SessionState.ACTIVE,
                context_usage=ContextUsage(
                    model=model or "unknown",
                    context_window=context_window,
                ),
                agent_name=agent_name,
                model=model,
                tags=tags or [],
                metadata=metadata or {},
                # ContextCore project context
                project_id=project_id,
                project_name=project_name,
                task_id=task_id,
                sprint_id=sprint_id,
                business_criticality=self._derive_business_criticality(project_id, project_name),
            )
            self._sessions[session_id] = metrics

            # Update metrics
            attrs = {
                "agent_name": agent_name or "unknown",
                "model": model or "unknown",
                "project_id": project_id or "",
            }

            # OpenTelemetry metrics (preferred)
            if self._otel_enabled and self._otel_active_sessions:
                self._otel_active_sessions.add(1, attrs)

            # Legacy Prometheus metrics
            if self._prom_active_sessions:
                self._prom_active_sessions.labels(
                    agent_name=agent_name or "unknown",
                    model=model or "unknown"
                ).inc()

            logger.debug(
                f"Started session {session_id}",
                extra={
                    "session_id": session_id,
                    "agent_name": agent_name,
                    "model": model,
                    "context_window": context_window,
                }
            )

        return session_id

    def set_project_context(
        self,
        session_id: str,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        task_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
    ) -> None:
        """
        Update ContextCore project context for an existing session.

        Args:
            session_id: Session to update
            project_id: ContextCore project identifier (io.contextcore.project.id)
            project_name: Human-readable project name (io.contextcore.project.name)
            task_id: ContextCore task identifier (io.contextcore.task.id)
            sprint_id: ContextCore sprint identifier (io.contextcore.sprint.id)

        Raises:
            KeyError: If session_id does not exist
        """
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"Session '{session_id}' not found")

            metrics = self._sessions[session_id]

            # Update provided fields (only if explicitly passed)
            if project_id is not None:
                metrics.project_id = project_id
            if project_name is not None:
                metrics.project_name = project_name
            if task_id is not None:
                metrics.task_id = task_id
            if sprint_id is not None:
                metrics.sprint_id = sprint_id

            # Re-derive business criticality if project context changed
            if project_id is not None or project_name is not None:
                metrics.business_criticality = self._derive_business_criticality(
                    metrics.project_id, metrics.project_name
                )

            logger.debug(
                f"Updated project context for session {session_id}",
                extra={
                    "session_id": session_id,
                    "project_id": metrics.project_id,
                    "task_id": metrics.task_id,
                    "sprint_id": metrics.sprint_id,
                }
            )

    def _derive_business_criticality(
        self,
        project_id: Optional[str],
        project_name: Optional[str]
    ) -> Optional[str]:
        """
        Derive business criticality from project context.

        This uses heuristics based on project naming conventions.
        Can be extended with external project metadata lookups.

        Args:
            project_id: Project identifier
            project_name: Project name

        Returns:
            Business criticality level ('low', 'medium', 'high', 'critical') or None
        """
        if not project_id and not project_name:
            return None

        # Check project name for keywords
        name_to_check = (project_name or project_id or "").lower()

        if any(kw in name_to_check for kw in ['prod', 'production', 'critical', 'live']):
            return 'critical'
        elif any(kw in name_to_check for kw in ['staging', 'pre-prod', 'preprod']):
            return 'high'
        elif any(kw in name_to_check for kw in ['test', 'qa', 'dev', 'development']):
            return 'medium'
        else:
            return 'low'

    def record_request(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        response_time_ms: int,
        cost: float = 0.0,
        success: bool = True,
        truncated: bool = False,
    ) -> None:
        """
        Record a request in a session.

        Args:
            session_id: Session to record in
            input_tokens: Input tokens used
            output_tokens: Output tokens generated
            response_time_ms: Response time in milliseconds
            cost: Cost of the request in USD
            success: Whether the request succeeded
            truncated: Whether the response was truncated
        """
        with self._lock:
            if session_id not in self._sessions:
                logger.warning(f"Session {session_id} not found, ignoring request")
                return

            metrics = self._sessions[session_id]

            # Update counts
            metrics.request_count += 1
            if success:
                metrics.successful_requests += 1
            else:
                metrics.failed_requests += 1

            # Update tokens
            metrics.total_input_tokens += input_tokens
            metrics.total_output_tokens += output_tokens

            # Update context usage
            if metrics.context_usage:
                metrics.context_usage.input_tokens += input_tokens
                metrics.context_usage.output_tokens += output_tokens

            # Update timing
            metrics.total_response_time_ms += response_time_ms
            metrics.last_activity = datetime.now(timezone.utc)

            # Update cost
            metrics.total_cost += cost

            # Update truncation count
            if truncated:
                metrics.truncation_count += 1

            # Prepare common attributes
            agent = metrics.agent_name or "unknown"
            model = metrics.model or "unknown"
            project_id = metrics.project_id or ""

            base_attrs = {
                "agent_name": agent,
                "model": model,
                "project_id": project_id,
            }

            # OpenTelemetry metrics (preferred)
            if self._otel_enabled:
                if self._otel_requests_counter:
                    self._otel_requests_counter.add(1, {
                        **base_attrs,
                        "status": "success" if success else "error",
                    })

                if self._otel_tokens_counter:
                    self._otel_tokens_counter.add(input_tokens, {
                        **base_attrs,
                        "direction": "input",
                    })
                    self._otel_tokens_counter.add(output_tokens, {
                        **base_attrs,
                        "direction": "output",
                    })

                if self._otel_response_time:
                    self._otel_response_time.record(response_time_ms, base_attrs)

                if truncated and self._otel_truncations:
                    self._otel_truncations.add(1, base_attrs)

                if cost > 0 and self._otel_cost_counter:
                    self._otel_cost_counter.add(cost, base_attrs)

            # Legacy Prometheus metrics
            if self._prom_total_requests:
                self._prom_total_requests.labels(
                    agent_name=agent,
                    model=model,
                    status="success" if success else "error"
                ).inc()

            if self._prom_total_tokens:
                self._prom_total_tokens.labels(
                    agent_name=agent,
                    model=model,
                    direction="input"
                ).inc(input_tokens)
                self._prom_total_tokens.labels(
                    agent_name=agent,
                    model=model,
                    direction="output"
                ).inc(output_tokens)

            if self._prom_response_time:
                self._prom_response_time.labels(
                    agent_name=agent,
                    model=model
                ).observe(response_time_ms)

            if self._prom_context_usage and metrics.context_usage:
                self._prom_context_usage.labels(
                    session_id=session_id,
                    agent_name=agent,
                    model=model
                ).set(metrics.context_usage.capacity_used)

            if truncated and self._prom_truncations:
                self._prom_truncations.labels(
                    agent_name=agent,
                    model=model
                ).inc()

            if cost > 0 and self._prom_total_cost:
                self._prom_total_cost.labels(
                    agent_name=agent,
                    model=model
                ).inc(cost)

            # Log warning if near capacity
            if metrics.context_usage and metrics.context_usage.is_near_capacity:
                logger.warning(
                    f"Session {session_id} near context capacity: "
                    f"{metrics.context_usage.capacity_used:.1%}",
                    extra={
                        "session_id": session_id,
                        "capacity_used": metrics.context_usage.capacity_used,
                        "tokens_remaining": metrics.context_usage.capacity_remaining,
                    }
                )

    def end_session(self, session_id: str, state: SessionState = SessionState.COMPLETED) -> None:
        """
        End a session.

        Args:
            session_id: Session to end
            state: Final state (COMPLETED or ERROR)
        """
        with self._lock:
            if session_id not in self._sessions:
                logger.warning(f"Session {session_id} not found")
                return

            metrics = self._sessions[session_id]
            metrics.state = state
            metrics.last_activity = datetime.now(timezone.utc)

            # Prepare attributes
            attrs = {
                "agent_name": metrics.agent_name or "unknown",
                "model": metrics.model or "unknown",
                "project_id": metrics.project_id or "",
            }

            # OpenTelemetry metrics (preferred)
            if self._otel_enabled and self._otel_active_sessions:
                self._otel_active_sessions.add(-1, attrs)

            # Legacy Prometheus metrics
            if self._prom_active_sessions:
                self._prom_active_sessions.labels(
                    agent_name=metrics.agent_name or "unknown",
                    model=metrics.model or "unknown"
                ).dec()

            if self._prom_context_usage:
                # Remove the gauge for this session
                try:
                    self._prom_context_usage.remove(
                        session_id,
                        metrics.agent_name or "unknown",
                        metrics.model or "unknown"
                    )
                except Exception:
                    pass  # Gauge may not exist

            logger.debug(
                f"Ended session {session_id} with state {state.value}",
                extra={
                    "session_id": session_id,
                    "state": state.value,
                    "total_requests": metrics.request_count,
                    "total_cost": metrics.total_cost,
                }
            )

    def get_session(self, session_id: str) -> Optional[SessionMetrics]:
        """Get metrics for a session"""
        with self._lock:
            return self._sessions.get(session_id)

    def get_active_sessions(self) -> List[SessionMetrics]:
        """Get all active sessions"""
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.state == SessionState.ACTIVE
            ]

    def get_all_sessions(self) -> List[SessionMetrics]:
        """Get all sessions (active and completed)"""
        with self._lock:
            return list(self._sessions.values())

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of all sessions.

        Returns:
            Dictionary with summary statistics
        """
        with self._lock:
            active = [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]
            completed = [s for s in self._sessions.values() if s.state == SessionState.COMPLETED]
            errored = [s for s in self._sessions.values() if s.state == SessionState.ERROR]

            total_tokens = sum(s.total_input_tokens + s.total_output_tokens for s in self._sessions.values())
            total_cost = sum(s.total_cost for s in self._sessions.values())
            total_requests = sum(s.request_count for s in self._sessions.values())
            total_truncations = sum(s.truncation_count for s in self._sessions.values())

            # Calculate average context usage for active sessions
            avg_context_usage = 0.0
            if active:
                usages = [s.context_usage.capacity_used for s in active if s.context_usage]
                if usages:
                    avg_context_usage = sum(usages) / len(usages)

            return {
                "active_sessions": len(active),
                "completed_sessions": len(completed),
                "errored_sessions": len(errored),
                "total_sessions": len(self._sessions),
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "total_truncations": total_truncations,
                "average_context_usage": avg_context_usage,
                "sessions_near_capacity": sum(
                    1 for s in active
                    if s.context_usage and s.context_usage.is_near_capacity
                ),
                "by_agent": self._summarize_by_agent(),
                "by_model": self._summarize_by_model(),
            }

    def _summarize_by_agent(self) -> Dict[str, Dict[str, Any]]:
        """Summarize metrics by agent name"""
        by_agent: Dict[str, Dict[str, Any]] = {}

        for session in self._sessions.values():
            agent = session.agent_name or "unknown"
            if agent not in by_agent:
                by_agent[agent] = {
                    "sessions": 0,
                    "active": 0,
                    "requests": 0,
                    "tokens": 0,
                    "cost": 0.0,
                }

            by_agent[agent]["sessions"] += 1
            if session.state == SessionState.ACTIVE:
                by_agent[agent]["active"] += 1
            by_agent[agent]["requests"] += session.request_count
            by_agent[agent]["tokens"] += session.total_input_tokens + session.total_output_tokens
            by_agent[agent]["cost"] += session.total_cost

        return by_agent

    def _summarize_by_model(self) -> Dict[str, Dict[str, Any]]:
        """Summarize metrics by model"""
        by_model: Dict[str, Dict[str, Any]] = {}

        for session in self._sessions.values():
            model = session.model or "unknown"
            if model not in by_model:
                by_model[model] = {
                    "sessions": 0,
                    "active": 0,
                    "requests": 0,
                    "tokens": 0,
                    "cost": 0.0,
                    "avg_context_usage": 0.0,
                }

            by_model[model]["sessions"] += 1
            if session.state == SessionState.ACTIVE:
                by_model[model]["active"] += 1
            by_model[model]["requests"] += session.request_count
            by_model[model]["tokens"] += session.total_input_tokens + session.total_output_tokens
            by_model[model]["cost"] += session.total_cost

        # Calculate average context usage per model
        for model in by_model:
            active_sessions = [
                s for s in self._sessions.values()
                if s.model == model and s.state == SessionState.ACTIVE and s.context_usage
            ]
            if active_sessions:
                by_model[model]["avg_context_usage"] = sum(
                    s.context_usage.capacity_used for s in active_sessions
                ) / len(active_sessions)

        return by_model

    def clear_completed(self) -> int:
        """
        Remove completed and errored sessions from memory.

        Returns:
            Number of sessions removed
        """
        with self._lock:
            to_remove = [
                sid for sid, s in self._sessions.items()
                if s.state in (SessionState.COMPLETED, SessionState.ERROR)
            ]
            for sid in to_remove:
                del self._sessions[sid]

            logger.info(f"Cleared {len(to_remove)} completed sessions")
            return len(to_remove)


# Global session tracker instance (optional singleton)
_global_tracker: Optional[SessionTracker] = None


def get_session_tracker(prometheus_port: Optional[int] = None) -> SessionTracker:
    """
    Get the global session tracker instance.

    Args:
        prometheus_port: Port for Prometheus metrics (only used on first call)

    Returns:
        Global SessionTracker instance
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = SessionTracker(prometheus_port=prometheus_port)
    return _global_tracker
