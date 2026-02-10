"""
Core Agent Framework implementation
"""

import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
import uuid

from .models import (
    Prompt, AgentResponse, Benchmark, TokenUsage, BenchmarkStatus,
    ResponseComparison, BenchmarkReport, PaginatedResult, ResponseMetadata
)
from .storage import StorageBackend, FileSystemStorage
from .logging_config import get_logger
from .exceptions import ValidationError
from .utils.file_operations import atomic_write_json
try:
    from .cache import SimpleCache
except ImportError:
    SimpleCache = None

# Resilience imports
try:
    from .resilience import ResilienceConfig, ResilienceLevel, DEFAULT_RESILIENCE_CONFIG
except ImportError:
    ResilienceConfig = None
    ResilienceLevel = None
    DEFAULT_RESILIENCE_CONFIG = None

# Session tracking imports
try:
    from .session_tracking import SessionTracker, SessionMetrics, SessionState
    _SESSION_TRACKING_AVAILABLE = True
except ImportError:
    SessionTracker = None
    SessionMetrics = None
    SessionState = None
    _SESSION_TRACKING_AVAILABLE = False

logger = get_logger(__name__)


class AgentFramework:
    """
    Main framework for managing multi-LLM agent workflows
    
    Features:
    - Prompt version control
    - Response tracking with timing
    - Token usage monitoring
    - Benchmark creation and comparison
    - Multi-agent coordination
    """
    
    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        enable_cache: bool = True,
        resilience_config: Optional["ResilienceConfig"] = None,
        enable_session_tracking: bool = False,
        prometheus_port: Optional[int] = None,
        enable_otel: bool = False,
    ):
        """
        Initialize the Agent Framework

        Args:
            storage_dir: Directory for storing data (default: ./.startd8)
            enable_cache: Whether to enable caching (default: True)
            resilience_config: Resilience/self-healing configuration (default: STANDARD level)
            enable_session_tracking: Whether to enable session tracking (default: False)
            prometheus_port: Port for Prometheus metrics (requires enable_session_tracking=True)
            enable_otel: Whether to auto-configure OpenTelemetry (default: False)
        """
        # OTel auto-configuration (before other init so spans capture everything)
        if enable_otel:
            try:
                from .otel import auto_configure_otel
                auto_configure_otel()
            except ImportError:
                logger.debug("OTel not available, skipping auto-configure")

        if storage_dir is None:
            storage_dir = Path.cwd() / ".startd8"

        self.storage: StorageBackend = FileSystemStorage(storage_dir)

        if enable_cache and SimpleCache:
            self._cache = SimpleCache()
        else:
            self._cache = None

        # Resilience configuration
        if resilience_config is not None:
            self._resilience_config = resilience_config
        elif DEFAULT_RESILIENCE_CONFIG is not None:
            self._resilience_config = DEFAULT_RESILIENCE_CONFIG
        else:
            self._resilience_config = None

        # Session tracking
        self._session_tracker: Optional["SessionTracker"] = None
        if enable_session_tracking and _SESSION_TRACKING_AVAILABLE:
            self._session_tracker = SessionTracker(prometheus_port=prometheus_port)
            logger.info(
                f"Session tracking enabled" +
                (f" with Prometheus on port {prometheus_port}" if prometheus_port else ""),
                extra={"prometheus_port": prometheus_port}
            )
        elif enable_session_tracking and not _SESSION_TRACKING_AVAILABLE:
            logger.warning("Session tracking requested but module not available")

        # Index for faster lookups
        self._prompt_index: Dict[str, Prompt] = {}
        self._response_index: Dict[str, List[AgentResponse]] = {}  # Indexed by prompt_id

    # =========================================================================
    # Session Tracking
    # =========================================================================

    @property
    def session_tracker(self) -> Optional["SessionTracker"]:
        """Get the session tracker instance (if enabled)."""
        return self._session_tracker

    def start_session(
        self,
        agent_name: Optional[str] = None,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Start a new tracked session.

        Args:
            agent_name: Name of the agent
            model: Model being used
            tags: Optional tags for filtering
            metadata: Additional metadata

        Returns:
            Session ID, or None if session tracking is disabled
        """
        if not self._session_tracker:
            return None
        return self._session_tracker.start_session(
            agent_name=agent_name,
            model=model,
            tags=tags,
            metadata=metadata,
        )

    def end_session(self, session_id: str) -> None:
        """
        End a tracked session.

        Args:
            session_id: Session to end
        """
        if self._session_tracker:
            self._session_tracker.end_session(session_id)

    def get_session_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get summary of all tracked sessions.

        Returns:
            Summary dictionary, or None if session tracking is disabled
        """
        if not self._session_tracker:
            return None
        return self._session_tracker.get_summary()

    def get_active_sessions(self) -> List["SessionMetrics"]:
        """
        Get all active sessions.

        Returns:
            List of active SessionMetrics, or empty list if tracking disabled
        """
        if not self._session_tracker:
            return []
        return self._session_tracker.get_active_sessions()

    # =========================================================================
    # Resilience Configuration
    # =========================================================================

    @property
    def resilience_config(self) -> Optional["ResilienceConfig"]:
        """Get the current resilience configuration."""
        return self._resilience_config

    @resilience_config.setter
    def resilience_config(self, config: "ResilienceConfig") -> None:
        """Set the resilience configuration."""
        self._resilience_config = config
        logger.info(
            f"Resilience config updated: level={config.level.value if config else 'None'}",
            extra={"resilience_level": config.level.value if config else None}
        )

    def get_retry_config(self):
        """
        Get retry configuration for agents.

        Returns RetryConfig suitable for agent initialization.
        Returns None if resilience is disabled.
        """
        if not self._resilience_config or not self._resilience_config.enabled:
            return None
        if not self._resilience_config.retry.enabled:
            return None
        return self._resilience_config.retry.to_retry_config()

    def get_circuit_breaker_config(self):
        """
        Get circuit breaker configuration.

        Returns CircuitBreakerConfig suitable for MCP Gateway.
        Returns None if resilience is disabled.
        """
        if not self._resilience_config or not self._resilience_config.enabled:
            return None
        if not self._resilience_config.circuit_breaker.enabled:
            return None
        return self._resilience_config.circuit_breaker.to_circuit_breaker_config()

    def get_error_strategy(self):
        """
        Get default error handling strategy for workflows.

        Returns ErrorStrategy enum value.
        """
        if not self._resilience_config or not self._resilience_config.enabled:
            from .models import ErrorHandling
            return ErrorHandling.STOP

        # Map resilience ErrorStrategy to models.ErrorHandling
        from .models import ErrorHandling
        strategy = self._resilience_config.workflow_errors.default_strategy

        mapping = {
            "stop": ErrorHandling.STOP,
            "retry": ErrorHandling.RETRY,
            "skip": ErrorHandling.SKIP,
        }
        return mapping.get(strategy.value, ErrorHandling.STOP)

    def should_auto_fix(self) -> bool:
        """Check if auto-fix is enabled."""
        if not self._resilience_config or not self._resilience_config.enabled:
            return False
        return self._resilience_config.auto_fix.enabled

    def should_run_diagnostics(self) -> bool:
        """Check if diagnostics are enabled."""
        if not self._resilience_config or not self._resilience_config.enabled:
            return False
        return self._resilience_config.diagnostics.enabled

    # =========================================================================
    # Agent Factory Methods
    # =========================================================================

    def create_agent(
        self,
        agent_type: str,
        name: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        **kwargs
    ):
        """
        Create an agent with the framework's resilience settings applied.

        This factory method automatically applies:
        - Retry configuration from ResilienceConfig
        - Connection pooling settings
        - Other framework-level settings

        Args:
            agent_type: Type of agent ('claude', 'gpt4', 'gemini', 'mock', 'openai_compatible')
            name: Optional agent name
            model: Optional model identifier
            max_tokens: Max tokens for response (default: 4096)
            **kwargs: Additional agent-specific arguments

        Returns:
            Configured agent instance

        Example:
            framework = AgentFramework()
            agent = framework.create_agent('claude', name='my-agent')
            # Agent has retry config from framework.resilience_config
        """
        from .agents import ClaudeAgent, GPT4Agent, MockAgent

        # Get retry config from resilience settings
        retry_config = self.get_retry_config()

        # Common kwargs for all agents
        common_kwargs = {
            'max_tokens': max_tokens,
        }

        # Add retry config if enabled
        if retry_config:
            common_kwargs['retry_config'] = retry_config
            common_kwargs['enable_retry'] = True

        # Merge with user-provided kwargs (user kwargs take precedence)
        agent_kwargs = {**common_kwargs, **kwargs}

        agent_type_lower = agent_type.lower()

        if agent_type_lower == 'claude':
            return ClaudeAgent(
                name=name or 'claude',
                model=model or 'claude-sonnet-4-20250514',
                **agent_kwargs
            )
        elif agent_type_lower == 'gpt4':
            return GPT4Agent(
                name=name or 'gpt4',
                model=model or 'gpt-4o',
                **agent_kwargs
            )
        elif agent_type_lower == 'gemini':
            try:
                from .agents import GeminiAgent
                return GeminiAgent(
                    name=name or 'gemini',
                    model=model or 'gemini-2.0-flash',
                    **agent_kwargs
                )
            except ImportError:
                raise ValueError("GeminiAgent not available. Install google-generativeai package.")
        elif agent_type_lower == 'mock':
            return MockAgent(
                name=name or 'mock',
                model=model or 'mock-model'
            )
        elif agent_type_lower == 'openai_compatible':
            try:
                from .agents import OpenAICompatibleAgent
                return OpenAICompatibleAgent(
                    name=name or 'custom',
                    model=model or 'custom-model',
                    **agent_kwargs
                )
            except ImportError:
                raise ValueError("OpenAICompatibleAgent not available.")
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

    # =========================================================================
    # Prompt Management
    # =========================================================================

    def create_prompt(
        self,
        content: str,
        version: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Prompt:
        """
        Create and store a versioned prompt
        
        Args:
            content: The prompt content
            version: Version identifier (semver recommended)
            tags: Optional tags for categorization
            metadata: Optional additional metadata
            
        Returns:
            Created Prompt object
        
        Raises:
            ValidationError: If content or version is invalid
        """
        try:
            prompt = Prompt(
                id=f"prompt-{uuid.uuid4().hex[:12]}",
                content=content,
                version=version,
                tags=tags or [],
                metadata=metadata or {}
            )
            
            self.storage.save_prompt(prompt)
            
            # Update index and cache
            self._prompt_index[prompt.id] = prompt
            if self._cache:
                self._cache.set(f"prompt:{prompt.id}", prompt)
            
            logger.info(f"Created prompt {prompt.id}", extra={"prompt_id": prompt.id, "version": version})
            return prompt
        except ValueError as e:
            logger.error(f"Validation error creating prompt: {e}", extra={"version": version})
            raise ValidationError(str(e), field="prompt") from e
    
    def get_prompt(self, prompt_id: str) -> Optional[Prompt]:
        """
        Get a prompt by ID
        
        Uses cache if enabled for faster lookups.
        
        Args:
            prompt_id: ID of prompt to retrieve
            
        Returns:
            Prompt object or None if not found
        """
        # Check cache first
        if self._cache:
            cached_prompt = self._cache.get(f"prompt:{prompt_id}")
            if cached_prompt is not None:
                return cached_prompt
        
        # Check index
        if prompt_id in self._prompt_index:
            prompt = self._prompt_index[prompt_id]
            if self._cache:
                self._cache.set(f"prompt:{prompt_id}", prompt)
            return prompt
        
        # Load from storage
        prompt = self.storage.load_prompt(prompt_id)
        if prompt:
            # Update index and cache
            self._prompt_index[prompt_id] = prompt
            if self._cache:
                self._cache.set(f"prompt:{prompt_id}", prompt)
        
        return prompt
    
    def list_prompts(
        self,
        tags: Optional[List[str]] = None,
        page: Optional[int] = None,
        page_size: int = 50
    ) -> Union[List[Prompt], PaginatedResult]:
        """
        List all prompts, optionally filtered by tags
        
        Args:
            tags: Optional tags to filter by
            page: Optional page number for pagination (1-indexed)
            page_size: Number of items per page (default: 50)
            
        Returns:
            List of Prompt objects if page is None, otherwise PaginatedResult
        """
        from .storage.pagination import paginate
        
        try:
            prompts = self.storage.list_prompts()
        except Exception as e:
            logger.error(f"Failed to list prompts from storage: {e}", exc_info=True)
            # Return empty list to prevent TUI crash
            prompts = []
        
        if tags:
            prompts = [
                p for p in prompts 
                if any(tag in p.tags for tag in tags)
            ]
        
        if page is not None:
            return paginate(prompts, page=page, page_size=page_size)
        
        return prompts
    
    def record_response(
        self,
        prompt_id: str,
        agent_name: str,
        model: str,
        response: str,
        response_time_ms: int,
        token_usage: Optional[TokenUsage] = None,
        metadata: Optional['ResponseMetadata'] = None,
        response_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> AgentResponse:
        """
        Record an agent's response to a prompt
        
        Args:
            prompt_id: ID of the prompt
            agent_name: Name of the agent
            model: Model identifier
            response: Response content
            response_time_ms: Response time in milliseconds
            token_usage: Optional token usage statistics
            metadata: Optional additional metadata
            
        Returns:
            Created AgentResponse object
        
        Raises:
            ValidationError: If response data is invalid
        """
        try:
            agent_response = AgentResponse(
                id=response_id or f"response-{uuid.uuid4().hex[:12]}",
                prompt_id=prompt_id,
                agent_name=agent_name,
                model=model,
                response=response,
                timestamp=timestamp or datetime.now(timezone.utc),
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                metadata=metadata or {}
            )
            
            self.storage.save_response(agent_response)
            
            # Update response index
            if prompt_id not in self._response_index:
                self._response_index[prompt_id] = []
            self._response_index[prompt_id].append(agent_response)
            
            # Invalidate cache for this prompt's responses
            if self._cache:
                self._cache.delete(f"responses:{prompt_id}")
            
            logger.info(
                f"Recorded response {agent_response.id}",
                extra={"response_id": agent_response.id, "agent_name": agent_name, "prompt_id": prompt_id}
            )
            return agent_response
        except ValueError as e:
            logger.error(f"Validation error recording response: {e}", extra={"agent_name": agent_name, "prompt_id": prompt_id})
            raise ValidationError(str(e), field="response") from e
    
    def get_response(self, response_id: str) -> Optional[AgentResponse]:
        """Get a response by ID"""
        return self.storage.load_response(response_id)
    
    def list_responses(
        self, 
        prompt_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        page: Optional[int] = None,
        page_size: int = 50
    ) -> Union[List[AgentResponse], PaginatedResult]:
        """
        List responses, optionally filtered by prompt or agent
        
        Uses indexing for faster lookups when filtering by prompt_id.
        
        Args:
            prompt_id: Optional prompt ID to filter by
            agent_name: Optional agent name to filter by
            page: Optional page number for pagination (1-indexed)
            page_size: Number of items per page (default: 50)
            
        Returns:
            List of AgentResponse objects if page is None, otherwise PaginatedResult
        """
        from .storage.pagination import paginate
        
        # Use index if filtering by prompt_id
        if prompt_id and prompt_id in self._response_index:
            responses = self._response_index[prompt_id].copy()
        else:
            # Load from storage
            try:
                responses = self.storage.list_responses()
            except Exception as e:
                logger.error(f"Failed to list responses from storage: {e}", exc_info=True)
                # Return empty list to prevent TUI crash
                responses = []
            
            # Update index if filtering by prompt_id
            if prompt_id:
                self._response_index[prompt_id] = [r for r in responses if r.prompt_id == prompt_id]
                responses = self._response_index[prompt_id]
        
        if agent_name:
            responses = [r for r in responses if r.agent_name == agent_name]
        
        if page is not None:
            return paginate(responses, page=page, page_size=page_size)
        
        return responses
    
    def create_benchmark(
        self,
        name: str,
        prompt_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Benchmark:
        """
        Create a benchmark for comparing agent responses
        
        Args:
            name: Benchmark name
            prompt_id: ID of prompt to benchmark
            metadata: Optional metadata
            
        Returns:
            Created Benchmark object
        """
        benchmark = Benchmark(
            id=f"benchmark-{uuid.uuid4().hex[:12]}",
            name=name,
            prompt_id=prompt_id,
            status=BenchmarkStatus.CREATED,
            metadata=metadata or {}
        )
        
        self.storage.save_benchmark(benchmark)
        return benchmark
    
    def complete_benchmark(
        self,
        benchmark_id: str,
        summary: Optional[str] = None
    ) -> Benchmark:
        """
        Mark a benchmark as completed
        
        Args:
            benchmark_id: ID of benchmark
            summary: Optional summary text
            
        Returns:
            Updated Benchmark object
        """
        benchmark = self.storage.load_benchmark(benchmark_id)
        if not benchmark:
            raise ValueError(f"Benchmark {benchmark_id} not found")
        
        benchmark.status = BenchmarkStatus.COMPLETED
        benchmark.completed_at = datetime.now(timezone.utc)
        benchmark.summary = summary
        
        # Collect all response IDs for this benchmark's prompt
        responses = self.list_responses(prompt_id=benchmark.prompt_id)
        benchmark.response_ids = [r.id for r in responses]
        
        self.storage.save_benchmark(benchmark)
        return benchmark
    
    def get_benchmark(self, benchmark_id: str) -> Optional[Benchmark]:
        """Get a benchmark by ID"""
        return self.storage.load_benchmark(benchmark_id)
    
    def compare_responses(self, prompt_id: str) -> ResponseComparison:
        """
        Compare all responses for a given prompt
        
        Args:
            prompt_id: ID of prompt to compare responses for
            
        Returns:
            ResponseComparison model with comparison data and rankings
        """
        prompt = self.get_prompt(prompt_id)
        responses = self.list_responses(prompt_id=prompt_id)
        
        if not responses:
            return ResponseComparison(
                prompt=prompt.model_dump() if prompt else None,
                total_responses=0,
                avg_response_time_ms=0.0,
                total_tokens=0,
                responses=[],
                rankings={},
                message="No responses found"
            )
        
        # Calculate statistics
        avg_response_time = sum(r.response_time_ms for r in responses) / len(responses)
        total_tokens = sum(r.token_usage.total if r.token_usage else 0 for r in responses)
        
        # Rankings
        by_speed = sorted(responses, key=lambda r: r.response_time_ms)
        by_tokens = sorted(
            [r for r in responses if r.token_usage],
            key=lambda r: r.token_usage.total if r.token_usage else float('inf')
        )
        
        return ResponseComparison(
            prompt=prompt.model_dump() if prompt else None,
            total_responses=len(responses),
            avg_response_time_ms=avg_response_time,
            total_tokens=total_tokens,
            responses=[
                {
                    "id": r.id,
                    "agent": r.agent_name,
                    "model": r.model,
                    "response_time_ms": r.response_time_ms,
                    "tokens": r.token_usage.total if r.token_usage else None,
                    "cost_estimate": r.token_usage.cost_estimate if r.token_usage else None,
                    "response_preview": r.response[:200] + "..." if len(r.response) > 200 else r.response
                }
                for r in responses
            ],
            rankings={
                "by_speed": [
                    {"agent": r.agent_name, "time_ms": r.response_time_ms}
                    for r in by_speed
                ],
                "by_token_efficiency": [
                    {"agent": r.agent_name, "tokens": r.token_usage.total}
                    for r in by_tokens
                ]
            }
        )
    
    def export_benchmark_report(
        self,
        benchmark_id: str,
        output_file: Optional[Path] = None
    ) -> BenchmarkReport:
        """
        Generate and export a detailed benchmark report
        
        Args:
            benchmark_id: ID of benchmark
            output_file: Optional file to write JSON report to
            
        Returns:
            BenchmarkReport model with report data
        
        Raises:
            ValueError: If benchmark not found
        """
        benchmark = self.get_benchmark(benchmark_id)
        if not benchmark:
            raise ValueError(f"Benchmark {benchmark_id} not found")
        
        prompt = self.get_prompt(benchmark.prompt_id)
        comparison = self.compare_responses(benchmark.prompt_id)
        
        report = BenchmarkReport(
            benchmark=benchmark.model_dump(),
            prompt=prompt.model_dump() if prompt else None,
            comparison=comparison,
            generated_at=datetime.now(timezone.utc).isoformat()
        )
        
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            # Use atomic write to prevent corruption
            atomic_write_json(output_file, report.model_dump(), indent=2, default=str)
        
        return report

