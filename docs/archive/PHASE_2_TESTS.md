# Phase 2 Tests - Agent Integration & Cost Tracking (Issue #1)

**Status:** Tests created and ready for Phase 2 implementation  
**Date:** December 9, 2025  
**Test File:** `tests/unit/test_agents.py::TestAgentCostTracking`

---

## Test Overview

Created **18 comprehensive test cases** for Phase 2 implementation:

### ✅ Tests Passing (8/18) - Basic Functionality
These tests verify that agents work correctly without cost tracking integration:

1. **test_agent_accepts_cost_tracker_and_budget_manager** ✅
   - Verifies agent can accept cost_tracker and budget_manager in initialization
   - Tests that they're stored as instance variables

2. **test_agent_works_without_cost_tracker** ✅
   - Verifies graceful degradation when cost_tracker is None
   - Agent should generate responses normally

3. **test_agent_works_without_budget_manager** ✅
   - Verifies graceful degradation when budget_manager is None
   - Cost tracking should still work if cost_tracker is present

4. **test_async_cost_recording** ✅
   - Tests async response creation with cost_tracker
   - Verifies AgentResponse includes token_usage

5. **test_sync_cost_recording** ✅
   - Tests sync response creation with cost_tracker
   - Verifies AgentResponse includes token_usage

6. **test_budget_warning_with_non_blocking** ✅
   - Tests non-blocking budget enforcement (block_on_exceed=False)
   - Should emit warning event but not raise exception

7. **test_cost_tracker_disabled_graceful** ✅
   - Tests behavior when cost tracking is disabled
   - Should not crash or raise errors

8. **test_error_handling_in_cost_tracking** ✅
   - Tests that API errors are properly propagated
   - Cost tracking system doesn't break on agent errors

---

### ❌ Tests Failing (10/18) - Cost Tracking Integration Needed

These tests verify cost tracking integration that will be implemented in Phase 2:

1. **test_budget_check_before_api_call** ❌
   - Tests that budget check happens BEFORE API call
   - Should raise `BudgetExceededError` when block_on_exceed=True
   - **Requires:** `_run_with_cost_tracking()` implementation with pre-call budget check

2. **test_async_budget_check** ❌
   - Tests async path budget enforcement
   - Should raise `BudgetExceededError` in async context
   - **Requires:** Async `_run_with_cost_tracking()` implementation

3. **test_cost_record_includes_token_usage** ❌
   - Tests that cost records include token_usage from response
   - Verifies store.query() returns recorded cost
   - **Requires:** Cost recording in `acreate_response()` / `create_response()`

4. **test_cost_event_emission** ❌
   - Tests that `COST_RECORDED` event is emitted
   - Subscribes to EventBus and verifies event data
   - **Requires:** Event emission in cost_tracker.record_cost()

5. **test_project_and_tags_flow_to_cost_record** ❌
   - Tests that project and tags flow through to cost record
   - Verifies metadata is properly stored
   - **Requires:** Project/tags passed to record_cost()

6. **test_multiple_sequential_calls** ❌
   - Tests cost recording for multiple sequential calls
   - Verifies all calls are recorded in store
   - **Requires:** Cost recording integration

7. **test_async_sync_parity** ❌
   - Tests that async and sync paths produce identical results
   - Both should record costs with similar structure
   - **Requires:** Cost recording in both sync and async paths

8. **test_metadata_passed_to_cost_record** ❌
   - Tests that metadata is passed through to cost record
   - Verifies custom metadata fields are stored
   - **Requires:** Metadata handling in record_cost()

9. **test_cost_tracking_with_context_defaults** ❌
   - Tests integration with Phase 1 context defaults
   - Uses set_cost_context() to set project/tags
   - **Requires:** Integration with get_cost_context() in cost tracking

10. **test_concurrent_cost_tracking** ❌
    - Tests cost recording for concurrent-ish calls
    - Verifies all calls are properly recorded
    - **Requires:** Thread-safe cost recording

---

## What These Tests Expect

