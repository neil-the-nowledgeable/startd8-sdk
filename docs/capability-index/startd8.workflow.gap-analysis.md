# StartD8 Workflow Gap Analysis (Phase 2)

**Date**: 2026-01-29
**Input**: `startd8.workflow.benefits.yaml` v2.0.0
**Scope**: 10 gap benefits + 2 partial benefits

---

## Summary

| # | Benefit ID | Priority | Status | Effort | Key Finding |
|---|-----------|----------|--------|--------|-------------|
| 1 | `workflow.execution.retry_resilience` | high | gap | medium | No retry/backoff anywhere in execution path |
| 2 | `workflow.reusability.composition` | high | gap | medium | No WorkflowStep primitive; Pipeline accepts only agents |
| 3 | `workflow.authoring.validation_helpers` | medium | gap | small | WorkflowBase has basic input validation; needs JSON Schema and custom extension |
| 4 | `workflow.discovery.search_filter` | medium | **partial** | small | API exists (`find_workflows_by_capability`); CLI `--capability` flag missing |
| 5 | `workflow.execution.conditional_routing` | medium | gap | medium | Pipeline is strictly sequential; no branching primitive |
| 6 | `workflow.execution.dry_run` | medium | gap | medium | No dry_run flag; validate_config only checks schema, not execution path |
| 7 | `workflow.observability.otel_integration` | medium | gap | medium | EventBus events exist; no OTel span emission from workflows |
| 8 | `workflow.testing.workflow_assertions` | medium | gap | small | No startd8.testing module; assertions are ad-hoc in tests |
| 9 | `workflow.observability.visualization` | low | gap | medium | No graph export; step_results are flat list only |
| 10 | `workflow.integration.webhook_triggers` | low | gap | medium | No HTTP server mode; CLI and MCP only |
| 11 | `workflow.execution.async_native` | -- | partial | small | arun() in WorkflowBase; not all builtins implement _aexecute |
| 12 | `workflow.execution.parallel_agents` | -- | partial | medium | Pipeline.arun_parallel_agents() for comparison; no ParallelStep |

**Correction from Phase 1**: `workflow.discovery.search_filter` upgraded from gap to partial (API delivered, CLI missing).

---

## Gap 1: workflow.execution.retry_resilience

### Benefit Summary
- **Name**: Automatic Retry and Resilience
- **Value**: Workflow users can recover from transient failures automatically so workflows complete despite API hiccups
- **Primary Personas**: workflow_user, ai_agent
- **Priority**: high

### Current State
- `Pipeline.arun()` iterates steps sequentially with no error recovery (orchestration.py:170)
- `WorkflowBase.run()` catches validation errors but not execution errors (base.py:208-266)
- `WorkflowRegistry.run_workflow()` catches exceptions and returns `WorkflowResult.from_error()` (registry.py:388-400) -- fail-fast, no retry
- Individual builtin workflows have no retry logic
- httpx client in providers has no retry/backoff configuration

### Gap Description
No retry or resilience mechanism exists at any layer. A single 429 or 502 from an LLM API fails the entire workflow, discarding progress from completed steps.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] Add optional `retry_policy` parameter to `Workflow.run()` and `WorkflowBase._execute()`
- [ ] Define `RetryPolicy` dataclass (max_retries, backoff_base, backoff_max, retryable_errors)
- [ ] No new metadata fields needed (retry is runtime config, not workflow definition)

#### Registry/Discovery Layer
- [ ] `WorkflowRegistry.run_workflow()` should accept `retry_policy` kwarg
- [ ] No YAML schema changes needed

#### Execution Layer
- [x] `Pipeline.arun()` needs try/except per step with retry loop
- [x] Exponential backoff with jitter: `delay = min(base * 2^attempt + random(), max_delay)`
- [x] Checkpoint: record completed step indices so resume skips them
- [x] Classify errors: retryable (429, 500, 502, 503, 504, ConnectionError) vs fatal (400, 401, 403, validation)

