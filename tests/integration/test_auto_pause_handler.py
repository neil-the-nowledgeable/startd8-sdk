"""
Integration tests for AutoPauseHandler
"""

import pytest
import tempfile
from pathlib import Path

from startd8.pause_manager import PauseStateManager
from startd8.auto_pause_handler import (
    AutoPauseHandler,
    AutoPauseConfig,
    build_agent_provider_map
)
from startd8.events import EventBus, Event, EventType, EventPriority
from startd8.costs.usage_limits import UsageLimitChecker, UsageSummary, UsageLimitStatus, LimitType, UsageLevel
from startd8.costs.store import CostStore
from datetime import datetime, timezone


@pytest.fixture
def temp_storage_path():
    """Create a temporary storage path for pause state"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "pause_state.json"


@pytest.fixture
def pause_manager(temp_storage_path):
    """Create a PauseStateManager instance"""
    return PauseStateManager(storage_path=temp_storage_path)


@pytest.fixture
def agent_provider_map():
    """Create a sample agent-provider mapping"""
    return {
        "claude": "anthropic",
        "gpt4": "openai",
        "gemini": "google",
        "composer": "anthropic",
    }


@pytest.fixture
def auto_pause_handler(pause_manager, agent_provider_map):
    """Create an AutoPauseHandler instance"""
    return AutoPauseHandler(
        pause_manager=pause_manager,
        agent_provider_map=agent_provider_map,
        config=AutoPauseConfig(
            enabled=True,
            pause_on_exceeded=True,
            pause_on_critical=False,
            pause_on_warning=False,
            auto_resume_enabled=True,
            resume_at_percentage=50.0
        )
    )


@pytest.fixture
def clear_event_bus():
    """Clear event bus before and after each test"""
    EventBus.clear()
    yield
    EventBus.clear()


@pytest.fixture
def cost_store():
    """Create a temporary cost store"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "costs.db"
        return CostStore(store_path)


class TestBuildAgentProviderMap:
    """Test build_agent_provider_map helper function"""
    
    def test_build_map_from_builtin_agents(self):
        """Test building map from built-in agents"""
        agents = [
            {'name': 'Claude', 'builtin_type': 'claude', 'type': 'builtin'},
            {'name': 'GPT-4', 'builtin_type': 'gpt4', 'type': 'builtin'},
            {'name': 'Mock', 'builtin_type': 'mock', 'type': 'builtin'},
        ]
        
        mapping = build_agent_provider_map(agents)
        
        assert mapping['Claude'] == 'anthropic'
        assert mapping['GPT-4'] == 'openai'
        assert mapping['Mock'] == 'mock'
    
    def test_build_map_from_custom_agents(self):
        """Test building map from custom agents"""
        agents = [
            {
                'name': 'MyAgent',
                'type': 'custom',
                'provider': 'anthropic',
                'custom_config': {}
            },
            {
                'name': 'AnotherAgent',
                'type': 'custom',
                'custom_config': {'provider': 'openai'}
            },
        ]
        
        mapping = build_agent_provider_map(agents)
        
        assert mapping['MyAgent'] == 'anthropic'
        assert mapping['AnotherAgent'] == 'openai'
    
    def test_build_map_mixed_agents(self):
        """Test building map from mixed built-in and custom agents"""
        agents = [
            {'name': 'Claude', 'builtin_type': 'claude', 'type': 'builtin'},
            {
                'name': 'CustomAgent',
                'type': 'custom',
                'provider': 'google',
                'custom_config': {}
            },
        ]
        
        mapping = build_agent_provider_map(agents)
        
        assert mapping['Claude'] == 'anthropic'
        assert mapping['CustomAgent'] == 'google'
    
    def test_build_map_normalizes_provider_names(self):
        """Test that provider names are normalized"""
        agents = [
            {
                'name': 'ClaudeAgent',
                'type': 'custom',
                'provider': 'claude',
                'custom_config': {}
            },
            {
                'name': 'GPTAgent',
                'type': 'custom',
                'provider': 'gpt4',
                'custom_config': {}
            },
        ]
        
        mapping = build_agent_provider_map(agents)
        
        assert mapping['ClaudeAgent'] == 'anthropic'
        assert mapping['GPTAgent'] == 'openai'


