# The Prime Contractor Paradigm for Iterative Development

## Purpose

This document describes the **Prime Contractor paradigm** — a domain-independent methodology for decomposing complex technical deliverables into tractable units, classifying them by difficulty, routing them to cost-appropriate execution backends, producing artifacts iteratively, and verifying quality at every step.

The paradigm was extracted from the StartD8 SDK's `PrimeContractorWorkflow`, which orchestrates multi-feature code generation. But the core loop — **decompose, classify, route, generate, verify** — contains no code-generation assumptions. This document specifies how to instantiate the paradigm for any technical domain: document authoring, data pipeline construction, infrastructure provisioning, test suite design, configuration management, or any batch workflow where work items vary in complexity and should be routed to different execution backends accordingly.

---

## 1. The Core Loop

Every Prime Contractor variant implements the same five-stage loop, executed per work item in dependency order:

```
┌─────────────┐
│  DECOMPOSE   │  Plan → discrete work items with dependencies
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  CLASSIFY    │  Extract signals → assign complexity tier
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   ROUTE      │  Tier → execution backend (template / economy / standard / premium)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  GENERATE    │  Backend produces artifact(s)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   VERIFY     │  Quality gate: pass → next item, fail → retry or escalate
└──────┴──────┘
```

Work items are processed **serially in dependency order**. Each item completes the full loop before the next begins. This prevents cascade failures from partial state and ensures later items can reference completed earlier items.

---

## 2. Stage Specifications

### 2.1 DECOMPOSE — Plan Intake and Task Decomposition

**Input:** A plan document (structured or free-form) describing the overall deliverable.

**Output:** An ordered queue of work items, each with:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier |
| `name` | string | Human-readable label |
| `description` | string | What this item must produce |
| `dependencies` | list[string] | IDs of items that must complete first |
| `target_artifacts` | list[string] | Paths or identifiers of artifacts to produce |
| `estimated_effort` | int/float | Domain-specific effort estimate (LOC, word count, resource count) |
| `metadata` | dict | Domain-specific annotations |
| `status` | enum | Lifecycle state (see 2.1.2) |

#### 2.1.1 Decomposition Requirements

| ID | Requirement |
|----|-------------|
| DC-001 | The decomposer SHALL accept both structured (JSON/YAML) and unstructured (Markdown) plan inputs. |
| DC-002 | Each work item SHALL be independently completable — no implicit coupling between items beyond declared `dependencies`. |
| DC-003 | The decomposer SHALL produce a dependency DAG. Circular dependencies SHALL be detected and rejected at intake. |
| DC-004 | Items targeting multiple artifacts MAY be auto-decomposed into sequential single-artifact sub-items, where each sub-item can reference artifacts produced by earlier sub-items. |
| DC-005 | The decomposer SHALL estimate effort per item using domain-specific heuristics or metadata when available, falling back to description-length heuristics when not. |
| DC-006 | The decomposer SHOULD support two intake paths: LLM-assisted (for unstructured plans) and deterministic (for structured plans or as fallback when LLM calls fail). |

#### 2.1.2 Work Item State Machine

```
PENDING → DEVELOPING → GENERATED → INTEGRATING → CHECKPOINT → COMPLETE
                                                              → FAILED → BLOCKED
```

| State | Meaning |
|-------|---------|
| PENDING | Awaiting execution; dependencies may or may not be satisfied |
| DEVELOPING | Currently being processed by the generate stage |
| GENERATED | Artifact(s) produced, awaiting verification/integration |
| INTEGRATING | Artifact(s) being merged into the target environment |
| CHECKPOINT | Verification in progress |
| COMPLETE | Fully verified and integrated |
| FAILED | Generation or verification failed; eligible for retry |
| BLOCKED | A dependency failed; cannot proceed until unblocked |

| ID | Requirement |
|----|-------------|
| DC-010 | Failed items SHALL cascade blocks to all transitive dependents. |
| DC-011 | The queue SHALL persist state to disk on every status transition, enabling crash recovery. |
| DC-012 | On resume, items in DEVELOPING or INTEGRATING state SHALL be reset to their prior stable state (PENDING or GENERATED respectively). |

#### 2.1.3 Dependency-Aware Scheduling

| ID | Requirement |
|----|-------------|
| DC-020 | `get_next_item()` SHALL only return items whose dependencies are ALL in COMPLETE status. |
| DC-021 | The scheduler SHOULD support wave/lane assignment for potential parallel execution of independent items. |
| DC-022 | When an item is retried, previously generated artifacts that still exist and pass staleness checks SHOULD be reused rather than regenerated (Mottainai principle — waste nothing). |

