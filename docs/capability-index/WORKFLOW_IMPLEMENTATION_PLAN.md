# Workflow Implementation Plan

**Version:** 1.0.0
**Created:** 2026-01-29
**Status:** Draft
**Covers:** 11 draft capabilities, 46 functional requirements, 4 phases
**Breaking changes:** 0

## Executive Summary

This document is the implementation plan for all 11 draft capabilities defined in `startd8.workflow.capabilities.yaml` v2.0.0. The plan covers 46 functional requirements from `startd8.workflow.functional-requirements.yaml` v1.0.0, organized into 4 sequential phases:

| Phase | Name | Capabilities | FRs | Key Deliverables |
|-------|------|-------------|-----|-----------------|
| 1 | Foundation | 4 | 14 | auto_validate, discovery.search, testing.assertions, async_audit |
| 2 | Core Orchestration | 5 | 17 | retry, mixed_steps (FR-310), conditional, parallel, compose |
| 3 | Observability | 3 | 12 | dry_run, otel, visualize |
| 4 | Enterprise | 1 | 3 | http server |
| **Total** | | **11 (+2 partial upgrades)** | **46** | |

All changes are additive. Zero breaking changes. Three new optional dependencies (`jsonschema`, `opentelemetry-api`, `starlette`+`uvicorn`). Three new modules (`startd8.testing`, `startd8.workflows.visualizer`, `startd8.server`).

### Cross-References

- **Capabilities manifest:** `docs/capability-index/startd8.workflow.capabilities.yaml`
- **Functional requirements:** `docs/capability-index/startd8.workflow.functional-requirements.yaml`
- **Gap analysis:** `docs/capability-index/startd8.workflow.gap-analysis.md`
- **Benefits manifest:** `docs/capability-index/startd8.workflow.benefits.yaml`

---

## Phase 1: Foundation

**Capabilities:** `auto_validate`, `discovery.search`, `testing.assertions`, `async_audit`
**FRs:** FR-110, FR-111, FR-112, FR-200, FR-201, FR-210, FR-211, FR-212, FR-500, FR-501, FR-502, FR-503, FR-504, FR-150
**Benefits delivered:** `workflow.authoring.validation_helpers`, `workflow.discovery.search_filter` (partial delivered), `workflow.testing.workflow_assertions`, `workflow.execution.async_native` (partial delivered)

### 1.1 Auto-Validate (FR-110, FR-111, FR-112)

**Capability:** `startd8.workflow.authoring.auto_validate`

Enhance `WorkflowBase.validate_config()` to auto-validate input types from `WorkflowInput.type` definitions, add optional JSON Schema validation, and provide a composable `_custom_validate()` hook.

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/workflows/base.py` (lines 178-206) | Extend `validate_config()` with type checking; add `_custom_validate()` method |
| `pyproject.toml` | Add `jsonschema` to optional dependencies: `validate = ["jsonschema"]` |

#### Implementation Details

**FR-110 — Type checking in `validate_config()`**

Add type validation after the existing required-field check in `WorkflowBase.validate_config()` (line 188-200):

```python
# After existing required-input check (line 190)
# Add type validation
TYPE_MAP = {
    "string": str, "text": str, "file": str,
    "number": (int, float), "boolean": bool,
    "agent_spec": str, "agent_spec_list": list,
}
for inp in meta.inputs:
    if inp.name in config:
        expected = TYPE_MAP.get(inp.type)
        if expected and not isinstance(config[inp.name], expected):
            errors.append(
                f"Input '{inp.name}': expected {inp.type}, "
                f"got {type(config[inp.name]).__name__}"
            )
```

**FR-111 — Optional JSON Schema validation**

After type checking, attempt JSON Schema validation if `jsonschema` is installed:

```python
try:
    import jsonschema
    schema = meta.get_input_schema()
    jsonschema.validate(config, schema)
except ImportError:
    pass  # Graceful fallback
except jsonschema.ValidationError as e:
    errors.append(f"Schema validation: {e.json_path}: {e.message}")
```

`get_input_schema()` already exists on `WorkflowMetadata` (models.py line 167-181).

**FR-112 — `_custom_validate()` hook**

Add to `WorkflowBase`:

```python
def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
    """Override for workflow-specific validation. Returns error messages."""
    return []
```

Call at end of `validate_config()`, before returning:

```python
# Merge custom validation errors
errors.extend(self._custom_validate(config))
```

#### Implementation Order

1. FR-110 (type checking) — standalone, no dependencies
2. FR-112 (`_custom_validate` hook) — standalone, integrates into same method
3. FR-111 (JSON Schema) — requires `pyproject.toml` change for optional dep

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_workflow_validation.py` (new) | `test_type_validation_string`, `test_type_validation_number`, `test_type_validation_boolean`, `test_type_validation_wrong_type_error_message`, `test_custom_validate_hook_called`, `test_custom_validate_errors_merged`, `test_json_schema_validation_when_installed`, `test_json_schema_graceful_fallback`, `test_existing_validation_preserved` |

#### Acceptance Criteria

- [ ] Type checking validates string, number, boolean inputs against `WorkflowInput.type`
- [ ] Error messages include field name, expected type, and actual type
- [ ] `_custom_validate()` returns `[]` by default and is called after auto-validation
- [ ] JSON Schema validation works when `jsonschema` is installed
- [ ] Graceful fallback to type-only validation when `jsonschema` absent
- [ ] All existing `validate_config()` overrides still work

#### Risks

| Risk | Mitigation |
|------|-----------|
| Custom `validate_config()` overrides bypass new logic | Auto-validation only applies to `WorkflowBase.validate_config()`; subclass overrides are unaffected |
| `jsonschema` version compatibility | Pin `jsonschema>=4.0` in optional deps |

---

### 1.2 Discovery Search (FR-200, FR-201, FR-210, FR-211, FR-212)

**Capability:** `startd8.workflow.discovery.search`

Add partial/substring matching to `find_workflows_by_capability()`, a new `search_workflows()` method, and CLI filter flags.

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/workflows/registry.py` (lines 449-491) | Modify `find_workflows_by_capability()` for partial match; add `search_workflows()` |
| `src/startd8/cli.py` | Add `--capability`, `--tag`, `--search` flags to `workflow list` command |

#### Implementation Details

**FR-200 — Partial matching in `find_workflows_by_capability()`**

Current code (registry.py line 468-471) uses exact match:

```python
# Current: exact match
if capability_lower in [c.lower() for c in w.metadata.capabilities]
```

Change to substring match:

```python
# New: partial/substring match
if any(capability_lower in c.lower() for c in w.metadata.capabilities)
```

Exact match still works (it's a subset of substring match).

**FR-201 — `search_workflows(query)`**

Add new method after `find_workflows_by_tag()` (after line 491):

```python
@classmethod
def search_workflows(cls, query: str) -> List[Workflow]:
    """Search workflows by name or description text."""
    cls.discover()
    query_lower = query.lower()
    with cls._lock:
        return [
            w for w in cls._workflows.values()
            if query_lower in w.metadata.name.lower()
            or query_lower in w.metadata.description.lower()
        ]
