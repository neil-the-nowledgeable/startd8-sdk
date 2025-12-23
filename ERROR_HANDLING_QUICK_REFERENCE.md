# Error Handling & Logging Quick Reference
## Current State & Immediate Improvements

**Date:** 2025-01-XX  
**Status:** Action Items for Production Readiness

---

## 📊 Current State Summary

### ✅ **Strengths** (Keep These)
- Custom exception hierarchy (`exceptions.py`) - well-structured
- JSON logging formatter with correlation IDs
- Some good patterns: `raise ... from e` in `agents.py`, `storage/base.py`
- Error decorators (`@handle_storage_errors`)

### ⚠️ **Critical Issues Found**

#### 1. Generic Exception Handling (422 instances found)
**Problem:** Too many `except Exception` blocks lose context

**Examples:**
```python
# document_enhancement.py:433
except Exception as e:
    # Returns error result but doesn't log!
    return EnhancementStepResult(..., error=str(e))

# benchmark.py:97
except Exception as e:
    logger.error(...)  # Good logging, but generic catch
    return None  # Swallows error
```

**Impact:** 
- Hard to debug root causes
- No error aggregation possible
- Can't distinguish transient vs permanent failures

#### 2. Missing Error Logging
**Problem:** Errors caught but not logged consistently

**Found in:**
- `document_enhancement.py` - errors returned but not logged
- `iterative_workflow.py` - some paths don't log
- `config.py:47` - silent exception handling

#### 3. Inconsistent Context
**Problem:** Logs missing key context fields

**Current:**
```python
logger.error(f"Error: {e}")  # Missing: agent_name, operation, trace_id
```

**Should be:**
```python
logger.error(
    f"Error: {e}",
    exc_info=True,
    extra={
        "agent_name": self.name,
        "operation": "generate",
        "model": self.model,
        "trace_id": trace.get_current_span().get_span_context().trace_id
    }
)
```

---

## 🎯 Immediate Improvements (Quick Wins)

### Priority 1: Fix Silent Error Handling

**File:** `src/startd8/document_enhancement.py:433`

**Current:**
```python
except Exception as e:
    return EnhancementStepResult(..., error=str(e))
```

**Fix:**
```python
except Exception as e:
    from ..logging_config import get_logger
    logger = get_logger(__name__)
    logger.error(
        f"Agent step {step_number} failed: {e}",
        exc_info=True,
        extra={
            "step_number": step_number,
            "agent_name": agent_config.agent_name,
            "model": agent.model if hasattr(agent, 'model') else "unknown"
        }
    )
    return EnhancementStepResult(..., error=str(e))
```

### Priority 2: Add Specific Exception Handling

**File:** `src/startd8/benchmark.py:97`

**Current:**
```python
except Exception as e:
    logger.error(...)
    return None
```

**Fix:**
```python
from ..exceptions import APIError, AgentError, ValidationError

except APIError as e:
    logger.warning(f"API error for {agent.name}: {e}", exc_info=True)
    if e.retry_after:
        logger.info(f"Retry after {e.retry_after}s")
    return None
except AgentError as e:
    logger.error(f"Agent error for {agent.name}: {e}", exc_info=True)
    return None
except ValidationError as e:
    logger.error(f"Validation error: {e}", exc_info=True)
    return None
except Exception as e:
    logger.error(f"Unexpected error for {agent.name}: {e}", exc_info=True)
    return None
```

### Priority 3: Standardize Error Context

**Create:** `src/startd8/observability/error_context.py`

```python
"""Standardized error context helpers"""
from opentelemetry import trace
from typing import Dict, Any, Optional

def get_error_context(
    operation: str,
    agent_name: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Get standardized error context for logging
    
    Args:
        operation: Operation name (e.g., "agent.generate")
        agent_name: Agent name if applicable
        model: Model name if applicable
        **kwargs: Additional context fields
    
    Returns:
        Dictionary of context fields
    """
    context = {
        "operation": operation,
    }
    
    if agent_name:
        context["agent_name"] = agent_name
    if model:
        context["model"] = model
    
    # Add trace context if available
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        span_ctx = span.get_span_context()
        context["trace_id"] = format(span_ctx.trace_id, '032x')
        context["span_id"] = format(span_ctx.span_id, '016x')
    
    context.update(kwargs)
    return context
```

