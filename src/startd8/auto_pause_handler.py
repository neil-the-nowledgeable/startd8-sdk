"""
Auto-Pause Handler

Automatically pauses agents when API usage limits are breached.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .pause_manager import PauseStateManager
from .events import EventBus, Event, EventType
from .logging_config import get_logger

logger = get_logger(__name__)


def build_agent_provider_map(agents: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Build agent-to-provider mapping from agent list.
    
    Extracts provider information from agent structures:
    - Built-in agents: Maps builtin_type to provider name
    - Custom agents: Uses provider field or type field
    
    Args:
        agents: List of agent dictionaries from _build_unified_agent_list()
        
    Returns:
        Dict mapping agent_id (name) -> provider name
        
    Example:
        agents = [
            {'name': 'Claude', 'builtin_type': 'claude', 'type': 'builtin'},
            {'name': 'GPT-4', 'builtin_type': 'gpt4', 'type': 'builtin'},
            {'name': 'MyAgent', 'provider': 'anthropic', 'type': 'custom'}
        ]
        mapping = build_agent_provider_map(agents)
        # {'Claude': 'anthropic', 'GPT-4': 'openai', 'MyAgent': 'anthropic'}
    """
    mapping = {}
    
    # Mapping from builtin_type to provider name
    builtin_provider_map = {
        'claude': 'anthropic',
        'gpt4': 'openai',
        'mock': 'mock',
        'gemini': 'google',
    }
    
    for agent in agents:
        agent_id = agent.get('name')
        if not agent_id:
            continue
        
        agent_type = agent.get('type', '')
        
        # Handle built-in agents
        if agent_type == 'builtin':
            builtin_type = agent.get('builtin_type')
            if builtin_type in builtin_provider_map:
                mapping[agent_id] = builtin_provider_map[builtin_type]
        
        # Handle custom agents
        elif agent_type == 'custom':
            # Try provider field first
            provider = agent.get('provider')
            if not provider:
                # Fall back to type field from custom_config
                custom_config = agent.get('custom_config', {})
                provider = custom_config.get('provider') or custom_config.get('type')
            
            if provider:
                # Normalize provider name (some might be 'anthropic', others 'claude')
                provider_normalized = provider.lower()
                if provider_normalized == 'claude':
                    provider_normalized = 'anthropic'
                elif provider_normalized in ['gpt', 'gpt4', 'gpt-4']:
                    provider_normalized = 'openai'
                elif provider_normalized == 'gemini':
                    provider_normalized = 'google'
                
                mapping[agent_id] = provider_normalized
    
    return mapping


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


# Singleton instance
_auto_pause_handler: Optional[AutoPauseHandler] = None


def get_auto_pause_handler() -> Optional[AutoPauseHandler]:
    """Get the singleton AutoPauseHandler instance."""
    return _auto_pause_handler


def initialize_auto_pause_handler(
    pause_manager: PauseStateManager,
    agent_provider_map: Dict[str, str],
    config: Optional[AutoPauseConfig] = None
) -> AutoPauseHandler:
    """
    Initialize the singleton AutoPauseHandler instance.
    
    This should be called once during framework initialization.
    
    Args:
        pause_manager: PauseStateManager instance
        agent_provider_map: Dict mapping agent_id -> provider name
        config: Auto-pause configuration
        
    Returns:
        The initialized AutoPauseHandler instance
    """
    global _auto_pause_handler
    
    if _auto_pause_handler is not None:
        logger.warning("AutoPauseHandler already initialized, updating agent-provider map")
        _auto_pause_handler.update_agent_provider_map(agent_provider_map)
        return _auto_pause_handler
    
    _auto_pause_handler = AutoPauseHandler(
        pause_manager=pause_manager,
        agent_provider_map=agent_provider_map,
        config=config
    )
    
    logger.info("AutoPauseHandler singleton initialized")
    return _auto_pause_handler

