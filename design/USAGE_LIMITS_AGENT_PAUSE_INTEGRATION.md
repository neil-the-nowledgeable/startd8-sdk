# Usage Limits + Agent Pause Integration
## Design Addendum v1.0

---

## 1. Overview

This document extends the Agent Manual Pause design (`AGENT_MANUAL_PAUSE_UI_PLAN_polished.md`) to support **automatic agent pausing** when API usage limits are reached or approaching critical thresholds.

### 1.1 Purpose

Enable the system to automatically pause agents when:
- Usage limits are **exceeded** (95%+ of limit)
- Usage limits are **critical** (90-95% of limit)
- Configurable thresholds are breached

### 1.2 Benefits

| Benefit | Description |
|---------|-------------|
| **Prevent Rate Limit Errors** | Automatically stop agents before hitting 429 errors |
| **Cost Control** | Prevent runaway costs from agents hitting limits |
| **User Experience** | Graceful degradation instead of hard failures |
| **Observability** | Clear visibility into why agents are paused |

---

## 2. Integration Architecture

### 2.1 Component Interaction

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        USAGE LIMIT MONITORING                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────────┐         Events          ┌──────────────────┐    │
│   │                  │ ───────────────────────▶│                  │    │
│   │ UsageLimitChecker│  USAGE_LIMIT_EXCEEDED   │ AutoPauseHandler │    │
│   │                  │  USAGE_LIMIT_CRITICAL   │                  │    │
│   └──────────────────┘                         └────────┬─────────┘    │
│           │                                             │               │
│           │ check_all_limits()                          │ pause_agent() │
│           ▼                                             ▼               │
│   ┌──────────────────┐                         ┌──────────────────┐    │
│   │                  │                         │                  │    │
│   │    CostStore     │                         │ PauseStateManager│    │
│   │   (Usage Data)   │                         │  (Pause State)   │    │
│   │                  │                         │                  │    │
│   └──────────────────┘                         └──────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

1. **UsageLimitChecker** monitors API usage against provider limits
2. When thresholds are breached, emits `USAGE_LIMIT_*` events
3. **AutoPauseHandler** listens for these events
4. Handler calls **PauseStateManager** to pause affected agents
5. Paused agents are filtered from selection workflows

---

## 3. Extended Data Models

### 3.1 Enhanced Pause State Schema

```json
{
  "version": "1.1",
  "pauses": {
    "claude": {
      "paused": true,
      "reason": "Usage limit exceeded: anthropic requests_per_minute at 97.5%",
      "paused_at": "2025-12-24T15:30:00Z",
      "paused_by": "system",
      "auto_pause": {
        "trigger": "usage_limit_exceeded",
        "provider": "anthropic",
        "limit_type": "requests_per_minute",
        "usage_percentage": 97.5,
        "threshold": 95.0,
        "auto_resume": true,
        "resume_at_percentage": 50.0
      }
    },
    "gpt4": {
      "paused": true,
      "reason": "Usage limit critical: openai tokens_per_minute at 92%",
      "paused_at": "2025-12-24T15:25:00Z",
      "paused_by": "system",
      "auto_pause": {
        "trigger": "usage_limit_critical",
        "provider": "openai",
        "limit_type": "tokens_per_minute",
        "usage_percentage": 92.0,
        "threshold": 90.0,
        "auto_resume": true,
        "resume_at_percentage": 50.0
      }
    },
    "gemini": {
      "paused": true,
      "reason": "Testing new model",
      "paused_at": "2025-12-24T10:00:00Z",
      "paused_by": "user"
    }
  }
}
```

### 3.2 New Fields

| Field | Type | Description |
|-------|------|-------------|
| `paused_by` | `"user"` \| `"system"` | Who initiated the pause |
| `auto_pause` | `object` \| `null` | Auto-pause metadata (null for manual pauses) |
| `auto_pause.trigger` | `string` | Event type that triggered pause |
| `auto_pause.provider` | `string` | Provider whose limit was breached |
| `auto_pause.limit_type` | `string` | Which limit was breached |
| `auto_pause.usage_percentage` | `float` | Usage % when paused |
| `auto_pause.threshold` | `float` | Threshold that was breached |
| `auto_pause.auto_resume` | `bool` | Whether to auto-resume when safe |
| `auto_pause.resume_at_percentage` | `float` | Usage % to resume at |

---

## 4. Configuration

### 4.1 Auto-Pause Configuration