#### Observability Layer
- [ ] Emit event on retry attempt (new EventType: PIPELINE_STEP_RETRY)
- [ ] StepResult.metadata should include retry_count
- [ ] WorkflowMetrics should include total_retries

#### Integration Layer
- [ ] CLI: `--max-retries N` flag for `startd8 workflow run`
- [ ] MCP: add retry_policy to execute_workflow input schema

### Dependencies
- **Workflows**: None -- applies to all workflows via Pipeline/WorkflowBase
- **Infrastructure**: httpx retry could be added at provider level too
- **External**: None

### Risks
- **Breaking Changes**: None if retry_policy is optional with sensible defaults
- **Performance**: Retry adds latency on failures but saves token cost of full re-runs
- **Adoption**: Transparent -- existing workflows benefit without code changes

### Effort Estimate
- **Size**: medium
- **Rationale**: Core retry loop is ~100 lines, but checkpoint/resume adds complexity. Provider-level retry is separate work.

---

## Gap 2: workflow.reusability.composition

### Benefit Summary
- **Name**: Workflow Composition
- **Value**: Workflow developers can compose workflows from other workflows so they build complex orchestrations from primitives
- **Primary Personas**: workflow_developer, sdk_architect
- **Priority**: high

### Current State
- `Pipeline.add_step()` accepts only `BaseAgent` instances (orchestration.py:89-115)
- `PipelineStep` has `agent: BaseAgent` field -- no workflow step type (orchestration.py:22-31)
- Builtin workflows are standalone; lead-contractor uses its own internal orchestration, not Pipeline
- No way to nest `workflow.run()` inside a Pipeline step

### Gap Description
Pipeline steps are agent-only. To compose workflows, developers must either: (a) copy logic between workflows, or (b) call `workflow.run()` manually inside `_execute()`. No standard primitive for workflow-as-step exists.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] No protocol changes -- composition is a Pipeline feature, not a protocol requirement
- [ ] WorkflowResult already has metrics/steps for aggregation

#### Registry/Discovery Layer
- [ ] No registry changes needed
- [ ] YAML: optional `composed_from` field in workflow metadata for documentation

#### Execution Layer
- [x] New `WorkflowStep` class wrapping a Workflow instance as a Pipeline step
- [x] `Pipeline.add_workflow(workflow, config_mapping)` method
- [x] Config mapping function: `Callable[[str], Dict[str, Any]]` -- transforms previous step output to sub-workflow config
- [x] WorkflowResult.output extracted as step output for next Pipeline step
- [x] Sub-workflow progress nested under parent progress

#### Observability Layer
- [x] Aggregate sub-workflow metrics into parent WorkflowMetrics
- [x] Flatten sub-workflow StepResults into parent with namespacing (e.g., "sub:step1")
- [ ] Events: emit PIPELINE_SUB_WORKFLOW_START / COMPLETE

#### Integration Layer
- [ ] No CLI changes needed (composition is code-level)
- [ ] MCP: no changes (users compose via Python, not MCP)

### Dependencies
- **Workflows**: None
- **Infrastructure**: Existing Pipeline class
- **External**: None

### Risks
- **Breaking Changes**: None -- additive (new class, new method)
- **Performance**: Nested workflows add overhead from double-validation and double-metrics
- **Adoption**: Low barrier -- optional feature, existing workflows unchanged

### Effort Estimate
- **Size**: medium
- **Rationale**: WorkflowStep adapter is ~50 lines, but metrics aggregation and progress nesting add complexity.

---

## Gap 3: workflow.authoring.validation_helpers

### Benefit Summary
- **Name**: Config Validation Helpers
- **Value**: Workflow developers can validate configs declaratively so they don't write repetitive validation code
- **Primary Personas**: workflow_developer
- **Priority**: medium