---

### 2.2 CLASSIFY — Signal Extraction and Tier Assignment

**Input:** A work item + project/environment state.

**Output:** A `(tier, reasoning)` tuple.

#### 2.2.1 Complexity Tiers

Four tiers, ordered by expected cost and capability:

| Tier | Intent | Typical Backend |
|------|--------|----------------|
| **TRIVIAL** | Matches a known template; no LLM needed | Template engine, deterministic generator |
| **SIMPLE** | Straightforward; economy backend sufficient | Economy LLM, local model, rule-based generator |
| **MODERATE** | Standard difficulty; default tier | Standard LLM, full pipeline |
| **COMPLEX** | High difficulty; requires premium backend | Premium LLM, multi-pass with expert review |

| ID | Requirement |
|----|-------------|
| CL-001 | Classification SHALL be a pure function: stateless, deterministic, no side effects beyond logging. |
| CL-002 | The classifier SHALL use a prioritized evaluation order: COMPLEX triggers (any single trigger fires) → SIMPLE eligibility (all conditions must pass) → MODERATE default. |
| CL-003 | When no signals are available, classification SHALL default to MODERATE (the safe middle). |
| CL-004 | Classification SHALL return a human-readable reason string listing which triggers or conditions determined the tier. |
| CL-005 | All classification thresholds SHALL be externalized into a configuration object, not hardcoded. |

#### 2.2.2 Signal Extraction

Signals are the raw measurements that feed the classifier. They are domain-specific, but the extraction pattern is universal.

| ID | Requirement |
|----|-------------|
| CL-010 | Signal extraction SHALL be separated from classification. Different subsystems or domains can contribute their own signal extractors while sharing the same classifier. |
| CL-011 | Signal extraction SHALL never raise exceptions. All lookups SHALL be wrapped in try/except with safe defaults. A failed extraction degrades to MODERATE, never crashes the pipeline. |
| CL-012 | Signals SHALL be represented as a frozen (immutable) dataclass with all fields having safe defaults. |
| CL-013 | The signal dataclass SHALL include a `to_dict()` method for serialization and forensic logging. |

#### 2.2.3 Domain Signal Adaptation

Each domain defines its own signal vocabulary. The classification algorithm structure (COMPLEX triggers → SIMPLE eligibility → MODERATE default) remains identical — only the signal field names and threshold values change.

**Reference signal mapping across domains:**

| Abstract Signal | Code Generation | Document Authoring | Data Pipelines | Infrastructure |
|----------------|----------------|-------------------|---------------|---------------|
| impact_radius | blast_radius (files importing target) | cross_reference_count | downstream_consumer_count | dependent_service_count |
| dependency_count | caller_count | citation_count | upstream_source_count | prerequisite_resource_count |
| has_dynamic_behavior | has_dynamic_dispatch | requires_dynamic_content | has_runtime_branching | has_conditional_provisioning |
| estimated_effort | estimated_loc | estimated_word_count | estimated_row_count | estimated_resource_count |
| target_count | target_file_count | target_section_count | target_table_count | target_resource_count |
| modification_mode | edit_mode (create/edit) | create_vs_revise | create_vs_migrate | create_vs_modify |
| hierarchy_depth | mro_depth | heading_nesting_depth | pipeline_stage_depth | dependency_chain_depth |
| schema_coverage | manifest_coverage | outline_coverage | catalog_coverage | state_file_coverage |
| has_cross_target_edges | cross_file_imports | cross_section_references | cross_table_joins | cross_resource_dependencies |

| ID | Requirement |
|----|-------------|
| CL-020 | A domain adaptation SHALL define: (a) a signal dataclass with domain-specific fields, (b) an extraction function mapping domain artifacts to signal values, and (c) threshold overrides for the shared classifier. |
| CL-021 | The shared classifier SHALL accept signals via a generic interface (dict or dataclass), not assume any specific domain's field names. |

---

### 2.3 ROUTE — Tier-to-Backend Mapping

**Input:** A complexity tier.

**Output:** An execution backend (generator, agent, template engine, etc.).

#### 2.3.1 Router Requirements

