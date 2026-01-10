# Rate Limit Header Detection - High Level Design

## Overview

This design document describes the implementation of proactive rate limit detection by extracting and monitoring rate limit headers from API responses. This enables the system to warn users and automatically throttle requests before hitting rate limits, rather than only reacting after a 429 error occurs.

## Goals

1. **Proactive Detection**: Detect when approaching rate limits before hitting them
2. **User Warnings**: Alert users when quota is running low
3. **Auto-Throttling**: Automatically slow down requests when approaching limits
4. **Pipeline Integration**: Integrate with existing pause/resume functionality
5. **Provider Agnostic**: Support multiple API providers (Anthropic, OpenAI, Google)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ ClaudeAgent  │  │  GPT4Agent   │  │ GeminiAgent │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                │
│                    ┌───────▼────────┐                       │
│                    │ Header Extractor│                       │
│                    └───────┬────────┘                       │
└────────────────────────────┼────────────────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │ RateLimitTracker │
                    │  - State Storage │
                    │  - Thresholds    │
                    │  - Warnings     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Event System    │
                    │  - Warnings      │
                    │  - Throttling    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Pipeline/TUI    │
                    │  - User Alerts   │
                    │  - Auto-Pause    │
                    └──────────────────┘
```

## Core Components

### 1. RateLimitInfo Data Class

**Purpose**: Store rate limit information extracted from headers

**Fields**:
- `limit: Optional[int]` - Total requests allowed
- `remaining: Optional[int]` - Remaining requests in window
- `reset_timestamp: Optional[int]` - Unix timestamp when limit resets
- `retry_after: Optional[int]` - Seconds until retry allowed
- `last_updated: datetime` - When this info was last updated
- `provider: str` - Provider name (anthropic, openai, gemini)
- `model: str` - Model identifier

**Methods**:
- `usage_percentage() -> Optional[float]` - Calculate usage percentage
- `is_approaching_limit(threshold: float) -> bool` - Check if approaching threshold
- `seconds_until_reset() -> Optional[int]` - Calculate seconds until reset
- `to_dict() -> Dict` - Serialize for storage

### 2. Header Extractor

**Purpose**: Extract rate limit headers from API response objects

**Responsibilities**:
- Parse common header formats (`X-RateLimit-*`, `Retry-After`)
- Handle provider-specific header variations
- Normalize header names (case-insensitive)
- Extract integer/timestamp values from headers

**Provider-Specific Handling**:
- **OpenAI**: Uses `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-reset`
- **Anthropic**: May use similar headers (needs verification)
- **Google Gemini**: May include quota info in error details (headers TBD)

**Implementation Pattern**:
```python
def extract_rate_limit_headers(response, provider: str, model: str) -> RateLimitInfo:
    """Extract rate limit info from response object"""
    # Try multiple ways to access headers
    headers = _get_headers_from_response(response)
    
    # Parse standard headers
    info = RateLimitInfo(provider=provider, model=model)
    info.limit = _parse_header_int(headers, ['X-RateLimit-Limit', ...])
    info.remaining = _parse_header_int(headers, ['X-RateLimit-Remaining', ...])
    info.reset_timestamp = _parse_header_int(headers, ['X-RateLimit-Reset', ...])
    
    return info
```

### 3. RateLimitTracker

**Purpose**: Track rate limit state across requests and providers

**Responsibilities**:
- Store rate limit state per provider/model combination
- Update state after each API call
- Check thresholds and emit warnings
- Provide state queries for pipeline decisions

**State Storage**:
- In-memory cache: `Dict[str, RateLimitInfo]` keyed by `provider:model`
- Optional persistence: Store in framework storage for cross-session tracking

**Thresholds**:
- **Warning (80%)**: Emit warning event, show in TUI
- **Critical (90%)**: Stronger warning, suggest pausing
- **Emergency (95%)**: Auto-throttle, recommend pause

**Methods**:
- `update_state(provider: str, model: str, info: RateLimitInfo)` - Update state
- `get_state(provider: str, model: str) -> Optional[RateLimitInfo]` - Get current state
- `check_thresholds(provider: str, model: str) -> List[ThresholdWarning]` - Check if thresholds crossed
- `should_throttle(provider: str, model: str) -> bool` - Determine if should throttle

### 4. Integration Points

#### Agent Integration

**Location**: `src/startd8/agents.py`

**Changes**:
- After successful API call, extract headers from response
- Update RateLimitTracker with new state
- Check thresholds and emit warnings if needed

**Pattern**:
```python
# In agent.agenerate() after successful response
response_text, response_time_ms, token_usage = await self._make_api_call(prompt)