### Current State
- `WorkflowBase.validate_config()` already validates required inputs and agent counts from metadata (base.py:178-206)
- `WorkflowInput.to_json_schema()` generates JSON Schema per input (models.py:113-138)
- `WorkflowMetadata.get_input_schema()` generates full JSON Schema (models.py:167-181)
- Builtin workflows override `validate_config()` with additional manual checks
- No JSON Schema validation library integration (jsonschema not a dependency)

### Gap Description
The foundation exists but is incomplete. Basic required-field checking works. What's missing: (a) type validation against JSON Schema, (b) custom validators composable with auto-validation, (c) declarative validation beyond required/type.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] No protocol changes -- `validate_config()` signature is sufficient
- [ ] Add optional `validators` list to WorkflowInput for custom rules

#### Registry/Discovery Layer
- [ ] No changes

#### Execution Layer
- [x] `WorkflowBase.validate_config()` should validate types from `get_input_schema()`
- [x] Add `jsonschema` as optional dependency (or lightweight inline type checking)
- [x] Custom validator hook: `validate_config()` calls auto-validation then `_custom_validate()`
- [x] Validation error messages include field name, expected type, actual value

#### Observability Layer
- [ ] No changes

#### Integration Layer
- [ ] No changes

### Dependencies
- **Workflows**: None
- **Infrastructure**: Optional `jsonschema` package
- **External**: None

### Risks
- **Breaking Changes**: None -- extends existing method behavior
- **Performance**: Negligible
- **Adoption**: Transparent improvement for existing workflows

### Effort Estimate
- **Size**: small
- **Rationale**: WorkflowBase already does half the work. Adding type checking is ~50 lines. jsonschema integration adds optional depth.

---

## Gap 4: workflow.discovery.search_filter (UPGRADED: partial)

### Benefit Summary
- **Name**: Workflow Search and Filter
- **Value**: Workflow users can search workflows by capability or tag so they find the right one quickly
- **Primary Personas**: workflow_user, ai_agent
- **Priority**: medium

### Current State
- `WorkflowRegistry.find_workflows_by_capability(capability)` EXISTS (registry.py:449-471) -- case-insensitive exact match
- `WorkflowRegistry.find_workflows_by_tag(tag)` EXISTS (registry.py:474-491) -- case-insensitive exact match
- CLI `startd8 workflow list` shows all workflows -- no filter flags
- MCP `startd8_workflow` list action returns all workflows -- no filter parameter

### Gap Description
API-level filtering is delivered. The gap is CLI and MCP integration only. Also missing: partial/fuzzy matching and description search.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] No changes

#### Registry/Discovery Layer
- [ ] Add `search_workflows(query)` for description text search
- [ ] Add partial matching to `find_workflows_by_capability()` (e.g., "doc" matches "document-enhancement")

#### Execution Layer
- [ ] No changes

#### Observability Layer
- [ ] No changes

#### Integration Layer
- [x] CLI: `startd8 workflow list --capability code-review`
- [x] CLI: `startd8 workflow list --tag multi-agent`
- [x] CLI: `startd8 workflow list --search "document"`
- [ ] MCP: add `capability` and `search` parameters to list action

### Dependencies
- **Workflows**: None
- **Infrastructure**: Existing registry methods
- **External**: None

### Risks
- **Breaking Changes**: None -- additive
- **Performance**: Negligible
- **Adoption**: Immediate value for CLI users

### Effort Estimate
- **Size**: small
- **Rationale**: Registry API exists. CLI flags are ~30 lines. Partial matching is ~10 lines.

---

## Gap 5: workflow.execution.conditional_routing

### Benefit Summary
- **Name**: Conditional Workflow Routing
- **Value**: Workflow developers can branch execution based on intermediate results so workflows adapt to content
- **Primary Personas**: workflow_developer, sdk_architect
- **Priority**: medium

### Current State
- `Pipeline` is strictly sequential: `for i, step in enumerate(self.steps)` (orchestration.py:170)
- `PipelineStep` has no condition/predicate field
- Builtin workflows implement branching internally (e.g., lead-contractor checks review verdicts)
- No standard conditional primitive