```

**FR-210, FR-211, FR-212 — CLI flags**

Add optional parameters to the `workflow list` command in `cli.py`:

```python
@workflow_app.command("list")
def workflow_list(
    capability: Optional[str] = typer.Option(None, help="Filter by capability (partial match)"),
    tag: Optional[str] = typer.Option(None, help="Filter by tag"),
    search: Optional[str] = typer.Option(None, help="Search name and description"),
):
```

Apply filters sequentially (intersection when multiple flags used).

#### Implementation Order

1. FR-200 (partial match) — modifies existing method
2. FR-201 (`search_workflows`) — new method, no dependencies
3. FR-210, FR-211, FR-212 (CLI flags) — depend on FR-200 and FR-201

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_workflow_registry.py` (extend) | `test_find_by_capability_partial_match`, `test_find_by_capability_exact_still_works`, `test_search_workflows_by_name`, `test_search_workflows_by_description`, `test_search_case_insensitive` |
| `tests/unit/test_cli_workflow.py` (extend) | `test_workflow_list_capability_filter`, `test_workflow_list_tag_filter`, `test_workflow_list_search_filter`, `test_workflow_list_combined_filters` |

#### Acceptance Criteria

- [ ] `find_workflows_by_capability('doc')` matches `'document-enhancement'`
- [ ] Existing exact match still works
- [ ] `search_workflows('document')` finds workflows with `'document'` in name or description
- [ ] `startd8 workflow list --capability code-review` filters output
- [ ] `startd8 workflow list --tag multi-agent` filters output
- [ ] `startd8 workflow list --search document` shows matching workflows
- [ ] Flags are optional; omitting shows all workflows
- [ ] `--capability` and `--tag` are combinable

#### Risks

| Risk | Mitigation |
|------|-----------|
| Partial match returns too many results for short queries | Minimum 2-character query length in CLI |

---

### 1.3 Testing Assertions (FR-500, FR-501, FR-502, FR-503, FR-504)

**Capability:** `startd8.workflow.testing.assertions`

Create a new `startd8.testing` module with pytest assertion helpers for `WorkflowResult`.

#### Files to Create

| File | Purpose |
|------|---------|
| `src/startd8/testing/__init__.py` | Package init, re-exports all assertion functions |
| `src/startd8/testing/assertions.py` | Assertion function implementations |

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/__init__.py` | No changes needed (testing module imported separately) |

#### Implementation Details

**FR-500 — Module structure**

```
src/startd8/testing/
├── __init__.py      # from .assertions import *
└── assertions.py    # All assertion functions
```

**FR-501 — `assert_workflow_success(result)`**

```python
def assert_workflow_success(result: WorkflowResult) -> None:
    if not result.success:
        step_summary = "\n".join(
            f"  - {s.step_name}: {'OK' if s.success else f'FAILED: {s.error}'}"
            for s in result.steps
        )
        raise AssertionError(
            f"Workflow '{result.workflow_id}' failed: {result.error}\n"
            f"Steps:\n{step_summary}"
        )
```

**FR-502 — `assert_step_called` / `assert_step_not_called`**

```python
def assert_step_called(result: WorkflowResult, step_name: str) -> None:
    names = [s.step_name for s in result.steps]
    if step_name not in names:
        raise AssertionError(
            f"Step '{step_name}' was not called. "
            f"Executed steps: {names}"
        )

def assert_step_not_called(result: WorkflowResult, step_name: str) -> None:
    names = [s.step_name for s in result.steps]
    if step_name in names:
        raise AssertionError(
            f"Step '{step_name}' was called but should not have been. "
            f"Executed steps: {names}"
        )
```

**FR-503 — `assert_cost_below(result, max_cost)`**

```python
def assert_cost_below(result: WorkflowResult, max_cost: float) -> None:
    actual = result.metrics.total_cost
    if actual > max_cost:
        raise AssertionError(
            f"Workflow cost ${actual:.4f} exceeds limit ${max_cost:.4f}"
        )
```

**FR-504 — `assert_steps_in_order(result, expected_step_names)`**

```python
def assert_steps_in_order(result: WorkflowResult, expected: List[str]) -> None:
    actual = [s.step_name for s in result.steps]
    idx = 0
    for name in expected:
        try:
            idx = actual.index(name, idx) + 1
        except ValueError:
            raise AssertionError(
                f"Expected step order {expected}, "
                f"but '{name}' not found after position {idx}. "
                f"Actual: {actual}"
            )
```

#### Implementation Order

1. FR-500 (module creation) — prerequisite for all others
2. FR-501, FR-502, FR-503, FR-504 — all independent, implement in parallel

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_testing_assertions.py` (new) | `test_assert_success_passes`, `test_assert_success_fails_with_details`, `test_assert_step_called_found`, `test_assert_step_called_not_found`, `test_assert_step_not_called_found`, `test_assert_step_not_called_absent`, `test_assert_cost_below_passes`, `test_assert_cost_below_fails`, `test_assert_steps_in_order_passes`, `test_assert_steps_in_order_allows_gaps`, `test_assert_steps_in_order_fails_wrong_order` |

#### Acceptance Criteria

- [ ] `from startd8.testing import assert_workflow_success` works
- [ ] `assert_workflow_success` raises `AssertionError` with workflow_id, error, and step statuses
- [ ] `assert_step_called` / `assert_step_not_called` check step presence
- [ ] `assert_cost_below` compares `metrics.total_cost` against limit
- [ ] `assert_steps_in_order` verifies order without requiring exact match

#### Risks

| Risk | Mitigation |
|------|-----------|
| None significant | New module, no existing code affected |

---

### 1.4 Async Audit (FR-150)

**Capability:** `startd8.workflow.execution.async_audit`

Audit all 9 builtin workflows and add native `_aexecute()` where workflows make async agent calls.

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/workflows/builtin/doc_enhancement_workflow.py` | Add `_aexecute()` if using `acreate_response()` |
| `src/startd8/workflows/builtin/critical_review_workflow.py` | Add `_aexecute()` if using `acreate_response()` |
| `src/startd8/workflows/builtin/design_polish_workflow.py` | Add `_aexecute()` if using `acreate_response()` |
| `src/startd8/workflows/builtin/policy_analysis_workflow.py` | Add `_aexecute()` if using `acreate_response()` |
| `src/startd8/workflows/builtin/plain_language_workflow.py` | Add `_aexecute()` if using `acreate_response()` |
| `src/startd8/workflows/builtin/lead_contractor_workflow.py` | Add `_aexecute()` if using `acreate_response()` |

#### Implementation Details

For each builtin workflow:

1. Review `_execute()` implementation
2. If it calls `agent.create_response()` (sync), add `_aexecute()` that calls `agent.acreate_response()` instead
3. `WorkflowBase.arun()` (base.py lines 268-313) already prefers `_aexecute()` when available and falls back to sync in executor — so adding `_aexecute()` removes thread pool overhead

Template for each workflow:

```python
async def _aexecute(self, config, agents, on_progress):
    # Same logic as _execute but using:
    #   await agent.acreate_response(...) instead of agent.create_response(...)
    ...
