# Investigation: 'ImprovedTUI' object has no attribute 'api_key_manager'

**Date**: December 7, 2025  
**Status**: Root Cause Identified  
**Severity**: 🟡 Single Feature Broken (Enhance Prompt File)

---

## Summary

The "Enhance Prompt File" feature fails with:

```
Unexpected Error: 'ImprovedTUI' object has no attribute 'api_key_manager'
```

**Root Cause**: Simple **typo** - the code uses `self.api_key_manager` but the attribute is named `self.key_manager`.

---

## Error Analysis

### Error Location

**File**: `src/startd8/tui_improved.py`  
**Line**: 2989  
**Method**: `enhance_prompt_file_menu()` (or similar)

### The Bug

```python
# Line 2989 (INCORRECT):
api_key = self.api_key_manager.get_key("anthropic")

# Should be:
api_key = self.key_manager.get_key("ANTHROPIC_API_KEY")
```

**Two issues**:
1. Wrong attribute name: `api_key_manager` → should be `key_manager`
2. Wrong key name format: `"anthropic"` → should be `"ANTHROPIC_API_KEY"`

---

## Root Cause Analysis

### Attribute Name Inconsistency

The `ImprovedTUI` class initializes the key manager as `self.key_manager`:

```python
# Line 670-671:
self.key_manager = APIKeyManager(storage_dir)
self.key_manager.load_all_keys()
```

But line 2989 incorrectly references `self.api_key_manager`.

### Key Name Format

Looking at how other parts of the code use `get_key()` and `get_key_status()`:

| Line | Usage | Key Name Format |
|------|-------|-----------------|
| 941 | `self.key_manager.get_key_status(key_name)` | Variable |
| 1243 | `self.key_manager.get_key_status(api_key_env)` | `"ANTHROPIC_API_KEY"` style |
| 1623 | `self.key_manager.get_key_status('ANTHROPIC_API_KEY')` | ✅ Correct format |
| 2989 | `self.api_key_manager.get_key("anthropic")` | ❌ Wrong format |

The `get_key()` method expects the **environment variable name** (e.g., `"ANTHROPIC_API_KEY"`), not a short alias (e.g., `"anthropic"`).

### Evidence

**`APIKeyManager.get_key()` implementation (lines 158-167)**:
```python
def get_key(self, key_name: str) -> Optional[str]:
    """Get an API key (checks env first, then config file)"""
    # Environment variable takes precedence
    env_key = os.getenv(key_name)  # Expects "ANTHROPIC_API_KEY"
    if env_key:
        return env_key
    
    # Check config file
    config = self._load_config()
    return config.get(key_name)  # Also expects "ANTHROPIC_API_KEY"
```

---

## Impact

| Feature | Status |
|---------|--------|
| Enhance Prompt File | ❌ Broken |
| Other TUI features | ✅ Working |
| API key management | ✅ Working |

---

## All Occurrences

```bash
$ grep -n "api_key_manager" src/startd8/tui_improved.py
2989:        api_key = self.api_key_manager.get_key("anthropic")
```

**Only 1 occurrence** - isolated bug.

---

# Implementation Plan

## Overview

**Effort**: 5 minutes  
**Risk**: Very Low  
**Files**: 1 (`src/startd8/tui_improved.py`)

---

## Task 1: Fix the Typo

**File**: `src/startd8/tui_improved.py`  
**Line**: 2989

### Change

```python
# FROM (line 2989):
api_key = self.api_key_manager.get_key("anthropic")

# TO:
api_key = self.key_manager.get_key("ANTHROPIC_API_KEY")
```

### Fixes Applied
1. ✅ `api_key_manager` → `key_manager` (correct attribute name)
2. ✅ `"anthropic"` → `"ANTHROPIC_API_KEY"` (correct key name format)

---

## Task 2: Verify Fix

After making the change:

1. **Test Enhance Prompt File**:
   - Run `startd8 tui`
   - Select "🔧 Enhance Prompt File"
   - Verify no attribute error occurs

2. **Test with API key set**:
   - Ensure `ANTHROPIC_API_KEY` is set
   - Verify enhancement actually works

3. **Test without API key**:
   - Unset `ANTHROPIC_API_KEY`
   - Verify the warning message appears (not a crash)

---

## Task 3 (Optional): Add Safeguard

Consider adding a fallback to prevent similar errors:

```python
# More defensive code:
api_key = None
if hasattr(self, 'key_manager'):
    api_key = self.key_manager.get_key("ANTHROPIC_API_KEY")
if not api_key:
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY")
```

**Note**: This is optional since fixing the typo is sufficient.

---

## Summary

| Item | Details |
|------|---------|
| **Root Cause** | Typo: `api_key_manager` instead of `key_manager` |
| **Secondary Issue** | Wrong key format: `"anthropic"` instead of `"ANTHROPIC_API_KEY"` |
| **Fix Location** | Line 2989 of `tui_improved.py` |
| **Effort** | ~5 minutes |
| **Risk** | Very Low |

---

## Checklist

- [ ] Change `self.api_key_manager` to `self.key_manager` (line 2989)
- [ ] Change `"anthropic"` to `"ANTHROPIC_API_KEY"` (line 2989)
- [ ] Test "Enhance Prompt File" feature
- [ ] Verify API key detection works
- [ ] Verify error message shows when key is missing

---

**Investigation Complete**: December 7, 2025  
**Ready for Implementation**: Yes
