"""
Cost tracking service

Central service for recording and tracking costs across all agent calls.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from contextlib import contextmanager
from contextvars import ContextVar
import threading

from .models import CostRecord, CostSummary
from .store import CostStore
from .pricing import PricingService
from ..events import EventBus, Event, EventType, EventPriority
from ..logging_config import get_logger, correlation_id

logger = get_logger(__name__)

# Module-level context var for cost tracking attribution (Issue #3)
_cost_context: ContextVar[Dict[str, Any]] = ContextVar(
    'cost_context',
    default={}
)


def get_cost_context() -> Dict[str, Any]:
    """
    Get the current cost tracking context.
    
    Returns the active project and tags for the current context.
    Used to apply defaults when recording costs.
    
    Returns:
        Dictionary with 'project' and 'tags' keys
        
    Example:
        context = get_cost_context()
        # {'project': 'my-app', 'tags': ['feature-x', 'v1']}
    """
    return _cost_context.get()


def set_cost_context(
    project: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> None:
    """
    Set the cost tracking context manually.
    
    This is called internally by tracking_context(), but can also be used
    directly for advanced use cases.
    
    Args:
        project: Project identifier (overrides outer context)
        tags: Attribution tags (accumulated/merged with outer context)
        
    Example:
        set_cost_context(project="my-app", tags=["feature-x"])
    """
    current = _cost_context.get()
    
    # Merge tags: accumulate with existing context (decision A3)
    existing_tags = current.get("tags", [])
    new_tags = tags or []
    merged_tags = list(set(existing_tags) | set(new_tags))
    
    # Project overrides (innermost wins)
    _cost_context.set({
        "project": project if project is not None else current.get("project"),
        "tags": merged_tags
    })


def clear_cost_context() -> None:
    """
    Clear all cost tracking context (reset to defaults).
    
    Used internally to clean up after context manager exits.
    """
    _cost_context.set({})


class CostTracker:
    """
    Central service for tracking and recording costs.
    
    Thread-safe and designed for high-throughput use.
    
    Example:
        tracker = CostTracker(store, pricing_service)
        
        # Record a cost
        record = tracker.record_cost(
            agent_name="claude",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1500,
            output_tokens=500,
            tags=["code-review"],
            project="my-app"
        )
        
        # Get summary
        summary = tracker.get_summary(
            start=datetime(2025, 12, 1),
            end=datetime(2025, 12, 31)
        )
    """
    
    def __init__(
        self,
        store: CostStore,
        pricing_service: PricingService,
        enabled: bool = True
    ):
        self.store = store
        self.pricing = pricing_service
        self.enabled = enabled
        self._lock = threading.RLock()

        # In-memory cache for fast aggregations
        self._running_totals: Dict[str, float] = {}  # period_key -> total

        # Lazy-initialized OTel cost metrics
        self._otel_metrics = None
    
    def record_cost(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        provider: Optional[str] = None,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        prompt_id: Optional[str] = None,
        response_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CostRecord:
        """
        Record a cost for an API call.
        
        Args:
            agent_name: Name of the agent
            model: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            provider: Provider name (auto-detected if not provided)
            tags: Attribution tags
            project: Project identifier
            prompt_id: Associated prompt ID
            response_id: Associated response ID
            pipeline_id: Pipeline ID if part of pipeline
            job_id: Job ID if from queue
            metadata: Additional metadata
            
        Returns:
            Created CostRecord
        """
        if not self.enabled:
            # Return a zero-cost record when disabled
            return CostRecord(
                agent_name=agent_name,
                model=model,
                provider=provider or "unknown",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                input_cost=0.0,
                output_cost=0.0,
                total_cost=0.0,
            )
        
        # Get context defaults (Issue #3 - context integration)
        context = get_cost_context()
        
        # Project: explicit parameter overrides context default
        if project is None:
            project = context.get("project")
        
        # Tags: merge explicit tags with context tags (decision A3)
        context_tags = context.get("tags", [])
        effective_tags = list(set((tags or []) + context_tags))
        
        # Calculate costs
        input_cost, output_cost = self.pricing.calculate_cost_breakdown(
            model, input_tokens, output_tokens
        )
        total_cost = input_cost + output_cost
        
        # Detect provider if not provided
        if provider is None:
            provider = self.pricing.get_provider_for_model(model) or "unknown"
        
        # Create record
        record = CostRecord(
            agent_name=agent_name,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            tags=effective_tags,
            project=project,
            prompt_id=prompt_id,
            response_id=response_id,
            pipeline_id=pipeline_id,
            job_id=job_id,
            correlation_id=correlation_id.get() or None,
            metadata=metadata or {}
        )
        
        # Persist
        with self._lock:
            self.store.save(record)
            self._update_running_totals(record)
        
        # Emit event
        EventBus.emit(Event(
            type=EventType.COST_RECORDED,
            source="CostTracker",
            priority=EventPriority.NORMAL,
            data={
                "record_id": record.id,
                "model": model,
                "total_cost": total_cost,
                "total_tokens": record.total_tokens,
            },
            correlation_id=record.correlation_id
        ))

        # Record OTel cost metrics (lazy-init on first call)
        if self._otel_metrics is None:
            try:
                from .otel_metrics import CostMetrics
                self._otel_metrics = CostMetrics()
            except ImportError:
                self._otel_metrics = False  # Prevent retrying
        if self._otel_metrics:
            self._otel_metrics.record(record)

        logger.debug(
            f"Recorded cost: ${total_cost:.6f} for {model}",
            extra={
                "cost_record_id": record.id,
                "model": model,
                "total_cost": total_cost,
                "tokens": record.total_tokens
            }
        )
        
        return record
    
    def _update_running_totals(self, record: CostRecord):
        """Update in-memory running totals for fast budget checks"""
        now = record.timestamp
        
        # Update various period totals
        keys = [
            f"hourly:{now.strftime('%Y-%m-%d-%H')}",
            f"daily:{now.strftime('%Y-%m-%d')}",
            f"weekly:{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}",
            f"monthly:{now.strftime('%Y-%m')}",
            "total",
        ]
        
        for key in keys:
            self._running_totals[key] = self._running_totals.get(key, 0) + record.total_cost
    
    def get_running_total(self, period: str, period_key: str) -> float:
        """Get running total for a period"""
        key = f"{period}:{period_key}"
        
        # Check cache first
        if key in self._running_totals:
            return self._running_totals[key]
        
        # Load from store
        total = self.store.get_total_for_period(period, period_key)
        self._running_totals[key] = total
        return total
    
    def get_summary(
        self,
        start: datetime,
        end: datetime,
        project: Optional[str] = None,
        tags: Optional[List[str]] = None,
        model: Optional[str] = None
    ) -> CostSummary:
        """
        Get aggregated cost summary for a time period.
        
        Args:
            start: Period start (inclusive)
            end: Period end (exclusive)
            project: Filter by project
            tags: Filter by tags (any match)
            model: Filter by model
            
        Returns:
            CostSummary with breakdowns
        """
        records = self.store.query(
            start=start,
            end=end,
            project=project,
            tags=tags,
            model=model
        )
        
        if not records:
            return CostSummary(
                period_start=start,
                period_end=end,
                total_cost=0.0,
                total_calls=0,
                total_tokens=0
            )
        
        # Aggregate
        total_cost = sum(r.total_cost for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        
        by_model: Dict[str, float] = {}
        by_agent: Dict[str, float] = {}
        by_provider: Dict[str, float] = {}
        by_project: Dict[str, float] = {}
        by_tag: Dict[str, float] = {}
        by_day: Dict[str, float] = {}
        
        for record in records:
            by_model[record.model] = by_model.get(record.model, 0) + record.total_cost
            by_agent[record.agent_name] = by_agent.get(record.agent_name, 0) + record.total_cost
            by_provider[record.provider] = by_provider.get(record.provider, 0) + record.total_cost
            
            if record.project:
                by_project[record.project] = by_project.get(record.project, 0) + record.total_cost
            
            for tag in record.tags:
                by_tag[tag] = by_tag.get(tag, 0) + record.total_cost
            
            day_key = record.timestamp.strftime('%Y-%m-%d')
            by_day[day_key] = by_day.get(day_key, 0) + record.total_cost
        
        return CostSummary(
            period_start=start,
            period_end=end,
            total_cost=total_cost,
            total_calls=len(records),
            total_tokens=total_tokens,
            by_model=by_model,
            by_agent=by_agent,
            by_provider=by_provider,
            by_project=by_project,
            by_tag=by_tag,
            by_day=by_day,
            avg_cost_per_call=total_cost / len(records) if records else 0,
            avg_tokens_per_call=total_tokens / len(records) if records else 0,
            avg_cost_per_1k_tokens=(total_cost / total_tokens * 1000) if total_tokens else 0
        )
    
    @contextmanager
    def tracking_context(
        self,
        project: Optional[str] = None,
        tags: Optional[List[str]] = None
    ):
        """
        Context manager to set default cost attribution for all records created within.
        
        Supports nested contexts that merge tags and override project.
        
        Args:
            project: Project identifier (applies to all costs in this context)
            tags: Attribution tags (accumulated with outer context tags)
            
        Example:
            tracker = CostTracker(store, pricing)
            
            with tracker.tracking_context(project="my-app", tags=["v1"]):
                agent.generate(prompt)  # Cost tagged as project="my-app", tags=["v1"]
                
                # Nested context
                with tracker.tracking_context(tags=["feature-x"]):
                    agent.generate(prompt)  # Cost tagged as project="my-app", tags=["v1", "feature-x"]
                
                agent.generate(prompt)  # Back to project="my-app", tags=["v1"]
        """
        # Save current context to restore on exit
        current = _cost_context.get()
        
        # Set new context (merges tags, overrides project)
        set_cost_context(project=project, tags=tags)
        
        try:
            yield
        finally:
            # Restore previous context
            _cost_context.set(current)

