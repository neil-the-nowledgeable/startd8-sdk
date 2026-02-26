# Code Manifest Phase 6 Pipeline Integration: Call Graph Consumer Wiring

**Status:** Draft
**Date:** 2026-02-24
**Author:** Neil Yashinsky + agent:claude-code
**Parent:** [CODE_MANIFEST_PHASE6_REQUIREMENTS.md](CODE_MANIFEST_PHASE6_REQUIREMENTS.md) (Section 10: Pipeline Integration)
**Prerequisites:** Phase 6 core implementation (complete), Phase 4 pipeline integration (complete)
**Implements:** Wiring Phase 6 call graph data into 7 pipeline consumer surfaces

---

## 1. Objective

Phase 6 core (complete) added bytecode-derived call graphs, blast radius computation, dead code detection, and callers/callees queries to the manifest system. Phase 4 (complete) wired Phase 1–3 *structural* manifest data into 6 pipeline consumers.

This document specifies wiring Phase 6 *call graph* data into 7 downstream consumer surfaces. The call graph answers questions the structural manifest cannot:

| Question | Structural Manifest (Phase 1–3) | Call Graph (Phase 6) |
|----------|--------------------------------|---------------------|
| What functions exist in this file? | Yes | — |
| Who calls function F? | No | `callers_of(F)` |
| If I change F, what breaks? | No | `blast_radius(F)` |
| Is this function actually used? | No | `dead_candidates()` |
| What does function F call? | No | `callees_of(F)` |

Without this wiring, the call graph data is available only via CLI commands. This phase embeds it into the pipeline's decision-making at each relevant stage.

---

## 2. Integration Architecture

### 2.1 Data Flow

```
Phase 6 Core                 ManifestRegistry               7 Consumers
──────────────    enrich()   ──────────────────  query()    ──────────────
generate_file_    ────────►  Element.call_graph  ─────────► 1. IMPLEMENT prompt
manifest()                   .call_graph()                  2. REVIEW prompt
mode="bytecode"              .reverse_call_graph()          3. DESIGN prompt
                             .blast_radius()                4. Plan Ingestion
                             .dead_candidates()             5. INTEGRATE pre-merge
                             .callers_of()                  6. Preflight validators
                             .callees_of()                  7. Code Review skill
```

### 2.2 Available API

These methods already exist on `ManifestRegistry` (Phase 6 core):

| Method | Signature | Returns |
|--------|-----------|---------|
| `call_graph()` | `() → dict[str, set[str]]` | Full caller→callees adjacency list |
| `reverse_call_graph()` | `() → dict[str, set[str]]` | Callee→callers adjacency list |
| `blast_radius()` | `(fqn: str, max_depth: int = 10) → set[str]` | All transitive callers |
| `dead_candidates()` | `() → list[str]` | Public callables with zero inbound edges |
| `callers_of()` | `(fqn: str) → set[str]` | Direct 1-hop callers |
| `callees_of()` | `(fqn: str) → set[str]` | Direct 1-hop callees |

Per-element data is available on `Element.call_graph: CallGraphInfo | None`:

| Field | Type | Description |
|-------|------|-------------|
| `calls` | `list[CallEntry]` | Outbound calls with target, kind, receiver |
| `attribute_reads` | `list[str]` | Sorted unique `self.*` reads |
| `attribute_writes` | `list[str]` | Sorted unique `self.*` writes |
| `has_dynamic_dispatch` | `bool` | Uses `getattr`/`eval`/`exec` |
| `unresolved_calls` | `list[str]` | Targets that couldn't be resolved |

### 2.3 Prerequisites

Call graph data is only populated when manifests are generated with `mode="bytecode"`. Consumers must handle the case where:
1. No manifest exists for a file (Phase 4 graceful degradation applies)
2. Manifest exists but `call_graph` is `None` on elements (generated with `mode="static"`)
3. Manifest exists with call graph data (full functionality)

### 2.4 New Extensions Required

This phase requires modest additions to `ManifestRegistry` and `ManifestDiff` beyond the Phase 6 core API:

| New Method | Location | Description |
|-----------|----------|-------------|
| `callers_of_file()` | `ManifestRegistry` | All FQNs from other files that call into elements in the given file |
| `call_graph_summary()` | `ManifestRegistry` | Compact text summary of call relationships for a file (budget-aware) |
| `call_edge_diff()` | `ManifestDiff` | Call edges added/removed between two file manifests |

---