```

#### Implementation Order

1. Audit all 9 builtin workflows (identify which use sync agent calls)
2. Add `_aexecute()` to each identified workflow — order doesn't matter

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_async_workflows.py` (new) | `test_doc_enhancement_arun`, `test_critical_review_arun`, `test_design_polish_arun`, `test_policy_analysis_arun`, `test_plain_language_arun`, `test_lead_contractor_arun` (each verifying `_aexecute` exists and returns `WorkflowResult`) |

#### Acceptance Criteria

- [ ] Each builtin workflow reviewed for async support
- [ ] Workflows calling `acreate_response()` implement `_aexecute()`
- [ ] `WorkflowBase` executor fallback still handles sync-only workflows
- [ ] No behavioral changes to existing sync execution
- [ ] `await workflow.arun(config, agents)` works for all builtins

#### Risks

| Risk | Mitigation |
|------|-----------|
| Async logic diverges from sync over time | Keep `_execute` and `_aexecute` as thin wrappers calling shared private methods |

---

## Phase 2: Core Orchestration

**Capabilities:** `retry`, `mixed_steps`, `conditional`, `parallel`, `compose`
**FRs:** FR-100, FR-101, FR-300, FR-301, FR-302, FR-310, FR-311, FR-312, FR-320, FR-321, FR-322, FR-330, FR-331, FR-332, FR-410, FR-411, FR-511
**Benefits delivered:** `workflow.execution.retry_resilience`, `workflow.execution.conditional_routing`, `workflow.execution.parallel_agents` (partial delivered), `workflow.reusability.composition`

### 2.1 Retry Resilience (FR-100, FR-101, FR-300, FR-301, FR-302, FR-410, FR-411, FR-511)

**Capability:** `startd8.workflow.execution.retry`

Add `RetryPolicy` model, per-step retry loop in `Pipeline.arun()`, error classification, checkpoint/resume, retry events, and CLI flag.

#### New Data Models

```python
# In src/startd8/workflows/models.py

@dataclass
class RetryPolicy:
    """Configuration for automatic retry on transient failures."""
    max_retries: int = 3
    backoff_base: float = 1.0       # seconds
    backoff_max: float = 60.0       # seconds
    jitter: bool = True
    retryable_status_codes: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )
```

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/workflows/models.py` | Add `RetryPolicy` dataclass (FR-100); add `total_retries: int = 0` to `WorkflowMetrics` (FR-411) |
| `src/startd8/workflows/base.py` (lines 208-266) | Add `retry_policy=None` parameter to `run()` and `arun()` signatures (FR-101) |
| `src/startd8/orchestration.py` (lines 117-341) | Add retry loop in `Pipeline.arun()` around step execution (FR-300); add `is_retryable()` function (FR-301); add checkpoint tracking (FR-302) |
| `src/startd8/events/types.py` (line 44) | Add `PIPELINE_STEP_RETRY = auto()` to `EventType` enum (FR-410) |
| `src/startd8/cli.py` | Add `--max-retries` flag to `workflow run` command (FR-511) |

#### Implementation Details

**FR-301 — Error classification (`is_retryable`)**

Add as a module-level function in `orchestration.py`:

```python
import httpx

def is_retryable(exc: Exception, retryable_codes: List[int]) -> bool:
    """Classify exception as retryable or fatal."""
    if isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in retryable_codes
    # Fatal: ValidationError, ConfigurationError, 400/401/403
    return False
```

**FR-300 — Retry loop in `Pipeline.arun()`**

Wrap the agent call block (lines 197-203) in a retry loop:

```python
# Inside the for loop over steps (line 170)
retry_count = 0
last_error = None
for attempt in range(1 + (retry_policy.max_retries if retry_policy else 0)):
    try:
        agent_response = await step.agent.acreate_response(...)
        break
    except Exception as e:
        if not retry_policy or not is_retryable(e, retry_policy.retryable_status_codes):
            raise
        last_error = e
        retry_count = attempt + 1
        delay = min(
            retry_policy.backoff_base * (2 ** attempt),
            retry_policy.backoff_max
        )
        if retry_policy.jitter:
            import random
            delay += random.uniform(0, delay * 0.1)
        # Emit retry event (FR-410)
        EventBus.emit(Event(
            type=EventType.PIPELINE_STEP_RETRY,
            source="Pipeline",
            data={
                "step_name": step.name,
                "attempt_number": retry_count,
                "error": str(e),
                "delay_seconds": delay,
            },
            correlation_id=pipeline_id
        ))
        await asyncio.sleep(delay)
else:
    raise last_error
```

**FR-302 — Checkpoint tracking**

Track completed step indices during execution:

```python
completed_steps: List[int] = []  # After each successful step
# At start of loop, skip if resuming:
# if resume_from and i < resume_from: continue
```

**FR-411 — Retry count in metrics**

Add `retry_count` to each `step_result` metadata dict, and sum into `WorkflowMetrics.total_retries`.

#### Implementation Order

1. FR-100 (RetryPolicy model) — no dependencies
2. FR-411 (total_retries field on WorkflowMetrics) — no dependencies
3. FR-410 (PIPELINE_STEP_RETRY event type) — no dependencies
4. FR-101 (retry_policy parameter on run/arun) — depends on FR-100
5. FR-301 (is_retryable function) — depends on FR-100
6. FR-300 (retry loop in Pipeline.arun) — depends on FR-100, FR-101, FR-301, FR-410
7. FR-302 (checkpoint) — depends on FR-300
8. FR-511 (CLI --max-retries) — depends on FR-300

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_retry.py` (new) | `test_retry_policy_defaults`, `test_is_retryable_timeout`, `test_is_retryable_429`, `test_is_retryable_401_fatal`, `test_pipeline_retry_on_transient`, `test_pipeline_no_retry_on_fatal`, `test_pipeline_retry_backoff_increases`, `test_pipeline_retry_event_emitted`, `test_retry_count_in_step_metadata`, `test_total_retries_in_metrics`, `test_pipeline_without_retry_policy`, `test_checkpoint_tracks_completed` |

#### Acceptance Criteria

- [ ] `RetryPolicy` dataclass importable from `startd8.workflows.models`
- [ ] `RetryPolicy` defaults: `max_retries=3`, `backoff_base=1.0`, `backoff_max=60`, `jitter=True`
- [ ] `run()` and `arun()` accept optional `retry_policy` parameter (None = no retry)
- [ ] Each step retried up to `max_retries` on retryable errors
- [ ] Exponential backoff: `delay = min(base * 2^attempt, max) + jitter`
- [ ] Non-retryable errors (400, 401, 403) fail immediately
- [ ] `PIPELINE_STEP_RETRY` event emitted before backoff sleep
- [ ] `StepResult.metadata['retry_count']` set after execution
- [ ] `WorkflowMetrics.total_retries` field included in `to_dict()`

#### Risks