### Gap Description
Pipeline only supports linear step chains. Conditional routing requires custom `_execute()` logic in each workflow. There's no `ConditionalStep` or `pipeline.add_conditional()` that evaluates a predicate on previous step output.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] No protocol changes
- [ ] New `ConditionalStep` dataclass

#### Registry/Discovery Layer
- [ ] No changes

#### Execution Layer
- [x] `ConditionalStep(predicate, if_step, else_step)` -- predicate receives previous output
- [x] `Pipeline.add_conditional(name, predicate, if_agent, else_agent)` method
- [x] Pipeline execution checks step type: PipelineStep vs ConditionalStep
- [x] Optional: `add_branch(name, router_fn, branches_dict)` for N-way routing
- [x] Async support: predicate can be sync (common case)

#### Observability Layer
- [ ] Events: emit which branch was taken
- [ ] StepResult.metadata includes `branch: "if"` or `branch: "else"`

#### Integration Layer
- [ ] No CLI/MCP changes (conditional routing is code-level)

### Dependencies
- **Workflows**: None
- **Infrastructure**: Pipeline class refactor from list iteration to step-type dispatch
- **External**: None

### Risks
- **Breaking Changes**: None if Pipeline iteration adds isinstance checks
- **Performance**: Negligible
- **Adoption**: Medium -- developers need to learn predicate pattern

### Effort Estimate
- **Size**: medium
- **Rationale**: ConditionalStep is simple, but Pipeline.arun() refactor to support mixed step types adds complexity.

---

## Gap 6: workflow.execution.dry_run

### Benefit Summary
- **Name**: Workflow Dry Run
- **Value**: Workflow users can simulate execution without API calls so they validate orchestration logic and cost estimates before committing tokens
- **Primary Personas**: workflow_developer, ai_agent
- **Priority**: medium

### Current State
- `validate_config()` checks config validity but not execution path
- No way to trace step order without executing
- Cost estimation requires knowing model pricing (CostTracker/PricingService exist)
- Pipeline steps are only visible via `pipeline.steps` list (names + agents)

### Gap Description
No simulation mode exists. Users must execute workflows with real API calls to verify orchestration logic. Cost estimation before execution is not available.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] Add optional `dry_run: bool = False` parameter to `Workflow.run()` / `WorkflowBase._execute()`
- [ ] Define `DryRunResult` with execution_plan, estimated_cost, step_order

#### Registry/Discovery Layer
- [ ] `WorkflowRegistry.run_workflow()` should pass `dry_run` through
- [ ] No YAML changes

#### Execution Layer
- [x] `WorkflowBase.run()` intercepts dry_run before calling `_execute()`
- [x] Builds execution plan from metadata: step count, agent assignments
- [x] Estimates tokens from input size * model-specific multiplier
- [x] Estimates cost from PricingService
- [x] Returns WorkflowResult with `metadata["dry_run"] = True` and plan in output

#### Observability Layer
- [ ] No events emitted during dry run
- [ ] Result marked clearly as simulated

#### Integration Layer
- [x] CLI: `startd8 workflow run <id> --dry-run`
- [x] MCP: `dry_run` parameter in execute_workflow

### Dependencies
- **Workflows**: Needs PricingService for cost estimation
- **Infrastructure**: Existing CostTracker
- **External**: None

### Risks
- **Breaking Changes**: None -- new optional parameter
- **Performance**: No API calls = fast
- **Adoption**: Low barrier; highly useful for agents

### Effort Estimate
- **Size**: medium
- **Rationale**: Base dry-run is simple (~80 lines), but accurate cost estimation per model requires PricingService integration and per-workflow input size estimation heuristics.

---

## Gap 7: workflow.observability.otel_integration

### Benefit Summary
- **Name**: OpenTelemetry Integration
- **Value**: Integration developers can export workflow telemetry to Grafana/Tempo so they use existing observability tools
- **Primary Personas**: integration_developer, sdk_architect
- **Priority**: medium

