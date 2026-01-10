# Developer Guide: Agent Pausing System

## Getting Started with Agent Pause/Resume

This guide explains how to implement the agent pausing system with automatic usage limit integration.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Components](#core-components)
4. [Implementation Steps](#implementation-steps)
5. [Code Examples](#code-examples)
6. [Testing Your Implementation](#testing-your-implementation)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### What You're Building

The agent pausing system allows:
- **Manual pausing**: Users pause/resume agents via UI
- **Automatic pausing**: System pauses agents when API limits are reached
- **State persistence**: Pause state survives restarts
- **Smart filtering**: Paused agents excluded from workflows

### Architecture at a Glance

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ UsageLimitChecker│────▶│ AutoPauseHandler│────▶│PauseStateManager│
│  (monitors API) │     │ (listens events)│     │ (manages state) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  pause_state.json│
                                                │   (persistence) │
                                                └─────────────────┘
```

---

## Quick Start

### Step 1: Create the PauseStateManager

Create `src/startd8/pause_manager.py`:

```python
"""
Agent Pause State Manager

Manages pause/resume state for agents with persistence.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field, asdict
import threading

from .paths import default_config_dir
from .logging_config import get_logger
from .events import EventBus, Event, EventType, EventPriority

logger = get_logger(__name__)


@dataclass
class PauseInfo:
    """Information about a paused agent."""
    paused: bool = False
    reason: Optional[str] = None
    paused_at: Optional[str] = None
    paused_by: str = "user"  # "user" or "system"
    auto_pause: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PauseInfo':
        return cls(
            paused=data.get("paused", False),
            reason=data.get("reason"),
            paused_at=data.get("paused_at"),
            paused_by=data.get("paused_by", "user"),
            auto_pause=data.get("auto_pause")
        )


class PauseStateManager:
    """
    Manages agent pause states with file-based persistence.
    
    Example:
        manager = PauseStateManager()
        
        # Pause an agent
        manager.pause_agent("claude", reason="Testing")
        
        # Check if paused
        if manager.is_paused("claude"):
            print("Claude is paused")
        
        # Resume
        manager.resume_agent("claude")
    """
    
    SCHEMA_VERSION = "1.1"
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the pause state manager.
        
        Args:
            storage_path: Path to pause state file. Defaults to 
                          ~/.startd8/pause_state.json
        """
        if storage_path is None:
            storage_path = default_config_dir() / "pause_state.json"
        
        self.storage_path = Path(storage_path)
        self._state: Dict[str, PauseInfo] = {}
        self._lock = threading.RLock()
        
        # Load existing state
        self._load_state()
        
        logger.info(f"PauseStateManager initialized: {self.storage_path}")
    
    def _load_state(self) -> None:
        """Load pause state from storage file."""
        if not self.storage_path.exists():
            logger.debug("No existing pause state file, starting fresh")
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            # Validate schema version
            version = data.get("version", "1.0")
            pauses = data.get("pauses", {})
            
            for agent_id, pause_data in pauses.items():
                self._state[agent_id] = PauseInfo.from_dict(pause_data)
            
            logger.info(f"Loaded pause state: {len(self._state)} agents")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid pause state file: {e}")
        except Exception as e:
            logger.error(f"Error loading pause state: {e}")
    
    def _save_state(self) -> None:
        """Save pause state to storage file."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "version": self.SCHEMA_VERSION,
                "pauses": {
                    agent_id: info.to_dict()
                    for agent_id, info in self._state.items()
                }
            }
            
            # Atomic write using temp file
            temp_path = self.storage_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_path.replace(self.storage_path)
            logger.debug(f"Saved pause state: {len(self._state)} agents")
            
        except Exception as e:
            logger.error(f"Error saving pause state: {e}")
    
    def pause_agent(
        self,
        agent_id: str,
        reason: Optional[str] = None,
        paused_by: str = "user",
        auto_pause_info: Optional[Dict] = None
    ) -> bool:
        """
        Pause an agent.
        
        Args:
            agent_id: Unique agent identifier
            reason: Human-readable reason for pausing
            paused_by: "user" for manual, "system" for automatic
            auto_pause_info: Metadata for automatic pauses
            
        Returns:
            True if agent was paused, False if already paused
        """
        with self._lock:
            # Check if already paused
            if agent_id in self._state and self._state[agent_id].paused:
                logger.debug(f"Agent {agent_id} already paused")
                return False
            
            # Create pause info
            pause_info = PauseInfo(
                paused=True,
                reason=reason,
                paused_at=datetime.now(timezone.utc).isoformat(),
                paused_by=paused_by,
                auto_pause=auto_pause_info
            )
            
            self._state[agent_id] = pause_info
            self._save_state()
            
            # Emit event
            event_type = (
                EventType.AGENT_AUTO_PAUSED if paused_by == "system"
                else EventType.AGENT_MANUAL_PAUSED
            )
            
            EventBus.emit(Event(
                type=event_type,
                source="PauseStateManager",
                priority=EventPriority.HIGH,
                data={
                    "agent_id": agent_id,
                    "reason": reason,
                    "paused_by": paused_by,
                    "auto_pause_info": auto_pause_info
                }
            ))
            
            logger.info(f"Paused agent: {agent_id} (by {paused_by})")
            return True
    
    def resume_agent(
        self,
        agent_id: str,
        resumed_by: str = "user"
    ) -> bool:
        """
        Resume a paused agent.
        
        Args:
            agent_id: Unique agent identifier
            resumed_by: "user" for manual, "system" for automatic
            
        Returns:
            True if agent was resumed, False if not paused
        """
        with self._lock:
            if agent_id not in self._state or not self._state[agent_id].paused:
                logger.debug(f"Agent {agent_id} not paused")
                return False
            
            # Store info for event
            was_auto_paused = self._state[agent_id].paused_by == "system"
            
            # Clear pause state
            self._state[agent_id] = PauseInfo(paused=False)
            self._save_state()
            
            # Emit event
            event_type = (
                EventType.AGENT_AUTO_RESUMED if resumed_by == "system"
                else EventType.AGENT_MANUAL_RESUMED
            )
            
            EventBus.emit(Event(
                type=event_type,
                source="PauseStateManager",
                priority=EventPriority.NORMAL,
                data={
                    "agent_id": agent_id,
                    "resumed_by": resumed_by,
                    "was_auto_paused": was_auto_paused
                }
            ))
            
            logger.info(f"Resumed agent: {agent_id} (by {resumed_by})")
            return True
    
    def is_paused(self, agent_id: str) -> bool:
        """Check if an agent is paused."""
        with self._lock:
            return (
                agent_id in self._state and 
                self._state[agent_id].paused
            )
    
    def get_pause_info(self, agent_id: str) -> Optional[PauseInfo]:
        """Get pause information for an agent."""
        with self._lock:
            return self._state.get(agent_id)
    
    def get_pause_reason(self, agent_id: str) -> Optional[str]:
        """Get the pause reason for an agent."""
        with self._lock:
            if agent_id in self._state:
                return self._state[agent_id].reason
            return None
    
    def list_paused_agents(self) -> List[str]:
        """Get list of all paused agent IDs."""
        with self._lock:
            return [
                agent_id for agent_id, info in self._state.items()
                if info.paused
            ]
    
    def list_auto_paused_agents(self) -> List[str]:
        """Get list of agents paused by the system."""
        with self._lock:
            return [
                agent_id for agent_id, info in self._state.items()
                if info.paused and info.paused_by == "system"
            ]
    
    def get_all_pauses(self) -> Dict[str, Dict]:
        """Get all pause information as a dictionary."""
        with self._lock:
            return {
                agent_id: info.to_dict()
                for agent_id, info in self._state.items()
                if info.paused
            }
    
    def bulk_pause(
        self,
        agent_ids: List[str],
        reason: Optional[str] = None,
        paused_by: str = "user"
    ) -> Dict[str, bool]:
        """
        Pause multiple agents at once.
        
        Returns:
            Dict mapping agent_id to success status
        """
        results = {}
        for agent_id in agent_ids:
            results[agent_id] = self.pause_agent(
                agent_id, reason=reason, paused_by=paused_by
            )
        return results
    
    def bulk_resume(
        self,
        agent_ids: List[str],
        resumed_by: str = "user"
    ) -> Dict[str, bool]:
        """
        Resume multiple agents at once.
        
        Returns:
            Dict mapping agent_id to success status
        """
        results = {}
        for agent_id in agent_ids:
            results[agent_id] = self.resume_agent(
                agent_id, resumed_by=resumed_by
            )
        return results
```

### Step 2: Add Event Types

Add these to `src/startd8/events/types.py`:

```python
# Add to EventType enum:

    # Agent pause events
    AGENT_AUTO_PAUSED = auto()      # Agent was auto-paused by system
    AGENT_AUTO_RESUMED = auto()     # Agent was auto-resumed by system
    AGENT_MANUAL_PAUSED = auto()    # Agent was paused by user
    AGENT_MANUAL_RESUMED = auto()   # Agent was resumed by user
```

### Step 3: Create the AutoPauseHandler

Create `src/startd8/auto_pause_handler.py`:

**Note**: This file also includes the `build_agent_provider_map()` helper function for dynamically building agent-provider mappings from agent structures.

```python
"""
Auto-Pause Handler

Automatically pauses agents when API usage limits are breached.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .pause_manager import PauseStateManager
from .events import EventBus, Event, EventType
from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class AutoPauseConfig:
    """Configuration for automatic agent pausing."""
    
    enabled: bool = True
    pause_on_exceeded: bool = True      # Pause at 95%+
    pause_on_critical: bool = False     # Pause at 90%+
    pause_on_warning: bool = False      # Pause at 80%+
    auto_resume_enabled: bool = True
    resume_at_percentage: float = 50.0


class AutoPauseHandler:
    """
    Handles automatic pausing of agents based on usage limits.
    
    Example:
        pause_manager = PauseStateManager()
        agent_provider_map = {"claude": "anthropic", "gpt4": "openai"}
        
        handler = AutoPauseHandler(
            pause_manager=pause_manager,
            agent_provider_map=agent_provider_map
        )
        
        # Handler automatically listens for usage limit events
        # and pauses agents when limits are breached
    """
    
    def __init__(
        self,
        pause_manager: PauseStateManager,
        agent_provider_map: Dict[str, str],
        config: Optional[AutoPauseConfig] = None
    ):
        """
        Initialize the auto-pause handler.
        
        Args:
            pause_manager: PauseStateManager instance
            agent_provider_map: Dict mapping agent_id -> provider name
            config: Auto-pause configuration
        """
        self.pause_manager = pause_manager
        self.agent_provider_map = agent_provider_map
        self.config = config or AutoPauseConfig()
        
        # Register event handlers
        self._register_handlers()
        
        logger.info("AutoPauseHandler initialized")
    
    def _register_handlers(self):
        """Register handlers for usage limit events."""
        EventBus.subscribe(
            EventType.USAGE_LIMIT_EXCEEDED,
            self._handle_limit_exceeded
        )
        EventBus.subscribe(
            EventType.USAGE_LIMIT_CRITICAL,
            self._handle_limit_critical
        )
        EventBus.subscribe(
            EventType.USAGE_LIMIT_WARNING,
            self._handle_limit_warning
        )
    
    def _handle_limit_exceeded(self, event: Event):
        """Handle usage limit exceeded (95%+) event."""
        if not self.config.enabled or not self.config.pause_on_exceeded:
            return
        
        self._pause_agents_for_provider(
            provider=event.data["provider"],
            trigger="exceeded",
            event_data=event.data
        )
    
    def _handle_limit_critical(self, event: Event):
        """Handle usage limit critical (90%+) event."""
        if not self.config.enabled or not self.config.pause_on_critical:
            return
        
        self._pause_agents_for_provider(
            provider=event.data["provider"],
            trigger="critical",
            event_data=event.data
        )
    
    def _handle_limit_warning(self, event: Event):
        """Handle usage limit warning (80%+) event."""
        if not self.config.enabled or not self.config.pause_on_warning:
            return
        
        self._pause_agents_for_provider(
            provider=event.data["provider"],
            trigger="warning",
            event_data=event.data
        )
    
    def _pause_agents_for_provider(
        self,
        provider: str,
        trigger: str,
        event_data: Dict
    ):
        """Pause all agents that use the specified provider."""
        # Find agents using this provider
        agents_to_pause = [
            agent_id for agent_id, agent_provider 
            in self.agent_provider_map.items()
            if agent_provider.lower() == provider.lower()
        ]
        
        if not agents_to_pause:
            logger.debug(f"No agents found for provider: {provider}")
            return
        
        logger.info(
            f"Auto-pausing {len(agents_to_pause)} agents for {provider} "
            f"({trigger}: {event_data.get('usage_percentage', 0):.1f}%)"
        )
        
        for agent_id in agents_to_pause:
            reason = (
                f"Usage limit {trigger}: {provider} "
                f"{event_data.get('limit_type', 'unknown')} at "
                f"{event_data.get('usage_percentage', 0):.1f}%"
            )
            
            auto_pause_info = {
                "trigger": f"usage_limit_{trigger}",
                "provider": provider,
                "limit_type": event_data.get("limit_type"),
                "usage_percentage": event_data.get("usage_percentage"),
                "auto_resume": self.config.auto_resume_enabled,
                "resume_at_percentage": self.config.resume_at_percentage
            }
            
            self.pause_manager.pause_agent(
                agent_id=agent_id,
                reason=reason,
                paused_by="system",
                auto_pause_info=auto_pause_info
            )
    
    def check_and_resume(self, usage_summary: 'UsageSummary') -> List[str]:
        """
        Check if any auto-paused agents can be resumed.
        
        Call this periodically or after checking usage limits.
        
        Args:
            usage_summary: Current usage summary from UsageLimitChecker
            
        Returns:
            List of agent IDs that were resumed
        """
        if not self.config.auto_resume_enabled:
            return []
        
        resumed = []
        auto_paused = self.pause_manager.list_auto_paused_agents()
        
        for agent_id in auto_paused:
            pause_info = self.pause_manager.get_pause_info(agent_id)
            if not pause_info or not pause_info.auto_pause:
                continue
            
            provider = pause_info.auto_pause.get("provider")
            resume_threshold = pause_info.auto_pause.get(
                "resume_at_percentage", 
                self.config.resume_at_percentage
            )
            
            # Check if provider usage is now below threshold
            if provider and provider in usage_summary.provider_statuses:
                statuses = usage_summary.provider_statuses[provider]
                
                # Check if all limits for this provider are below threshold
                all_below = all(
                    status.usage_percentage < resume_threshold
                    for status in statuses
                )
                
                if all_below:
                    self.pause_manager.resume_agent(
                        agent_id=agent_id,
                        resumed_by="system"
                    )
                    resumed.append(agent_id)
                    logger.info(f"Auto-resumed agent: {agent_id}")
        
        return resumed
    
    def update_agent_provider_map(self, agent_provider_map: Dict[str, str]):
        """Update the agent-to-provider mapping."""
        self.agent_provider_map = agent_provider_map
```

---

## Implementation Steps

### Step-by-Step Checklist

#### Phase 1: Core Pause Manager
- [x] Create `src/startd8/pause_manager.py` with `PauseStateManager` class
- [x] Add pause event types to `src/startd8/events/types.py`
- [x] Add unit tests for `PauseStateManager`
- [x] Test manual pause/resume functionality

#### Phase 2: Auto-Pause Handler
- [x] Create `src/startd8/auto_pause_handler.py`
- [x] Implement agent-provider mapping logic (`build_agent_provider_map()` helper)
- [x] Register event handlers for usage limit events
- [x] Test auto-pause triggers

#### Phase 3: TUI Integration
- [x] Add pause status to agent status table
- [x] Filter paused agents from `_get_ready_agents_for_selection()`
- [x] Add "Manage Agent Pauses" menu option
- [x] Add pause/resume functionality to agent management

#### Phase 4: Auto-Resume
- [x] Implement `check_and_resume()` method
- [x] Integrate auto-resume into `UsageLimitChecker.check_all_limits()`
- [x] Test auto-resume functionality
- [x] Initialize AutoPauseHandler as singleton in TUI

---

## Code Examples

### Example 1: Basic Pause/Resume

```python
from startd8.pause_manager import PauseStateManager

# Initialize
manager = PauseStateManager()

# Pause an agent
manager.pause_agent("claude", reason="Testing new model")

# Check status
if manager.is_paused("claude"):
    print(f"Claude is paused: {manager.get_pause_reason('claude')}")

# Resume
manager.resume_agent("claude")
```

### Example 2: Filter Paused Agents from Selection

```python
def _get_ready_agents_for_selection(self) -> List[Dict]:
    """Get list of agents ready for selection (excluding paused)."""
    
    # Initialize pause manager
    pause_manager = PauseStateManager()
    
    all_agents = self._get_all_agents()
    ready_agents = []
    
    for agent in all_agents:
        agent_id = agent.get("name") or agent.get("id")
        
        # Skip paused agents
        if pause_manager.is_paused(agent_id):
            continue
        
        # Check if agent is ready (has API key, etc.)
        if self._is_agent_ready(agent):
            ready_agents.append(agent)
    
    return ready_agents
```

### Example 3: Initialize Auto-Pause Handler

```python
from startd8.pause_manager import PauseStateManager
from startd8.auto_pause_handler import (
    AutoPauseHandler, 
    AutoPauseConfig,
    initialize_auto_pause_handler,
    build_agent_provider_map
)

# Option 1: Manual initialization
pause_manager = PauseStateManager()
agent_provider_map = {
    "claude": "anthropic",
    "gpt4": "openai",
    "gemini": "google",
    "composer": "anthropic",
}

config = AutoPauseConfig(
    enabled=True,
    pause_on_exceeded=True,
    pause_on_critical=False,
    auto_resume_enabled=True,
    resume_at_percentage=50.0
)

handler = AutoPauseHandler(
    pause_manager=pause_manager,
    agent_provider_map=agent_provider_map,
    config=config
)

# Option 2: Singleton pattern (recommended)
# Initialize once, then access via get_auto_pause_handler()
from startd8.auto_pause_handler import get_auto_pause_handler

# Build agent-provider map dynamically from agent list
agents = [...]  # Your agent list from _build_unified_agent_list()
agent_provider_map = build_agent_provider_map(agents)

handler = initialize_auto_pause_handler(
    pause_manager=pause_manager,
    agent_provider_map=agent_provider_map,
    config=config
)

# Later, get the singleton instance
handler = get_auto_pause_handler()
```

### Example 4: Check Usage and Auto-Resume

```python
from startd8.costs.usage_limits import UsageLimitChecker
from startd8.costs.store import CostStore
from startd8.paths import default_data_dir
from startd8.auto_pause_handler import get_auto_pause_handler

# Initialize
store = CostStore(default_data_dir() / "costs.db")
checker = UsageLimitChecker(store)

# Get auto-pause handler singleton
handler = get_auto_pause_handler()

# Check usage limits (auto-resume is called automatically if handler is provided)
summary = checker.check_all_limits(auto_pause_handler=handler)

# Or manually check and resume
if handler:
    resumed = handler.check_and_resume(summary)
    if resumed:
        print(f"Auto-resumed agents: {resumed}")
```

### Example 5: Display Pause Status in Agent Table

```python
def show_agent_status_table(self):
    """Show agent status table with pause information."""
    from rich.table import Table
    
    pause_manager = PauseStateManager()
    
    table = Table(title="Agent Status")
    table.add_column("Agent", style="cyan")
    table.add_column("Model")
    table.add_column("Status", justify="center")
    table.add_column("Pause Reason")
    
    for agent in self.get_all_agents():
        agent_id = agent.get("name")
        
        if pause_manager.is_paused(agent_id):
            info = pause_manager.get_pause_info(agent_id)
            
            # Determine status icon
            if info.paused_by == "system":
                status = "⏸️ Auto-Paused"
                icon = "🤖"
            else:
                status = "⏸️ Paused"
                icon = "👤"
            
            reason = f"{icon} {info.reason or 'No reason'}"
        else:
            status = "✅ Ready"
            reason = ""
        
        table.add_row(
            agent_id,
            agent.get("model", "unknown"),
            status,
            reason
        )
    
    self.console.print(table)
```

---

## Testing Your Implementation

### Unit Test Example

```python
# tests/test_pause_manager.py

import pytest
from pathlib import Path
import tempfile

from startd8.pause_manager import PauseStateManager


@pytest.fixture
def pause_manager():
    """Create a pause manager with temp storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "pause_state.json"
        yield PauseStateManager(storage_path=storage_path)


def test_pause_agent(pause_manager):
    """Test pausing an agent."""
    result = pause_manager.pause_agent("claude", reason="Testing")
    
    assert result is True
    assert pause_manager.is_paused("claude")
    assert pause_manager.get_pause_reason("claude") == "Testing"


def test_resume_agent(pause_manager):
    """Test resuming an agent."""
    pause_manager.pause_agent("claude")
    result = pause_manager.resume_agent("claude")
    
    assert result is True
    assert not pause_manager.is_paused("claude")


def test_already_paused(pause_manager):
    """Test pausing already paused agent returns False."""
    pause_manager.pause_agent("claude")
    result = pause_manager.pause_agent("claude")
    
    assert result is False


def test_not_paused_resume(pause_manager):
    """Test resuming non-paused agent returns False."""
    result = pause_manager.resume_agent("claude")
    
    assert result is False


def test_persistence(pause_manager):
    """Test pause state persists."""
    pause_manager.pause_agent("claude", reason="Test")
    
    # Create new manager with same storage
    new_manager = PauseStateManager(
        storage_path=pause_manager.storage_path
    )
    
    assert new_manager.is_paused("claude")
    assert new_manager.get_pause_reason("claude") == "Test"


def test_auto_pause_info(pause_manager):
    """Test auto-pause with metadata."""
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


def test_list_paused_agents(pause_manager):
    """Test listing paused agents."""
    pause_manager.pause_agent("claude")
    pause_manager.pause_agent("gpt4")
    
    paused = pause_manager.list_paused_agents()
    
    assert "claude" in paused
    assert "gpt4" in paused
    assert len(paused) == 2
```

### Integration Test Example

```python
# tests/test_auto_pause_integration.py

import pytest
from startd8.pause_manager import PauseStateManager
from startd8.auto_pause_handler import AutoPauseHandler, AutoPauseConfig
from startd8.events import EventBus, Event, EventType, EventPriority


@pytest.fixture
def setup_auto_pause(tmp_path):
    """Set up auto-pause handler for testing."""
    pause_manager = PauseStateManager(
        storage_path=tmp_path / "pause_state.json"
    )
    
    agent_provider_map = {
        "claude": "anthropic",
        "gpt4": "openai",
    }
    
    handler = AutoPauseHandler(
        pause_manager=pause_manager,
        agent_provider_map=agent_provider_map,
        config=AutoPauseConfig(
            enabled=True,
            pause_on_exceeded=True
        )
    )
    
    return pause_manager, handler


def test_auto_pause_on_exceeded(setup_auto_pause):
    """Test agents are auto-paused when limit exceeded."""
    pause_manager, handler = setup_auto_pause
    
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
    
    # Claude should be paused (uses anthropic)
    assert pause_manager.is_paused("claude")
    
    # GPT-4 should NOT be paused (uses openai)
    assert not pause_manager.is_paused("gpt4")
    
    # Check pause reason
    info = pause_manager.get_pause_info("claude")
    assert info.paused_by == "system"
    assert "anthropic" in info.reason
```

---

## Troubleshooting

### Common Issues

#### 1. Pause state not persisting

**Symptom**: Paused agents appear ready after restart

**Solution**: Check file permissions and storage path
```python
# Verify storage path
manager = PauseStateManager()
print(f"Storage path: {manager.storage_path}")
print(f"Exists: {manager.storage_path.exists()}")
```

#### 2. Auto-pause not triggering

**Symptom**: Agents not paused when limits exceeded

**Checklist**:
- [ ] AutoPauseHandler initialized?
- [ ] `config.enabled = True`?
- [ ] `config.pause_on_exceeded = True`?
- [ ] Agent in `agent_provider_map`?
- [ ] Provider name matches (case-insensitive)?

```python
# Debug auto-pause
print(f"Config enabled: {handler.config.enabled}")
print(f"Pause on exceeded: {handler.config.pause_on_exceeded}")
print(f"Agent map: {handler.agent_provider_map}")
```

#### 3. Wrong agents being paused

**Symptom**: Agents paused for wrong provider

**Solution**: Check agent-provider mapping
```python
# Verify mapping
for agent_id, provider in handler.agent_provider_map.items():
    print(f"{agent_id} -> {provider}")
```

#### 4. Auto-resume not working

**Symptom**: Agents stay paused even when usage drops

**Solution**: 
- Ensure `check_and_resume()` is called periodically
- Verify `auto_resume_enabled = True` in config
- Check `resume_at_percentage` threshold

---

## File Structure

After implementation, your project should have:

```
src/startd8/
├── pause_manager.py          # NEW: PauseStateManager
├── auto_pause_handler.py     # NEW: AutoPauseHandler
├── costs/
│   └── usage_limits.py       # EXISTING: UsageLimitChecker
├── events/
│   └── types.py              # MODIFIED: Add pause events
└── tui_improved.py           # MODIFIED: Add pause UI

tests/
├── unit/
│   └── test_pause_manager.py     # NEW: Unit tests for PauseStateManager
└── integration/
    └── test_auto_pause_handler.py  # NEW: Integration tests for AutoPauseHandler

~/.startd8/
└── pause_state.json          # CREATED: Pause state storage (config directory)
```

---

## Implementation Status

✅ **COMPLETE** - All phases have been implemented and tested.

### Completed Features

1. ✅ **PauseStateManager**: Full implementation with persistence and event emission
2. ✅ **AutoPauseHandler**: Automatic pausing based on usage limits with configurable thresholds
3. ✅ **TUI Integration**: Complete pause management interface with status display
4. ✅ **Auto-Resume**: Integrated into usage limit checking workflow
5. ✅ **Tests**: Comprehensive unit and integration tests
6. ✅ **Singleton Pattern**: AutoPauseHandler initialized as singleton for framework-wide access

### Key Implementation Details

- **Storage Location**: Pause state is stored in `~/.startd8/pause_state.json` (config directory)
- **Singleton Pattern**: Use `initialize_auto_pause_handler()` and `get_auto_pause_handler()` for framework-wide access
- **Dynamic Mapping**: `build_agent_provider_map()` helper function builds agent-provider mappings from agent structures
- **Auto-Resume Integration**: Automatically called when `UsageLimitChecker.check_all_limits()` is invoked with the handler

## Next Steps

1. ✅ **Implement Phase 1**: Create `PauseStateManager` and add event types - **DONE**
2. ✅ **Write tests**: Add unit tests for pause manager - **DONE**
3. ✅ **Implement Phase 2**: Create `AutoPauseHandler` - **DONE**
4. ✅ **Integrate with TUI**: Add pause UI to agent management - **DONE**
5. ✅ **Test end-to-end**: Verify auto-pause triggers correctly - **DONE**

### Usage

The system is ready to use! Agents will automatically pause when API usage limits are exceeded, and can be manually managed through the TUI's "Manage Agent Pauses" menu option.

---

## References

- [Usage Limits + Agent Pause Integration Design](../design/USAGE_LIMITS_AGENT_PAUSE_INTEGRATION.md)
- [Agent Manual Pause Design](../AGENT_MANUAL_PAUSE_UI_PLAN_polished.md)
- [Usage Limits Module](../src/startd8/costs/usage_limits.py)