| Risk | Mitigation |
|------|-----------|
| Retry loop increases step execution time | Backoff max caps at 60s; configurable via RetryPolicy |
| Random jitter non-deterministic in tests | Seed random in test fixtures or mock `random.uniform` |

---

### 2.2 Mixed Steps — Pipeline Refactor (FR-310)

**Capability:** `startd8.workflow.execution.mixed_steps`

> **Critical refactor.** This FR refactors `Pipeline.arun()` from a flat `for` loop iterating `PipelineStep` instances to an `isinstance` dispatch pattern. It unlocks three capabilities simultaneously: conditional (2.3), parallel (2.4), and compose (2.5).

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/orchestration.py` (lines 170-261) | Refactor step execution loop to dispatch by type |

#### Current Code (lines 170-261)

```python
for i, step in enumerate(self.steps):
    # Assumes step is always PipelineStep
    step_input = step.transform(current_input) if step.transform else current_input
    agent_response = await step.agent.acreate_response(...)
    ...
```

#### New Code Structure

```python
for i, step in enumerate(self.steps):
    if isinstance(step, PipelineStep):
        # Existing sequential behavior (unchanged)
        current_input = await self._execute_sequential_step(step, current_input, ...)
    elif isinstance(step, ConditionalStep):
        # Evaluate predicate, run matching branch
        current_input = await self._execute_conditional_step(step, current_input, ...)
    elif isinstance(step, ParallelStep):
        # Run steps concurrently via asyncio.gather
        current_input = await self._execute_parallel_step(step, current_input, ...)
    elif isinstance(step, WorkflowStep):
        # Delegate to sub-workflow
        current_input = await self._execute_workflow_step(step, current_input, ...)
    else:
        raise TypeError(f"Unknown step type: {type(step)}")
```

The existing `PipelineStep` code block (lines 184-261) becomes `_execute_sequential_step()` — an extract-method refactoring with identical behavior.

#### Type Changes

Update `Pipeline.steps` type hint:

```python
# Before
self.steps: List[PipelineStep] = []

# After
from typing import Union
StepType = Union[PipelineStep, 'ConditionalStep', 'ParallelStep', 'WorkflowStep']
self.steps: List[StepType] = []
```

#### Implementation Order

1. Extract `_execute_sequential_step()` from current inline code
2. Add `isinstance` dispatch in `arun()` loop
3. Verify all existing Pipeline tests pass unchanged

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_pipeline.py` (extend) | `test_existing_pipeline_unchanged`, `test_unknown_step_type_raises`, `test_mixed_step_types_accepted` |

#### Acceptance Criteria

- [ ] `Pipeline.arun()` dispatches on `isinstance` for each step type
- [ ] `PipelineStep` behavior identical to current implementation
- [ ] `Pipeline.steps` accepts `Union[PipelineStep, ConditionalStep, ParallelStep, WorkflowStep]`
- [ ] Unknown step types raise `TypeError`
- [ ] All existing Pipeline tests pass without modification

#### Risks

| Risk | Mitigation |
|------|-----------|
| Regression in core pipeline loop | Extract-method refactoring preserves behavior; run full test suite before and after |
| Type hint `Union` may confuse static analysis | Add `StepType` type alias for clarity |

---

### 2.3 Conditional Routing (FR-311, FR-312)

**Capability:** `startd8.workflow.execution.conditional`

Define `ConditionalStep` and add `Pipeline.add_conditional()`.

#### New Data Models

```python
# In src/startd8/orchestration.py

@dataclass
class ConditionalStep:
    """A pipeline step that branches based on a predicate."""
    name: str
    predicate: Callable[[str], bool]   # Receives previous step output
    if_step: PipelineStep              # Run if predicate returns True
    else_step: Optional[PipelineStep] = None  # Run if predicate returns False (optional)
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
```

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/orchestration.py` | Add `ConditionalStep` dataclass (FR-311); add `Pipeline.add_conditional()` method (FR-312); implement `_execute_conditional_step()` |

#### Implementation Details

**FR-312 — `Pipeline.add_conditional()`**

```python
def add_conditional(
    self,
    name: str,
    predicate: Callable[[str], bool],
    if_agent: BaseAgent,
    else_agent: Optional[BaseAgent] = None,
    if_transform: Optional[Callable[[str], str]] = None,
    else_transform: Optional[Callable[[str], str]] = None,
) -> 'Pipeline':
    if_step = PipelineStep(name=f"{name}_if", agent=if_agent, transform=if_transform)
    else_step = PipelineStep(name=f"{name}_else", agent=else_agent, transform=else_transform) if else_agent else None
    self.steps.append(ConditionalStep(name=name, predicate=predicate, if_step=if_step, else_step=else_step))
    return self
```

**`_execute_conditional_step()`**

```python
async def _execute_conditional_step(self, step, current_input, ...):
    branch_taken = step.predicate(current_input)
    target = step.if_step if branch_taken else step.else_step
    if target is None:
        return current_input  # No else_step, skip
    return await self._execute_sequential_step(target, current_input, ...)
```

#### Implementation Order

1. FR-311 (ConditionalStep dataclass) — no dependencies
2. FR-312 (add_conditional method) — depends on FR-311, FR-310

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_conditional.py` (new) | `test_conditional_true_branch`, `test_conditional_false_branch`, `test_conditional_no_else_skips`, `test_add_conditional_returns_self`, `test_conditional_metadata_includes_branch` |

#### Acceptance Criteria

- [ ] `ConditionalStep(name, predicate, if_step, else_step)` defined
- [ ] `predicate: Callable[[str], bool]` receives previous step output
- [ ] `else_step` is optional (skip if predicate False and no else)
- [ ] `Pipeline.add_conditional()` returns self for chaining
- [ ] Step result metadata includes which branch was taken

---

### 2.4 Parallel Execution (FR-320, FR-321, FR-322)

**Capability:** `startd8.workflow.execution.parallel`

Define `ParallelStep` and add `Pipeline.add_parallel()` with configurable failure policy.

#### New Data Models

```python
# In src/startd8/orchestration.py

@dataclass
class ParallelStep:
    """A pipeline step that runs multiple steps concurrently."""
    name: str
    steps: List[PipelineStep]
    aggregator: Optional[Callable[[List[str]], str]] = None  # Default: join with separator
    failure_policy: str = "collect_all"  # "fail_fast" | "collect_all"
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.aggregator is None:
            self.aggregator = lambda outputs: "\n---\n".join(outputs)
```

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/orchestration.py` | Add `ParallelStep` dataclass (FR-320); add `Pipeline.add_parallel()` (FR-321); implement `_execute_parallel_step()` with failure policy (FR-322) |

#### Implementation Details

**FR-321 — `Pipeline.add_parallel()`**

```python
def add_parallel(
    self,
    name: str,
    steps: List[PipelineStep],
    aggregator: Optional[Callable[[List[str]], str]] = None,
    failure_policy: str = "collect_all",
) -> 'Pipeline':
    self.steps.append(ParallelStep(
        name=name, steps=steps, aggregator=aggregator, failure_policy=failure_policy
    ))
    return self
