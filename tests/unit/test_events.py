"""
Unit tests for event system
"""

import pytest
import asyncio
from datetime import datetime

from startd8.events import (
    Event,
    EventType,
    EventBus,
    LoggingHandler,
    MetricsHandler,
    ConsoleProgressHandler,
    agent_call_start,
    agent_call_complete,
    agent_call_error
)


class TestEvent:
    """Test Event class"""
    
    def test_event_creation(self):
        """Test creating an event"""
        event = Event(
            type=EventType.AGENT_CALL_START,
            source="TestAgent",
            data={"test": "data"}
        )
        
        assert event.type == EventType.AGENT_CALL_START
        assert event.source == "TestAgent"
        assert event.data["test"] == "data"
        assert isinstance(event.timestamp, datetime)
    
    def test_event_to_dict(self):
        """Test converting event to dictionary"""
        event = Event(
            type=EventType.PIPELINE_COMPLETE,
            source="Pipeline",
            data={"result": "success"},
            correlation_id="test-123"
        )
        
        event_dict = event.to_dict()
        assert event_dict["type"] == "PIPELINE_COMPLETE"
        assert event_dict["source"] == "Pipeline"
        assert event_dict["data"]["result"] == "success"
        assert event_dict["correlation_id"] == "test-123"
    
    def test_event_data_immutability(self):
        """Test that event data is copied (immutable)"""
        original_data = {"key": "value"}
        event = Event(
            type=EventType.AGENT_CALL_START,
            source="Test",
            data=original_data
        )
        
        # Modifying original shouldn't affect event
        original_data["key"] = "modified"
        assert event.data["key"] == "value"


class TestEventConstructors:
    """Test convenience event constructors"""
    
    def test_agent_call_start(self):
        """Test agent_call_start constructor"""
        event = agent_call_start(
            agent_name="TestAgent",
            model="test-model",
            prompt_preview="Test prompt here",
            correlation_id="corr-123"
        )
        
        assert event.type == EventType.AGENT_CALL_START
        assert event.data["agent_name"] == "TestAgent"
        assert event.data["model"] == "test-model"
        assert event.correlation_id == "corr-123"
    
    def test_agent_call_complete(self):
        """Test agent_call_complete constructor"""
        event = agent_call_complete(
            agent_name="TestAgent",
            model="test-model",
            response_time_ms=1500,
            tokens=100,
            correlation_id="corr-123"
        )
        
        assert event.type == EventType.AGENT_CALL_COMPLETE
        assert event.data["response_time_ms"] == 1500
        assert event.data["tokens"] == 100
    
    def test_agent_call_error(self):
        """Test agent_call_error constructor"""
        event = agent_call_error(
            agent_name="TestAgent",
            model="test-model",
            error="Test error message"
        )
        
        assert event.type == EventType.AGENT_CALL_ERROR
        assert event.data["error"] == "Test error message"