```python
@dataclass
class AutoPauseConfig:
    """Configuration for automatic agent pausing."""
    
    # Enable/disable auto-pause
    enabled: bool = True
    
    # Thresholds for pausing
    pause_on_exceeded: bool = True      # Pause at 95%+
    pause_on_critical: bool = False     # Pause at 90%+ (more aggressive)
    pause_on_warning: bool = False      # Pause at 80%+ (most aggressive)
    
    # Auto-resume settings
    auto_resume_enabled: bool = True
    resume_at_percentage: float = 50.0  # Resume when usage drops to 50%
    
    # Provider-specific overrides
    provider_overrides: Dict[str, Dict] = field(default_factory=dict)
    # Example: {"anthropic": {"pause_on_critical": True}}
```

### 4.2 Default Behavior

| Threshold | Default Action | Configurable |
|-----------|---------------|--------------|
| 80% (Warning) | Log warning, no pause | Yes |
| 90% (Critical) | Log warning, no pause | Yes |
| 95% (Exceeded) | **Auto-pause agents** | Yes |

---

## 5. API Extensions

### 5.1 PauseStateManager Extensions

```python
class PauseStateManager:
    """Extended with auto-pause support."""
    
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
            agent_id: Agent identifier
            reason: Human-readable reason
            paused_by: "user" or "system"
            auto_pause_info: Auto-pause metadata (for system pauses)
            
        Returns:
            True if agent was paused, False if already paused
        """
        pass
    
    def resume_agent(
        self,
        agent_id: str,
        resumed_by: str = "user"
    ) -> bool:
        """
        Resume a paused agent.
        
        Args:
            agent_id: Agent identifier
            resumed_by: "user" or "system"
            
        Returns:
            True if agent was resumed, False if not paused
        """
        pass
    
    def get_auto_paused_agents(self) -> Dict[str, Dict]:
        """Get all agents paused by the system."""
        pass
    
    def get_agents_by_provider(self, provider: str) -> List[str]:
        """Get agent IDs that use a specific provider."""
        pass
    
    def check_auto_resume(self, usage_summary: 'UsageSummary') -> List[str]:
        """
        Check if any auto-paused agents can be resumed.
        
        Args:
            usage_summary: Current usage status
            
        Returns:
            List of agent IDs that were auto-resumed
        """
        pass
```

### 5.2 AutoPauseHandler

```python
class AutoPauseHandler:
    """
    Handles automatic pausing/resuming of agents based on usage limits.
    
    Listens for usage limit events and manages agent pause state.
    """
    
    def __init__(
        self,
        pause_manager: PauseStateManager,
        config: AutoPauseConfig,
        agent_provider_map: Dict[str, str]  # agent_id -> provider
    ):
        self.pause_manager = pause_manager
        self.config = config
        self.agent_provider_map = agent_provider_map
        
        # Register event handlers
        self._register_handlers()
    
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
        """Handle usage limit exceeded event."""
        if not self.config.enabled or not self.config.pause_on_exceeded:
            return
        
        provider = event.data["provider"]
        self._pause_agents_for_provider(
            provider=provider,
            trigger="usage_limit_exceeded",
            event_data=event.data
        )
    
    def _handle_limit_critical(self, event: Event):
        """Handle usage limit critical event."""
        if not self.config.enabled or not self.config.pause_on_critical:
            return
        
        provider = event.data["provider"]
        self._pause_agents_for_provider(
            provider=provider,
            trigger="usage_limit_critical",
            event_data=event.data
        )
    
    def _handle_limit_warning(self, event: Event):
        """Handle usage limit warning event."""
        if not self.config.enabled or not self.config.pause_on_warning:
            return
        
        provider = event.data["provider"]
        self._pause_agents_for_provider(
            provider=provider,
            trigger="usage_limit_warning",
            event_data=event.data
        )
    
    def _pause_agents_for_provider(
        self,
        provider: str,
        trigger: str,
        event_data: Dict
    ):
        """Pause all agents that use the specified provider."""
        agents_to_pause = [
            agent_id for agent_id, agent_provider 
            in self.agent_provider_map.items()
            if agent_provider.lower() == provider.lower()
        ]
        
        for agent_id in agents_to_pause:
            reason = (
                f"Usage limit {trigger.replace('usage_limit_', '')}: "
                f"{provider} {event_data['limit_type']} at "
                f"{event_data['usage_percentage']:.1f}%"
            )
            
            auto_pause_info = {
                "trigger": trigger,
                "provider": provider,
                "limit_type": event_data["limit_type"],
                "usage_percentage": event_data["usage_percentage"],
                "threshold": self._get_threshold_for_trigger(trigger),
                "auto_resume": self.config.auto_resume_enabled,
                "resume_at_percentage": self.config.resume_at_percentage
            }
            
            self.pause_manager.pause_agent(
                agent_id=agent_id,
                reason=reason,
                paused_by="system",
                auto_pause_info=auto_pause_info
            )
    
    def check_and_resume(self, usage_summary: 'UsageSummary'):
        """Check if any auto-paused agents can be resumed."""
        if not self.config.auto_resume_enabled:
            return
        
        resumed = self.pause_manager.check_auto_resume(usage_summary)
        for agent_id in resumed:
            logger.info(f"Auto-resumed agent: {agent_id}")
    
    def _get_threshold_for_trigger(self, trigger: str) -> float:
        """Get the threshold percentage for a trigger type."""
        thresholds = {
            "usage_limit_exceeded": 95.0,
            "usage_limit_critical": 90.0,
            "usage_limit_warning": 80.0
        }
        return thresholds.get(trigger, 95.0)
```