```

**FR-322 — `_execute_parallel_step()` with failure policy**

```python
async def _execute_parallel_step(self, step, current_input, ...):
    async def run_sub(sub_step):
        return await self._execute_sequential_step(sub_step, current_input, ...)

    if step.failure_policy == "fail_fast":
        results = await asyncio.gather(
            *[run_sub(s) for s in step.steps]
            # No return_exceptions — first failure propagates
        )
    else:  # collect_all
        results = await asyncio.gather(
            *[run_sub(s) for s in step.steps],
            return_exceptions=True
        )
        # Separate successes and failures
        outputs = []
        for r in results:
            if isinstance(r, Exception):
                outputs.append(f"[ERROR: {r}]")
            else:
                outputs.append(r)

    return step.aggregator(outputs)
```

#### Implementation Order

1. FR-320 (ParallelStep dataclass) — no dependencies
2. FR-321 (add_parallel method) — depends on FR-320, FR-310
3. FR-322 (failure policy handling) — depends on FR-320

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_parallel.py` (new) | `test_parallel_runs_concurrently`, `test_parallel_results_ordered`, `test_parallel_default_aggregator`, `test_parallel_custom_aggregator`, `test_parallel_collect_all_partial_failure`, `test_parallel_fail_fast_cancels`, `test_add_parallel_returns_self` |

#### Acceptance Criteria

- [ ] `ParallelStep(name, steps, aggregator, failure_policy)` defined
- [ ] Steps run concurrently via `asyncio.gather()`
- [ ] Results ordered same as input steps
- [ ] `fail_fast`: cancel remaining on first failure
- [ ] `collect_all`: run all, return mixed success/failure results
- [ ] Default aggregator joins outputs with separator

---

### 2.5 Workflow Composition (FR-330, FR-331, FR-332)

**Capability:** `startd8.workflow.reusability.compose`

Define `WorkflowStep` and add `Pipeline.add_workflow()` with metrics aggregation.

#### New Data Models

```python
# In src/startd8/orchestration.py

@dataclass
class WorkflowStep:
    """A pipeline step that delegates to a sub-workflow."""
    name: str
    workflow: 'WorkflowBase'  # The sub-workflow instance
    config_mapping: Callable[[str], Dict[str, Any]]  # Transform previous output to config
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
```

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/orchestration.py` | Add `WorkflowStep` dataclass (FR-330); add `Pipeline.add_workflow()` (FR-331); implement `_execute_workflow_step()` with metrics aggregation (FR-332) |

#### Implementation Details

**FR-331 — `Pipeline.add_workflow()`**

```python
def add_workflow(
    self,
    name: str,
    workflow: 'WorkflowBase',
    config_mapping: Callable[[str], Dict[str, Any]],
) -> 'Pipeline':
    self.steps.append(WorkflowStep(name=name, workflow=workflow, config_mapping=config_mapping))
    return self
```

**FR-332 — `_execute_workflow_step()` with metrics aggregation**

```python
async def _execute_workflow_step(self, step, current_input, pipeline_id, ...):
    config = step.config_mapping(current_input)
    # Validate sub-workflow
    validation = step.workflow.validate_config(config)
    if not validation.valid:
        raise ConfigurationError(f"Sub-workflow validation failed: {validation.errors}")

    # Execute sub-workflow
    if hasattr(step.workflow, 'arun'):
        result = await step.workflow.arun(config, agents=config.get('agents'))
    else:
        result = step.workflow.run(config, agents=config.get('agents'))

    # Aggregate metrics into parent
    if result.metrics:
        total_tokens += result.metrics.input_tokens + result.metrics.output_tokens
        total_cost += result.metrics.total_cost

    # Flatten sub-workflow steps with namespace prefix
    for sub_step in result.steps:
        sub_step.step_name = f"{step.name}:{sub_step.step_name}"
        step_results.append(sub_step.to_dict())

    return str(result.output) if result.output else ""
```

#### Implementation Order

1. FR-330 (WorkflowStep dataclass) — no dependencies
2. FR-331 (add_workflow method) — depends on FR-330, FR-310
3. FR-332 (metrics aggregation) — depends on FR-330

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_compose.py` (new) | `test_workflow_step_delegates`, `test_config_mapping_called`, `test_sub_workflow_validated`, `test_sub_workflow_metrics_aggregated`, `test_sub_workflow_steps_namespaced`, `test_add_workflow_returns_self` |

#### Acceptance Criteria

- [ ] `WorkflowStep(name, workflow, config_mapping)` defined
- [ ] `config_mapping` transforms previous output to sub-workflow config
- [ ] Sub-workflow validated before execution
- [ ] Sub-workflow tokens/cost added to parent `WorkflowMetrics`
- [ ] Sub-workflow `StepResult`s flattened with `"sub:"` prefix (e.g., `"enhance:step1"`)
- [ ] `Pipeline.add_workflow()` returns self for chaining

---

### Phase 2 Dependency Chain

```
FR-100 (RetryPolicy) ─────┬──> FR-101 (retry param) ──> FR-300 (retry loop) ──> FR-302 (checkpoint)
                           │                                     │                      │
FR-301 (is_retryable) ─────┘                                     ├──> FR-410 (retry event)
                                                                 ├──> FR-411 (retry metrics)
                                                                 └──> FR-511 (CLI flag)

FR-310 (dispatch refactor) ──┬──> FR-312 (add_conditional) ←── FR-311 (ConditionalStep)
                             ├──> FR-321 (add_parallel) ←── FR-320 (ParallelStep) ──> FR-322 (failure policy)
                             └──> FR-331 (add_workflow) ←── FR-330 (WorkflowStep) ──> FR-332 (metrics)
```

**Recommended order:** FR-100, FR-301, FR-410, FR-411 → FR-101, FR-300, FR-302, FR-511 → FR-310 → FR-311, FR-320, FR-330 → FR-312, FR-321, FR-322, FR-331, FR-332

---

## Phase 3: Observability

**Capabilities:** `dry_run`, `otel`, `visualize`
**FRs:** FR-102, FR-103, FR-340, FR-341, FR-400, FR-401, FR-402, FR-403, FR-420, FR-421, FR-510, FR-530
**Benefits delivered:** `workflow.execution.dry_run`, `workflow.observability.otel_integration`, `workflow.observability.visualization`

### 3.1 Dry Run (FR-102, FR-103, FR-340, FR-341, FR-510)

**Capability:** `startd8.workflow.execution.dry_run`

Simulate workflow execution without API calls, returning an execution plan and cost estimate.

#### New Data Models