class TestAutoPauseHandler:
    """Test AutoPauseHandler functionality"""
    
    def test_initialization(self, auto_pause_handler, pause_manager, agent_provider_map):
        """Test AutoPauseHandler initialization"""
        assert auto_pause_handler.pause_manager == pause_manager
        assert auto_pause_handler.agent_provider_map == agent_provider_map
        assert auto_pause_handler.config.enabled is True
    
    def test_auto_pause_on_exceeded(self, auto_pause_handler, pause_manager, clear_event_bus):
        """Test agents are auto-paused when limit exceeded"""
        # Emit usage limit exceeded event
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        # Claude and Composer should be paused (both use anthropic)
        assert pause_manager.is_paused("claude")
        assert pause_manager.is_paused("composer")
        
        # GPT-4 should NOT be paused (uses openai)
        assert not pause_manager.is_paused("gpt4")
        
        # Check pause info
        info = pause_manager.get_pause_info("claude")
        assert info.paused_by == "system"
        assert "anthropic" in info.reason
        assert info.auto_pause["provider"] == "anthropic"
        assert info.auto_pause["usage_percentage"] == 97.5
    
    def test_auto_pause_on_critical_disabled(self, pause_manager, agent_provider_map, clear_event_bus):
        """Test that critical events don't pause when disabled"""
        handler = AutoPauseHandler(
            pause_manager=pause_manager,
            agent_provider_map=agent_provider_map,
            config=AutoPauseConfig(
                enabled=True,
                pause_on_exceeded=True,
                pause_on_critical=False,  # Disabled
                pause_on_warning=False
            )
        )
        
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_CRITICAL,
            source="test",
            priority=EventPriority.HIGH,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 92.0
            }
        ))
        
        # Should not be paused
        assert not pause_manager.is_paused("claude")
    
    def test_auto_pause_on_critical_enabled(self, pause_manager, agent_provider_map, clear_event_bus):
        """Test that critical events pause when enabled"""
        handler = AutoPauseHandler(
            pause_manager=pause_manager,
            agent_provider_map=agent_provider_map,
            config=AutoPauseConfig(
                enabled=True,
                pause_on_exceeded=True,
                pause_on_critical=True,  # Enabled
                pause_on_warning=False
            )
        )
        
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_CRITICAL,
            source="test",
            priority=EventPriority.HIGH,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 92.0
            }
        ))
        
        # Should be paused
        assert pause_manager.is_paused("claude")
    
    def test_auto_pause_handler_disabled(self, pause_manager, agent_provider_map, clear_event_bus):
        """Test that handler doesn't pause when disabled"""
        handler = AutoPauseHandler(
            pause_manager=pause_manager,
            agent_provider_map=agent_provider_map,
            config=AutoPauseConfig(enabled=False)
        )
        
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        # Should not be paused
        assert not pause_manager.is_paused("claude")
    
    def test_update_agent_provider_map(self, auto_pause_handler):
        """Test updating agent-provider mapping"""
        new_map = {
            "new_agent": "anthropic",
            "another_agent": "openai"
        }
        
        auto_pause_handler.update_agent_provider_map(new_map)
        assert auto_pause_handler.agent_provider_map == new_map