| ID | Requirement |
|----|-------------|
| RT-001 | The router SHALL map each tier to an optional backend. Unmapped tiers SHALL fall back to MODERATE's backend. |
| RT-002 | The router SHALL support both generator objects (for direct invocation) and agent spec strings (for deferred resolution). |
| RT-003 | Routing SHALL happen per work item, not per batch. A single batch MAY contain items routed to different backends. |
| RT-004 | The router SHALL be reconfigurable without restarting the workflow (e.g., via `enable_complexity_routing(config)`). |
| RT-005 | When routing is disabled, all items SHALL use the default (MODERATE) backend. Classification MAY still run for metadata/forensics. |

#### 2.3.2 Cost Optimization Hierarchy

The four-tier model implements a cost-quality tradeoff:

```
TRIVIAL   →  $0      (template, deterministic, instant)
SIMPLE    →  $       (economy model, fast, sufficient for straightforward items)
MODERATE  →  $$      (standard model, reliable, default)
COMPLEX   →  $$$     (premium model, thorough, for genuinely hard items)
```

| ID | Requirement |
|----|-------------|
| RT-010 | The workflow SHALL track cumulative cost across all items and enforce a configurable budget ceiling. |
| RT-011 | Cost per item SHALL be recorded in the item's metadata for post-run analysis. |
| RT-012 | The workflow SHOULD log tier distribution at run completion (e.g., "12 SIMPLE, 5 MODERATE, 2 COMPLEX"). |

---

### 2.4 GENERATE — Artifact Production

**Input:** Work item description + resolved context + selected backend.

**Output:** A `GenerationResult` containing produced artifacts, cost, and metadata.

#### 2.4.1 Generator Protocol

Every execution backend implements a common protocol:

```
generate(task: str, context: dict, target_artifacts: list[str]) → GenerationResult
```

Where `GenerationResult` contains:

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether generation succeeded |
| `produced_artifacts` | list[str] | Paths or identifiers of produced artifacts |
| `cost` | float | Cost in dollars (or domain-appropriate unit) |
| `input_tokens` | int | Tokens consumed (if LLM-backed) |
| `output_tokens` | int | Tokens produced (if LLM-backed) |
| `metadata` | dict | Backend-specific metadata |

| ID | Requirement |
|----|-------------|
| GN-001 | All backends SHALL implement the same generator protocol, making them interchangeable from the orchestrator's perspective. |
| GN-002 | The TRIVIAL backend SHALL be a deterministic template registry that produces artifacts without LLM calls. |
| GN-003 | The SIMPLE backend SHOULD use a generate-repair-verify inner loop: generate with an economy model, run a domain-specific repair pipeline, then structurally verify. |
| GN-004 | When a backend fails, the system SHOULD escalate to the next tier rather than immediately failing the item. |
| GN-005 | When a backend cannot match all target artifacts, it SHALL report which artifacts were produced and which were missed. |

#### 2.4.2 Context Resolution

The generator receives a `context` dict assembled by a pluggable context resolution strategy. This separates *what context the generator needs* from *how that context is gathered*.

| ID | Requirement |
|----|-------------|
| GN-010 | Context resolution SHALL support at least two modes: **standalone** (minimal context, works independently) and **pipeline** (rich context from upstream phases). |
| GN-011 | The strategy SHALL be selected via a factory function or constructor parameter, not hardcoded in the orchestrator. |
| GN-012 | Pipeline context SHOULD include: prior item results, domain constraints, architectural guidance, and error feedback from prior failed attempts. |
| GN-013 | When a prior attempt failed, the error message SHALL be injected into context so the generator can address the specific failure rather than blindly retrying. |

#### 2.4.3 Template Registry (TRIVIAL Tier)

| ID | Requirement |
|----|-------------|
| GN-020 | The template registry SHALL provide `is_trivial(item) → bool` to test if an item matches a known template. |
| GN-021 | Templates SHALL be deterministic: same input always produces same output. |
| GN-022 | The registry SHALL be extensible — domains register their own templates without modifying the core framework. |

#### 2.4.4 Repair Pipeline (SIMPLE Tier)

| ID | Requirement |
|----|-------------|
| GN-030 | The repair pipeline SHALL be a chain of non-destructive transformation steps, each fixing a known failure mode of the economy backend. |
| GN-031 | Each repair step SHALL be idempotent: applying it twice produces the same result as applying it once. |
| GN-032 | The pipeline SHALL track which steps made changes and report them for forensic logging. |

---

### 2.5 VERIFY — Quality Gates and Integration

**Input:** Produced artifact(s) + target environment state.

**Output:** Pass/fail verdict with diagnostic details.

#### 2.5.1 Verification Pipeline

Verification is a multi-step pipeline applied after each item's artifacts are produced:

```
pre-validate → merge/integrate → checkpoint → pass/rollback
```

| ID | Requirement |
|----|-------------|
| VF-001 | Pre-validation SHALL check artifacts in isolation before they touch the target environment (syntax, format, structural correctness). |
| VF-002 | Integration SHALL use a snapshot-merge-checkpoint-rollback pattern: snapshot current state, apply changes, run quality checks, rollback on failure. |
| VF-003 | Rollback SHALL restore the target environment to exactly its pre-integration state. |
| VF-004 | Each checkpoint type SHALL return a status of PASSED, FAILED, WARNING, or SKIPPED. |
| VF-005 | WARNING status SHALL be treated as passing (continue) but logged for human review. |

#### 2.5.2 Checkpoint Types

Each domain defines its own checkpoint types. The checkpoint framework is universal:

| ID | Requirement |
|----|-------------|
| VF-010 | Checkpoints SHALL be pluggable — domains register their own checkpoint types. |
| VF-011 | Checkpoints SHALL run with configurable timeouts to prevent hanging. |
| VF-012 | The system SHALL support a **regression baseline**: capture current quality indicators before the batch begins, then verify each item does not degrade them. |
| VF-013 | Checkpoint results SHALL include actionable diagnostic messages — not just "failed" but *what failed and why*. |

**Reference checkpoint mapping across domains:**

| Abstract Checkpoint | Code Generation | Document Authoring | Data Pipelines | Infrastructure |
|--------------------|----------------|-------------------|---------------|---------------|
| Syntax check | `py_compile` | Markdown/HTML parse | Schema validation | HCL/YAML parse |
| Import check | `python -c "import X"` | Cross-reference resolution | Source connectivity | Resource dependency resolution |
| Lint check | `ruff check` | Style/readability check | Data quality rules | Policy compliance |
| Regression test | `pytest` | Reading-level / link validation | Data integrity tests | Smoke tests |

#### 2.5.3 Domain Preflight Rules

Before generation, domain-specific rules can enrich each work item with constraints and validators.

