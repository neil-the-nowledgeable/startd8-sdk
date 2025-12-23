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
    ResponseComparison, BenchmarkReport, PaginatedResult
)
from .storage import StorageBackend, FileSystemStorage
from .logging_config import get_logger
from .exceptions import ValidationError
from .utils.file_operations import atomic_write_json
try:
    from .cache import SimpleCache
except ImportError:
    SimpleCache = None

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
    
    def __init__(self, storage_dir: Optional[Path] = None, enable_cache: bool = True):
        """
        Initialize the Agent Framework
        
        Args:
            storage_dir: Directory for storing data (default: ./.startd8)
            enable_cache: Whether to enable caching (default: True)
        """
        if storage_dir is None:
            storage_dir = Path.cwd() / ".startd8"
        
        self.storage: StorageBackend = FileSystemStorage(storage_dir)
        
        if enable_cache and SimpleCache:
            self._cache = SimpleCache()
        else:
            self._cache = None
            
        # Index for faster lookups
        self._prompt_index: Dict[str, Prompt] = {}
        self._response_index: Dict[str, List[AgentResponse]] = {}  # Indexed by prompt_id
    
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
        metadata: Optional[Dict[str, Any]] = None,
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