# Extract rate limit headers
rate_limit_info = extract_rate_limit_headers(response, self.name, self.model)

# Update tracker
if rate_limit_tracker:
    rate_limit_tracker.update_state(self.name, self.model, rate_limit_info)
    
    # Check thresholds
    warnings = rate_limit_tracker.check_thresholds(self.name, self.model)
    for warning in warnings:
        EventBus.emit(Event(
            type=EventType.RATE_LIMIT_WARNING,
            source=self.name,
            data=warning.to_dict()
        ))
```

#### Pipeline Integration

**Location**: `src/startd8/orchestration.py`

**Changes**:
- Before each pipeline step, check rate limit state
- If approaching limit, warn user or auto-pause
- Integrate with existing pause/resume functionality

**Pattern**:
```python
# Before executing pipeline step
rate_limit_info = rate_limit_tracker.get_state(step.agent.name, step.agent.model)

if rate_limit_info and rate_limit_info.is_approaching_limit(threshold=90.0):
    # Warn user
    EventBus.emit(Event(
        type=EventType.RATE_LIMIT_WARNING,
        source="Pipeline",
        data={
            "pipeline_id": pipeline_id,
            "step_number": i + 1,
            "usage_percentage": rate_limit_info.usage_percentage,
            "remaining": rate_limit_info.remaining,
            "suggestion": "Consider pausing pipeline"
        }
    ))
    
    # Optionally auto-pause if critical
    if rate_limit_info.usage_percentage >= 95.0:
        raise RateLimitWarning(
            f"Rate limit at {rate_limit_info.usage_percentage:.1f}% - auto-pausing",
            can_pause=True
        )
```

#### TUI Integration

**Location**: `src/startd8/tui_improved.py`

**Changes**:
- Display rate limit warnings in pipeline execution
- Show remaining quota in agent selection
- Add proactive pause option when approaching limits

**UI Elements**:
- Warning banner: "⚠ Rate limit at 85% - 12 requests remaining"
- Progress indicator: Show usage percentage
- Pause suggestion: "Consider pausing - rate limit resets in 45s"

## Data Flow

### Successful API Call Flow

```
1. Agent makes API call
   ↓
2. API returns successful response with headers
   ↓
3. Header Extractor parses headers
   ↓
4. RateLimitTracker updates state
   ↓
5. Threshold checker evaluates state
   ↓
6. If threshold crossed:
   - Emit RATE_LIMIT_WARNING event
   - Update TUI display
   - Optionally auto-throttle
```

### Pipeline Execution Flow

```
1. Pipeline starts step execution
   ↓
2. Check rate limit state for agent
   ↓
3. If approaching limit:
   - Show warning to user
   - Offer pause option
   - Continue if user chooses
   ↓
4. Execute API call
   ↓
5. Update rate limit state from response
   ↓
6. If limit hit during call:
   - Raise RateLimitError (existing behavior)
   - Offer pause (existing behavior)
```

## Event System

### New Event Types

**EventType.RATE_LIMIT_WARNING**
- Emitted when usage crosses warning threshold
- Data: `{provider, model, usage_percentage, remaining, reset_timestamp}`

**EventType.RATE_LIMIT_CRITICAL**
- Emitted when usage crosses critical threshold
- Data: Same as warning, with `suggestion: "pause"`

**EventType.RATE_LIMIT_STATE_UPDATE**
- Emitted after each state update
- Data: Full `RateLimitInfo` dict

## Configuration

### Threshold Configuration

```python
# In config or environment
RATE_LIMIT_THRESHOLDS = {
    "warning": 80.0,    # Show warning at 80%
    "critical": 90.0,   # Strong warning at 90%
    "emergency": 95.0,  # Auto-throttle at 95%
}