| ID | Requirement |
|----|-------------|
| VF-020 | The preflight system SHALL classify each work item into a domain (e.g., Python module, YAML config, SQL migration). |
| VF-021 | Rules SHALL be registered in a priority-sorted registry and filtered by domain. |
| VF-022 | Each rule contributes: environment checks, prompt constraints (strings injected into the generator's context), and post-generation validators. |
| VF-023 | The rule registry SHALL support third-party rule discovery via entry points or plugin registration. |

#### 2.5.4 Retry and Escalation

| ID | Requirement |
|----|-------------|
| VF-030 | Failed items SHALL be eligible for retry up to a configurable `max_retries` limit. |
| VF-031 | On retry, the error from the previous attempt SHALL be included in the generator's context (error-informed retry). |
| VF-032 | If an item has previously generated artifacts that still exist and pass staleness checks, retry SHALL skip generation and proceed directly to integration (Mottainai reuse). |
| VF-033 | When retries are exhausted, the item SHALL transition to FAILED and block its dependents. |

---

## 3. Orchestrator Requirements

The orchestrator is the central loop that processes items from the queue through all five stages.

### 3.1 Execution Model

| ID | Requirement |
|----|-------------|
| OR-001 | The orchestrator SHALL process items in dependency order, one at a time, completing the full loop before advancing to the next item. |
| OR-002 | The orchestrator SHALL support a `dry_run` mode that simulates execution without making LLM calls or modifying the target environment. |
| OR-003 | The orchestrator SHALL support a `walkthrough` mode that persists the prompts/context that *would* be sent to generators, for human review before committing to LLM costs. |
| OR-004 | The orchestrator SHALL enforce configurable limits: `max_items`, `max_cost`, `max_retries_per_item`. |
| OR-005 | The orchestrator SHALL track and report: items processed, succeeded, failed, total cost, total tokens, and elapsed time. |

### 3.2 Context Lifecycle

| ID | Requirement |
|----|-------------|
| OR-010 | Workflow context SHALL be mutable during setup and frozen at execution start. No context reconfiguration during the main loop. |
| OR-011 | The freeze boundary SHALL be enforced programmatically (e.g., `__setattr__` guard after `freeze()`). |
| OR-012 | Context SHALL support two execution modes via the Strategy pattern: standalone (minimal context, works independently) and pipeline (rich context from an upstream intake process). |
| OR-013 | Mode detection SHOULD be automatic (signal-based) with a manual override. |

### 3.3 Observability

| ID | Requirement |
|----|-------------|
| OR-020 | The orchestrator SHALL log tier classification, routing decisions, and generation outcomes at INFO level. |
| OR-021 | The orchestrator SHOULD emit OTel spans per item and per stage for distributed tracing. |
| OR-022 | The orchestrator SHOULD record tier distribution as an OTel histogram metric. |
| OR-023 | Classification results (tier, reason, signals) SHALL be persisted in item metadata for post-run forensics. |

### 3.4 Pluggable Extension Points

The orchestrator delegates all domain-specific behavior to pluggable protocols:

| Extension Point | Protocol | Purpose |
|----------------|----------|---------|
| Generator | `generate(task, context, targets) → Result` | Artifact production |
| Instrumentor | `emit_span()`, `emit_event()`, `emit_metric()` | Observability |
| Size Estimator | `estimate(task, inputs) → SizeEstimate` | Pre-flight sizing |
| Merge Strategy | `merge(source, target) → MergeResult` | Artifact integration |
| Context Strategy | `resolve(seed) → ResolvedContext` | Context gathering |
| Integration Listener | `on_started()`, `on_completed()`, `on_failed()` | Event hooks |
| Preflight Rule | `evaluate(ctx) → RuleContribution` | Domain constraints |
| Checkpoint | `check(artifacts) → CheckpointResult` | Quality verification |

| ID | Requirement |
|----|-------------|
| OR-030 | All extension points SHALL be defined as runtime-checkable protocols, not abstract base classes. |
| OR-031 | Extension points SHALL support discovery via entry points for third-party plugins. |
| OR-032 | The orchestrator SHALL function with default/no-op implementations for all optional extension points. |

---

## 4. Implementing a New Domain

To instantiate the Prime Contractor paradigm for a new domain, implement these components:

### Step 1: Define Your Work Item

Extend or adapt the generic work item model with domain-specific fields:

```
GenericWorkItem:
  id, name, description, dependencies, status, metadata
  + target_artifacts    → your domain's output identifiers
  + estimated_effort    → your domain's effort metric
```

### Step 2: Define Your Signals

Create a frozen signal dataclass with fields relevant to your domain's complexity dimensions. Every field must have a safe default that degrades classification to MODERATE.

Map your domain's COMPLEX triggers:
- What makes an item genuinely hard? (analogous to: high blast radius, dynamic dispatch, deep inheritance)

Map your domain's SIMPLE eligibility:
- What makes an item trivially straightforward? (analogous to: new file, zero dependencies, small size, full schema coverage)

### Step 3: Implement Signal Extraction

Write an `extract_signals(item, environment) → Signals` function that inspects the work item and the target environment to populate your signal dataclass. This function must never raise — wrap every lookup in try/except with safe defaults.

### Step 4: Configure Thresholds

Create a threshold configuration dataclass with tunable values for each COMPLEX trigger and SIMPLE eligibility condition. Provide sensible defaults that can be overridden per project or per run.

### Step 5: Build Your Generators

Implement the generator protocol for each tier you want to support:

| Tier | What to Build |
|------|--------------|
| TRIVIAL | A template registry of deterministic patterns in your domain |
| SIMPLE | An economy generator (cheap LLM + repair pipeline) |
| MODERATE | Your standard generator (default, reliable) |
| COMPLEX | A premium generator (thorough, expensive, multi-pass) |

You don't need all four. Any missing tier falls back to MODERATE.

### Step 6: Build Your Verifiers

Implement checkpoint types for your domain's quality criteria:
- What does "syntactically valid" mean for your artifacts?
- What does "structurally correct" mean?
- What does "no regressions" mean?

### Step 7: Wire the Orchestrator

Instantiate the orchestrator with your domain's implementations:

```python
workflow = PrimeContractorWorkflow(
    project_root=...,
    code_generator=YourModeratGenerator(),  # default backend
    merge_strategy=YourMergeStrategy(),
    context_strategy=YourContextStrategy(),
)
workflow.enable_complexity_routing(
    config=YourThresholdConfig(),
    tier3_agent="your-premium-backend-spec",
)
```

### Step 8: Define Preflight Rules (Optional)

Register domain-specific rules that classify items by sub-domain and contribute constraints, environment checks, and validators.

---

## 5. Design Principles

These principles emerged from production use of the paradigm across three subsystems (Artisan, Prime Contractor, Micro Prime) and should guide any new domain adaptation.

### 5.1 Mottainai — Waste Nothing

Never regenerate what already exists and is still valid. Check for:
- Previously generated artifacts that pass staleness checks
- Items that failed integration but whose artifacts are fine (retry integration only, skip generation)
- Completed items whose state persisted through a crash

### 5.2 Feature-Serial Continuous Integration

Complete each item through the full loop before starting the next. This eliminates cross-item interference (merge conflicts, stale references, cascading failures from partial state). The cost is sequential execution; the benefit is that failures are isolated and debuggable.

### 5.3 Error-Informed Retry

When an item fails, preserve the error and inject it as context for the next attempt. The generator should address the specific failure, not blindly retry. Generic retry is wasteful; targeted retry is effective.

### 5.4 Safe Defaults Degrade to MODERATE

Every signal extraction, every threshold lookup, every environment check must have a safe default. When data is missing or extraction fails, the item routes to MODERATE — never crashes, never misroutes to TRIVIAL (under-provisioned) or COMPLEX (over-provisioned).

### 5.5 Separate Classification from Extraction

The classifier is a pure function that evaluates signals against thresholds. The signal extractor is a domain-specific function that inspects the environment. Keep them separate so multiple domains can share one classifier while each contributing their own signal vocabulary.

### 5.6 Transactional Integration

Every integration attempt must be reversible. Snapshot the target state before applying changes. If any verification step fails, restore the snapshot. The target environment should never be left in a partially modified state.

### 5.7 Graduated Enforcement

Quality gates should support three enforcement modes:
- **skip** — don't check (development/prototyping)
- **warn** — check and log, but continue (soft launch)
- **block** — check and halt on failure (production)

This lets teams adopt the paradigm incrementally without being blocked by incomplete verifier implementations.

---

## 6. Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Pattern |
|-------------|-------------|----------------|
| Batch-then-integrate | Generating all items before integrating any creates merge conflicts and stale context | Feature-serial: generate, integrate, verify, then next |
| Hardcoded thresholds | Every domain and project has different complexity profiles | Externalized threshold configuration |
| Silent signal extraction failures | Missing signals misroute items to wrong tiers | Never-raise extraction with safe MODERATE defaults and debug logging |
| Bare retry without error context | The generator makes the same mistake again | Error-informed retry: inject prior failure as context |
| Single-tier routing | Every item uses the same expensive model | Four-tier routing: template (free) → economy → standard → premium |
| Coupling classifier to one domain | Can't reuse classification logic across subsystems | Separate signal extraction (domain-specific) from classification (shared) |
| Mutable context during execution | Mid-run configuration changes cause inconsistent behavior | Freeze context at execution start |
| All-or-nothing verification | Single failed check blocks everything | Graduated enforcement (skip/warn/block) per checkpoint type |

---

## 7. Relationship to Existing Subsystems

The Prime Contractor paradigm is already instantiated in three StartD8 subsystems:

| Subsystem | Decomposition Unit | Signal Source | Tiers Used | Generator |
|-----------|-------------------|--------------|------------|-----------|
| **PrimeContractorWorkflow** | `FeatureSpec` (feature-level) | `extract_signals_from_feature()` — disk scanning, import counting | 4 (TRIVIAL–COMPLEX) | `LeadContractorCodeGenerator` (Drafter→Reviewer loop) |
| **Artisan CMR** | `SeedTask` (chunk-level) | `_extract_complexity_signals()` — call graph, MRO, manifest | 3 (mapped to Artisan Tier 1/2/3) | `LLMChunkExecutor` with per-tier model selection |
| **Micro Prime** | `ForwardElementSpec` (element-level) | `classify_element()` — params, decorators, names, docstrings | 4 (TRIVIAL–COMPLEX) | Template registry (TRIVIAL), Ollama + repair (SIMPLE), cloud escalation (MODERATE/COMPLEX) |

All three share:
- The `ComplexityTier` enum from `startd8.complexity`
- The `classify_tier()` function (Artisan and Prime) or bridge to it (Micro Prime via `classify_element_shared()`)
- The `ComplexityRouter` class for tier-to-backend mapping
- The `ComplexityRoutingConfig` for externalized thresholds

---

## 8. Requirement Index

| ID Range | Stage | Count |
|----------|-------|-------|
| DC-001 – DC-022 | Decompose | 12 |
| CL-001 – CL-021 | Classify | 11 |
| RT-001 – RT-012 | Route | 8 |
| GN-001 – GN-032 | Generate | 14 |
| VF-001 – VF-033 | Verify | 16 |
| OR-001 – OR-032 | Orchestrator | 15 |
| **Total** | | **76** |
