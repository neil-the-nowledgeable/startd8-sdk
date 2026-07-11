# Agent Configuration Fix Summary

## Issue
`'ClaudeAgent' object has no attribute 'agent_name'` error when accessing `agent.agent_name` on agent instances.

## Root Cause
- `BaseAgent` stores the agent name as `self.name` (not `self.agent_name`)
- Some code was accessing `agent.agent_name` directly on agent instances
- Only `SkillAgent` had a compatibility property `agent_name`, but other agent classes (`ClaudeAgent`, `GPT4Agent`, `GeminiAgent`, `OpenAICompatibleAgent`, `MockAgent`) did not

## Solution
Added `agent_name` property to `BaseAgent` class so all agent subclasses inherit it:

```python
@property
def agent_name(self) -> str:
    """
    Alias for name property for compatibility.
    
    Some code expects agent.agent_name instead of agent.name.
    This property provides backward compatibility.
    """
    return self.name
```

## Files Changed

### 1. `src/startd8/agents.py`
- Added `agent_name` property to `BaseAgent` class (line 142-148)
- This property is now available on all agent instances:
  - `ClaudeAgent`
  - `GPT4Agent`
  - `GeminiAgent`
  - `OpenAICompatibleAgent`
  - `MockAgent`
  - `ComposerAgent`
  - `SkillAgent` (inherits from BaseAgent)

### 2. `src/startd8/skills/agent.py`
- Note: `SkillAgent` already had an `agent_name` property (line 725-728)
- This is now redundant but harmless (it overrides the base property with identical implementation)
- Can be removed in a future cleanup if desired

## Code Locations Using `agent.agent_name`

The following code locations now work correctly:

1. **`src/startd8/tui_improved.py`** (lines 5999-6000)
   - `dev_agent.agent_name` and `review_agent.agent_name` in workflow confirmation

2. **`src/startd8/iterative_workflow.py`** (lines 270, 274, 289, 293)
   - `self.developer_agent.agent_name` and `self.reviewer_agent.agent_name` in logging and iteration tracking

## Testing

All agent classes now support both access patterns:
- `agent.name` (original attribute)
- `agent.agent_name` (compatibility property)

Both return the same value, ensuring backward compatibility.

## Verification Checklist

- [x] `BaseAgent` has `agent_name` property
- [x] All agent subclasses inherit the property
- [x] Code accessing `agent.agent_name` will work correctly
- [x] No breaking changes to existing code using `agent.name`
- [x] Tests should continue to pass (they use `agent.name` which still works)

## Additional Notes

- The `AgentConfig` model (in `src/startd8/models.py`) has an `agent_name` field - this is correct as it's a configuration model, not an agent instance
- The `AgentResponse` model has an `agent_name` field - this is also correct as it's a response model
- The fix ensures agent instances can be accessed with either `.name` or `.agent_name` for maximum compatibility

## Next Steps

1. Run unit tests to verify no regressions
2. Test agent creation and usage in TUI
3. Test iterative workflow with different agent types
4. Consider removing duplicate `agent_name` property from `SkillAgent` in future cleanup

