"""
Event bus implementation for framework-wide event handling
"""

from typing import Callable, Deque, Dict, List, Union, Optional, Set
from collections import defaultdict, deque
import threading
import asyncio
import logging
from contextlib import contextmanager

from .types import Event, EventType
from ..context import correlation_id

logger = logging.getLogger(__name__)

# Type aliases for event handlers
EventHandler = Callable[[Event], None]
AsyncEventHandler = Callable[[Event], 'asyncio.Future']


class EventBus:
    """
    Central event bus for framework-wide event handling.
    
    Supports:
    - Synchronous and asynchronous event handlers
    - Decorator-based and explicit handler registration
    - Event filtering by type
    - Optional persistence for critical events
    - Thread-safe operation across multiple threads
    
    Example:
        # Subscribe to events
        @EventBus.on(EventType.AGENT_CALL_COMPLETE)
        def log_agent_call(event: Event):
            logger.info(
                f"Agent {event.data['agent_name']} completed",
                extra={
                    "agent_name": event.data.get('agent_name'),
                    "response_time_ms": event.data.get('response_time_ms'),
                    "event_type": event.type.name
                }
            )
        
        # Or subscribe programmatically
        EventBus.subscribe(EventType.JOB_COMPLETE, my_handler)
        
        # Emit events
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Claude", data={...}))
    """
    
    _listeners: Dict[EventType, List[EventHandler]] = defaultdict(list)
    _async_listeners: Dict[EventType, List[AsyncEventHandler]] = defaultdict(list)
    _global_listeners: List[EventHandler] = []
    _wildcard_handlers: Set[EventHandler] = set()
    _max_history: int = 1000
    # deque(maxlen=...) trims atomically on append — avoids the rebind-under-lock
    # race the manual list slice had (harden-in-place, R1-S2 gate ADR 2026-06-07)
    _event_history: Deque[Event] = deque(maxlen=_max_history)
    _lock = threading.RLock()
    _enabled: bool = True
    _persistence_enabled: bool = False
    _persistence_callback: Optional[Callable[[Event], None]] = None
    
    @classmethod
    def subscribe(
        cls, 
        event_type: Union[EventType, List[EventType]], 
        handler: EventHandler
    ) -> None:
        """
        Subscribe a handler to one or more event types.
        
        Args:
            event_type: Single event type or list of types
            handler: Callback function that receives Event
        """
        with cls._lock:
            types = [event_type] if isinstance(event_type, EventType) else event_type
            for et in types:
                if handler not in cls._listeners[et]:
                    cls._listeners[et].append(handler)
    
    @classmethod
    def subscribe_async(
        cls, 
        event_type: EventType, 
        handler: AsyncEventHandler
    ) -> None:
        """Subscribe an async handler to an event type"""
        with cls._lock:
            if handler not in cls._async_listeners[event_type]:
                cls._async_listeners[event_type].append(handler)
    
    @classmethod
    def subscribe_all(cls, handler: EventHandler) -> None:
        """Subscribe a handler to ALL events"""
        with cls._lock:
            if handler not in cls._global_listeners:
                cls._global_listeners.append(handler)
            cls._wildcard_handlers.add(handler)
    
    @classmethod
    def unsubscribe(cls, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type"""
        with cls._lock:
            if handler in cls._listeners[event_type]:
                cls._listeners[event_type].remove(handler)
    
    @classmethod
    def unsubscribe_all(cls, handler: EventHandler) -> None:
        """
        Unsubscribe a handler from all events.
        
        Args:
            handler: Handler to remove
        """
        with cls._lock:
            cls._wildcard_handlers.discard(handler)
            cls._global_listeners = [h for h in cls._global_listeners if h != handler]
            for handlers in cls._listeners.values():
                if handler in handlers:
                    handlers.remove(handler)
    
    @classmethod
    def emit(cls, event: Event) -> None:
        """
        Emit an event to all subscribed handlers.
        
        Handlers are called synchronously in subscription order.
        Exceptions in handlers are logged but don't stop other handlers.
        """
        if not cls._enabled:
            return
        
        # Set correlation ID if not already set
        if not event.correlation_id:
            event.correlation_id = correlation_id.get()
        
        with cls._lock:
            # Add to history if it should be persisted
            if event.should_persist():
                # deque(maxlen=_max_history) trims oldest entries automatically
                cls._event_history.append(event)

                # Call persistence callback if enabled
                if cls._persistence_enabled and cls._persistence_callback:
                    try:
                        cls._persistence_callback(event)
                    except Exception as e:
                        logger.error(f"Error persisting event: {e}", exc_info=True)
            
            # Get handlers for this event type
            handlers = cls._listeners.get(event.type, []) + cls._global_listeners
            # Preserve subscription order while removing duplicates
            handlers = list(dict.fromkeys(handlers))
        
        # Call handlers outside the lock to prevent deadlocks
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Error in event handler for {event.type.name}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": event.type.name,
                        "event_id": event.id,
                        "handler": handler.__name__
                    }
                )
        
        logger.debug(
            f"Emitted event {event.type.name}",
            extra={
                "event_id": event.id,
                "event_type": event.type.name,
                "handlers_called": len(handlers)
            }
        )
    
    @classmethod
    async def emit_async(cls, event: Event) -> None:
        """Emit event and await async handlers"""
        cls.emit(event)  # Call sync handlers
        
        with cls._lock:
            async_handlers = cls._async_listeners.get(event.type, [])
        
        if async_handlers:
            results = await asyncio.gather(
                *[h(event) for h in async_handlers],
                return_exceptions=True
            )
            # Log any exceptions from async handlers
            for i, result in enumerate(results):
                if isinstance(result, BaseException) and not isinstance(result, Exception):
                    raise result
                if isinstance(result, Exception):
                    logger.error(
                        f"Async event handler failed for {event.type}: {result}",
                        exc_info=result
                    )
    
    @classmethod
    def on(cls, event_type: Union[EventType, List[EventType]]):
        """
        Decorator to subscribe a function to event type(s).
        
        Example:
            @EventBus.on(EventType.AGENT_CALL_COMPLETE)
            def handle_completion(event: Event):
                logger.debug(
                    "Event completed",
                    extra={"event_type": event.type.name, "event_data": event.data}
                )
        """
        def decorator(func: EventHandler) -> EventHandler:
            cls.subscribe(event_type, func)
            return func
        return decorator
    
    @classmethod
    def get_history(
        cls,
        event_type: Optional[EventType] = None,
        limit: Optional[int] = None
    ) -> List[Event]:
        """
        Get event history.
        
        Only returns persisted events (priority HIGH or CRITICAL).
        
        Args:
            event_type: Optional filter by event type
            limit: Optional limit on number of events
            
        Returns:
            List of events, most recent first
        """
        with cls._lock:
            events = list(cls._event_history)

        # Filter by type if specified
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        # Reverse to get most recent first
        events.reverse()
        
        # Apply limit
        if limit:
            events = events[:limit]
        
        return events
    
    @classmethod
    def clear_history(cls) -> None:
        """Clear event history"""
        with cls._lock:
            cls._event_history.clear()
            logger.debug("Cleared event history")
    
    @classmethod
    def enable_persistence(cls, callback: Callable[[Event], None]) -> None:
        """
        Enable event persistence with a custom callback.
        
        The callback will be called for all events that should be persisted
        (priority HIGH or CRITICAL).
        
        Args:
            callback: Function to call for persisting events
        """
        with cls._lock:
            cls._persistence_enabled = True
            cls._persistence_callback = callback
            logger.info("Event persistence enabled")
    
    @classmethod
    def disable_persistence(cls) -> None:
        """Disable event persistence"""
        with cls._lock:
            cls._persistence_enabled = False
            cls._persistence_callback = None
            logger.info("Event persistence disabled")
    
    @classmethod
    def clear(cls) -> None:
        """Remove all event handlers"""
        with cls._lock:
            cls._listeners.clear()
            cls._async_listeners.clear()
            cls._global_listeners.clear()
            cls._wildcard_handlers.clear()
    
    @classmethod
    def clear_handlers(cls) -> None:
        """Clear all event handlers (useful for testing)"""
        with cls._lock:
            cls._listeners.clear()
            cls._async_listeners.clear()
            cls._wildcard_handlers.clear()
            logger.debug("Cleared all event handlers")
    
    @classmethod
    def get_handler_count(cls, event_type: Optional[EventType] = None) -> int:
        """
        Get count of registered handlers.
        
        Args:
            event_type: Optional event type to count handlers for
            
        Returns:
            Number of handlers
        """
        with cls._lock:
            if event_type:
                return len(cls._listeners.get(event_type, []))
            else:
                return sum(len(handlers) for handlers in cls._listeners.values()) + len(cls._global_listeners) + len(cls._wildcard_handlers)
    
    @classmethod
    @contextmanager
    def disabled(cls):
        """Context manager to temporarily disable event emission"""
        old_state = cls._enabled
        cls._enabled = False
        try:
            yield
        finally:
            cls._enabled = old_state