---

## 6. Agent-Provider Mapping

### 6.1 Mapping Strategy

The system needs to know which agents use which providers to pause the correct agents when a provider's limit is breached.

```python
def build_agent_provider_map(agent_configs: List[Dict]) -> Dict[str, str]:
    """
    Build a mapping of agent IDs to their providers.
    
    Args:
        agent_configs: List of agent configuration dictionaries
        
    Returns:
        Dict mapping agent_id -> provider name
    """
    provider_map = {}
    
    # Built-in agents
    builtin_providers = {
        "claude": "anthropic",
        "gpt4": "openai",
        "gpt-4": "openai",
        "gemini": "google",
        "composer": "anthropic",  # Uses Claude under the hood
    }
    
    for config in agent_configs:
        agent_id = config.get("name") or config.get("id")
        
        # Check explicit provider
        if "provider" in config:
            provider_map[agent_id] = config["provider"]
        # Check model name for provider hints
        elif "model" in config:
            model = config["model"].lower()
            if "claude" in model or "anthropic" in model:
                provider_map[agent_id] = "anthropic"
            elif "gpt" in model or "openai" in model:
                provider_map[agent_id] = "openai"
            elif "gemini" in model or "google" in model:
                provider_map[agent_id] = "google"
        # Fall back to built-in mapping
        elif agent_id.lower() in builtin_providers:
            provider_map[agent_id] = builtin_providers[agent_id.lower()]
    
    return provider_map
```

---

## 7. UI Integration

### 7.1 Enhanced Agent Status Table

```
Agent Status Table (with auto-pause indicators):
┌─────────────┬──────────────┬──────────────┬─────────────┬──────────────────────────┐
│ Agent       │ Model        │ Status       │ Actions     │ Pause Reason             │
├─────────────┼──────────────┼──────────────┼─────────────┼──────────────────────────┤
│ Claude      │ claude-3.5   │ ⏸️ Auto-Paused│ [Resume]    │ 🤖 anthropic RPM at 97%  │
│ GPT-4       │ gpt-4-turbo  │ ⏸️ Auto-Paused│ [Resume]    │ 🤖 openai TPM at 92%     │
│ Gemini      │ gemini-1.5   │ ✅ Ready     │ [Pause]     │                          │
│ Composer    │ claude-3.5   │ ⏸️ Paused    │ [Resume]    │ 👤 Testing new model     │
└─────────────┴──────────────┴──────────────┴─────────────┴──────────────────────────┘

Legend: 🤖 = System auto-pause, 👤 = Manual user pause
```

### 7.2 Auto-Pause Notification

When agents are auto-paused, show a notification:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ⚠️  AGENTS AUTO-PAUSED                                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ The following agents have been automatically paused due to         │
│ API usage limits:                                                   │
│                                                                     │
│   • Claude - anthropic requests/minute at 97.5%                    │
│   • Composer - anthropic requests/minute at 97.5%                  │
│                                                                     │
│ These agents will auto-resume when usage drops below 50%.          │
│                                                                     │
│ [View Usage Limits]  [Resume All]  [Dismiss]                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Event Types

### 8.1 New Events

