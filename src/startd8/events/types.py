"""
Event types and event data structures for the StartD8 framework
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid


class EventType(Enum):
    """All event types in the StartD8 framework"""

    # Agent events
    AGENT_CALL_START = auto()
    AGENT_CALL_COMPLETE = auto()
    AGENT_CALL_ERROR = auto()

    # Agent pause/resume events
    AGENT_MANUAL_PAUSED = auto()
    AGENT_AUTO_PAUSED = auto()
    AGENT_MANUAL_RESUMED = auto()
    AGENT_AUTO_RESUMED = auto()
    
    # Cost tracking events
    COST_RECORDED = auto()
    BUDGET_WARNING = auto()
    BUDGET_EXCEEDED = auto()
    BUDGET_CREATED = auto()
    BUDGET_UPDATED = auto()
    BUDGET_DELETED = auto()

    # Usage limit events
    USAGE_LIMIT_WARNING = auto()
    USAGE_LIMIT_EXCEEDED = auto()
    USAGE_LIMIT_CRITICAL = auto()
    
    # Pipeline events
    PIPELINE_START = auto()
    PIPELINE_STEP_START = auto()
    PIPELINE_STEP_COMPLETE = auto()
    PIPELINE_COMPLETE = auto()
    PIPELINE_STEP_RETRY = auto()  # FR-410
    PIPELINE_ERROR = auto()
    
    # Job Queue events
    JOB_QUEUED = auto()
    JOB_PROCESSING_START = auto()
    JOB_PROCESSING_COMPLETE = auto()
    JOB_FAILED = auto()
    JOB_ARCHIVED = auto()
    
    # Document Enhancement events
    ENHANCEMENT_START = auto()
    ENHANCEMENT_STEP_START = auto()
    ENHANCEMENT_STEP_COMPLETE = auto()
    ENHANCEMENT_COMPLETE = auto()
    
    # Storage events
    PROMPT_CREATED = auto()
    RESPONSE_RECORDED = auto()
    BENCHMARK_CREATED = auto()
    BENCHMARK_COMPLETED = auto()
    
    # System events
    SYSTEM_ERROR = auto()
    SYSTEM_WARNING = auto()
    
    # Framework lifecycle
    FRAMEWORK_INITIALIZED = auto()
    CACHE_CLEARED = auto()


class EventPriority(Enum):
    """Event priority levels for persistence"""
    LOW = "low"           # Informational, don't persist
    NORMAL = "normal"     # Standard events, optional persistence
    HIGH = "high"         # Important events, should persist
    CRITICAL = "critical" # Critical events, must persist


@dataclass
class Event:
    """
    Base event class for all StartD8 events.
    
    Events are immutable records of something that happened
    in the framework.
    """
    type: EventType
    source: str  # Component that emitted the event (e.g., "Pipeline", "JobQueue")
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None  # For tracing related events
    priority: EventPriority = field(default=EventPriority.NORMAL)  # Event priority for persistence
    id: str = field(default_factory=lambda: f"event-{uuid.uuid4().hex[:12]}")  # Unique event ID
    
    def __post_init__(self):
        # Ensure data is immutable by creating a copy
        self.data = dict(self.data)
    
    def should_persist(self) -> bool:
        """Determine if this event should be persisted"""
        return self.priority in (EventPriority.HIGH, EventPriority.CRITICAL)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary format"""
        return {
            "id": self.id,
            "type": self.type.name,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "priority": self.priority.value,
        }


# Convenience event constructors
def agent_call_start(
    agent_name: str, 
    model: str, 
    prompt_preview: str,
    correlation_id: Optional[str] = None
) -> Event:
    """Create an agent call start event"""
    return Event(
        type=EventType.AGENT_CALL_START,
        source="Agent",
        data={
            "agent_name": agent_name,
            "model": model,
            "prompt_preview": prompt_preview[:100],
        },
        correlation_id=correlation_id,
    )


def agent_call_complete(
    agent_name: str,
    model: str,
    response_time_ms: int,
    tokens: int,
    correlation_id: Optional[str] = None
) -> Event:
    """Create an agent call complete event"""
    return Event(
        type=EventType.AGENT_CALL_COMPLETE,
        source="Agent",
        data={
            "agent_name": agent_name,
            "model": model,
            "response_time_ms": response_time_ms,
            "tokens": tokens,
        },
        correlation_id=correlation_id,
    )


def agent_call_error(
    agent_name: str,
    model: str,
    error: str,
    correlation_id: Optional[str] = None
) -> Event:
    """Create an agent call error event"""
    return Event(
        type=EventType.AGENT_CALL_ERROR,
        source="Agent",
        data={
            "agent_name": agent_name,
            "model": model,
            "error": error,
        },
        correlation_id=correlation_id,
    )

