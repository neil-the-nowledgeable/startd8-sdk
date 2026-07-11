# Issue 2: Gemini Provider - Quick Start Guide

**Last Updated:** December 10, 2025  
**Status:** ✅ READY TO IMPLEMENT  
**Estimated Time:** 4-8 hours  
**Priority:** Medium

---

## 📚 Documentation Map

Before starting implementation, review these documents in order:

### 1. **This File (Quick Start)**
   - Navigation guide
   - Key decisions
   - Quick reference

### 2. **ISSUE_2_ANALYSIS.md**
   - Complete problem analysis
   - Three implementation options
   - Why we chose Option A
   - Reference: google-generativeai API

### 3. **ISSUE_2_IMPLEMENTATION_PLAN.md** ⭐ **START HERE FOR CODING**
   - Step-by-step implementation guide
   - 9 phases with code examples
   - Implementation checklist
   - Known challenges & solutions

### 4. **ISSUE_2_PREPARATION_SUMMARY.md**
   - Executive overview
   - Success criteria
   - Reference patterns
   - Time breakdown

---

## ✅ Key Decisions

### Decision 1: Which Option?
**Chosen:** Option A - Full Implementation  
**Why:** Provides real value, consistent with other providers, clear pattern exists

### Decision 2: Technology
**Chosen:** google-generativeai library with asyncio executor pattern  
**Why:** Well-maintained, has token counting, pattern already used in project

### Decision 3: Approach
**Chosen:** Follow existing agent patterns (ClaudeAgent, GPT4Agent)  
**Why:** Consistency, maintainability, reduced complexity

---

## 🚀 How to Start Implementing

### Step 1: Read the Plan (30 minutes)
```
Read: ISSUE_2_IMPLEMENTATION_PLAN.md
Focus on:
  - Phase Overview (phases 1-9)
  - Code examples for each phase
  - Known challenges section
```

### Step 2: Review Reference Code (15 minutes)
```
Files to examine:
  - src/startd8/agents.py lines 325-383 (ClaudeAgent)
  - src/startd8/agents.py lines 386-444 (GPT4Agent)
  - src/startd8/agents.py lines 1-28 (Import patterns)
```

### Step 3: Start Phase 1 (15 minutes)
```
Task: Update pyproject.toml
Add google-generativeai to optional dependencies

Checklist:
  ☐ Add to gemini optional dependency
  ☐ Add to all optional dependency
  ☐ Verify TOML syntax
```

### Step 4: Continue Phases 2-9 (3-7 hours)
```
Follow ISSUE_2_IMPLEMENTATION_PLAN.md
Run tests after each phase
Commit frequently
```

---

## 📋 Implementation Checklist

### Phase 1: Dependencies (15 min)
- [ ] Update pyproject.toml
- [ ] Add google-generativeai>=0.3.0

### Phase 2: Imports (10 min)
- [ ] Add import handling to agents.py
- [ ] Create _GEMINI_AVAILABLE flag

### Phase 3: Core Implementation (2-3 hours)
- [ ] Replace GeminiAgent class
- [ ] Implement __init__()
- [ ] Implement agenerate()
- [ ] Handle token counting

### Phase 4: Imports (2 min)
- [ ] Add os import
- [ ] Add logging import

### Phase 5-7: Integration (1 hour)
- [ ] Update provider
- [ ] Verify cost tracking works
- [ ] Add error handling

### Phase 8: Testing (1-2 hours)
- [ ] Write unit tests
- [ ] Test with mocking
- [ ] Test error scenarios

### Phase 9: Documentation (30 min)
- [ ] Update docstrings
- [ ] Add examples
- [ ] Update NEXT_STEPS.md

---

## 🎯 Success Criteria

Check all of these when done:

- [ ] `GeminiAgent.agenerate()` fully implemented
- [ ] Returns proper `TokenUsage` with accurate token counts
- [ ] Works with all 4 Gemini models
- [ ] Cost tracking integration working
- [ ] Budget enforcement working
- [ ] All tests passing
- [ ] No breaking changes
- [ ] Consistent with Claude/OpenAI agents
- [ ] Error messages are clear
- [ ] Documentation complete

---

## 🔧 Key Technical Points

### Async Handling
```python
# google-generativeai is sync, wrap in executor
loop = asyncio.get_event_loop()
response = await loop.run_in_executor(
    None,
    lambda: self.model_instance.generate_content(prompt)
)
```

### Token Counting
```python
# Gemini doesn't return tokens in response
# Call countTokens() separately
input_count = self.model_instance.count_tokens(prompt)
output_count = self.model_instance.count_tokens(response.text)
```

### Error Handling
```python
# Catch exceptions and provide clear messages
if not api_key:
    raise ValueError("Google API key required...")

if not response.text:
    raise RuntimeError(f"Empty response: {response.finish_reason}")
```

---

## 📖 Code Examples Reference

### Import Pattern
See: lines 12-28 in src/startd8/agents.py
```python
try:
    import google.generativeai as genai
except ImportError:
    genai = None
    _GEMINI_AVAILABLE = False
else:
    _GEMINI_AVAILABLE = True
```

### Class Pattern
See: lines 325-383 (ClaudeAgent) in src/startd8/agents.py
```python
class GeminiAgent(BaseAgent):
    def __init__(self, ...):
        super().__init__(...)
        if not _GEMINI_AVAILABLE:
            raise ImportError(...)
        self.model_instance = genai.GenerativeModel(...)
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        # Implementation here
```