class TestEventBus:
    """Test EventBus functionality"""
    
    def setup_method(self):
        """Clear event bus before each test"""
        EventBus.clear()
    
    def teardown_method(self):
        """Clear event bus after each test"""
        EventBus.clear()
    
    def test_subscribe_and_emit(self):
        """Test basic subscribe and emit"""
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        EventBus.subscribe(EventType.AGENT_CALL_START, handler)
        
        event = Event(
            type=EventType.AGENT_CALL_START,
            source="Test",
            data={"test": "data"}
        )
        EventBus.emit(event)
        
        assert len(received_events) == 1
        assert received_events[0] == event
    
    def test_subscribe_multiple_event_types(self):
        """Test subscribing to multiple event types"""
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        EventBus.subscribe([EventType.AGENT_CALL_START, EventType.AGENT_CALL_COMPLETE], handler)
        
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        EventBus.emit(Event(type=EventType.AGENT_CALL_COMPLETE, source="Test"))
        EventBus.emit(Event(type=EventType.PIPELINE_START, source="Test"))
        
        assert len(received_events) == 2
    
    def test_subscribe_all(self):
        """Test subscribing to all events"""
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        EventBus.subscribe_all(handler)
        
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        EventBus.emit(Event(type=EventType.PIPELINE_COMPLETE, source="Test"))
        
        assert len(received_events) == 2
    
    def test_unsubscribe(self):
        """Test unsubscribing from events"""
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        EventBus.subscribe(EventType.AGENT_CALL_START, handler)
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        
        EventBus.unsubscribe(EventType.AGENT_CALL_START, handler)
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        
        assert len(received_events) == 1
    
    def test_decorator_subscription(self):
        """Test @EventBus.on decorator"""
        received_events = []
        
        @EventBus.on(EventType.AGENT_CALL_START)
        def handler(event: Event):
            received_events.append(event)
        
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        
        assert len(received_events) == 1
    
    def test_handler_exception_doesnt_break_others(self):
        """Test that exceptions in one handler don't affect others"""
        handler1_called = []
        handler2_called = []
        
        def failing_handler(event: Event):
            handler1_called.append(True)
            raise Exception("Test exception")
        
        def working_handler(event: Event):
            handler2_called.append(True)
        
        EventBus.subscribe(EventType.AGENT_CALL_START, failing_handler)
        EventBus.subscribe(EventType.AGENT_CALL_START, working_handler)
        
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        
        assert len(handler1_called) == 1
        assert len(handler2_called) == 1
    
    def test_disabled_context_manager(self):
        """Test disabling event emission temporarily"""
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        EventBus.subscribe(EventType.AGENT_CALL_START, handler)
        
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        
        with EventBus.disabled():
            EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        
        EventBus.emit(Event(type=EventType.AGENT_CALL_START, source="Test"))
        
        assert len(received_events) == 2
    
    @pytest.mark.asyncio
    async def test_async_handler(self):
        """Test async event handlers"""
        received_events = []
        
        async def async_handler(event: Event):
            await asyncio.sleep(0.01)
            received_events.append(event)
        
        EventBus.subscribe_async(EventType.AGENT_CALL_START, async_handler)
        
        event = Event(type=EventType.AGENT_CALL_START, source="Test")
        await EventBus.emit_async(event)
        
        assert len(received_events) == 1


class TestMetricsHandler:
    """Test MetricsHandler functionality"""
    
    def setup_method(self):
        """Clear event bus and reset metrics before each test"""
        EventBus.clear()
        MetricsHandler.reset_metrics()
    
    def teardown_method(self):
        """Clear after each test"""
        EventBus.clear()
        MetricsHandler.reset_metrics()
    
    def test_metrics_collection(self):
        """Test that metrics are collected from events"""
        MetricsHandler.register()
        
        # Emit various events
        EventBus.emit(agent_call_complete(
            agent_name="test",
            model="test-model",
            response_time_ms=1000,
            tokens=100
        ))
        EventBus.emit(agent_call_complete(
            agent_name="test2",
            model="test-model",
            response_time_ms=500,
            tokens=50
        ))
        EventBus.emit(Event(type=EventType.JOB_PROCESSING_COMPLETE, source="Test"))
        EventBus.emit(Event(type=EventType.JOB_FAILED, source="Test"))
        
        metrics = MetricsHandler.get_metrics()
        
        assert metrics["agent_calls"] == 2
        assert metrics["total_tokens"] == 150
        assert metrics["total_response_time_ms"] == 1500
        assert metrics["jobs_completed"] == 1
        assert metrics["jobs_failed"] == 1
    
    def test_reset_metrics(self):
        """Test resetting metrics"""
        MetricsHandler.register()
        
        EventBus.emit(agent_call_complete(
            agent_name="test",
            model="test-model",
            response_time_ms=1000,
            tokens=100
        ))
        
        metrics_before = MetricsHandler.get_metrics()
        assert metrics_before["agent_calls"] == 1
        
        MetricsHandler.reset_metrics()
        
        metrics_after = MetricsHandler.get_metrics()
        assert metrics_after["agent_calls"] == 0

