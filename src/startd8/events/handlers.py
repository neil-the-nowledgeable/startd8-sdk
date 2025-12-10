"""
Built-in event handlers for common use cases
"""

import logging
from typing import Dict, Any
from .types import Event, EventType
from .bus import EventBus

logger = logging.getLogger(__name__)


class LoggingHandler:
    """Handler that logs all events"""
    
    @staticmethod
    def handle(event: Event) -> None:
        """Log an event"""
        logger.info(
            f"[{event.type.name}] {event.source}",
            extra={
                "event_type": event.type.name,
                "event_source": event.source,
                "correlation_id": event.correlation_id,
                **event.data
            }
        )
    
    @classmethod
    def register(cls):
        """Register this handler to receive all events"""
        EventBus.subscribe_all(cls.handle)


class MetricsHandler:
    """Handler that collects metrics from events"""
    
    _metrics: Dict[str, Any] = {
        "agent_calls": 0,
        "total_tokens": 0,
        "total_response_time_ms": 0,
        "jobs_completed": 0,
        "jobs_failed": 0,
        "pipelines_completed": 0,
        "pipelines_failed": 0,
    }
    
    @classmethod
    def handle(cls, event: Event) -> None:
        """Update metrics based on event"""
        if event.type == EventType.AGENT_CALL_COMPLETE:
            cls._metrics["agent_calls"] += 1
            cls._metrics["total_tokens"] += event.data.get("tokens", 0)
            cls._metrics["total_response_time_ms"] += event.data.get("response_time_ms", 0)
        elif event.type == EventType.JOB_PROCESSING_COMPLETE:
            cls._metrics["jobs_completed"] += 1
        elif event.type == EventType.JOB_FAILED:
            cls._metrics["jobs_failed"] += 1
        elif event.type == EventType.PIPELINE_COMPLETE:
            cls._metrics["pipelines_completed"] += 1
        elif event.type == EventType.PIPELINE_ERROR:
            cls._metrics["pipelines_failed"] += 1
    
    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Get a copy of current metrics"""
        return cls._metrics.copy()
    
    @classmethod
    def reset_metrics(cls) -> None:
        """Reset all metrics to zero"""
        cls._metrics = {
            "agent_calls": 0,
            "total_tokens": 0,
            "total_response_time_ms": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "pipelines_completed": 0,
            "pipelines_failed": 0,
        }
    
    @classmethod
    def register(cls):
        """Register this handler to receive relevant events"""
        EventBus.subscribe([
            EventType.AGENT_CALL_COMPLETE,
            EventType.JOB_PROCESSING_COMPLETE,
            EventType.JOB_FAILED,
            EventType.PIPELINE_COMPLETE,
            EventType.PIPELINE_ERROR,
        ], cls.handle)


class ConsoleProgressHandler:
    """Handler that prints progress to console"""
    
    @staticmethod
    def handle(event: Event) -> None:
        """Print event progress to console"""
        if event.type == EventType.AGENT_CALL_START:
            print(f"🤖 Calling {event.data.get('agent_name')} ({event.data.get('model')})...")
        elif event.type == EventType.AGENT_CALL_COMPLETE:
            print(f"✅ {event.data.get('agent_name')} completed in {event.data.get('response_time_ms')}ms")
        elif event.type == EventType.AGENT_CALL_ERROR:
            print(f"❌ {event.data.get('agent_name')} failed: {event.data.get('error')}")
        elif event.type == EventType.PIPELINE_START:
            print(f"🚀 Pipeline started")
        elif event.type == EventType.PIPELINE_COMPLETE:
            print(f"✨ Pipeline completed successfully")
        elif event.type == EventType.PIPELINE_ERROR:
            print(f"💥 Pipeline failed: {event.data.get('error')}")
    
    @classmethod
    def register(cls):
        """Register this handler to receive progress events"""
        EventBus.subscribe([
            EventType.AGENT_CALL_START,
            EventType.AGENT_CALL_COMPLETE,
            EventType.AGENT_CALL_ERROR,
            EventType.PIPELINE_START,
            EventType.PIPELINE_COMPLETE,
            EventType.PIPELINE_ERROR,
        ], cls.handle)

