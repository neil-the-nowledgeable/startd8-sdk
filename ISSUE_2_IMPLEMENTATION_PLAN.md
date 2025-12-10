# Issue 2: Gemini Provider Implementation Plan

**Status:** Ready for Implementation  
**Recommendation:** Option A (Full Implementation)  
**Estimated Time:** 4-8 hours (broken into phases)  
**Priority:** Medium

---

## Executive Summary

Implement full Google Gemini support in the StartD8 SDK by:
1. Adding `google-generativeai` to optional dependencies
2. Implementing `GeminiAgent` with API integration
3. Adding cost tracking support
4. Writing comprehensive tests

This brings Gemini to feature parity with existing providers (Claude, OpenAI).

---

## Implementation Details

### Phase 1: Dependency Setup (15 minutes)

#### File: `pyproject.toml`

**Current:**
```toml
[project.optional-dependencies]
anthropic = ["anthropic>=0.18.0"]
openai = ["openai>=1.0.0"]
all = [
    "anthropic>=0.18.0",
    "openai>=1.0.0",
]
```

**Update to:**
```toml
[project.optional-dependencies]
anthropic = ["anthropic>=0.18.0"]
openai = ["openai>=1.0.0"]
gemini = ["google-generativeai>=0.3.0"]
all = [
    "anthropic>=0.18.0",
    "openai>=1.0.0",
    "google-generativeai>=0.3.0",
]
```

**Why:**
- Follows pattern of other optional dependencies
- Allows installation via `pip install startd8[gemini]`
- Keeps main package lightweight

---

### Phase 2: Import Handling (10 minutes)

#### File: `src/startd8/agents.py`

**Add at top with other optional imports (after line 28):**
```python
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
except ImportError:
    genai = None
    GenerationConfig = None
    _GEMINI_AVAILABLE = False
else:
    _GEMINI_AVAILABLE = True
```

**Why:**
- Follows existing pattern (Anthropic, OpenAI)
- Clear error handling if library not installed
- `_GEMINI_AVAILABLE` flag for conditional initialization

---

### Phase 3: GeminiAgent Implementation (2-3 hours)

#### File: `src/startd8/agents.py`

**Replace current GeminiAgent class (lines 447-472):**

```python
class GeminiAgent(BaseAgent):
    """Google Gemini agent with async support"""
    
    def __init__(
        self,
        name: str = "gemini",
        model: str = "gemini-pro",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        """
        Initialize Gemini agent
        
        Args:
            name: Agent identifier
            model: Gemini model to use (e.g., 'gemini-pro', 'gemini-1.5-pro')
            api_key: Google API key (uses GOOGLE_API_KEY env var if not provided)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 2.0)
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
            
        Raises:
            ImportError: If google-generativeai package is not installed
        """
        super().__init__(name, model, cost_tracker, budget_manager)
        
        if not _GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai package not installed. "
                "Install with: pip install startd8[gemini] or pip install google-generativeai"
            )
        
        # Get API key from parameter or environment
        if api_key is None:
            api_key = os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            raise ValueError(
                "Google API key required. "
                "Set GOOGLE_API_KEY environment variable or pass api_key parameter."
            )
        
        # Configure the API
        genai.configure(api_key=api_key)
        
        # Create the model instance
        generation_config = GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        
        self.model_instance = genai.GenerativeModel(
            model_name=self.model,
            generation_config=generation_config
        )
        
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Generate response using Gemini async API
        
        Args:
            prompt: The prompt text
            
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
            
        Raises:
            RuntimeError: If Gemini API call fails
        """
        start_time = time.time()
        
        try:
            # google-generativeai doesn't have native async, 
            # but we can use asyncio to run it in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model_instance.generate_content(prompt)
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {e}") from e
        
        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)
        
        # Extract response text
        if not response.text:
            raise RuntimeError(
                f"Gemini returned empty response. "
                f"Finish reason: {response.finish_reason}"
            )
        
        response_text = response.text
        
        # Google Gemini doesn't provide token counts in standard API response,
        # so we need to use the countTokens method
        try:
            # Count input tokens
            input_count_response = self.model_instance.count_tokens(prompt)
            input_tokens = input_count_response.total_tokens
            
            # Count output tokens (response text)
            output_count_response = self.model_instance.count_tokens(response_text)
            output_tokens = output_count_response.total_tokens
        except Exception as e:
            # If token counting fails, provide reasonable estimates
            # ~1.3 tokens per word as rough estimate
            input_tokens = max(1, len(prompt.split()) // 1.3)
            output_tokens = max(1, len(response_text.split()) // 1.3)
            logger.warning(f"Failed to count tokens, using estimate: {e}")
        
        token_usage = TokenUsage(
            input=int(input_tokens),
            output=int(output_tokens),
            total=int(input_tokens + output_tokens)
        )
        
        return response_text, response_time_ms, token_usage
```

