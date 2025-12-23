# Agent Validation Improvements

## Summary

Added comprehensive validation to ensure only properly configured agents can be selected for workflows. Invalid agents (e.g., with non-existent model names like `gpt-5.2-pro`) are now filtered out before they appear in selection lists.

## Problem

Users could select agents with invalid configurations (e.g., invalid model names) for workflows, which would fail at runtime with confusing error messages like:
```
Design polish pipeline failed: Model 'gpt-5.2-pro' not found or not available.
```

## Solution

Implemented a two-layer validation system:

1. **Pre-selection validation** - Filters out invalid agents before they appear in selection lists
2. **Post-selection validation** - Final check when agent is actually selected

## Changes Made

### 1. Added `_validate_agent_for_workflow()` Method

**Location:** `src/startd8/tui_improved.py:3082-3174`

This method performs real validation by:
- Attempting to create the agent instance
- Validating model names against provider supported models
- Checking for obviously invalid model names (e.g., `gpt-5`, `gpt-6`)
- Detecting API key configuration issues
- Returning clear error messages

**Key Features:**
- Validates built-in agents (mock, claude, gpt4)
- Validates custom agents (provider-backed and others)
- Checks model names against provider supported models
- Catches invalid model patterns (e.g., `gpt-5.2-pro` for OpenAI)
- Provides specific error messages for different failure types

### 2. Enhanced `_get_ready_agents_for_selection()` Method

**Location:** `src/startd8/tui_improved.py:3176-3230`

**Changes:**
- Now validates each agent before including it in the selection list
- Filters out agents that fail validation
- Logs invalid agents for debugging
- Shows user-friendly messages when no valid agents are available

**Behavior:**
- Only returns agents that pass validation
- Invalid agents are logged but not shown to user
- If no valid agents available, shows helpful error message with details

### 3. Enhanced `_select_ready_agent()` Method

**Location:** `src/startd8/tui_improved.py:3227-3375`

**Changes:**
- Added final validation after agent creation
- Validates model names against provider supported models
- Catches invalid GPT model versions (gpt-5, gpt-6)
- Provides helpful error messages with supported model lists
- Better error handling with specific messages

**Validation Checks:**
- Model name validation for OpenAI (catches `gpt-5.2-pro`, etc.)
- Model name validation for Gemini
- Provider-supported model checking
- Clear error messages with supported model lists

### 4. Added Tuple Import

**Location:** `src/startd8/tui_improved.py:11`

Added `Tuple` to typing imports for type hints.

## Validation Rules

### OpenAI Models
- **Invalid:** `gpt-5.*`, `gpt-6.*` (don't exist)
- **Valid patterns:** `gpt-4`, `gpt-3`, `gpt-4o`, `o1`, `davinci`, `curie`, `babbage`, `ada`
- **Supported models:** `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`, `gpt-4o`, `gpt-4o-mini`

### Gemini Models
- **Valid patterns:** `gemini-1.*`, `gemini-2.*`, `gemini-pro`
- **Supported models:** `gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash-exp`

### Other Providers
- Validates against provider's `supported_models` list
- Allows permissive providers (unknown models) but validates creation

## User Experience Improvements

### Before
- Invalid agents appeared in selection lists
- Errors occurred at workflow runtime
- Confusing error messages
- No guidance on fixing issues

### After
- Only valid agents appear in selection lists
- Invalid agents filtered out proactively
- Clear error messages when no valid agents available
- Helpful hints about supported models
- Validation happens before workflow execution

## Example Scenarios

### Scenario 1: Invalid GPT Model
**Before:**
- User selects agent with `gpt-5.2-pro`
- Workflow starts, then fails with error
- User confused about what went wrong

**After:**
- Agent with `gpt-5.2-pro` filtered out
- Doesn't appear in selection list
- If somehow selected, caught immediately with clear error:
  ```
  Error: Model 'gpt-5.2-pro' is not a valid OpenAI model.
  Supported OpenAI models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o
  ```

### Scenario 2: Missing API Key
**Before:**
- Agent appears in list
- Selected, workflow fails at runtime

**After:**
- Agent filtered out during validation
- User sees: "API key not configured"
- Can fix before attempting workflow

### Scenario 3: Invalid Gemini Model
**Before:**
- Agent with `gemini-3-pro-preview` selected
- Fails at runtime

**After:**
- Agent filtered out if model doesn't match valid patterns
- Clear error message about supported Gemini models

## Error Messages

### When No Valid Agents Available
```
No valid agents available for selection.
Found 2 agent(s) with configuration issues:
  • my-gpt-agent (gpt-5.2-pro): Model 'gpt-5.2-pro' is not a valid OpenAI model
  • my-gemini-agent (gemini-3-pro): Model 'gemini-3-pro' is not a recognized Gemini model
```

### When Agent Creation Fails
```
Error: Could not create agent from selection '⭐ my-agent (gpt-5.2-pro)'
Agent Type: provider, Provider: openai, Model: gpt-5.2-pro
Hint: Check that OPENAI_API_KEY is set and model name is valid.
Supported OpenAI models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o, gpt-4o-mini
```

## Testing Recommendations

1. **Test with invalid GPT models:**
   - Create agent with `gpt-5.2-pro`
   - Verify it doesn't appear in selection list
   - Verify error message if somehow selected

2. **Test with invalid Gemini models:**
   - Create agent with `gemini-3-pro-preview`
   - Verify filtering and error messages

3. **Test with missing API keys:**
   - Create agent without API key
   - Verify it's filtered out

4. **Test with valid agents:**
   - Verify valid agents still appear and work correctly

## Backward Compatibility

- ✅ Existing valid agents continue to work
- ✅ No breaking changes to agent creation
- ✅ Validation is additive (doesn't break existing workflows)
- ✅ Invalid agents are filtered but not deleted

## Future Enhancements

1. **Auto-fix suggestions:** Suggest correct model names for typos
2. **Model name suggestions:** "Did you mean gpt-4o instead of gpt-5.2-pro?"
3. **Batch validation:** Validate all agents on startup
4. **Validation cache:** Cache validation results for performance
5. **Provider-specific validation:** More sophisticated validation per provider

## Related Files

- `src/startd8/tui_improved.py` - Main implementation
- `src/startd8/providers/registry.py` - Provider registry
- `src/startd8/providers/openai.py` - OpenAI provider
- `src/startd8/providers/gemini.py` - Gemini provider