### Current State
- EventBus emits PIPELINE_* events (types.py:40-44) -- custom event system, not OTel
- ProjectContext has `to_labels()` for Prometheus/OTel (models.py:51-62)
- LeadContractorContextCoreWorkflow emits OTel spans via ContextCore SessionTracker
- SessionTracker has OpenTelemetry metrics integration (separate from workflow system)
- No OTel SpanProcessor or TracerProvider in workflow base classes

### Gap Description
Workflow events use a custom EventBus, not OpenTelemetry. ContextCore integration exists in one workflow (lead-contractor-contextcore) but is not generalized. Standard workflows don't emit OTel spans.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] No protocol changes -- OTel is infrastructure, not workflow API
- [ ] Optional `tracer` parameter on WorkflowBase for dependency injection

#### Registry/Discovery Layer
- [ ] No changes

#### Execution Layer
- [x] `WorkflowBase.run()` creates parent span: `workflow.{workflow_id}`
- [x] Each step creates child span: `workflow.{workflow_id}.step.{step_name}`
- [x] Span attributes: `workflow.id`, `workflow.name`, `step.name`, `agent.name`, `agent.model`
- [x] Span events for step start/complete/error
- [x] Optional: bridge EventBus events to OTel spans

#### Observability Layer
- [x] opentelemetry-api as optional dependency
- [x] Graceful no-op when OTel not installed
- [x] ProjectContext labels attached to root span
- [x] WorkflowMetrics (tokens, cost, time) as span attributes on completion

#### Integration Layer
- [ ] CLI: `--trace` flag to enable span export
- [ ] Documentation: Grafana/Tempo setup guide

### Dependencies
- **Workflows**: None -- applies to all via WorkflowBase
- **Infrastructure**: opentelemetry-api, opentelemetry-sdk (optional)
- **External**: Tempo or Jaeger for trace backend

### Risks
- **Breaking Changes**: None -- optional, no-op without OTel installed
- **Performance**: Minimal overhead (~1ms per span)
- **Adoption**: Requires OTel stack setup

### Effort Estimate
- **Size**: medium
- **Rationale**: Span creation is ~100 lines. The complexity is in graceful degradation (optional import), attribute mapping, and ensuring no-op when OTel absent.

---

## Gap 8: workflow.testing.workflow_assertions

### Benefit Summary
- **Name**: Workflow Test Assertions
- **Value**: Workflow developers can assert on workflow behavior so they catch regressions automatically
- **Primary Personas**: workflow_developer
- **Priority**: medium

### Current State
- Tests assert on WorkflowResult fields directly (e.g., `assert result.success`)
- No `startd8.testing` module exists
- MockAgent exists in `startd8.providers.mock` for response simulation
- No assertion helpers, no snapshot testing, no cost guards

### Gap Description
Workflow testing requires ad-hoc assertions. No purpose-built helpers for common patterns: success checks, step verification, cost bounds, output schema validation.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] No changes

#### Registry/Discovery Layer
- [ ] No changes

#### Execution Layer
- [ ] No changes

#### Observability Layer
- [ ] No changes

#### Integration Layer
- [x] New module: `startd8.testing` with assertion helpers
- [x] `assert_workflow_success(result)` -- raises AssertionError with step details on failure
- [x] `assert_step_called(result, step_name)` -- verify step executed
- [x] `assert_step_not_called(result, step_name)` -- verify step skipped (for conditionals)
- [x] `assert_cost_below(result, max_cost)` -- cost guard
- [x] `assert_steps_in_order(result, ["step1", "step2"])` -- execution order
- [x] `WorkflowTestCase` base class with MockAgent setup helpers

### Dependencies
- **Workflows**: None
- **Infrastructure**: pytest (already a dev dependency)
- **External**: None