```python
# In src/startd8/workflows/models.py

@dataclass
class DryRunResult:
    """Result of a dry-run simulation."""
    execution_plan: List[Dict[str, Any]]  # Step details
    estimated_tokens: Dict[str, int]      # Per-step token estimates
    estimated_cost: float                 # Total estimated cost
    step_order: List[str]                 # Step names in execution order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_plan": self.execution_plan,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost": self.estimated_cost,
            "step_order": self.step_order,
        }
```

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/workflows/models.py` | Add `DryRunResult` dataclass (FR-102) |
| `src/startd8/workflows/base.py` (lines 208-266) | Add `dry_run: bool = False` parameter to `run()` (FR-103); intercept before `_execute()` (FR-340); estimate tokens/cost (FR-341) |
| `src/startd8/cli.py` | Add `--dry-run` flag to `workflow run` command (FR-510) |

#### Implementation Details

**FR-103 — `dry_run` parameter on `run()`**

```python
def run(self, config, agents=None, on_progress=None, dry_run=False):
    validation = self.validate_config(config)
    if not validation.valid:
        return WorkflowResult.from_error(...)

    if dry_run:
        return self._build_dry_run_result(config, agents)

    # Existing execution logic...
```

**FR-340 — Dry run interception**

```python
def _build_dry_run_result(self, config, agents):
    meta = self.metadata
    steps = []
    for i, inp in enumerate(meta.inputs):
        steps.append({
            "step": i + 1,
            "name": inp.name,
            "type": inp.type,
            "agent": agents[i].name if agents and i < len(agents) else "unassigned",
        })

    step_order = [inp.name for inp in meta.inputs]
    estimated_tokens = self._estimate_tokens(config)
    estimated_cost = self._estimate_cost(estimated_tokens)

    dry_result = DryRunResult(
        execution_plan=steps,
        estimated_tokens=estimated_tokens,
        estimated_cost=estimated_cost,
        step_order=step_order,
    )
    return WorkflowResult(
        workflow_id=meta.workflow_id,
        success=True,
        output=dry_result.to_dict(),
        metadata={"dry_run": True},
    )
```

**FR-341 — Token/cost estimation**

```python
def _estimate_tokens(self, config):
    """Estimate tokens from input character count (chars/4 heuristic)."""
    estimates = {}
    for inp in self.metadata.inputs:
        value = config.get(inp.name, "")
        char_count = len(str(value))
        input_tokens = char_count // 4
        output_tokens = input_tokens * 2  # Model-specific multiplier
        estimates[inp.name] = {"input": input_tokens, "output": output_tokens}
    return estimates

def _estimate_cost(self, token_estimates):
    """Estimate cost using PricingService."""
    try:
        from ..costs.pricing import PricingService
        # Use default pricing for estimation
        total = 0.0
        for name, tokens in token_estimates.items():
            total += PricingService.estimate(tokens["input"], tokens["output"])
        return total
    except ImportError:
        return 0.0
```

**FR-510 — CLI `--dry-run` flag**

```python
@workflow_app.command("run")
def workflow_run(
    ...,
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without API calls"),
):
    if dry_run:
        result = registry.run_workflow(workflow_id, config, dry_run=True)
        # Display Rich table with execution plan
```

#### Implementation Order

1. FR-102 (DryRunResult model) — no dependencies
2. FR-103 (dry_run parameter) — depends on FR-102
3. FR-340 (dry run interception) — depends on FR-102, FR-103
4. FR-341 (token/cost estimation) — depends on FR-340
5. FR-510 (CLI --dry-run) — depends on FR-340

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_dry_run.py` (new) | `test_dry_run_result_serializable`, `test_dry_run_no_api_calls`, `test_dry_run_returns_execution_plan`, `test_dry_run_estimates_tokens`, `test_dry_run_estimates_cost`, `test_dry_run_metadata_flag`, `test_dry_run_backward_compatible` |

#### Acceptance Criteria

- [ ] `DryRunResult` dataclass with `execution_plan`, `estimated_tokens`, `estimated_cost`, `step_order`
- [ ] `run(dry_run=True)` builds execution plan without calling `_execute()`
- [ ] No LLM API calls made during dry run
- [ ] Token estimation uses chars/4 heuristic
- [ ] Cost estimation uses `PricingService`
- [ ] `WorkflowResult.metadata['dry_run'] == True`
- [ ] `startd8 workflow run <id> --dry-run` shows plan in Rich table

---

### 3.2 OpenTelemetry Integration (FR-400, FR-401, FR-402, FR-403)

**Capability:** `startd8.workflow.observability.otel`

Add OpenTelemetry span instrumentation for workflow and step execution.

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/workflows/base.py` | Add OTel parent span in `run()`/`arun()` (FR-400); attach ProjectContext labels (FR-402); graceful no-op (FR-403) |
| `src/startd8/orchestration.py` | Add child span per step in `_execute_sequential_step()` (FR-401) |
| `pyproject.toml` | Add optional dependency: `otel = ["opentelemetry-api"]` |

#### Implementation Details

**FR-403 — Graceful no-op (implement first)**

```python
# At top of base.py
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("startd8.workflows")
except ImportError:
    _tracer = None
```

**FR-400 — Parent span in `run()`**

```python
def run(self, config, agents=None, on_progress=None, ...):
    span_ctx = None
    if _tracer:
        span_ctx = _tracer.start_span(
            f"workflow.{self.metadata.workflow_id}",
            attributes={
                "workflow.id": self.metadata.workflow_id,
                "workflow.name": self.metadata.name,
                "workflow.version": self.metadata.version,
            }
        )
    try:
        result = ...  # existing logic
        return result
    except Exception as e:
        if span_ctx:
            span_ctx.set_status(trace.StatusCode.ERROR, str(e))
            span_ctx.record_exception(e)
        raise
    finally:
        if span_ctx:
            span_ctx.end()
```

**FR-401 — Child span per step**

In `_execute_sequential_step()` (orchestration.py):

```python
if _tracer:
    step_span = _tracer.start_span(
        f"workflow.{self.name}.step.{step.name}",
        attributes={
            "step.name": step.name,
            "agent.name": step.agent.name,
            "agent.model": step.agent.model,
        }
    )
# ... execute step ...
if step_span:
    step_span.set_attribute("tokens", token_usage.total)
    step_span.set_attribute("cost", token_usage.cost_estimate)
    step_span.end()
```

**FR-402 — ProjectContext on root span**

```python
if span_ctx and not project_context.is_empty():
    labels = project_context.to_labels()
    for key, value in labels.items():
        span_ctx.set_attribute(f"io.contextcore.{key}", value)
```

`ProjectContext.to_labels()` already exists (models.py line 51-62).

#### Implementation Order

1. FR-403 (graceful no-op) — prerequisite for all others
2. FR-400 (parent span) — depends on FR-403
3. FR-401 (child step spans) — depends on FR-400
4. FR-402 (ProjectContext labels) — depends on FR-400

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_otel.py` (new) | `test_no_op_without_otel`, `test_parent_span_created`, `test_parent_span_attributes`, `test_child_step_span`, `test_error_recorded_on_span`, `test_project_context_on_span` |

#### Acceptance Criteria

- [ ] No errors when `opentelemetry` not installed (graceful no-op)
- [ ] Zero performance overhead when OTel not installed
- [ ] Parent span: `workflow.{workflow_id}` with `workflow.id`, `workflow.name`, `workflow.version`
- [ ] Child span: `workflow.{id}.step.{name}` with `step.name`, `agent.name`, `agent.model`
- [ ] Token and cost metrics as span attributes on completion
- [ ] Error recorded on span if workflow fails
- [ ] ProjectContext labels attached to root span (`io.contextcore.*`)
- [ ] `pip install startd8[otel]` installs `opentelemetry-api`

