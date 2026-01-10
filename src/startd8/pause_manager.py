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
                          ~/.startd8/data/pause_state.json
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