## 3. Integration Point 1 — Artisan IMPLEMENT Phase

**Current state:** `LLMChunkExecutor._build_prompt()` (`development.py`, ~line 578) builds the implementation prompt with domain constraints, project context, and file targets. Manifest structural context (Phase 4: IM-1 through IM-6) provides element summaries but no caller/callee relationships. The LLM generates code without knowing which existing functions depend on the target.

**Failure mode addressed:** Lesson Leg 13 #28 — generated code changes a function signature, breaking all callers. The LLM had no visibility into the caller contract.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-IM-1 | **Caller context injection.** When `ManifestRegistry` is available and the target element has callers, append a `## Callers` section to the implementation prompt listing each direct caller's FQN and the call signature it uses. | Gives the LLM explicit backward-compatibility constraints. If 5 functions call `parse_config(path: str)`, the LLM knows not to change the signature to `parse_config(config: dict)`. |
| CG-IM-2 | **Blast radius annotation.** For each target element, include the blast radius count: `"Changing this function affects {N} transitive callers."` Use `max_depth=3` to keep the count relevant (direct + near callers). | Quantitative impact signal helps the LLM prioritize backward compatibility proportional to usage. A function with 30 callers warrants more care than one with 2. |
| CG-IM-3 | **Callee context for new functions.** When generating a new function that must call existing functions, include the callees' signatures so the LLM generates correct call sites. Resolve via `callees_of()` on similar functions (heuristic: same class, same module). | Reduces incorrect API usage in generated code — the LLM sees the actual signature rather than guessing from the function name. |
| CG-IM-4 | **Budget constraint.** Call graph context per chunk must not exceed 2000 characters (configurable via `call_graph_context_budget` in artisan config YAML). Progressive truncation: full caller list → top-N by blast radius → count-only summary. | Shares the LLM context window with structural context (4000 chars), domain constraints, and retry feedback. Must not crowd existing context. |
| CG-IM-5 | **Post-generation caller compatibility check.** After code generation, re-parse the generated file in `bytecode` mode and verify that all callers' expected call patterns remain satisfiable. Log WARNING if a public element's signature changed while callers exist. | Catches backward-incompatible changes at generation time rather than at integration or test time. Complements Phase 4's IM-5 (post-generation ManifestDiff). |
| CG-IM-6 | **Graceful degradation.** When call graph data is unavailable (mode != "bytecode" or registry is None), skip all CG-IM requirements with no behavioral change. | Ensures IMPLEMENT works identically on projects without bytecode manifests. |

### Prompt Template

```
## Function Call Dependencies

### Callers of `{target_fqn}` ({blast_radius_count} transitive)
These functions call `{target_name}` — preserve their call contract:
- `{caller_1_fqn}` calls `{target_name}({arg_pattern})`
- `{caller_2_fqn}` calls `{target_name}({arg_pattern})`
{... truncated if over budget ...}

### Available Callees
Functions you can call from this context:
- `{callee_1_fqn}{signature}`
- `{callee_2_fqn}{signature}`
```

---

## 4. Integration Point 2 — Artisan REVIEW Phase

**Current state:** `ReviewPhaseHandler._build_review_prompt()` (`context_seed_handlers.py`, ~line 8162) builds the review prompt from 7 modular section builders. No cross-function impact analysis exists — the reviewer sees code quality in isolation.

**Failure mode addressed:** Reviewer approves a signature change without knowing it breaks 14 downstream callers.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-RV-1 | **Blast radius section in review prompt.** Add `_build_call_graph_section()` to the review prompt builder. For each modified element, include blast radius count and direct callers. | Reviewer can check: "This function changed its return type from `list` to `dict`. It has 8 callers. Did the generated code update all callers?" |
| CG-RV-2 | **Dead code flag.** If a generated function has zero callers in the call graph, include a note: `"This function has no known callers — verify it is intentionally public."` | Catches generated code that creates utility functions that nothing calls. Common in LLM code generation where the model creates helpers it never wires up. |
| CG-RV-3 | **Signature change + caller mismatch detection.** When Phase 4's IM-5 ManifestDiff detects a signature change and `callers_of()` returns non-empty, flag this to the reviewer as a high-priority item. | Combines two signals (structural diff + call graph) into a single actionable finding. This is the highest-value call graph integration for quality. |
| CG-RV-4 | **Budget constraint.** Call graph review context must not exceed 1500 characters per task. | Review prompts are already large (design doc, code, parameters). Call graph is supplementary. |
| CG-RV-5 | **Graceful degradation.** When call graph data is unavailable, `_build_call_graph_section()` returns an empty list (no section rendered). | Existing review behavior is unchanged. |