### Risks
- **Breaking Changes**: None -- new module
- **Performance**: N/A (test-time only)
- **Adoption**: Low barrier -- import and use

### Effort Estimate
- **Size**: small
- **Rationale**: Pure utility functions, ~150 lines total. No infrastructure changes.

---

## Gap 9: workflow.observability.visualization

### Benefit Summary
- **Name**: Workflow Visualization
- **Value**: Workflow developers can see a visual representation of workflow execution graphs so they understand complex multi-step orchestrations at a glance
- **Primary Personas**: workflow_developer, workflow_user
- **Priority**: low

### Current State
- `Pipeline.steps` is a flat list of PipelineStep objects
- `WorkflowResult.steps` is a flat list of StepResult objects
- No graph/DAG structure; no export format
- CLI `startd8 workflow describe` shows text metadata only

### Gap Description
Workflows have no visual representation. Step order is implicit in list position. With conditional routing and composition (Gaps 5, 2), a visual DAG becomes more valuable.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] Optional `to_graph()` method on WorkflowBase returning step DAG

#### Registry/Discovery Layer
- [ ] No changes

#### Execution Layer
- [ ] No changes (visualization is read-only)

#### Observability Layer
- [x] `WorkflowVisualizer` class: accepts Pipeline or WorkflowResult
- [x] Export to Mermaid markdown (LR or TD direction)
- [x] Post-execution: color steps by status (green=success, red=failed, gray=skipped)
- [x] Include timing annotations on edges

#### Integration Layer
- [x] CLI: `startd8 workflow visualize <id>` outputs Mermaid
- [x] CLI: `startd8 workflow visualize --last-run` shows execution result
- [x] Option: `--format mermaid|dot|ascii`

### Dependencies
- **Workflows**: Benefits from Gap 5 (conditional routing) and Gap 2 (composition) for richer graphs
- **Infrastructure**: None (Mermaid is text-based)
- **External**: Mermaid renderer for visual display (optional)

### Risks
- **Breaking Changes**: None -- additive
- **Performance**: Negligible
- **Adoption**: Useful but not blocking any other work

### Effort Estimate
- **Size**: medium
- **Rationale**: Mermaid generation is ~100 lines, but post-execution visualization with timing and status requires result-graph correlation.

---

## Gap 10: workflow.integration.webhook_triggers

### Benefit Summary
- **Name**: Webhook Workflow Triggers
- **Value**: Integration developers can trigger workflows via HTTP so they connect to CI/CD and external systems
- **Primary Personas**: integration_developer
- **Priority**: low

### Current State
- Workflows invokable via: Python API, CLI, MCP tool
- No HTTP server mode
- No webhook endpoint
- No async execution with status polling

### Gap Description
Workflows cannot be triggered externally via HTTP. CI/CD pipelines (GitHub Actions, Jenkins) and external systems have no integration path besides CLI subprocess calls.

### Technical Requirements

#### Protocol/Interface Layer
- [ ] No changes

#### Registry/Discovery Layer
- [ ] No changes

#### Execution Layer
- [x] Async execution queue: submit workflow, get run_id, poll for result
- [x] Run state storage: in-memory dict or SQLite for persistence

#### Observability Layer
- [ ] HTTP request logging
- [ ] Run status events

#### Integration Layer
- [x] New module: `startd8.server` with FastAPI/Starlette app
- [x] `POST /workflows/{id}/run` -- trigger execution, return run_id
- [x] `GET /workflows/{id}/runs/{run_id}` -- poll status/result
- [x] `GET /workflows` -- list workflows (mirrors registry)
- [x] Authentication: API key header (`X-API-Key`)
- [x] CLI: `startd8 serve --port 8080 --api-key <key>`

### Dependencies
- **Workflows**: None
- **Infrastructure**: ASGI framework (uvicorn + starlette or FastAPI)
- **External**: New dependency: fastapi or starlette + uvicorn

### Risks
- **Breaking Changes**: None -- new module
- **Performance**: Server mode is separate from CLI usage
- **Adoption**: Requires deploying a process; more ops overhead

