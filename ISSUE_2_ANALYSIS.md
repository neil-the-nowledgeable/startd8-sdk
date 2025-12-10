# Issue 2: Gemini Provider Unimplemented - Analysis & Options

**Date:** December 10, 2025  
**Priority:** Medium  
**Estimated Time:** 4-8 hours (decision-dependent)

---

## Problem Statement

The `GeminiAgent.agenerate()` method raises `NotImplementedError`, but the provider registry advertises Gemini support via entry points in `pyproject.toml`. Users selecting Gemini will crash at runtime with:

```
NotImplementedError: Gemini agent requires google-generativeai package. 
Install with: pip install google-generativeai
```

### Current State

**Files Involved:**
- `src/startd8/agents.py` - Lines 447-472: `GeminiAgent` class
- `src/startd8/providers/gemini.py` - Full provider stub with metadata
- `pyproject.toml` - Lines 58-63: Entry points including Gemini
- `src/startd8/providers/registry.py` - Provider discovery system

**Current Implementation:**
```python
class GeminiAgent(BaseAgent):
    """Google Gemini agent (placeholder - requires google-generativeai)"""
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """Generate response using Gemini"""
        raise NotImplementedError(
            "Gemini agent requires google-generativeai package. "
            "Install with: pip install google-generativeai"
        )
```

**Provider Metadata:**
- 4 supported models: `gemini-pro`, `gemini-pro-vision`, `gemini-1.5-pro`, `gemini-1.5-flash`
- Pricing data included
- Model metadata (context window, max output tokens)
- Provider validation logic exists

---

## Three Options to Fix

### Option A: Full Implementation ✅ RECOMMENDED

**Description:** Implement complete Gemini support using the `google-generativeai` package.

**Pros:**
- ✅ Provides full functionality for users
- ✅ Consistent with other providers (Anthropic, OpenAI)
- ✅ Users get real value from Gemini models
- ✅ Supports streaming (capability is already declared)
- ✅ Aligns with existing provider pattern

**Cons:**
- ⚠️ Longest implementation (4-8 hours)
- ⚠️ Requires `google-generativeai` package dependency
- ⚠️ More testing complexity

**Implementation Steps:**
1. Add `google-generativeai` to optional dependencies in pyproject.toml
2. Implement `GeminiAgent.agenerate()` with proper API integration
3. Handle token counting (google-generativeai has different token counting)
4. Implement `generate()` sync wrapper
5. Integrate with cost tracking (handle pricing conversion)
6. Add error handling for API failures
7. Write comprehensive tests

**Code Pattern to Follow:**
- Look at `ClaudeAgent` for Anthropic integration pattern
- Look at `OpenAICompatibleAgent` for API integration pattern

---

### Option B: Remove from Registry ❌ NOT RECOMMENDED

**Description:** Remove Gemini from provider registry and entry points until implemented.

**Pros:**
- ✅ Prevents runtime crashes
- ✅ Least implementation work
- ✅ Clear message to users: "Not yet supported"

**Cons:**
- ❌ Loses Gemini as advertised feature
- ❌ Users expecting Gemini support are disappointed
- ❌ Metadata (pricing, models) goes unused
- ❌ Breaks compatibility if anyone is using Gemini
- ❌ Need to update docs/marketing materials

**What Would Change:**
```python
# Remove from pyproject.toml
# gemini = "startd8.providers.gemini:GeminiProvider"

# Remove from _register_builtin_providers() if added
# (currently not registered in built-in, only via entry points)
```

---

### Option C: Fail-Fast Validation ⚠️ PARTIAL SOLUTION

**Description:** Add startup validation that fails early with clear error message if Gemini is selected but library isn't installed.

**Pros:**
- ✅ Prevents runtime crashes mid-operation
- ✅ Clear error message to developer
- ✅ Minimal implementation (1-2 hours)
- ✅ Can be placeholder until full implementation

**Cons:**
- ⚠️ Still doesn't provide actual functionality
- ⚠️ Users still can't use Gemini
- ⚠️ Just shifts error from runtime to initialization
- ⚠️ Only a partial solution