**Key Design Decisions:**

1. **No native async:** google-generativeai is synchronous. Use `asyncio.run_in_executor()` to avoid blocking.

2. **Token counting:** Gemini doesn't return token counts in response. Use `countTokens()` method.

3. **Error handling:** Wrap API calls with try-except to catch common errors.

4. **Fallback estimates:** If token counting fails, use word-based estimation (1.3 tokens/word).

5. **Configuration:** Support temperature and max_tokens parameters matching other agents.

---

### Phase 4: Add `os` import (2 minutes)

**File:** `src/startd8/agents.py`

**Add near top if not already present:**
```python
import os
```

---

### Phase 5: Add Logging (2 minutes)

**File:** `src/startd8/agents.py`

**Add after imports:**
```python
import logging
logger = logging.getLogger(__name__)
```

---

### Phase 6: Update Existing Imports Check (5 minutes)

**Verify at top of agents.py that you have:**
- `import os` ✅
- `import logging` ✅
- `import time` ✅
- `import asyncio` ✅
- `import uuid` ✅

---

### Phase 7: Cost Tracker Integration (30 minutes)

The cost tracking integration is **automatic**! 

How it works:
1. `GeminiAgent` inherits from `BaseAgent`
2. `BaseAgent.acreate_response()` automatically handles cost tracking
3. When `_run_with_cost_tracking()` calls `agenerate()`, it gets proper `TokenUsage`
4. Cost is recorded automatically with token counts

**No changes needed** - just ensure `TokenUsage` is returned correctly.

---

### Phase 8: GeminiProvider Update (15 minutes)

#### File: `src/startd8/providers/gemini.py`

**Update `create_agent()` method to support cost_tracker and budget_manager:**

```python
def create_agent(
    self, 
    model: str, 
    name: Optional[str] = None,
    **config
) -> GeminiAgent:
    """
    Create a Gemini agent instance.
    
    Args:
        model: Gemini model identifier
        name: Optional agent name (defaults to model-based name)
        **config: Configuration options
            - api_key: Google API key (or use GOOGLE_API_KEY env var)
            - max_tokens: Maximum tokens to generate (default: 4096)
            - temperature: Sampling temperature (default: 0.7)
            - cost_tracker: Optional cost tracker instance
            - budget_manager: Optional budget manager instance
    
    Returns:
        Configured GeminiAgent instance
    """
    if model not in self.MODELS:
        raise ValueError(
            f"Model {model} not supported by Gemini provider. "
            f"Available models: {', '.join(self.MODELS)}"
        )
    
    # Generate a friendly name if not provided
    if name is None:
        parts = model.split('-')
        if len(parts) >= 2:
            name = f"gemini-{parts[1]}"
        else:
            name = model
    
    from ..agents import GeminiAgent
    
    return GeminiAgent(
        name=name,
        model=model,
        api_key=config.get('api_key'),
        max_tokens=config.get('max_tokens', 4096),
        temperature=config.get('temperature', 0.7),
        cost_tracker=config.get('cost_tracker'),
        budget_manager=config.get('budget_manager')
    )
```

---

### Phase 9: Testing (1-2 hours)

#### File: `tests/unit/test_agents.py` (add to TestAsyncAgents or new section)

```python
class TestGeminiAgent:
    """Test Gemini agent implementation"""
    
    @pytest.fixture
    def gemini_available(self):
        """Check if google-generativeai is available"""
        try:
            import google.generativeai
            return True
        except ImportError:
            return False
    
    @pytest.mark.skipif(not gemini_available, reason="google-generativeai not installed")
    def test_gemini_agent_initialization(self):
        """Test creating a Gemini agent (requires API key)"""
        import os
        api_key = os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")
        
        from startd8.agents import GeminiAgent
        agent = GeminiAgent(
            name="test-gemini",
            model="gemini-pro",
            api_key=api_key
        )
        
        assert agent.name == "test-gemini"
        assert agent.model == "gemini-pro"
    
    def test_gemini_agent_requires_package(self):
        """Test that GeminiAgent raises error if package not installed"""
        # This test will run even without google-generativeai installed
        # It verifies the error message is clear
        pass  # Can be implemented with mocking
    
    def test_gemini_provider_creates_agent(self):
        """Test that GeminiProvider creates agents correctly"""
        from startd8.providers.gemini import GeminiProvider
        
        provider = GeminiProvider()
        
        # Should handle cost_tracker and budget_manager
        agent = provider.create_agent(
            model="gemini-pro",
            cost_tracker=None,
            budget_manager=None
        )
        
        assert agent is not None
        assert agent.model == "gemini-pro"
```

