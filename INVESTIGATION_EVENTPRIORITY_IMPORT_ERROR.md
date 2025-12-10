# Investigation: EventPriority ImportError on Startup

**Date**: December 7, 2025  
**Status**: Root Cause Identified  
**Severity**: 🔴 Application Won't Start

---

## Summary

The `startd8 tui` command fails immediately with:

```
ImportError: cannot import name 'EventPriority' from 'startd8.events' 
(/Users/neilyashinsky/.../src/startd8/events/__init__.py)
```

**Root Cause**: There are **two conflicting event systems** in the codebase:
1. `events.py` (single file) - contains `EventPriority`
2. `events/` (package directory) - does NOT contain `EventPriority`

Python prioritizes the **package** over the file, so the import fails.

---

## Error Analysis

### Full Traceback
```
Traceback (most recent call last):
  File "/Users/neilyashinsky/.local/bin/startd8", line 3, in <module>
    from startd8.cli import app
  File ".../src/startd8/__init__.py", line 73, in <module>
    from .events import EventBus, Event, EventType, EventPriority
ImportError: cannot import name 'EventPriority' from 'startd8.events'
```

### Python Import Resolution

When you have both:
- `events.py` (module file)
- `events/` (package directory with `__init__.py`)

Python will **always import the package** (`events/`) and ignore the file (`events.py`).

---

## Root Cause Analysis

### Two Event Systems Exist

#### 1. `events.py` (Single File) - Created Dec 8, 22:49
Contains:
```python
class EventPriority(Enum):
    """Event priority levels for persistence"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

class Event(BaseModel):  # Uses Pydantic
    priority: EventPriority = Field(default=EventPriority.NORMAL)
```

**Features**:
- Uses Pydantic models
- Has `EventPriority` enum
- Different `EventType` values (e.g., `AGENT_CALL_STARTED` vs `AGENT_CALL_START`)
- Used by `costs/budget.py` and `costs/tracker.py`

#### 2. `events/` (Package) - Created Dec 8, 23:01
Contains in `__init__.py`:
```python
from .types import Event, EventType, agent_call_start, agent_call_complete, agent_call_error
from .bus import EventBus

__all__ = [
    'Event',
    'EventType',
    'EventBus',
    # ... NO EventPriority!
]
```

**Features**:
- Uses dataclasses
- NO `EventPriority` enum
- Different `EventType` values (e.g., `AGENT_CALL_START` vs `AGENT_CALL_STARTED`)
- NOT used by cost tracking modules

### Timeline
| Time | File | Action |
|------|------|--------|
| Dec 8, 22:49 | `events.py` | Created with `EventPriority` |
| Dec 8, 22:53 | `events/` dir | Package created |
| Dec 8, 23:01 | `events/__init__.py` | Package init created (shadows `events.py`) |

### The Conflict

**`__init__.py` (line 73)** tries to import:
```python
from .events import EventBus, Event, EventType, EventPriority
```

But Python resolves `events` to the **package** (`events/`), which doesn't export `EventPriority`.

**Cost tracking modules** also import from `events`:
```python
# costs/budget.py (line 13)
from ..events import EventBus, Event, EventType, EventPriority
```

---

## Impact

| Component | Status |
|-----------|--------|
| `startd8 tui` | ❌ Won't start |
| `startd8` CLI | ❌ Won't start |
| Python imports | ❌ All fail |
| Cost tracking | ❌ Broken |
| Event system | ⚠️ Two incompatible versions |

---

## Files Affected

### Files That Import `EventPriority`

| File | Line | Import Statement |
|------|------|-----------------|
| `__init__.py` | 73 | `from .events import EventBus, Event, EventType, EventPriority` |
| `costs/budget.py` | 13 | `from ..events import EventBus, Event, EventType, EventPriority` |
| `costs/tracker.py` | 15 | `from ..events import EventBus, Event, EventType, EventPriority` |

### Files That Use `EventPriority`

| File | Lines | Usage |
|------|-------|-------|
| `costs/budget.py` | 98, 131, 152, 233, 248, 262 | `priority=EventPriority.HIGH/CRITICAL/NORMAL` |
| `costs/tracker.py` | 150 | `priority=EventPriority.NORMAL` |

---

# Implementation Plan

## Overview

**Two Options**:
1. **Option A**: Merge `events.py` into `events/` package (recommended)
2. **Option B**: Rename `events.py` to avoid conflict

**Effort**: 1-2 hours  
**Risk**: Medium (affects multiple modules)

---

## Option A: Merge events.py into events/ Package (Recommended)

### Rationale
- The package structure is cleaner and more maintainable
- Consolidates all event functionality
- Follows Python best practices

### Task A.1: Add EventPriority to events/types.py

**File**: `src/startd8/events/types.py`

Add `EventPriority` enum:

```python
class EventPriority(Enum):
    """Event priority levels for persistence"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
```

Add `priority` field to `Event` dataclass:

```python
@dataclass
class Event:
    type: EventType
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None
    priority: EventPriority = EventPriority.NORMAL  # Add this
    
    def should_persist(self) -> bool:
        """Determine if this event should be persisted"""
        return self.priority in (EventPriority.HIGH, EventPriority.CRITICAL)
```

### Task A.2: Export EventPriority from events/__init__.py

**File**: `src/startd8/events/__init__.py`