### Prompt Template

```
## Call Graph Impact

### Modified Functions with Callers
- `{fqn}` — {blast_radius} transitive callers, {direct_callers} direct
  Callers: {caller_1}, {caller_2}, ...
  ⚠ Signature changed: `{old_sig}` → `{new_sig}`

### Generated Functions with No Callers
- `{fqn}` — no known callers (dead code candidate)
```

---

## 5. Integration Point 3 — Artisan DESIGN Phase

**Current state:** `DesignPhaseHandler` (`context_seed_handlers.py`, ~line 2019) injects manifest structural context (element summaries, dependency graph, edit-mode hints) into design prompts via lines 2595–2630. The design LLM knows *what* exists but not *how things are connected*.

**Failure mode addressed:** Design document proposes changing a heavily-used internal API without noting the migration path for callers.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-DS-1 | **API impact summary in design context.** When manifest call graph data is available, extend `_manifest_context()` to include a "Call Relationships" subsection showing the top-N most-called functions in target files with their caller counts. | Gives the design LLM grounding in which functions are API-critical. A function called by 20 other functions should be modified carefully; a function called by none can be freely refactored. |
| CG-DS-2 | **Blast radius annotation for edit targets.** When `edit_mode_hint == "edit"` and the target element has callers, annotate the edit context with: `"This function has {N} callers. Consider backward-compatible changes."` | Design documents that propose surgical edits should account for the blast radius. This steers the LLM toward additive changes (new parameters with defaults) rather than breaking changes. |
| CG-DS-3 | **Cross-file call dependencies for multi-file features.** When a feature spans multiple files, include cross-file call edges between those files so the design LLM can reason about interface contracts. Use `callers_of_file()` for this. | Multi-file features often break at file boundaries. The design LLM needs to see which functions in file A call functions in file B to design compatible interfaces. |
| CG-DS-4 | **Budget constraint.** Call graph context must fit within the existing `manifest_context_budget` (default 4000 chars). Call graph data shares this budget with structural context — progressive truncation drops call graph before dropping element summaries. | Structural context (what exists) is more fundamental than call context (how it's connected). When budget is tight, keep structure, drop calls. |
| CG-DS-5 | **Graceful degradation.** When call graph data is unavailable, design prompts render identically to current behavior. | No change to design output quality on projects without bytecode manifests. |

---

## 6. Integration Point 4 — Plan Ingestion

**Current state:** `_heuristic_assess_complexity()` (`plan_ingestion_workflow.py`, ~line 657) scores complexity across 5 dimensions. Phase 4 (PI-1, PI-2) replaced heuristics with manifest-backed API surface scoring and dependency ordering. No function-level connectivity data is used.

**Failure mode addressed:** A feature is classified as "low complexity" because it touches few files, but it modifies a function with 40 transitive callers — the actual integration risk is high.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-PI-1 | **Blast radius as complexity dimension.** When call graph data is available, compute the maximum blast radius across all target FQNs referenced by a feature. Add this as a sixth complexity dimension (`call_graph_impact`) weighted equally with `integration_depth`. | A feature that modifies a function with 40 transitive callers has fundamentally higher integration risk than one that modifies an isolated helper. The complexity score should reflect this. |
| CG-PI-2 | **Feature blast radius annotation.** Annotate each `ParsedFeature` with `affected_callers: list[str]` containing the union of `callers_of(fqn)` for all target FQNs. This feeds downstream ordering and review prioritization. | Features with overlapping blast radii should not be implemented in parallel — their changes may conflict. The annotation enables the task scheduler to sequence them correctly. |
| CG-PI-3 | **High-blast-radius warning.** When a feature's maximum blast radius exceeds a configurable threshold (default: 20), emit a WARNING and annotate the feature with `high_impact: true`. | Alerts the pipeline operator that this feature carries outsized integration risk and may benefit from manual review or serialized execution. |
| CG-PI-4 | **Dead code feature detection.** When all target FQNs of a feature are in `dead_candidates()`, annotate the feature with `targets_dead_code: true` and log INFO. | Features that modify dead code may be low-priority or incorrectly targeted. This annotation helps operators triage. |
| CG-PI-5 | **Graceful degradation.** When call graph data is unavailable, all CG-PI requirements are skipped. Complexity scoring uses existing 5 dimensions. | Ensures plan ingestion works on projects without bytecode manifests. |

---

## 7. Integration Point 5 — Artisan INTEGRATE Phase

**Current state:** `IntegrationEngine._manifest_pre_merge_diff()` (`integration_engine.py`, ~line 96) performs pre-merge structural comparison (IN-1 through IN-3). Detects removed public elements and element count regression. No function-level call graph comparison is performed.

**Failure mode addressed:** A merge introduces a function whose signature changed, but the structural diff only sees "signature changed" without knowing whether any existing code actually calls this function. Noisy warnings for functions that are never called, silent pass-through for heavily-called functions.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-IN-1 | **Call-graph-aware breaking change severity.** Extend IN-2's breaking change detection: when a public element is removed or its signature changes, cross-reference against `callers_of(fqn)`. If callers exist, escalate to `severity=ERROR` (from WARNING). If no callers exist, keep at `severity=INFO`. | Focuses breaking-change alerts on changes that actually break callers. Eliminates false positives for unused functions, elevates true positives for heavily-used functions. |
| CG-IN-2 | **Call edge diff logging.** Extend `ManifestDiff` with `call_edge_diff()` that computes added/removed call edges between old and new file manifests. Log the diff at DEBUG level. | Provides fine-grained visibility into how generated code changes the call graph. Useful for post-mortem analysis when integration tests fail. |
| CG-IN-3 | **Cross-file caller notification.** When a modified function has callers in *other* files (cross-file callers via `callers_of(fqn)`), log INFO with the list of affected files. These files may need re-testing even though they weren't modified. | Enables targeted re-testing: instead of re-running the entire test suite after a merge, the pipeline can prioritize tests for files that call the modified functions. |
| CG-IN-4 | **Graceful degradation.** When call graph data is unavailable on either the old or new manifest, all CG-IN requirements are skipped. IN-1 through IN-3 continue to function as before. | Backward compatible with `mode="static"` manifests. |

---

## 8. Integration Point 6 — Preflight Validators

**Current state:** `CrossFileImportValidator` (`cross_file_imports.py`, ~line 29) detects circular imports and missing FQN references using `dependency_graph()`. Validation operates at the import level — it cannot detect functional connectivity issues.

**Failure mode addressed:** Generated code imports a module and calls a function that doesn't exist in that module (import succeeds, call fails at runtime).

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-PF-1 | **Call target existence validation.** For each generated file with call graph data, verify that all resolved `target_fqn` values exist in the registry via `fqn_exists()`. Flag missing targets as WARNING. | Catches generated code that calls functions that were removed, renamed, or never existed. Goes beyond import validation (import succeeds) to call-site validation (call would fail). |
| CG-PF-2 | **Circular call chain detection.** Detect cycles in the call graph (A calls B calls C calls A) that could indicate infinite recursion. Report as WARNING with the cycle path. | Distinct from circular imports — two files can import each other safely, but mutual function calls may indicate a logic error. Especially relevant for generated code where the LLM may create recursive patterns unintentionally. |
| CG-PF-3 | **Dynamic dispatch advisory.** When a generated function has `has_dynamic_dispatch = True`, emit an INFO-level advisory noting that static analysis is incomplete for this function. | Alerts reviewers that `getattr()`/`eval()` usage means the call graph is a lower bound — additional calls may occur at runtime. |
| CG-PF-4 | **New preflight rule: `CallGraphValidator`.** Create a new preflight rule class separate from `CrossFileImportValidator` to house CG-PF-1 through CG-PF-3. Register it in the preflight rule registry. | Separation of concerns: import validation and call graph validation are distinct analysis domains with different data requirements. |
| CG-PF-5 | **Graceful degradation.** `CallGraphValidator` checks `ctx.manifest_registry` and `element.call_graph` before accessing call graph data. When unavailable, the validator is a no-op. | Ensures preflight works on projects without bytecode manifests. |

---

## 9. Integration Point 7 — Code Review Skill

**Current state:** The `/code-review` skill analyzes code for brittleness, reliability, performance, and maintainability. It operates on raw source code without structural or call graph context.

**Failure mode addressed:** Code review misses that a "simple" function change has outsized impact because it's called by 30 other functions across 12 files.

### Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| CG-CR-1 | **Call graph context loading.** When reviewing code with a `ManifestRegistry` available, load call graph data for reviewed files. Pass `callers_of()` and `blast_radius()` data to the review prompt. | Transforms code review from syntax-level to architecture-level. The reviewer sees not just *what* the code does, but *how it's connected* to the rest of the system. |
| CG-CR-2 | **Impact-proportional review focus.** Annotate each reviewed function with its blast radius. Instruct the reviewer to apply more scrutiny to functions with higher blast radius. | Review effort should be proportional to impact. A function with 50 callers warrants deeper analysis than a private helper. |
| CG-CR-3 | **Dead code detection finding.** Report functions that appear in `dead_candidates()` as a review finding with category "maintainability". | Dead code increases maintenance burden and confuses future developers. The code review skill should flag it. |
| CG-CR-4 | **Unresolved call advisory.** When a function has unresolved calls (`call_graph.unresolved_calls` is non-empty), include an advisory that the function may have dependencies not captured by static analysis. | Prevents the reviewer from making incorrect assumptions about a function's dependency surface. |
| CG-CR-5 | **Graceful degradation.** When call graph data is unavailable, the code review skill operates identically to its current behavior. | No regression for projects without bytecode manifests. |

---

## 10. New ManifestRegistry and ManifestDiff Extensions

### 10.1 ManifestRegistry Additions

| Method | Signature | Description |
|--------|-----------|-------------|
| `callers_of_file` | `(relative_path: str) → dict[str, set[str]]` | Returns `{element_fqn: {caller_fqns}}` for all elements in the given file that have external callers. Filters to callers from *other* files only. |
| `call_graph_summary` | `(relative_path: str, budget: int = 2000) → str` | Compact LLM-readable summary of call relationships for a file. Format: `"function_name: called by N, calls M"` per element. Progressive truncation: full list → top-N by caller count → count-only. |
| `max_blast_radius` | `(fqns: list[str]) → tuple[str, int]` | Returns `(fqn_with_max_radius, radius_count)` across the given FQNs. Used by plan ingestion for complexity scoring. |
| `call_graph_cycles` | `(max_depth: int = 10) → list[list[str]]` | Detect cycles in the call graph. Returns list of cycle paths. Each path is `[fqn_a, fqn_b, ..., fqn_a]`. Bounded by `max_depth` to prevent pathological graphs. |

### 10.2 ManifestDiff Additions

| Property | Type | Description |
|----------|------|-------------|
| `removed_call_edges` | `list[CallEdge]` | Call edges present in the old manifest but absent in the new. |
| `added_call_edges` | `list[CallEdge]` | Call edges present in the new manifest but absent in the old. |
| `signature_changes_with_callers` | `list[tuple[str, str, str, set[str]]]` | `(fqn, old_sig, new_sig, callers)` — signature changes cross-referenced against call graph. Only populated when call graph data exists on both manifests. |

### 10.3 Element-Level Convenience

| Property | Location | Description |
|----------|----------|-------------|
| `Element.caller_count` | Computed from registry | Number of direct callers. Populated lazily when the element is accessed through the registry. Not serialized. |

---

## 11. Performance Budget

| ID | Metric | Budget | Rationale |
|----|--------|--------|-----------|
| PB-1 | `call_graph_summary()` for a single file | < 10ms | String formatting of cached call graph data. No I/O. |
| PB-2 | `callers_of_file()` | < 50ms | Reverse graph lookup + file filter. O(elements × avg_callers). |
| PB-3 | `max_blast_radius()` for 10 FQNs | < 200ms | 10 × BFS traversal with `max_depth=3`. Cached reverse graph. |
| PB-4 | `call_graph_cycles()` | < 500ms | DFS cycle detection on full call graph. Bounded by `max_depth=10`. |
| PB-5 | `ManifestDiff.call_edge_diff()` | < 20ms | Set difference on call edges. O(edges). |
| PB-6 | Per-task IMPLEMENT prompt overhead (CG-IM-1 through CG-IM-4) | < 50ms | Call graph query + string formatting. Must not regress prompt build time. |
| PB-7 | Per-task REVIEW prompt overhead (CG-RV-1 through CG-RV-4) | < 30ms | Simpler than IMPLEMENT (fewer queries). |
| PB-8 | Pipeline startup overhead (call graph cache population) | < 200ms | Call graph and reverse graph are lazy-computed on first access. Not at startup. |

---

## 12. Graceful Degradation

| ID | Requirement | Rationale |
|----|-------------|-----------|
| GD-1 | **Every integration point falls back when call graph data is absent.** If `element.call_graph` is `None` or the registry has no call graph data (manifests generated with `mode="static"`), each consumer skips call-graph-specific logic with no behavioral change. | Phase 4 graceful degradation (GD-1 through GD-5) applies at the manifest level. This extends it to the call graph level within manifests. |
| GD-2 | **Call graph degradation is independent of structural degradation.** A manifest with structural data but no call graph data (`mode="static"`) still provides Phase 4 benefits (element summaries, dependency graph, ManifestDiff). Only call-graph-specific features are skipped. | Prevents a missing bytecode layer from disabling all manifest features. The two layers degrade independently. |
| GD-3 | **Dynamic dispatch limitation acknowledged.** When a function has `has_dynamic_dispatch = True`, call graph consumers must note that the call list is a lower bound. Never assert "this function has exactly N callers" — always use "at least N known callers." | `getattr()` and `eval()` create call paths invisible to static analysis. Consumers must not over-promise completeness. |
| GD-4 | **Cross-file resolution gaps.** When `target_fqn` is `None` on a `CallEntry` (unresolved call), the entry is excluded from all call graph queries. The `unresolved_calls` list is available for diagnostic purposes only. | Unresolved calls (third-party libraries, dynamic targets) should not produce phantom edges in the call graph. |
| GD-5 | **All degradation logged at DEBUG.** When a consumer skips call graph logic due to data absence, log a single DEBUG message: `"Call graph data unavailable for {context}; skipping {feature_id}"`. | DEBUG (not INFO) to avoid log noise — call graph absence is expected on most projects today. Upgrade to INFO once `mode="bytecode"` becomes the default. |

---

## 13. Acceptance Criteria

### 13.1 Functional Criteria

| ID | Criterion | Integration Point | Validation |
|----|-----------|-------------------|------------|
| AC-1 | IMPLEMENT prompt contains a `## Function Call Dependencies` section listing callers when call graph data is present. | CG-IM-1 | Unit test: generate manifest with `mode="bytecode"` for a file with known callers. Assert prompt substring `"## Function Call Dependencies"` and caller FQNs. |
| AC-2 | IMPLEMENT prompt caller section respects the 2000-character budget. | CG-IM-4 | Unit test: file with 50+ callers. Assert section length ≤ 2000 characters and contains `"... and N more"` truncation. |
| AC-3 | Post-generation caller compatibility check logs WARNING when a function's signature changes while callers exist. | CG-IM-5 | Unit test: mock a generated file where `foo(x: int)` becomes `foo(x: str)` with 3 callers. Assert WARNING log. |
| AC-4 | REVIEW prompt contains a `## Call Graph Impact` section for modified elements. | CG-RV-1 | Unit test: assert section presence in review prompt when call graph data exists. |
| AC-5 | REVIEW prompt flags dead code candidates from `dead_candidates()`. | CG-RV-2 | Unit test: generated function with zero callers produces dead code advisory in review prompt. |
| AC-6 | DESIGN prompt includes caller counts for target elements when editing existing code. | CG-DS-1, CG-DS-2 | Unit test: manifest with call graph + `edit_mode_hint="edit"`. Assert caller count annotation in design context. |
| AC-7 | Plan ingestion complexity score includes `call_graph_impact` dimension when call graph data is available. | CG-PI-1 | Unit test: mock registry with known blast radii. Assert complexity score differs from baseline (no call graph). |
| AC-8 | Features with blast radius > 20 are annotated `high_impact: true`. | CG-PI-3 | Unit test: feature targeting a function with 25 callers. Assert `high_impact` annotation. |
| AC-9 | INTEGRATE phase escalates breaking change severity when callers exist. | CG-IN-1 | Unit test: ManifestDiff with removed public element + `callers_of()` returns 3 callers. Assert `severity=ERROR`. |
| AC-10 | INTEGRATE phase logs cross-file affected files for modified functions. | CG-IN-3 | Unit test: modified function with callers in other files. Assert INFO log listing affected file paths. |
| AC-11 | `CallGraphValidator` preflight rule flags missing call targets. | CG-PF-1 | Unit test: generated file calls `nonexistent.func()`. Assert WARNING from validator. |
| AC-12 | `CallGraphValidator` detects circular call chains. | CG-PF-2 | Unit test: A calls B, B calls A. Assert WARNING with cycle path. |
| AC-13 | Code review skill includes blast radius annotation per function. | CG-CR-1, CG-CR-2 | Unit test: review prompt for file with known callers includes blast radius counts. |
| AC-14 | **Full pipeline completes without call graph data.** Pipeline with `mode="static"` manifests produces identical behavior to pre-Phase-6-pipeline. | All GD-* | Integration test: run pipeline with and without call graph data, verify identical outputs (via mock instrumentation per Phase 4 AC-9 pattern). |

### 13.2 Performance Criteria

| ID | Criterion | Budget | Validation |
|----|-----------|--------|------------|
| AP-1 | `call_graph_summary()` | < 10ms | Benchmark test with largest project file. |
| AP-2 | `max_blast_radius()` for 10 FQNs | < 200ms | Benchmark test with full project call graph. |
| AP-3 | `call_graph_cycles()` | < 500ms | Benchmark test with full project. |
| AP-4 | IMPLEMENT prompt build regression | < 50ms added | Benchmark IMPLEMENT prompt build time with and without call graph. |
| AP-5 | Full pipeline startup regression | < 200ms added | End-to-end timing comparison. |

---

## 14. Configuration

New artisan config YAML fields:

```yaml
artisan:
  # Existing fields...

  # Phase 6 call graph integration
  call_graph_context_budget: 2000        # CG-IM-4: max chars for IMPLEMENT prompt
  call_graph_review_budget: 1500         # CG-RV-4: max chars for REVIEW prompt
  blast_radius_warning_threshold: 20     # CG-PI-3: high-impact annotation threshold
  blast_radius_max_depth: 3              # CG-IM-2: depth limit for blast radius count
  enable_call_graph_preflight: true      # CG-PF-4: enable/disable CallGraphValidator
```

All fields are optional with the defaults shown above. `manifest_consumption_enabled: false` (Phase 4 kill switch) also disables all call graph consumers.

---

## 15. Rollout Strategy

### Tier 1: Foundation (Prerequisites)

| Component | Description | Deps |
|-----------|-------------|------|
| `callers_of_file()` | New registry method for cross-file caller lookups | Phase 6 core |
| `call_graph_summary()` | Budget-aware text summary for LLM prompts | Phase 6 core |
| `max_blast_radius()` | Batch blast radius computation | Phase 6 core |
| `ManifestDiff.call_edge_diff()` | Call edge comparison | Phase 6 core + Phase 4 ManifestDiff |
| Configuration fields | YAML config for budgets and thresholds | — |
| Graceful degradation (GD-1 through GD-5) | All fallback paths | — |

### Tier 2: High-Value Consumers

| Component | Description | Deps | Priority |
|-----------|-------------|------|----------|
| IMPLEMENT caller context (CG-IM-1, CG-IM-2, CG-IM-4, CG-IM-6) | Backward-compatibility awareness | Tier 1 | **P0** — highest impact on code quality |
| INTEGRATE severity escalation (CG-IN-1) | Focused breaking-change alerts | Tier 1 | **P0** — catches breaks before test |
| REVIEW blast radius section (CG-RV-1, CG-RV-3, CG-RV-4, CG-RV-5) | Impact-scoped review | Tier 1 | **P1** — improves review quality |
| Plan ingestion blast radius (CG-PI-1, CG-PI-2, CG-PI-3) | Risk-aware task ordering | Tier 1 | **P1** — prevents parallel conflicts |

### Tier 3: Validation and Auxiliary

| Component | Description | Deps |
|-----------|-------------|------|
| Post-generation caller check (CG-IM-5) | Signature compatibility validation | Tier 2 |
| CallGraphValidator preflight (CG-PF-1 through CG-PF-5) | Call target and cycle validation | Tier 1 |
| DESIGN call graph context (CG-DS-1 through CG-DS-5) | API-aware design | Tier 1 |
| Code review skill integration (CG-CR-1 through CG-CR-5) | Architecture-level review | Tier 1 |
| Dead code detection (CG-RV-2, CG-PI-4, CG-CR-3) | Maintenance quality | Tier 1 |
| Cross-file caller notification (CG-IN-3) | Targeted re-testing | Tier 2 |
| Call edge diff logging (CG-IN-2) | Diagnostic visibility | Tier 1 |
| Callee context for new functions (CG-IM-3) | Correct API usage | Tier 2 |
| Cycle detection (CG-PF-2) | Recursion prevention | Tier 1 |

---

## 16. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | **LLM ignores caller context in IMPLEMENT prompts.** Call graph context adds tokens but the model may not use them to preserve backward compatibility. | Medium | Medium | CG-IM-4 budget constraint keeps overhead low. CG-IM-5 post-generation check catches failures regardless of whether the LLM used the context. A/B evaluation recommended before full Tier 2 rollout. |
| R2 | **Blast radius overcounting creates false urgency.** Transitive caller counts can be inflated by deep call chains (A→B→C→D→... all count as callers). | Medium | Low | CG-IM-2 limits depth to 3 hops. CG-PI-3 threshold (20) is tuned for direct + near callers, not deep transitive closure. |
| R3 | **Stale call graph data after INTEGRATE.** If manifests are regenerated with `mode="static"` instead of `mode="bytecode"` after integration, call graph data disappears for modified files while structural data refreshes. | Medium | Medium | IN-4 cache refresh must use the same mode as the original generation. Add a `manifest_mode` field to the context dict so refresh preserves the mode. |
| R4 | **Dynamic dispatch false negatives.** Functions using `getattr()` or plugins may have callers that the static call graph cannot see. `callers_of()` returns an incomplete set, leading to underestimated blast radius. | High | Medium | GD-3 requires consumers to use "at least N known callers" language. `has_dynamic_dispatch` flag alerts consumers when completeness is uncertain. |
| R5 | **Call graph cycle false positives.** Indirect recursion through callbacks or event handlers may appear as cycles but is intentional. | Medium | Low | CG-PF-2 reports cycles as WARNING (non-blocking). Operators can filter known-intentional cycles via the preflight allowlist mechanism. |
| R6 | **Mode proliferation confusion.** Users must remember to use `mode="bytecode"` to get call graph data, `mode="static"` for structural only. The mode is not visible in the manifest output. | Medium | Low | Add `analysis_mode` field to FileManifest metadata in a follow-up. For now, `schema_version="1.3.0"` indicates bytecode capability but not whether it was used. |
| R7 | **Budget pressure on IMPLEMENT prompts.** Adding 2000 chars of call graph context (CG-IM-4) on top of 4000 chars structural context (Phase 4 IM-3) and domain constraints may crowd the implementation prompt. | Medium | Medium | Progressive truncation drops call graph first (CG-DS-4 pattern). Monitor prompt sizes in pipeline telemetry. Consider reducing structural budget when call graph is present (shared budget mode). |

---

## 17. File Changes

| File | Change | Tier |
|------|--------|------|
| `src/startd8/utils/manifest_registry.py` | Add `callers_of_file()`, `call_graph_summary()`, `max_blast_radius()`, `call_graph_cycles()` | 1 |
| `src/startd8/utils/manifest_registry.py` | Extend `ManifestDiff` with `call_edge_diff()`, `removed_call_edges`, `added_call_edges`, `signature_changes_with_callers` | 1 |
| `src/startd8/contractors/artisan_phases/development.py` | Add call graph context to `_build_prompt()` (CG-IM-1 through CG-IM-4) | 2 |
| `src/startd8/contractors/artisan_phases/development.py` | Add post-generation caller compatibility check (CG-IM-5) | 3 |
| `src/startd8/contractors/context_seed_handlers.py` | Extend `DesignPhaseHandler._manifest_context()` with call graph (CG-DS-1 through CG-DS-3) | 3 |
| `src/startd8/contractors/context_seed_handlers.py` | Add `ReviewPhaseHandler._build_call_graph_section()` (CG-RV-1 through CG-RV-3) | 2 |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | Add `call_graph_impact` dimension to `_heuristic_assess_complexity()` (CG-PI-1 through CG-PI-4) | 2 |
| `src/startd8/contractors/integration_engine.py` | Extend `_manifest_pre_merge_diff()` with call-graph-aware severity (CG-IN-1, CG-IN-3) | 2 |
| `src/startd8/workflows/builtin/preflight_rules/call_graph_validator.py` | **New file**: `CallGraphValidator` preflight rule (CG-PF-1 through CG-PF-4) | 3 |
| `src/startd8/contractors/artisan_phases/design_prompts/seed_mapping.py` | Extend `extract_manifest_context()` with call graph data | 3 |
| `tests/unit/contractors/test_call_graph_pipeline.py` | **New file**: Integration tests for all 7 consumer surfaces | 2 |
| `tests/unit/test_call_graph_preflight.py` | **New file**: `CallGraphValidator` unit tests | 3 |

---

## Appendix: Iterative Review Log

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

*(Pending first review round)*

### Areas Needing Further Review

*(Pending first review round)*

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(Awaiting first review round)*
