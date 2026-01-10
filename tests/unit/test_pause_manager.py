"""
Unit tests for PauseStateManager
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from startd8.pause_manager import PauseStateManager, PauseInfo
from startd8.events import EventBus, EventType


@pytest.fixture
def temp_storage_path():
    """Create a temporary storage path for pause state"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "pause_state.json"


@pytest.fixture
def pause_manager(temp_storage_path):
    """Create a PauseStateManager instance with temp storage"""
    return PauseStateManager(storage_path=temp_storage_path)


@pytest.fixture
def clear_event_bus():
    """Clear event bus before and after each test"""
    EventBus.clear()
    yield
    EventBus.clear()


class TestPauseInfo:
    """Test PauseInfo dataclass"""
    
    def test_pause_info_creation(self):
        """Test creating PauseInfo"""
        info = PauseInfo(
            paused=True,
            reason="Testing",
            paused_by="user"
        )
        
        assert info.paused is True
        assert info.reason == "Testing"
        assert info.paused_by == "user"
        assert info.auto_pause is None
    
    def test_pause_info_to_dict(self):
        """Test converting PauseInfo to dictionary"""
        info = PauseInfo(
            paused=True,
            reason="Test reason",
            paused_at="2024-01-01T00:00:00Z",
            paused_by="system",
            auto_pause={"provider": "anthropic"}
        )
        
        data = info.to_dict()
        assert data["paused"] is True
        assert data["reason"] == "Test reason"
        assert data["paused_at"] == "2024-01-01T00:00:00Z"
        assert data["paused_by"] == "system"
        assert data["auto_pause"]["provider"] == "anthropic"
    
    def test_pause_info_from_dict(self):
        """Test creating PauseInfo from dictionary"""
        data = {
            "paused": True,
            "reason": "Test reason",
            "paused_at": "2024-01-01T00:00:00Z",
            "paused_by": "system",
            "auto_pause": {"provider": "anthropic"}
        }
        
        info = PauseInfo.from_dict(data)
        assert info.paused is True
        assert info.reason == "Test reason"
        assert info.paused_by == "system"
        assert info.auto_pause["provider"] == "anthropic"
    
    def test_pause_info_to_dict_omits_none(self):
        """Test that to_dict omits None values"""
        info = PauseInfo(paused=False)
        data = info.to_dict()
        
        assert "reason" not in data
        assert "paused_at" not in data
        assert "auto_pause" not in data