---

### 3.3 Visualization (FR-420, FR-421, FR-530)

**Capability:** `startd8.workflow.observability.visualize`

Create `WorkflowVisualizer` for Mermaid diagram export of pipeline structure and execution results.

#### Files to Create

| File | Purpose |
|------|---------|
| `src/startd8/workflows/visualizer.py` | `WorkflowVisualizer` class with `to_mermaid()` methods |

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/cli.py` | Add `workflow visualize` command (FR-530) |

#### Implementation Details

**FR-420 — Structure visualization**

```python
class WorkflowVisualizer:
    @staticmethod
    def to_mermaid(pipeline_or_result) -> str:
        """Generate Mermaid flowchart from Pipeline or WorkflowResult."""
        if isinstance(pipeline_or_result, Pipeline):
            return WorkflowVisualizer._pipeline_to_mermaid(pipeline_or_result)
        elif isinstance(pipeline_or_result, WorkflowResult):
            return WorkflowVisualizer._result_to_mermaid(pipeline_or_result)

    @staticmethod
    def _pipeline_to_mermaid(pipeline: Pipeline) -> str:
        lines = ["graph TD"]
        prev_id = "start([Start])"
        lines.append(f"    {prev_id}")
        for i, step in enumerate(pipeline.steps):
            step_id = f"step{i}"
            if isinstance(step, PipelineStep):
                lines.append(f"    {step_id}[{step.name}]")
            elif isinstance(step, ConditionalStep):
                lines.append(f"    {step_id}{{{step.name}}}")  # Diamond
                lines.append(f"    {step_id}_if[{step.if_step.name}]")
                lines.append(f"    {step_id} -->|True| {step_id}_if")
                if step.else_step:
                    lines.append(f"    {step_id}_else[{step.else_step.name}]")
                    lines.append(f"    {step_id} -->|False| {step_id}_else")
            elif isinstance(step, ParallelStep):
                lines.append(f"    {step_id}_fork{{{{Fork}}}}")
                for j, sub in enumerate(step.steps):
                    lines.append(f"    {step_id}_p{j}[{sub.name}]")
                    lines.append(f"    {step_id}_fork --> {step_id}_p{j}")
                lines.append(f"    {step_id}_join{{{{Join}}}}")
                for j in range(len(step.steps)):
                    lines.append(f"    {step_id}_p{j} --> {step_id}_join")
            elif isinstance(step, WorkflowStep):
                lines.append(f"    subgraph {step_id}_sub[{step.name}]")
                lines.append(f"        {step_id}_wf[{step.workflow.metadata.name}]")
                lines.append(f"    end")
            lines.append(f"    {prev_id} --> {step_id}")
            prev_id = step_id
        lines.append(f"    {prev_id} --> finish([End])")
        return "\n".join(lines)
```

**FR-421 — Post-execution visualization**

```python
@staticmethod
def _result_to_mermaid(result: WorkflowResult) -> str:
    lines = ["graph TD"]
    for i, step in enumerate(result.steps):
        step_id = f"step{i}"
        # Color by status
        if step.success:
            style = ":::success"  # Green
        else:
            style = ":::failure"  # Red
        label = f"{step.step_name}<br/>{step.time_ms}ms"
        if step.error:
            label += f"<br/>ERROR: {step.error[:30]}"
        lines.append(f"    {step_id}[\"{label}\"]{style}")
        if i > 0:
            lines.append(f"    step{i-1} --> step{i}")
    # Add classDefs
    lines.append("    classDef success fill:#2ecc71,color:#fff")
    lines.append("    classDef failure fill:#e74c3c,color:#fff")
    return "\n".join(lines)