```python
# In events/types.py

class EventType(Enum):
    # ... existing events ...
    
    # Auto-pause events
    AGENT_AUTO_PAUSED = auto()      # Agent was auto-paused by system
    AGENT_AUTO_RESUMED = auto()     # Agent was auto-resumed by system
    AGENT_MANUAL_PAUSED = auto()    # Agent was paused by user
    AGENT_MANUAL_RESUMED = auto()   # Agent was resumed by user
```

### 8.2 Event Data

```python
# AGENT_AUTO_PAUSED event data
{
    "agent_id": "claude",
    "provider": "anthropic",
    "trigger": "usage_limit_exceeded",
    "limit_type": "requests_per_minute",
    "usage_percentage": 97.5,
    "reason": "Usage limit exceeded: anthropic requests_per_minute at 97.5%"
}

# AGENT_AUTO_RESUMED event data
{
    "agent_id": "claude",
    "provider": "anthropic",
    "previous_usage_percentage": 97.5,
    "current_usage_percentage": 45.0,
    "paused_duration_seconds": 300
}
```

---

## 9. Testing Requirements

### 9.1 Unit Tests

| Test Case | Description |
|-----------|-------------|
| `test_auto_pause_on_exceeded` | Verify agents pause at 95%+ usage |
| `test_auto_pause_on_critical` | Verify agents pause at 90%+ when configured |
| `test_no_pause_when_disabled` | Verify no pause when auto-pause disabled |
| `test_auto_resume` | Verify agents resume when usage drops |
| `test_provider_mapping` | Verify correct agents paused per provider |
| `test_manual_override` | Verify manual resume overrides auto-pause |

### 9.2 Integration Tests

| Test Case | Description |
|-----------|-------------|
| `test_end_to_end_auto_pause` | Full flow from usage check to agent pause |
| `test_ui_shows_auto_pause` | Verify UI displays auto-pause correctly |
| `test_selection_filters_auto_paused` | Verify auto-paused agents filtered |
| `test_persistence_across_restart` | Verify auto-pause state persists |

---

## 10. Implementation Phases

### Phase 1: Core Auto-Pause (Priority: High)
- [ ] Extend PauseStateManager with `paused_by` and `auto_pause` fields
- [ ] Create AutoPauseHandler class
- [ ] Register event handlers for usage limit events
- [ ] Implement agent-provider mapping

### Phase 2: Auto-Resume (Priority: Medium)
- [ ] Implement `check_auto_resume()` method
- [ ] Add periodic check for auto-resume conditions
- [ ] Add AGENT_AUTO_RESUMED event

### Phase 3: UI Integration (Priority: Medium)
- [ ] Update agent status table with auto-pause indicators
- [ ] Add auto-pause notification panel
- [ ] Add "Resume All Auto-Paused" action

### Phase 4: Configuration (Priority: Low)
- [ ] Add auto-pause configuration to settings
- [ ] Add provider-specific overrides
- [ ] Add threshold customization

---

## 11. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Rate limit errors prevented | 95% reduction | Error logs |
| Auto-pause latency | < 500ms from event to pause | Metrics |
| Auto-resume accuracy | 100% resume when safe | Integration tests |
| User awareness | 100% see pause notification | UI tests |

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| False positives (unnecessary pauses) | User frustration | Conservative thresholds, easy manual resume |
| Missed pauses (race conditions) | Rate limit errors | Event queue with guaranteed delivery |
| All agents paused | Workflow blocked | Clear UI guidance, quick resume options |
| Config complexity | User confusion | Sensible defaults, simple UI |

---

## 13. Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| UsageLimitChecker | ✅ Complete | `src/startd8/costs/usage_limits.py` |
| Usage Limit Events | ✅ Complete | `USAGE_LIMIT_*` events in `events/types.py` |
| PauseStateManager | 🔄 Needs Extension | Add `paused_by`, `auto_pause` fields |
| Agent Provider Map | ❌ Not Started | Need to build mapping logic |
| AutoPauseHandler | ❌ Not Started | Core integration component |

---

## 14. References

- [Agent Manual Pause Design](./AGENT_MANUAL_PAUSE_UI_PLAN_polished.md)
- [Agent Manual Pause Next Steps](./AGENT_MANUAL_PAUSE_DESIGN_NEXT_STEPS.md)
- [Usage Limits Module](../src/startd8/costs/usage_limits.py)
- [Event Types](../src/startd8/events/types.py)