### Effort Estimate
- **Size**: medium
- **Rationale**: Basic HTTP server is ~200 lines with FastAPI. Async execution queue and authentication add complexity.

---

## Partial 11: workflow.execution.async_native

### Benefit Summary
- **Name**: Native Async Execution
- **Status**: partial
- **Remaining Gap**: Not all builtin workflows implement `_aexecute()`

### Current State
- `WorkflowBase` has full async support: `arun()` wraps `_aexecute()` or falls back to `_execute()` in executor (base.py:268-313)
- `AsyncWorkflow` protocol defined (base.py:125-156)
- `Pipeline.arun()` fully async (orchestration.py:117)
- `WorkflowRegistry.arun_workflow()` exists (registry.py:403-446)
- Builtin workflows implementing async: Pipeline (via Pipeline.arun)
- Builtin workflows NOT implementing _aexecute: most use `_execute()` only

### Remaining Work
- [ ] Audit all 9 builtin workflows for async support
- [ ] Add `_aexecute()` to workflows that call `agent.agenerate()` or `agent.acreate_response()`
- [ ] Low priority: WorkflowBase auto-wrapping handles the gap transparently

### Effort Estimate
- **Size**: small
- **Rationale**: WorkflowBase's executor fallback means this "just works." Native async would improve performance in event loops but isn't blocking.

---

## Partial 12: workflow.execution.parallel_agents

### Benefit Summary
- **Name**: Parallel Agent Execution
- **Status**: partial
- **Remaining Gap**: No ParallelStep pipeline primitive; arun_parallel_agents is comparison-only

### Current State
- `Pipeline.arun_parallel_agents(initial_input, agents)` runs same input to multiple agents concurrently (orchestration.py:374-390)
- Returns `List[tuple[str, int, TokenUsage]]` -- designed for comparison, not orchestration
- No `ParallelStep` in Pipeline that runs different inputs to different agents
- PolicyAnalysisWorkflow implements internal parallel execution (7 criteria analyzed concurrently)

### Remaining Work
- [x] `ParallelStep(steps: List[PipelineStep])` -- run multiple steps concurrently
- [x] `Pipeline.add_parallel(name, steps)` method
- [x] Result aggregation: list of step outputs, or custom aggregator function
- [x] Failure policy: fail-fast vs collect-all
- [ ] Progress: report parallel step completions

### Effort Estimate
- **Size**: medium
- **Rationale**: `asyncio.gather()` is straightforward, but result aggregation, failure policies, and progress reporting for concurrent steps add complexity.

---

## Cross-Cutting Dependencies

```
                    ┌──────────────────────┐
                    │  Gap 7: OTel Integ.  │
                    └──────────┬───────────┘
                               │ spans for all gaps
                               ▼
┌───────────┐    ┌──────────────────────────┐    ┌───────────┐
│ Gap 2:    │───▶│  Pipeline refactor for   │◀───│ Gap 5:    │
│ Composit. │    │  mixed step types        │    │ Cond.Rout.│
└───────────┘    └──────────────────────────┘    └───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Partial 12: Parallel │
                    └──────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Gap 9: Visualization │
                    │ (richer with all     │
                    │  step types)         │
                    └──────────────────────┘
```

**Implementation order recommendation**:
1. **Foundation**: Gap 3 (validation helpers), Gap 4 (search CLI), Gap 8 (test assertions) -- small, no dependencies
2. **Core orchestration**: Gap 1 (retry), Gap 5 (conditional), Partial 12 (parallel), Gap 2 (composition) -- Pipeline refactor batch
3. **Observability**: Gap 7 (OTel), Gap 6 (dry-run), Gap 9 (visualization) -- benefits from core changes
4. **Enterprise**: Gap 10 (webhooks) -- standalone, low priority

---

*Phase 2 complete. Proceed to Phase 3 (Functional Requirements) when ready.*