**Implementation:**
```python
class GeminiAgent(BaseAgent):
    def __init__(self, ...):
        super().__init__(...)
        
        try:
            import google.generativeai
        except ImportError:
            raise ImportError(
                "Gemini agent requires google-generativeai package. "
                "Install with: pip install google-generativeai"
            )
    
    async def agenerate(self, prompt: str):
        raise NotImplementedError("Full Gemini integration coming soon")
```

---

## Recommendation: Option A (Full Implementation)

**Why Option A:**

1. **Strategic:** The project is enterprise-grade with comprehensive cost tracking. Gemini support adds real value.

2. **Consistency:** Other providers (Anthropic, OpenAI) are fully implemented. Gemini should be too.

3. **User Value:** Google Gemini is a major LLM provider with competitive pricing and unique features (1M token context).

4. **Long-term:** Full implementation future-proofs the codebase. Placeholder will eventually need fixing anyway.

5. **Pattern Exists:** Implementation pattern is clear from existing agents (Claude, OpenAI).

6. **Metadata Ready:** Provider already has models, pricing, validation logic.

---

## Implementation Path (Option A)

### Phase 1: Setup (30 minutes)
- [ ] Add `google-generativeai` to optional dependencies
- [ ] Understand google-generativeai API (response format, token counting)
- [ ] Review existing agent implementations (Claude, OpenAI)

### Phase 2: Core Implementation (2-3 hours)
- [ ] Implement `GeminiAgent.__init__()` with API client setup
- [ ] Implement `agenerate()` with proper error handling
- [ ] Implement `generate()` sync wrapper
- [ ] Handle token counting (Gemini uses different model)
- [ ] Integrate with cost tracking

### Phase 3: Robustness (1-2 hours)
- [ ] Add error handling (API errors, rate limits, auth errors)
- [ ] Add retry logic for transient failures
- [ ] Validate model support
- [ ] Handle streaming (if needed)

### Phase 4: Testing (1-2 hours)
- [ ] Unit tests with mocking
- [ ] Integration tests (optional, requires API key)
- [ ] Cost tracking tests
- [ ] Error scenario tests

### Phase 5: Documentation (30 minutes)
- [ ] Update docstrings
- [ ] Add usage examples
- [ ] Document API key setup
- [ ] Update NEXT_STEPS.md

---

## Decision Needed

**What should we do?**

1. **Option A:** Fully implement Gemini support (4-8 hours)
2. **Option B:** Remove from registry until implemented (30 minutes)
3. **Option C:** Add fail-fast validation (1-2 hours)

**Recommended:** Option A (Full Implementation)

---

## Reference: google-generativeai API

Basic pattern (pseudo-code):
```python
import google.generativeai as genai

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-pro')

response = model.generate_content("Your prompt here")
response.text  # Response text
response.usage_metadata  # Token counts
```

---

## Files Needing Changes (Option A)

1. **pyproject.toml**
   - Add `google-generativeai` to optional dependencies

2. **src/startd8/agents.py**
   - `GeminiAgent.__init__()` - Initialize API client
   - `GeminiAgent.agenerate()` - Full implementation
   - `GeminiAgent.generate()` - Sync wrapper (if not inherited)

3. **tests/unit/test_agents.py** (or new file)
   - Unit tests with mocking
   - Integration tests

4. **NEXT_STEPS.md** (optional)
   - Update Issue 2 status when complete

---

## Next Steps

1. **Decide:** Choose Option A, B, or C
2. **Implement:** Follow chosen implementation path
3. **Test:** Verify with existing test suite
4. **Document:** Update NEXT_STEPS.md and any docs
5. **Review:** Code review before merging

---

## Success Criteria

- [ ] Decision made on which option to implement
- [ ] Implementation complete and working
- [ ] Tests passing (unit and integration if applicable)
- [ ] Cost tracking integration working
- [ ] Documentation updated
- [ ] No breaking changes to existing code
- [ ] Commit created with clear message

