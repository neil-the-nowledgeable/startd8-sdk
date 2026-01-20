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
    """
    Handler that collects metrics from events with ContextCore project context support.
    
    Supports semantic conventions:
        - io.contextcore.project.id
        - io.contextcore.project.name
        - io.contextcore.task.id
        - io.contextcore.sprint.id
    """
    
    # Global metrics (all projects combined)
    _metrics: Dict[str, Any] = {
        "agent_calls": 0,
        "total_tokens": 0,
        "total_response_time_ms": 0,
        "jobs_completed": 0,
        "jobs_failed": 0,
        "pipelines_completed": 0,
        "pipelines_failed": 0,
    }
    
    # Per-project metrics: {project_id: {metric_name: value}}
    _project_metrics: Dict[str, Dict[str, Any]] = {}
    
    # Per-task metrics: {task_id: {metric_name: value}}
    _task_metrics: Dict[str, Dict[str, Any]] = {}
    
    # Per-sprint metrics: {sprint_id: {metric_name: value}}
    _sprint_metrics: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def _get_contextcore_attrs(cls, event: Event) -> Dict[str, Any]:
        """
        Extract ContextCore attributes from event data.
        
        Returns dict with project_id, task_id, sprint_id, project_name if present.
        """
        return {
            "project_id": event.data.get("project_id"),
            "project_name": event.data.get("project_name"),
            "task_id": event.data.get("task_id"),
            "sprint_id": event.data.get("sprint_id"),
        }
    
    @classmethod
    def _ensure_context_metrics(cls, project_id: str = None, task_id: str = None, sprint_id: str = None) -> None:
        """Ensure metric dicts exist for given context IDs."""
        base_metrics = {
            "agent_calls": 0,
            "total_tokens": 0,
            "total_response_time_ms": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "pipelines_completed": 0,
            "pipelines_failed": 0,
        }
        
        if project_id and project_id not in cls._project_metrics:
            cls._project_metrics[project_id] = base_metrics.copy()
        if task_id and task_id not in cls._task_metrics:
            cls._task_metrics[task_id] = base_metrics.copy()
        if sprint_id and sprint_id not in cls._sprint_metrics:
            cls._sprint_metrics[sprint_id] = base_metrics.copy()
    
    @classmethod
    def _update_context_metrics(
        cls, 
        metric_name: str, 
        value: Any,
        project_id: str = None,
        task_id: str = None,
        sprint_id: str = None,
        operation: str = "add"
    ) -> None:
        """
        Update metrics for all applicable contexts.
        
        Args:
            metric_name: Name of metric to update
            value: Value to add or set
            project_id: ContextCore project ID
            task_id: ContextCore task ID  
            sprint_id: ContextCore sprint ID
            operation: "add" to increment, "set" to replace
        """
        cls._ensure_context_metrics(project_id, task_id, sprint_id)
        
        targets = []
        if project_id:
            targets.append(cls._project_metrics[project_id])
        if task_id:
            targets.append(cls._task_metrics[task_id])
        if sprint_id:
            targets.append(cls._sprint_metrics[sprint_id])
        
        for target in targets:
            if operation == "add":
                target[metric_name] = target.get(metric_name, 0) + value
            else:
                target[metric_name] = value
    
    @classmethod
    def handle(cls, event: Event) -> None:
        """Update metrics based on event, including ContextCore context."""
        ctx = cls._get_contextcore_attrs(event)
        project_id = ctx.get("project_id")
        task_id = ctx.get("task_id")
        sprint_id = ctx.get("sprint_id")
        
        if event.type == EventType.AGENT_CALL_COMPLETE:
            tokens = event.data.get("tokens", 0)
            response_time = event.data.get("response_time_ms", 0)
            
            # Update global metrics
            cls._metrics["agent_calls"] += 1
            cls._metrics["total_tokens"] += tokens
            cls._metrics["total_response_time_ms"] += response_time
            
            # Update context-specific metrics
            cls._update_context_metrics("agent_calls", 1, project_id, task_id, sprint_id)
            cls._update_context_metrics("total_tokens", tokens, project_id, task_id, sprint_id)
            cls._update_context_metrics("total_response_time_ms", response_time, project_id, task_id, sprint_id)
            
        elif event.type == EventType.JOB_PROCESSING_COMPLETE:
            cls._metrics["jobs_completed"] += 1
            cls._update_context_metrics("jobs_completed", 1, project_id, task_id, sprint_id)
            
        elif event.type == EventType.JOB_FAILED:
            cls._metrics["jobs_failed"] += 1
            cls._update_context_metrics("jobs_failed", 1, project_id, task_id, sprint_id)
            
        elif event.type == EventType.PIPELINE_COMPLETE:
            cls._metrics["pipelines_completed"] += 1
            cls._update_context_metrics("pipelines_completed", 1, project_id, task_id, sprint_id)
            
        elif event.type == EventType.PIPELINE_ERROR:
            cls._metrics["pipelines_failed"] += 1
            cls._update_context_metrics("pipelines_failed", 1, project_id, task_id, sprint_id)
    
    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Get a copy of current global metrics"""
        return cls._metrics.copy()
    
    @classmethod
    def get_metrics_by_project(cls, project_id: str = None) -> Dict[str, Any]:
        """
        Get metrics filtered by project.
        
        Args:
            project_id: ContextCore project ID. If None, returns all project metrics.
            
        Returns:
            Metrics dict for the project, or dict of all project metrics
        """
        if project_id:
            return cls._project_metrics.get(project_id, {}).copy()
        return {pid: m.copy() for pid, m in cls._project_metrics.items()}
    
    @classmethod
    def get_metrics_by_task(cls, task_id: str = None) -> Dict[str, Any]:
        """
        Get metrics filtered by task.
        
        Args:
            task_id: ContextCore task ID. If None, returns all task metrics.
            
        Returns:
            Metrics dict for the task, or dict of all task metrics
        """
        if task_id:
            return cls._task_metrics.get(task_id, {}).copy()
        return {tid: m.copy() for tid, m in cls._task_metrics.items()}
    
    @classmethod
    def get_metrics_by_sprint(cls, sprint_id: str = None) -> Dict[str, Any]:
        """
        Get metrics filtered by sprint.
        
        Args:
            sprint_id: ContextCore sprint ID. If None, returns all sprint metrics.
            
        Returns:
            Metrics dict for the sprint, or dict of all sprint metrics
        """
        if sprint_id:
            return cls._sprint_metrics.get(sprint_id, {}).copy()
        return {sid: m.copy() for sid, m in cls._sprint_metrics.items()}
    
    @classmethod
    def get_all_metrics_with_context(cls) -> Dict[str, Any]:
        """
        Get comprehensive metrics including all ContextCore dimensions.
        
        Returns:
            Dict with global, by_project, by_task, and by_sprint metrics
        """
        return {
            "global": cls._metrics.copy(),
            "by_project": {pid: m.copy() for pid, m in cls._project_metrics.items()},
            "by_task": {tid: m.copy() for tid, m in cls._task_metrics.items()},
            "by_sprint": {sid: m.copy() for sid, m in cls._sprint_metrics.items()},
        }
    
    @classmethod
    def reset_metrics(cls) -> None:
        """Reset all metrics to zero (global and per-context)"""
        cls._metrics = {
            "agent_calls": 0,
            "total_tokens": 0,
            "total_response_time_ms": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "pipelines_completed": 0,
            "pipelines_failed": 0,
        }
        cls._project_metrics = {}
        cls._task_metrics = {}
        cls._sprint_metrics = {}
    
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
    """Handler that prints progress to console and logs events"""
    
    @staticmethod
    def handle(event: Event) -> None:
        """Print event progress to console and log to logger"""
        if event.type == EventType.AGENT_CALL_START:
            agent_name = event.data.get('agent_name', 'Unknown')
            model = event.data.get('model', 'Unknown')
            message = f"🤖 Calling {agent_name} ({model})..."
            print(message)
            logger.info(
                f"Agent call started: {agent_name}",
                extra={
                    "event_type": event.type.name,
                    "agent_name": agent_name,
                    "model": model,
                    "correlation_id": event.correlation_id
                }
            )
        elif event.type == EventType.AGENT_CALL_COMPLETE:
            agent_name = event.data.get('agent_name', 'Unknown')
            response_time_ms = event.data.get('response_time_ms', 0)
            message = f"✅ {agent_name} completed in {response_time_ms}ms"
            print(message)
            logger.info(
                f"Agent call completed: {agent_name}",
                extra={
                    "event_type": event.type.name,
                    "agent_name": agent_name,
                    "response_time_ms": response_time_ms,
                    "correlation_id": event.correlation_id
                }
            )
        elif event.type == EventType.AGENT_CALL_ERROR:
            agent_name = event.data.get('agent_name', 'Unknown')
            error = event.data.get('error', 'Unknown error')
            message = f"❌ {agent_name} failed: {error}"
            print(message)
            logger.error(
                f"Agent call failed: {agent_name}",
                extra={
                    "event_type": event.type.name,
                    "agent_name": agent_name,
                    "error": error,
                    "correlation_id": event.correlation_id
                }
            )
        elif event.type == EventType.PIPELINE_START:
            message = "🚀 Pipeline started"
            print(message)
            logger.info(
                "Pipeline started",
                extra={
                    "event_type": event.type.name,
                    "correlation_id": event.correlation_id,
                    **event.data
                }
            )
        elif event.type == EventType.PIPELINE_COMPLETE:
            message = "✨ Pipeline completed successfully"
            print(message)
            logger.info(
                "Pipeline completed successfully",
                extra={
                    "event_type": event.type.name,
                    "correlation_id": event.correlation_id,
                    **event.data
                }
            )
        elif event.type == EventType.PIPELINE_ERROR:
            error = event.data.get('error', 'Unknown error')
            message = f"💥 Pipeline failed: {error}"
            print(message)
            logger.error(
                "Pipeline failed",
                extra={
                    "event_type": event.type.name,
                    "error": error,
                    "correlation_id": event.correlation_id,
                    **event.data
                }
            )
    
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