**Usage:**
```python
from ..observability.error_context import get_error_context

try:
    result = agent.generate(prompt)
except Exception as e:
    logger.error(
        f"Generation failed: {e}",
        exc_info=True,
        extra=get_error_context(
            operation="agent.generate",
            agent_name=agent.name,
            model=agent.model,
            prompt_length=len(prompt)
        )
    )
    raise
```

---

## 🔍 OpenTelemetry Integration Roadmap

### Phase 1: Foundation (Week 1)
**Goal:** Set up OTel SDK

**Tasks:**
1. ✅ Create review document (DONE)
2. ⏳ Install dependencies
3. ⏳ Create `src/startd8/observability/` module
4. ⏳ Set up basic tracing
5. ⏳ Set up basic metrics

**Dependencies:**
```bash
pip install opentelemetry-api opentelemetry-sdk
pip install opentelemetry-exporter-otlp-proto-grpc
pip install opentelemetry-instrumentation-logging
```

### Phase 2: Core Instrumentation (Week 2-3)
**Goal:** Instrument critical paths

**Priority Order:**
1. `agents.py` - API calls (highest value)
2. `orchestration.py` - Pipeline execution
3. `document_enhancement.py` - Multi-step workflows
4. `storage/base.py` - Storage operations

### Phase 3: Advanced Features (Week 4)
**Goal:** Enhanced observability

- Custom metrics (tokens, costs)
- Error tracking and aggregation
- Performance profiling
- Distributed tracing across async

### Phase 4: Production (Week 5)
**Goal:** Production deployment

- Sampling strategies
- Exporter configuration
- Health checks
- Documentation

---

## 📋 Action Items Checklist

### Immediate (This Week)
- [ ] Fix silent error handling in `document_enhancement.py`
- [ ] Add specific exception handling in `benchmark.py`
- [ ] Create `error_context.py` helper
- [ ] Add error logging to all exception handlers

### Short Term (Next 2 Weeks)
- [ ] Install OpenTelemetry dependencies
- [ ] Create observability module structure
- [ ] Implement basic tracing decorators
- [ ] Instrument `agents.py` as proof of concept

### Medium Term (Next Month)
- [ ] Complete core instrumentation
- [ ] Add metrics collection
- [ ] Set up OTLP exporters
- [ ] Create monitoring dashboards

---

## 🎓 Best Practices Going Forward

### 1. Always Log Errors
```python
# ❌ BAD
except Exception as e:
    return None

# ✅ GOOD
except Exception as e:
    logger.error(f"Operation failed: {e}", exc_info=True, extra=context)
    return None
```

### 2. Use Specific Exceptions
```python
# ❌ BAD
except Exception as e:
    ...

# ✅ GOOD
except APIError as e:
    # Handle API errors
except ValidationError as e:
    # Handle validation errors
except Exception as e:
    # Unexpected errors - log and re-raise
    logger.error(..., exc_info=True)
    raise
```

### 3. Preserve Exception Context
```python
# ❌ BAD
except Exception as e:
    raise RuntimeError(str(e))

# ✅ GOOD
except Exception as e:
    raise APIError(f"Failed: {e}", original_error=e) from e
```

### 4. Add Rich Context
```python
# ❌ BAD
logger.error(f"Error: {e}")

# ✅ GOOD
logger.error(
    f"Error: {e}",
    exc_info=True,
    extra={
        "agent_name": self.name,
        "model": self.model,
        "operation": "generate",
        "trace_id": trace_id
    }
)
```

---

## 📚 Reference Documents

- **Full Review:** `ERROR_HANDLING_AND_OBSERVABILITY_REVIEW.md`
- **Exception Hierarchy:** `src/startd8/exceptions.py`
- **Logging Config:** `src/startd8/logging_config.py`

---

## 🚀 Next Steps

1. **Review this document** and prioritize action items
2. **Start with quick wins** (fix silent errors)
3. **Set up OTel foundation** (Phase 1)
4. **Instrument one module** as proof of concept
5. **Expand systematically** to other modules

**Ready to start?** I can:
- Fix the immediate error handling issues
- Set up the OpenTelemetry foundation
- Create the observability module structure
- Instrument a specific module as proof of concept

Let me know which you'd like to tackle first!