# Per-provider overrides
PROVIDER_THRESHOLDS = {
    "anthropic": {"warning": 75.0, "critical": 85.0},
    "openai": {"warning": 80.0, "critical": 90.0},
}
```

### Auto-Throttle Configuration

```python
AUTO_THROTTLE_ENABLED = True
AUTO_THROTTLE_THRESHOLD = 95.0
THROTTLE_DELAY_SECONDS = 2.0  # Delay between requests when throttling
```

## Error Handling

### Missing Headers

- **Scenario**: API doesn't provide headers or headers not accessible
- **Handling**: Fall back to client-side tracking (Option 2)
- **Logging**: Log warning that headers unavailable

### Invalid Header Values

- **Scenario**: Headers contain non-numeric or malformed values
- **Handling**: Skip invalid headers, log warning, continue with available data
- **Logging**: Log parsing errors for debugging

### State Staleness

- **Scenario**: Rate limit state is old (e.g., > 5 minutes)
- **Handling**: Treat as unknown state, don't make decisions based on stale data
- **Logging**: Log when using stale state

## Testing Strategy

### Unit Tests

1. **Header Extraction**
   - Test parsing of various header formats
   - Test case-insensitive header matching
   - Test handling of missing headers
   - Test invalid header values

2. **RateLimitTracker**
   - Test state updates
   - Test threshold detection
   - Test state queries
   - Test persistence (if implemented)

3. **Integration Tests**
   - Test agent integration (mock responses with headers)
   - Test pipeline integration (check before steps)
   - Test TUI integration (display warnings)

### Manual Testing

1. **With Real APIs**
   - Test with OpenAI API (known to provide headers)
   - Test with Anthropic API (verify header availability)
   - Test with Gemini API (check header support)

2. **Threshold Testing**
   - Make many requests to approach limits
   - Verify warnings appear at correct thresholds
   - Verify auto-throttle works

## Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Create `RateLimitInfo` data class
- [ ] Implement header extractor
- [ ] Create `RateLimitTracker` class
- [ ] Add unit tests

### Phase 2: Agent Integration (Week 1-2)
- [ ] Integrate with `ClaudeAgent`
- [ ] Integrate with `GPT4Agent`
- [ ] Integrate with `GeminiAgent`
- [ ] Test with real API calls

### Phase 3: Pipeline Integration (Week 2)
- [ ] Add rate limit checks to Pipeline
- [ ] Integrate with pause/resume
- [ ] Add warning events
- [ ] Test pipeline scenarios

### Phase 4: TUI Integration (Week 2-3)
- [ ] Display warnings in TUI
- [ ] Show remaining quota
- [ ] Add proactive pause option
- [ ] User testing

### Phase 5: Auto-Throttling (Week 3)
- [ ] Implement throttling logic
- [ ] Add configuration options
- [ ] Test throttling behavior
- [ ] Performance testing

## Success Metrics

1. **Detection Accuracy**: >90% of rate limits detected before 429 errors
2. **False Positives**: <5% false warnings
3. **User Experience**: Users can proactively pause before hitting limits
4. **Performance**: <10ms overhead per API call

## Future Enhancements

1. **Predictive Modeling**: Predict when limits will be hit based on usage patterns
2. **Multi-Provider Balancing**: Distribute requests across providers when one approaches limit
3. **Historical Analysis**: Track rate limit patterns over time
4. **Dashboard**: Visual dashboard showing rate limit status across providers

## Dependencies

- Existing event system (`EventBus`, `EventType`)
- Existing cost tracking infrastructure
- Agent framework for response object access
- Configuration system for thresholds

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Headers not available | High | Fall back to client-side tracking |
| SDK doesn't expose headers | Medium | Use response wrapper or request hooks |
| Stale state causes issues | Medium | Add staleness checks, TTL on state |
| Performance overhead | Low | Cache state, async updates |
| False warnings | Low | Tune thresholds, add hysteresis |

## Open Questions

1. **Header Availability**: Do all providers expose headers consistently?
2. **SDK Access**: Can we access raw HTTP responses from SDK wrappers?
3. **State Persistence**: Should rate limit state persist across sessions?
4. **Multi-Instance**: How to share state across multiple process instances?

## References

- [RATE_LIMIT_DETECTION_OPTIONS.md](../RATE_LIMIT_DETECTION_OPTIONS.md) - Original options analysis
- [orchestration.py](../../src/startd8/orchestration.py) - Pipeline implementation
- [agents.py](../../src/startd8/agents.py) - Agent implementations
- [events.py](../../src/startd8/events.py) - Event system