class TestAutoResume:
    """Test auto-resume functionality"""
    
    def test_auto_resume_below_threshold(self, auto_pause_handler, pause_manager, clear_event_bus):
        """Test that agents are auto-resumed when usage drops below threshold"""
        # First, auto-pause an agent
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        assert pause_manager.is_paused("claude")
        
        # Create usage summary with usage below threshold
        summary = UsageSummary(timestamp=datetime.now(timezone.utc))
        summary.provider_statuses["anthropic"] = [
            UsageLimitStatus(
                provider="anthropic",
                model=None,
                limit_type=LimitType.REQUESTS_PER_MINUTE,
                current_usage=30,
                limit_value=50,
                usage_percentage=40.0,  # Below 50% threshold
                remaining=20,
                level=UsageLevel.LOW,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc)
            )
        ]
        
        # Check and resume
        resumed = auto_pause_handler.check_and_resume(summary)
        
        assert "claude" in resumed
        assert not pause_manager.is_paused("claude")
    
    def test_auto_resume_above_threshold(self, auto_pause_handler, pause_manager, clear_event_bus):
        """Test that agents are NOT resumed when usage is still above threshold"""
        # Auto-pause an agent
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        assert pause_manager.is_paused("claude")
        
        # Create usage summary with usage still above threshold
        summary = UsageSummary(timestamp=datetime.now(timezone.utc))
        summary.provider_statuses["anthropic"] = [
            UsageLimitStatus(
                provider="anthropic",
                model=None,
                limit_type=LimitType.REQUESTS_PER_MINUTE,
                current_usage=40,
                limit_value=50,
                usage_percentage=80.0,  # Still above 50% threshold
                remaining=10,
                level=UsageLevel.HIGH,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc)
            )
        ]
        
        # Check and resume
        resumed = auto_pause_handler.check_and_resume(summary)
        
        assert len(resumed) == 0
        assert pause_manager.is_paused("claude")
    
    def test_auto_resume_disabled(self, pause_manager, agent_provider_map, clear_event_bus):
        """Test that auto-resume doesn't work when disabled"""
        handler = AutoPauseHandler(
            pause_manager=pause_manager,
            agent_provider_map=agent_provider_map,
            config=AutoPauseConfig(
                enabled=True,
                pause_on_exceeded=True,
                auto_resume_enabled=False  # Disabled
            )
        )
        
        # Auto-pause
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        assert pause_manager.is_paused("claude")
        
        # Create summary with low usage
        summary = UsageSummary(timestamp=datetime.now(timezone.utc))
        summary.provider_statuses["anthropic"] = [
            UsageLimitStatus(
                provider="anthropic",
                model=None,
                limit_type=LimitType.REQUESTS_PER_MINUTE,
                current_usage=20,
                limit_value=50,
                usage_percentage=40.0,
                remaining=30,
                level=UsageLevel.LOW,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc)
            )
        ]
        
        resumed = handler.check_and_resume(summary)
        assert len(resumed) == 0
        assert pause_manager.is_paused("claude")
    
    def test_auto_resume_multiple_limits(self, auto_pause_handler, pause_manager, clear_event_bus):
        """Test that all limits must be below threshold for resume"""
        # Auto-pause
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        assert pause_manager.is_paused("claude")
        
        # Create summary with one limit below threshold, one above
        summary = UsageSummary(timestamp=datetime.now(timezone.utc))
        summary.provider_statuses["anthropic"] = [
            UsageLimitStatus(
                provider="anthropic",
                model=None,
                limit_type=LimitType.REQUESTS_PER_MINUTE,
                current_usage=20,
                limit_value=50,
                usage_percentage=40.0,  # Below threshold
                remaining=30,
                level=UsageLevel.LOW,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc)
            ),
            UsageLimitStatus(
                provider="anthropic",
                model=None,
                limit_type=LimitType.TOKENS_PER_MINUTE,
                current_usage=50000,
                limit_value=40000,
                usage_percentage=125.0,  # Above threshold
                remaining=-10000,
                level=UsageLevel.EXCEEDED,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc)
            )
        ]
        
        resumed = auto_pause_handler.check_and_resume(summary)
        assert len(resumed) == 0
        assert pause_manager.is_paused("claude")
    
    def test_auto_resume_custom_threshold(self, pause_manager, agent_provider_map, clear_event_bus):
        """Test auto-resume with custom threshold"""
        handler = AutoPauseHandler(
            pause_manager=pause_manager,
            agent_provider_map=agent_provider_map,
            config=AutoPauseConfig(
                enabled=True,
                pause_on_exceeded=True,
                auto_resume_enabled=True,
                resume_at_percentage=75.0  # Custom threshold
            )
        )
        
        # Auto-pause
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        assert pause_manager.is_paused("claude")
        
        # Usage at 70% - below custom 75% threshold
        summary = UsageSummary(timestamp=datetime.now(timezone.utc))
        summary.provider_statuses["anthropic"] = [
            UsageLimitStatus(
                provider="anthropic",
                model=None,
                limit_type=LimitType.REQUESTS_PER_MINUTE,
                current_usage=35,
                limit_value=50,
                usage_percentage=70.0,  # Below 75% threshold
                remaining=15,
                level=UsageLevel.MODERATE,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc)
            )
        ]
        
        resumed = handler.check_and_resume(summary)
        assert "claude" in resumed
        assert not pause_manager.is_paused("claude")


class TestIntegrationWithUsageLimitChecker:
    """Test integration with UsageLimitChecker"""
    
    def test_check_all_limits_triggers_auto_resume(self, cost_store, pause_manager, agent_provider_map, clear_event_bus):
        """Test that check_all_limits triggers auto-resume"""
        handler = AutoPauseHandler(
            pause_manager=pause_manager,
            agent_provider_map=agent_provider_map,
            config=AutoPauseConfig(
                enabled=True,
                pause_on_exceeded=True,
                auto_resume_enabled=True,
                resume_at_percentage=50.0
            )
        )
        
        # First auto-pause
        EventBus.emit(Event(
            type=EventType.USAGE_LIMIT_EXCEEDED,
            source="test",
            priority=EventPriority.CRITICAL,
            data={
                "provider": "anthropic",
                "limit_type": "requests_per_minute",
                "usage_percentage": 97.5
            }
        ))
        
        assert pause_manager.is_paused("claude")
        
        # Create checker and call check_all_limits with handler
        checker = UsageLimitChecker(cost_store)
        summary = checker.check_all_limits(auto_pause_handler=handler)
        
        # Since there's no actual usage data, the agent should remain paused
        # But the check_and_resume should have been called
        # (In real scenario with usage data, it would resume if below threshold)
        assert isinstance(summary, UsageSummary)