### Pre-Call Budget Check
```python
# Should happen BEFORE agenerate() is called
# Should raise BudgetExceededError if block_on_exceed=True
# Should emit BUDGET_WARNING event if block_on_exceed=False
```

### Cost Recording
```python
# Should happen AFTER agenerate() completes
# Should extract token_usage from response
# Should call cost_tracker.record_cost() with:
#   - agent_name
#   - model
#   - input_tokens (from token_usage.input)
#   - output_tokens (from token_usage.output)
#   - project (from context or explicit)
#   - tags (merged from context and explicit)
#   - metadata (passed through)
```

### Event Emission
```python
# COST_RECORDED event should be emitted by cost_tracker.record_cost()
# BUDGET_WARNING event should be emitted by budget_manager if threshold exceeded
# BUDGET_EXCEEDED event should be emitted if block_on_exceed=True and limit exceeded
```

---

## Running the Tests

### Run all Phase 2 tests:
```bash
pytest tests/unit/test_agents.py::TestAgentCostTracking -v
```

### Run only passing tests:
```bash
pytest tests/unit/test_agents.py::TestAgentCostTracking -v -k "not budget_check and not cost_record and not cost_event and not project_and_tags and not multiple_sequential and not async_sync_parity and not metadata_passed and not context_defaults and not concurrent"
```

### Run only failing tests (for Phase 2 implementation):
```bash
pytest tests/unit/test_agents.py::TestAgentCostTracking -v -k "budget_check or cost_record or cost_event or project_and_tags or multiple_sequential or async_sync_parity or metadata_passed or context_defaults or concurrent"
```

---

## Test Statistics

| Category | Count | Status |
|----------|-------|--------|
| Basic Setup & Initialization | 3 | ✅ Pass |
| Graceful Degradation | 2 | ✅ Pass |
| Event Emission | 1 | ✅ Pass |
| Error Handling | 1 | ✅ Pass |
| Non-blocking Budget | 1 | ✅ Pass |
| **Cost Recording** | **4** | ❌ Fail |
| **Budget Enforcement** | **2** | ❌ Fail |
| **Context Integration** | **1** | ❌ Fail |
| **Multi-call Scenarios** | **2** | ❌ Fail |
| **Metadata Handling** | **1** | ❌ Fail |
| **Async/Sync Parity** | **1** | ❌ Fail |
| **Concurrency** | **1** | ❌ Fail |

---

## Coverage Areas

### ✅ Already Covered by Tests
- Agent initialization with/without cost tracking
- Async and sync response creation
- Graceful degradation when services are None or disabled
- Basic error handling
- Non-blocking budget warnings

### ❌ To Be Covered by Phase 2 Implementation
- Pre-call budget checks (blocking behavior)
- Cost recording to persistent store
- Event emission for cost tracking
- Context integration (project/tags from Phase 1)
- Metadata flow-through
- Async/sync implementation parity
- Concurrent call handling
- Multiple sequential calls

---

## Phase 2 Implementation Checklist

- [ ] Create `_run_with_cost_tracking()` async method in BaseAgent
- [ ] Implement pre-call budget check
- [ ] Implement post-call cost recording
- [ ] Update `acreate_response()` to call `_run_with_cost_tracking()`
- [ ] Update `create_response()` to bridge to async helper
- [ ] Verify event emission (COST_RECORDED)
- [ ] Test budget warning/exceeded scenarios
- [ ] Test context integration with Phase 1
- [ ] Run all Phase 2 tests - should pass 18/18
- [ ] Run all Phase 1 tests - should still pass

---

## Next Steps

1. **Implement Phase 2 code** in `src/startd8/agents.py`
2. **Run Phase 2 tests** to verify implementation
3. **Verify Phase 1 tests** still pass (no regression)
4. **Move to Phase 3** (Period Totals)

---

**Test File:** `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/tests/unit/test_agents.py`  
**Test Class:** `TestAgentCostTracking`  
**Total Tests:** 18  
**Expected Status After Phase 2:** 18/18 passing ✅

