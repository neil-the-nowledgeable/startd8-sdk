"""
Event system for the StartD8 framework

This module provides a unified event system for observing and reacting to
framework activity.
"""

from .types import Event, EventType, EventPriority, agent_call_start, agent_call_complete, agent_call_error
from .bus import EventBus
from .handlers import LoggingHandler, MetricsHandler, ConsoleProgressHandler

__all__ = [
    'Event',
    'EventType',
    'EventPriority',
    'EventBus',
    'LoggingHandler',
    'MetricsHandler',
    'ConsoleProgressHandler',
    'agent_call_start',
    'agent_call_complete',
    'agent_call_error',
]