---

## Implementation Checklist

### Before Starting
- [ ] Read google-generativeai documentation
- [ ] Understand token counting in Gemini API
- [ ] Review Claude and OpenAI implementations as reference

### Phase 1: Dependencies
- [ ] Update pyproject.toml with google-generativeai
- [ ] Verify syntax of pyproject.toml

### Phase 2: Imports
- [ ] Add google-generativeai imports to agents.py
- [ ] Add _GEMINI_AVAILABLE flag
- [ ] Add os import (if needed)
- [ ] Add logging import (if needed)

### Phase 3: Core Implementation
- [ ] Replace GeminiAgent class
- [ ] Implement __init__() with API configuration
- [ ] Implement agenerate() with token counting
- [ ] Add error handling for API failures
- [ ] Test syntax with py_compile

### Phase 4: Provider Update
- [ ] Update GeminiProvider.create_agent()
- [ ] Add cost_tracker and budget_manager support
- [ ] Test syntax

### Phase 5: Testing
- [ ] Write unit tests with mocking
- [ ] Add integration tests (optional, requires API key)
- [ ] Verify cost tracking works
- [ ] Test error scenarios

### Phase 6: Documentation
- [ ] Update docstrings
- [ ] Add usage examples
- [ ] Document API key setup
- [ ] Update NEXT_STEPS.md

### Phase 7: Code Review
- [ ] Review code for quality
- [ ] Check consistency with other agents
- [ ] Verify error messages are clear
- [ ] Run all tests

### Phase 8: Commit
- [ ] Create commit with detailed message
- [ ] Push to remote (if applicable)
- [ ] Update NEXT_STEPS.md

---

## Known Challenges & Solutions

### Challenge 1: google-generativeai is Synchronous
**Problem:** Library doesn't have native async support  
**Solution:** Use `asyncio.run_in_executor()` to run in thread pool

### Challenge 2: Token Counting
**Problem:** Response object doesn't include token counts  
**Solution:** Use `model.countTokens()` method for both input and output

### Challenge 3: Error Handling
**Problem:** Various Gemini API errors (auth, rate limit, invalid model)  
**Solution:** Catch broad Exception and convert to meaningful error messages

### Challenge 4: Missing API Key
**Problem:** Users might forget to set GOOGLE_API_KEY  
**Solution:** Check in __init__ and raise clear ValueError with instructions

---

## Success Criteria

✅ All of the following must be true:

- [ ] `GeminiAgent` fully implements `agenerate()`
- [ ] Returns proper `TokenUsage` with token counts
- [ ] Works with cost tracking system
- [ ] Works with budget enforcement
- [ ] All tests pass (including new tests)
- [ ] No breaking changes to existing code
- [ ] Clear error messages for missing dependencies/keys
- [ ] Consistent with Claude and OpenAI agents
- [ ] Code follows existing style/patterns
- [ ] Documentation is complete

---

## Next Steps (After Implementation)

1. Test with actual Gemini API (if you have a key)
2. Test cost tracking integration
3. Test budget enforcement
4. Performance testing
5. Documentation review
6. Code review with team
7. Merge to main branch

---

## Useful References

### google-generativeai Documentation
- Models: https://ai.google.dev/models/gemini
- API Reference: https://ai.google.dev/api/python
- Token Counting: `model.countTokens(content)`
- Response Format: `GenerateContentResponse` object

### Similar Implementation
- `ClaudeAgent` (lines 325-383): Anthropic integration
- `GPT4Agent` (lines 386-444): OpenAI integration

### Existing Pattern
- Optional dependency pattern in pyproject.toml
- Import guard pattern with `_AVAILABLE` flags
- Token extraction from response objects
- Error handling in __init__

---

## Estimated Timeline

- **Phase 1-2:** 25 minutes (Setup)
- **Phase 3-5:** 2-3 hours (Core implementation)
- **Phase 6-7:** 30 minutes (Documentation/polish)
- **Phase 8:** 1-2 hours (Testing/debugging)
- **Total:** 4-5 hours (estimate may vary based on debugging needs)

---

**Ready to implement! 🚀**