### Token Usage Pattern
See: lines 377-381 in src/startd8/agents.py
```python
token_usage = TokenUsage(
    input=response.usage.input_tokens,
    output=response.usage.output_tokens,
    total=response.usage.input_tokens + response.usage.output_tokens
)
return response_text, response_time_ms, token_usage
```

---

## 🐛 Common Issues & Fixes

### Issue: "No module named google"
**Solution:** Install google-generativeai
```bash
pip install google-generativeai
```

### Issue: API Key not found
**Solution:** Set GOOGLE_API_KEY environment variable
```bash
export GOOGLE_API_KEY="your-key-here"
```

### Issue: Token counting fails
**Solution:** Use fallback word-based estimate
```python
try:
    input_tokens = self.model_instance.count_tokens(prompt).total_tokens
except:
    input_tokens = max(1, len(prompt.split()) // 1.3)
```

### Issue: Response is empty
**Solution:** Check finish_reason
```python
if not response.text:
    raise RuntimeError(f"Empty response: {response.finish_reason}")
```

---

## 📊 Files You'll Need to Modify

1. **pyproject.toml**
   - Add google-generativeai to dependencies

2. **src/startd8/agents.py**
   - Lines 28-29: Add import handling
   - Lines 447-472: Replace GeminiAgent class

3. **src/startd8/providers/gemini.py**
   - Update create_agent() method

4. **tests/unit/test_agents.py**
   - Add unit tests for GeminiAgent

5. **NEXT_STEPS.md** (optional)
   - Update Issue 2 status when complete

---

## ⏱️ Time Estimates

| Phase | Task | Time | Status |
|-------|------|------|--------|
| 1 | Dependencies | 15 min | Ready |
| 2 | Imports | 10 min | Ready |
| 3 | Core Implementation | 2-3 hrs | Ready |
| 4 | os import | 2 min | Ready |
| 5 | Logging | 2 min | Ready |
| 6 | Imports check | 5 min | Ready |
| 7 | Cost tracking | 30 min | Ready |
| 8 | Provider update | 15 min | Ready |
| 9 | Testing | 1-2 hrs | Ready |
| **Total** | | **4-8 hrs** | **Ready** |

---

## 🎓 Learning Resources

### Google Generative AI
- Official Docs: https://ai.google.dev/
- Python SDK: https://ai.google.dev/tutorials/python_quickstart
- Token Counting: `model.countTokens(content)`

### Project Reference
- ClaudeAgent: src/startd8/agents.py (lines 325-383)
- GPT4Agent: src/startd8/agents.py (lines 386-444)
- BaseAgent: src/startd8/agents.py (lines 45-189)

### Similar Implementations
- Anthropic: Synchronous client with AsyncAnthropic wrapper
- OpenAI: Synchronous client with AsyncOpenAI wrapper
- Pattern: Import → Initialize → Async wrapper → Return TokenUsage

---

## 📞 Questions to Ask During Implementation

1. **About Models:** Are all 4 models (gemini-pro, gemini-pro-vision, gemini-1.5-pro, gemini-1.5-flash) supported?
2. **About Streaming:** Do we need streaming support? (Not needed for Phase 1)
3. **About Vision:** Do we need vision input support? (Not needed for Phase 1)
4. **About Testing:** Should we mock or use real API for tests? (Mocking primary)

---

## ✨ Pro Tips

1. **Test often:** Run tests after each phase
2. **Read examples:** Study ClaudeAgent and GPT4Agent patterns
3. **Clear errors:** Make error messages helpful for users
4. **Follow patterns:** Don't reinvent patterns used elsewhere
5. **Document well:** Clear docstrings help maintainability
6. **Commit frequently:** Small commits are easier to review

---

## 🎬 Action Items

### Before You Start
1. [ ] Read ISSUE_2_ANALYSIS.md
2. [ ] Read ISSUE_2_IMPLEMENTATION_PLAN.md
3. [ ] Review ClaudeAgent code
4. [ ] Confirm Option A choice

### Ready to Code
1. [ ] Follow Phase 1 of ISSUE_2_IMPLEMENTATION_PLAN.md
2. [ ] Run syntax checks after each phase
3. [ ] Write tests for each feature
4. [ ] Commit with clear messages

### When Complete
1. [ ] All tests passing
2. [ ] Documentation updated
3. [ ] Code review approved
4. [ ] Merged to main

---

## 📝 Session Context

**Previous Session:**
- ✅ Issue 1: Response ID Linkage - FIXED
- ✅ 3 regression tests added
- ✅ Documentation complete

**This Session:**
- ⏳ Issue 2: Gemini Provider - PREPARED
- 📄 4 analysis/planning documents created
- ✅ Ready for implementation

**Next Session:**
- 🔧 Implement Phase 1-9 of ISSUE_2_IMPLEMENTATION_PLAN.md
- 🧪 Test all changes
- 📄 Document completion

---

## 🏁 Quick Reference

| What | Where | Time |
|------|-------|------|
| Analysis | ISSUE_2_ANALYSIS.md | Read: 15 min |
| Plan | ISSUE_2_IMPLEMENTATION_PLAN.md | Read: 30 min |
| Reference | src/startd8/agents.py (lines 325-444) | Read: 15 min |
| Implement | ISSUE_2_IMPLEMENTATION_PLAN.md (phases 1-9) | Do: 4-8 hrs |
| Test | Write unit tests | Do: 1-2 hrs |
| Document | Update docstrings and NEXT_STEPS.md | Do: 30 min |

---

**Status: ✅ READY TO IMPLEMENT**

**Start with:** Phase 1 of ISSUE_2_IMPLEMENTATION_PLAN.md