```python
from .types import Event, EventType, EventPriority, agent_call_start, agent_call_complete, agent_call_error
from .bus import EventBus
from .handlers import LoggingHandler, MetricsHandler, ConsoleProgressHandler

__all__ = [
    'Event',
    'EventType',
    'EventPriority',  # Add this
    'EventBus',
    'LoggingHandler',
    'MetricsHandler',
    'ConsoleProgressHandler',
    'agent_call_start',
    'agent_call_complete',
    'agent_call_error',
]
```

### Task A.3: Synchronize EventType Values

The two files have different event type names. Need to reconcile:

| events.py | events/types.py | Recommendation |
|-----------|-----------------|----------------|
| `AGENT_CALL_STARTED` | `AGENT_CALL_START` | Keep `_START` (shorter) |
| `AGENT_CALL_COMPLETED` | `AGENT_CALL_COMPLETE` | Keep `_COMPLETE` (shorter) |
| `AGENT_CALL_FAILED` | `AGENT_CALL_ERROR` | Keep `_ERROR` (more accurate) |
| `COST_RECORDED` | (missing) | Add to types.py |
| `BUDGET_WARNING` | (missing) | Add to types.py |
| `BUDGET_EXCEEDED` | (missing) | Add to types.py |
| `BUDGET_CREATED` | (missing) | Add to types.py |
| `BUDGET_UPDATED` | (missing) | Add to types.py |
| `BUDGET_DELETED` | (missing) | Add to types.py |

Add missing cost-related event types to `events/types.py`:

```python
class EventType(Enum):
    # ... existing types ...
    
    # Cost tracking events (add these)
    COST_RECORDED = auto()
    BUDGET_WARNING = auto()
    BUDGET_EXCEEDED = auto()
    BUDGET_CREATED = auto()
    BUDGET_UPDATED = auto()
    BUDGET_DELETED = auto()
    
    # System events (add these)
    SYSTEM_ERROR = auto()
    SYSTEM_WARNING = auto()
```

### Task A.4: Update EventBus with Missing Features

The `events.py` version has additional features:
- Event history with persistence
- Max history limit
- Persistence callbacks
- `should_persist()` method

Review `events/bus.py` and add any missing features from `events.py`.

### Task A.5: Delete events.py

After merging all functionality, delete the redundant file:

```bash
rm src/startd8/events.py
```

### Task A.6: Update Cost Module Imports (If Needed)

Verify that `costs/budget.py` and `costs/tracker.py` still work after the merge.

The imports should work unchanged:
```python
from ..events import EventBus, Event, EventType, EventPriority
```

---

## Option B: Rename events.py (Alternative)

### Rationale
- Simpler, less risk of breaking things
- Keeps both event systems separate
- Allows gradual migration

### Task B.1: Rename events.py

```bash
mv src/startd8/events.py src/startd8/event_bus.py
```

### Task B.2: Update __init__.py Import

```python
# Change from:
from .events import EventBus, Event, EventType, EventPriority

# To:
from .event_bus import EventBus, Event, EventType, EventPriority
```

### Task B.3: Update Cost Module Imports

```python
# costs/budget.py and costs/tracker.py
# Change from:
from ..events import EventBus, Event, EventType, EventPriority

# To:
from ..event_bus import EventBus, Event, EventType, EventPriority
```

### Downside
- Two different event systems remain
- Confusing for developers
- Tech debt accumulates

---

## Recommended Approach: Option A

**Why Option A is better**:
1. Single source of truth for events
2. Cleaner architecture
3. No redundant code
4. Better maintainability

---

## Testing Plan

### After Implementation

1. **Import Test**:
```bash
python3 -c "from startd8.events import EventBus, Event, EventType, EventPriority; print('OK')"
```

2. **TUI Startup Test**:
```bash
startd8 tui
```

3. **Cost Tracking Test**:
```python
from startd8.costs import CostTracker, BudgetManager
# Should import without errors
```

4. **Event Emission Test**:
```python
from startd8.events import EventBus, Event, EventType, EventPriority

EventBus.emit(Event(
    type=EventType.COST_RECORDED,
    source="test",
    priority=EventPriority.HIGH,
    data={"amount": 0.01}
))
```

---

## Summary

| Task | Option A | Option B |
|------|----------|----------|
| Risk | Medium | Low |
| Effort | 1-2 hours | 30 minutes |
| Tech Debt | ✅ Eliminated | ⚠️ Increased |
| Maintainability | ✅ High | ⚠️ Medium |

**Recommendation**: Implement **Option A** to properly consolidate the event systems.

---

## Checklist

### Option A Tasks
- [ ] A.1: Add `EventPriority` to `events/types.py`
- [ ] A.2: Export `EventPriority` from `events/__init__.py`
- [ ] A.3: Add missing `EventType` values (cost-related)
- [ ] A.4: Merge `EventBus` features (history, persistence)
- [ ] A.5: Delete `events.py`
- [ ] A.6: Verify cost module imports work
- [ ] Test: Import verification
- [ ] Test: TUI startup
- [ ] Test: Cost tracking

### Acceptance Criteria
- [ ] `startd8 tui` starts without import errors
- [ ] All imports of `EventPriority` succeed
- [ ] Cost tracking modules work correctly
- [ ] Event emission with priority works
- [ ] No redundant event system files

---

**Investigation Complete**: December 7, 2025  
**Ready for Implementation**: Yes