```

**FR-530 — CLI command**

```python
@workflow_app.command("visualize")
def workflow_visualize(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    format: str = typer.Option("mermaid", help="Output format: mermaid or ascii"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
):
    # Build pipeline from workflow metadata
    diagram = WorkflowVisualizer.to_mermaid(pipeline)
    if output:
        Path(output).write_text(diagram)
    else:
        console.print(diagram)
```

#### Implementation Order

1. FR-420 (structure visualization) — no dependencies (but benefits from Phase 2 step types)
2. FR-421 (post-execution visualization) — depends on FR-420
3. FR-530 (CLI command) — depends on FR-420

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_visualizer.py` (new) | `test_mermaid_sequential`, `test_mermaid_conditional_diamond`, `test_mermaid_parallel_fork_join`, `test_mermaid_workflow_subgraph`, `test_result_mermaid_success_colors`, `test_result_mermaid_failure_colors`, `test_result_mermaid_timing` |

#### Acceptance Criteria

- [ ] `WorkflowVisualizer.to_mermaid(pipeline)` returns valid Mermaid markdown
- [ ] Sequential steps shown as linear flow
- [ ] ConditionalSteps shown as diamond decision nodes
- [ ] ParallelSteps shown as fork/join
- [ ] WorkflowSteps shown as sub-graph
- [ ] Post-execution: steps colored green (success) or red (failed)
- [ ] Timing annotations on steps
- [ ] `startd8 workflow visualize <id>` outputs Mermaid diagram

---

## Phase 4: Enterprise

**Capabilities:** `http`
**FRs:** FR-520, FR-521, FR-522
**Benefits delivered:** `workflow.integration.webhook_triggers`

### 4.1 HTTP Server (FR-520, FR-521, FR-522)

**Capability:** `startd8.workflow.integration.http`

Create an HTTP server module for webhook-triggered workflow execution.

#### Files to Create

| File | Purpose |
|------|---------|
| `src/startd8/server/__init__.py` | Package init, exports `create_app` |
| `src/startd8/server/app.py` | ASGI app with workflow endpoints (FR-520) |
| `src/startd8/server/auth.py` | API key middleware (FR-521) |

#### Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/cli.py` | Add `startd8 serve` command (FR-522) |
| `pyproject.toml` | Add optional dependency: `server = ["starlette", "uvicorn"]` |

#### Implementation Details

**FR-520 — HTTP endpoints**

Using Starlette (lighter than FastAPI):

```python
# src/startd8/server/app.py
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

async def list_workflows(request):
    """GET /workflows — list all workflows."""
    WorkflowRegistry.discover()
    workflows = WorkflowRegistry.list_workflow_metadata()
    return JSONResponse([w.to_dict() for w in workflows])

async def run_workflow(request):
    """POST /workflows/{id}/run — trigger async execution."""
    workflow_id = request.path_params["id"]
    body = await request.json()
    run_id = str(uuid.uuid4())
    # Queue async execution
    asyncio.create_task(_execute_run(run_id, workflow_id, body))
    return JSONResponse({"run_id": run_id, "status": "queued"})

async def get_run_status(request):
    """GET /workflows/{id}/runs/{run_id} — poll status."""
    run_id = request.path_params["run_id"]
    result = _run_store.get(run_id)
    if result is None:
        return JSONResponse({"status": "running"})
    return JSONResponse(result.to_dict())

def create_app(api_key: Optional[str] = None) -> Starlette:
    routes = [
        Route("/workflows", list_workflows),
        Route("/workflows/{id}/run", run_workflow, methods=["POST"]),
        Route("/workflows/{id}/runs/{run_id}", get_run_status),
    ]
    middleware = []
    if api_key:
        middleware.append(Middleware(APIKeyMiddleware, api_key=api_key))
    return Starlette(routes=routes, middleware=middleware)
```

**FR-521 — API key authentication**

```python
# src/startd8/server/auth.py
class APIKeyMiddleware:
    def __init__(self, app, api_key: str):
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            # Allow GET /workflows without auth (read-only)
            if scope["method"] != "GET" or b"/run" in scope["path"]:
                key = headers.get(b"x-api-key", b"").decode()
                if key != self.api_key:
                    response = JSONResponse(
                        {"error": "Unauthorized"}, status_code=401
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
```

**FR-522 — CLI `serve` command**

```python
@app.command("serve")
def serve(
    port: int = typer.Option(8080, help="Server port"),
    api_key: Optional[str] = typer.Option(None, envvar="STARTD8_API_KEY", help="API key"),
):
    try:
        import uvicorn
        from startd8.server import create_app
    except ImportError:
        console.print("[red]Install server extras: pip install startd8[server][/red]")
        raise typer.Exit(1)

    app = create_app(api_key=api_key)
    console.print(f"Starting server on port {port}")
    console.print(f"  GET  http://localhost:{port}/workflows")
    console.print(f"  POST http://localhost:{port}/workflows/{{id}}/run")
    uvicorn.run(app, host="0.0.0.0", port=port)
```

#### Implementation Order

1. FR-520 (server module and endpoints) — no dependencies
2. FR-521 (API key auth middleware) — depends on FR-520
3. FR-522 (CLI serve command) — depends on FR-520

#### Tests

| Test File | Tests |
|-----------|-------|
| `tests/integration/test_server.py` (new) | `test_list_workflows_endpoint`, `test_run_workflow_returns_run_id`, `test_poll_run_status`, `test_api_key_required_for_mutation`, `test_api_key_rejected_invalid`, `test_get_workflows_without_auth` |

#### Acceptance Criteria

- [ ] `GET /workflows` lists all registered workflows
- [ ] `POST /workflows/{id}/run` triggers async execution, returns `run_id`
- [ ] `GET /workflows/{id}/runs/{run_id}` polls status
- [ ] `X-API-Key` header required for mutation endpoints
- [ ] API key configurable via `STARTD8_API_KEY` env var
- [ ] 401 on missing/invalid key
- [ ] `startd8 serve --port 8080` starts server
- [ ] Graceful error message when `starlette`/`uvicorn` not installed

#### Risks

| Risk | Mitigation |
|------|-----------|
| In-memory run store lost on restart | Document as known limitation; suggest SQLite for production |
| Concurrent run execution resource limits | Add configurable max concurrent runs |

---

## Summary: All 46 FRs Mapped

### Phase 1 (14 FRs)

| FR | Description | Capability |
|----|-------------|-----------|
| FR-110 | Type checking in validate_config() | auto_validate |
| FR-111 | JSON Schema validation | auto_validate |
| FR-112 | _custom_validate() hook | auto_validate |
| FR-200 | Partial match in find_by_capability | discovery.search |
| FR-201 | search_workflows() method | discovery.search |
| FR-210 | CLI --capability flag | discovery.search |
| FR-211 | CLI --tag flag | discovery.search |
| FR-212 | CLI --search flag | discovery.search |
| FR-500 | Testing module creation | testing.assertions |
| FR-501 | assert_workflow_success | testing.assertions |
| FR-502 | assert_step_called / assert_step_not_called | testing.assertions |
| FR-503 | assert_cost_below | testing.assertions |
| FR-504 | assert_steps_in_order | testing.assertions |
| FR-150 | Async audit of builtin workflows | async_audit |

### Phase 2 (17 FRs)

| FR | Description | Capability |
|----|-------------|-----------|
| FR-100 | RetryPolicy dataclass | retry |
| FR-101 | retry_policy parameter on run/arun | retry |
| FR-300 | Retry loop in Pipeline.arun() | retry |
| FR-301 | Error classification (is_retryable) | retry |
| FR-302 | Checkpoint/resume | retry |
| FR-310 | Pipeline step-type dispatch refactor | mixed_steps |
| FR-311 | ConditionalStep dataclass | conditional |
| FR-312 | Pipeline.add_conditional() | conditional |
| FR-320 | ParallelStep dataclass | parallel |
| FR-321 | Pipeline.add_parallel() | parallel |
| FR-322 | Parallel failure policy | parallel |
| FR-330 | WorkflowStep dataclass | compose |
| FR-331 | Pipeline.add_workflow() | compose |
| FR-332 | Sub-workflow metrics aggregation | compose |
| FR-410 | PIPELINE_STEP_RETRY event | retry |
| FR-411 | retry_count / total_retries metrics | retry |
| FR-511 | CLI --max-retries flag | retry |

### Phase 3 (12 FRs)

| FR | Description | Capability |
|----|-------------|-----------|
| FR-102 | DryRunResult dataclass | dry_run |
| FR-103 | dry_run parameter on run() | dry_run |
| FR-340 | Dry run interception | dry_run |
| FR-341 | Token/cost estimation | dry_run |
| FR-400 | Parent OTel span | otel |
| FR-401 | Child step spans | otel |
| FR-402 | ProjectContext on spans | otel |
| FR-403 | Graceful no-op | otel |
| FR-420 | Mermaid structure visualizer | visualize |
| FR-421 | Post-execution visualization | visualize |
| FR-510 | CLI --dry-run flag | dry_run |
| FR-530 | CLI workflow visualize command | visualize |

### Phase 4 (3 FRs)

| FR | Description | Capability |
|----|-------------|-----------|
| FR-520 | HTTP server module | http |
| FR-521 | API key authentication | http |
| FR-522 | CLI serve command | http |

---

## New Modules Summary

| Module | Phase | Files | Purpose |
|--------|-------|-------|---------|
| `startd8.testing` | 1 | `__init__.py`, `assertions.py` | Pytest assertion helpers |
| `startd8.workflows.visualizer` | 3 | `visualizer.py` | Mermaid diagram export |
| `startd8.server` | 4 | `__init__.py`, `app.py`, `auth.py` | HTTP workflow API |

## Optional Dependencies

| Extra | Package | Phase | pyproject.toml key |
|-------|---------|-------|--------------------|
| Validation | `jsonschema>=4.0` | 1 | `validate` |
| Observability | `opentelemetry-api>=1.0` | 3 | `otel` |
| Server | `starlette>=0.27`, `uvicorn>=0.23` | 4 | `server` |

## Changelog

- **1.0.0** (2026-01-29): Initial implementation plan covering 11 capabilities, 46 FRs, 4 phases.