class TestPauseStateManager:
    """Test PauseStateManager functionality"""
    
    def test_initialization(self, pause_manager, temp_storage_path):
        """Test PauseStateManager initialization"""
        assert pause_manager.storage_path == temp_storage_path
        assert len(pause_manager._state) == 0
    
    def test_pause_agent(self, pause_manager, clear_event_bus):
        """Test pausing an agent"""
        result = pause_manager.pause_agent("claude", reason="Testing")
        
        assert result is True
        assert pause_manager.is_paused("claude")
        assert pause_manager.get_pause_reason("claude") == "Testing"
    
    def test_pause_agent_already_paused(self, pause_manager, clear_event_bus):
        """Test pausing an already paused agent returns False"""
        pause_manager.pause_agent("claude")
        result = pause_manager.pause_agent("claude")
        
        assert result is False
    
    def test_resume_agent(self, pause_manager, clear_event_bus):
        """Test resuming a paused agent"""
        pause_manager.pause_agent("claude")
        result = pause_manager.resume_agent("claude")
        
        assert result is True
        assert not pause_manager.is_paused("claude")
    
    def test_resume_not_paused(self, pause_manager, clear_event_bus):
        """Test resuming a non-paused agent returns False"""
        result = pause_manager.resume_agent("claude")
        
        assert result is False
    
    def test_is_paused(self, pause_manager, clear_event_bus):
        """Test checking if agent is paused"""
        assert not pause_manager.is_paused("claude")
        
        pause_manager.pause_agent("claude")
        assert pause_manager.is_paused("claude")
        
        pause_manager.resume_agent("claude")
        assert not pause_manager.is_paused("claude")
    
    def test_get_pause_info(self, pause_manager, clear_event_bus):
        """Test getting pause information"""
        assert pause_manager.get_pause_info("claude") is None
        
        pause_manager.pause_agent("claude", reason="Test reason")
        info = pause_manager.get_pause_info("claude")
        
        assert info is not None
        assert info.paused is True
        assert info.reason == "Test reason"
        assert info.paused_by == "user"
    
    def test_get_pause_reason(self, pause_manager, clear_event_bus):
        """Test getting pause reason"""
        assert pause_manager.get_pause_reason("claude") is None
        
        pause_manager.pause_agent("claude", reason="Test reason")
        assert pause_manager.get_pause_reason("claude") == "Test reason"
    
    def test_list_paused_agents(self, pause_manager, clear_event_bus):
        """Test listing paused agents"""
        assert len(pause_manager.list_paused_agents()) == 0
        
        pause_manager.pause_agent("claude")
        pause_manager.pause_agent("gpt4")
        
        paused = pause_manager.list_paused_agents()
        assert "claude" in paused
        assert "gpt4" in paused
        assert len(paused) == 2
    
    def test_list_auto_paused_agents(self, pause_manager, clear_event_bus):
        """Test listing auto-paused agents"""
        pause_manager.pause_agent("claude", paused_by="user")
        pause_manager.pause_agent("gpt4", paused_by="system")
        
        auto_paused = pause_manager.list_auto_paused_agents()
        assert "gpt4" in auto_paused
        assert "claude" not in auto_paused
        assert len(auto_paused) == 1
    
    def test_get_all_pauses(self, pause_manager, clear_event_bus):
        """Test getting all pause information"""
        pause_manager.pause_agent("claude", reason="Test 1")
        pause_manager.pause_agent("gpt4", reason="Test 2")
        
        all_pauses = pause_manager.get_all_pauses()
        assert "claude" in all_pauses
        assert "gpt4" in all_pauses
        assert all_pauses["claude"]["reason"] == "Test 1"
    
    def test_bulk_pause(self, pause_manager, clear_event_bus):
        """Test pausing multiple agents at once"""
        results = pause_manager.bulk_pause(
            ["claude", "gpt4", "gemini"],
            reason="Bulk pause test"
        )
        
        assert results["claude"] is True
        assert results["gpt4"] is True
        assert results["gemini"] is True
        assert all(pause_manager.is_paused(agent) for agent in ["claude", "gpt4", "gemini"])
    
    def test_bulk_resume(self, pause_manager, clear_event_bus):
        """Test resuming multiple agents at once"""
        pause_manager.pause_agent("claude")
        pause_manager.pause_agent("gpt4")
        
        results = pause_manager.bulk_resume(["claude", "gpt4"])
        
        assert results["claude"] is True
        assert results["gpt4"] is True
        assert not pause_manager.is_paused("claude")
        assert not pause_manager.is_paused("gpt4")
    
    def test_persistence(self, temp_storage_path, clear_event_bus):
        """Test that pause state persists across instances"""
        # Create first manager and pause an agent
        manager1 = PauseStateManager(storage_path=temp_storage_path)
        manager1.pause_agent("claude", reason="Persistent test")
        
        # Create second manager with same storage path
        manager2 = PauseStateManager(storage_path=temp_storage_path)
        
        assert manager2.is_paused("claude")
        assert manager2.get_pause_reason("claude") == "Persistent test"
    
    def test_persistence_file_format(self, pause_manager, clear_event_bus):
        """Test that persistence file has correct format"""
        pause_manager.pause_agent("claude", reason="Test")
        pause_manager.pause_agent("gpt4", paused_by="system", auto_pause_info={"provider": "openai"})
        
        # Read file directly
        with open(pause_manager.storage_path, 'r') as f:
            data = json.load(f)
        
        assert "version" in data
        assert data["version"] == PauseStateManager.SCHEMA_VERSION
        assert "pauses" in data
        assert "claude" in data["pauses"]
        assert "gpt4" in data["pauses"]
        assert data["pauses"]["claude"]["paused_by"] == "user"
        assert data["pauses"]["gpt4"]["paused_by"] == "system"
    
    def test_load_invalid_json(self, temp_storage_path, clear_event_bus):
        """Test loading invalid JSON file"""
        # Write invalid JSON
        temp_storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_storage_path, 'w') as f:
            f.write("invalid json{")
        
        # Should handle gracefully
        manager = PauseStateManager(storage_path=temp_storage_path)
        assert len(manager._state) == 0
    
    def test_load_missing_file(self, temp_storage_path, clear_event_bus):
        """Test loading when file doesn't exist"""
        manager = PauseStateManager(storage_path=temp_storage_path)
        assert len(manager._state) == 0
    
    def test_auto_pause_info(self, pause_manager, clear_event_bus):
        """Test pausing with auto-pause metadata"""
        auto_info = {
            "trigger": "usage_limit_exceeded",
            "provider": "anthropic",
            "usage_percentage": 97.5
        }
        
        pause_manager.pause_agent(
            "claude",
            reason="Usage limit exceeded",
            paused_by="system",
            auto_pause_info=auto_info
        )
        
        info = pause_manager.get_pause_info("claude")
        assert info.paused_by == "system"
        assert info.auto_pause["provider"] == "anthropic"
        assert info.auto_pause["usage_percentage"] == 97.5
    
    def test_event_emission_on_pause(self, pause_manager, clear_event_bus):
        """Test that events are emitted when pausing"""
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        EventBus.subscribe(EventType.AGENT_MANUAL_PAUSED, handler)
        EventBus.subscribe(EventType.AGENT_AUTO_PAUSED, handler)
        
        pause_manager.pause_agent("claude", reason="Test")
        assert len(received_events) == 1
        assert received_events[0].type == EventType.AGENT_MANUAL_PAUSED
        assert received_events[0].data["agent_id"] == "claude"
        
        pause_manager.pause_agent("gpt4", paused_by="system")
        assert len(received_events) == 2
        assert received_events[1].type == EventType.AGENT_AUTO_PAUSED
    
    def test_event_emission_on_resume(self, pause_manager, clear_event_bus):
        """Test that events are emitted when resuming"""
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        EventBus.subscribe(EventType.AGENT_MANUAL_RESUMED, handler)
        EventBus.subscribe(EventType.AGENT_AUTO_RESUMED, handler)
        
        pause_manager.pause_agent("claude")
        pause_manager.resume_agent("claude")
        
        assert len(received_events) == 1
        assert received_events[0].type == EventType.AGENT_MANUAL_RESUMED
        assert received_events[0].data["agent_id"] == "claude"
        
        pause_manager.pause_agent("gpt4", paused_by="system")
        pause_manager.resume_agent("gpt4", resumed_by="system")
        
        assert len(received_events) == 2
        assert received_events[1].type == EventType.AGENT_AUTO_RESUMED
    
    def test_thread_safety(self, pause_manager, clear_event_bus):
        """Test thread safety of pause manager"""
        import threading
        
        results = []
        
        def pause_agent(agent_id):
            result = pause_manager.pause_agent(agent_id)
            results.append((agent_id, result))
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=pause_agent, args=(f"agent_{i}",))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All should succeed
        assert len(results) == 10
        assert all(result for _, result in results)
        assert len(pause_manager.list_paused_agents()) == 10

